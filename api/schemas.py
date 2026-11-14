"""
Pydantic-модели ответов API.

Все времена — UTC ISO 8601. `timestamp` — Unix ms (для lightweight-charts).
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ChartPoint(BaseModel):
    """Одна свеча + сигнал осцилляторной системы."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": 1762430400000,
                "time": "2026-11-06T12:00:00Z",
                "open": 3450.12,
                "high": 3470.55,
                "low": 3440.10,
                "close": 3465.30,
                "volume": 1234.56,
                "signal": "buy",
                "score": 5.0,
                "has_signal": True,
                "is_filtered_signal": True,
            }
        }
    )

    timestamp: int = Field(..., description="Unix ms (UTC)")
    time: datetime = Field(..., description="Время открытия свечи (UTC)")
    open: float = Field(..., description="Цена открытия")
    high: float = Field(..., description="Максимум свечи")
    low: float = Field(..., description="Минимум свечи")
    close: float = Field(..., description="Цена закрытия")
    volume: float = Field(..., description="Объём")
    signal: Optional[str] = Field(
        None,
        description="buy | sell | strong buy | strong sell | neutral | null",
    )
    score: Optional[float] = Field(
        None, description="overall_score из oscillator_data (-14..+14)"
    )
    has_signal: bool = Field(
        False, description="Есть непустой сигнал (включая neutral)"
    )
    is_filtered_signal: bool = Field(
        False,
        description="Точка прошла текущий фильтр. Используется для маркеров.",
    )


class ChartResponse(BaseModel):
    """Ответ GET /api/chart."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "ETHUSDT",
                "interval": "1h",
                "period": "1d",
                "from_time": "2026-11-06T12:00:00Z",
                "to_time": "2026-11-07T12:00:00Z",
                "points_count": 24,
                "signal_points_count": 5,
                "points": [],
            }
        }
    )

    symbol: str = Field(..., description="Разрешённый символ (ETHUSDT)")
    interval: str = Field("1h", description="Таймфрейм свечей")
    period: str = Field(..., description="1h | 4h | 6h | 12h | 1d")
    from_time: datetime = Field(..., description="Начало диапазона (UTC)")
    to_time: datetime = Field(..., description="Конец диапазона (UTC)")
    points_count: int = Field(..., description="Всего свечей")
    signal_points_count: int = Field(..., description="Сколько прошло фильтр")
    points: List[ChartPoint] = Field(
        ..., description="Свечи по возрастанию времени (ASC)"
    )


class HealthResponse(BaseModel):
    """Ответ GET /api/health."""

    status: str = Field(..., examples=["ok"])
    db: str = Field(..., examples=["ok"])
    version: str = Field(..., examples=["1.0.0"])


class ErrorResponse(BaseModel):
    """Стандартная ошибка (HTTPException)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"detail": "invalid period '2d'. allowed: ['1d', ...]"}
        }
    )
    detail: str = Field(..., description="Описание ошибки")

# ============ Trades (te_trades) ============

class TradeItem(BaseModel):
    id: int
    symbol: str = Field(..., description="Тикер: BTCUSDT")
    secid: Optional[str] = Field(None, description="ArenaGo secid (в crypto_analyzer всегда None)")
    direction: str = Field(..., description="LONG")
    status: str = Field(..., description="open | closed")
    open_time: datetime = Field(..., description="Время открытия (UTC)")
    entry_price: float
    quantity: float = Field(..., description="Количество контрактов (float)")
    size_usd: float = Field(..., description="Notional позиции в USD")
    open_score: float = Field(..., description="overall_score при открытии (-14..+14)")
    stop_loss: float
    take_profit: float
    close_time: Optional[datetime] = Field(None, description="Время закрытия (UTC), null если открыта")
    exit_price: Optional[float] = None
    close_reason: Optional[str] = Field(None, description="STOP_LOSS | TAKE_PROFIT | SIGNAL | ...")
    close_score: Optional[float] = None
    pnl_pct: Optional[float] = Field(None, description="PnL %, 1.5 = +1.5% (realized)")
    pnl_usd: Optional[float] = None
    current_price: Optional[float] = Field(None, description="Текущая цена (close последней свечи)")
    current_price_time: Optional[datetime] = Field(None, description="Время последней свечи (UTC)")
    unrealized_pnl_pct: Optional[float] = Field(None, description="Нереализованный PnL % (только для open)")
    signal_snapshot: Optional[dict] = None


class TradesSummary(BaseModel):
    total: int
    open_count: int
    closed_count: int
    wins: int
    losses: int
    win_rate: float
    total_pnl_pct: float
    total_pnl_usd: float
    avg_pnl_pct: Optional[float] = None
    unrealized_pnl_pct: float = Field(0.0, description="Суммарный нереализованный PnL % (по open)")


class TradesResponse(BaseModel):
    limit: int
    offset: int
    filters: dict
    summary: TradesSummary
    items: List[TradeItem]
