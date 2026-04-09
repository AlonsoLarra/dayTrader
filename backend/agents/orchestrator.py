import asyncio
import uuid
from datetime import datetime
from typing import Optional

import numpy as np
from sqlalchemy import func, select

from database import AsyncSessionLocal
from models import AgentState, PaperWallet, Trade
from agents.agent import TradingAgent
from strategies.ma_crossover import MACrossoverStrategy
from strategies.rsi import RSIStrategy
from strategies.trend_rsi import TrendRSIStrategy
from strategies.adaptive import AdaptiveStrategy
from exchange.client import create_exchange, get_available_symbols, get_ohlcv
from risk.guardrails import RiskGuardrails
from config import settings

STRATEGY_MAP = {
    "ma_crossover": MACrossoverStrategy,
    "rsi": RSIStrategy,
    "trend_rsi": TrendRSIStrategy,
    "adaptive": AdaptiveStrategy,
}

ALL_PAIRS = ["BTC/MXN", "ETH/MXN", "SOL/MXN", "XRP/MXN", "AVAX/MXN", "LTC/MXN"]
AUTO_MIN_BUY_CONFIDENCE = 0.15
SUPPORTED_PAPER_QUOTES = ("MXN", "BTC", "USD", "USDT")


def _normalize_quote_currency(value: Optional[str] = "MXN") -> str:
    normalized = (value or "MXN").upper()
    return normalized if normalized in SUPPORTED_PAPER_QUOTES else "MXN"


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


def _normalize_market_action(signal_value: str) -> str:
    normalized = (signal_value or "").lower()
    if normalized == "buy":
        return "BUY SIGNAL"
    if normalized == "sell":
        return "SELL SIGNAL"
    return "WAITING"


def _estimate_long_upside_metrics(ohlcv: list, indicators: Optional[dict] = None, confidence: float = 0.0) -> dict:
    """Estimate whether a long setup has enough upside and reward/risk to justify deployment."""
    if len(ohlcv) < 20:
        return {
            "expected_roi_pct": 0.0,
            "reward_risk_ratio": 0.0,
            "trend_strength_pct": 0.0,
            "atr_pct": 0.0,
            "upside_room_pct": 0.0,
        }

    closes = np.array([c[4] for c in ohlcv], dtype=float)
    highs = np.array([c[2] for c in ohlcv], dtype=float)
    lows = np.array([c[3] for c in ohlcv], dtype=float)
    current_price = float(closes[-1] or 0.0)
    if current_price <= 0:
        return {
            "expected_roi_pct": 0.0,
            "reward_risk_ratio": 0.0,
            "trend_strength_pct": 0.0,
            "atr_pct": 0.0,
            "upside_room_pct": 0.0,
        }

    ema20 = float(np.mean(closes[-20:]))
    ema50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else ema20
    trend_strength_pct = ((ema20 - ema50) / ema50 * 100.0) if ema50 else 0.0
    short_momentum_pct = ((current_price - float(closes[-6])) / float(closes[-6]) * 100.0) if len(closes) >= 6 and closes[-6] else 0.0
    recent_high = float(np.max(highs[-20:]))
    upside_room_pct = max(0.0, ((recent_high - current_price) / current_price) * 100.0)
    atr_pct = max(0.0, float(np.mean(highs[-14:] - lows[-14:])) / current_price * 100.0) if len(highs) >= 14 else 0.0

    indicator_map = indicators or {}
    price_vs_ema = float(indicator_map.get("price_vs_ema", 0.0) or 0.0)
    volume_ratio = float(indicator_map.get("volume_ratio", 1.0) or 1.0)

    if price_vs_ema < -2.5 or price_vs_ema > 4.0:
        pullback_quality = 0.65
    elif -1.5 <= price_vs_ema <= 2.5:
        pullback_quality = 1.0
    else:
        pullback_quality = 0.85

    reward_risk_ratio = upside_room_pct / max(atr_pct * 1.35, 0.35)

    expected_roi_pct = (
        upside_room_pct * 0.45
        + max(trend_strength_pct, 0.0) * 0.9
        + max(short_momentum_pct, 0.0) * 0.35
        + atr_pct * 0.35
    )
    expected_roi_pct *= (0.7 + min(max(confidence, 0.0), 1.0) * 0.6)
    expected_roi_pct *= min(1.25, max(0.8, volume_ratio / 1.1))
    expected_roi_pct *= pullback_quality
    expected_roi_pct = max(0.0, min(8.0, expected_roi_pct))

    return {
        "expected_roi_pct": round(expected_roi_pct, 2),
        "reward_risk_ratio": round(max(0.0, reward_risk_ratio), 2),
        "trend_strength_pct": round(trend_strength_pct, 2),
        "atr_pct": round(atr_pct, 2),
        "upside_room_pct": round(upside_room_pct, 2),
    }


