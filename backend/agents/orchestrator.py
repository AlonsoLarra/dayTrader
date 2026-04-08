import asyncio
import uuid
from datetime import datetime
from typing import Optional

import numpy as np
from sqlalchemy import select

from database import AsyncSessionLocal
from models import AgentState
from agents.agent import TradingAgent
from strategies.ma_crossover import MACrossoverStrategy
from strategies.rsi import RSIStrategy
from strategies.trend_rsi import TrendRSIStrategy
from strategies.adaptive import AdaptiveStrategy
from exchange.client import create_exchange, get_ohlcv
from risk.guardrails import RiskGuardrails
from config import settings

STRATEGY_MAP = {
    "ma_crossover": MACrossoverStrategy,
    "rsi": RSIStrategy,
    "trend_rsi": TrendRSIStrategy,
    "adaptive": AdaptiveStrategy,
}

ALL_PAIRS = ["BTC/MXN", "ETH/MXN", "SOL/MXN", "XRP/MXN", "AVAX/MXN", "LTC/MXN"]


def pick_auto_strategy_for_ohlcv(ohlcv: list) -> tuple:
    """Pick the more active auto-trade strategy profile for the current market tape."""
    trend_rsi_params = {
        "ema_period": 50,
        "rsi_period": 14,
        "rsi_buy": 48,
        "rsi_sell": 67,
        "volume_factor": 1.0,
        "profit_target_pct": 0.02,
        "max_hold_candles": 12,
    }
    adaptive_params = {
        "volume_factor": 1.0,
        "rsi_buy_low_vol": 42.0,
        "rsi_buy_normal": 47.0,
        "max_hold_candles": 16,
        "min_profit_for_macd_exit": 0.003,
    }
    rsi_params = {"period": 14, "oversold": 38, "overbought": 68}

    if len(ohlcv) < 20:
        return "trend_rsi", dict(trend_rsi_params)

    closes = np.array([c[4] for c in ohlcv], dtype=float)
    if len(closes) < 2:
        return "trend_rsi", dict(trend_rsi_params)

    previous = np.where(closes[:-1] == 0, 1.0, closes[:-1])
    returns = np.abs(np.diff(closes) / previous)
    volatility = float(np.std(returns)) * 100 if len(returns) else 0.0

    ema20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else float(np.mean(closes))
    ema50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else float(np.mean(closes))
    trend_strength = ((ema20 - ema50) / ema50 * 100) if ema50 else 0.0

    if volatility >= 5.0:
        return "rsi", dict(rsi_params)
    if volatility < 1.2 and abs(trend_strength) < 0.35:
        return "adaptive", dict(adaptive_params)
    return "trend_rsi", dict(trend_rsi_params)


def _score_pair(ohlcv: list) -> float:
    """
    Score a pair 0-100 for how attractive it is to trade right now.
    Higher = better opportunity.

    Scoring:
    - RSI distance from the nearest extreme (oversold/overbought) → 0-60 pts
      A coin at RSI 20 (deeply oversold) or RSI 80 (deeply overbought) scores highest.
    - Volatility (recent price movement) → 0-40 pts
      More movement = more opportunity to profit.
    """
    if len(ohlcv) < 16:
        return 0.0
    try:
        closes = np.array([c[4] for c in ohlcv], dtype=float)

        # RSI (14-period)
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_gain = float(np.mean(gains[:14]))
        avg_loss = float(np.mean(losses[:14]))
        for i in range(14, len(deltas)):
            avg_gain = (avg_gain * 13 + gains[i]) / 14
            avg_loss = (avg_loss * 13 + losses[i]) / 14
        rs = avg_gain / avg_loss if avg_loss != 0 else 100.0
        rsi = 100.0 - (100.0 / (1.0 + rs))

        # Distance from neutral (50) weighted toward extremes
        rsi_distance = abs(rsi - 50)  # 0-50 range
        rsi_score = min(rsi_distance / 50 * 60, 60)

        # Volatility over last 20 candles
        recent = closes[-20:]
        returns = np.abs(np.diff(recent) / recent[:-1])
        volatility = float(np.std(returns)) * 100
        vol_score = min(volatility / 3.0 * 40, 40)

        return round(rsi_score + vol_score, 2)
    except Exception:
        return 0.0


