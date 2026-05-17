"""Single-pass historical backtester (Phase 0 — see docs/rl-roadmap.md).

Network orchestration only: fetches OHLCV from the public Bitso API and
delegates trade replay to ``engine.simulate`` and metrics to ``metrics`` —
behaviour is identical to the legacy implementation, core logic is offline
unit-testable.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import ccxt

from backtester.engine import OHLCV, simulate
from backtester.metrics import summarize
from strategies.base import BaseStrategy


def _to_ms(date: str) -> int:
    return int(datetime.strptime(date, "%Y-%m-%d").timestamp() * 1000)


def fetch_ohlcv_range(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
) -> Tuple[OHLCV, Optional[str]]:
    """Page public OHLCV between two dates.

    Returns ``(candles, warning)``. ``warning`` is ``None`` on a clean run; on
    an exchange/network failure it carries the reason and whatever candles were
    collected so far are still returned (no silent ``except``).
    """
    start_ts = _to_ms(start_date)
    end_ts = _to_ms(end_date)

    all_ohlcv: OHLCV = []
    warning: Optional[str] = None
    since = start_ts
    while since < end_ts:
        try:
            page = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=500)
        except ccxt.BaseError as exc:
            warning = f"OHLCV fetch interrupted: {type(exc).__name__}: {exc}"
            break
        if not page:
            break
        all_ohlcv.extend(page)
        last_ts = page[-1][0]
        since = last_ts + 1
        if last_ts >= end_ts:
            break

    in_range = [c for c in all_ohlcv if start_ts <= c[0] <= end_ts]
    return in_range, warning


def _insufficient(have: int, need: int) -> Dict[str, Any]:
    return {
        "total_return_pct": 0.0,
        "win_rate": 0.0,
        "total_trades": 0,
        "max_drawdown_pct": 0.0,
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "equity_curve": [],
        "trades": [],
        "error": f"Insufficient data: {have} candles (need {need})",
    }


class BacktestRunner:
    def __init__(self) -> None:
        self._exchange: ccxt.Exchange = ccxt.bitso()  # public API; no auth

    async def run(
        self,
        strategy: BaseStrategy,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        initial_capital: float,
    ) -> Dict[str, Any]:
        ohlcv, warning = fetch_ohlcv_range(
            self._exchange, symbol, timeframe, start_date, end_date
        )

        if len(ohlcv) < strategy.min_candles:
            result = _insufficient(len(ohlcv), strategy.min_candles)
            if warning:
                result["warning"] = warning
            return result

        sim = simulate(strategy, ohlcv, initial_capital)
        metrics = summarize(
            sim.equity_values,
            sim.closed_pnls,
            initial_capital,
            sim.final_capital,
        )

        result = metrics.as_dict()
        result["equity_curve"] = sim.equity_curve
        result["trades"] = sim.trades
        if warning:
            result["warning"] = warning
        return result
