import json

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import AutoWatcherLog

router = APIRouter(prefix="/api/auto-watcher", tags=["auto-watcher"])


@router.get("/logs")
async def get_auto_watcher_logs(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AutoWatcherLog)
        .order_by(AutoWatcherLog.timestamp.desc())
        .offset(skip)
        .limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "id": lg.id,
            "timestamp": lg.timestamp.isoformat(),
            "action": lg.action,
            "pairs_evaluated": lg.pairs_evaluated,
            "eligible_pairs": lg.eligible_pairs,
            "agents_deployed": lg.agents_deployed,
            "details": json.loads(lg.details) if lg.details else None,
        }
        for lg in logs
    ]
