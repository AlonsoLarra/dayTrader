import asyncio
import json
import random
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select

from backtester.runner import BacktestRunner
from database import AsyncSessionLocal
from models import TrainingRun, TrainingTrial
from strategies.adaptive import AdaptiveStrategy
from strategies.ma_crossover import MACrossoverStrategy
from strategies.rsi import RSIStrategy
from strategies.trend_rsi import TrendRSIStrategy

STRATEGY_MAP = {
    "rsi": RSIStrategy,
    "ma_crossover": MACrossoverStrategy,
    "trend_rsi": TrendRSIStrategy,
    "adaptive": AdaptiveStrategy,
}

DEFAULT_CANDIDATES = ["rsi", "ma_crossover", "trend_rsi", "adaptive"]


def _json_dumps(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"))


def _json_loads(payload: Optional[str], default: Any) -> Any:
    if not payload:
        return default
    try:
        return json.loads(payload)
    except Exception:
        return default


class TrainingService:
    _instance: Optional["TrainingService"] = None

    def __new__(cls) -> "TrainingService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tasks = {}
            cls._instance._broadcaster = None
        return cls._instance

    def set_broadcaster(self, broadcaster) -> None:
        self._broadcaster = broadcaster

    async def start_run(self, payload: Dict[str, Any]) -> str:
        run_id = str(uuid.uuid4())[:10]
        now = datetime.utcnow()

        candidates = [
            c for c in payload.get("strategy_candidates", DEFAULT_CANDIDATES)
            if c in STRATEGY_MAP
        ]
        if not candidates:
            candidates = list(DEFAULT_CANDIDATES)

        goal = {
            "target_return_pct": float(payload.get("goal", {}).get("target_return_pct", 0.1)),
            "min_win_rate": float(payload.get("goal", {}).get("min_win_rate", 45.0)),
            "max_drawdown_pct": float(payload.get("goal", {}).get("max_drawdown_pct", 18.0)),
            "min_trades": int(payload.get("goal", {}).get("min_trades", 5)),
        }

        async with AsyncSessionLocal() as session:
            session.add(
                TrainingRun(
                    run_id=run_id,
                    status="running",
                    symbol=payload.get("symbol", "BTC/MXN"),
                    timeframe=payload.get("timeframe", "1h"),
                    start_date=payload.get("start_date", "2024-01-01"),
                    end_date=payload.get("end_date", "2024-06-01"),
                    initial_capital=float(payload.get("initial_capital", 10000.0)),
                    max_trials=max(1, int(payload.get("max_trials", 24))),
                    completed_trials=0,
                    strategy_candidates_json=_json_dumps(candidates),
                    goal_json=_json_dumps(goal),
                    created_at=now,
                    started_at=now,
                    updated_at=now,
                )
            )
            await session.commit()

        self._tasks[run_id] = asyncio.create_task(self._execute_run(run_id))
        await self._emit("training_update", {
            "run_id": run_id,
            "status": "running",
            "completed_trials": 0,
        })
        return run_id

    async def stop_run(self, run_id: str) -> bool:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(TrainingRun).where(TrainingRun.run_id == run_id))
            run = result.scalar_one_or_none()
            if not run:
                return False
            if run.status in ("completed", "failed", "stopped"):
                return True
            run.status = "stopped"
            run.finished_at = datetime.utcnow()
            run.updated_at = datetime.utcnow()
            await session.commit()

        task = self._tasks.get(run_id)
        if task and not task.done():
            task.cancel()
        await self._emit("training_update", {
            "run_id": run_id,
            "status": "stopped",
        })
        return True

    async def _execute_run(self, run_id: str) -> None:
        stats: Dict[str, Dict[str, float]] = {}
        runner = BacktestRunner()

        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(TrainingRun).where(TrainingRun.run_id == run_id))
                run = result.scalar_one_or_none()
                if not run:
                    return

                candidates = _json_loads(run.strategy_candidates_json, DEFAULT_CANDIDATES)
                goal = _json_loads(run.goal_json, {})

            for strategy_name in candidates:
                stats[strategy_name] = {"plays": 0.0, "reward_sum": 0.0}

            for trial_index in range(1, 100000):
                async with AsyncSessionLocal() as session:
                    run = await self._get_run(session, run_id)
                    if not run:
                        return
                    if run.status != "running":
                        break
                    if trial_index > int(run.max_trials):
                        break

                strategy_name = self._pick_strategy(stats)
                params = self._sample_params(strategy_name)
                now = datetime.utcnow()

                async with AsyncSessionLocal() as session:
                    session.add(
                        TrainingTrial(
                            run_id=run_id,
                            trial_index=trial_index,
                            strategy=strategy_name,
                            params_json=_json_dumps(params),
                            status="pending",
                            created_at=now,
                        )
                    )
                    await session.commit()

                metrics: Dict[str, Any]
                score = -9999.0
                trial_status = "completed"
                trial_error = None

                try:
                    strategy_cls = STRATEGY_MAP[strategy_name]
                    strategy = strategy_cls(params)
                    metrics = await runner.run(
                        strategy=strategy,
                        symbol=run.symbol,
                        timeframe=run.timeframe,
                        start_date=run.start_date,
                        end_date=run.end_date,
                        initial_capital=run.initial_capital,
                    )
                    if metrics.get("error"):
                        trial_status = "failed"
                        trial_error = str(metrics.get("error"))
                    score, goal_met = self._score_metrics(metrics, goal)
                    metrics["goal_met"] = goal_met
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    metrics = {"error": str(exc)}
                    trial_status = "failed"
                    trial_error = str(exc)

                stats[strategy_name]["plays"] += 1
                stats[strategy_name]["reward_sum"] += float(score)

                await self._record_trial_result(
                    run_id=run_id,
                    trial_index=trial_index,
                    strategy_name=strategy_name,
                    metrics=metrics,
                    score=score,
                    status=trial_status,
                    error_message=trial_error,
                )

            await self._finalize_run_if_running(run_id)
        except asyncio.CancelledError:
            await self._emit("training_update", {"run_id": run_id, "status": "stopped"})
            raise
        except Exception as exc:
            await self._mark_failed(run_id, str(exc))

    async def _record_trial_result(
        self,
        run_id: str,
        trial_index: int,
        strategy_name: str,
        metrics: Dict[str, Any],
        score: float,
        status: str,
        error_message: Optional[str],
    ) -> None:
        finished_at = datetime.utcnow()
        async with AsyncSessionLocal() as session:
            run = await self._get_run(session, run_id)
            if not run:
                return

            result = await session.execute(
                select(TrainingTrial).where(
                    TrainingTrial.run_id == run_id,
                    TrainingTrial.trial_index == trial_index,
                )
            )
            trial = result.scalar_one_or_none()
            if trial:
                trial.status = status
                trial.metrics_json = _json_dumps(metrics)
                trial.objective_score = float(score)
                trial.error_message = error_message
                trial.finished_at = finished_at

            run.completed_trials = int(run.completed_trials or 0) + 1
            run.updated_at = finished_at

            best_score = float(run.best_score) if run.best_score is not None else None
            if status == "completed" and (best_score is None or score > best_score):
                run.best_score = float(score)
                run.best_strategy = strategy_name
                run.best_params_json = trial.params_json if trial else _json_dumps({})
                run.best_metrics_json = _json_dumps(metrics)

            if run.completed_trials >= run.max_trials and run.status == "running":
                run.status = "completed"
                run.finished_at = finished_at

            await session.commit()

            await self._emit(
                "training_update",
                {
                    "run_id": run_id,
                    "status": run.status,
                    "completed_trials": run.completed_trials,
                    "max_trials": run.max_trials,
                    "best_score": run.best_score,
                    "best_strategy": run.best_strategy,
                },
            )

            if run.status == "completed":
                await self._emit(
                    "training_run_completed",
                    {
                        "run_id": run_id,
                        "best_score": run.best_score,
                        "best_strategy": run.best_strategy,
                        "completed_trials": run.completed_trials,
                    },
                )

    async def _finalize_run_if_running(self, run_id: str) -> None:
        async with AsyncSessionLocal() as session:
            run = await self._get_run(session, run_id)
            if not run:
                return
            if run.status == "running":
                run.status = "completed"
                run.finished_at = datetime.utcnow()
                run.updated_at = datetime.utcnow()
                await session.commit()
                await self._emit(
                    "training_run_completed",
                    {
                        "run_id": run_id,
                        "best_score": run.best_score,
                        "best_strategy": run.best_strategy,
                        "completed_trials": run.completed_trials,
                    },
                )

    async def _mark_failed(self, run_id: str, message: str) -> None:
        async with AsyncSessionLocal() as session:
            run = await self._get_run(session, run_id)
            if not run:
                return
            run.status = "failed"
            run.error_message = message
            run.finished_at = datetime.utcnow()
            run.updated_at = datetime.utcnow()
            await session.commit()
        await self._emit("training_run_failed", {"run_id": run_id, "error": message})

    async def _emit(self, msg_type: str, payload: Dict[str, Any]) -> None:
        if not self._broadcaster:
            return
        try:
            await self._broadcaster.broadcast({"type": msg_type, "payload": payload})
        except Exception:
            pass

    async def _get_run(self, session, run_id: str) -> Optional[TrainingRun]:
        result = await session.execute(select(TrainingRun).where(TrainingRun.run_id == run_id))
        return result.scalar_one_or_none()

    def _pick_strategy(self, stats: Dict[str, Dict[str, float]]) -> str:
        epsilon = 0.25
        names = list(stats.keys())
        if not names:
            return "trend_rsi"
        if random.random() < epsilon:
            return random.choice(names)

        best_name = names[0]
        best_value = -9999.0
        for name in names:
            plays = max(1.0, stats[name]["plays"])
            avg_reward = stats[name]["reward_sum"] / plays
            if avg_reward > best_value:
                best_value = avg_reward
                best_name = name
        return best_name

    def _score_metrics(self, metrics: Dict[str, Any], goal: Dict[str, Any]) -> Tuple[float, bool]:
        if metrics.get("error"):
            return -100.0, False

        total_return_pct = float(metrics.get("total_return_pct", 0.0) or 0.0)
        win_rate = float(metrics.get("win_rate", 0.0) or 0.0)
        drawdown = float(metrics.get("max_drawdown_pct", 0.0) or 0.0)
        total_trades = float(metrics.get("total_trades", 0) or 0)

        target_return_pct = max(0.01, float(goal.get("target_return_pct", 0.1)))
        min_win_rate = max(1.0, float(goal.get("min_win_rate", 45.0)))
        max_drawdown_pct = max(1.0, float(goal.get("max_drawdown_pct", 18.0)))
        min_trades = max(1.0, float(goal.get("min_trades", 5)))

        score = 0.0
        score += max(-40.0, min(60.0, total_return_pct * 4.0))
        if total_return_pct > 0:
            score += 20.0

        score += max(0.0, min(20.0, (win_rate / min_win_rate) * 20.0))
        drawdown_factor = max(0.0, 1.0 - min(drawdown, max_drawdown_pct) / max_drawdown_pct)
        score += drawdown_factor * 15.0
        score += max(0.0, min(5.0, (total_trades / min_trades) * 5.0))

        goal_met = (
            total_return_pct >= target_return_pct
            and win_rate >= min_win_rate
            and drawdown <= max_drawdown_pct
            and total_trades >= min_trades
        )
        if goal_met:
            score += 10.0

        return round(score, 3), goal_met

    def _sample_params(self, strategy_name: str) -> Dict[str, Any]:
        if strategy_name == "rsi":
            period = random.randint(10, 20)
            oversold = random.randint(28, 42)
            overbought = random.randint(58, 75)
            if oversold >= overbought:
                overbought = min(80, oversold + 15)
            return {
                "period": period,
                "oversold": oversold,
                "overbought": overbought,
            }

        if strategy_name == "ma_crossover":
            fast = random.randint(6, 16)
            slow = random.randint(18, 60)
            if fast >= slow:
                slow = fast + random.randint(8, 20)
            return {
                "fast_period": fast,
                "slow_period": slow,
            }

        if strategy_name == "trend_rsi":
            return {
                "ema_period": random.randint(40, 80),
                "rsi_period": random.randint(10, 18),
                "rsi_buy": random.randint(38, 50),
                "rsi_sell": random.randint(60, 75),
                "volume_factor": round(random.uniform(0.9, 1.25), 2),
                "profit_target_pct": round(random.uniform(0.01, 0.045), 4),
                "max_hold_candles": random.randint(8, 24),
            }

        return {
            "ema_period": random.randint(40, 80),
            "rsi_period": random.randint(10, 18),
            "volume_factor": round(random.uniform(0.9, 1.25), 2),
            "max_hold_candles": random.randint(10, 30),
            "rsi_buy_low_vol": round(random.uniform(38.0, 46.0), 1),
            "rsi_buy_normal": round(random.uniform(40.0, 48.0), 1),
            "rsi_buy_high_vol": round(random.uniform(30.0, 42.0), 1),
            "rsi_sell_low_vol": round(random.uniform(58.0, 66.0), 1),
            "rsi_sell_normal": round(random.uniform(60.0, 70.0), 1),
            "rsi_sell_high_vol": round(random.uniform(68.0, 80.0), 1),
            "min_profit_for_macd_exit": round(random.uniform(0.002, 0.01), 4),
        }


training_service = TrainingService()
