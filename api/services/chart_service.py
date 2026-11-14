"""
Сервис сбора данных для графика: свечи + сигналы.

Источники:
- kline_data       — OHLCV (все поля NOT NULL)
- oscillator_data  — сигналы (nullable overall_score / overall_signal)

Допущения:
1. kline_data хранит часовые свечи (колонки interval нет).
2. open_time — naive timestamp в UTC.
3. symbol в БД — полный тикер (ETHUSDT). API принимает и базовый (eth)
   с fallback через LIKE 'ETH%'.
4. kline_data : oscillator_data = 1 : 1. DISTINCT ON защищает от дублей.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Разрешённые периоды → часы

# None = «всё время» (без нижней границы по времени).
PERIOD_HOURS: Dict[str, Optional[int]] = {
    "1h": 1,
    "4h": 4,
    "6h": 6,
    "12h": 12,
    "1d": 24,
    "2d": 48,
    "7d": 168,
    "30d": 720,
    "all": None,
}

# Жёсткий cap на количество строк в ответе.
# Защита от выкачивания всей БД, если данных очень много.
ABSOLUTE_MAX_ROWS = 2000

# Алиасы сигналов → канонические 5 имён
SIGNAL_ALIASES: Dict[str, str] = {
    "strong buy": "strong buy",
    "strong_buy": "strong buy",
    "strong-buy": "strong buy",
    "strongbuy": "strong buy",
    "buy": "buy",
    "long": "buy",
    "sell": "sell",
    "short": "sell",
    "strong sell": "strong sell",
    "strong_sell": "strong sell",
    "strong-sell": "strong sell",
    "strongsell": "strong sell",
    "neutral": "neutral",
    "hold": "neutral",
    "none": "neutral",
}

QUOTE_SUFFIXES: tuple = ("USDT", "USDC", "BUSD", "FDUSD", "TUSD")

MAX_SYMBOL_LEN = 32
MAX_SIGNAL_ITEMS = 20
MAX_SIGNAL_ITEM_LEN = 32


# --- Нормализаторы (чистые функции, легко тестируются) -----------------

def normalize_signal(raw: Optional[str]) -> Optional[str]:
    """
    Приводит вариант сигнала к каноническому.

    Примеры:
        "STRONG_BUY" -> "strong buy"
        "Strong Buy" -> "strong buy"
        "  BUY  "    -> "buy"
        ""           -> None
    """
    if not raw:
        return None
    key = raw.strip().lower().replace("_", " ").replace("-", " ")
    key = " ".join(key.split())
    if not key:
        return None
    return SIGNAL_ALIASES.get(key, key)


def normalize_signals_filter(
    signals: Optional[List[str]],
) -> Optional[Set[str]]:
    """
    Приводит фильтр сигналов к множеству канонических имён.

    Поддерживает:
        ?signals=buy,sell          -> ["buy,sell"]   -> split внутри
        ?signals=buy&signals=sell  -> ["buy","sell"] -> как есть
    """
    if not signals:
        return None

    result: Set[str] = set()
    for raw in signals:
        if not raw:
            continue
        if len(raw) > MAX_SIGNAL_ITEM_LEN:
            raise ValueError(
                f"signal item too long (max {MAX_SIGNAL_ITEM_LEN} chars)"
            )
        for piece in raw.split(","):
            normalized = normalize_signal(piece)
            if normalized:
                result.add(normalized)

    if len(result) > MAX_SIGNAL_ITEMS:
        raise ValueError(
            f"too many signal filters (max {MAX_SIGNAL_ITEMS})"
        )

    return result or None


def normalize_symbol(symbol: str) -> str:
    """Upper-case + защита от LIKE-инъекций (только alnum)."""
    if not symbol:
        raise ValueError("symbol is empty")
    sym = symbol.strip().upper()
    if not sym:
        raise ValueError("symbol is empty after strip")
    if len(sym) > MAX_SYMBOL_LEN:
        raise ValueError(f"symbol too long (max {MAX_SYMBOL_LEN} chars)")
    if not sym.isalnum():
        raise ValueError("symbol must be alphanumeric (letters and digits only)")
    return sym


def _is_full_symbol(sym: str) -> bool:
    """True, если тикер уже содержит котируемую валюту (ETHUSDT)."""
    return any(sym.endswith(q) for q in QUOTE_SUFFIXES)


# --- Работа с БД -------------------------------------------------------

async def _fetch_rows(
    db: AsyncSession,
    sym: str,
    from_time: datetime,
    to_time: datetime,
    max_rows: int,
    *,
    prefix: bool,
) -> List[Any]:
    """
    Загружает свечи + сигналы за диапазон.

    prefix=True → LIKE 'ETH%', иначе точное совпадение.
    DISTINCT ON (k.id) защищает от дублей при множественных строках
    в oscillator_data на один kline_id.
    """
    if max_rows <= 0:
        raise ValueError(f"max_rows must be positive, got {max_rows}")

    symbol_clause = "k.symbol LIKE :sym" if prefix else "k.symbol = :sym"

    sql = text(
        f"""
        SELECT DISTINCT ON (k.open_time)
            k.id              AS kline_id,
            k.symbol          AS symbol,
            k.open_time       AS open_time,
            k.open_price      AS open_price,
            k.high_price      AS high_price,
            k.low_price       AS low_price,
            k.close_price     AS close_price,
            k.volume          AS volume,
            o.overall_score   AS overall_score,
            o.overall_signal  AS overall_signal
        FROM kline_data k
        LEFT JOIN oscillator_data o ON o.kline_id = k.id
        WHERE {symbol_clause}
          AND k.open_time >= :from_time
          AND k.open_time <= :to_time
        ORDER BY k.open_time ASC, o.id DESC NULLS LAST
        LIMIT :max_rows
        """
    )

    params = {
        "sym": f"{sym}%" if prefix else sym,
        "from_time": from_time,
        "to_time": to_time,
        "max_rows": max_rows,
    }
    result = await db.execute(sql, params)
    return result.fetchall()


def _pick_dominant_symbol(rows: List[Any]) -> List[Any]:
    """Если префикс совпал с несколькими тикерами — берём самый частый."""
    if not rows:
        return rows
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r.symbol] = counts.get(r.symbol, 0) + 1
    if len(counts) <= 1:
        return rows
    best = max(counts, key=counts.get)
    logger.info("symbol prefix matched %s; picked %s", list(counts), best)
    return [r for r in rows if r.symbol == best]


def _to_naive_utc(dt: datetime) -> datetime:
    """aware/naive → naive UTC (для сравнения с timestamp в БД)."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _to_aware_utc(dt: datetime) -> datetime:
    """naive из БД → aware UTC (для сериализации)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# --- Основная точка входа ---------------------------------------------

async def get_chart_data(
    db: AsyncSession,
    symbol: str,
    period: str,
    signals: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Возвращает свечи + сигналы за период.

    Исключения:
        ValueError — некорректные symbol/period/signals (→ HTTP 400).
    """
    period_key = (period or "").strip().lower()
    if period_key not in PERIOD_HOURS:
        raise ValueError(
            f"invalid period '{period}'. allowed: {sorted(PERIOD_HOURS)}"
    )
    hours = PERIOD_HOURS[period_key]   # Optional[int]

    sym = normalize_symbol(symbol)
    signals_set = normalize_signals_filter(signals)

    to_time_naive = _to_naive_utc(datetime.now(timezone.utc))

    if hours is None:
        # «Всё время»: без нижней границы, но не более ABSOLUTE_MAX_ROWS строк
        from_time_naive = to_time_naive - timedelta(days=365 * 10)
        max_rows = ABSOLUTE_MAX_ROWS
    else:
        from_time_naive = to_time_naive - timedelta(hours=hours + 1)
        # Запас на случай будущих минутных свечей, но не больше жёсткого cap
        max_rows = min(hours * 60 + 100, ABSOLUTE_MAX_ROWS)

    rows = await _fetch_rows(
        db, sym, from_time_naive, to_time_naive, max_rows, prefix=False,
    )

    if not rows and not _is_full_symbol(sym):
        rows = await _fetch_rows(
            db, sym, from_time_naive, to_time_naive, max_rows, prefix=True,
        )
        rows = _pick_dominant_symbol(rows)

    resolved_symbol = rows[0].symbol if rows else sym

    points: List[Dict[str, Any]] = []
    signal_points_count = 0

    for row in rows:
        sig = normalize_signal(row.overall_signal)
        has_signal = sig is not None

        if signals_set is None:
            is_filtered = has_signal
        else:
            is_filtered = sig is not None and sig in signals_set

        if is_filtered:
            signal_points_count += 1

        open_dt = _to_aware_utc(row.open_time)

        points.append({
            "timestamp": int(open_dt.timestamp() * 1000),
            "time": open_dt,
            "open": float(row.open_price),
            "high": float(row.high_price),
            "low": float(row.low_price),
            "close": float(row.close_price),
            "volume": float(row.volume),
            "signal": sig,
            "score": (
                float(row.overall_score)
                if row.overall_score is not None else None
            ),
            "has_signal": has_signal,
            "is_filtered_signal": is_filtered,
        })

    logger.info(
        "chart fetched: symbol=%s period=%s rows=%d filtered=%d filter=%s",
        resolved_symbol, period_key, len(points), signal_points_count,
        sorted(signals_set) if signals_set else "ALL",
    )

    return {
        "symbol": resolved_symbol,
        "interval": "1h",
        "period": period_key,
        "from_time": _to_aware_utc(from_time_naive),
        "to_time": _to_aware_utc(to_time_naive),
        "points_count": len(points),
        "signal_points_count": signal_points_count,
        "points": points,
    }