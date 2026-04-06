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
    # Comma-separated list of allowed frontend origins
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    # Optional allowlist for login emails. Override in .env for production.
    ALLOWED_EMAILS: str = "alonzo.larraguibel@gmail.com"
    # Optional API secret — if set, all /api requests require Authorization: Bearer <key>
    API_SECRET_KEY: str = ""
    # Exit criteria: stop opening new positions if either threshold is hit today
    MAX_LOSSES_PER_DAY: int = 3        # max number of losing trades per bot per day
    MAX_DAILY_LOSS_PCT: float = 0.05   # max loss as a fraction of budget (e.g. 0.05 = 5%)

    model_config = {"env_file": str(_ENV_FILE), "extra": "ignore"}

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_emails_list(self) -> list[str]:
        return [email.strip().lower() for email in self.ALLOWED_EMAILS.split(",") if email.strip()]

    @property
    def is_postgres(self) -> bool:
        return self.DATABASE_URL.startswith("postgresql")


settings = Settings()
