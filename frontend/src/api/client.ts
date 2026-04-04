import axios from 'axios';
import type { Agent, Trade, AgentLog, BacktestResult, TradeSummary } from '../types';

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

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

export const runBacktest = (data: {
  strategy: string;
  params: Record<string, number>;
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
}) => api.post<BacktestResult>('/backtest', data).then(r => r.data);
