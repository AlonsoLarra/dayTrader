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

    # Create the base tables first and commit that work before running any
    # idempotent ALTER TABLE migrations. PostgreSQL marks a transaction as
    # failed after a single bad ALTER, which would otherwise roll back the
    # newly created tables on first boot.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.begin() as conn:
        await conn.run_sync(_migrate_schema)


def _migrate_schema(conn):
    """Add new columns to existing tables without dropping data.
    Each statement runs in a savepoint so PostgreSQL failures do not poison
    the entire transaction during startup."""
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
        "ALTER TABLE agent_states ADD COLUMN stop_loss_pct REAL",
        "ALTER TABLE agent_states ADD COLUMN position_size_pct REAL",
        "ALTER TABLE paper_wallet ADD COLUMN realized_pnl_banked_mxn  REAL DEFAULT 0.0",
        "ALTER TABLE paper_wallet ADD COLUMN realized_pnl_banked_btc  REAL DEFAULT 0.0",
        "ALTER TABLE paper_wallet ADD COLUMN realized_pnl_banked_usd  REAL DEFAULT 0.0",
        "ALTER TABLE paper_wallet ADD COLUMN realized_pnl_banked_usdt REAL DEFAULT 0.0",
        """CREATE TABLE IF NOT EXISTS risk_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            max_losses_per_day INTEGER NOT NULL DEFAULT 3,
            max_daily_loss_pct REAL NOT NULL DEFAULT 0.05,
            max_trades_per_day INTEGER NOT NULL DEFAULT 10,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
    ]
    def _run_safe(sql: str) -> None:
        try:
            with conn.begin_nested():
                conn.execute(text(sql))
        except Exception:
            pass  # already applied / not applicable for this database

    for sql in migrations:
        _run_safe(sql)

    # Backfill data for rows that predate these columns
    _run_safe("UPDATE agent_states SET symbol = 'BTC/MXN' WHERE symbol IS NULL")
    _run_safe("UPDATE agent_states SET quote_currency = COALESCE(quote_currency, substr(symbol, instr(symbol, '/') + 1)) WHERE symbol IS NOT NULL")
    _run_safe("UPDATE trades SET quote_currency = COALESCE(quote_currency, substr(symbol, instr(symbol, '/') + 1)) WHERE symbol IS NOT NULL")
    _run_safe("UPDATE paper_wallet SET usd_balance = COALESCE(NULLIF(usd_balance, 0), 100.0)")
    _run_safe("UPDATE paper_wallet SET usdt_balance = COALESCE(NULLIF(usdt_balance, 0), 100.0)")
    _run_safe(
        "UPDATE agent_states SET min_rotation_score_delta = 1.0 "
        "WHERE rotation_enabled = 1 AND (min_rotation_score_delta IS NULL OR min_rotation_score_delta = 8.0)"
    )
    # Seed the single risk_config row if it doesn't exist yet
    _run_safe(
        "INSERT INTO risk_config (max_losses_per_day, max_daily_loss_pct, max_trades_per_day, updated_at) "
        "SELECT 3, 0.05, 10, CURRENT_TIMESTAMP "
        "WHERE NOT EXISTS (SELECT 1 FROM risk_config)"
    )
    # Backfill banked P&L from trades of agents that were already deleted
    for _quote, _col in [
        ("MXN", "realized_pnl_banked_mxn"),
        ("BTC", "realized_pnl_banked_btc"),
        ("USD", "realized_pnl_banked_usd"),
        ("USDT", "realized_pnl_banked_usdt"),
    ]:
        _run_safe(
            f"UPDATE paper_wallet SET {_col} = COALESCE("
            f"  (SELECT SUM(t.pnl) FROM trades t"
            f"   WHERE t.quote_currency = '{_quote}' AND t.pnl IS NOT NULL"
            f"   AND t.agent_id NOT IN (SELECT agent_id FROM agent_states)"
            f"), 0.0) WHERE {_col} = 0.0"
        )


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
