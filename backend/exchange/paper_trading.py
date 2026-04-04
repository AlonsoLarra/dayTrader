import ccxt
import time
from datetime import datetime


class PaperExchange:
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

    def create_order(self, symbol: str, order_type: str, side: str, amount: float, price: float = None) -> dict:
        ticker = self.fetch_ticker(symbol)
        fill_price = price or ticker.get("last", 1_800_000.0)

        parts = symbol.split("/")
        base_currency = parts[0]
        quote_currency = parts[1]
        cost = amount * fill_price

        if side == "buy":
            available = self.balance.get(quote_currency, 0)
            if available < cost:
                raise Exception(f"Insufficient {quote_currency} balance: have {available:.2f}, need {cost:.2f}")
            self.balance[quote_currency] = available - cost
            self.balance[base_currency] = self.balance.get(base_currency, 0.0) + amount

            if symbol not in self.positions:
                self.positions[symbol] = {"amount": 0.0, "avg_entry_price": 0.0}
            pos = self.positions[symbol]
            total_cost = pos["amount"] * pos["avg_entry_price"] + cost
            pos["amount"] += amount
            pos["avg_entry_price"] = total_cost / pos["amount"] if pos["amount"] > 0 else fill_price

        elif side == "sell":
            available = self.balance.get(base_currency, 0)
            if available < amount:
                raise Exception(f"Insufficient {base_currency} balance: have {available:.8f}, need {amount:.8f}")
            self.balance[base_currency] = available - amount
            self.balance[quote_currency] = self.balance.get(quote_currency, 0.0) + cost

            if symbol in self.positions:
                pos = self.positions[symbol]
                realized_pnl = (fill_price - pos["avg_entry_price"]) * amount
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
            "cost": cost,
            "filled": amount,
            "status": "closed",
            "timestamp": int(time.time() * 1000),
            "datetime": datetime.utcnow().isoformat(),
        }
        self.orders.append(order)
        return order
