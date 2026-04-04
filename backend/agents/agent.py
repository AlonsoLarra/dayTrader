import asyncio
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from models import Trade, AgentLog, AgentState
from strategies.base import BaseStrategy, Signal
from risk.guardrails import RiskGuardrails
from exchange.client import get_ohlcv, get_ticker, place_order
from config import settings


class TradingAgent:
    def __init__(
        self,
        agent_id: str,
        strategy: BaseStrategy,
        exchange,
        guardrails: RiskGuardrails,
        session_factory,
    ):
        self.agent_id = agent_id
        self.strategy = strategy
        self.exchange = exchange
        self.guardrails = guardrails
        self.session_factory = session_factory
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.open_position: Optional[dict] = None  # {side, price, amount}
        self._broadcaster = None  # set by orchestrator

    async def _log(
        self,
        session: AsyncSession,
        level: str,
        message: str,
        decision: str = None,
        reasoning: str = None,
    ):
        log = AgentLog(
            agent_id=self.agent_id,
            timestamp=datetime.utcnow(),
            level=level,
            message=message,
            decision=decision,
            reasoning=reasoning,
        )
        session.add(log)
        await session.commit()

        if self._broadcaster:
            await self._broadcaster.broadcast(
                {
                    "type": "log",
                    "payload": {
                        "agent_id": self.agent_id,
                        "level": level,
                        "message": message,
                        "decision": decision,
                        "reasoning": reasoning,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                }
            )

    async def _get_state(self, session: AsyncSession) -> Optional[AgentState]:
        result = await session.execute(select(AgentState).where(AgentState.agent_id == self.agent_id))
        return result.scalar_one_or_none()

    async def _update_state(self, session: AsyncSession, **kwargs):
        kwargs["updated_at"] = datetime.utcnow()
        await session.execute(
            update(AgentState).where(AgentState.agent_id == self.agent_id).values(**kwargs)
        )
        await session.commit()

        state = await self._get_state(session)
        if state and self._broadcaster:
            await self._broadcaster.broadcast(
                {
                    "type": "state_update",
                    "payload": {
                        "agent_id": self.agent_id,
                        "status": state.status,
                        "budget_used": state.budget_used,
                        "trades_today": state.trades_today,
                    },
                }
            )

    async def tick(self):
        async with self.session_factory() as session:
            try:
                state = await self._get_state(session)
                if not state or state.status in ("killed", "stopped"):
                    self._running = False
                    return

                # Check stop loss on open position
                if self.open_position:
                    ticker = await get_ticker(self.exchange, settings.TRADING_PAIR)
                    current_price = ticker.get("last", 0)
                    if current_price and self.guardrails.check_stop_loss(
                        self.open_position["price"], current_price, self.open_position["side"]
                    ):
                        close_side = "sell" if self.open_position["side"] == "buy" else "buy"
                        try:
                            await place_order(
                                self.exchange,
                                settings.TRADING_PAIR,
                                close_side,
                                self.open_position["amount"],
                            )
                            pnl = (current_price - self.open_position["price"]) * self.open_position["amount"]
                            if close_side == "buy":
                                pnl = -pnl

                            trade = Trade(
                                agent_id=self.agent_id,
                                symbol=settings.TRADING_PAIR,
                                side=close_side,
                                amount=self.open_position["amount"],
                                price=current_price,
                                timestamp=datetime.utcnow(),
                                pnl=pnl,
                                mode="paper" if settings.PAPER_MODE else "live",
                                strategy=self.strategy.name,
                            )
                            session.add(trade)
                            await session.commit()

                            await self._log(
                                session,
                                "warning",
                                f"Stop loss triggered at {current_price:.2f}",
                                decision="stop_loss",
                                reasoning=f"Loss exceeded {self.guardrails.stop_loss_pct * 100:.1f}%",
                            )
                            self.open_position = None
                        except Exception as e:
                            await self._log(session, "error", f"Stop loss order failed: {e}")

                can_trade, reason = self.guardrails.can_trade(state)
                if not can_trade:
                    await self._log(session, "info", f"Cannot trade: {reason}")
                    return

                ohlcv = await get_ohlcv(self.exchange, settings.TRADING_PAIR, "1h", 100)
                if not ohlcv:
                    await self._log(session, "warning", "Failed to fetch OHLCV data")
                    return

                result = self.strategy.analyze(ohlcv)

                await self._update_state(
                    session,
                    last_signal=result.signal.value,
                    last_tick_at=datetime.utcnow(),
                )

                await self._log(
                    session,
                    "info",
                    f"Strategy analysis: {result.signal.value} (confidence: {result.confidence:.2f})",
                    decision=result.signal.value,
                    reasoning=result.reasoning,
                )

                if result.signal == Signal.HOLD:
                    return

                ticker = await get_ticker(self.exchange, settings.TRADING_PAIR)
                current_price = ticker.get("last", 0)
                if not current_price:
                    await self._log(session, "error", "Could not get current price")
                    return

                available_budget = state.budget_allocated - state.budget_used
                amount = self.guardrails.calculate_position_size(available_budget, current_price)

                if amount <= 0:
                    await self._log(session, "warning", "Calculated position size is 0")
                    return

                # Don't trade same direction as open position
                if self.open_position and self.open_position["side"] == result.signal.value:
                    await self._log(session, "info", f"Already have open {result.signal.value} position")
                    return

                try:
                    order = await place_order(
                        self.exchange,
                        settings.TRADING_PAIR,
                        result.signal.value,
                        amount,
                    )

                    fill_price = order.get("price", current_price)
                    cost = amount * fill_price

                    pnl = None
                    if self.open_position and result.signal.value != self.open_position["side"]:
                        if result.signal == Signal.SELL:
                            pnl = (fill_price - self.open_position["price"]) * amount
                        else:
                            pnl = (self.open_position["price"] - fill_price) * amount
                        self.open_position = None
                    else:
                        self.open_position = {
                            "side": result.signal.value,
                            "price": fill_price,
                            "amount": amount,
                        }

                    trade = Trade(
                        agent_id=self.agent_id,
                        symbol=settings.TRADING_PAIR,
                        side=result.signal.value,
                        amount=amount,
                        price=fill_price,
                        timestamp=datetime.utcnow(),
                        pnl=pnl,
                        mode="paper" if settings.PAPER_MODE else "live",
                        strategy=self.strategy.name,
                    )
                    session.add(trade)

                    await self._update_state(
                        session,
                        budget_used=state.budget_used + cost,
                        trades_today=state.trades_today + 1,
                    )

                    if self._broadcaster:
                        await self._broadcaster.broadcast(
                            {
                                "type": "trade",
                                "payload": {
                                    "agent_id": self.agent_id,
                                    "symbol": settings.TRADING_PAIR,
                                    "side": result.signal.value,
                                    "amount": amount,
                                    "price": fill_price,
                                    "pnl": pnl,
                                    "timestamp": datetime.utcnow().isoformat(),
                                },
                            }
                        )

                    await self._log(
                        session,
                        "trade",
                        f"Executed {result.signal.value} {amount:.8f} {settings.TRADING_PAIR} @ {fill_price:.2f}",
                        decision=result.signal.value,
                        reasoning=result.reasoning,
                    )

                except Exception as e:
                    await self._log(session, "error", f"Order failed: {e}")

            except Exception as e:
                try:
                    await self._log(session, "error", f"Tick error: {e}")
                except Exception:
                    pass

    async def start(self):
        self._running = True
        async with self.session_factory() as session:
            await self._update_state(session, status="running")

        while self._running:
            await self.tick()
            await asyncio.sleep(30)  # tick every 30 seconds

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        async with self.session_factory() as session:
            await self._update_state(session, status="stopped")

    async def kill(self):
        self._running = False
        if self._task:
            self._task.cancel()
        self.open_position = None
        async with self.session_factory() as session:
            await self._update_state(session, status="killed")
