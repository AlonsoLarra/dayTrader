import json
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case

from database import get_db
from models import Trade, AgentState, AgentLog

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("/summary")
async def trade_summary(db: AsyncSession = Depends(get_db)):
    # Trade stats — P&L is already net of fees in the recorded values
    result = await db.execute(
        select(
            func.count(Trade.id).label("total_trades"),
            func.sum(Trade.pnl).label("total_pnl"),
            func.sum(Trade.fee).label("total_fees"),
            func.sum(case((Trade.pnl > 0, 1), else_=0)).label("winning_trades"),
        ).where(Trade.pnl.is_not(None))
    )
    row = result.first()
    total_trades = row.total_trades or 0
    total_pnl = float(row.total_pnl or 0)
    total_fees = float(row.total_fees or 0)
    winning = row.winning_trades or 0
    win_rate = (winning / total_trades * 100) if total_trades > 0 else 0.0

    # Capital summary from agent states
    agents_result = await db.execute(
        select(
            func.sum(AgentState.budget_allocated).label("total_allocated"),
            func.sum(AgentState.budget_used).label("total_used"),
            func.count(AgentState.id).label("total_agents"),
            func.sum(case((AgentState.status == "running", 1), else_=0)).label("running_agents"),
        ).where(AgentState.status != "killed")
    )
    arow = agents_result.first()
    total_allocated = float(arow.total_allocated or 0)
    total_used = float(arow.total_used or 0)
    total_agents = int(arow.total_agents or 0)
    running_agents = int(arow.running_agents or 0)

    return {
        "total_trades": total_trades,
        "total_pnl": total_pnl,
        "total_fees": total_fees,
        "win_rate": round(win_rate, 2),
        "winning_trades": winning,
        "total_allocated": total_allocated,
        "total_deployed": total_used,
        "total_agents": total_agents,
        "running_agents": running_agents,
    }
    # Trade stats
    result = await db.execute(
        select(
            func.count(Trade.id).label("total_trades"),
            func.sum(Trade.pnl).label("total_pnl"),
            func.sum(case((Trade.pnl > 0, 1), else_=0)).label("winning_trades"),
        ).where(Trade.pnl.is_not(None))
    )
    row = result.first()
    total_trades = row.total_trades or 0
    total_pnl = float(row.total_pnl or 0)
    winning = row.winning_trades or 0
    win_rate = (winning / total_trades * 100) if total_trades > 0 else 0.0

    # Capital summary from agent states
    agents_result = await db.execute(
        select(
            func.sum(AgentState.budget_allocated).label("total_allocated"),
            func.sum(AgentState.budget_used).label("total_used"),
            func.count(AgentState.id).label("total_agents"),
            func.sum(case((AgentState.status == "running", 1), else_=0)).label("running_agents"),
        ).where(AgentState.status != "killed")
    )
    arow = agents_result.first()
    total_allocated = float(arow.total_allocated or 0)
    total_used = float(arow.total_used or 0)
    total_agents = int(arow.total_agents or 0)
    running_agents = int(arow.running_agents or 0)

    return {
        "total_trades": total_trades,
        "total_pnl": total_pnl,
        "win_rate": round(win_rate, 2),
        "winning_trades": winning,
        "total_allocated": total_allocated,
        "total_deployed": total_used,
        "total_agents": total_agents,
        "running_agents": running_agents,
    }


