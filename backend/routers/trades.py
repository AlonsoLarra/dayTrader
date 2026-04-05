from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case

from database import get_db
from models import Trade, AgentState

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("/summary")
async def trade_summary(db: AsyncSession = Depends(get_db)):
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
            "mode": t.mode,
            "strategy": t.strategy,
        }
        for t in trades
    ]
