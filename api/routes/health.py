"""GET /api/health — живость API и доступность БД."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import get_db
from api.schemas import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/health", tags=["Health"])


@router.get(
    "",
    response_model=HealthResponse,
    summary="Проверка живости API и БД",
    responses={
        200: {"description": "Всё работает"},
        503: {"description": "БД недоступна"},
    },
)
async def health(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    """
    Возвращает 200, если API отвечает и БД принимает соединения.
    Возвращает 503, если БД недоступна.
    """
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.exception("health check: db unavailable")
        raise HTTPException(
            status_code=503, detail=f"db unavailable: {exc}"
        ) from exc

    return HealthResponse(status="ok", db="ok", version="1.0.0")