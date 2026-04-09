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

SUPPORTED_PAPER_QUOTES = ("MXN", "BTC", "USD", "USDT")


def _normalize_quote_currency(value: str = "MXN") -> str:
    normalized = (value or "MXN").upper()
    return normalized if normalized in SUPPORTED_PAPER_QUOTES else "MXN"


def _get_starting_balance_for_quote(wallet: PaperWallet, quote_currency: str) -> float:
    quote = _normalize_quote_currency(quote_currency)
    attribute_map = {
        "MXN": "starting_balance",
        "BTC": "btc_balance",
        "USD": "usd_balance",
        "USDT": "usdt_balance",
    }
    return float(getattr(wallet, attribute_map.get(quote, "starting_balance"), 0.0) or 0.0)


def _set_starting_balance_for_quote(wallet: PaperWallet, quote_currency: str, amount: float) -> None:
    quote = _normalize_quote_currency(quote_currency)
    attribute_map = {
        "MXN": "starting_balance",
        "BTC": "btc_balance",
        "USD": "usd_balance",
        "USDT": "usdt_balance",
    }
    setattr(wallet, attribute_map.get(quote, "starting_balance"), float(amount))


async def _get_wallet_snapshot(db: AsyncSession, quote_currency: str = "MXN"):
    normalized_quote = _normalize_quote_currency(quote_currency)
    result = await db.execute(select(PaperWallet).limit(1))
    wallet = result.scalar_one_or_none()
    if not wallet:
        wallet = PaperWallet(
            starting_balance=100.0,
            btc_balance=0.01,
            usd_balance=100.0,
            usdt_balance=100.0,
            updated_at=datetime.utcnow(),
        )
        db.add(wallet)
        await db.commit()
        await db.refresh(wallet)
    else:
        updated_wallet = False
        for attr, default_value in (("btc_balance", 0.01), ("usd_balance", 100.0), ("usdt_balance", 100.0)):
            current = getattr(wallet, attr, None)
            if current is None or float(current or 0.0) <= 0.0:
                setattr(wallet, attr, default_value)
                updated_wallet = True
        if updated_wallet:
            wallet.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(wallet)

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

    snapshots = {
        quote: {
            "starting_balance": _get_starting_balance_for_quote(wallet, quote),
            "deployed": 0.0,
            "in_market": 0.0,
            "realized_pnl": 0.0,
            "available": _get_starting_balance_for_quote(wallet, quote),
        }
        for quote in SUPPORTED_PAPER_QUOTES
    }

    for state in states:
        state_quote = _normalize_quote_currency(
            getattr(state, "quote_currency", None)
            or ((state.symbol or "").split("/")[-1] if getattr(state, "symbol", None) else normalized_quote)
        )
        realized_pnl = pnl_by_agent.get(state.agent_id, 0.0)
        snapshots[state_quote]["realized_pnl"] += realized_pnl

        if state.status == "killed":
            continue

        agent_equity = max(0.0, float(state.budget_allocated or 0.0) + realized_pnl)
        snapshots[state_quote]["deployed"] += agent_equity
        snapshots[state_quote]["in_market"] += float(state.budget_used or 0.0)

    for quote, snapshot in snapshots.items():
        snapshot["available"] = max(
            0.0,
            float(snapshot["starting_balance"] or 0.0) + float(snapshot.get("realized_pnl", 0.0) or 0.0) - float(snapshot["deployed"] or 0.0),
        )
        snapshot.pop("realized_pnl", None)

    return wallet, snapshots, snapshots[normalized_quote]


async def get_available_budget(db: AsyncSession, quote_currency: str = "MXN") -> float:
    """Return how much budget is still unallocated in the requested paper-wallet quote currency."""
    _, _, snapshot = await _get_wallet_snapshot(db, quote_currency)
    return float(snapshot["available"])

class ModeUpdate(BaseModel):
    paper_mode: bool


class PaperWalletUpdate(BaseModel):
    starting_balance: float
    currency: str = "MXN"


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
async def get_paper_wallet(currency: str = "MXN", db: AsyncSession = Depends(get_db)):
    """Return paper wallet balances and per-quote breakdown."""
    wallet, balances, selected = await _get_wallet_snapshot(db, currency)
    normalized_quote = _normalize_quote_currency(currency)

    return {
        "currency": normalized_quote,
        "starting_balance": selected["starting_balance"],
        "deployed": selected["deployed"],
        "in_market": selected["in_market"],
        "available": selected["available"],
        "balances": balances,
    }


@router.post("/paper-wallet")
async def set_paper_wallet(body: PaperWalletUpdate, db: AsyncSession = Depends(get_db)):
    """Set the paper wallet balance for the requested quote currency."""
    if body.starting_balance <= 0:
        raise HTTPException(status_code=400, detail="Balance must be positive")

    normalized_quote = _normalize_quote_currency(body.currency)
    result = await db.execute(select(PaperWallet).limit(1))
    wallet = result.scalar_one_or_none()
    if wallet:
        _set_starting_balance_for_quote(wallet, normalized_quote, body.starting_balance)
        wallet.updated_at = datetime.utcnow()
    else:
        wallet = PaperWallet(
            starting_balance=100.0,
            btc_balance=0.01,
            usd_balance=100.0,
            usdt_balance=100.0,
            updated_at=datetime.utcnow(),
        )
        _set_starting_balance_for_quote(wallet, normalized_quote, body.starting_balance)
        db.add(wallet)

    await db.commit()
    return {"currency": normalized_quote, "starting_balance": _get_starting_balance_for_quote(wallet, normalized_quote)}


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
