const PRODUCTION_BACKEND_ORIGIN = 'https://daytrader-production-7bc2.up.railway.app';

export function getApiBaseUrl() {
  return import.meta.env.VITE_API_BASE_URL || (import.meta.env.PROD ? `${PRODUCTION_BACKEND_ORIGIN}/api` : '/api');
}

export function getWsUrl() {
  return import.meta.env.VITE_WS_URL || (import.meta.env.PROD ? `wss://${PRODUCTION_BACKEND_ORIGIN.replace(/^https?:\/\//, '')}/ws` : 'ws://localhost:8000/ws');
}