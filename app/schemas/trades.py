from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.types import Fill, Side
from app.schemas.common import DecimalStr, PositiveAmount, Symbol, TradeId, UtcDatetime, Venue


class TradeIn(BaseModel):
    """A trade as reported by a venue."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "venue": "binance",
                    "trade_id": "T1",
                    "symbol": "BTC-USD",
                    "side": "BUY",
                    "quantity": "10",
                    "price": "100",
                    "timestamp": "2026-10-29T10:00:00Z",
                }
            ]
        },
    )

    venue: Venue = Field(
        description="Exchange the trade happened on. Stored in lowercase.", examples=["binance"]
    )
    trade_id: TradeId = Field(
        description="The venue's id for this trade. `venue` + `trade_id` identify a trade, "
        "so resending it is safe.",
        examples=["T1"],
    )
    symbol: Symbol = Field(
        description="What was traded, `BASE-QUOTE`. Stored in uppercase.", examples=["BTC-USD"]
    )
    side: Side = Field(description="`BUY` or `SELL`.")
    quantity: PositiveAmount = Field(
        description="How much was traded, as a string. Must be > 0.", examples=["10"]
    )
    price: PositiveAmount = Field(
        description="Price per unit in the quote currency, as a string. Must be > 0.",
        examples=["100"],
    )
    timestamp: UtcDatetime = Field(
        description="When the trade happened at the venue. Must include a timezone.",
        examples=["2026-10-29T10:00:00Z"],
    )

    def to_fill(self) -> Fill:
        return Fill(side=self.side, quantity=self.quantity, price=self.price)


class TradeOut(BaseModel):
    """A recorded trade."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Arrival number assigned by this service (1, 2, 3...).")
    venue: str
    trade_id: str
    symbol: str
    side: Side
    quantity: DecimalStr
    price: DecimalStr
    timestamp: datetime = Field(
        validation_alias="executed_at", description="When the trade happened, in UTC."
    )
    ingested_at: datetime = Field(description="When this service received it, in UTC.")


class TradeIngestResult(BaseModel):
    trade: TradeOut = Field(description="The trade as stored.")
    duplicate: bool = Field(
        description="`true` if this exact trade was already recorded, so nothing changed."
    )


class TradeList(BaseModel):
    items: list[TradeOut] = Field(description="Trades, oldest first.")
    next_after_id: int | None = Field(
        description="Pass as `after_id` to get the next page. `null` means this is the last page."
    )