async def assess_market_opportunity(exchange, symbol: str, timeframe: str = "15m", limit: int = 100) -> dict:
    """Score a market specifically for long-only auto-trade deployment and rotation."""
    try:
        ohlcv = await get_ohlcv(exchange, symbol, timeframe, limit)
        if len(ohlcv) < 20:
            return {
                "symbol": symbol,
                "score": 0.0,
                "rank_score": 0.0,
                "base_score": 0.0,
                "expected_roi_pct": 0.0,
                "reward_risk_ratio": 0.0,
                "trend_strength_pct": 0.0,
                "strategy": "trend_rsi",
                "params": {},
                "signal": "hold",
                "action": "WAITING",
                "confidence": 0.0,
                "reason": "Insufficient data",
                "eligible": False,
                "indicators": {},
            }

        base_score = float(_score_pair(ohlcv) or 0.0)
        strategy_name, params = pick_auto_strategy_for_ohlcv(ohlcv)
        strategy_cls = STRATEGY_MAP.get(strategy_name, AdaptiveStrategy)
        strategy = strategy_cls(params)

        if getattr(strategy, "min_candles", 0) > len(ohlcv):
            return {
                "symbol": symbol,
                "score": 0.0,
                "rank_score": 0.0,
                "base_score": round(base_score, 2),
                "expected_roi_pct": 0.0,
                "reward_risk_ratio": 0.0,
                "trend_strength_pct": 0.0,
                "strategy": strategy_name,
                "params": params,
                "signal": "hold",
                "action": "WAITING",
                "confidence": 0.0,
                "reason": f"Insufficient data ({len(ohlcv)} candles)",
                "eligible": False,
                "indicators": {},
            }

        import inspect

        sig = inspect.signature(strategy.analyze)
        if "entry_price" in sig.parameters:
            result = strategy.analyze(ohlcv, entry_price=None, candles_held=0)
        else:
            result = strategy.analyze(ohlcv)

        signal = result.signal.value
        confidence = round(float(result.confidence or 0.0), 2)
        indicators = result.indicators or {}
        in_uptrend = bool(indicators.get("in_uptrend", False))
        volume_ok = bool(indicators.get("volume_ok", False))

        upside_metrics = _estimate_long_upside_metrics(ohlcv, indicators, confidence)
        expected_roi_pct = float(upside_metrics.get("expected_roi_pct", 0.0) or 0.0)
        reward_risk_ratio = float(upside_metrics.get("reward_risk_ratio", 0.0) or 0.0)
        trend_strength_pct = float(upside_metrics.get("trend_strength_pct", 0.0) or 0.0)

        score = 0.0
        rank_score = 0.0
        if signal == "buy":
            score = base_score + 18.0 + confidence * 22.0
            if in_uptrend:
                score += 3.0
            if volume_ok:
                score += 2.0
            score += min(14.0, expected_roi_pct * 3.5)
            score += min(8.0, max(0.0, reward_risk_ratio - 1.0) * 4.0)
            rank_score = score + min(12.0, expected_roi_pct * 2.5) + min(8.0, max(0.0, trend_strength_pct) * 2.0)
        elif signal == "hold":
            score = min(base_score * (0.35 if in_uptrend else 0.2), 24.0)
            rank_score = score
        else:
            score = min(base_score * 0.1, 10.0)
            rank_score = score

        eligible = (
            signal == "buy"
            and confidence >= AUTO_MIN_BUY_CONFIDENCE
            and expected_roi_pct >= 1.0
            and reward_risk_ratio >= 1.1
        )
        if not eligible:
            score = min(score, 24.0)
            rank_score = min(rank_score, 24.0)

        roi_reason = f"Estimated upside ~{expected_roi_pct:.1f}% · reward/risk {reward_risk_ratio:.1f}x"

        return {
            "symbol": symbol,
            "score": round(min(100.0, max(0.0, score)), 2),
            "rank_score": round(min(120.0, max(0.0, rank_score)), 2),
            "base_score": round(base_score, 2),
            "expected_roi_pct": round(expected_roi_pct, 2),
            "reward_risk_ratio": round(reward_risk_ratio, 2),
            "trend_strength_pct": round(trend_strength_pct, 2),
            "strategy": strategy_name,
            "params": params,
            "signal": signal,
            "action": _normalize_market_action(signal),
            "confidence": confidence,
            "reason": f"{result.reasoning} · {roi_reason}",
            "eligible": eligible,
            "indicators": indicators,
        }
    except Exception as exc:
        return {
            "symbol": symbol,
            "score": 0.0,
            "rank_score": 0.0,
            "base_score": 0.0,
            "expected_roi_pct": 0.0,
            "reward_risk_ratio": 0.0,
            "trend_strength_pct": 0.0,
            "strategy": "ma_crossover",
            "params": {},
            "signal": "hold",
            "action": "WAITING",
            "confidence": 0.0,
            "reason": f"Scan failed: {exc}",
            "eligible": False,
            "indicators": {},
        }


