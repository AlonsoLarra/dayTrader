from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    EXCHANGE: str = "paper"
    BITSO_API_KEY: str = ""
    BITSO_API_SECRET: str = ""
    BINANCE_API_KEY: str = ""
    BINANCE_API_SECRET: str = ""
    TRADING_PAIR: str = "BTC/USDT"
    INITIAL_BUDGET: float = 1000.0
    STOP_LOSS_PCT: float = 0.03
    MAX_TRADES_PER_DAY: int = 10
    DATABASE_URL: str = "sqlite+aiosqlite:///./daytrader.db"
    PAPER_MODE: bool = True

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
