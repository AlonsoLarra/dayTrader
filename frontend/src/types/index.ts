export interface Agent {
  agent_id: string;
  strategy: string;
  status: 'running' | 'stopped' | 'killed';
  budget_allocated: number;
  budget_used: number;
  trades_today: number;
  last_signal?: 'buy' | 'sell' | 'hold' | null;
  last_tick_at?: string | null;
  created_at?: string;
}

export interface Trade {
  id: number;
  agent_id: string;
  symbol: string;
  side: 'buy' | 'sell';
  amount: number;
  price: number;
  timestamp: string;
  pnl: number | null;
  mode: 'paper' | 'live';
  strategy: string;
}

export interface AgentLog {
  id: number;
  agent_id: string;
  timestamp: string;
  level: 'info' | 'warning' | 'error' | 'trade';
  message: string;
  decision: string | null;
  reasoning: string | null;
}

export interface BacktestResult {
  total_return_pct: number;
  win_rate: number;
  total_trades: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  equity_curve: [number, number][];
  trades: { side: string; price: number; amount: number; timestamp: number; pnl: number | null }[];
  error?: string;
}

export interface TradeSummary {
  total_trades: number;
  total_pnl: number;
  win_rate: number;
  winning_trades: number;
}

export interface WsMessage {
  type: 'trade' | 'log' | 'state_update' | 'price_update' | 'ping' | 'pong';
  payload?: unknown;
}
