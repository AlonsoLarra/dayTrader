"""
Unit tests for paper trading logic — fee, spread, min order enforcement.
These run without a network connection (PaperExchange uses real Bitso prices
only for fetch_ticker; we mock that to make tests hermetic).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch
from exchange.paper_trading import PaperExchange

SYMBOL = "XRP/MXN"
PRICE = 10.0  # 10 MXN per XRP — simple round number


def _make_exchange(balance=200.0):
    """Create a PaperExchange with a mocked ticker so no network is needed."""
    ex = PaperExchange(symbol=SYMBOL, initial_balance=balance)
    return ex


def _ticker(price):
    return {"last": price, "symbol": SYMBOL, "timestamp": 0}


def _ohlcv_from_closes(closes, volume=100.0):
    rows = []
    for idx, close in enumerate(closes):
        rows.append([idx, close, close * 1.01, close * 0.99, close, volume])
    return rows


# ── Balance ────────────────────────────────────────────────────────────────────

def test_initial_mxn_balance():
    ex = _make_exchange(200.0)
    bal = ex.fetch_balance()
    assert bal["free"]["MXN"] == 200.0


def test_initial_crypto_balance_zero():
    ex = _make_exchange(200.0)
    bal = ex.fetch_balance()
    assert bal["free"]["XRP"] == 0.0


# ── Buy ────────────────────────────────────────────────────────────────────────

def test_buy_reduces_mxn_balance():
    ex = _make_exchange(200.0)
    with patch.object(ex, "fetch_ticker", return_value=_ticker(PRICE)):
        ex.create_order(SYMBOL, "market", "buy", 2.0, PRICE)
    bal = ex.fetch_balance()
    assert bal["free"]["MXN"] < 200.0


def test_buy_adds_crypto_balance():
    ex = _make_exchange(200.0)
    with patch.object(ex, "fetch_ticker", return_value=_ticker(PRICE)):
        ex.create_order(SYMBOL, "market", "buy", 2.0, PRICE)
    bal = ex.fetch_balance()
    assert bal["free"]["XRP"] == 2.0


def test_buy_order_has_fee():
    ex = _make_exchange(200.0)
    with patch.object(ex, "fetch_ticker", return_value=_ticker(PRICE)):
        order = ex.create_order(SYMBOL, "market", "buy", 2.0, PRICE)
    assert "fee" in order
    assert order["fee"]["cost"] > 0


def test_buy_cost_higher_than_notional_due_to_fee():
    """The total MXN spent should be > amount * price because of the taker fee."""
    ex = _make_exchange(200.0)
    amount = 2.0
    with patch.object(ex, "fetch_ticker", return_value=_ticker(PRICE)):
        # patch spread to 0 for clean math
        with patch.dict("exchange.paper_trading.SPREAD", {SYMBOL: 0.0}):
            order = ex.create_order(SYMBOL, "market", "buy", amount, PRICE)
    # cost = notional (spread may add a tiny bit); fee is on top
    fee = order["fee"]["cost"]
    assert fee > 0
    mxn_remaining = ex.fetch_balance()["free"]["MXN"]
    mxn_spent = 200.0 - mxn_remaining
    assert mxn_spent > amount * PRICE  # spent more than notional


# ── Sell ───────────────────────────────────────────────────────────────────────

def test_sell_increases_mxn_balance():
    ex = _make_exchange(200.0)
    with patch.object(ex, "fetch_ticker", return_value=_ticker(PRICE)):
        ex.create_order(SYMBOL, "market", "buy", 2.0, PRICE)
    mxn_after_buy = ex.fetch_balance()["free"]["MXN"]
    with patch.object(ex, "fetch_ticker", return_value=_ticker(PRICE)):
        ex.create_order(SYMBOL, "market", "sell", 2.0, PRICE)
    mxn_after_sell = ex.fetch_balance()["free"]["MXN"]
    assert mxn_after_sell > mxn_after_buy


def test_round_trip_loses_to_fees():
    """After buy + sell at same mid price, balance is lower due to taker fees."""
    ex = _make_exchange(200.0)
    with patch.object(ex, "fetch_ticker", return_value=_ticker(PRICE)):
        ex.create_order(SYMBOL, "market", "buy", 2.0, PRICE)
        ex.create_order(SYMBOL, "market", "sell", 2.0, PRICE)
    final = ex.fetch_balance()["free"]["MXN"]
    assert final < 200.0     # lost to fees
    assert final > 180.0     # but not catastrophically


def test_restored_position_can_sell_after_restart():
    """A paper-traded position restored from DB after a restart must still be sellable."""
    ex = _make_exchange(200.0)
    with patch.object(ex, "fetch_ticker", return_value=_ticker(PRICE)):
        buy = ex.create_order(SYMBOL, "market", "buy", 2.0, PRICE)

    spent = 200.0 - ex.fetch_balance()["free"]["MXN"]

    restored = PaperExchange(symbol=SYMBOL, initial_balance=200.0)
    restored.restore_position(
        SYMBOL,
        amount=2.0,
        entry_price=buy["price"],
        total_cost=spent,
    )

    with patch.object(restored, "fetch_ticker", return_value=_ticker(PRICE)):
        restored.create_order(SYMBOL, "market", "sell", 2.0, PRICE)

    bal = restored.fetch_balance()["free"]
    assert bal["XRP"] == 0.0
    assert bal["MXN"] > 0.0


# ── Error cases ───────────────────────────────────────────────────────────────

def test_buy_insufficient_balance_raises():
    ex = _make_exchange(1.0)  # only 1 MXN
    with pytest.raises(Exception, match="Insufficient"):
        with patch.object(ex, "fetch_ticker", return_value=_ticker(PRICE)):
            ex.create_order(SYMBOL, "market", "buy", 100.0, PRICE)


def test_sell_without_holding_raises():
    ex = _make_exchange(200.0)
    with pytest.raises(Exception, match="Insufficient"):
        with patch.object(ex, "fetch_ticker", return_value=_ticker(PRICE)):
            ex.create_order(SYMBOL, "market", "sell", 1.0, PRICE)


# ── Guardrails ────────────────────────────────────────────────────────────────

from risk.guardrails import RiskGuardrails  # noqa: E402
from agents.orchestrator import evaluate_rotation_decision, pick_auto_strategy_for_ohlcv  # noqa: E402


@pytest.fixture()
def guardrails():
    return RiskGuardrails(budget=100.0, stop_loss_pct=0.05, max_trades_per_day=10)


def test_position_size_25_percent(guardrails):
    """Default sizing is 25% of available budget."""
    size = guardrails.calculate_position_size(100.0, 10.0, "XRP/MXN")
    # 25% of 100 = 25 MXN / 10 MXN per unit = 2.5 units
    assert abs(size - 2.5) < 0.01


def test_position_size_returns_zero_if_below_min(guardrails):
    """If calculated amount is below the pair minimum order size, return 0."""
    size = guardrails.calculate_position_size(1.0, 2_000_000.0, "BTC/MXN")
    # 25% of 1 MXN / 2,000,000 = 0.000000125 BTC — far below min 0.00001 BTC
    assert size == 0.0


def test_position_size_zero_if_no_budget(guardrails):
    assert guardrails.calculate_position_size(0.0, 100.0, "XRP/MXN") == 0.0


def test_stop_loss_triggers_on_drop(guardrails):
    assert guardrails.check_stop_loss(entry_price=100.0, current_price=89.0, side="buy") is True


def test_stop_loss_no_trigger_small_drop(guardrails):
    assert guardrails.check_stop_loss(entry_price=100.0, current_price=98.0, side="buy") is False


def test_pick_auto_strategy_prefers_trend_rsi_for_normal_markets():
    closes = [100 + (i * 0.35) + ((-1) ** i) * 0.2 for i in range(80)]
    strategy_name, params = pick_auto_strategy_for_ohlcv(_ohlcv_from_closes(closes, volume=120.0))
    assert strategy_name == "trend_rsi"
    assert params["rsi_buy"] >= 47
    assert params["volume_factor"] <= 1.0


def test_pick_auto_strategy_uses_rsi_when_volatility_is_extreme():
    closes = [100, 108, 94, 111, 90, 114, 88, 117] * 10
    strategy_name, params = pick_auto_strategy_for_ohlcv(_ohlcv_from_closes(closes, volume=140.0))
    assert strategy_name == "rsi"
    assert params["oversold"] >= 35


def test_rotation_decision_rotates_for_stronger_market():
    action, reason = evaluate_rotation_decision(
        current_symbol="XRP/MXN",
        current_score=48.0,
        best_symbol="SOL/MXN",
        best_score=66.0,
        has_position=True,
        unrealized_pnl_pct=0.8,
        aggressive=True,
        min_score_delta=8.0,
        cooldown_active=False,
    )
    assert action == "rotate"
    assert "SOL/MXN" in reason


def test_rotation_decision_holds_when_score_gap_is_small():
    action, reason = evaluate_rotation_decision(
        current_symbol="XRP/MXN",
        current_score=58.0,
        best_symbol="SOL/MXN",
        best_score=62.0,
        has_position=True,
        unrealized_pnl_pct=1.2,
        aggressive=True,
        min_score_delta=8.0,
        cooldown_active=False,
    )
    assert action == "hold"
    assert "score gap" in reason.lower()


def test_rotation_default_threshold_is_responsive_to_live_market_gaps():
    action, reason = evaluate_rotation_decision(
        current_symbol="XRP/MXN",
        current_score=12.0,
        best_symbol="AVAX/MXN",
        best_score=13.3,
        has_position=True,
        aggressive=True,
        cooldown_active=False,
    )
    assert action == "rotate"
    assert "AVAX/MXN" in reason


def test_rotation_decision_protects_deeply_underwater_trade():
    action, reason = evaluate_rotation_decision(
        current_symbol="XRP/MXN",
        current_score=46.0,
        best_symbol="BTC/MXN",
        best_score=56.0,
        has_position=True,
        unrealized_pnl_pct=-4.2,
        aggressive=True,
        min_score_delta=8.0,
        cooldown_active=False,
    )
    assert action == "hold"
    assert "drawdown" in reason.lower()


@pytest.mark.asyncio
async def test_scan_best_opportunity_prefers_buy_signal_over_hold_rank(monkeypatch):
    import agents.orchestrator as orch

    async def fake_get_available_symbols(*args, **kwargs):
        return ["AVAX/MXN", "BTC/MXN"]

    async def fake_assess_market_opportunity(exchange, symbol, timeframe="15m", limit=100):
        if symbol == "AVAX/MXN":
            return {
                "symbol": symbol,
                "strategy": "trend_rsi",
                "params": {},
                "score": 0.0,
                "eligible": False,
            }
        return {
            "symbol": symbol,
            "strategy": "trend_rsi",
            "params": {},
            "score": 67.5,
            "eligible": True,
        }

    monkeypatch.setattr(orch, "get_available_symbols", fake_get_available_symbols, raising=False)
    monkeypatch.setattr(orch, "assess_market_opportunity", fake_assess_market_opportunity)

    symbol, strategy_name, params, score = await orch.scan_best_opportunity()

    assert symbol == "BTC/MXN"
    assert strategy_name == "trend_rsi"
    assert score == 67.5


@pytest.mark.asyncio
async def test_scan_best_opportunity_prefers_higher_roi_rank(monkeypatch):
    import agents.orchestrator as orch

    async def fake_get_available_symbols(*args, **kwargs):
        return ["ETH/USD", "SOL/USD"]

    async def fake_assess_market_opportunity(exchange, symbol, timeframe="15m", limit=100):
        if symbol == "ETH/USD":
            return {
                "symbol": symbol,
                "strategy": "adaptive",
                "params": {},
                "score": 74.0,
                "rank_score": 78.0,
                "expected_roi_pct": 1.6,
                "eligible": True,
            }
        return {
            "symbol": symbol,
            "strategy": "adaptive",
            "params": {},
            "score": 71.0,
            "rank_score": 92.0,
            "expected_roi_pct": 4.9,
            "eligible": True,
        }

    monkeypatch.setattr(orch, "get_available_symbols", fake_get_available_symbols, raising=False)
    monkeypatch.setattr(orch, "assess_market_opportunity", fake_assess_market_opportunity)

    symbol, strategy_name, params, score = await orch.scan_best_opportunity(quote_currency="USD")

    assert symbol == "SOL/USD"
    assert strategy_name == "adaptive"
    assert score == 92.0
