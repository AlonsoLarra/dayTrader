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
from sqlalchemy.pool import StaticPool

# Ensure backend package root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use a temporary file-backed SQLite DB for tests so all async connections share state
TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test_app.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"
os.environ["PAPER_MODE"] = "true"
os.environ["BITSO_API_KEY"] = ""
os.environ["BITSO_API_SECRET"] = ""
os.environ["OPENAI_API_KEY"] = ""
# Use a known test secret so we can mint valid tokens
os.environ["JWT_SECRET"] = "test-secret-for-tests-only"

from database import Base, get_db, _migrate_schema  # noqa: E402
from main import app                              # noqa: E402

# Override the DB engine to use the shared test SQLite file
test_engine = create_async_engine(
    os.environ["DATABASE_URL"],
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """Create all tables once per test session."""
    import models  # noqa: F401
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_schema)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


@pytest_asyncio.fixture()
async def client(setup_database):
    """HTTP client bound to the FastAPI app with the test DB."""
    from datetime import datetime, timedelta
    from jose import jwt as _jwt
    # Mint a valid token for the allowed user so all API calls pass auth
    token = _jwt.encode(
        {"sub": "alonzo.larraguibel@gmail.com", "exp": datetime.utcnow() + timedelta(days=1)},
        "test-secret-for-tests-only",
        algorithm="HS256",
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as ac:
        yield ac
