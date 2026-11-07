"""
Точка входа FastAPI-приложения.

Запуск:
    uvicorn api.main:app --reload --port 8000
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings
from api.routes import chart_router, health_router

_settings = get_settings()

logging.basicConfig(
    level=logging.DEBUG if _settings.API_DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Crypto Alert API",
    version="1.0.0",
    description=(
        "REST API для графика криптовалют и сигналов осцилляторной системы.\n\n"
        "## Возможности\n"
        "- Свечи OHLCV (1h) с сигналами\n"
        "- Фильтр по силе сигнала\n"
        "- Периоды: 1h, 4h, 6h, 12h, 1d\n"
        "- Fallback eth → ETHUSDT\n\n"
        "## Соглашения\n"
        "- Все времена — UTC\n"
        "- `timestamp` — Unix ms\n"
        "- `is_filtered_signal` — флаг для маркеров на фронте"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS для фронтенда. Если origins = ["*"], credentials отключаем
# (браузер блокирует allow_credentials=True при wildcard).
_origins = _settings.cors_origins_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials="*" not in _origins,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(chart_router)
app.include_router(health_router)