import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True, slots=True)
class Fill:
    """The part of a trade that affects a position."""

    side: Side
    quantity: Decimal
    price: Decimal


@dataclass(frozen=True, slots=True)
class TradeRecord:
    """A trade as seen by reconciliation, from either our ledger or a venue statement."""

    trade_id: str
    symbol: str
    side: Side
    quantity: Decimal
    price: Decimal
    executed_at: datetime


_SYMBOL_SEPARATOR = re.compile(r"[-/_]")


def quote_currency(symbol: str) -> str | None:
    """``BTC-USD`` -> ``USD``. PnL of a symbol is denominated in its quote currency, so
    totals are only ever summed within one quote currency."""
    parts = _SYMBOL_SEPARATOR.split(symbol)
    return parts[-1] if len(parts) > 1 else None
