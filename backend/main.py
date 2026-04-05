from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import agents, trades, backtest, ws, prices, settings as settings_router, portfolio
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
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router)
app.include_router(trades.router)
app.include_router(backtest.router)
app.include_router(ws.router)
app.include_router(prices.router)
app.include_router(settings_router.router)
app.include_router(portfolio.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
