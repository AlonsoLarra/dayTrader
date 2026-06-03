from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    quote_currency: Mapped[str] = mapped_column(String, nullable=False, default="MXN")
    side: Mapped[str] = mapped_column(String, nullable=False)  # buy / sell
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fee: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mode: Mapped[str] = mapped_column(String, nullable=False, default="paper")  # paper / live
    strategy: Mapped[str] = mapped_column(String, nullable=False)


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    level: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    decision: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reasoning: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class AutoWatcherLog(Base):
    __tablename__ = "auto_watcher_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    # Values: "deployed" | "skipped_bots_running" | "no_eligible_pairs"
    #         | "budget_insufficient" | "no_symbols" | "error"
    pairs_evaluated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    eligible_pairs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    agents_deployed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class AgentState(Base):
    __tablename__ = "agent_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    strategy: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="stopped")  # running / stopped / killed
    budget_allocated: Mapped[float] = mapped_column(Float, nullable=False)
    budget_used: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    trades_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    losses_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    realized_pnl_today: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rotation_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    aggressive_rotation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rotation_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    min_rotation_score_delta: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    last_signal: Mapped[Optional[str]] = mapped_column(String, nullable=True)   # hold / buy / sell
    last_tick_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_market_review_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_rotation_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False, default="BTC/MXN")
    quote_currency: Mapped[str] = mapped_column(String, nullable=False, default="MXN")
    open_position_side: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    open_position_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    open_position_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    position_size_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class PaperWallet(Base):
    __tablename__ = "paper_wallet"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    starting_balance: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    btc_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.01)
    usd_balance: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    usdt_balance: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    realized_pnl_banked_mxn: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    realized_pnl_banked_btc: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    realized_pnl_banked_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    realized_pnl_banked_usdt: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class RiskConfig(Base):
    __tablename__ = "risk_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    max_losses_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    max_daily_loss_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.05)
    max_trades_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class TrainingRun(Base):
    __tablename__ = "training_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    timeframe: Mapped[str] = mapped_column(String, nullable=False)
    start_date: Mapped[str] = mapped_column(String, nullable=False)
    end_date: Mapped[str] = mapped_column(String, nullable=False)
    initial_capital: Mapped[float] = mapped_column(Float, nullable=False)
    max_trials: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    completed_trials: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    strategy_candidates_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    goal_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    best_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    best_strategy: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    best_params_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    best_metrics_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class TrainingTrial(Base):
    __tablename__ = "training_trials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    trial_index: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy: Mapped[str] = mapped_column(String, nullable=False)
    params_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    objective_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metrics_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
