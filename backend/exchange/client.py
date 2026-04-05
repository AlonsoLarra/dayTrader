import asyncio
import ccxt
from config import settings
from exchange.paper_trading import PaperExchange


def create_exchange(budget: float = None):
    """Creates an exchange instance based on config."""
    if settings.PAPER_MODE:
        # Seed with the agent's budget so balance is realistic
        initial = budget if budget and budget > 0 else settings.INITIAL_BUDGET
        return PaperExchange(symbol=settings.TRADING_PAIR, initial_balance=initial)
    elif settings.EXCHANGE == "bitso":
        return ccxt.bitso(
            {
                "apiKey": settings.BITSO_API_KEY,
                "secret": settings.BITSO_API_SECRET,
            }
        )
    elif settings.EXCHANGE == "binance":
        return ccxt.binance(
            {
                "apiKey": settings.BINANCE_API_KEY,
                "secret": settings.BINANCE_API_SECRET,
            }
        )
    else:
        return PaperExchange(symbol=settings.TRADING_PAIR, initial_balance=settings.INITIAL_BUDGET * 10)


def _run_sync(fn, *args, **kwargs):
    """Run a synchronous ccxt call in a thread pool executor."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, lambda: fn(*args, **kwargs))


async def get_balance(exchange) -> dict:
    try:
        if isinstance(exchange, PaperExchange):
            return exchange.fetch_balance()
        result = await _run_sync(exchange.fetch_balance)
        return result
    except Exception as e:
        return {"total": {}, "free": {}, "error": str(e)}


async def get_ticker(exchange, symbol: str) -> dict:
    try:
        if isinstance(exchange, PaperExchange):
            return exchange.fetch_ticker(symbol)
        result = await _run_sync(exchange.fetch_ticker, symbol)
        return result
    except Exception as e:
        return {"last": 0, "error": str(e)}


async def get_ohlcv(exchange, symbol: str, timeframe: str = "1h", limit: int = 100) -> list:
    try:
        if isinstance(exchange, PaperExchange):
            return exchange.fetch_ohlcv(symbol, timeframe, limit)
        result = await _run_sync(exchange.fetch_ohlcv, symbol, timeframe, None, limit)
        return result
    except Exception as e:
        return []


async def place_order(exchange, symbol: str, side: str, amount: float, price: float = None) -> dict:
    try:
        if isinstance(exchange, PaperExchange):
            return exchange.create_order(symbol, "market", side, amount, price)
        order_type = "limit" if price else "market"
        result = await _run_sync(exchange.create_order, symbol, order_type, side, amount, price)
        return result
    except Exception as e:
        raise Exception(str(e))
