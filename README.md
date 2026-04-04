# dayTrader 🤖

An AI crypto day-trading agent platform with a Python FastAPI backend and React TypeScript frontend. Agents run configurable strategies (MA Crossover, RSI) in **paper trading mode** by default, with full risk guardrails and real-time WebSocket updates.

## Features

- **Paper trading** (default) using live Binance price feeds via ccxt — no real money at risk
- **Multiple strategies**: Moving Average Crossover, RSI
- **Risk guardrails**: per-agent stop-loss, max trades/day, budget limits
- **Backtester**: fetch historical OHLCV data and replay strategies with equity curve
- **Real-time dashboard**: WebSocket-driven live updates for trades, P&L, agent status
- **Kill switch**: instantly stop all agents from the UI

## Quick Start

```bash
git clone <repo>
cd dayTrader
chmod +x start.sh
./start.sh
```

Open **http://localhost:5173** in your browser.

## Manual Setup

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd ..
cp .env.example .env
PYTHONPATH=. uvicorn backend.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Configuration

Copy `.env.example` to `.env` and edit as needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `EXCHANGE` | `paper` | `paper`, `bitso`, or `binance` |
| `PAPER_MODE` | `true` | Force paper trading even for real exchanges |
| `TRADING_PAIR` | `BTC/USDT` | Symbol to trade |
| `INITIAL_BUDGET` | `1000.0` | Default agent budget in USD |
| `STOP_LOSS_PCT` | `0.03` | Stop-loss threshold (3%) |
| `MAX_TRADES_PER_DAY` | `10` | Per-agent daily trade limit |

## Architecture

```
dayTrader/
├── backend/               # FastAPI application
│   ├── main.py            # App entry point, CORS, lifespan
│   ├── config.py          # Pydantic settings from .env
│   ├── database.py        # SQLAlchemy async engine + session
│   ├── models.py          # Trade, AgentLog, AgentState ORM models
│   ├── exchange/          # ccxt wrappers + paper trading simulator
│   ├── strategies/        # MA Crossover & RSI strategies
│   ├── backtester/        # Historical backtest runner
│   ├── agents/            # TradingAgent + AgentOrchestrator
│   ├── risk/              # RiskGuardrails (stop-loss, position sizing)
│   └── routers/           # REST API + WebSocket routes
└── frontend/              # React + TypeScript + Tailwind
    └── src/
        ├── App.tsx         # Tab navigation, WebSocket connection
        ├── components/     # Dashboard, AgentCard, BacktestPanel, etc.
        ├── api/            # Axios API client
        ├── hooks/          # useWebSocket with auto-reconnect
        └── types/          # Shared TypeScript interfaces
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/agents` | List all agents |
| POST | `/api/agents` | Create agent `{strategy, params, budget}` |
| POST | `/api/agents/{id}/start` | Start agent |
| POST | `/api/agents/{id}/stop` | Stop agent |
| POST | `/api/agents/{id}/kill` | Kill agent permanently |
| POST | `/api/agents/kill-all` | Kill all agents |
| GET | `/api/agents/{id}/logs` | Agent logs |
| GET | `/api/trades` | List trades |
| GET | `/api/trades/summary` | Aggregate P&L summary |
| POST | `/api/backtest` | Run backtest |
| WS | `/ws` | Real-time updates |

## Live Exchange Setup

Set your `.env` to use a real exchange:

```env
EXCHANGE=binance
PAPER_MODE=false
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
```

> ⚠️ **Warning**: Live trading involves real financial risk. Always test with paper mode first.
