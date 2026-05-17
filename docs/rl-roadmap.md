# dayTrader v2 — RL Bot Refactor Roadmap
**Spec-Driven Development**

---

## Context

dayTrader today trades with static, hand-tuned strategies (MA Crossover, RSI,
TrendRSI, Adaptive). This roadmap transforms the bot into a self-tuning
**reinforcement-learning agent** with automatic exploration and market-drift
detection, while keeping the existing strategies as always-available
performance baselines.

This document is the single source of truth for the multi-phase program. Each
phase is delivered as its own focused PR; later phases must not start before
the previous one is merged and its acceptance criteria are met.

---

## Core Mission

An "auto-exploration" RL agent that:

- Learns continuously from market data.
- Self-adjusts its exploration rate without manual tuning.
- Detects market regime changes and triggers retraining.
- Preserves existing strategies as performance baselines.

---

## Technical Stack Additions

| Concern | Tooling |
|---|---|
| RL framework | stable-baselines3 (PPO, SAC) |
| Tensors | PyTorch |
| Hyperparameter tuning | Optuna |
| Drift detection | river (Page-Hinkley test) |
| Model registry | MLflow |
| Time-series storage | TimescaleDB extension on the existing Postgres |

> These dependencies are introduced **only in the phase that first needs
> them** — Phase 0 adds none of them.

---

## Development Phases

| Phase | Goal |
|---|---|
| **0** | Robust walk-forward backtester with a metrics suite (Sharpe, Sortino, max drawdown). |
| **1** | Feature pipeline and normalized state representation with lookahead prevention. |
| **2** | PPO strategy as a Gymnasium environment with a standardized reward function. |
| **3** | Automatic exploration adjustment and concept-drift detection via the Page-Hinkley test. |
| **4** | Separate training worker with a champion/challenger model-promotion pattern. |
| **5** | UI inspector for RL transparency (equity curves, feature attribution, drift status). |
| **6** | After 90 days of successful paper trading, gated live trading with strict capital caps ($100 max). |

---

## Non-Negotiable Principles

- Paper trading stays the default; live trading requires explicit, multi-step
  confirmation.
- Existing MA/RSI/TrendRSI/Adaptive strategies **cannot be removed**.
- Code must pass `mypy --strict`; **no bare `except` clauses**.
- Each PR limited to **400 lines** of non-test code.
- Live trading sits behind feature flags with circuit breakers for drawdown
  protection.

## Execution Protocol

1. Read the full spec before coding.
2. Write failing tests first.
3. Complete one phase before advancing.
4. Document decisions in the phase report below.
5. Use conventional commits with phase prefixes (e.g.
   `feat(phase-0): …`).

---

## Phase 0 — Walk-Forward Backtester + Metrics Suite

**Status:** ✅ Implemented (active phase).

**Problem.** The legacy backtester (`backend/backtester/runner.py`) was a
single-pass replay with no out-of-sample segmentation, no Sortino ratio, an
error-swallowing `except`, no type coverage, and simulation logic coupled to
`ccxt` (so it could not be unit-tested offline). Every later RL phase needs a
trustworthy evaluation harness first.

**Specification.**

- Extract the trade-simulation loop into a pure, network-free, fully-typed
  engine (`backtester/engine.py`) — the single source of truth shared by the
  single-pass and walk-forward runners. Behaviour is byte-equivalent to the
  legacy loop so existing `POST /api/backtest` results do not change.
- Pure metrics module (`backtester/metrics.py`): periodic returns, Sharpe,
  **Sortino** (downside-deviation denominator), max drawdown, total return,
  win rate — all deterministic and unit-testable, no division-by-zero.
- Walk-forward harness (`backtester/walk_forward.py`): partition the
  evaluatable region into contiguous, non-overlapping out-of-sample folds
  (earlier candles used purely as indicator warmup; the strategy never sees a
  future candle), with per-fold metrics plus aggregate robustness stats
  (mean/std fold return, % profitable folds, worst-fold drawdown).
- Additive API only: `POST /api/backtest` keeps its shape and gains a
  `sortino_ratio` field; new `POST /api/backtest/walk-forward` endpoint.
- `mypy --strict` enforced on the `backtester.*` package via
  `backend/mypy.ini`; wired into `test.sh`.

**Acceptance criteria.**

- [x] Simulation engine is byte-equivalent to the legacy loop (regression
      oracle test).
- [x] Strategy never receives a window containing future candles (lookahead
      test).
- [x] Sharpe/Sortino/max-drawdown handle zero-variance / no-downside / empty
      inputs without crashing.
- [x] Walk-forward folds are contiguous, non-overlapping, and reject
      insufficient data.
- [x] `POST /api/backtest` response unchanged except for the additive
      `sortino_ratio`; existing 54 backend tests still pass.
- [x] `mypy --config-file mypy.ini -p backtester` reports no issues.

**Files.** `backend/backtester/engine.py` (new),
`backend/backtester/metrics.py` (new),
`backend/backtester/walk_forward.py` (new),
`backend/backtester/runner.py` (refactor),
`backend/routers/backtest.py` (additive endpoint),
`backend/mypy.ini` (new), `backend/requirements.txt`, `test.sh`,
`backend/tests/test_backtester.py` (new).

**Verification.**

```bash
cd backend
PYTHONPATH=. .venv/bin/pytest tests/ -q          # all suites green
.venv/bin/mypy --config-file mypy.ini -p backtester
# Manual: POST /api/backtest (now includes sortino_ratio) and
#         POST /api/backtest/walk-forward {"n_folds": 3, ...}
```

---

## Phase Reports

### Phase 0
- Extracted `engine.simulate` as the shared, offline-testable core; `runner`
  is now network-orchestration only.
- Legacy error-swallowing `except Exception` replaced with
  `except ccxt.BaseError`, surfacing a structured `warning` while still
  returning partial data — no silent failures, no bare `except`.
- `mypy --strict` is scoped to `backtester.*` only; legacy modules are
  intentionally deferred and will be tightened by later phases.
- No new runtime dependencies (only `mypy` as a typing gate) — keeps Phase 0
  free of the heavy ML stack.