async def _validate_agent_creation(session, symbol: str, budget: float, quote_currency: str = "MXN") -> None:
    """Guard against duplicate pair allocation and wallet oversubscription for the selected quote wallet."""
    normalized_quote = _normalize_quote_currency(
        quote_currency or (symbol.split("/")[-1] if symbol and "/" in symbol else "MXN")
    )

    result = await session.execute(select(AgentState).where(AgentState.status != "killed"))
    states = result.scalars().all()

    if any((state.symbol or settings.TRADING_PAIR) == symbol for state in states):
        raise ValueError(
            f"{symbol} already has a bot using wallet funds. Stop or delete it before creating another."
        )

    wallet_result = await session.execute(select(PaperWallet).limit(1))
    wallet = wallet_result.scalar_one_or_none()
    if wallet is None:
        wallet = PaperWallet(
            starting_balance=100.0,
            btc_balance=0.01,
            usd_balance=100.0,
            usdt_balance=100.0,
            updated_at=datetime.utcnow(),
        )
        session.add(wallet)
        await session.flush()

    pnl_result = await session.execute(
        select(Trade.agent_id, func.sum(Trade.pnl))
        .where(Trade.pnl.is_not(None))
        .group_by(Trade.agent_id)
    )
    pnl_by_agent = {
        agent_id: float(total or 0.0)
        for agent_id, total in pnl_result.all()
    }

    relevant_states = []
    for state in states:
        state_quote = _normalize_quote_currency(
            getattr(state, "quote_currency", None)
            or ((state.symbol or "").split("/")[-1] if getattr(state, "symbol", None) else "MXN")
        )
        if state_quote == normalized_quote:
            relevant_states.append(state)

    total_realized_pnl = sum(pnl_by_agent.get(state.agent_id, 0.0) for state in relevant_states)
    deployed = 0.0
    for state in relevant_states:
        agent_equity = max(
            0.0,
            float(state.budget_allocated or 0.0) + pnl_by_agent.get(state.agent_id, 0.0),
        )
        deployed += agent_equity

    attribute_map = {
        "MXN": "starting_balance",
        "BTC": "btc_balance",
        "USD": "usd_balance",
        "USDT": "usdt_balance",
    }
    starting_balance = float(getattr(wallet, attribute_map.get(normalized_quote, "starting_balance"), 0.0) or 0.0)
    available = max(0.0, starting_balance + total_realized_pnl - deployed)
    if float(budget or 0.0) > available + 1e-9:
        precision = 8 if normalized_quote == "BTC" else 2
        raise ValueError(
            f"Insufficient wallet balance. Requested {float(budget):.{precision}f} {normalized_quote} "
            f"but only {available:.{precision}f} {normalized_quote} available."
        )


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
        return "hold", "No stronger long setup with better upside was found in the latest market scan"
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


