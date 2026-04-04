from fastapi import APIRouter
from pydantic import BaseModel

from strategies.ma_crossover import MACrossoverStrategy
from strategies.rsi import RSIStrategy
from backtester.runner import BacktestRunner

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

STRATEGY_MAP = {
    "ma_crossover": MACrossoverStrategy,
    "rsi": RSIStrategy,
}


class BacktestRequest(BaseModel):
    strategy: str
    params: dict = {}
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    start_date: str = "2024-01-01"
    end_date: str = "2024-06-01"
    initial_capital: float = 10000.0


@router.post("")
async def run_backtest(req: BacktestRequest):
    strategy_cls = STRATEGY_MAP.get(req.strategy)
    if not strategy_cls:
        return {"error": f"Unknown strategy: {req.strategy}"}

    strategy = strategy_cls(req.params)
    runner = BacktestRunner()

    result = await runner.run(
        strategy=strategy,
        symbol=req.symbol,
        timeframe=req.timeframe,
        start_date=req.start_date,
        end_date=req.end_date,
        initial_capital=req.initial_capital,
    )
    return result
