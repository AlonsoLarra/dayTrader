from fastapi import APIRouter
from datetime import datetime
from typing import Optional
import asyncio
import ccxt

router = APIRouter(prefix="/api/prices", tags=["prices"])

SYMBOLS = ["BTC/MXN", "ETH/MXN", "SOL/MXN", "XRP/MXN", "AVAX/MXN", "LTC/MXN"]

_exchange = ccxt.bitso({"enableRateLimit": True})

_price_cache: dict = {}
_cache_ts: Optional[datetime] = None
_CACHE_TTL_SECONDS = 30


def _fetch_one(symbol: str) -> dict:
    try:
        t = _exchange.fetch_ticker(symbol)
        last = t.get("last") or 0
        # Bitso doesn't expose a normalized 'open' through ccxt.
        # Use change_24 (absolute MXN change) from the raw info payload instead.
        info = t.get("info", {})
        change_24 = info.get("change_24")
        if change_24 is not None and last:
            try:
                change_24 = float(change_24)
                prev = last - change_24
                change_pct = (change_24 / prev * 100) if prev else 0.0
            except (TypeError, ZeroDivisionError):
                change_pct = 0.0
        else:
            # Fallback: try ccxt-normalized percentage field
            change_pct = float(t.get("percentage") or 0.0)
        return symbol, {
            "last": last,
            "change_pct": round(change_pct, 2),
            "high": t.get("high") or 0,
            "low": t.get("low") or 0,
        }
    except Exception:
        return symbol, None


@router.get("")
async def get_prices():
    global _price_cache, _cache_ts

    now = datetime.utcnow()
    if _cache_ts and (now - _cache_ts).total_seconds() < _CACHE_TTL_SECONDS and _price_cache:
        return {"prices": _price_cache, "timestamp": _cache_ts.isoformat()}

    loop = asyncio.get_event_loop()
    results = await asyncio.gather(
        *[loop.run_in_executor(None, _fetch_one, sym) for sym in SYMBOLS],
        return_exceptions=True,
    )

    prices: dict = {}
    for r in results:
        if isinstance(r, Exception) or r is None:
            continue
        sym, data = r
        if data:
            prices[sym] = data

    if prices:
        _price_cache = prices
        _cache_ts = now
    else:
        prices = _price_cache or {}

    return {"prices": prices, "timestamp": now.isoformat()}


@router.get("/{symbol}/ohlcv")
async def get_ohlcv(symbol: str, timeframe: str = "1h", limit: int = 50):
    canonical = symbol.replace("-", "/")
    loop = asyncio.get_event_loop()
    try:
        raw = await loop.run_in_executor(
            None, lambda: _exchange.fetch_ohlcv(canonical, timeframe=timeframe, limit=limit)
        )
        data = [[c[0], c[1], c[2], c[3], c[4], c[5]] for c in raw]
    except Exception:
        data = []
    return {"symbol": canonical, "timeframe": timeframe, "data": data}
