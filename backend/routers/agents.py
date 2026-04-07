from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
import ccxt

from database import get_db
from models import AgentState, AgentLog, Trade
from routers.settings import get_available_budget
from agents.orchestrator import orchestrator

router = APIRouter(prefix="/api/agents", tags=["agents"])

SUPPORTED_SYMBOLS = [
    "BTC/MXN", "ETH/MXN", "SOL/MXN", "XRP/MXN",
    "AVAX/MXN", "LTC/MXN", "BCH/MXN", "MANA/MXN", "TRX/MXN", "BAT/MXN",
]


@router.get("/markets")
async def list_markets():
    """Return tradeable symbols on Bitso."""
    return {"symbols": SUPPORTED_SYMBOLS}


class CreateAgentRequest(BaseModel):
    strategy: str
    params: dict = {}
    budget: float = 1000.0
    symbol: Optional[str] = None


@router.get("")
async def list_agents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentState))
    states = result.scalars().all()

    pnl_result = await db.execute(
        select(Trade.agent_id, func.sum(Trade.pnl))
        .where(Trade.pnl.is_not(None))
        .group_by(Trade.agent_id)
    )
    pnl_by_agent = {
        agent_id: float(total or 0.0)
        for agent_id, total in pnl_result.all()
    }

    return [
        {
            "agent_id": s.agent_id,
            "strategy": s.strategy,
            "status": s.status,
            "symbol": s.symbol,
            "budget_allocated": s.budget_allocated,
            "budget_used": s.budget_used,
            "trades_today": s.trades_today,
            "losses_today": getattr(s, 'losses_today', 0) or 0,
            "realized_pnl_today": getattr(s, 'realized_pnl_today', 0.0) or 0.0,
            "realized_pnl_total": pnl_by_agent.get(s.agent_id, 0.0),
            "last_signal": s.last_signal,
            "last_tick_at": s.last_tick_at.isoformat() if s.last_tick_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in states
    ]


@router.post("")
async def create_agent(req: CreateAgentRequest, db: AsyncSession = Depends(get_db)):
    available = await get_available_budget(db)
    if req.budget > available:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient wallet balance. Requested ${req.budget:.2f} MXN but only ${available:.2f} MXN available.",
        )
    try:
        agent_id, chosen_strategy = await orchestrator.create_agent(req.strategy, req.params, req.budget, req.symbol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"agent_id": agent_id, "strategy": chosen_strategy, "status": "created"}



@router.post("/kill-all")
async def kill_all():
    await orchestrator.kill_all()
    return {"status": "all killed"}


@router.get("/positions")
async def get_all_positions():
    """Return all open positions across all running agents with current price."""
    from exchange.client import get_ticker, create_exchange
    positions = []
    exchange = create_exchange()
    for agent_id, agent in orchestrator._agents.items():
        if agent.open_position:
            pos = agent.open_position
            try:
                ticker = await get_ticker(exchange, agent.symbol)
                current_price = ticker.get("last", 0)
                unrealized_pnl = (current_price - pos["price"]) * pos["amount"] if current_price else None
                proceeds = current_price * pos["amount"] if current_price else None
                pnl_pct = ((current_price - pos["price"]) / pos["price"] * 100) if current_price and pos["price"] else None
            except Exception:
                current_price = None
                unrealized_pnl = None
                proceeds = None
                pnl_pct = None
            positions.append({
                "agent_id": agent_id,
                "symbol": agent.symbol,
                "strategy": agent.strategy.name,
                "side": pos["side"],
                "amount": pos["amount"],
                "entry_price": pos["price"],
                "current_price": current_price,
                "unrealized_pnl": unrealized_pnl,
                "pnl_pct": pnl_pct,
                "proceeds_if_sold": proceeds,
                "cost_basis": pos["amount"] * pos["price"],
            })
    return {"positions": positions}

@router.get("/{agent_id}")
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentState).where(AgentState.agent_id == agent_id))
    state = result.scalar_one_or_none()
    if not state:
        raise HTTPException(status_code=404, detail="Agent not found")

    pnl_result = await db.execute(
        select(func.sum(Trade.pnl)).where(
            Trade.agent_id == agent_id,
            Trade.pnl.is_not(None),
        )
    )
    realized_pnl_total = float(pnl_result.scalar() or 0.0)

    return {
        "agent_id": state.agent_id,
        "strategy": state.strategy,
        "status": state.status,
        "symbol": state.symbol,
        "budget_allocated": state.budget_allocated,
        "budget_used": state.budget_used,
        "trades_today": state.trades_today,
        "losses_today": getattr(state, 'losses_today', 0) or 0,
        "realized_pnl_today": getattr(state, 'realized_pnl_today', 0.0) or 0.0,
        "realized_pnl_total": realized_pnl_total,
        "last_signal": state.last_signal,
        "last_tick_at": state.last_tick_at.isoformat() if state.last_tick_at else None,
        "created_at": state.created_at.isoformat() if state.created_at else None,
    }


@router.post("/{agent_id}/start")
async def start_agent(agent_id: str):
    try:
        await orchestrator.start_agent(agent_id)
        return {"status": "started"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{agent_id}/stop")
async def stop_agent(agent_id: str):
    await orchestrator.stop_agent(agent_id)
    return {"status": "stopped"}


@router.post("/{agent_id}/kill")
async def kill_agent(agent_id: str):
    await orchestrator.kill_agent(agent_id)
    return {"status": "killed"}




@router.post("/{agent_id}/force-sell")
async def force_sell(agent_id: str):
    """Manually close an agent's open position at market price."""
    agent = orchestrator._agents.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        result = await agent.force_sell()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Remove a killed agent from the database entirely."""
    result = await db.execute(select(AgentState).where(AgentState.agent_id == agent_id))
    state = result.scalar_one_or_none()
    if not state:
        raise HTTPException(status_code=404, detail="Agent not found")
    if state.status not in ("killed", "stopped"):
        raise HTTPException(status_code=400, detail="Only killed or stopped agents can be deleted")
    await db.delete(state)
    await db.commit()
    # Also remove from orchestrator memory
    orchestrator._agents.pop(agent_id, None)
    orchestrator._tasks.pop(agent_id, None)
    return {"status": "deleted"}


@router.get("/{agent_id}/logs")
async def get_agent_logs(
    agent_id: str,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentLog)
        .where(AgentLog.agent_id == agent_id)
        .order_by(AgentLog.timestamp.desc())
        .offset(skip)
        .limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "id": lg.id,
            "agent_id": lg.agent_id,
            "timestamp": lg.timestamp.isoformat(),
            "level": lg.level,
            "message": lg.message,
            "decision": lg.decision,
            "reasoning": lg.reasoning,
        }
        for lg in logs
    ]
