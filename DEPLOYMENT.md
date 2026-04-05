# Deploying dayTrader to the Cloud

**Recommended stack:** Railway (backend + PostgreSQL) + Vercel (frontend)

---

## 1 — Prepare your repo

```bash
cp .env.example .env           # fill in your real values
cp frontend/.env.example frontend/.env  # fill in production URLs after deploy
git add -A && git commit -m "cloud deployment config"
git push origin main
```

---

## 2 — Deploy the Backend on Railway

1. Go to [railway.app](https://railway.app) → **New Project → Deploy from GitHub**
2. Select your `dayTrader` repo
3. Railway will detect `railway.toml` and use it automatically
4. Add a **PostgreSQL** plugin: click **+ New** → **Database → PostgreSQL**
5. In your service → **Variables**, set:

| Variable | Value |
|---|---|
| `DATABASE_URL` | (auto-filled by Railway from the Postgres plugin) |
| `EXCHANGE` | `bitso` |
| `PAPER_MODE` | `true` |
| `BITSO_API_KEY` | your key |
| `BITSO_API_SECRET` | your secret |
| `CORS_ORIGINS` | `https://your-app.vercel.app` (fill in after Vercel deploy) |
| `API_SECRET_KEY` | `$(openssl rand -hex 32)` — generate a strong key |

6. Railway will build and deploy. Copy the URL: `https://your-app.railway.app`

---

## 3 — Deploy the Frontend on Vercel

1. Go to [vercel.com](https://vercel.com) → **Add New Project → Import Git Repository**
2. Select your `dayTrader` repo
3. **Root directory**: leave as `/` (Vercel will use `vercel.json`)
4. In **Environment Variables**, set:

| Variable | Value |
|---|---|
| `VITE_API_BASE_URL` | `https://your-app.railway.app/api` |
| `VITE_WS_URL` | `wss://your-app.railway.app/ws` |
| `VITE_API_SECRET_KEY` | same value as `API_SECRET_KEY` in Railway |

5. Deploy → Vercel gives you: `https://your-app.vercel.app`

---

## 4 — Link them together

- Back in Railway → update `CORS_ORIGINS` to include your Vercel URL:
  ```
  CORS_ORIGINS=https://your-app.vercel.app
  ```
- Redeploy (Railway redeploys on env var change automatically)

---

## 5 — Verify

```bash
curl https://your-app.railway.app/api/health
# → {"status": "ok"}
```

Open `https://your-app.vercel.app` — the dashboard should connect and show live data.

---

## Local development (unchanged)

```bash
./start.sh        # starts backend on :8000, frontend on :5173
```

No env vars needed for local — SQLite and localhost defaults are used automatically.

---

## Environment variable reference

| Variable | Where | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Backend | SQLite (local) | PostgreSQL URL for production |
| `CORS_ORIGINS` | Backend | localhost | Comma-separated allowed frontend origins |
| `API_SECRET_KEY` | Backend | (empty) | If set, requires Bearer token on all API calls |
| `PAPER_MODE` | Backend | `true` | Safe mode — no real money traded |
| `EXCHANGE` | Backend | `bitso` | Which exchange to connect to |
| `VITE_API_BASE_URL` | Frontend | (uses proxy) | Full URL of backend `/api` |
| `VITE_WS_URL` | Frontend | `ws://localhost:8000/ws` | Full URL of backend WebSocket |
| `VITE_API_SECRET_KEY` | Frontend | (empty) | Must match backend `API_SECRET_KEY` |
