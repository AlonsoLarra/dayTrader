import axios from 'axios';
import type { Agent, Trade, AgentLog, BacktestResult, TradeSummary, PairAnalysis, DeployResult, Position } from '../types';

// In production, set VITE_API_BASE_URL = https://your-backend.railway.app/api
// Locally it falls back to the Vite proxy at /api
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  headers: { 'Content-Type': 'application/json' },
  timeout: 120000,
});

// Attach JWT token from localStorage on every request
api.interceptors.request.use(config => {
  const token = localStorage.getItem('daytrader_token');
  if (token) {
    config.headers = config.headers ?? {};
    config.headers['Authorization'] = `Bearer ${token}`;
  }
  return config;
});

// On 401, clear token and signal logout via custom event (no reload — that causes an infinite loop)
api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('daytrader_token');
      window.dispatchEvent(new Event('daytrader:logout'));
    }
    return Promise.reject(err);
  }
);

export const getAgents = () => api.get<Agent[]>('/agents').then(r => r.data);
export const getAgent = (id: string) => api.get<Agent>(`/agents/${id}`).then(r => r.data);
export const createAgent = (data: {
  strategy: string;
  params: Record<string, number>;
  budget: number;
  symbol: string;
  quote_currency?: string;
}) => api.post<{ agent_id: string }>('/agents', data).then(r => r.data);
export const getMarkets = (quote = 'MXN') =>
  api.get<{ symbols: string[] }>('/agents/markets', { params: { quote } }).then(r => r.data);
export const startAgent = (id: string) => api.post(`/agents/${id}/start`).then(r => r.data);
export const stopAgent = (id: string) => api.post(`/agents/${id}/stop`).then(r => r.data);
export const killAgent = (id: string) => api.post(`/agents/${id}/kill`).then(r => r.data);
export const killAllAgents = () => api.post('/agents/kill-all').then(r => r.data);
export const deleteAgent = (id: string) => api.delete(`/agents/${id}`).then(r => r.data);
export const getAgentLogs = (id: string, skip = 0, limit = 50) =>
  api.get<AgentLog[]>(`/agents/${id}/logs`, { params: { skip, limit } }).then(r => r.data);

export const getTrades = (params?: {
  agent_id?: string;
  strategy?: string;
  skip?: number;
  limit?: number;
}) => api.get<Trade[]>('/trades', { params }).then(r => r.data);
export const getTradeSummary = () => api.get<TradeSummary>('/trades/summary').then(r => r.data);

export interface PriceTick {
  last: number;
  change_pct: number;
  high: number;
  low: number;
}

export interface PricesResponse {
  prices: Record<string, PriceTick>;
  timestamp: string;
}

export const getPrices = () => api.get<PricesResponse>('/prices').then(r => r.data);

export interface OhlcvResponse {
  symbol: string;
  timeframe: string;
  data: Array<[number, number, number, number, number, number]>;
}

export const getPriceOhlcv = (symbol: string, timeframe = '1h', limit = 50) =>
  api.get<OhlcvResponse>(`/prices/${symbol.replace('/', '-')}/ohlcv`, { params: { timeframe, limit } }).then(r => r.data);

export const getWallet = () => api.get<{ balances: Record<string, { free: number; used: number; total: number }>; paper_mode: boolean }>('/settings/wallet').then(r => r.data);
export const getMode = () => api.get<{ paper_mode: boolean; exchange: string }>('/settings/mode').then(r => r.data);
export const setMode = (paper_mode: boolean) => api.post('/settings/mode', { paper_mode }).then(r => r.data);

export const runBacktest = (data: {
  strategy: string;
  params: Record<string, number>;
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
}) => api.post<BacktestResult>('/backtest', data).then(r => r.data);

export const analyzeMarket = (max_pairs = 10, quote_currency = 'MXN') =>
  api.post<{ pairs: PairAnalysis[]; quote_currency?: string; total_markets?: number }>('/portfolio/analyze', null, {
    params: { max_pairs, quote_currency },
  }).then(r => r.data);

export const deployPortfolio = (data: {
  budget: number;
  max_agents: number;
  min_score: number;
  quote_currency?: string;
  rotation_enabled?: boolean;
  rotation_interval_minutes?: number;
  aggressive_rotation?: boolean;
  min_rotation_score_delta?: number;
}) => api.post<DeployResult>('/portfolio/deploy', data).then(r => r.data);

export const getPositions = () =>
  api.get<{ positions: Position[] }>('/agents/positions').then(r => r.data);

export const forceSell = (agentId: string) =>
  api.post<{ symbol: string; amount: number; price: number; pnl: number; proceeds: number }>(`/agents/${agentId}/force-sell`).then(r => r.data);

export interface PaperWalletSnapshot {
  starting_balance: number;
  deployed: number;
  in_market: number;
  available: number;
}

export interface PaperWalletData extends PaperWalletSnapshot {
  currency?: string;
  balances?: Record<string, PaperWalletSnapshot>;
}

export const getPaperWallet = (currency = 'MXN') =>
  api.get<PaperWalletData>('/settings/paper-wallet', { params: { currency } }).then(r => r.data);

export const setPaperWallet = (starting_balance: number, currency = 'MXN') =>
  api.post<{ starting_balance: number; currency?: string }>('/settings/paper-wallet', {
    starting_balance,
    currency,
  }).then(r => r.data);

export interface BotReasoning {
  agent_id: string;
  symbol: string;
  strategy: string;
  current_price: number;
  has_position: boolean;
  entry_price: number | null;
  unrealized_pnl: number | null;
  stop_loss_price: number | null;
  stop_loss_pct: number;
  reasoning: {
    action: string;
    trigger: string;
    urgency: string;
    rsi?: number;
    oversold?: number;
    overbought?: number;
    distance_to_buy?: number;
    distance_to_sell?: number;
    fast_ma?: number;
    slow_ma?: number;
    spread_pct?: number;
    bullish?: boolean;
  };
  error?: string;
}

export interface PairScan {
  symbol: string;
  score: number;
  rsi: number;
  price: number;
  strategy: string;
  action: string;
  reason: string;
  confidence?: number;
  tracked_by?: string[];
  tracked_count?: number;
}

export const getStrategyReasoning = () =>
  api.get<{ bots: BotReasoning[] }>('/strategy/reasoning').then(r => r.data);

export const getMarketScan = () =>
  api.get<{ pairs: PairScan[] }>('/strategy/market-scan').then(r => r.data);
