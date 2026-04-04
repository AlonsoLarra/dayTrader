from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class Signal(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class StrategyResult:
    signal: Signal
    confidence: float  # 0-1
    reasoning: str
    indicators: dict = field(default_factory=dict)


class BaseStrategy(ABC):
    def __init__(self, params: dict = None):
        self.params = params or {}

    @abstractmethod
    def analyze(self, ohlcv_data: list) -> StrategyResult:
        """Takes OHLCV list [[timestamp, open, high, low, close, volume], ...], returns signal."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    def min_candles(self) -> int:
        return 50
