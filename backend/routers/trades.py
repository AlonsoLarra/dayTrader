from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case

from database import get_db
from models import Trade

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("/summary")
async def trade_summary(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            func.count(Trade.id).label("total_trades"),
            func.sum(Trade.pnl).label("total_pnl"),
            func.sum(case((Trade.pnl > 0, 1), else_=0)).label("winning_trades"),
        ).where(Trade.pnl.is_not(None))
    )
    row = result.first()
    total_trades = row.total_trades or 0
    total_pnl = float(row.total_pnl or 0)
    winning = row.winning_trades or 0
    win_rate = (winning / total_trades * 100) if total_trades > 0 else 0.0
    return {
        "total_trades": total_trades,
        "total_pnl": total_pnl,
        "win_rate": round(win_rate, 2),
        "winning_trades": winning,
    }


@router.get("")
async def list_trades(
    agent_id: str = None,
    strategy: str = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    query = select(Trade)
    if agent_id:
        query = query.where(Trade.agent_id == agent_id)
    if strategy:
        query = query.where(Trade.strategy == strategy)
    query = query.order_by(Trade.timestamp.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    trades = result.scalars().all()
    return [
        {
            "id": t.id,
            "agent_id": t.agent_id,
            "symbol": t.symbol,
            "side": t.side,
            "amount": t.amount,
            "price": t.price,
            "timestamp": t.timestamp.isoformat(),
            "pnl": t.pnl,
            "mode": t.mode,
            "strategy": t.strategy,
        }
        for t in trades
    ]
