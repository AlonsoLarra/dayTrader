"""
Adaptive — dynamic strategy that adjusts parameters based on market volatility.

Combines five indicator systems:
  1. Trend filter (50-period EMA) — only buy in uptrends
  2. RSI with volatility-adaptive thresholds (tighter in calm markets, wider in volatile)
  3. MACD (12/26/9) for momentum confirmation
  4. ATR-based trailing stop instead of fixed profit target
  5. Bollinger Band squeeze detection for breakout confluence
  6. Volume confirmation (current bar > 1.1× 20-bar average)

Volatility regime (based on ATR% percentile over 50 bars):
  Low  (<30th pctl): RSI buy<40/sell>60, trailing stop = 1.0×ATR
  Normal (30-70th):  RSI buy<45/sell>65, trailing stop = 1.5×ATR
  High  (>70th pctl): RSI buy<35/sell>75, trailing stop = 2.5×ATR

Why this beats TrendRSI:
  - Adaptive thresholds avoid whipsaws in high vol and missed entries in low vol
  - MACD confirmation prevents entering against momentum
  - ATR trailing stop lets winners run instead of capping at fixed 2.5%
  - Bollinger squeeze detects pre-breakout consolidation for higher conviction entries
  - Confidence-based position sizing risks more on strong signals
"""

import numpy as np
from strategies.base import BaseStrategy, Signal, StrategyResult


