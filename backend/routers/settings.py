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
from models import PaperWallet, AgentState

router = APIRouter(prefix="/api/settings", tags=["settings"])


async def get_available_budget(db: AsyncSession) -> float:
    """Return how much MXN budget is still unallocated in the wallet."""
    result = await db.execute(select(PaperWallet).limit(1))
    wallet = result.scalar_one_or_none()
    if not wallet:
        wallet = PaperWallet(starting_balance=100.0, updated_at=datetime.utcnow())
        db.add(wallet)
        await db.commit()

    dep_result = await db.execute(
        select(func.sum(AgentState.budget_allocated)).where(AgentState.status != "killed")
    )
    deployed = dep_result.scalar() or 0.0
    return max(0.0, wallet.starting_balance - deployed)

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
    result = await db.execute(select(PaperWallet).limit(1))
    wallet = result.scalar_one_or_none()
    if not wallet:
        # Seed with 100 MXN on first access
        wallet = PaperWallet(starting_balance=100.0, updated_at=datetime.utcnow())
        db.add(wallet)
        await db.commit()

    # Deployed = sum of budget_allocated for all non-killed agents
    dep_result = await db.execute(
        select(func.sum(AgentState.budget_allocated)).where(AgentState.status != "killed")
    )
    deployed = dep_result.scalar() or 0.0

    # In-market = sum of budget_used (capital currently in open positions)
    used_result = await db.execute(
        select(func.sum(AgentState.budget_used)).where(AgentState.status != "killed")
    )
    in_market = used_result.scalar() or 0.0

    available = max(0.0, wallet.starting_balance - deployed)

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
