"""Reusable annotated types for the HTTP boundary.

Inbound amounts must be JSON strings (or integers). JSON floats are rejected outright:
by the time ``0.1`` reaches Python as a float it is already
0.1000000000000000055511151231257827, and no amount of Decimal afterwards recovers it.
Outbound amounts are always strings.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    Field,
    PlainSerializer,
    StringConstraints,
)

from app.domain.money import SCALE, format_decimal

_MAX_DIGITS = 38


def _reject_floats(value: Any) -> Any:
    if isinstance(value, bool | float):
        raise ValueError('must be a decimal string such as "100.25" (JSON floats lose precision)')
    if isinstance(value, str):
        return value.strip()
    return value


def _finite(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError("must be a finite number")
    return value


PositiveAmount = Annotated[
    Decimal,
    BeforeValidator(_reject_floats),
    Field(gt=0, max_digits=_MAX_DIGITS, decimal_places=SCALE),
    AfterValidator(_finite),
]

DecimalStr = Annotated[Decimal, PlainSerializer(format_decimal, return_type=str)]


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]


def _normalizer(transform: Callable[[str], str]) -> BeforeValidator:
    # Runs before the pattern check, so " Binance " and "btc-usd" are accepted and stored
    # in canonical form ("binance", "BTC-USD").
    return BeforeValidator(lambda v: transform(v.strip()) if isinstance(v, str) else v)


Venue = Annotated[
    str,
    _normalizer(str.lower),
    StringConstraints(pattern=r"^[a-z0-9][a-z0-9_.-]{0,31}$"),
]

Symbol = Annotated[
    str,
    _normalizer(str.upper),
    StringConstraints(max_length=32, pattern=r"^[A-Z0-9]+([-/_][A-Z0-9]+)*$"),
]

TradeId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | list[Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Shape of every non-2xx response."""

    error: ErrorDetail
