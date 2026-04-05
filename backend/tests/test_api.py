"""
API smoke tests — cover every major endpoint so regressions are caught immediately.
These run against an in-memory DB with no real exchange calls.
"""
import pytest


# ── Health ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


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
