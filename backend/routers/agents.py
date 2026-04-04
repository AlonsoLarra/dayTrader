from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import ccxt

from database import get_db
from models import AgentState, AgentLog
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
    return [
        {
            "agent_id": s.agent_id,
            "strategy": s.strategy,
            "status": s.status,
            "symbol": s.symbol,
            "budget_allocated": s.budget_allocated,
            "budget_used": s.budget_used,
            "trades_today": s.trades_today,
            "last_signal": s.last_signal,
            "last_tick_at": s.last_tick_at.isoformat() if s.last_tick_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in states
    ]


@router.post("")
async def create_agent(req: CreateAgentRequest, db: AsyncSession = Depends(get_db)):
    try:
        agent_id = await orchestrator.create_agent(req.strategy, req.params, req.budget, req.symbol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"agent_id": agent_id, "status": "created"}


@router.get("/{agent_id}")
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentState).where(AgentState.agent_id == agent_id))
    state = result.scalar_one_or_none()
    if not state:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {
        "agent_id": state.agent_id,
        "strategy": state.strategy,
        "status": state.status,
        "budget_allocated": state.budget_allocated,
        "budget_used": state.budget_used,
        "trades_today": state.trades_today,
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


@router.post("/kill-all")
async def kill_all():
    await orchestrator.kill_all()
    return {"status": "all killed"}


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
