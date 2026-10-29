from decimal import Decimal
from typing import Any

from app.domain.money import format_decimal


class DomainError(Exception):
    """Base class for business-rule violations. ``code`` is a stable, machine-readable id."""

    code = "DOMAIN_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def details(self) -> dict[str, Any]:
        return {}


class OversellError(DomainError):
    """A SELL would take the position below zero. Nothing is written when this is raised."""

    code = "INSUFFICIENT_POSITION"

    def __init__(self, *, available: Decimal, requested: Decimal, symbol: str | None = None):
        self.symbol = symbol
        self.available = available
        self.requested = requested
        subject = f"{symbol} position" if symbol else "position"
        super().__init__(
            f"SELL of {format_decimal(requested)} rejected: {subject} is only "
            f"{format_decimal(available)}. Short selling is not allowed."
        )

    def details(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "available_quantity": format_decimal(self.available),
            "requested_quantity": format_decimal(self.requested),
        }


class DuplicateStatementEntryError(DomainError):
    code = "DUPLICATE_STATEMENT_TRADE"

    def __init__(self, trade_ids: list[str]) -> None:
        self.trade_ids = trade_ids
        super().__init__(f"Venue statement lists these trade_ids more than once: {trade_ids}")

    def details(self) -> dict[str, Any]:
        return {"trade_ids": self.trade_ids}