async def scan_best_opportunity(
    exclude_symbol: Optional[str] = None,
    blocked_symbols: Optional[set] = None,
    quote_currency: str = "MXN",
) -> tuple:
    """
    Scan all currently available Bitso markets for the selected quote wallet and return the strongest long setup.
    Returns (symbol, strategy_name, params, score).
    A positive score means the pair has an active BUY setup with enough confidence to justify deployment/rotation.
    """
    exchange = create_exchange()
    blocked = {sym for sym in (blocked_symbols or set()) if sym}
    all_pairs = await get_available_symbols(_normalize_quote_currency(quote_currency))
    pairs_to_scan = [p for p in all_pairs if p not in blocked and p != exclude_symbol]
    if exclude_symbol and exclude_symbol in all_pairs and exclude_symbol not in blocked:
        pairs_to_scan.append(exclude_symbol)
    if not pairs_to_scan:
        pairs_to_scan = [p for p in all_pairs if p not in blocked]
    if not pairs_to_scan:
        return (exclude_symbol or settings.TRADING_PAIR, "ma_crossover", {}, 0.0)

    async def _score_one(symbol: str):
        market = await assess_market_opportunity(exchange, symbol, timeframe="15m", limit=100)
        if not market.get("eligible"):
            return symbol, market.get("strategy", "ma_crossover"), market.get("params", {}), 0.0
        return (
            symbol,
            market["strategy"],
            market.get("params", {}),
            float(market.get("rank_score", market.get("score", 0.0)) or 0.0),
        )

    results = await asyncio.gather(*[_score_one(sym) for sym in pairs_to_scan])
    results = sorted(results, key=lambda x: x[3], reverse=True)
    best = results[0] if results else (exclude_symbol or settings.TRADING_PAIR, "ma_crossover", {}, 0.0)
    return best  # (symbol, strategy_name, params, score)


class AgentOrchestrator:
    _instance: Optional["AgentOrchestrator"] = None

    def __new__(cls) -> "AgentOrchestrator":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._agents: dict[str, TradingAgent] = {}
            cls._instance._tasks: dict[str, asyncio.Task] = {}
            cls._instance._broadcaster = None
            cls._instance._create_lock = None
            cls._instance._create_lock_loop = None
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
        quote_currency: str = "MXN",
        rotation_enabled: bool = False,
        aggressive_rotation: bool = False,
        rotation_interval_minutes: int = 1,
        min_rotation_score_delta: float = 1.0,
    ) -> str:
        symbol = symbol or settings.TRADING_PAIR
        quote_currency = _normalize_quote_currency(
            quote_currency or (symbol.split("/")[-1] if symbol and "/" in symbol else "MXN")
        )
        rotation_interval_minutes = max(1, int(rotation_interval_minutes or 1))
        min_rotation_score_delta = float(min_rotation_score_delta or 1.0)

        # Auto-select: scan all pairs and pick the best opportunity right now
        if strategy_name == "auto":
            rotation_enabled = True
            aggressive_rotation = True
            blocked_symbols = {
                getattr(agent, "symbol", None)
                for agent in self._agents.values()
                if getattr(agent, "symbol", None)
            }
            best_symbol, strategy_name, params, score = await scan_best_opportunity(
                blocked_symbols=blocked_symbols,
                quote_currency=quote_currency,
            )
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

        current_loop = asyncio.get_running_loop()
        if self._create_lock is None or self._create_lock_loop is not current_loop:
            self._create_lock = asyncio.Lock()
            self._create_lock_loop = current_loop

        async with self._create_lock:
            async with AsyncSessionLocal() as session:
                await _validate_agent_creation(session, symbol, budget, quote_currency=quote_currency)
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
                    quote_currency=quote_currency,
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
