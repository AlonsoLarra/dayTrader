"""
Shared fixtures for backend tests.
Uses an in-memory SQLite database so tests are isolated and fast.
"""
import sys
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# Ensure backend package root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use in-memory DB for tests — must be set before any app module is imported
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["PAPER_MODE"] = "true"
os.environ["BITSO_API_KEY"] = ""
os.environ["BITSO_API_SECRET"] = ""
os.environ["OPENAI_API_KEY"] = ""

from database import Base, get_db  # noqa: E402
from main import app               # noqa: E402

# Override the DB engine to use in-memory SQLite
test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
TestingSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """Create all tables once per test session."""
    import models  # noqa: F401
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def client():
    """HTTP client bound to the FastAPI app with the test DB."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