class AdaptiveStrategy(BaseStrategy):

    supports_adaptive_sizing = True

    def __init__(self, params: dict = None):
        super().__init__(params)
        self.ema_period: int = int(self.params.get("ema_period", 50))
        self.rsi_period: int = int(self.params.get("rsi_period", 14))
        self.macd_fast: int = int(self.params.get("macd_fast", 12))
        self.macd_slow: int = int(self.params.get("macd_slow", 26))
        self.macd_signal: int = int(self.params.get("macd_signal", 9))
        self.bb_period: int = int(self.params.get("bb_period", 20))
        self.bb_std: float = float(self.params.get("bb_std", 2.0))
        self.atr_period: int = int(self.params.get("atr_period", 14))
        self.volume_factor: float = float(self.params.get("volume_factor", 1.1))
        self.max_hold_candles: int = int(self.params.get("max_hold_candles", 20))
        self.min_profit_for_macd_exit: float = float(self.params.get("min_profit_for_macd_exit", 0.005))

        # Volatility regime percentile thresholds
        self.low_vol_percentile: float = float(self.params.get("low_vol_percentile", 30.0))
        self.high_vol_percentile: float = float(self.params.get("high_vol_percentile", 70.0))

        # RSI thresholds per regime
        self.rsi_buy_low_vol: float = float(self.params.get("rsi_buy_low_vol", 40.0))
        self.rsi_buy_normal: float = float(self.params.get("rsi_buy_normal", 45.0))
        self.rsi_buy_high_vol: float = float(self.params.get("rsi_buy_high_vol", 35.0))
        self.rsi_sell_low_vol: float = float(self.params.get("rsi_sell_low_vol", 60.0))
        self.rsi_sell_normal: float = float(self.params.get("rsi_sell_normal", 65.0))
        self.rsi_sell_high_vol: float = float(self.params.get("rsi_sell_high_vol", 75.0))

        # Trailing stop ATR multipliers per regime
        self.trail_mult_low_vol: float = float(self.params.get("trail_mult_low_vol", 1.0))
        self.trail_mult_normal: float = float(self.params.get("trail_mult_normal", 1.5))
        self.trail_mult_high_vol: float = float(self.params.get("trail_mult_high_vol", 2.5))

    @property
    def name(self) -> str:
        return "adaptive"

    @property
    def min_candles(self) -> int:
        return max(self.ema_period, self.macd_slow + self.macd_signal, self.bb_period) + self.atr_period + self.rsi_period + 5

    # ── Indicator calculations ─────────────────────────────────────────

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

    def _atr(self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> np.ndarray:
        """Average True Range using EMA smoothing."""
        n = len(closes)
        tr = np.zeros(n)
        tr[0] = highs[0] - lows[0]
        for i in range(1, n):
            tr[i] = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
        return self._ema(tr, self.atr_period)

    def _macd(self, closes: np.ndarray) -> tuple:
        """Returns (macd_line, signal_line, histogram) as arrays."""
        ema_fast = self._ema(closes, self.macd_fast)
        ema_slow = self._ema(closes, self.macd_slow)
        macd_line = ema_fast - ema_slow
        signal_line = self._ema(macd_line, self.macd_signal)
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def _bollinger(self, closes: np.ndarray) -> tuple:
        """Returns (bandwidth_array, is_squeeze_releasing)."""
        n = len(closes)
        middle = np.zeros(n)
        bandwidth = np.zeros(n)

        for i in range(self.bb_period - 1, n):
            window = closes[i - self.bb_period + 1: i + 1]
            sma = np.mean(window)
            std = np.std(window)
            middle[i] = sma
            upper = sma + self.bb_std * std
            lower = sma - self.bb_std * std
            bandwidth[i] = (upper - lower) / sma if sma else 0.0

        # Squeeze: bandwidth below its 20th percentile over last 50 bars
        recent_bw = bandwidth[-50:] if len(bandwidth) >= 50 else bandwidth[bandwidth > 0]
        if len(recent_bw) > 5:
            squeeze_threshold = float(np.percentile(recent_bw[recent_bw > 0], 20)) if np.any(recent_bw > 0) else 0.0
            prev_bw = bandwidth[-2] if n >= 2 else 0.0
            curr_bw = bandwidth[-1]
            is_squeeze_releasing = prev_bw < squeeze_threshold and curr_bw > prev_bw
        else:
            is_squeeze_releasing = False

        return bandwidth, is_squeeze_releasing

    def _get_volatility_regime(self, atr_values: np.ndarray, closes: np.ndarray) -> str:
        """Classify current volatility as 'low', 'normal', or 'high'."""
        # ATR as percentage of price over last 50 bars
        lookback = min(50, len(atr_values), len(closes))
        atr_pct = atr_values[-lookback:] / closes[-lookback:] * 100
        current_atr_pct = atr_pct[-1]

        if len(atr_pct) < 5:
            return "normal"

        percentile = float(np.sum(atr_pct < current_atr_pct) / len(atr_pct) * 100)

        if percentile < self.low_vol_percentile:
            return "low"
        elif percentile > self.high_vol_percentile:
            return "high"
        return "normal"

    def _get_regime_params(self, regime: str) -> dict:
        """Return RSI thresholds and trailing stop multiplier for the given regime."""
        if regime == "low":
            return {
                "rsi_buy": self.rsi_buy_low_vol,
                "rsi_sell": self.rsi_sell_low_vol,
                "trail_mult": self.trail_mult_low_vol,
            }
        elif regime == "high":
            return {
                "rsi_buy": self.rsi_buy_high_vol,
                "rsi_sell": self.rsi_sell_high_vol,
                "trail_mult": self.trail_mult_high_vol,
            }
        return {
            "rsi_buy": self.rsi_buy_normal,
            "rsi_sell": self.rsi_sell_normal,
            "trail_mult": self.trail_mult_normal,
        }

    # ── Main analysis ──────────────────────────────────────────────────

    def analyze(self, ohlcv_data: list, entry_price: float = None, candles_held: int = 0) -> StrategyResult:
        if len(ohlcv_data) < self.min_candles:
            return StrategyResult(
                signal=Signal.HOLD,
                confidence=0.0,
                reasoning=f"Insufficient data ({len(ohlcv_data)} candles, need {self.min_candles})",
                indicators={},
            )

        closes = np.array([c[4] for c in ohlcv_data], dtype=float)
        highs = np.array([c[2] for c in ohlcv_data], dtype=float)
        lows = np.array([c[3] for c in ohlcv_data], dtype=float)
        volumes = np.array([c[5] for c in ohlcv_data], dtype=float)

        # Compute all indicators
        ema50 = self._ema(closes, self.ema_period)
        rsi = self._rsi(closes)
        atr_values = self._atr(highs, lows, closes)
        macd_line, signal_line, histogram = self._macd(closes)
        bandwidth, squeeze_releasing = self._bollinger(closes)

        current_price = closes[-1]
        current_ema = ema50[-1]
        current_atr = atr_values[-1]
        in_uptrend = current_price > current_ema

        # Volatility regime
        regime = self._get_volatility_regime(atr_values, closes)
        regime_params = self._get_regime_params(regime)
        rsi_buy_threshold = regime_params["rsi_buy"]
        rsi_sell_threshold = regime_params["rsi_sell"]
        trail_mult = regime_params["trail_mult"]

        # Volume check
        avg_vol = float(np.mean(volumes[-20:])) if len(volumes) >= 20 else float(np.mean(volumes))
        current_vol = float(volumes[-1])
        volume_ok = current_vol >= avg_vol * self.volume_factor

        # MACD state
        macd_hist_positive = histogram[-1] > 0
        macd_bullish_cross = (histogram[-1] > 0 and histogram[-2] <= 0) if len(histogram) >= 2 else False
        macd_bearish_cross = (histogram[-1] < 0 and histogram[-2] >= 0) if len(histogram) >= 2 else False

        indicators = {
            "rsi": rsi,
            "ema50": round(current_ema, 2),
            "price_vs_ema": round((current_price - current_ema) / current_ema * 100, 2),
            "in_uptrend": in_uptrend,
            "atr": round(current_atr, 2),
            "atr_pct": round(current_atr / current_price * 100, 3),
            "regime": regime,
            "rsi_buy_threshold": rsi_buy_threshold,
            "rsi_sell_threshold": rsi_sell_threshold,
            "macd_histogram": round(histogram[-1], 2),
            "macd_bullish_cross": macd_bullish_cross,
            "macd_bearish_cross": macd_bearish_cross,
            "bb_squeeze_releasing": squeeze_releasing,
            "volume_ratio": round(current_vol / avg_vol, 2) if avg_vol else 1.0,
            "volume_ok": volume_ok,
            "trail_stop_distance": round(current_atr * trail_mult, 2),
            "entry_price": entry_price,
            "candles_held": candles_held,
        }

        # ── SELL logic (checked first if we have a position) ───────────
        if entry_price is not None:
            profit_pct = (current_price - entry_price) / entry_price

            # 1. Trailing stop: price fell below (highest since entry - N×ATR)
            if candles_held > 0:
                recent_highs = [c[2] for c in ohlcv_data[-candles_held:]]
                highest_since_entry = max(recent_highs) if recent_highs else entry_price
            else:
                highest_since_entry = current_price
            trailing_distance = current_atr * trail_mult
            trailing_stop_price = highest_since_entry - trailing_distance
            indicators["highest_since_entry"] = round(highest_since_entry, 2)
            indicators["trailing_stop_price"] = round(trailing_stop_price, 2)

            if current_price <= trailing_stop_price and profit_pct > 0:
                locked_profit = (trailing_stop_price - entry_price) / entry_price * 100
                return StrategyResult(
                    signal=Signal.SELL,
                    confidence=1.0,
                    reasoning=f"Trailing stop hit: price ${current_price:,.0f} <= stop ${trailing_stop_price:,.0f} (peak ${highest_since_entry:,.0f} - {trail_mult}×ATR). Locked ~{locked_profit:.1f}% profit",
                    indicators=indicators,
                )

            # 2. RSI overbought (adaptive threshold)
            if rsi >= rsi_sell_threshold:
                confidence = min((rsi - rsi_sell_threshold) / (100 - rsi_sell_threshold), 1.0)
                return StrategyResult(
                    signal=Signal.SELL,
                    confidence=confidence,
                    reasoning=f"RSI overbought: {rsi:.1f} >= {rsi_sell_threshold} ({regime} vol regime)",
                    indicators=indicators,
                )

            # 3. MACD bearish crossover while in profit
            if macd_bearish_cross and profit_pct > self.min_profit_for_macd_exit:
                return StrategyResult(
                    signal=Signal.SELL,
                    confidence=0.75,
                    reasoning=f"MACD bearish crossover with +{profit_pct*100:.2f}% profit — momentum exhaustion",
                    indicators=indicators,
                )

            # 4. Trend broken
            if not in_uptrend:
                return StrategyResult(
                    signal=Signal.SELL,
                    confidence=0.8,
                    reasoning=f"Trend broken: price ${current_price:,.0f} fell below EMA50 ${current_ema:,.0f}",
                    indicators=indicators,
                )

            # 5. Time exit: held too long with negligible profit
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
                reasoning=f"Holding: RSI {rsi:.1f}, {regime} vol, trend {'up' if in_uptrend else 'down'}, P&L {profit_pct*100:.2f}%, trail stop ${trailing_stop_price:,.0f}",
                indicators=indicators,
            )

        # ── BUY logic (no position) ────────────────────────────────────
        if not in_uptrend:
            return StrategyResult(
                signal=Signal.HOLD,
                confidence=0.0,
                reasoning=f"No buy: downtrend (price ${current_price:,.0f} < EMA50 ${current_ema:,.0f})",
                indicators=indicators,
            )

        if rsi >= rsi_buy_threshold:
            return StrategyResult(
                signal=Signal.HOLD,
                confidence=0.0,
                reasoning=f"Waiting: RSI {rsi:.1f} (need < {rsi_buy_threshold}, {regime} vol regime)",
                indicators=indicators,
            )

        if not volume_ok:
            return StrategyResult(
                signal=Signal.HOLD,
                confidence=0.0,
                reasoning=f"RSI {rsi:.1f} OK but volume too low ({current_vol/avg_vol:.1f}x avg, need {self.volume_factor}x)",
                indicators=indicators,
            )

        # MACD confirmation: histogram positive or bullish crossover in last 2 bars
        macd_ok = macd_hist_positive or macd_bullish_cross
        if not macd_ok:
            return StrategyResult(
                signal=Signal.HOLD,
                confidence=0.0,
                reasoning=f"RSI {rsi:.1f} + volume OK but MACD not confirming (histogram {histogram[-1]:.2f})",
                indicators=indicators,
            )

        # All conditions met — BUY
        base_confidence = (rsi_buy_threshold - rsi) / rsi_buy_threshold
        macd_factor = 1.0 if macd_hist_positive else 0.7
        volume_ratio = min(current_vol / avg_vol, 2.0) / 2.0 if avg_vol else 0.5
        squeeze_bonus = 0.15 if squeeze_releasing else 0.0
        confidence = min(base_confidence * macd_factor * (0.5 + volume_ratio) + squeeze_bonus, 1.0)

        parts = [f"uptrend", f"RSI {rsi:.1f}<{rsi_buy_threshold}", f"MACD {'positive' if macd_hist_positive else 'crossing up'}", f"vol {current_vol/avg_vol:.1f}x"]
        if squeeze_releasing:
            parts.append("BB squeeze releasing")

        return StrategyResult(
            signal=Signal.BUY,
            confidence=confidence,
            reasoning=f"Buy signal ({regime} vol): {' + '.join(parts)}",
            indicators=indicators,
        )
