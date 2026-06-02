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

export interface AutoWatcherLog {
  id: number;
  timestamp: string;
  action:
    | 'deployed'
    | 'skipped_bots_running'
    | 'no_eligible_pairs'
    | 'budget_insufficient'
    | 'no_symbols'
    | 'error';
  pairs_evaluated: number;
  eligible_pairs: number;
  agents_deployed: number;
  details: Record<string, unknown> | null;
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
  type:
    | 'trade'
    | 'log'
    | 'state_update'
    | 'price_update'
    | 'training_update'
    | 'training_run_completed'
    | 'training_run_failed'
    | 'ping'
    | 'pong';
  payload?: unknown;
}

export interface TrainingGoalRequest {
  target_return_pct: number;
  min_win_rate: number;
  max_drawdown_pct: number;
  min_trades: number;
}

export interface TrainingStartRequest {
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  max_trials: number;
  strategy_candidates: string[];
  goal: TrainingGoalRequest;
}

export interface TrainingRunSummary {
  run_id: string;
  status: string;
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  max_trials: number;
  completed_trials: number;
  best_score: number | null;
  best_strategy: string | null;
  best_goal_met: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  finished_at?: string | null;
}

export interface TrainingTrialResult {
  id: number;
  trial_index: number;
  strategy: string;
  params: Record<string, unknown>;
  status: string;
  objective_score: number | null;
  metrics: Record<string, unknown>;
  error_message?: string | null;
  created_at?: string | null;
  finished_at?: string | null;
}

export interface TrainingRunDetail {
  run_id: string;
  status: string;
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  max_trials: number;
  completed_trials: number;
  strategy_candidates: string[];
  goal: TrainingGoalRequest;
  best: {
    strategy: string | null;
    score: number | null;
    params: Record<string, unknown>;
    metrics: Record<string, unknown>;
    goal_met: boolean;
  };
  error_message?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  updated_at?: string | null;
  trials: TrainingTrialResult[];
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
