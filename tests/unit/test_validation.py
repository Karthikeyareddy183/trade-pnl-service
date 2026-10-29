from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.money import format_decimal
from app.domain.types import quote_currency
from app.schemas.trades import TradeIn

VALID: dict[str, Any] = {
    "venue": "binance",
    "trade_id": "T-1001",
    "symbol": "BTC-USD",
    "side": "BUY",
    "quantity": "10",
    "price": "100",
    "timestamp": "2026-10-29T10:00:00Z",
}


def test_example_trade_from_requirements_is_valid() -> None:
    trade = TradeIn.model_validate(VALID)
    assert trade.quantity == Decimal("10")
    assert trade.price == Decimal("100")


def test_identifiers_are_normalised_and_time_converted_to_utc() -> None:
    trade = TradeIn.model_validate(
        VALID
        | {"venue": " Binance ", "symbol": "btc-usd", "timestamp": "2026-10-29T15:30:00+05:30"}
    )
    assert trade.venue == "binance"
    assert trade.symbol == "BTC-USD"
    assert trade.timestamp.isoformat() == "2026-10-29T10:00:00+00:00"


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"quantity": "0"}, "quantity"),
        ({"quantity": "-5"}, "quantity"),
        ({"price": "0"}, "price"),
        ({"price": "-1"}, "price"),
        ({"quantity": 10.5}, "quantity"),  # JSON float: precision already lost
        ({"quantity": "NaN"}, "quantity"),
        ({"price": "Infinity"}, "price"),
        ({"quantity": "abc"}, "quantity"),
        ({"price": "1.0000000000000000001"}, "price"),  # beyond 18 dp of storage
        ({"side": "buy"}, "side"),
        ({"side": "HOLD"}, "side"),
        ({"timestamp": "2026-10-29T10:00:00"}, "timestamp"),  # naive time is ambiguous
        ({"venue": ""}, "venue"),
        ({"symbol": "BTC USD"}, "symbol"),
        ({"trade_id": ""}, "trade_id"),
        ({"fee": "1"}, "fee"),  # unknown fields are rejected, not silently dropped
    ],
)
def test_invalid_trades_are_rejected(override: dict[str, Any], field: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        TradeIn.model_validate(VALID | override)
    assert field in {str(err["loc"][0]) for err in exc_info.value.errors()}


def test_integer_amounts_are_accepted() -> None:
    assert TradeIn.model_validate(VALID | {"quantity": 3}).quantity == Decimal(3)


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (Decimal("105.000000000000000000"), "105"),
        (Decimal("106.666666666666666667"), "106.666666666666666667"),
        (Decimal("1E+2"), "100"),
        (Decimal("-0.50"), "-0.5"),
        (Decimal("0E-18"), "0"),
    ],
)
def test_decimal_formatting(value: Decimal, text: str) -> None:
    assert format_decimal(value) == text


@pytest.mark.parametrize(
    ("symbol", "quote"), [("BTC-USD", "USD"), ("ETH/BTC", "BTC"), ("SOL_USDT", "USDT"), ("X", None)]
)
def test_quote_currency(symbol: str, quote: str | None) -> None:
    assert quote_currency(symbol) == quote
