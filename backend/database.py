from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import settings

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
    """Add new columns to existing tables without dropping data."""
    migrations = [
        "ALTER TABLE agent_states ADD COLUMN last_signal TEXT",
        "ALTER TABLE agent_states ADD COLUMN last_tick_at DATETIME",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except Exception:
            pass  # column already exists


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
