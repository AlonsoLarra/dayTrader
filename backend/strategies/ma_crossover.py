import numpy as np
from strategies.base import BaseStrategy, Signal, StrategyResult


class MACrossoverStrategy(BaseStrategy):
    """Moving average crossover strategy."""

    def __init__(self, params: dict = None):
        super().__init__(params)
        self.fast_period: int = int(self.params.get("fast_period", 9))
        self.slow_period: int = int(self.params.get("slow_period", 21))

    @property
    def name(self) -> str:
        return "ma_crossover"

    @property
    def min_candles(self) -> int:
        return self.slow_period + 2

    def analyze(self, ohlcv_data: list) -> StrategyResult:
        if len(ohlcv_data) < self.min_candles:
            return StrategyResult(
                signal=Signal.HOLD,
                confidence=0.0,
                reasoning=f"Insufficient data: {len(ohlcv_data)} candles, need {self.min_candles}",
                indicators={},
            )

        closes = np.array([c[4] for c in ohlcv_data], dtype=float)

        fast_ma = np.convolve(closes, np.ones(self.fast_period) / self.fast_period, mode="valid")
        slow_ma = np.convolve(closes, np.ones(self.slow_period) / self.slow_period, mode="valid")

        min_len = min(len(fast_ma), len(slow_ma))
        fast_ma = fast_ma[-min_len:]
        slow_ma = slow_ma[-min_len:]

        current_fast = fast_ma[-1]
        current_slow = slow_ma[-1]
        prev_fast = fast_ma[-2]
        prev_slow = slow_ma[-2]

        spread = (current_fast - current_slow) / current_slow
        confidence = min(abs(spread) * 100, 1.0)

        if prev_fast <= prev_slow and current_fast > current_slow:
            signal = Signal.BUY
            reasoning = f"Fast MA ({current_fast:.2f}) crossed above Slow MA ({current_slow:.2f})"
        elif prev_fast >= prev_slow and current_fast < current_slow:
            signal = Signal.SELL
            reasoning = f"Fast MA ({current_fast:.2f}) crossed below Slow MA ({current_slow:.2f})"
        else:
            signal = Signal.HOLD
            reasoning = f"No crossover. Fast MA: {current_fast:.2f}, Slow MA: {current_slow:.2f}"
            confidence = 0.0

        return StrategyResult(
            signal=signal,
            confidence=confidence,
            reasoning=reasoning,
            indicators={
                "fast_ma": float(current_fast),
                "slow_ma": float(current_slow),
                "spread_pct": float(spread * 100),
                "fast_period": self.fast_period,
                "slow_period": self.slow_period,
            },
        )
