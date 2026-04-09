from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from config import settings

# PostgreSQL needs connection pooling; SQLite doesn't support it
DATABASE_URL = settings.database_url_async

if settings.is_postgres:
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=10,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
else:
    engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    import models  # noqa: F401 - ensure models are registered
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Safe migrations: add new columns if they don't exist yet
        await conn.run_sync(_migrate_schema)


def _migrate_schema(conn):
    """Add new columns to existing tables without dropping data.
    Uses try/except so this is safe for both SQLite and PostgreSQL."""
    migrations = [
        "ALTER TABLE agent_states ADD COLUMN losses_today INTEGER DEFAULT 0",
        "ALTER TABLE agent_states ADD COLUMN realized_pnl_today REAL DEFAULT 0.0",
        "ALTER TABLE trades ADD COLUMN fee REAL",
        "ALTER TABLE trades ADD COLUMN quote_currency TEXT DEFAULT 'MXN'",
        "ALTER TABLE agent_states ADD COLUMN last_signal TEXT",
        "ALTER TABLE agent_states ADD COLUMN last_tick_at TIMESTAMP",
        "ALTER TABLE agent_states ADD COLUMN symbol TEXT",
        "ALTER TABLE agent_states ADD COLUMN open_position_side TEXT",
        "ALTER TABLE agent_states ADD COLUMN open_position_price REAL",
        "ALTER TABLE agent_states ADD COLUMN open_position_amount REAL",
        "ALTER TABLE agent_states ADD COLUMN rotation_enabled BOOLEAN DEFAULT 0",
        "ALTER TABLE agent_states ADD COLUMN aggressive_rotation BOOLEAN DEFAULT 0",
        "ALTER TABLE agent_states ADD COLUMN rotation_interval_minutes INTEGER DEFAULT 1",
        "ALTER TABLE agent_states ADD COLUMN min_rotation_score_delta REAL DEFAULT 1.0",
        "ALTER TABLE agent_states ADD COLUMN last_market_review_at TIMESTAMP",
        "ALTER TABLE agent_states ADD COLUMN last_rotation_at TIMESTAMP",
        "ALTER TABLE agent_states ADD COLUMN quote_currency TEXT DEFAULT 'MXN'",
        "ALTER TABLE paper_wallet ADD COLUMN btc_balance REAL DEFAULT 0.01",
        "ALTER TABLE paper_wallet ADD COLUMN usd_balance REAL DEFAULT 100.0",
        "ALTER TABLE paper_wallet ADD COLUMN usdt_balance REAL DEFAULT 100.0",
        # Auth table (create via raw SQL so it's not tied to SQLAlchemy models)
        """CREATE TABLE IF NOT EXISTS auth_users (
            email TEXT PRIMARY KEY,
            password_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
    ]
    for sql in migrations:
        try:
            conn.execute(text(sql))
        except Exception:
            pass  # column/table already exists — safe to ignore
    # Backfill symbol for rows that predate this column
    try:
        conn.execute(text("UPDATE agent_states SET symbol = 'BTC/MXN' WHERE symbol IS NULL"))
    except Exception:
        pass
    try:
        conn.execute(text("UPDATE agent_states SET quote_currency = COALESCE(quote_currency, substr(symbol, instr(symbol, '/') + 1)) WHERE symbol IS NOT NULL"))
    except Exception:
        pass
    try:
        conn.execute(text("UPDATE trades SET quote_currency = COALESCE(quote_currency, substr(symbol, instr(symbol, '/') + 1)) WHERE symbol IS NOT NULL"))
    except Exception:
        pass
    try:
        conn.execute(text("UPDATE paper_wallet SET usd_balance = COALESCE(NULLIF(usd_balance, 0), 100.0)"))
        conn.execute(text("UPDATE paper_wallet SET usdt_balance = COALESCE(NULLIF(usdt_balance, 0), 100.0)"))
    except Exception:
        pass
    try:
        conn.execute(text(
            "UPDATE agent_states SET min_rotation_score_delta = 1.0 "
            "WHERE rotation_enabled = 1 AND (min_rotation_score_delta IS NULL OR min_rotation_score_delta = 8.0)"
        ))
    except Exception:
        pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
