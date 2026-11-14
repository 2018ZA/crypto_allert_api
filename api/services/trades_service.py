"""Сервис выборки сделок из te_trades."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PERIOD_HOURS: Dict[str, Optional[int]] = {
    "1h": 1, "4h": 4, "6h": 6, "12h": 12,
    "1d": 24, "2d": 48, "7d": 168, "30d": 720,
    "all": None,
}

QUOTE_SUFFIXES = ("USDT", "USDC", "BUSD", "FDUSD", "TUSD")
MAX_LIMIT = 1000
MAX_SYMBOL_LEN = 32


def _resolve_symbol(raw: str) -> str:
    s = raw.strip().upper()
    if not s:
        raise ValueError("symbol is empty")
    if len(s) > MAX_SYMBOL_LEN:
        raise ValueError(f"symbol too long (max {MAX_SYMBOL_LEN})")
    if not s.isalnum():
        raise ValueError("symbol must be alphanumeric")
    if any(s.endswith(q) for q in QUOTE_SUFFIXES):
        return s
    return s + "USDT"


def _normalize_status(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    s = raw.strip().lower()
    if s in ("open", "opened", "active", "1"):
        return "1"
    if s in ("closed", "close", "0"):
        return "0"
    raise ValueError(f"invalid status '{raw}', expected 'open' or 'closed'")


def _normalize_pnl(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    s = raw.strip().lower()
    if s in ("profit", "win", "positive", "+"):
        return "profit"
    if s in ("loss", "lose", "negative", "-"):
        return "loss"
    raise ValueError(f"invalid pnl '{raw}', expected 'profit' or 'loss'")


def _to_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _to_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _build_where(*, symbol, status, pnl, from_time, to_time):
    clauses = ["1=1"]
    params = {}
    if symbol:
        clauses.append("t.symbol = :symbol"); params["symbol"] = symbol
    if status:
        clauses.append("t.status = :status"); params["status"] = status
    if from_time is not None:
        clauses.append("t.open_time >= :from_time"); params["from_time"] = from_time
    if to_time is not None:
        clauses.append("t.open_time <= :to_time"); params["to_time"] = to_time
    if pnl == "profit":
        clauses.append("t.status = '0' AND t.pnl_pct > 0")
    elif pnl == "loss":
        clauses.append("t.status = '0' AND t.pnl_pct <= 0")
    return " AND ".join(clauses), params


async def get_trades_data(
    db: AsyncSession,
    *,
    symbol: Optional[str] = None,
    status: Optional[str] = None,
    pnl: Optional[str] = None,
    period: Optional[str] = None,
    from_time: Optional[datetime] = None,
    to_time: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
    include_snapshot: bool = False,
) -> Dict[str, Any]:
    if limit < 1 or limit > MAX_LIMIT:
        raise ValueError(f"limit must be in [1, {MAX_LIMIT}]")
    if offset < 0:
        raise ValueError("offset must be >= 0")

    sym = _resolve_symbol(symbol) if symbol else None
    st = _normalize_status(status)
    pnl_norm = _normalize_pnl(pnl)

    if pnl_norm is not None and st == "1":
        raise ValueError("pnl filter only applies to closed trades (status='closed')")

    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    to_naive = _to_naive_utc(to_time) if to_time else now_naive

    if from_time is not None:
        from_naive = _to_naive_utc(from_time)
    elif period:
        key = (period or "").strip().lower()
        if key not in PERIOD_HOURS:
            raise ValueError(f"invalid period '{period}'. allowed: {sorted(PERIOD_HOURS)}")
        hours = PERIOD_HOURS[key]
        from_naive = None if hours is None else now_naive - timedelta(hours=hours)
    else:
        from_naive = None

    where_sql, params = _build_where(
        symbol=sym, status=st, pnl=pnl_norm,
        from_time=from_naive, to_time=to_naive,
    )

    snapshot_col = "t.signal_snapshot" if include_snapshot else "NULL::json"
    items_sql = text(f"""
        SELECT
            t.id, t.symbol, t.direction, t.status,
            t.open_time, t.entry_price, t.quantity, t.size_usd, t.open_score,
            t.stop_loss, t.take_profit,
            t.close_time, t.exit_price, t.close_reason, t.close_score,
            t.pnl_pct, t.pnl_usd,
            {snapshot_col} AS signal_snapshot
        FROM te_trades t
        WHERE {where_sql}
        ORDER BY t.open_time DESC, t.id DESC
        LIMIT :limit OFFSET :offset
    """)
    rows = (await db.execute(items_sql, {**params, "limit": limit, "offset": offset})).fetchall()

    items = []
    for r in rows:
        pnl_pct_pct = float(r.pnl_pct) * 100.0 if r.pnl_pct is not None else None
        items.append({
            "id": r.id,
            "symbol": r.symbol,
            "secid": None,  # в этой БД нет secid (только symbol)
            "direction": r.direction,
            "status": "open" if r.status == "1" else "closed",
            "open_time": _to_aware_utc(r.open_time),
            "entry_price": float(r.entry_price),
            "quantity": float(r.quantity),
            "size_usd": float(r.size_usd),
            "open_score": float(r.open_score),
            "stop_loss": float(r.stop_loss),
            "take_profit": float(r.take_profit),
            "close_time": _to_aware_utc(r.close_time),
            "exit_price": float(r.exit_price) if r.exit_price is not None else None,
            "close_reason": r.close_reason,
            "close_score": float(r.close_score) if r.close_score is not None else None,
            "pnl_pct": pnl_pct_pct,
            "pnl_usd": float(r.pnl_usd) if r.pnl_usd is not None else None,
            "signal_snapshot": r.signal_snapshot if include_snapshot else None,
        })

    summary_sql = text(f"""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE t.status = '1') AS open_count,
            COUNT(*) FILTER (WHERE t.status = '0') AS closed_count,
            COUNT(*) FILTER (WHERE t.status = '0' AND t.pnl_pct > 0)  AS wins,
            COUNT(*) FILTER (WHERE t.status = '0' AND t.pnl_pct <= 0) AS losses,
            COALESCE(SUM(t.pnl_pct) FILTER (WHERE t.status = '0'), 0) AS total_pnl_frac,
            COALESCE(SUM(t.pnl_usd) FILTER (WHERE t.status = '0'), 0) AS total_pnl_usd
        FROM te_trades t
        WHERE {where_sql}
    """)
    srow = (await db.execute(summary_sql, params)).first()

    total = int(srow.total or 0)
    closed_count = int(srow.closed_count or 0)
    wins = int(srow.wins or 0)
    losses = int(srow.losses or 0)
    total_pnl_pct = float(srow.total_pnl_frac or 0.0) * 100.0
    total_pnl_usd = float(srow.total_pnl_usd or 0.0)
    win_rate = (wins / closed_count) if closed_count else 0.0
    avg_pnl_pct = (total_pnl_pct / closed_count) if closed_count else None

    summary = {
        "total": total,
        "open_count": int(srow.open_count or 0),
        "closed_count": closed_count,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 4),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "total_pnl_usd": round(total_pnl_usd, 4),
        "avg_pnl_pct": round(avg_pnl_pct, 2) if avg_pnl_pct is not None else None,
    }

    filters = {
        "symbol": sym,
        "status": "open" if st == "1" else ("closed" if st == "0" else None),
        "pnl": pnl_norm, "period": period,
        "from_time": _to_aware_utc(from_naive),
        "to_time": _to_aware_utc(to_naive),
    }

    logger.info("trades fetched: total=%d items=%d", total, len(items))

    return {
        "limit": limit, "offset": offset,
        "filters": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in filters.items()},
        "summary": summary, "items": items,
    }
