import numpy as np
from strategies.base import BaseStrategy, Signal, StrategyResult


class RSIStrategy(BaseStrategy):
    """RSI-based trading strategy."""

    def __init__(self, params: dict = None):
        super().__init__(params)
        self.period: int = int(self.params.get("period", 14))
        self.oversold: float = float(self.params.get("oversold", 30))
        self.overbought: float = float(self.params.get("overbought", 70))

    @property
    def name(self) -> str:
        return "rsi"

    @property
    def min_candles(self) -> int:
        return self.period + 2

    def _calculate_rsi(self, closes: np.ndarray) -> np.ndarray:
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)

        avg_gain = float(np.mean(gains[: self.period]))
        avg_loss = float(np.mean(losses[: self.period]))

        rsi_values = []
        for i in range(self.period, len(deltas)):
            avg_gain = (avg_gain * (self.period - 1) + gains[i]) / self.period
            avg_loss = (avg_loss * (self.period - 1) + losses[i]) / self.period
            rs = avg_gain / avg_loss if avg_loss != 0 else 100.0
            rsi = 100.0 - (100.0 / (1.0 + rs))
            rsi_values.append(rsi)

        return np.array(rsi_values)

    def analyze(self, ohlcv_data: list, entry_price: float = None, candles_held: int = 0) -> StrategyResult:
        if len(ohlcv_data) < self.min_candles:
            return StrategyResult(
                signal=Signal.HOLD,
                confidence=0.0,
                reasoning=f"Insufficient data: {len(ohlcv_data)} candles, need {self.min_candles}",
                indicators={},
            )

        closes = np.array([c[4] for c in ohlcv_data], dtype=float)
        rsi_values = self._calculate_rsi(closes)

        if len(rsi_values) < 2:
            return StrategyResult(
                signal=Signal.HOLD,
                confidence=0.0,
                reasoning="Not enough RSI values computed",
                indicators={},
            )

        current_rsi = float(rsi_values[-1])
        prev_rsi = float(rsi_values[-2])

        if current_rsi < self.oversold:
            confidence = min((self.oversold - current_rsi) / self.oversold, 1.0)
            signal = Signal.BUY
            reasoning = f"RSI oversold at {current_rsi:.2f} (threshold: {self.oversold})"
        elif current_rsi > self.overbought:
            confidence = min((current_rsi - self.overbought) / (100 - self.overbought), 1.0)
            signal = Signal.SELL
            reasoning = f"RSI overbought at {current_rsi:.2f} (threshold: {self.overbought})"
        else:
            signal = Signal.HOLD
            confidence = 0.0
            reasoning = f"RSI at {current_rsi:.2f}, within neutral zone [{self.oversold}, {self.overbought}]"

        return StrategyResult(
            signal=signal,
            confidence=confidence,
            reasoning=reasoning,
            indicators={
                "rsi": current_rsi,
                "prev_rsi": prev_rsi,
                "oversold": self.oversold,
                "overbought": self.overbought,
                "period": self.period,
            },
        )
