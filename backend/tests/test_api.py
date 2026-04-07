"""
API smoke tests — cover every major endpoint so regressions are caught immediately.
These run against an in-memory DB with no real exchange calls.
"""
import pytest

from config import settings


# ── Health / Auth ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_auth_flow_allows_configured_owner_email(client):
    email = settings.allowed_emails_list[0]

    check = await client.post("/api/auth/check-email", json={"email": email})
    assert check.status_code == 200
    assert check.json()["has_password"] is False

    setup = await client.post(
        "/api/auth/set-password",
        json={"email": email, "password": "strong-pass-123"},
    )
    assert setup.status_code == 200
    assert setup.json()["token"]

    login = await client.post(
        "/api/auth/login",
        json={"email": email, "password": "strong-pass-123"},
    )
    assert login.status_code == 200
    assert login.json()["token"]


# ── Mode toggle ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_mode_default(client):
    r = await client.get("/api/settings/mode")
    assert r.status_code == 200
    data = r.json()
    assert "paper_mode" in data
    assert isinstance(data["paper_mode"], bool)


@pytest.mark.asyncio
async def test_set_mode(client):
    # Toggle to paper (safe to toggle back)
    r = await client.post("/api/settings/mode", json={"paper_mode": True})
    assert r.status_code == 200
    assert r.json()["paper_mode"] is True


# ── Paper wallet ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_paper_wallet_returns_defaults(client):
    r = await client.get("/api/settings/paper-wallet")
    assert r.status_code == 200
    data = r.json()
    assert "starting_balance" in data
    assert "available" in data
    assert "deployed" in data
    assert "in_market" in data
    # Fresh DB — nothing deployed
    assert data["deployed"] == 0.0
    assert data["available"] == data["starting_balance"]


@pytest.mark.asyncio
async def test_set_paper_wallet(client):
    r = await client.post("/api/settings/paper-wallet", json={"starting_balance": 500.0})
    assert r.status_code == 200
    assert r.json()["starting_balance"] == 500.0

    # Verify it persisted
    r2 = await client.get("/api/settings/paper-wallet")
    assert r2.json()["starting_balance"] == 500.0

    # Reset for other tests
    await client.post("/api/settings/paper-wallet", json={"starting_balance": 100.0})


@pytest.mark.asyncio
async def test_set_paper_wallet_rejects_zero(client):
    r = await client.post("/api/settings/paper-wallet", json={"starting_balance": 0})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_set_paper_wallet_rejects_negative(client):
    r = await client.post("/api/settings/paper-wallet", json={"starting_balance": -50})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_paper_wallet_available_reflects_closed_agent_losses(client):
    from datetime import datetime
    from models import AgentState, Trade
    from tests.conftest import TestingSessionLocal

    await client.post("/api/settings/paper-wallet", json={"starting_balance": 500.0})

    async with TestingSessionLocal() as session:
        now = datetime.utcnow()
        session.add(AgentState(
            agent_id="loss-bot",
            strategy="rsi",
            status="killed",
            budget_allocated=100.0,
            budget_used=0.0,
            trades_today=1,
            losses_today=1,
            realized_pnl_today=-20.0,
            symbol="XRP/MXN",
            created_at=now,
            updated_at=now,
        ))
        session.add(Trade(
            agent_id="loss-bot",
            symbol="XRP/MXN",
            side="sell",
            amount=10.0,
            price=8.0,
            timestamp=now,
            pnl=-20.0,
            fee=1.0,
            mode="paper",
            strategy="rsi",
        ))
        await session.commit()

    r = await client.get("/api/settings/paper-wallet")
    assert r.status_code == 200
    assert r.json()["available"] == pytest.approx(480.0)


