import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from sqlalchemy import select

from config import settings
from database import init_db, AsyncSessionLocal
from models import AgentState, AutoWatcherLog
from routers import agents, trades, backtest, ws, prices, settings as settings_router, portfolio
from routers import strategy as strategy_router
from routers import auth as auth_router
from routers import auto_watcher as auto_watcher_router
from agents.orchestrator import orchestrator, assess_market_opportunity
from exchange.client import create_exchange, get_available_symbols
from routers.ws import manager

import os
_JWT_SECRET = os.environ.get("JWT_SECRET", "daytrader-local-jwt-secret-change-in-prod")
_JWT_ALGORITHM = "HS256"

_PUBLIC_PATHS = {"/api/health", "/api/auth/login", "/api/auth/check-email", "/api/auth/set-password"}

_log = logging.getLogger("auto_watcher")

AUTO_WATCHER_INTERVAL_SECONDS = 60
AUTO_WATCHER_MIN_SCORE = 30.0
AUTO_WATCHER_MAX_AGENTS = 3
AUTO_WATCHER_QUOTE = "USD"
STARTUP_INIT_TIMEOUT_SECONDS = 8
STARTUP_INIT_RETRIES = 2
STARTUP_INIT_RETRY_DELAY_SECONDS = 2


async def _log_watcher_cycle(
    db,
    action: str,
    pairs_evaluated: int = 0,
    eligible_pairs: int = 0,
    agents_deployed: int = 0,
    details: Optional[dict] = None,
) -> None:
    entry = AutoWatcherLog(
        timestamp=datetime.now(timezone.utc),
        action=action,
        pairs_evaluated=pairs_evaluated,
        eligible_pairs=eligible_pairs,
        agents_deployed=agents_deployed,
        details=json.dumps(details) if details else None,
    )
    db.add(entry)
    await db.commit()


async def _auto_trade_watcher():
    """Background task: when no bots are running, scan the market every 60s and auto-deploy."""
    # Small initial delay so the server finishes starting before the first scan
    await asyncio.sleep(30)

    while True:
        try:
            async with AsyncSessionLocal() as db:
                # Only act when zero bots are currently running
                result = await db.execute(
                    select(AgentState).where(AgentState.status == "running")
                )
                if result.scalars().first():
                    await _log_watcher_cycle(db, "skipped_bots_running")
                    await asyncio.sleep(AUTO_WATCHER_INTERVAL_SECONDS)
                    continue

                quote_currency = AUTO_WATCHER_QUOTE
                min_budget = 0.0001 if quote_currency == "BTC" else 5.0

                # Lazy import to avoid circular dependency at module load time
                from routers.settings import get_available_budget
                available = await get_available_budget(db, quote_currency)
                if available < min_budget:
                    _log.debug("Auto-watcher: insufficient budget (%.4f %s), skipping", available, quote_currency)
                    await _log_watcher_cycle(db, "budget_insufficient", details={
                        "available": available,
                        "min_budget": min_budget,
                        "currency": quote_currency,
                    })
                    await asyncio.sleep(AUTO_WATCHER_INTERVAL_SECONDS)
                    continue

                # Exclude symbols already claimed by any non-killed bot
                active_result = await db.execute(
                    select(AgentState.symbol).where(AgentState.status != "killed")
                )
                active_symbols = {row[0] for row in active_result.all() if row[0]}

                symbols = await get_available_symbols(quote_currency)
                symbols = [s for s in symbols if s not in active_symbols]
                if not symbols:
                    await _log_watcher_cycle(db, "no_symbols", details={
                        "active_symbols": list(active_symbols),
                    })
                    await asyncio.sleep(AUTO_WATCHER_INTERVAL_SECONDS)
                    continue

                exchange = create_exchange()
                market_results = await asyncio.gather(
                    *[assess_market_opportunity(exchange, s) for s in symbols]
                )

                scored = [
                    r for r in market_results
                    if r.get("eligible")
                    and r.get("rank_score", r.get("score", 0.0)) >= AUTO_WATCHER_MIN_SCORE
                ]
                scored = sorted(
                    scored,
                    key=lambda x: x.get("rank_score", x.get("score", 0.0)),
                    reverse=True,
                )[:AUTO_WATCHER_MAX_AGENTS]

                if not scored:
                    _log.info("Auto-watcher: no eligible setups right now, rechecking in %ds", AUTO_WATCHER_INTERVAL_SECONDS)
                    await _log_watcher_cycle(db, "no_eligible_pairs",
                        pairs_evaluated=len(market_results),
                        details={"symbols_scanned": symbols})
                    await asyncio.sleep(AUTO_WATCHER_INTERVAL_SECONDS)
                    continue

                total_score = sum(r.get("rank_score", r.get("score", 0.0)) for r in scored)
                precision = 8 if quote_currency == "BTC" else 2

                deployed_count = 0
                deployment_details = []
                for pair in scored:
                    weight = pair.get("rank_score", pair.get("score", 0.0)) / total_score
                    allocated = round(available * weight, precision)
                    if allocated < min_budget:
                        allocated = min_budget
                    try:
                        agent_id, _ = await orchestrator.create_agent(
                            strategy_name=pair["strategy"],
                            params=pair.get("params", {}),
                            budget=allocated,
                            symbol=pair["symbol"],
                            quote_currency=quote_currency,
                            rotation_enabled=True,
                            aggressive_rotation=True,
                            rotation_interval_minutes=1,
                            min_rotation_score_delta=1.0,
                        )
                        await orchestrator.start_agent(agent_id)
                        deployed_count += 1
                        deployment_details.append({
                            "symbol": pair["symbol"],
                            "agent_id": agent_id,
                            "strategy": pair["strategy"],
                            "score": pair.get("rank_score", pair.get("score", 0.0)),
                            "allocated": allocated,
                        })
                        _log.info(
                            "Auto-watcher: deployed %s (agent %s, budget %.*f %s, score %.1f)",
                            pair["symbol"], agent_id, precision, allocated, quote_currency,
                            pair.get("rank_score", pair.get("score", 0.0)),
                        )
                    except Exception as exc:
                        _log.warning("Auto-watcher: failed to deploy %s: %s", pair["symbol"], exc)
                        deployment_details.append({"symbol": pair["symbol"], "error": str(exc)})

                if not deployed_count:
                    _log.warning("Auto-watcher: all deployments failed, will retry in %ds", AUTO_WATCHER_INTERVAL_SECONDS)

                await _log_watcher_cycle(
                    db,
                    "deployed" if deployed_count > 0 else "error",
                    pairs_evaluated=len(market_results),
                    eligible_pairs=len(scored),
                    agents_deployed=deployed_count,
                    details={"deployments": deployment_details},
                )

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _log.error("Auto-watcher unexpected error: %s", exc, exc_info=True)
            try:
                async with AsyncSessionLocal() as err_db:
                    await _log_watcher_cycle(err_db, "error", details={"error": str(exc)})
            except Exception:
                pass

        await asyncio.sleep(AUTO_WATCHER_INTERVAL_SECONDS)


