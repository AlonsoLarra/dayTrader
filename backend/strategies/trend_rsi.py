"""
TrendRSI — composite strategy that combines:
  1. Trend filter (50-period EMA) — only buy in uptrends
  2. RSI mean-reversion with looser thresholds (buy<45, sell>65)
  3. Volume confirmation (current bar volume > 1.1× 20-bar average)
  4. Profit target (2.5% gain triggers sell)
  5. Time-based exit (>16 candles = ~4h with no profit → free capital)

Why this beats pure RSI:
  - Trend filter prevents catching falling knives in downtrends
  - RSI 45 gives more buy opportunities than RSI 30
  - Volume filter avoids low-conviction moves
  - Profit target provides a deterministic exit rather than waiting for RSI 70+
  - Time exit frees capital stuck in flat positions
"""
import numpy as np
from strategies.base import BaseStrategy, Signal, StrategyResult


class TrendRSIStrategy(BaseStrategy):

    def __init__(self, params: dict = None):
        super().__init__(params)
        self.ema_period: int = int(self.params.get("ema_period", 50))
        self.rsi_period: int = int(self.params.get("rsi_period", 14))
        self.rsi_buy: float = float(self.params.get("rsi_buy", 45))
        self.rsi_sell: float = float(self.params.get("rsi_sell", 65))
        self.volume_factor: float = float(self.params.get("volume_factor", 1.1))
        self.profit_target_pct: float = float(self.params.get("profit_target_pct", 0.025))
        self.max_hold_candles: int = int(self.params.get("max_hold_candles", 16))

    @property
    def name(self) -> str:
        return "trend_rsi"

    @property
    def min_candles(self) -> int:
        return self.ema_period + self.rsi_period + 5

    def _ema(self, values: np.ndarray, period: int) -> np.ndarray:
        k = 2.0 / (period + 1)
        ema = np.zeros(len(values))
        ema[0] = values[0]
        for i in range(1, len(values)):
            ema[i] = values[i] * k + ema[i - 1] * (1 - k)
        return ema

    def _rsi(self, closes: np.ndarray) -> float:
        deltas = np.diff(closes[-(self.rsi_period + 20):])
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_gain = float(np.mean(gains[:self.rsi_period]))
        avg_loss = float(np.mean(losses[:self.rsi_period]))
        for i in range(self.rsi_period, len(deltas)):
            avg_gain = (avg_gain * (self.rsi_period - 1) + gains[i]) / self.rsi_period
            avg_loss = (avg_loss * (self.rsi_period - 1) + losses[i]) / self.rsi_period
        rs = avg_gain / avg_loss if avg_loss else 100.0
        return round(100.0 - (100.0 / (1.0 + rs)), 2)

    def analyze(self, ohlcv_data: list, entry_price: float = None, candles_held: int = 0) -> StrategyResult:
        if len(ohlcv_data) < self.min_candles:
            return StrategyResult(
                signal=Signal.HOLD,
                confidence=0.0,
                reasoning=f"Insufficient data ({len(ohlcv_data)} candles, need {self.min_candles})",
                indicators={},
            )

        closes = np.array([c[4] for c in ohlcv_data], dtype=float)
        volumes = np.array([c[5] for c in ohlcv_data], dtype=float)

        # Trend: 50 EMA
        ema50 = self._ema(closes, self.ema_period)
        current_price = closes[-1]
        current_ema = ema50[-1]
        in_uptrend = current_price > current_ema

        # RSI
        rsi = self._rsi(closes)

        # Volume: current bar vs 20-bar avg
        avg_vol = float(np.mean(volumes[-20:])) if len(volumes) >= 20 else float(np.mean(volumes))
        current_vol = float(volumes[-1])
        volume_ok = current_vol >= avg_vol * self.volume_factor

        indicators = {
            "rsi": rsi,
            "ema50": round(current_ema, 2),
            "price_vs_ema": round((current_price - current_ema) / current_ema * 100, 2),
            "in_uptrend": in_uptrend,
            "volume_ratio": round(current_vol / avg_vol, 2) if avg_vol else 1.0,
            "volume_ok": volume_ok,
            "entry_price": entry_price,
            "candles_held": candles_held,
        }

        # ── SELL logic (checked first if we have a position) ───────────────
        if entry_price is not None:
            profit_pct = (current_price - entry_price) / entry_price

            # 1. Profit target hit
            if profit_pct >= self.profit_target_pct:
                return StrategyResult(
                    signal=Signal.SELL,
                    confidence=1.0,
                    reasoning=f"Profit target hit: +{profit_pct*100:.2f}% (target {self.profit_target_pct*100:.1f}%)",
                    indicators=indicators,
                )

            # 2. RSI overbought
            if rsi >= self.rsi_sell:
                return StrategyResult(
                    signal=Signal.SELL,
                    confidence=min((rsi - self.rsi_sell) / (100 - self.rsi_sell), 1.0),
                    reasoning=f"RSI overbought: {rsi:.1f} ≥ {self.rsi_sell}",
                    indicators=indicators,
                )

            # 3. Trend broken (price fell below EMA — exit regardless of RSI)
            if not in_uptrend:
                return StrategyResult(
                    signal=Signal.SELL,
                    confidence=0.8,
                    reasoning=f"Trend broken: price ${current_price:,.0f} fell below EMA50 ${current_ema:,.0f}",
                    indicators=indicators,
                )

            # 4. Time exit: been held too long with no profit
            if candles_held >= self.max_hold_candles and profit_pct < 0.005:
                return StrategyResult(
                    signal=Signal.SELL,
                    confidence=0.6,
                    reasoning=f"Time exit: held {candles_held} candles with only {profit_pct*100:.2f}% gain — freeing capital",
                    indicators=indicators,
                )

            return StrategyResult(
                signal=Signal.HOLD,
                confidence=0.0,
                reasoning=f"Holding: RSI {rsi:.1f}, trend {'up' if in_uptrend else 'down'}, P&L {profit_pct*100:.2f}%",
                indicators=indicators,
            )

        # ── BUY logic (no position) ────────────────────────────────────────
        if not in_uptrend:
            return StrategyResult(
                signal=Signal.HOLD,
                confidence=0.0,
                reasoning=f"No buy: downtrend (price ${current_price:,.0f} < EMA50 ${current_ema:,.0f})",
                indicators=indicators,
            )

        if rsi < self.rsi_buy and volume_ok:
            confidence = min((self.rsi_buy - rsi) / self.rsi_buy, 1.0) * (current_vol / avg_vol if avg_vol else 1.0)
            return StrategyResult(
                signal=Signal.BUY,
                confidence=min(confidence, 1.0),
                reasoning=f"Buy signal: uptrend + RSI {rsi:.1f} < {self.rsi_buy} + volume {current_vol/avg_vol:.1f}× avg",
                indicators=indicators,
            )

        if rsi < self.rsi_buy and not volume_ok:
            return StrategyResult(
                signal=Signal.HOLD,
                confidence=0.0,
                reasoning=f"RSI {rsi:.1f} OK but volume too low ({current_vol/avg_vol:.1f}× avg, need {self.volume_factor}×)",
                indicators=indicators,
            )

        return StrategyResult(
            signal=Signal.HOLD,
            confidence=0.0,
            reasoning=f"Waiting: RSI {rsi:.1f} (need < {self.rsi_buy}), trend {'up ✓' if in_uptrend else 'down ✗'}",
            indicators=indicators,
        )
