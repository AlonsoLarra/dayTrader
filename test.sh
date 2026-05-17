#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PASS=0; FAIL=0

run_suite() {
  local name="$1"
  shift
  echo ""
  echo "━━━ $name ━━━"
  if "$@"; then
    echo "✓ $name passed"
    PASS=$((PASS+1))
  else
    echo "✗ $name FAILED"
    FAIL=$((FAIL+1))
  fi
}

# ── Backend: unit tests (paper trading, guardrails) ───────────────────────
run_suite "Backend unit tests" \
  bash -c "cd '$SCRIPT_DIR/backend' && PYTHONPATH='$SCRIPT_DIR/backend' .venv/bin/pytest tests/test_paper_trading.py -v --tb=short -q"

# ── Backend: API smoke tests ──────────────────────────────────────────────
run_suite "Backend API tests" \
  bash -c "cd '$SCRIPT_DIR/backend' && PYTHONPATH='$SCRIPT_DIR/backend' .venv/bin/pytest tests/test_api.py -v --tb=short -q"

# ── Backend: backtester unit tests (Phase 0) ──────────────────────────────
run_suite "Backend backtester tests" \
  bash -c "cd '$SCRIPT_DIR/backend' && PYTHONPATH='$SCRIPT_DIR/backend' .venv/bin/pytest tests/test_backtester.py -v --tb=short -q"

# ── Backend: strict typing on new backtester code (Phase 0) ───────────────
run_suite "Backend mypy --strict (backtester)" \
  bash -c "cd '$SCRIPT_DIR/backend' && .venv/bin/mypy --config-file mypy.ini -p backtester"

# ── Frontend: TypeScript compile check ────────────────────────────────────
run_suite "Frontend TypeScript" \
  bash -c "cd '$SCRIPT_DIR/frontend' && npx tsc --noEmit 2>&1"

# ── Frontend: component tests ─────────────────────────────────────────────
run_suite "Frontend component tests" \
  bash -c "cd '$SCRIPT_DIR/frontend' && npm test 2>&1"

# ── Summary ───────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $FAIL -eq 0 ]; then
  echo "✅ All $PASS suites passed"
  exit 0
else
  echo "❌ $FAIL suite(s) FAILED  ($PASS passed)"
  exit 1
fi
