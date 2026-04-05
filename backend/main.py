from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db
from routers import agents, trades, backtest, ws, prices, settings as settings_router, portfolio
from routers import strategy as strategy_router
from agents.orchestrator import orchestrator
from routers.ws import manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    orchestrator.set_broadcaster(manager)
    await orchestrator.reload_from_db()
    yield


app = FastAPI(title="dayTrader API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Enforce Bearer token auth when API_SECRET_KEY is configured."""
    if settings.API_SECRET_KEY:
        # Let WebSocket and health pass through unprotected
        if not request.url.path.startswith("/ws") and request.url.path != "/api/health":
            auth_header = request.headers.get("Authorization", "")
            if auth_header != f"Bearer {settings.API_SECRET_KEY}":
                raise HTTPException(status_code=401, detail="Unauthorized")
    return await call_next(request)


app.include_router(agents.router)
app.include_router(trades.router)
app.include_router(backtest.router)
app.include_router(ws.router)
app.include_router(prices.router)
app.include_router(settings_router.router)
app.include_router(strategy_router.router)
app.include_router(portfolio.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