def evaluate_rotation_decision(
    current_symbol: str,
    current_score: float,
    best_symbol: str,
    best_score: float,
    has_position: bool,
    unrealized_pnl_pct: Optional[float] = None,
    aggressive: bool = False,
    min_score_delta: float = 1.0,
    cooldown_active: bool = False,
) -> tuple:
    """Decide whether a bot should rotate to a stronger market opportunity."""
    score_delta = float(best_score or 0.0) - float(current_score or 0.0)

    if cooldown_active:
        return "hold", "Rotation cooldown is still active after the last switch"
    if float(best_score or 0.0) <= 0.0:
        return "hold", "No strong alternative setup was found in the latest market scan"
    if best_symbol == current_symbol:
        return "hold", f"{current_symbol} remains the best-ranked setup right now"
    if score_delta < float(min_score_delta or 0.0):
        return "hold", f"Score gap is only {score_delta:.1f}; waiting for a clearer edge before rotating"

    if has_position and unrealized_pnl_pct is not None:
        if aggressive and unrealized_pnl_pct <= -3.0 and score_delta < float(min_score_delta or 0.0) * 1.5:
            return "hold", (
                f"Current trade is in a {unrealized_pnl_pct:.1f}% drawdown; "
                "waiting for a stronger edge before rotating"
            )
        if not aggressive and unrealized_pnl_pct < 0:
            return "hold", "Conservative rotation avoids switching while the current trade is underwater"

    return "rotate", f"Rotate from {current_symbol} to {best_symbol}: score edge +{score_delta:.1f} supports a stronger setup"


async def scan_best_opportunity(exclude_symbol: Optional[str] = None) -> tuple:
    """
    Scan all trading pairs and return the best opportunity right now.
    Returns (symbol, strategy_name, params, score).
    Falls back to BTC/MXN with MA Crossover if all scans fail.
    """
    exchange = create_exchange()
    pairs_to_scan = [p for p in ALL_PAIRS if p != exclude_symbol] + (
        [exclude_symbol] if exclude_symbol else []
    )

    async def _score_one(symbol: str):
        try:
            ohlcv = await get_ohlcv(exchange, symbol, "15m", 50)
            base_score = _score_pair(ohlcv)

            # Auto-trade now leans into a more active profile:
            # Trend RSI for most markets, RSI for violent swings, Adaptive only in calm tape.
            strategy_name, params = pick_auto_strategy_for_ohlcv(ohlcv)

            strategy_cls = STRATEGY_MAP.get(strategy_name, AdaptiveStrategy)
            strategy = strategy_cls(params)
            if getattr(strategy, "min_candles", 0) > len(ohlcv):
                result = None
            else:
                import inspect
                sig = inspect.signature(strategy.analyze)
                if "entry_price" in sig.parameters:
                    result = strategy.analyze(ohlcv, entry_price=None, candles_held=0)
                else:
                    result = strategy.analyze(ohlcv)

            signal_bonus = 0.0
            if result is not None:
                if result.signal.value == "buy":
                    signal_bonus += 18.0 + float(result.confidence or 0.0) * 22.0
                elif result.signal.value == "sell":
                    signal_bonus -= 8.0
                else:
                    signal_bonus += float(result.confidence or 0.0) * 4.0

                if result.indicators.get("in_uptrend"):
                    signal_bonus += 3.0
                if result.indicators.get("volume_ok"):
                    signal_bonus += 2.0

            score = round(min(100.0, max(0.0, base_score + signal_bonus)), 2)
            return symbol, strategy_name, params, score
        except Exception:
            return symbol, "ma_crossover", {}, 0.0

    results = await asyncio.gather(*[_score_one(sym) for sym in pairs_to_scan])

    # Sort by score descending, pick best
    results = sorted(results, key=lambda x: x[3], reverse=True)
    best = results[0] if results else ("BTC/MXN", "ma_crossover", {}, 0.0)
    return best  # (symbol, strategy_name, params, score)


