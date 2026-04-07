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
    open_position_side: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    open_position_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    open_position_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class PaperWallet(Base):
    __tablename__ = "paper_wallet"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    starting_balance: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
