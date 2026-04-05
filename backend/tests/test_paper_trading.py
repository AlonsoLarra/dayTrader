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
