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
        symbol: str = "BTC/MXN",
    ):
        self.agent_id = agent_id
        self.strategy = strategy
        self.exchange = exchange
        self.guardrails = guardrails
        self.session_factory = session_factory
        self.symbol = symbol
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

                # Daily reset: if last tick was on a different UTC date, reset trades_today
                now_date = datetime.utcnow().date()
                if state.last_tick_at and state.last_tick_at.date() < now_date:
                    await self._update_state(session, trades_today=0)
                    state = await self._get_state(session)

                # Check stop loss on open position
                if self.open_position:
                    ticker = await get_ticker(self.exchange, self.symbol)
                    current_price = ticker.get("last", 0)
                    if current_price and self.guardrails.check_stop_loss(
                        self.open_position["price"], current_price, self.open_position["side"]
                    ):
                        close_side = "sell" if self.open_position["side"] == "buy" else "buy"
                        try:
                            sl_order = await place_order(
                                self.exchange,
                                self.symbol,
                                close_side,
                                self.open_position["amount"],
                            )
                            sl_fill = sl_order.get("price", current_price)
                            sl_fee = sl_order.get("fee", {}).get("cost", 0.0)
                            pnl = (sl_fill - self.open_position["price"]) * self.open_position["amount"] - sl_fee
                            if close_side == "buy":
                                pnl = -pnl

                            buy_cost = self.open_position.get("total_cost", self.open_position["amount"] * self.open_position["price"])

                            trade = Trade(
                                agent_id=self.agent_id,
                                symbol=self.symbol,
                                side=close_side,
                                amount=self.open_position["amount"],
                                price=sl_fill,
                                timestamp=datetime.utcnow(),
                                pnl=pnl,
                                fee=sl_fee,
                                mode="paper" if settings.PAPER_MODE else "live",
                                strategy=self.strategy.name,
                            )
                            session.add(trade)
                            # Update DB first, then clear in-memory — keeps them in sync if DB update fails
                            await self._update_state(
                                session,
                                budget_used=max(0, state.budget_used - buy_cost),
                                trades_today=state.trades_today + 1,
                                open_position_side=None,
                                open_position_price=None,
                                open_position_amount=None,
                            )
                            self.open_position = None

                            await self._log(
                                session,
                                "warning",
                                f"Stop loss triggered at {current_price:.2f}",
                                decision="stop_loss",
                                reasoning=f"Loss exceeded {self.guardrails.stop_loss_pct * 100:.1f}%",
                            )
                        except Exception as e:
                            await self._log(session, "error", f"Stop loss order failed: {e}")

                can_trade, reason = self.guardrails.can_trade(state)
                if not can_trade:
                    await self._log(session, "info", f"Cannot trade: {reason}")
                    return

                ohlcv = await get_ohlcv(self.exchange, self.symbol, "15m", 100)
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

                ticker = await get_ticker(self.exchange, self.symbol)
                current_price = ticker.get("last", 0)
                if not current_price:
                    await self._log(session, "error", "Could not get current price")
                    return

                # Long-only spot trading:
                # BUY only if we have no open position
                # SELL only if we have an open long position to close
                if result.signal == Signal.BUY and self.open_position:
                    await self._log(session, "info", "Already holding a long position, skipping BUY")
                    return

                if result.signal == Signal.SELL and not self.open_position:
                    await self._log(session, "info", "No open position to sell")
                    return

                available_budget = state.budget_allocated - state.budget_used

                if result.signal == Signal.BUY:
                    amount = self.guardrails.calculate_position_size(available_budget, current_price, self.symbol)
                    if amount <= 0:
                        await self._log(session, "info", f"Insufficient budget for minimum order size on {self.symbol}")
                        return
                else:
                    # Selling: use the exact amount we hold
                    amount = self.open_position["amount"]

                try:
                    order = await place_order(
                        self.exchange,
                        self.symbol,
                        result.signal.value,
                        amount,
                    )

                    fill_price = order.get("price", current_price)
                    fee = order.get("fee", {}).get("cost", 0.0)

                    pnl = None
                    if result.signal == Signal.SELL and self.open_position:
                        # P&L = proceeds - fee - original cost (including buy fee)
                        sell_fee = order.get("fee", {}).get("cost", 0.0)
                        pnl = (fill_price - self.open_position["price"]) * amount - sell_fee
                        # Return original buy cost to budget (the amount we locked up)
                        buy_cost = self.open_position.get("total_cost", self.open_position["amount"] * self.open_position["price"])
                        # Update DB first — if this fails, in-memory position is preserved (consistent)
                        await self._update_state(
                            session,
                            budget_used=max(0, state.budget_used - buy_cost),
                            trades_today=state.trades_today + 1,
                            open_position_side=None,
                            open_position_price=None,
                            open_position_amount=None,
                        )
                        self.open_position = None
                    else:
                        # Opening long position — update DB first, then set in-memory
                        # If DB update fails the exception propagates and in-memory is NOT set
                        cost = amount * fill_price + fee  # include fee in total cost
                        await self._update_state(
                            session,
                            budget_used=state.budget_used + cost,
                            trades_today=state.trades_today + 1,
                            open_position_side="buy",
                            open_position_price=fill_price,
                            open_position_amount=amount,
                        )
                        self.open_position = {
                            "side": "buy",
                            "price": fill_price,
                            "amount": amount,
                            "symbol": self.symbol,
                            "total_cost": cost,
                        }

                    if self._broadcaster:
                        await self._broadcaster.broadcast(
                            {
                                "type": "trade",
                                "payload": {
                                    "agent_id": self.agent_id,
                                    "symbol": self.symbol,
                                    "side": result.signal.value,
                                    "amount": amount,
                                    "price": fill_price,
                                    "pnl": pnl,
                                    "fee": fee,
                                    "timestamp": datetime.utcnow().isoformat(),
                                },
                            }
                        )

                    # Persist trade record
                    trade = Trade(
                        agent_id=self.agent_id,
                        symbol=self.symbol,
                        side=result.signal.value,
                        amount=amount,
                        price=fill_price,
                        timestamp=datetime.utcnow(),
                        pnl=pnl,
                        fee=fee,
                        mode="paper" if settings.PAPER_MODE else "live",
                        strategy=self.strategy.name,
                    )
                    session.add(trade)
                    await session.commit()

                    await self._log(
                        session,
                        "trade",
                        f"Executed {result.signal.value} {amount:.8f} {self.symbol} @ {fill_price:.2f} | fee: ${fee:.2f} MXN",
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

    async def force_sell(self) -> dict:
        """Manually close the open position at market price."""
        if not self.open_position:
            raise ValueError("No open position to sell")
        async with self.session_factory() as session:
            state = await self._get_state(session)
            ticker = await get_ticker(self.exchange, self.symbol)
            current_price = ticker.get("last", 0)
            if not current_price:
                raise ValueError("Could not fetch current price")
            amount = self.open_position["amount"]
            order = await place_order(self.exchange, self.symbol, "sell", amount)
            fill_price = order.get("price", current_price)
            fee = order.get("fee", {}).get("cost", 0.0)
            pnl = (fill_price - self.open_position["price"]) * amount - fee
            buy_cost = self.open_position.get("total_cost", self.open_position["amount"] * self.open_position["price"])
            trade = Trade(
                agent_id=self.agent_id,
                symbol=self.symbol,
                side="sell",
                amount=amount,
                price=fill_price,
                timestamp=datetime.utcnow(),
                pnl=pnl,
                fee=fee,
                mode="paper" if settings.PAPER_MODE else "live",
                strategy=self.strategy.name,
            )
            session.add(trade)
            # Update DB first, then clear in-memory
            await self._update_state(
                session,
                budget_used=max(0, (state.budget_used if state else 0) - buy_cost),
                trades_today=(state.trades_today + 1) if state else 1,
                open_position_side=None,
                open_position_price=None,
                open_position_amount=None,
            )
            self.open_position = None
            await self._log(
                session, "trade",
                f"Force-sold {amount:.8f} {self.symbol} @ {fill_price:.2f} | P&L: {pnl:+.2f} MXN",
                decision="force_sell", reasoning="Manual close by user",
            )
            result = {
                "symbol": self.symbol,
                "amount": amount,
                "price": fill_price,
                "pnl": pnl,
                "proceeds": amount * fill_price,
            }
            if self._broadcaster:
                await self._broadcaster.broadcast({"type": "trade", "payload": {**result, "agent_id": self.agent_id, "side": "sell", "timestamp": datetime.utcnow().isoformat()}})
            return result

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
        # Auto-close any open position before killing
        if self.open_position:
            try:
                await self.force_sell()
            except Exception:
                pass  # Best effort — still kill even if sell fails
        async with self.session_factory() as session:
            await self._update_state(session, status="killed")
