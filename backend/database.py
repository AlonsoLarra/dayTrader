from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from config import settings

# PostgreSQL needs connection pooling; SQLite doesn't support it
if settings.is_postgres:
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_size=10,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
else:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

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
        "ALTER TABLE trades ADD COLUMN fee REAL",
        "ALTER TABLE agent_states ADD COLUMN last_signal TEXT",
        "ALTER TABLE agent_states ADD COLUMN last_tick_at TIMESTAMP",
        "ALTER TABLE agent_states ADD COLUMN symbol TEXT",
        "ALTER TABLE agent_states ADD COLUMN open_position_side TEXT",
        "ALTER TABLE agent_states ADD COLUMN open_position_price REAL",
        "ALTER TABLE agent_states ADD COLUMN open_position_amount REAL",
    ]
    for sql in migrations:
        try:
            conn.execute(text(sql))
        except Exception:
            pass  # column already exists — safe to ignore on both SQLite and PostgreSQL
    # Backfill symbol for rows that predate this column
    try:
        conn.execute(text("UPDATE agent_states SET symbol = 'BTC/MXN' WHERE symbol IS NULL"))
    except Exception:
        pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
