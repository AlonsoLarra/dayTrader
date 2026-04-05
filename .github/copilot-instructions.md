# dayTrader — Project Guidelines

## Project Overview

Local AI crypto day-trading platform. FastAPI (Python 3.9) backend + React/TypeScript/Tailwind frontend. Connects to Bitso (Mexican exchange). Runs paper trading by default (real prices, simulated orders). Multi-agent architecture — each agent runs a strategy (RSI, MA Crossover, AUTO) on a symbol with an isolated budget.

## Architecture

- `backend/` — FastAPI app, `main.py` is entry point, `PYTHONPATH=backend`
- `backend/agents/` — `agent.py` (trading loop), `orchestrator.py` (lifecycle manager)
- `backend/exchange/` — `paper_trading.py` (fee/spread simulation), `client.py` (real Bitso via ccxt)
- `backend/routers/` — `agents.py`, `settings.py`, `portfolio.py`, `trades.py`
- `backend/risk/guardrails.py` — position sizing (25%), stop-loss, daily trade limits
- `frontend/src/components/` — React components; `App.tsx` is the shell
- `frontend/src/api/client.ts` — all API calls (axios)

## Build & Test

```bash
./start.sh       # Start backend (port 8000) + frontend (port 5173)
./test.sh        # Run all 4 test suites — always run before considering a feature done
```

Test suites (42 tests total):
- Backend unit: paper trading fees, spread, guardrails
- Backend API: every endpoint via httpx + in-memory SQLite
- Frontend TypeScript: `tsc --noEmit`
- Frontend components: Vitest + Testing Library

## Critical Rules

### After every feature, run the Test Runner agent

**Always invoke the Test Runner subagent after completing any feature or code change.**
This is non-negotiable. Do not mark a task complete until tests pass.

To invoke: delegate to the `Test Runner` agent (`.github/agents/test-runner.agent.md`).
It will run `./test.sh`, surface failures in plain English, and ask the user which to fix.

### Code conventions

- Python 3.9: use `Optional[X]`, `List[X]` from `typing` — no `X | Y` union syntax
- SQLAlchemy 2: all raw SQL must use `text()` wrapper
- DB migrations: `ALTER TABLE ADD COLUMN` in try/except (idempotent)
- Route ordering: static routes (`/positions`, `/kill-all`) must come BEFORE wildcard routes (`/{agent_id}`) in FastAPI
- No emojis in UI — professional, clean aesthetic
- `vi.mock()` factories are hoisted — declare mock functions as `vi.fn()` inside the factory, not as external variables

### Paper trading realism

- Taker fee: 0.625% on every order
- Bid/ask spread simulated per pair (see `SPREAD` dict in `paper_trading.py`)
- Position sizing: 25% of available budget per trade
- Wallet enforced: agents cannot allocate more than available paper wallet balance
- Min order sizes enforced per pair (see `MIN_ORDER_AMOUNT` in `paper_trading.py`)

## Key Files

- `backend/exchange/paper_trading.py` — fee/spread/slippage simulation
- `backend/agents/agent.py` — trading loop, force_sell, kill, daily reset
- `backend/routers/settings.py` — `get_available_budget()` shared helper
- `frontend/src/components/WalletHeader.tsx` — header wallet pill + dropdown (paper/live toggle)
- `frontend/src/components/AutoTradeModal.tsx` — smart deploy modal (analyze + deploy)
- `backend/tests/test_api.py` — API smoke tests
- `backend/tests/test_paper_trading.py` — unit tests for trading logic
- `frontend/src/test/components.test.tsx` — UI component tests