class AgentOrchestrator:
    _instance: Optional["AgentOrchestrator"] = None

    def __new__(cls) -> "AgentOrchestrator":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._agents: dict[str, TradingAgent] = {}
            cls._instance._tasks: dict[str, asyncio.Task] = {}
            cls._instance._broadcaster = None
        return cls._instance

    def set_broadcaster(self, broadcaster) -> None:
        self._broadcaster = broadcaster
        for agent in self._agents.values():
            agent._broadcaster = broadcaster

    async def reload_from_db(self) -> None:
        """On startup, recreate agent instances in memory for all non-killed agents."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(AgentState).where(AgentState.status != "killed")
            )
            states = result.scalars().all()
            for state in states:
                strategy_cls = STRATEGY_MAP.get(state.strategy)
                if not strategy_cls:
                    continue
                strategy = strategy_cls({})
                exchange = create_exchange(budget=state.budget_allocated, symbol=state.symbol)
                guardrails = RiskGuardrails(
                    state.budget_allocated,
                    settings.STOP_LOSS_PCT,
                    settings.MAX_TRADES_PER_DAY,
                    settings.MAX_LOSSES_PER_DAY,
                    settings.MAX_DAILY_LOSS_PCT,
                )
                agent = TradingAgent(
                    state.agent_id,
                    strategy,
                    exchange,
                    guardrails,
                    AsyncSessionLocal,
                    symbol=state.symbol,
                    rotation_enabled=bool(getattr(state, "rotation_enabled", False)),
                    aggressive_rotation=bool(getattr(state, "aggressive_rotation", False)),
                    rotation_interval_minutes=int(getattr(state, "rotation_interval_minutes", 1) or 1),
                    min_rotation_score_delta=float(getattr(state, "min_rotation_score_delta", 1.0) or 1.0),
                )
                agent._broadcaster = self._broadcaster
                agent._last_market_review_at = getattr(state, "last_market_review_at", None)
                agent._last_rotation_at = getattr(state, "last_rotation_at", None)
                # Restore open position from DB
                if state.open_position_price and state.open_position_amount:
                    total_cost = float(state.budget_used or (state.open_position_amount * state.open_position_price))
                    agent.open_position = {
                        "side": state.open_position_side or "buy",
                        "price": state.open_position_price,
                        "amount": state.open_position_amount,
                        "symbol": state.symbol,
                        "total_cost": total_cost,
                    }
                    if hasattr(exchange, "restore_position"):
                        exchange.restore_position(
                            state.symbol,
                            state.open_position_amount,
                            state.open_position_price,
                            total_cost=total_cost,
                        )
                self._agents[state.agent_id] = agent

                # If it was mid-run when server died, mark it stopped
                if state.status == "running":
                    state.status = "stopped"
                    state.updated_at = datetime.utcnow()

            await session.commit()

    async def create_agent(
        self,
        strategy_name: str,
        params: dict,
        budget: float,
        symbol: str = None,
        rotation_enabled: bool = False,
        aggressive_rotation: bool = False,
        rotation_interval_minutes: int = 1,
        min_rotation_score_delta: float = 1.0,
    ) -> str:
        symbol = symbol or settings.TRADING_PAIR
        rotation_interval_minutes = max(1, int(rotation_interval_minutes or 1))
        min_rotation_score_delta = float(min_rotation_score_delta or 1.0)

        # Auto-select: scan all pairs and pick the best opportunity right now
        if strategy_name == "auto":
            rotation_enabled = True
            aggressive_rotation = True
            best_symbol, strategy_name, params, score = await scan_best_opportunity()
            symbol = best_symbol
        
        strategy_cls = STRATEGY_MAP.get(strategy_name)
        if not strategy_cls:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        agent_id = str(uuid.uuid4())[:8]
        strategy = strategy_cls(params)
        exchange = create_exchange(budget=budget, symbol=symbol)
        guardrails = RiskGuardrails(
            budget,
            settings.STOP_LOSS_PCT,
            settings.MAX_TRADES_PER_DAY,
            settings.MAX_LOSSES_PER_DAY,
            settings.MAX_DAILY_LOSS_PCT,
        )

        agent = TradingAgent(
            agent_id,
            strategy,
            exchange,
            guardrails,
            AsyncSessionLocal,
            symbol=symbol,
            rotation_enabled=rotation_enabled,
            aggressive_rotation=aggressive_rotation,
            rotation_interval_minutes=rotation_interval_minutes,
            min_rotation_score_delta=min_rotation_score_delta,
        )
        agent._broadcaster = self._broadcaster

        async with AsyncSessionLocal() as session:
            state = AgentState(
                agent_id=agent_id,
                strategy=strategy_name,
                status="stopped",
                budget_allocated=budget,
                budget_used=0.0,
                trades_today=0,
                losses_today=0,
                realized_pnl_today=0.0,
                rotation_enabled=rotation_enabled,
                aggressive_rotation=aggressive_rotation,
                rotation_interval_minutes=rotation_interval_minutes,
                min_rotation_score_delta=min_rotation_score_delta,
                symbol=symbol,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(state)
            await session.commit()

        self._agents[agent_id] = agent
        return agent_id, strategy_name

    async def start_agent(self, agent_id: str) -> None:
        agent = self._agents.get(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found in memory. It may need to be recreated.")

        existing_task = self._tasks.get(agent_id)
        if existing_task and not existing_task.done():
            return  # already running

        task = asyncio.create_task(agent.start())
        self._tasks[agent_id] = task
        agent._task = task

    async def stop_agent(self, agent_id: str) -> None:
        agent = self._agents.get(agent_id)
        if agent:
            await agent.stop()

    async def kill_agent(self, agent_id: str) -> None:
        agent = self._agents.get(agent_id)
        if agent:
            await agent.kill()

    async def kill_all(self) -> None:
        for agent_id in list(self._agents.keys()):
            await self.kill_agent(agent_id)

    def get_agents(self) -> list[str]:
        return list(self._agents.keys())

    def get_agent(self, agent_id: str) -> Optional[TradingAgent]:
        return self._agents.get(agent_id)


orchestrator = AgentOrchestrator()
