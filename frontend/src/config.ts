const PRODUCTION_BACKEND_ORIGIN = 'https://daytrader-production-7bc2.up.railway.app';

export function getApiBaseUrl() {
  if (import.meta.env.PROD) {
    return `${PRODUCTION_BACKEND_ORIGIN}/api`;
  }
  return import.meta.env.VITE_API_BASE_URL || '/api';
}

export function getWsUrl() {
  if (import.meta.env.PROD) {
    return `wss://${PRODUCTION_BACKEND_ORIGIN.replace(/^https?:\/\//, '')}/ws`;
  }
  return import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws';
}