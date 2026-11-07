"""
Юнит-тесты для api/services/chart_service.py.
Не требуют БД — тестируются только чистые функции.
"""

import pytest

from api.services.chart_service import (
    normalize_signal,
    normalize_signals_filter,
    normalize_symbol,
)


# --- normalize_signal --------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("buy", "buy"),
    ("BUY", "buy"),
    ("  Buy  ", "buy"),
    ("Strong Buy", "strong buy"),
    ("STRONG_BUY", "strong buy"),
    ("strong-buy", "strong buy"),
    ("strongbuy", "strong buy"),
    ("sell", "sell"),
    ("SHORT", "sell"),
    ("neutral", "neutral"),
    ("hold", "neutral"),
    ("none", "neutral"),
    ("", None),
    ("   ", None),
    (None, None),
])
def test_normalize_signal(raw, expected):
    assert normalize_signal(raw) == expected


# --- normalize_signals_filter ------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    (None, None),
    ([], None),
    (["buy"], {"buy"}),
    (["buy,sell"], {"buy", "sell"}),
    (["buy", "sell"], {"buy", "sell"}),
    (["strong buy"], {"strong buy"}),
    (["BUY", "Strong_Sell"], {"buy", "strong sell"}),
    (["buy, strong buy"], {"buy", "strong buy"}),
])
def test_normalize_signals_filter(raw, expected):
    assert normalize_signals_filter(raw) == expected


def test_normalize_signals_filter_too_many():
    with pytest.raises(ValueError, match="too many"):
        normalize_signals_filter([f"s{i}" for i in range(25)])


def test_normalize_signals_filter_item_too_long():
    with pytest.raises(ValueError, match="too long"):
        normalize_signals_filter(["x" * 40])


# --- normalize_symbol --------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("eth", "ETH"),
    ("  eth  ", "ETH"),
    ("ETHUSDT", "ETHUSDT"),
    ("Sol", "SOL"),
])
def test_normalize_symbol_ok(raw, expected):
    assert normalize_symbol(raw) == expected


@pytest.mark.parametrize("raw", [
    "",
    "   ",
    "x" * 40,
    "eth;drop",
    "eth%",
    "eth_usdt",
    "eth usdt",
])
def test_normalize_symbol_rejects(raw):
    with pytest.raises(ValueError):
        normalize_symbol(raw)