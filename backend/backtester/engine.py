"""Network-free backtest simulation core, shared by the single-pass and
walk-forward runners (Phase 0 — see docs/rl-roadmap.md).

Lookahead guarantee: on iteration ``i`` the strategy only ever receives
``ohlcv[:i + 1]`` -- never a future candle. Orders execute at candle ``i``'s
close (legacy convention, preserved for result parity); any position still
open after the final candle is force-closed there.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from strategies.base import BaseStrategy, Signal

Candle = List[float]
OHLCV = List[Candle]
Trade = Dict[str, Any]
EquityPoint = List[float]


@dataclass
class SimResult:
    """Outcome of a simulation run over a (sub)sequence of candles."""

    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[EquityPoint] = field(default_factory=list)
    final_capital: float = 0.0

    @property
    def closed_pnls(self) -> List[float]:
        return [
            t["pnl"]
            for t in self.trades
            if t["side"] == "sell" and t["pnl"] is not None
        ]

    @property
    def equity_values(self) -> List[float]:
        return [point[1] for point in self.equity_curve]


def simulate(
    strategy: BaseStrategy,
    ohlcv: OHLCV,
    initial_capital: float,
    start_index: Optional[int] = None,
) -> SimResult:
    """Replay ``strategy`` over ``ohlcv`` starting at ``start_index``.

    ``start_index`` defaults to ``strategy.min_candles`` so earlier candles
    serve purely as indicator warmup. The strategy still sees the full history
    up to each evaluated candle, but trading/equity only spans
    ``[start_index, len(ohlcv))`` -- this is what makes per-fold walk-forward
    windows independent without leaking future data.
    """
    start = strategy.min_candles if start_index is None else start_index
    capital = initial_capital
    position: Optional[Trade] = None
    trades: List[Trade] = []
    equity_curve: List[EquityPoint] = [[ohlcv[0][0], capital]]

    for i in range(start, len(ohlcv)):
        window = ohlcv[: i + 1]
        result = strategy.analyze(window)

        current_candle = ohlcv[i]
        current_price: float = current_candle[4]
        timestamp = current_candle[0]

        if result.signal == Signal.BUY and position is None:
            amount = (capital * 0.95) / current_price
            position = {
                "side": "buy",
                "entry_price": current_price,
                "amount": amount,
                "timestamp": timestamp,
            }
            capital -= amount * current_price
            trades.append(
                {
                    "side": "buy",
                    "price": current_price,
                    "amount": amount,
                    "timestamp": timestamp,
                    "pnl": None,
                }
            )

        elif (
            result.signal == Signal.SELL
            and position is not None
            and position["side"] == "buy"
        ):
            pnl = (current_price - position["entry_price"]) * position["amount"]
            capital += position["amount"] * current_price
            trades.append(
                {
                    "side": "sell",
                    "price": current_price,
                    "amount": position["amount"],
                    "timestamp": timestamp,
                    "pnl": pnl,
                }
            )
            position = None

        held = position["amount"] * current_price if position else 0.0
        equity_curve.append([timestamp, capital + held])

    if position is not None:
        last_price: float = ohlcv[-1][4]
        pnl = (last_price - position["entry_price"]) * position["amount"]
        capital += position["amount"] * last_price
        trades.append(
            {
                "side": "sell",
                "price": last_price,
                "amount": position["amount"],
                "timestamp": ohlcv[-1][0],
                "pnl": pnl,
            }
        )

    return SimResult(
        trades=trades,
        equity_curve=equity_curve,
        final_capital=capital,
    )
