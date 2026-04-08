"""
Strategy reasoning endpoint — explains what each active bot is watching
and what conditions would trigger its next trade.
"""
import asyncio
import numpy as np
from fastapi import APIRouter

from agents.orchestrator import STRATEGY_MAP, _score_pair, orchestrator, pick_auto_strategy_for_ohlcv
from exchange.client import create_exchange, get_ohlcv, get_ticker

router = APIRouter(prefix="/api/strategy", tags=["strategy"])

SYMBOLS = ["BTC/MXN", "ETH/MXN", "SOL/MXN", "XRP/MXN", "AVAX/MXN", "LTC/MXN"]


def _compute_rsi(closes: list, period: int = 14) -> float:
    if len(closes) < period + 2:
        return 50.0
    arr = np.array(closes, dtype=float)
    deltas = np.diff(arr)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    rs = avg_gain / avg_loss if avg_loss else 100.0
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def _compute_ma(closes: list, period: int) -> float:
    if len(closes) < period:
        return closes[-1] if closes else 0.0
    return float(np.mean(closes[-period:]))


def _rsi_reasoning(rsi: float, oversold: float, overbought: float, has_position: bool) -> dict:
    distance_to_buy = max(0, rsi - oversold)   # how far RSI needs to DROP to trigger buy
    distance_to_sell = max(0, overbought - rsi)  # how far RSI needs to RISE to trigger sell

    if has_position:
        action = "HOLDING"
        trigger = f"Will sell when RSI reaches {overbought} (currently {rsi}, needs +{distance_to_sell:.1f})"
        urgency = "high" if distance_to_sell < 5 else "medium" if distance_to_sell < 15 else "low"
    elif rsi < oversold:
        action = "BUY SIGNAL"
        trigger = f"RSI oversold at {rsi} — buy signal active"
        urgency = "high"
    else:
        action = "WAITING"
        trigger = f"Will buy when RSI drops to {oversold} (currently {rsi}, needs -{distance_to_buy:.1f})"
        urgency = "high" if distance_to_buy < 5 else "medium" if distance_to_buy < 15 else "low"

    return {"action": action, "trigger": trigger, "urgency": urgency,
            "rsi": rsi, "oversold": oversold, "overbought": overbought,
            "distance_to_buy": round(distance_to_buy, 1),
            "distance_to_sell": round(distance_to_sell, 1)}


def _ma_reasoning(closes: list, fast: int, slow: int, has_position: bool, current_price: float) -> dict:
    fast_ma = _compute_ma(closes, fast)
    slow_ma = _compute_ma(closes, slow)
    spread_pct = (fast_ma - slow_ma) / slow_ma * 100 if slow_ma else 0

    bullish = fast_ma > slow_ma

    if has_position:
        if not bullish:
            action = "SELL SIGNAL"
            trigger = f"MAs crossed bearish — fast MA (${fast_ma:,.0f}) fell below slow MA (${slow_ma:,.0f})"
            urgency = "high"
        else:
            action = "HOLDING"
            trigger = f"Fast MA (${fast_ma:,.0f}) still above slow MA (${slow_ma:,.0f}) by {abs(spread_pct):.2f}%"
            urgency = "low"
    elif bullish:
        action = "BUY SIGNAL"
        trigger = f"Fast MA (${fast_ma:,.0f}) above slow MA (${slow_ma:,.0f}) — uptrend active"
        urgency = "medium"
    else:
        action = "WAITING"
        trigger = f"Bearish: fast MA (${fast_ma:,.0f}) below slow MA (${slow_ma:,.0f}), waiting for crossover"
        urgency = "low"

    return {"action": action, "trigger": trigger, "urgency": urgency,
            "fast_ma": round(fast_ma, 2), "slow_ma": round(slow_ma, 2),
            "spread_pct": round(spread_pct, 3), "bullish": bullish}


def _normalize_action(signal_value: str, has_position: bool) -> str:
    normalized = (signal_value or "").lower()
    if normalized == "buy":
        return "BUY SIGNAL"
    if normalized == "sell":
        return "SELL SIGNAL"
    return "HOLDING" if has_position else "WAITING"


def _pick_strategy_for_pair(ohlcv: list) -> tuple:
    """Mirror the shared auto-trade selector so the Strategy tab explains the same choices bots use."""
    return pick_auto_strategy_for_ohlcv(ohlcv)


def _reasoning_from_strategy_result(result, has_position: bool) -> dict:
    return {
        "action": _normalize_action(result.signal.value, has_position),
        "trigger": result.reasoning,
        "urgency": "high" if result.confidence > 0.7 else "medium" if result.confidence > 0.3 else "low",
        "confidence": round(float(result.confidence or 0.0), 2),
        **result.indicators,
    }


