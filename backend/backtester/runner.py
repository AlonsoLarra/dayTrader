import asyncio
import ccxt
import numpy as np
from datetime import datetime
from typing import Optional

from strategies.base import BaseStrategy, Signal

FEE_RATE = 0.005  # 0.5% taker fee per side (Bitso BTC/MXN)


class BacktestRunner:
    def __init__(self):
        self._exchange = ccxt.bitso()

    # ── Data fetching ──────────────────────────────────────────────────

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
    ) -> list:
        """Fetch OHLCV candles from the exchange, running in a thread executor
        so the event loop stays unblocked."""
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

        loop = asyncio.get_event_loop()

        def _fetch_sync() -> list:
            all_ohlcv: list = []
            since = start_ts
            while since < end_ts:
                try:
                    batch = self._exchange.fetch_ohlcv(
                        symbol, timeframe, since=since, limit=500
                    )
                    if not batch:
                        break
                    all_ohlcv.extend(batch)
                    last_ts = batch[-1][0]
                    since = last_ts + 1
                    if last_ts >= end_ts:
                        break
                except Exception as exc:
                    raise RuntimeError(f"OHLCV fetch failed at since={since}: {exc}") from exc
            return [c for c in all_ohlcv if start_ts <= c[0] <= end_ts]

        return await loop.run_in_executor(None, _fetch_sync)

    # ── Simulation ─────────────────────────────────────────────────────

    def simulate(
        self,
        strategy: BaseStrategy,
        ohlcv_data: list,
        initial_capital: float,
    ) -> dict:
        """Run a backtest on pre-fetched OHLCV data.

        Correctness notes:
        - Signals fire on candle i; fills execute at candle i+1's open (no look-ahead).
        - 0.5% fee applied on both entry and exit.
        - entry_price and candles_held are passed to strategy.analyze() so trailing
          stops and time exits behave identically to the live agent.
        """
        if len(ohlcv_data) < strategy.min_candles + 1:
            return {
                "total_return_pct": 0.0,
                "win_rate": 0.0,
                "total_trades": 0,
                "max_drawdown_pct": 0.0,
                "sharpe_ratio": 0.0,
                "equity_curve": [],
                "trades": [],
                "error": (
                    f"Insufficient data: {len(ohlcv_data)} candles "
                    f"(need {strategy.min_candles + 1})"
                ),
            }

        capital = initial_capital
        position: Optional[dict] = None
        candles_held: int = 0
        trades: list = []
        equity_curve: list = [[ohlcv_data[0][0], capital]]

        # Iterate up to second-to-last candle so we always have a next-bar fill.
        for i in range(strategy.min_candles, len(ohlcv_data) - 1):
            window = ohlcv_data[: i + 1]
            entry_price = position["entry_price"] if position else None

            result = strategy.analyze(
                window,
                entry_price=entry_price,
                candles_held=candles_held,
            )

            # Fill at the *open* of the next candle — no look-ahead bias.
            next_candle = ohlcv_data[i + 1]
            fill_price: float = next_candle[1]
            fill_ts: int = next_candle[0]

            if result.signal == Signal.BUY and position is None:
                amount = (capital * 0.95) / fill_price
                cost = amount * fill_price
                fee = cost * FEE_RATE
                capital -= cost + fee
                position = {
                    "entry_price": fill_price,
                    "amount": amount,
                    "timestamp": fill_ts,
                }
                trades.append(
                    {
                        "side": "buy",
                        "price": fill_price,
                        "amount": amount,
                        "timestamp": fill_ts,
                        "fee": fee,
                        "pnl": None,
                    }
                )
                candles_held = 0

            elif result.signal == Signal.SELL and position is not None:
                proceeds = position["amount"] * fill_price
                fee = proceeds * FEE_RATE
                pnl = proceeds - fee - (position["amount"] * position["entry_price"])
                capital += proceeds - fee
                trades.append(
                    {
                        "side": "sell",
                        "price": fill_price,
                        "amount": position["amount"],
                        "timestamp": fill_ts,
                        "fee": fee,
                        "pnl": pnl,
                    }
                )
                position = None
                candles_held = 0
            else:
                if position is not None:
                    candles_held += 1

            # Mark-to-market using the current bar's close (what we can observe).
            current_close: float = ohlcv_data[i][4]
            mark = position["amount"] * current_close if position else 0.0
            equity_curve.append([ohlcv_data[i][0], capital + mark])

        # Force-close any open position at the last available close.
        if position is not None:
            last_candle = ohlcv_data[-1]
            close_price: float = last_candle[4]
            proceeds = position["amount"] * close_price
            fee = proceeds * FEE_RATE
            pnl = proceeds - fee - (position["amount"] * position["entry_price"])
            capital += proceeds - fee
            trades.append(
                {
                    "side": "sell",
                    "price": close_price,
                    "amount": position["amount"],
                    "timestamp": last_candle[0],
                    "fee": fee,
                    "pnl": pnl,
                }
            )

        final_equity = capital
        total_return_pct = (final_equity - initial_capital) / initial_capital * 100

        sell_trades = [t for t in trades if t["side"] == "sell" and t["pnl"] is not None]
        win_trades = [t for t in sell_trades if t["pnl"] > 0]
        win_rate = len(win_trades) / len(sell_trades) * 100 if sell_trades else 0.0

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
            "win_rate": round(win_rate, 2),
            "total_trades": len(sell_trades),
            "max_drawdown_pct": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe, 2),
            "equity_curve": equity_curve,
            "trades": trades,
        }

    # ── Convenience wrapper (used by the backtest API route) ───────────

    async def run(
        self,
        strategy: BaseStrategy,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        initial_capital: float,
    ) -> dict:
        try:
            ohlcv_data = await self.fetch_ohlcv(symbol, timeframe, start_date, end_date)
        except RuntimeError as exc:
            return {"error": str(exc)}
        return self.simulate(strategy, ohlcv_data, initial_capital)
