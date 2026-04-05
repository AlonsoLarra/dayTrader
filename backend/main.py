from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError, jwt

from config import settings
from database import init_db
from routers import agents, trades, backtest, ws, prices, settings as settings_router, portfolio
from routers import strategy as strategy_router
from routers import auth as auth_router
from agents.orchestrator import orchestrator
from routers.ws import manager

ALLOWED_EMAIL = "alonzo.larraguibel@gmail.com"

import os
_JWT_SECRET = os.environ.get("JWT_SECRET", "daytrader-local-jwt-secret-change-in-prod")
_JWT_ALGORITHM = "HS256"

_PUBLIC_PATHS = {"/api/health", "/api/auth/login", "/api/auth/check-email", "/api/auth/set-password"}


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
    """Enforce JWT auth on all routes except public paths and WebSocket.
    Must return JSONResponse on failure — raising HTTPException inside
    BaseHTTPMiddleware causes a 500 crash on Starlette."""
    path = request.url.path
    if path.startswith("/ws") or path in _PUBLIC_PATHS:
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
        if payload.get("sub") != ALLOWED_EMAIL:
            return JSONResponse(status_code=401, content={"detail": "Invalid user"})
    except JWTError:
        return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})

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


@app.get("/api/health")
async def health():
    return {"status": "ok"}