async def _initialize_runtime_state() -> None:
    await asyncio.wait_for(init_db(), timeout=STARTUP_INIT_TIMEOUT_SECONDS)
    await asyncio.wait_for(orchestrator.reload_from_db(), timeout=STARTUP_INIT_TIMEOUT_SECONDS)


async def _initialize_runtime_state_with_retries() -> None:
    last_exc = None
    for attempt in range(1, STARTUP_INIT_RETRIES + 1):
        try:
            await _initialize_runtime_state()
            if attempt > 1:
                _log.info("Startup dependencies became ready on attempt %d/%d", attempt, STARTUP_INIT_RETRIES)
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last_exc = exc
            _log.warning(
                "Startup initialization attempt %d/%d did not complete: %s",
                attempt,
                STARTUP_INIT_RETRIES,
                exc,
                exc_info=True,
            )
            if attempt < STARTUP_INIT_RETRIES:
                await asyncio.sleep(STARTUP_INIT_RETRY_DELAY_SECONDS)

    if last_exc is not None:
        raise last_exc


async def _background_retry_startup_state(app: FastAPI) -> None:
    while not getattr(app.state, "runtime_ready", False):
        try:
            await asyncio.sleep(15)
            await _initialize_runtime_state_with_retries()
            app.state.runtime_ready = True
            app.state.startup_error = None
            _log.info("Background startup recovery succeeded")
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            app.state.startup_error = str(exc)
            _log.warning("Background startup recovery still failing: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    orchestrator.set_broadcaster(manager)
    app.state.runtime_ready = False
    app.state.startup_error = None
    retry_task = None

    try:
        await _initialize_runtime_state_with_retries()
        app.state.runtime_ready = True
    except Exception as exc:
        app.state.startup_error = str(exc)
        _log.error(
            "Starting API in degraded mode while startup dependencies recover: %s",
            exc,
            exc_info=True,
        )
        retry_task = asyncio.create_task(_background_retry_startup_state(app))

    watcher_task = asyncio.create_task(_auto_trade_watcher())
    yield

    if retry_task:
        retry_task.cancel()
        try:
            await retry_task
        except asyncio.CancelledError:
            pass

    watcher_task.cancel()
    try:
        await watcher_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="dayTrader API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _cors_auth_error(request: Request, detail: str) -> JSONResponse:
    """Return auth errors with CORS headers so browsers don't surface a network error."""
    response = JSONResponse(status_code=401, content={"detail": detail})
    origin = request.headers.get("origin")
    if origin and origin in settings.cors_origins_list:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"
    return response


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Enforce JWT auth on all routes except public paths, WebSocket, and CORS preflight.
    Must return JSONResponse on failure — raising HTTPException inside
    BaseHTTPMiddleware causes a 500 crash on Starlette."""
    path = request.url.path
    if request.method == "OPTIONS" or path.startswith("/ws") or path in _PUBLIC_PATHS:
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return _cors_auth_error(request, "Not authenticated")

    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
        email = str(payload.get("sub", "")).strip().lower()
        allowed_emails = settings.allowed_emails_list
        if not email or (allowed_emails and email not in allowed_emails):
            return _cors_auth_error(request, "Invalid user")
    except JWTError:
        return _cors_auth_error(request, "Invalid or expired token")

    return await call_next(request)


app.include_router(auth_router.router)
app.include_router(agents.router)
app.include_router(trades.router)
app.include_router(backtest.router)
app.include_router(ws.router)
app.include_router(prices.router)
app.include_router(settings_router.router)
app.include_router(strategy_router.router)
app.include_router(portfolio.router)
app.include_router(auto_watcher_router.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
