import asyncio
import ccxt
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from pydantic import BaseModel
from config import settings
from exchange.client import create_exchange, get_balance
from database import get_db
from models import PaperWallet, AgentState, Trade

router = APIRouter(prefix="/api/settings", tags=["settings"])


async def _get_wallet_snapshot(db: AsyncSession):
    result = await db.execute(select(PaperWallet).limit(1))
    wallet = result.scalar_one_or_none()
    if not wallet:
        wallet = PaperWallet(starting_balance=100.0, updated_at=datetime.utcnow())
        db.add(wallet)
        await db.commit()

    states_result = await db.execute(select(AgentState))
    states = states_result.scalars().all()

    pnl_result = await db.execute(
        select(Trade.agent_id, func.sum(Trade.pnl))
        .where(Trade.pnl.is_not(None))
        .group_by(Trade.agent_id)
    )
    pnl_by_agent = {
        agent_id: float(total or 0.0)
        for agent_id, total in pnl_result.all()
    }

    total_realized_pnl = sum(pnl_by_agent.values())
    deployed = 0.0
    in_market = 0.0
    for state in states:
        if state.status == "killed":
            continue
        agent_equity = max(0.0, float(state.budget_allocated or 0.0) + pnl_by_agent.get(state.agent_id, 0.0))
        deployed += agent_equity
        in_market += float(state.budget_used or 0.0)

    available = max(0.0, float(wallet.starting_balance or 0.0) + total_realized_pnl - deployed)
    return wallet, deployed, in_market, available


async def get_available_budget(db: AsyncSession) -> float:
    """Return how much MXN budget is still unallocated in the wallet."""
    _, _, _, available = await _get_wallet_snapshot(db)
    return available

class ModeUpdate(BaseModel):
    paper_mode: bool


class PaperWalletUpdate(BaseModel):
    starting_balance: float


@router.get("/mode")
async def get_mode():
    return {
        "paper_mode": settings.PAPER_MODE,
        "exchange": settings.EXCHANGE,
    }


@router.post("/mode")
async def set_mode(body: ModeUpdate):
    settings.PAPER_MODE = body.paper_mode
    return {"paper_mode": settings.PAPER_MODE}


@router.get("/paper-wallet")
async def get_paper_wallet(db: AsyncSession = Depends(get_db)):
    """Return paper wallet balance and breakdown."""
    wallet, deployed, in_market, available = await _get_wallet_snapshot(db)

    return {
        "starting_balance": wallet.starting_balance,
        "deployed": deployed,
        "in_market": in_market,
        "available": available,
    }


@router.post("/paper-wallet")
async def set_paper_wallet(body: PaperWalletUpdate, db: AsyncSession = Depends(get_db)):
    """Set the paper wallet starting balance."""
    if body.starting_balance <= 0:
        raise HTTPException(status_code=400, detail="Balance must be positive")
    result = await db.execute(select(PaperWallet).limit(1))
    wallet = result.scalar_one_or_none()
    if wallet:
        wallet.starting_balance = body.starting_balance
        wallet.updated_at = datetime.utcnow()
    else:
        wallet = PaperWallet(starting_balance=body.starting_balance, updated_at=datetime.utcnow())
        db.add(wallet)
    await db.commit()
    return {"starting_balance": wallet.starting_balance}


@router.get("/wallet")
async def get_wallet():
    """Fetch real Bitso wallet balance."""
    if not settings.BITSO_API_KEY or not settings.BITSO_API_SECRET:
        raise HTTPException(status_code=400, detail="Bitso API keys not configured in .env")
    try:
        loop = asyncio.get_event_loop()
        exchange = ccxt.bitso({
            "apiKey": settings.BITSO_API_KEY,
            "secret": settings.BITSO_API_SECRET,
        })
        balance = await loop.run_in_executor(None, exchange.fetch_balance)
        # Use ccxt-normalized format — skip meta keys
        _skip = {"info", "free", "used", "total", "datetime", "timestamp"}
        non_zero = {
            currency: {
                "free": float(vals.get("free") or 0),
                "used": float(vals.get("used") or 0),
                "total": float(vals.get("total") or 0),
            }
            for currency, vals in balance.items()
            if isinstance(vals, dict)
            and currency not in _skip
            and float(vals.get("total") or 0) > 0
        }
        return {"balances": non_zero, "paper_mode": settings.PAPER_MODE}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Bitso API error: {str(e)}")
