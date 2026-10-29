from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.domain.money import format_decimal
from app.domain.types import Side, TradeRecord
from app.schemas.common import DecimalStr, PositiveAmount, Symbol, TradeId, UtcDatetime


class StatementTrade(BaseModel):
    """One line of the venue's statement. Same fields as a trade, without `venue`."""

    model_config = ConfigDict(extra="forbid")

    trade_id: TradeId = Field(description="Matched against our `trade_id` for this venue.")
    symbol: Symbol
    side: Side
    quantity: PositiveAmount = Field(description='As a string, e.g. `"10"`.')
    price: PositiveAmount = Field(description='As a string, e.g. `"100"`.')
    timestamp: UtcDatetime = Field(description="Must include a timezone.")

    def to_record(self) -> TradeRecord:
        return TradeRecord(
            trade_id=self.trade_id,
            symbol=self.symbol,
            side=self.side,
            quantity=self.quantity,
            price=self.price,
            executed_at=self.timestamp,
        )


class StatementIn(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "trades": [
                        {
                            "trade_id": "T1",
                            "symbol": "BTC-USD",
                            "side": "BUY",
                            "quantity": "10",
                            "price": "100",
                            "timestamp": "2026-10-29T10:00:00Z",
                        },
                        {
                            "trade_id": "T2",
                            "symbol": "BTC-USD",
                            "side": "BUY",
                            "quantity": "10",
                            "price": "110",
                            "timestamp": "2026-10-29T10:01:00Z",
                        },
                    ]
                }
            ]
        },
    )

    period_start: UtcDatetime | None = Field(
        default=None,
        description="Optional. Start of the period the statement covers. Our trades before "
        "this time are ignored.",
    )
    period_end: UtcDatetime | None = Field(
        default=None,
        description="Optional. End of the period (exclusive). Our trades at or after this "
        "time are ignored.",
    )
    trades: list[StatementTrade] = Field(
        max_length=100_000, description="Every trade the venue reports for this period."
    )

    @model_validator(mode="after")
    def _period_is_ordered(self) -> "StatementIn":
        if self.period_start and self.period_end and self.period_start >= self.period_end:
            raise ValueError("period_start must be before period_end")
        return self


class StatementTradeOut(BaseModel):
    trade_id: str
    symbol: str
    side: Side
    quantity: DecimalStr
    price: DecimalStr
    timestamp: datetime

    @classmethod
    def from_record(cls, record: TradeRecord) -> "StatementTradeOut":
        return cls(
            trade_id=record.trade_id,
            symbol=record.symbol,
            side=record.side,
            quantity=record.quantity,
            price=record.price,
            timestamp=record.executed_at,
        )


class FieldDifferenceOut(BaseModel):
    field: str = Field(description="Which field differs, e.g. `quantity`.")
    recorded: Any = Field(description="Our value.")
    statement: Any = Field(description="The venue's value.")

    @field_serializer("recorded", "statement")
    def _render(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Decimal):
            return format_decimal(value)
        return str(value)


class MismatchOut(BaseModel):
    trade_id: str
    differences: list[FieldDifferenceOut] = Field(description="Only the fields that differ.")


class ReconciliationSummary(BaseModel):
    """Counts of each bucket."""

    statement_trades: int = Field(description="Trades on the venue's statement.")
    recorded_trades: int = Field(description="Our trades for this venue and period.")
    matched: int = Field(description="Same on both sides.")
    missing: int = Field(description="On the statement, not in our records.")
    extra: int = Field(description="In our records, not on the statement.")
    mismatched: int = Field(description="On both sides, with different values.")


class ReconciliationReport(BaseModel):
    venue: str
    is_clean: bool = Field(description="`true` when there is nothing missing, extra or mismatched.")
    summary: ReconciliationSummary
    missing: list[StatementTradeOut] = Field(
        description="On the venue statement but not in our records."
    )
    extra: list[StatementTradeOut] = Field(
        description="In our records but not on the venue statement."
    )
    mismatched: list[MismatchOut] = Field(
        description="Present on both sides with different field values."
    )