@router.get("/reasoning")
async def get_reasoning():
    """
    For each active bot, explain the current market state,
    what the strategy is watching, and what would trigger the next trade.
    """
    exchange = create_exchange()
    results = []

    for agent_id, agent in orchestrator._agents.items():
        try:
            ohlcv = await get_ohlcv(exchange, agent.symbol, "15m", 60)
            ticker = await get_ticker(exchange, agent.symbol)
            current_price = ticker.get("last", 0)
            closes = [c[4] for c in ohlcv]

            has_position = agent.open_position is not None
            strategy_name = agent.strategy.name
            params = agent.strategy.params
            entry_price = agent.open_position["price"] if has_position else None

            if strategy_name == "rsi":
                oversold = float(params.get("oversold", 30))
                overbought = float(params.get("overbought", 70))
                period = int(params.get("period", 14))
                rsi = _compute_rsi(closes, period)
                reasoning = _rsi_reasoning(rsi, oversold, overbought, has_position)
            elif strategy_name == "ma_crossover":
                fast = int(params.get("fast_period", 9))
                slow = int(params.get("slow_period", 21))
                reasoning = _ma_reasoning(closes, fast, slow, has_position, current_price)
            elif strategy_name in ("trend_rsi", "adaptive"):
                # Use the strategy's own analyze() for rich reasoning
                import inspect
                sig = inspect.signature(agent.strategy.analyze)
                if "entry_price" in sig.parameters:
                    result = agent.strategy.analyze(
                        ohlcv,
                        entry_price=entry_price,
                        candles_held=agent.open_position.get("candles_held", 0) if agent.open_position else 0,
                    )
                else:
                    result = agent.strategy.analyze(ohlcv)
                reasoning = _reasoning_from_strategy_result(result, has_position)
            else:
                reasoning = {"action": "UNKNOWN", "trigger": "Unknown strategy", "urgency": "low"}
            unrealized_pnl = None
            stop_loss_price = None
            if has_position and entry_price and current_price:
                unrealized_pnl = round((current_price - entry_price) * agent.open_position["amount"], 2)
                stop_loss_price = round(entry_price * (1 - agent.guardrails.stop_loss_pct), 2)

            results.append({
                "agent_id": agent_id,
                "symbol": agent.symbol,
                "strategy": strategy_name,
                "current_price": current_price,
                "has_position": has_position,
                "entry_price": entry_price,
                "unrealized_pnl": unrealized_pnl,
                "stop_loss_price": stop_loss_price,
                "stop_loss_pct": agent.guardrails.stop_loss_pct * 100,
                "reasoning": reasoning,
            })
        except Exception as e:
            results.append({
                "agent_id": agent_id,
                "symbol": agent.symbol,
                "strategy": agent.strategy.name,
                "error": str(e),
            })

    return {"bots": results}


@router.get("/market-scan")
async def get_market_scan():
    """Score all pairs right now and explain the current buy/sell/hold bias for each one."""
    exchange = create_exchange()

    async def _scan_one(symbol: str):
        try:
            ohlcv = await get_ohlcv(exchange, symbol, "15m", 100)
            closes = [c[4] for c in ohlcv]
            ticker = await get_ticker(exchange, symbol)
            price = ticker.get("last", 0)
            score = _score_pair(ohlcv)
            rsi = _compute_rsi(closes) if len(closes) >= 16 else 50.0
            strategy_name, params = _pick_strategy_for_pair(ohlcv)
            strategy_cls = STRATEGY_MAP.get(strategy_name)
            tracked_by = [agent_id for agent_id, agent in orchestrator._agents.items() if agent.symbol == symbol]

            if not strategy_cls:
                return {
                    "symbol": symbol,
                    "score": score,
                    "rsi": rsi,
                    "price": price,
                    "strategy": strategy_name,
                    "action": "WAITING",
                    "reason": "No strategy available for this pair right now",
                    "confidence": 0.0,
                    "tracked_by": tracked_by,
                    "tracked_count": len(tracked_by),
                }

            strategy = strategy_cls(params)
            if len(ohlcv) < getattr(strategy, "min_candles", 0):
                reason = f"Insufficient data ({len(ohlcv)} candles, need {strategy.min_candles})"
                action = "WAITING"
                confidence = 0.0
            else:
                import inspect
                sig = inspect.signature(strategy.analyze)
                if "entry_price" in sig.parameters:
                    result = strategy.analyze(ohlcv, entry_price=None, candles_held=0)
                else:
                    result = strategy.analyze(ohlcv)
                action = _normalize_action(result.signal.value, False)
                reason = result.reasoning
                confidence = round(float(result.confidence or 0.0), 2)

            return {
                "symbol": symbol,
                "score": round(float(score or 0.0), 2),
                "rsi": rsi,
                "price": price,
                "strategy": strategy_name,
                "action": action,
                "reason": reason,
                "confidence": confidence,
                "tracked_by": tracked_by,
                "tracked_count": len(tracked_by),
            }
        except Exception as e:
            return {
                "symbol": symbol,
                "score": 0,
                "rsi": 50,
                "price": 0,
                "strategy": "adaptive",
                "action": "WAITING",
                "reason": f"Scan failed: {e}",
                "confidence": 0.0,
                "tracked_by": [],
                "tracked_count": 0,
            }

    results = await asyncio.gather(*[_scan_one(s) for s in SYMBOLS])
    results = sorted(results, key=lambda x: x["score"], reverse=True)
    return {"pairs": results}
