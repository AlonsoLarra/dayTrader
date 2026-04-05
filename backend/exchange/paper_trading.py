import ccxt
import time
import random
from datetime import datetime

# Bitso taker fee rate
TAKER_FEE = 0.00625  # 0.625%

# Simulated bid/ask half-spread per symbol (as fraction of price)
SPREAD = {
    "BTC/MXN":  0.0005,   # 0.05%
    "ETH/MXN":  0.0008,
    "SOL/MXN":  0.0010,
    "XRP/MXN":  0.0012,
    "AVAX/MXN": 0.0015,
    "LTC/MXN":  0.0010,
    "BCH/MXN":  0.0010,
    "MANA/MXN": 0.0020,
    "TRX/MXN":  0.0015,
    "BAT/MXN":  0.0020,
}
DEFAULT_SPREAD = 0.0015

# Bitso minimum order amounts (in base currency)
MIN_ORDER_AMOUNT = {
    "BTC/MXN":  0.00001,
    "ETH/MXN":  0.001,
    "SOL/MXN":  0.01,
    "XRP/MXN":  1.0,
    "AVAX/MXN": 0.01,
    "LTC/MXN":  0.001,
    "BCH/MXN":  0.001,
    "MANA/MXN": 1.0,
    "TRX/MXN":  1.0,
    "BAT/MXN":  1.0,
}
DEFAULT_MIN_AMOUNT = 0.001


class PaperExchange:
    """Paper trading simulator using real market prices from Bitso public API.

    Simulates realistic trading conditions:
    - Bid/ask spread (buy at ask, sell at bid)
    - Taker fee (0.625%)
    - Minimum order size enforcement per pair
    """

    def __init__(self, symbol: str = "BTC/MXN", initial_balance: float = 10000.0):
        self._bitso = ccxt.bitso()
        parts = symbol.split("/")
        self._base = parts[0]
        self._quote = parts[1]
        self.balance: dict[str, float] = {
            self._quote: initial_balance,
            self._base: 0.0,
        }
        self.positions: dict[str, dict] = {}
        self.orders: list[dict] = []
        self.pnl: float = 0.0

    def fetch_balance(self) -> dict:
        free = dict(self.balance)
        return {"free": free, "total": free, "used": {}}

    def fetch_ticker(self, symbol: str) -> dict:
        try:
            return self._bitso.fetch_ticker(symbol)
        except Exception:
            return {"last": 1_800_000.0, "symbol": symbol, "timestamp": int(time.time() * 1000)}

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> list:
        try:
            return self._bitso.fetch_ohlcv(symbol, timeframe, limit=limit)
        except Exception:
            return []

    def create_order(self, symbol: str, order_type: str, side: str, amount: float, price: float = None) -> dict:
        # Enforce minimum order size
        min_amount = MIN_ORDER_AMOUNT.get(symbol, DEFAULT_MIN_AMOUNT)
        if amount < min_amount:
            raise Exception(
                f"Order amount {amount:.8f} is below minimum {min_amount} for {symbol}"
            )

        ticker = self.fetch_ticker(symbol)
        mid_price = price or ticker.get("last", 1_800_000.0)

        # Simulate bid/ask spread: buy at ask (slightly above mid), sell at bid (slightly below)
        half_spread = SPREAD.get(symbol, DEFAULT_SPREAD)
        if side == "buy":
            fill_price = mid_price * (1 + half_spread)
        else:
            fill_price = mid_price * (1 - half_spread)

        # Add small random slippage on top (market impact)
        slippage = random.uniform(0, half_spread * 0.5)
        if side == "buy":
            fill_price *= (1 + slippage)
        else:
            fill_price *= (1 - slippage)

        parts = symbol.split("/")
        base_currency = parts[0]
        quote_currency = parts[1]

        notional = amount * fill_price
        fee_amount = notional * TAKER_FEE  # always taker for market orders

        if side == "buy":
            total_cost = notional + fee_amount  # fee paid in quote currency
            available = self.balance.get(quote_currency, 0)
            if available < total_cost:
                raise Exception(
                    f"Insufficient {quote_currency} balance: have {available:.2f}, need {total_cost:.2f} (inc. {fee_amount:.2f} fee)"
                )
            self.balance[quote_currency] = available - total_cost
            self.balance[base_currency] = self.balance.get(base_currency, 0.0) + amount

            if symbol not in self.positions:
                self.positions[symbol] = {"amount": 0.0, "avg_entry_price": 0.0}
            pos = self.positions[symbol]
            total_pos_cost = pos["amount"] * pos["avg_entry_price"] + total_cost
            pos["amount"] += amount
            pos["avg_entry_price"] = total_pos_cost / pos["amount"] if pos["amount"] > 0 else fill_price

        elif side == "sell":
            available = self.balance.get(base_currency, 0)
            if available < amount:
                raise Exception(
                    f"Insufficient {base_currency} balance: have {available:.8f}, need {amount:.8f}"
                )
            proceeds_after_fee = notional - fee_amount  # fee paid from proceeds
            self.balance[base_currency] = available - amount
            self.balance[quote_currency] = self.balance.get(quote_currency, 0.0) + proceeds_after_fee

            if symbol in self.positions:
                pos = self.positions[symbol]
                realized_pnl = (fill_price - pos["avg_entry_price"]) * amount - fee_amount
                self.pnl += realized_pnl
                pos["amount"] -= amount
                if pos["amount"] <= 1e-10:
                    del self.positions[symbol]

        order = {
            "id": str(len(self.orders) + 1),
            "symbol": symbol,
            "type": order_type,
            "side": side,
            "amount": amount,
            "price": fill_price,
            "cost": notional,
            "fee": {"cost": fee_amount, "currency": quote_currency, "rate": TAKER_FEE},
            "filled": amount,
            "status": "closed",
            "timestamp": int(time.time() * 1000),
            "datetime": datetime.utcnow().isoformat(),
        }
        self.orders.append(order)
        return order

    """Paper trading simulator using real market prices from Bitso public API."""

    def __init__(self, symbol: str = "BTC/MXN", initial_balance: float = 10000.0):
        self._bitso = ccxt.bitso()
        parts = symbol.split("/")
        self._base = parts[0]   # e.g. BTC
        self._quote = parts[1]  # e.g. MXN
        self.balance: dict[str, float] = {
            self._quote: initial_balance,
            self._base: 0.0,
        }
        self.positions: dict[str, dict] = {}
        self.orders: list[dict] = []
        self.pnl: float = 0.0

    def fetch_balance(self) -> dict:
        free = dict(self.balance)
        return {"free": free, "total": free, "used": {}}

    def fetch_ticker(self, symbol: str) -> dict:
        try:
            return self._bitso.fetch_ticker(symbol)
        except Exception:
            # Fallback: approximate BTC/MXN price
            return {"last": 1_800_000.0, "symbol": symbol, "timestamp": int(time.time() * 1000)}

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> list:
        try:
            return self._bitso.fetch_ohlcv(symbol, timeframe, limit=limit)
        except Exception:
            return []
