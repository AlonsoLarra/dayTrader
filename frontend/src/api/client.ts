import axios from 'axios';
import type { Agent, Trade, AgentLog, BacktestResult, TradeSummary, PairAnalysis, DeployResult, Position } from '../types';

// In production, set VITE_API_BASE_URL = https://your-backend.railway.app/api
// Locally it falls back to the Vite proxy at /api
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  headers: { 'Content-Type': 'application/json' },
});

// If API_SECRET_KEY is configured in production, add Bearer token to all requests
const apiSecret = import.meta.env.VITE_API_SECRET_KEY;
if (apiSecret) {
  api.defaults.headers.common['Authorization'] = `Bearer ${apiSecret}`;
}

export const getAgents = () => api.get<Agent[]>('/agents').then(r => r.data);
export const getAgent = (id: string) => api.get<Agent>(`/agents/${id}`).then(r => r.data);
export const createAgent = (data: { strategy: string; params: Record<string, number>; budget: number; symbol: string }) =>
  api.post<{ agent_id: string }>('/agents', data).then(r => r.data);
export const getMarkets = () => api.get<{ symbols: string[] }>('/agents/markets').then(r => r.data);
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

export const analyzeMarket = (max_pairs = 10) =>
  api.post<{ pairs: PairAnalysis[] }>('/portfolio/analyze', null, { params: { max_pairs } }).then(r => r.data);

export const deployPortfolio = (data: { budget: number; max_agents: number; min_score: number }) =>
  api.post<DeployResult>('/portfolio/deploy', data).then(r => r.data);

export const getPositions = () =>
  api.get<{ positions: Position[] }>('/agents/positions').then(r => r.data);

export const forceSell = (agentId: string) =>
  api.post<{ symbol: string; amount: number; price: number; pnl: number; proceeds: number }>(`/agents/${agentId}/force-sell`).then(r => r.data);

export interface PaperWalletData {
  starting_balance: number;
  deployed: number;
  in_market: number;
  available: number;
}

export const getPaperWallet = () =>
  api.get<PaperWalletData>('/settings/paper-wallet').then(r => r.data);

export const setPaperWallet = (starting_balance: number) =>
  api.post<{ starting_balance: number }>('/settings/paper-wallet', { starting_balance }).then(r => r.data);

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
}

export const getStrategyReasoning = () =>
  api.get<{ bots: BotReasoning[] }>('/strategy/reasoning').then(r => r.data);

export const getMarketScan = () =>
  api.get<{ pairs: PairScan[] }>('/strategy/market-scan').then(r => r.data);
