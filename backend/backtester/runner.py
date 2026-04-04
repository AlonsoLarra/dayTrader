import ccxt
import numpy as np
from datetime import datetime

from backend.strategies.base import BaseStrategy, Signal


class BacktestRunner:
    def __init__(self):
        self._exchange = ccxt.binance()  # public API only

    async def run(
        self,
        strategy: BaseStrategy,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        initial_capital: float,
    ) -> dict:
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

        all_ohlcv: list = []
        since = start_ts
        while since < end_ts:
            try:
                ohlcv = self._exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=500)
                if not ohlcv:
                    break
                all_ohlcv.extend(ohlcv)
                last_ts = ohlcv[-1][0]
                since = last_ts + 1
                if last_ts >= end_ts:
                    break
            except Exception:
                break

        all_ohlcv = [c for c in all_ohlcv if start_ts <= c[0] <= end_ts]

        if len(all_ohlcv) < strategy.min_candles:
            return {
                "total_return_pct": 0.0,
                "win_rate": 0.0,
                "total_trades": 0,
                "max_drawdown_pct": 0.0,
                "sharpe_ratio": 0.0,
                "equity_curve": [],
                "trades": [],
                "error": f"Insufficient data: {len(all_ohlcv)} candles (need {strategy.min_candles})",
            }

        capital = initial_capital
        position: dict | None = None
        trades: list[dict] = []
        equity_curve: list[list] = [[all_ohlcv[0][0], capital]]

        for i in range(strategy.min_candles, len(all_ohlcv)):
            window = all_ohlcv[: i + 1]
            result = strategy.analyze(window)

            current_candle = all_ohlcv[i]
            current_price: float = current_candle[4]
            timestamp: int = current_candle[0]

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

            elif result.signal == Signal.SELL and position is not None and position["side"] == "buy":
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

            current_equity = capital + (position["amount"] * current_price if position else 0.0)
            equity_curve.append([timestamp, current_equity])

        # Close any open position at end
        if position is not None:
            last_price = all_ohlcv[-1][4]
            pnl = (last_price - position["entry_price"]) * position["amount"]
            capital += position["amount"] * last_price
            trades.append(
                {
                    "side": "sell",
                    "price": last_price,
                    "amount": position["amount"],
                    "timestamp": all_ohlcv[-1][0],
                    "pnl": pnl,
                }
            )

        final_equity = capital
        total_return_pct = (final_equity - initial_capital) / initial_capital * 100

        sell_trades = [t for t in trades if t["side"] == "sell" and t["pnl"] is not None]
        win_trades = [t for t in sell_trades if t["pnl"] > 0]
        win_rate = len(win_trades) / len(sell_trades) if sell_trades else 0.0

        equity_values = [e[1] for e in equity_curve]
        max_drawdown = 0.0
        peak = equity_values[0] if equity_values else initial_capital
        for v in equity_values:
            if v > peak:
                peak = v
            if peak > 0:
                dd = (peak - v) / peak * 100
                if dd > max_drawdown:
                    max_drawdown = dd

        if len(equity_values) > 1:
            returns = np.diff(equity_values) / np.array(equity_values[:-1], dtype=float)
            std = float(np.std(returns))
            sharpe = float(np.mean(returns) / std * np.sqrt(252)) if std > 0 else 0.0
        else:
            sharpe = 0.0

        return {
            "total_return_pct": round(total_return_pct, 2),
            "win_rate": round(win_rate * 100, 2),
            "total_trades": len(sell_trades),
            "max_drawdown_pct": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe, 2),
            "equity_curve": equity_curve,
            "trades": trades,
        }
