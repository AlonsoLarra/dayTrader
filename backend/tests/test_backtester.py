"""Phase 0 backtester tests: hermetic, no network.

Covers the pure metrics, the extracted simulation engine (including a
byte-equivalence guard against the legacy single-pass loop and a lookahead
assertion), and walk-forward fold construction + aggregation.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pytest

from backtester import metrics
from backtester.engine import simulate
from backtester.runner import BacktestRunner
from backtester import runner as runner_mod
from backtester import walk_forward as wf_mod
from backtester.walk_forward import WalkForwardBacktester, make_folds
from strategies.base import BaseStrategy, Signal, StrategyResult


# ── Test helpers ──────────────────────────────────────────────────────────


class ScriptedStrategy(BaseStrategy):
    """Emits a preset signal keyed by the current (last) candle index."""

    def __init__(self, signals: Dict[int, Signal], min_candles: int = 2):
        super().__init__({})
        self._signals = signals
        self._min = min_candles
        self.seen_windows: List[list] = []

    @property
    def name(self) -> str:
        return "scripted"

    @property
    def min_candles(self) -> int:
        return self._min

    def analyze(self, ohlcv_data: list) -> StrategyResult:
        self.seen_windows.append([list(c) for c in ohlcv_data])
        idx = len(ohlcv_data) - 1
        return StrategyResult(
            signal=self._signals.get(idx, Signal.HOLD),
            confidence=1.0,
            reasoning="scripted",
        )


def assert_equivalent(new: dict, old: dict) -> None:
    """Compare a metrics dict against the legacy oracle, structure-aware."""
    scalar_keys = ("total_return_pct", "win_rate", "total_trades",
                   "max_drawdown_pct", "sharpe_ratio")
    for key in scalar_keys:
        assert new[key] == pytest.approx(old[key]), key

    assert len(new["equity_curve"]) == len(old["equity_curve"])
    for (nt, nv), (ot, ov) in zip(new["equity_curve"], old["equity_curve"]):
        assert nt == ot
        assert nv == pytest.approx(ov)

    assert len(new["trades"]) == len(old["trades"])
    for nt, ot in zip(new["trades"], old["trades"]):
        assert nt["side"] == ot["side"]
        assert nt["timestamp"] == ot["timestamp"]
        assert nt["price"] == pytest.approx(ot["price"])
        assert nt["amount"] == pytest.approx(ot["amount"])
        if ot["pnl"] is None:
            assert nt["pnl"] is None
        else:
            assert nt["pnl"] == pytest.approx(ot["pnl"])


def make_ohlcv(closes: List[float]) -> List[list]:
    """Synthetic OHLCV; only timestamp and close matter to the engine."""
    return [
        [1_000 + i * 60_000, c, c, c, c, 1.0] for i, c in enumerate(closes)
    ]


def legacy_result(strategy: BaseStrategy, ohlcv: list, initial: float) -> dict:
    """Faithful copy of the pre-refactor runner.run math (regression oracle)."""
    capital = initial
    position: Optional[dict] = None
    trades: List[dict] = []
    equity_curve: List[list] = [[ohlcv[0][0], capital]]
    for i in range(strategy.min_candles, len(ohlcv)):
        result = strategy.analyze(ohlcv[: i + 1])
        price = ohlcv[i][4]
        ts = ohlcv[i][0]
        if result.signal == Signal.BUY and position is None:
            amount = (capital * 0.95) / price
            position = {"side": "buy", "entry_price": price, "amount": amount}
            capital -= amount * price
            trades.append({"side": "buy", "price": price, "amount": amount,
                           "timestamp": ts, "pnl": None})
        elif (result.signal == Signal.SELL and position is not None
              and position["side"] == "buy"):
            pnl = (price - position["entry_price"]) * position["amount"]
            capital += position["amount"] * price
            trades.append({"side": "sell", "price": price,
                           "amount": position["amount"], "timestamp": ts,
                           "pnl": pnl})
            position = None
        held = position["amount"] * price if position else 0.0
        equity_curve.append([ts, capital + held])
    if position is not None:
        last_price = ohlcv[-1][4]
        pnl = (last_price - position["entry_price"]) * position["amount"]
        capital += position["amount"] * last_price
        trades.append({"side": "sell", "price": last_price,
                       "amount": position["amount"],
                       "timestamp": ohlcv[-1][0], "pnl": pnl})
    total_return = (capital - initial) / initial * 100
    sells = [t for t in trades if t["side"] == "sell" and t["pnl"] is not None]
    wins = [t for t in sells if t["pnl"] > 0]
    win_rate = len(wins) / len(sells) if sells else 0.0
    eq = [e[1] for e in equity_curve]
    mdd = 0.0
    peak = eq[0] if eq else initial
    for v in eq:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100
            mdd = max(mdd, dd)
    if len(eq) > 1:
        rets = np.diff(eq) / np.array(eq[:-1], dtype=float)
        std = float(np.std(rets))
        sharpe = float(np.mean(rets) / std * np.sqrt(252)) if std > 0 else 0.0
    else:
        sharpe = 0.0
    return {
        "total_return_pct": round(total_return, 2),
        "win_rate": round(win_rate * 100, 2),
        "total_trades": len(sells),
        "max_drawdown_pct": round(mdd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "equity_curve": equity_curve,
        "trades": trades,
    }


# ── Metrics ───────────────────────────────────────────────────────────────


def test_to_returns_basic():
    assert metrics.to_returns([100.0, 110.0, 99.0]) == pytest.approx([0.1, -0.1])
    assert metrics.to_returns([100.0]) == []


def test_sharpe_zero_variance_is_zero():
    assert metrics.sharpe_ratio([0.01, 0.01, 0.01]) == 0.0
    assert metrics.sharpe_ratio([0.01]) == 0.0


def test_sharpe_positive_for_positive_drift():
    assert metrics.sharpe_ratio([0.01, 0.02, 0.01, 0.03]) > 0.0


def test_sortino_no_downside_is_zero():
    assert metrics.sortino_ratio([0.01, 0.02, 0.03]) == 0.0


def test_sortino_finite_with_downside():
    s = metrics.sortino_ratio([0.02, -0.01, 0.03, -0.02])
    assert np.isfinite(s) and s != 0.0


def test_max_drawdown_known_curve():
    # peak 120 then trough 90 -> 25% drawdown; later new peak, no deeper dd.
    assert metrics.max_drawdown_pct([100, 120, 90, 130]) == pytest.approx(25.0)
    assert metrics.max_drawdown_pct([], fallback=1000) == 0.0


def test_total_return_and_win_rate():
    assert metrics.total_return_pct(1000, 1100) == pytest.approx(10.0)
    assert metrics.total_return_pct(0, 100) == 0.0
    assert metrics.win_rate_pct([1.0, -1.0, 2.0, 0.0]) == pytest.approx(50.0)
    assert metrics.win_rate_pct([]) == 0.0


# ── Engine ────────────────────────────────────────────────────────────────


def test_simulate_round_trip_trade():
    ohlcv = make_ohlcv([10, 10, 10, 12, 15, 15])
    strat = ScriptedStrategy({2: Signal.BUY, 4: Signal.SELL})
    sim = simulate(strat, ohlcv, 1000.0)
    assert [t["side"] for t in sim.trades] == ["buy", "sell"]
    assert sim.trades[1]["pnl"] == pytest.approx(475.0)
    assert sim.final_capital == pytest.approx(1475.0)
    assert sim.closed_pnls == pytest.approx([475.0])


def test_simulate_force_closes_open_position():
    ohlcv = make_ohlcv([10, 10, 10, 12, 18, 20])
    strat = ScriptedStrategy({2: Signal.BUY})
    sim = simulate(strat, ohlcv, 1000.0)
    assert [t["side"] for t in sim.trades] == ["buy", "sell"]
    assert sim.trades[1]["pnl"] == pytest.approx((20 - 10) * 95.0)


def test_simulate_no_lookahead():
    ohlcv = make_ohlcv([1, 2, 3, 4, 5, 6, 7])
    strat = ScriptedStrategy({3: Signal.BUY}, min_candles=2)
    simulate(strat, ohlcv, 1000.0)
    for offset, window in enumerate(strat.seen_windows):
        i = 2 + offset
        assert window == ohlcv[: i + 1]  # exact prefix, never future candles


@pytest.mark.parametrize(
    "closes,signals",
    [
        ([10, 10, 10, 12, 9, 9, 11, 14, 14, 8],
         {2: Signal.BUY, 4: Signal.SELL, 6: Signal.BUY, 8: Signal.SELL}),
        ([5, 5, 6, 7, 8, 9, 10], {2: Signal.BUY}),  # ends with open position
        ([5, 5, 5, 5, 5], {}),                       # no trades at all
    ],
)
def test_engine_equivalent_to_legacy(closes, signals):
    ohlcv = make_ohlcv(closes)
    new_sim = simulate(ScriptedStrategy(dict(signals)), ohlcv, 1000.0)
    new = metrics.summarize(
        new_sim.equity_values, new_sim.closed_pnls, 1000.0,
        new_sim.final_capital,
    ).as_dict()
    new["equity_curve"] = new_sim.equity_curve
    new["trades"] = new_sim.trades
    old = legacy_result(ScriptedStrategy(dict(signals)), ohlcv, 1000.0)
    assert_equivalent(new, old)


# ── Walk-forward folds ────────────────────────────────────────────────────


def test_make_folds_even_split():
    folds = make_folds(n_candles=22, min_candles=2, n_folds=4)
    assert len(folds) == 4
    assert folds[0].oos_start == 2
    assert folds[-1].oos_end == 22
    for a, b in zip(folds, folds[1:]):
        assert a.oos_end == b.oos_start          # contiguous
    assert all(f.candles == 5 for f in folds)    # even


def test_make_folds_remainder_front_loaded():
    folds = make_folds(n_candles=13, min_candles=3, n_folds=4)
    assert [f.candles for f in folds] == [3, 3, 2, 2]
    assert folds[0].oos_start == 3
    assert folds[-1].oos_end == 13


def test_make_folds_rejects_bad_input():
    with pytest.raises(ValueError):
        make_folds(n_candles=5, min_candles=3, n_folds=4)
    with pytest.raises(ValueError):
        make_folds(n_candles=20, min_candles=2, n_folds=0)


# ── Walk-forward + runner end-to-end (network stubbed) ────────────────────


async def test_walk_forward_run_aggregates(monkeypatch):
    ohlcv = make_ohlcv([10, 10, 11, 12, 11, 13, 12, 14, 13, 15, 14, 16])
    monkeypatch.setattr(
        wf_mod, "fetch_ohlcv_range", lambda *a, **k: (ohlcv, None)
    )
    strat = ScriptedStrategy(
        {3: Signal.BUY, 5: Signal.SELL, 8: Signal.BUY, 10: Signal.SELL}
    )
    out = await WalkForwardBacktester().run(
        strat, "BTC/MXN", "1h", "2024-01-01", "2024-02-01",
        initial_capital=1000.0, n_folds=2,
    )
    assert out["n_folds"] == 2
    assert len(out["folds"]) == 2
    agg = out["aggregate"]
    for key in ("mean_return_pct", "std_return_pct", "profitable_folds_pct",
                "worst_fold_drawdown_pct", "mean_sharpe", "mean_sortino"):
        assert key in agg
    assert 0.0 <= agg["profitable_folds_pct"] <= 100.0


async def test_walk_forward_insufficient_data(monkeypatch):
    monkeypatch.setattr(
        wf_mod, "fetch_ohlcv_range",
        lambda *a, **k: (make_ohlcv([1, 2, 3]), None),
    )
    out = await WalkForwardBacktester().run(
        ScriptedStrategy({}), "BTC/MXN", "1h", "2024-01-01", "2024-02-01",
        initial_capital=1000.0, n_folds=4,
    )
    assert "error" in out and out["folds"] == []


async def test_runner_adds_sortino_and_matches_legacy(monkeypatch):
    closes = [10, 10, 10, 12, 9, 9, 11, 14, 14, 8]
    signals = {2: Signal.BUY, 4: Signal.SELL, 6: Signal.BUY, 8: Signal.SELL}
    ohlcv = make_ohlcv(closes)
    monkeypatch.setattr(
        runner_mod, "fetch_ohlcv_range", lambda *a, **k: (ohlcv, None)
    )
    res = await BacktestRunner().run(
        ScriptedStrategy(dict(signals)), "BTC/MXN", "1h",
        "2024-01-01", "2024-02-01", 1000.0,
    )
    assert "sortino_ratio" in res
    old = legacy_result(ScriptedStrategy(dict(signals)), ohlcv, 1000.0)
    assert_equivalent(res, old)


async def test_runner_insufficient_data_reports_error(monkeypatch):
    monkeypatch.setattr(
        runner_mod, "fetch_ohlcv_range",
        lambda *a, **k: (make_ohlcv([1, 2]), "boom"),
    )
    res = await BacktestRunner().run(
        ScriptedStrategy({}, min_candles=50), "BTC/MXN", "1h",
        "2024-01-01", "2024-02-01", 1000.0,
    )
    assert "error" in res
    assert res["sortino_ratio"] == 0.0
    assert res["warning"] == "boom"
