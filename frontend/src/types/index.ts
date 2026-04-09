export interface Agent {
  agent_id: string;
  strategy: string;
  status: 'running' | 'stopped' | 'killed';
  symbol: string;
  quote_currency?: string;
  budget_allocated: number;
  budget_used: number;
  trades_today: number;
  losses_today: number;
  realized_pnl_today: number;
  realized_pnl_total?: number;
  rotation_enabled?: boolean;
  aggressive_rotation?: boolean;
  rotation_interval_minutes?: number;
  min_rotation_score_delta?: number;
  last_signal?: 'buy' | 'sell' | 'hold' | null;
  last_tick_at?: string | null;
  last_market_review_at?: string | null;
  last_rotation_at?: string | null;
  created_at?: string;
}

export interface Trade {
  id: number;
  agent_id: string;
  symbol: string;
  quote_currency?: string;
  side: 'buy' | 'sell';
  amount: number;
  price: number;
  timestamp: string;
  pnl: number | null;
  fee: number | null;
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
  total_fees: number;
  win_rate: number;
  winning_trades: number;
  total_allocated: number;
  total_deployed: number;
  total_agents: number;
  running_agents: number;
}

export interface Position {
  agent_id: string;
  symbol: string;
  strategy: string;
  side: string;
  amount: number;
  entry_price: number;
  current_price: number | null;
  unrealized_pnl: number | null;
  pnl_pct: number | null;
  proceeds_if_sold: number | null;
  cost_basis: number;
}

export interface WsMessage {
  type: 'trade' | 'log' | 'state_update' | 'price_update' | 'ping' | 'pong';
  payload?: unknown;
}

export interface PairAnalysis {
  symbol: string;
  score: number;
  rank_score?: number;
  expected_roi_pct?: number;
  reward_risk_ratio?: number;
  trend_strength_pct?: number;
  strategy: string;
  reason: string;
  action?: string;
  signal?: 'buy' | 'sell' | 'hold';
  confidence?: number;
  eligible?: boolean;
  rsi?: number;
  volatility?: number;
  ma_bullish?: boolean;
}

export interface DeployResult {
  total_budget: number;
  quote_currency?: string;
  pairs: { symbol: string; score: number; strategy: string; reason: string; budget_allocated: number }[];
  agent_ids: string[];
}
