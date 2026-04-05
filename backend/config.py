from pathlib import Path
from pydantic_settings import BaseSettings

# .env lives at project root (one level above backend/)
_ENV_FILE = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    EXCHANGE: str = "bitso"
    BITSO_API_KEY: str = ""
    BITSO_API_SECRET: str = ""
    BINANCE_API_KEY: str = ""
    BINANCE_API_SECRET: str = ""
    TRADING_PAIR: str = "BTC/MXN"
    INITIAL_BUDGET: float = 10000.0
    STOP_LOSS_PCT: float = 0.03
    MAX_TRADES_PER_DAY: int = 10
    DATABASE_URL: str = "sqlite+aiosqlite:///./daytrader.db"
    PAPER_MODE: bool = True

    model_config = {"env_file": str(_ENV_FILE), "extra": "ignore"}


settings = Settings()
