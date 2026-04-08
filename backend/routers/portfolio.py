import asyncio
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from config import settings
from exchange.client import create_exchange, get_available_symbols, get_ohlcv
from agents.orchestrator import STRATEGY_MAP, orchestrator, pick_auto_strategy_for_ohlcv
from database import get_db
from models import AgentState
from routers.settings import get_available_budget

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class DeployRequest(BaseModel):
    budget: float
    max_agents: int = 3
    min_score: float = 30.0
    rotation_enabled: bool = True
    aggressive_rotation: bool = True
    rotation_interval_minutes: int = 1
    min_rotation_score_delta: float = 1.0


class PairScore(BaseModel):
    symbol: str
    score: float
    strategy: str
    reason: str
    budget_allocated: float


class DeployResponse(BaseModel):
    total_budget: float
    pairs: List[dict]
    agent_ids: List[str]


async def _analyze_pair(exchange, symbol: str) -> dict:
    """Score a trading pair 0-100 based on technical analysis."""
    try:
        ohlcv = await get_ohlcv(exchange, symbol, "1h", 50)
        if len(ohlcv) < 20:
            return {"symbol": symbol, "score": 0, "strategy": "rsi", "reason": "insufficient data"}

        closes = [c[4] for c in ohlcv]
        volumes = [c[5] for c in ohlcv]

        # --- RSI ---
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        avg_gain = sum(gains[-14:]) / 14
        avg_loss = sum(losses[-14:]) / 14
        rsi = 100 - (100 / (1 + avg_gain / avg_loss)) if avg_loss > 0 else 50

        # --- Moving averages ---
        fast = sum(closes[-9:]) / 9
        slow = sum(closes[-21:]) / 21
        ma_bullish = fast > slow
        ma_strength = abs(fast - slow) / slow * 100

        # --- Volatility ---
        returns = [abs(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
        volatility = (sum(r ** 2 for r in returns) / len(returns)) ** 0.5 * 100

        # --- Volume trend ---
        recent_vol = sum(volumes[-5:]) / 5
        older_vol = sum(volumes[-20:-5]) / 15
        vol_ratio = recent_vol / older_vol if older_vol > 0 else 1

        # --- Scoring ---
        score = 0.0
        reasons = []

        if 25 <= rsi <= 40:
            score += 35
            reasons.append(f"RSI {rsi:.0f} oversold")
        elif 40 < rsi <= 55:
            score += 20
            reasons.append(f"RSI {rsi:.0f} neutral")
        elif 55 < rsi <= 65:
            score += 15
            reasons.append(f"RSI {rsi:.0f} bullish")
        elif rsi > 70:
            score -= 10
            reasons.append(f"RSI {rsi:.0f} overbought")
        else:
            score += 5

        if ma_bullish:
            score += min(25, ma_strength * 5)
            reasons.append(f"MA bullish +{ma_strength:.1f}%")
        else:
            score += max(0, 10 - ma_strength * 3)

        if 1.0 <= volatility <= 3.5:
            score += 25
            reasons.append(f"good volatility {volatility:.1f}%")
        elif volatility < 1.0:
            score += 5
            reasons.append(f"low volatility {volatility:.1f}%")
        else:
            score += 10
            reasons.append(f"high volatility {volatility:.1f}%")

        if vol_ratio > 1.3:
            score += 15
            reasons.append("rising volume")
        elif vol_ratio > 1.0:
            score += 5

        strategy, params = pick_auto_strategy_for_ohlcv(ohlcv)
        strategy_reason = {
            "trend_rsi": "active trend pullback profile",
            "adaptive": "adaptive calm-market profile",
            "rsi": "high-vol swing profile",
        }.get(strategy, strategy)

        signal = "hold"
        action = "WAITING"
        confidence = 0.0
        eligible = False

        strategy_cls = STRATEGY_MAP.get(strategy)
        if strategy_cls:
            signal_ohlcv = await get_ohlcv(exchange, symbol, "15m", 100)
            strategy_obj = strategy_cls(params)
            if len(signal_ohlcv) >= getattr(strategy_obj, "min_candles", 0):
                import inspect

                sig = inspect.signature(strategy_obj.analyze)
                if "entry_price" in sig.parameters:
                    result = strategy_obj.analyze(signal_ohlcv, entry_price=None, candles_held=0)
                else:
                    result = strategy_obj.analyze(signal_ohlcv)

                signal = result.signal.value
                action = {"buy": "BUY SIGNAL", "sell": "SELL SIGNAL"}.get(signal, "WAITING")
                confidence = round(float(result.confidence or 0.0), 2)
                eligible = signal == "buy" and confidence >= 0.15
                reasons.append(result.reasoning)

                if signal == "buy":
                    score += 18.0 + confidence * 22.0
                    if result.indicators.get("in_uptrend"):
                        score += 3.0
                    if result.indicators.get("volume_ok"):
                        score += 2.0
                else:
                    score = min(score, 24.0 if signal == "hold" else 10.0)

                if not eligible:
                    score = min(score, 24.0)

        reasons.append(strategy_reason)
        score = max(0.0, min(100.0, score))

        return {
            "symbol": symbol,
            "score": round(score, 1),
            "strategy": strategy,
            "params": params,
            "reason": " · ".join(reasons),
            "action": action,
            "signal": signal,
            "confidence": confidence,
            "eligible": eligible,
            "rsi": round(rsi, 1),
            "volatility": round(volatility, 2),
            "ma_bullish": ma_bullish,
        }
    except Exception as e:
        return {"symbol": symbol, "score": 0, "strategy": "ma_crossover", "reason": f"error: {e}"}


@router.post("/analyze")
async def analyze_market(max_pairs: int = 10):
    """Analyze all available pairs and return scores without deploying."""
    exchange = create_exchange()
    symbols = await get_available_symbols("MXN")
    results = await asyncio.gather(*[_analyze_pair(exchange, s) for s in symbols])
    sorted_results = sorted(results, key=lambda x: x["score"], reverse=True)
    return {"pairs": sorted_results[:max_pairs]}


@router.post("/deploy")
async def deploy_portfolio(req: DeployRequest, db: AsyncSession = Depends(get_db)):
    """Analyze market, pick best pairs, create + start agents."""
    if req.budget < 10:
        raise HTTPException(status_code=400, detail="Minimum budget is $10 MXN")
    if req.max_agents < 1 or req.max_agents > 6:
        raise HTTPException(status_code=400, detail="max_agents must be 1–6")
    if req.rotation_interval_minutes < 1 or req.rotation_interval_minutes > 5:
        raise HTTPException(status_code=400, detail="rotation_interval_minutes must be 1–5")

    available = await get_available_budget(db)
    if req.budget > available:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient wallet balance. Requested ${req.budget:.2f} MXN but only ${available:.2f} MXN available.",
        )

    active_symbols_result = await db.execute(
        select(AgentState.symbol).where(AgentState.status != "killed")
    )
    active_symbols = {row[0] for row in active_symbols_result.all() if row[0]}

    exchange = create_exchange()
    symbols = await get_available_symbols("MXN")
    symbols = [symbol for symbol in symbols if symbol not in active_symbols]

    if not symbols:
        raise HTTPException(
            status_code=400,
            detail="All supported pairs already have active bots. Stop or delete one before deploying more.",
        )

    results = await asyncio.gather(*[_analyze_pair(exchange, s) for s in symbols])
    scored = [
        r for r in results
        if r["score"] >= req.min_score and r.get("eligible") and r.get("signal") == "buy"
    ]
    scored = sorted(scored, key=lambda x: x["score"], reverse=True)[: req.max_agents]

    if not scored:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No markets currently have a strong long buy setup above score {req.min_score}. "
                "The system will keep scanning — try again in a minute or lower min_score."
            ),
        )

    total_score = sum(r["score"] for r in scored)
    agent_ids = []
    pairs_out = []

    for pair in scored:
        weight = pair["score"] / total_score
        allocated = round(req.budget * weight, 2)
        if allocated < 10:
            allocated = 10.0

        params = pair.get("params", {})

        try:
            agent_id, strategy_name = await orchestrator.create_agent(
                strategy_name=pair["strategy"],
                params=params,
                budget=allocated,
                symbol=pair["symbol"],
                rotation_enabled=req.rotation_enabled,
                aggressive_rotation=req.aggressive_rotation,
                rotation_interval_minutes=req.rotation_interval_minutes,
                min_rotation_score_delta=req.min_rotation_score_delta,
            )
            await orchestrator.start_agent(agent_id)
            agent_ids.append(agent_id)
            pairs_out.append(
                {
                    "symbol": pair["symbol"],
                    "score": pair["score"],
                    "strategy": strategy_name,
                    "reason": pair["reason"],
                    "budget_allocated": allocated,
                }
            )
        except Exception:
            continue

    if not agent_ids:
        raise HTTPException(status_code=500, detail="Failed to create any agents")

    return {
        "total_budget": req.budget,
        "pairs": pairs_out,
        "agent_ids": agent_ids,
    }
