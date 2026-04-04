#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check .env exists
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "No .env found, copying from .env.example..."
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
fi

# Kill any stale processes on our ports
echo "Cleaning up stale processes..."
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:5173 | xargs kill -9 2>/dev/null || true
sleep 1

cleanup() {
    echo ""
    echo "Shutting down..."
    kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM

# ── Backend ──────────────────────────────────────────────────────────────────
cd "$SCRIPT_DIR/backend"
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate
echo "Installing backend dependencies..."
pip install -r requirements.txt -q

cd "$SCRIPT_DIR/backend"
PYTHONPATH="$SCRIPT_DIR/backend" uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!
echo "Backend started (PID $BACKEND_PID) at http://localhost:8000"

# ── Frontend ─────────────────────────────────────────────────────────────────
cd "$SCRIPT_DIR/frontend"
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi
npm run dev &
FRONTEND_PID=$!
echo "Frontend started (PID $FRONTEND_PID) at http://localhost:5173"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║  dayTrader is running!               ║"
echo "║  Frontend: http://localhost:5173     ║"
echo "║  Backend:  http://localhost:8000     ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Press Ctrl+C to stop."
wait