@pytest.mark.asyncio
async def test_list_agents_includes_cumulative_realized_pnl(client):
    from datetime import datetime
    from models import AgentState, Trade
    from tests.conftest import TestingSessionLocal

    async with TestingSessionLocal() as session:
        now = datetime.utcnow()
        session.add(AgentState(
            agent_id="running-loss-bot",
            strategy="rsi",
            status="running",
            budget_allocated=100.0,
            budget_used=0.0,
            trades_today=2,
            losses_today=1,
            realized_pnl_today=-5.0,
            symbol="XRP/MXN",
            created_at=now,
            updated_at=now,
        ))
        session.add(Trade(
            agent_id="running-loss-bot",
            symbol="XRP/MXN",
            side="sell",
            amount=5.0,
            price=9.0,
            timestamp=now,
            pnl=-12.5,
            fee=0.5,
            mode="paper",
            strategy="rsi",
        ))
        await session.commit()

    r = await client.get("/api/agents")
    assert r.status_code == 200
    agent = next(a for a in r.json() if a["agent_id"] == "running-loss-bot")
    assert agent["realized_pnl_total"] == pytest.approx(-12.5)


# ── Agents ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_agents_empty(client):
    r = await client.get("/api/agents")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_create_agent_over_budget_rejected(client):
    """Requesting more budget than the wallet has must be rejected."""
    # Wallet has 100 MXN (reset above); request 999 MXN
    r = await client.post("/api/agents", json={
        "strategy": "RSI",
        "budget": 999.0,
        "symbol": "XRP/MXN",
    })
    assert r.status_code == 400
    assert "Insufficient" in r.json()["detail"]


@pytest.mark.asyncio
async def test_list_markets(client):
    r = await client.get("/api/agents/markets")
    assert r.status_code == 200
    data = r.json()
    assert "symbols" in data
    assert "BTC/MXN" in data["symbols"]
    assert "XRP/MXN" in data["symbols"]


@pytest.mark.asyncio
async def test_get_nonexistent_agent_404(client):
    r = await client.get("/api/agents/does-not-exist")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_kill_agent_succeeds_or_404(client):
    # Kill is a soft operation — it succeeds if agent not in orchestrator memory
    r = await client.post("/api/agents/does-not-exist/kill")
    assert r.status_code in (200, 404)


@pytest.mark.asyncio
async def test_positions_returns_data(client):
    r = await client.get("/api/agents/positions")
    assert r.status_code == 200
    data = r.json()
    # Endpoint returns {"positions": [...]}
    assert "positions" in data
    assert isinstance(data["positions"], list)


# ── Trades ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_trades(client):
    r = await client.get("/api/trades")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_trade_summary(client):
    r = await client.get("/api/trades/summary")
    assert r.status_code == 200
    data = r.json()
    for key in ("total_pnl", "total_trades", "win_rate", "total_allocated"):
        assert key in data, f"Missing key: {key}"


# ── Prices ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_prices_endpoint(client):
    r = await client.get("/api/prices")
    # May fail with 502 if Bitso unreachable in CI, but endpoint must exist
    assert r.status_code in (200, 502)


# ── Strategy visibility ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_strategy_market_scan_includes_pair_decisions(client):
    r = await client.get("/api/strategy/market-scan")
    assert r.status_code == 200
    data = r.json()
    assert "pairs" in data
    assert isinstance(data["pairs"], list)
    assert len(data["pairs"]) > 0
    first = data["pairs"][0]
    for key in ("symbol", "score", "rsi", "price", "strategy", "action", "reason"):
        assert key in first, f"Missing key: {key}"


@pytest.mark.asyncio
async def test_strategy_reasoning_returns_bots_key(client):
    r = await client.get("/api/strategy/reasoning")
    assert r.status_code == 200
    assert "bots" in r.json()


# ── Portfolio / Smart Deploy ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deploy_over_budget_rejected(client):
    """Smart deploy requesting more than wallet should be rejected."""
    r = await client.post("/api/portfolio/deploy", json={
        "budget": 9999.0,
        "max_agents": 3,
        "min_score": 20,
    })
    # Either 400 (budget check) or 502 (can't reach Bitso for analysis) is acceptable
    assert r.status_code in (400, 502)