@router.get("/export")
async def export_trades(
    limit_days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Export all trades with agent reasoning for LLM analysis."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=limit_days)

    trades_result = await db.execute(
        select(Trade)
        .where(Trade.timestamp >= cutoff)
        .order_by(Trade.timestamp.asc())
    )
    trades = trades_result.scalars().all()

    if not trades:
        agent_ids = []
    else:
        agent_ids = list({t.agent_id for t in trades})

    logs_result = await db.execute(
        select(AgentLog)
        .where(AgentLog.agent_id.in_(agent_ids))
        .where(AgentLog.timestamp >= cutoff)
        .order_by(AgentLog.timestamp.asc())
    )
    all_logs = logs_result.scalars().all()

    logs_by_agent: dict[str, list] = {}
    for log in all_logs:
        logs_by_agent.setdefault(log.agent_id, []).append(log)

    agents_result = await db.execute(
        select(AgentState).where(AgentState.agent_id.in_(agent_ids))
    )
    agent_states = {s.agent_id: s for s in agents_result.scalars().all()}

    trades_by_agent: dict[str, list] = {}
    for t in trades:
        trades_by_agent.setdefault(t.agent_id, []).append(t)

    total_pnl = sum(t.pnl for t in trades if t.pnl is not None)
    total_fees = sum(t.fee for t in trades if t.fee is not None)
    winning = sum(1 for t in trades if t.pnl is not None and t.pnl > 0)
    losing = sum(1 for t in trades if t.pnl is not None and t.pnl <= 0)
    total_closed = winning + losing
    win_rate = round(winning / total_closed, 4) if total_closed > 0 else 0.0

    agents_out = []
    for aid in agent_ids:
        agent_trades = trades_by_agent.get(aid, [])
        agent_logs = logs_by_agent.get(aid, [])
        state = agent_states.get(aid)

        trades_out = []
        for t in agent_trades:
            trade_ts = t.timestamp.replace(tzinfo=timezone.utc) if t.timestamp.tzinfo is None else t.timestamp
            window = timedelta(minutes=2)
            reasoning = [
                {"timestamp": lg.timestamp.isoformat(), "decision": lg.decision, "reasoning": lg.reasoning}
                for lg in agent_logs
                if lg.decision and lg.reasoning
                and abs((lg.timestamp.replace(tzinfo=timezone.utc) if lg.timestamp.tzinfo is None else lg.timestamp) - trade_ts) <= window
                and lg.decision.lower() == t.side.lower()
            ]
            trades_out.append({
                "trade_id": t.id,
                "timestamp": t.timestamp.isoformat(),
                "side": t.side,
                "symbol": t.symbol,
                "amount": t.amount,
                "price": t.price,
                "pnl": t.pnl,
                "fee": t.fee,
                "mode": t.mode,
                "strategy": t.strategy,
                "reasoning_at_entry": reasoning,
            })

        agent_pnl = sum(t.pnl for t in agent_trades if t.pnl is not None)
        agents_out.append({
            "agent_id": aid,
            "symbol": state.symbol if state else "unknown",
            "strategy": state.strategy if state else "unknown",
            "quote_currency": state.quote_currency if state else "USD",
            "budget_allocated": state.budget_allocated if state else 0.0,
            "realized_pnl": round(agent_pnl, 6),
            "trades": trades_out,
        })

    date_from = trades[0].timestamp.isoformat() if trades else None
    date_to = trades[-1].timestamp.isoformat() if trades else None

    document = {
        "export_metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_trades": len(trades),
            "total_agents": len(agent_ids),
            "limit_days": limit_days,
            "date_range": {"from": date_from, "to": date_to},
            "system_prompt_hint": (
                "This is a complete trading session export from an autonomous crypto day-trading bot. "
                "Each trade entry includes the bot's reasoning at the time it made the decision. "
                "Use this to analyze: (1) which signals led to profitable trades, "
                "(2) where the bot's reasoning was flawed, "
                "(3) patterns in losing vs winning trades, "
                "(4) whether the strategy parameters should be adjusted."
            ),
        },
        "summary": {
            "total_pnl": round(total_pnl, 6),
            "total_fees": round(total_fees, 6),
            "win_rate": win_rate,
            "winning_trades": winning,
            "losing_trades": losing,
            "total_closed_trades": total_closed,
        },
        "agents": agents_out,
    }

    content = json.dumps(document, indent=2, default=str)
    return JSONResponse(
        content=document,
        headers={"Content-Disposition": "attachment; filename=daytrader_export.json"},
    )


@router.get("")
async def list_trades(
    agent_id: str = None,
    strategy: str = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    query = select(Trade)
    if agent_id:
        query = query.where(Trade.agent_id == agent_id)
    if strategy:
        query = query.where(Trade.strategy == strategy)
    query = query.order_by(Trade.timestamp.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    trades = result.scalars().all()
    return [
        {
            "id": t.id,
            "agent_id": t.agent_id,
            "symbol": t.symbol,
            "side": t.side,
            "amount": t.amount,
            "price": t.price,
            "timestamp": t.timestamp.isoformat(),
            "pnl": t.pnl,
            "fee": t.fee,
            "mode": t.mode,
            "strategy": t.strategy,
        }
        for t in trades
    ]
