"""Walk-forward backtester (Phase 0 — see docs/rl-roadmap.md).

Splits the evaluatable region into contiguous, non-overlapping out-of-sample
folds and replays the strategy on each independently with fresh capital.
Earlier candles are indicator warmup only; folds never overlap and the
strategy never sees a future candle (lookahead-safe — see engine). Per-fold
metrics expose consistency rather than one lucky path, and the OOS
segmentation is where later RL train/validation splits will attach.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import ccxt

from backtester.engine import OHLCV, simulate
from backtester.metrics import summarize
from backtester.runner import fetch_ohlcv_range
from strategies.base import BaseStrategy


@dataclass
class Fold:
    """One out-of-sample segment, as half-open candle indices."""

    index: int
    oos_start: int
    oos_end: int  # exclusive

    @property
    def candles(self) -> int:
        return self.oos_end - self.oos_start


def make_folds(n_candles: int, min_candles: int, n_folds: int) -> List[Fold]:
    """Partition ``[min_candles, n_candles)`` into ``n_folds`` OOS segments.

    Folds are contiguous and non-overlapping; remainder candles are spread
    over the earliest folds so sizes differ by at most one. Raises
    ``ValueError`` if the region cannot supply at least one candle per fold.
    """
    if n_folds < 1:
        raise ValueError("n_folds must be >= 1")
    region = n_candles - min_candles
    if region < n_folds:
        raise ValueError(
            f"Need >= {min_candles + n_folds} candles for {n_folds} folds; "
            f"have {n_candles}"
        )
    base, extra = divmod(region, n_folds)
    folds: List[Fold] = []
    cursor = min_candles
    for i in range(n_folds):
        size = base + (1 if i < extra else 0)
        folds.append(Fold(index=i, oos_start=cursor, oos_end=cursor + size))
        cursor += size
    return folds


class WalkForwardBacktester:
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
        n_folds: int = 4,
    ) -> Dict[str, Any]:
        ohlcv, warning = fetch_ohlcv_range(
            self._exchange, symbol, timeframe, start_date, end_date
        )

        try:
            folds = make_folds(len(ohlcv), strategy.min_candles, n_folds)
        except ValueError as exc:
            err: Dict[str, Any] = {"error": str(exc), "folds": [],
                                   "aggregate": {}}
            if warning:
                err["warning"] = warning
            return err

        fold_reports: List[Dict[str, Any]] = []
        returns: List[float] = []
        drawdowns: List[float] = []
        sharpes: List[float] = []
        sortinos: List[float] = []

        for fold in folds:
            sim = simulate(
                strategy,
                ohlcv[: fold.oos_end],
                initial_capital,
                start_index=fold.oos_start,
            )
            metrics = summarize(
                sim.equity_values,
                sim.closed_pnls,
                initial_capital,
                sim.final_capital,
            )
            report = metrics.as_dict()
            report["fold"] = fold.index
            report["candles"] = fold.candles
            fold_reports.append(report)

            returns.append(metrics.total_return_pct)
            drawdowns.append(metrics.max_drawdown_pct)
            sharpes.append(metrics.sharpe_ratio)
            sortinos.append(metrics.sortino_ratio)

        n = len(returns)
        mean_return = sum(returns) / n
        variance = sum((r - mean_return) ** 2 for r in returns) / n
        profitable = sum(1 for r in returns if r > 0)

        result: Dict[str, Any] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "n_folds": n,
            "initial_capital": initial_capital,
            "folds": fold_reports,
            "aggregate": {
                "mean_return_pct": round(mean_return, 2),
                "std_return_pct": round(variance**0.5, 2),
                "profitable_folds_pct": round(profitable / n * 100, 2),
                "worst_fold_drawdown_pct": round(max(drawdowns), 2),
                "mean_sharpe": round(sum(sharpes) / n, 2),
                "mean_sortino": round(sum(sortinos) / n, 2),
            },
        }
        if warning:
            result["warning"] = warning
        return result
