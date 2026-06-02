import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from agents.orchestrator import orchestrator
from database import AsyncSessionLocal
from models import TrainingRun, TrainingTrial
from training.service import training_service

router = APIRouter(prefix="/api/training", tags=["training"])


class TrainingGoalRequest(BaseModel):
    target_return_pct: float = 0.1
    min_win_rate: float = 45.0
    max_drawdown_pct: float = 18.0
    min_trades: int = 5


class StartTrainingRequest(BaseModel):
    symbol: str = "BTC/MXN"
    timeframe: str = "1h"
    start_date: str = "2024-01-01"
    end_date: str = "2024-06-01"
    initial_capital: float = 10000.0
    max_trials: int = Field(default=24, ge=1, le=500)
    strategy_candidates: List[str] = ["rsi", "ma_crossover", "trend_rsi", "adaptive"]
    goal: TrainingGoalRequest = TrainingGoalRequest()


class PromoteRequest(BaseModel):
    budget: float = Field(gt=0)
    auto_start: bool = True
    allow_unmet_goal: bool = False


def _safe_json(payload: Optional[str], default: Any) -> Any:
    if not payload:
        return default
    try:
        return json.loads(payload)
    except Exception:
        return default


@router.post("/runs")
async def start_training_run(req: StartTrainingRequest):
    run_id = await training_service.start_run(req.model_dump())
    return {"run_id": run_id, "status": "running"}


@router.get("/runs")
async def list_training_runs(limit: int = 20):
    safe_limit = min(max(limit, 1), 200)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TrainingRun).order_by(desc(TrainingRun.created_at)).limit(safe_limit)
        )
        runs = result.scalars().all()

    return [
        {
            "run_id": run.run_id,
            "status": run.status,
            "symbol": run.symbol,
            "timeframe": run.timeframe,
            "start_date": run.start_date,
            "end_date": run.end_date,
            "max_trials": run.max_trials,
            "completed_trials": run.completed_trials,
            "best_score": run.best_score,
            "best_strategy": run.best_strategy,
            "best_goal_met": bool(_safe_json(run.best_metrics_json, {}).get("goal_met", False)),
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        }
        for run in runs
    ]


@router.get("/runs/{run_id}")
async def get_training_run(run_id: str):
    async with AsyncSessionLocal() as session:
        run_result = await session.execute(select(TrainingRun).where(TrainingRun.run_id == run_id))
        run = run_result.scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail="Training run not found")

        trials_result = await session.execute(
            select(TrainingTrial)
            .where(TrainingTrial.run_id == run_id)
            .order_by(desc(TrainingTrial.objective_score), desc(TrainingTrial.trial_index))
            .limit(100)
        )
        trials = trials_result.scalars().all()

    best_metrics = _safe_json(run.best_metrics_json, {})
    return {
        "run_id": run.run_id,
        "status": run.status,
        "symbol": run.symbol,
        "timeframe": run.timeframe,
        "start_date": run.start_date,
        "end_date": run.end_date,
        "initial_capital": run.initial_capital,
        "max_trials": run.max_trials,
        "completed_trials": run.completed_trials,
        "strategy_candidates": _safe_json(run.strategy_candidates_json, []),
        "goal": _safe_json(run.goal_json, {}),
        "best": {
            "strategy": run.best_strategy,
            "score": run.best_score,
            "params": _safe_json(run.best_params_json, {}),
            "metrics": best_metrics,
            "goal_met": bool(best_metrics.get("goal_met", False)),
        },
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "trials": [
            {
                "id": trial.id,
                "trial_index": trial.trial_index,
                "strategy": trial.strategy,
                "params": _safe_json(trial.params_json, {}),
                "status": trial.status,
                "objective_score": trial.objective_score,
                "metrics": _safe_json(trial.metrics_json, {}),
                "error_message": trial.error_message,
                "created_at": trial.created_at.isoformat() if trial.created_at else None,
                "finished_at": trial.finished_at.isoformat() if trial.finished_at else None,
            }
            for trial in trials
        ],
    }


@router.post("/runs/{run_id}/stop")
async def stop_training_run(run_id: str):
    stopped = await training_service.stop_run(run_id)
    if not stopped:
        raise HTTPException(status_code=404, detail="Training run not found")
    return {"run_id": run_id, "status": "stopped"}


@router.post("/runs/{run_id}/promote")
async def promote_run(run_id: str, req: PromoteRequest):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(TrainingRun).where(TrainingRun.run_id == run_id))
        run = result.scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail="Training run not found")
        if not run.best_strategy:
            raise HTTPException(status_code=400, detail="Run has no promotable strategy yet")
        params = _safe_json(run.best_params_json, {})
        best_metrics = _safe_json(run.best_metrics_json, {})
        goal_met = bool(best_metrics.get("goal_met", False))

        if not goal_met and not req.allow_unmet_goal:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Best candidate has not met the training goal yet. "
                    "Wait for a better run or explicitly allow unmet-goal promotion."
                ),
            )

    try:
        agent_id, strategy = await orchestrator.create_agent(
            strategy_name=run.best_strategy,
            params=params,
            budget=req.budget,
            symbol=run.symbol,
            quote_currency=run.symbol.split("/")[-1] if "/" in run.symbol else "MXN",
            rotation_enabled=True,
            aggressive_rotation=True,
            rotation_interval_minutes=1,
            min_rotation_score_delta=1.0,
        )
        if req.auto_start:
            await orchestrator.start_agent(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "run_id": run_id,
        "agent_id": agent_id,
        "strategy": strategy,
        "status": "promoted",
        "auto_started": req.auto_start,
        "goal_met": goal_met,
    }
