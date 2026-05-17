"""Pure, network-free performance metrics (Phase 0 — see docs/rl-roadmap.md).

Conventions match the legacy runner so /api/backtest results are unchanged:
simple returns (e_t-e_{t-1})/e_{t-1}, population std (ddof=0), annualised by
sqrt(periods_per_year) (default 252).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np


def to_returns(equity: List[float]) -> List[float]:
    """Periodic simple returns of an equity curve.

    Returns an empty list when fewer than two points are supplied. Mirrors the
    legacy ``np.diff(values) / values[:-1]`` computation for equivalence.
    """
    if len(equity) < 2:
        return []
    arr = np.asarray(equity, dtype=float)
    returns = np.diff(arr) / arr[:-1]
    return [float(r) for r in returns]


def sharpe_ratio(
    returns: List[float],
    periods_per_year: int = 252,
    risk_free: float = 0.0,
) -> float:
    """Annualised Sharpe ratio. Returns 0.0 when undefined (no variance)."""
    if len(returns) < 2:
        return 0.0
    arr = np.asarray(returns, dtype=float)
    rf_per_period = risk_free / periods_per_year
    excess = arr - rf_per_period
    std = float(np.std(excess))
    if std <= 0.0:
        return 0.0
    return float(np.mean(excess) / std * np.sqrt(periods_per_year))


def sortino_ratio(
    returns: List[float],
    periods_per_year: int = 252,
    risk_free: float = 0.0,
) -> float:
    """Annualised Sortino ratio (downside-deviation denominator).

    Returns 0.0 when there is no downside dispersion below the target return.
    """
    if len(returns) < 2:
        return 0.0
    arr = np.asarray(returns, dtype=float)
    rf_per_period = risk_free / periods_per_year
    excess = arr - rf_per_period
    downside = np.minimum(excess, 0.0)
    downside_dev = float(np.sqrt(np.mean(downside**2)))
    if downside_dev <= 0.0:
        return 0.0
    return float(np.mean(excess) / downside_dev * np.sqrt(periods_per_year))


def max_drawdown_pct(equity: List[float], fallback: float = 0.0) -> float:
    """Largest peak-to-trough decline of the equity curve, as a percentage.

    ``fallback`` seeds the running peak when ``equity`` is empty, matching the
    legacy behaviour of seeding with ``initial_capital``.
    """
    peak = equity[0] if equity else fallback
    worst = 0.0
    for value in equity:
        if value > peak:
            peak = value
        if peak > 0:
            drawdown = (peak - value) / peak * 100.0
            if drawdown > worst:
                worst = drawdown
    return worst


def total_return_pct(initial_capital: float, final_capital: float) -> float:
    """Total return over the run, as a percentage of starting capital."""
    if initial_capital <= 0:
        return 0.0
    return (final_capital - initial_capital) / initial_capital * 100.0


def win_rate_pct(closed_pnls: List[float]) -> float:
    """Share of closed trades with strictly positive PnL, as a percentage."""
    if not closed_pnls:
        return 0.0
    wins = sum(1 for pnl in closed_pnls if pnl > 0)
    return wins / len(closed_pnls) * 100.0


@dataclass
class MetricsSummary:
    """Aggregated metrics for one equity curve + its closed-trade PnLs."""

    total_return_pct: float
    win_rate: float
    total_trades: int
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_return_pct": round(self.total_return_pct, 2),
            "win_rate": round(self.win_rate, 2),
            "total_trades": self.total_trades,
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "sortino_ratio": round(self.sortino_ratio, 2),
        }


def summarize(
    equity: List[float],
    closed_pnls: List[float],
    initial_capital: float,
    final_capital: float,
    periods_per_year: int = 252,
) -> MetricsSummary:
    """Build a :class:`MetricsSummary` from an equity curve and closed PnLs."""
    returns = to_returns(equity)
    return MetricsSummary(
        total_return_pct=total_return_pct(initial_capital, final_capital),
        win_rate=win_rate_pct(closed_pnls),
        total_trades=len(closed_pnls),
        max_drawdown_pct=max_drawdown_pct(equity, fallback=initial_capital),
        sharpe_ratio=sharpe_ratio(returns, periods_per_year),
        sortino_ratio=sortino_ratio(returns, periods_per_year),
    )
