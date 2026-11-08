"""GET /api/chart — свечи + сигналы по часам."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import get_db
from api.schemas import ChartResponse, ErrorResponse
from api.services.chart_service import get_chart_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chart", tags=["Chart"])


@router.get(
    "",
    response_model=ChartResponse,
    summary="Свечи + сигналы по часам",
    description=(
        "Возвращает OHLCV-свечи и сигналы осцилляторной системы.\n\n"
        "**Фильтр `signals`** не сужает массив свечей — каждой точке "
        "ставится флаг `is_filtered_signal`. Фронт использует его "
        "для маркеров, а свечи рисует полностью."
    ),
    responses={
        200: {"model": ChartResponse, "description": "Успех"},
        400: {"model": ErrorResponse, "description": "Невалидные параметры"},
        500: {"model": ErrorResponse, "description": "Внутренняя ошибка"},
    },
    operation_id="get_chart_data",
)
async def get_chart(
    response: Response,
    symbol: str = Query(
        ...,
        min_length=1,
        max_length=32,
        description="eth | btc | sol | ETHUSDT",
        openapi_examples={
            "base_ticker": {"summary": "ETH", "value": "eth"},
            "full_ticker": {"summary": "ETHUSDT", "value": "ETHUSDT"},
        },
    ),
    period: str = Query(
    "1d",
    description="1h | 4h | 6h | 12h | 1d | 2d | 7d | 30d | all",
    openapi_examples={
        "last_hour":   {"summary": "1 час",     "value": "1h"},
        "last_4h":     {"summary": "4 часа",    "value": "4h"},
        "last_6h":     {"summary": "6 часов",   "value": "6h"},
        "last_12h":    {"summary": "12 часов",  "value": "12h"},
        "last_day":    {"summary": "Сутки",     "value": "1d"},
        "last_2d":     {"summary": "2 дня",     "value": "2d"},
        "last_week":   {"summary": "7 дней",    "value": "7d"},
        "last_month":  {"summary": "Месяц",     "value": "30d"},
        "all_time":    {"summary": "Всё время", "value": "all"},
        },
    ),
    signals: Optional[List[str]] = Query(
        None,
        description=(
            "buy | sell | strong buy | strong sell | neutral. "
            "Форматы: `?signals=buy,sell` или `?signals=buy&signals=sell`."
        ),
        openapi_examples={
            "all": {"summary": "Все сигналы", "value": None},
            "buy_family": {
                "summary": "buy + strong buy",
                "value": ["buy", "strong buy"],
            },
            "sell_family": {
                "summary": "sell + strong sell",
                "value": ["sell", "strong sell"],
            },
        },
    ),
    db: AsyncSession = Depends(get_db),
) -> ChartResponse:
    try:
        data = await get_chart_data(
            db=db, symbol=symbol, period=period, signals=signals,
        )
        response.headers["Cache-Control"] = "public, max-age=30"
        return ChartResponse(**data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception(
            "unexpected error in /api/chart symbol=%r period=%r",
            symbol, period,
        )
        raise HTTPException(status_code=500, detail="internal server error")