import asyncio
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from database import AsyncSessionLocal
from models import AgentState
from agents.agent import TradingAgent
from strategies.ma_crossover import MACrossoverStrategy
from strategies.rsi import RSIStrategy
from exchange.client import create_exchange, get_ohlcv
from risk.guardrails import RiskGuardrails
from config import settings

STRATEGY_MAP = {
    "ma_crossover": MACrossoverStrategy,
    "rsi": RSIStrategy,
}


async def _pick_best_strategy(symbol: str) -> tuple:
    """Auto-select strategy based on current market volatility.
    High volatility (large price swings) → RSI catches extremes.
    Trending market (consistent direction) → MA Crossover follows trend.
    Returns (strategy_name, params).
    """
    try:
        exchange = create_exchange()
        ohlcv = await get_ohlcv(exchange, symbol, "1h", 50)
        if len(ohlcv) < 20:
            return "ma_crossover", {}

        import numpy as np
        closes = [c[4] for c in ohlcv]
        returns = [abs(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
        volatility = float(np.std(returns)) * 100  # % volatility

        # High volatility → RSI (catches overbought/oversold extremes)
        # Low volatility / trending → MA Crossover
        if volatility > 2.0:
            return "rsi", {"period": 14, "oversold": 35, "overbought": 65}
        else:
            return "ma_crossover", {"fast_period": 9, "slow_period": 21}
    except Exception:
        return "ma_crossover", {}


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
                exchange = create_exchange(budget=state.budget_allocated)
                guardrails = RiskGuardrails(
                    state.budget_allocated, settings.STOP_LOSS_PCT, settings.MAX_TRADES_PER_DAY
                )
                agent = TradingAgent(state.agent_id, strategy, exchange, guardrails, AsyncSessionLocal, symbol=state.symbol)
                agent._broadcaster = self._broadcaster
                # Restore open position from DB
                if state.open_position_price and state.open_position_amount:
                    agent.open_position = {
                        "side": state.open_position_side or "buy",
                        "price": state.open_position_price,
                        "amount": state.open_position_amount,
                        "symbol": state.symbol,
                    }
                self._agents[state.agent_id] = agent

                # If it was mid-run when server died, mark it stopped
                if state.status == "running":
                    state.status = "stopped"
                    state.updated_at = datetime.utcnow()

            await session.commit()

    async def create_agent(self, strategy_name: str, params: dict, budget: float, symbol: str = None) -> str:
        symbol = symbol or settings.TRADING_PAIR

        # Auto-select strategy based on market conditions
        if strategy_name == "auto":
            strategy_name, params = await _pick_best_strategy(symbol)

        strategy_cls = STRATEGY_MAP.get(strategy_name)
        if not strategy_cls:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        agent_id = str(uuid.uuid4())[:8]
        strategy = strategy_cls(params)
        exchange = create_exchange(budget=budget)  # seed paper exchange with agent's budget
        guardrails = RiskGuardrails(budget, settings.STOP_LOSS_PCT, settings.MAX_TRADES_PER_DAY)

        agent = TradingAgent(agent_id, strategy, exchange, guardrails, AsyncSessionLocal, symbol=symbol)
        agent._broadcaster = self._broadcaster

        async with AsyncSessionLocal() as session:
            state = AgentState(
                agent_id=agent_id,
                strategy=strategy_name,
                status="stopped",
                budget_allocated=budget,
                budget_used=0.0,
                trades_today=0,
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
