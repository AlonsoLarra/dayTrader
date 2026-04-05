import asyncio
import ccxt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from config import settings
from exchange.client import create_exchange, get_balance

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ModeUpdate(BaseModel):
    paper_mode: bool


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


@router.get("/wallet")
async def get_wallet():
    """Fetch real Bitso wallet balance (always reads from real exchange regardless of PAPER_MODE)."""
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
