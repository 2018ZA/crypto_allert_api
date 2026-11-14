"""GET /api/trades — сделки из te_trades с фильтрами."""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import get_db
from api.schemas import TradesResponse
from api.services.trades_service import get_trades_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trades", tags=["Trades"])


@router.get(
    "",
    response_model=TradesResponse,
    summary="Список сделок (te_trades)",
    description="Сделки с фильтрами: symbol, status, pnl, period. Пагинация: limit/offset.",
    operation_id="get_trades",
)
async def get_trades(
    response: Response,
    symbol: Optional[str] = Query(None, min_length=1, max_length=32, description="btc | BTCUSDT"),
    status: Optional[str] = Query(None, pattern="^(open|closed)$"),
    pnl: Optional[str] = Query(None, pattern="^(profit|loss)$", description="только для closed"),
    period: Optional[str] = Query(None, description="1h|4h|6h|12h|1d|2d|7d|30d|all"),
    from_time: Optional[datetime] = Query(None, description="ISO 8601 UTC"),
    to_time: Optional[datetime] = Query(None, description="ISO 8601 UTC"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    include_snapshot: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> TradesResponse:
    try:
        data = await get_trades_data(
            db, symbol=symbol, status=status, pnl=pnl, period=period,
            from_time=from_time, to_time=to_time,
            limit=limit, offset=offset, include_snapshot=include_snapshot,
        )
        response.headers["Cache-Control"] = "public, max-age=10"
        return TradesResponse(**data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("error in /api/trades")
        raise HTTPException(status_code=500, detail="internal server error")
