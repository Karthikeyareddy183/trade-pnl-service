from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import DecimalStr, PositiveAmount


class PriceIn(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"price": "125"}]})

    price: PositiveAmount = Field(
        description="Current market price per unit, as a string. Must be > 0.", examples=["125"]
    )


class PriceOut(BaseModel):
    symbol: str
    price: DecimalStr = Field(description="The stored latest price.")
    updated_at: datetime = Field(description="When the price was last set, in UTC.")


class PositionOut(BaseModel):
    """What you hold of one symbol, across all venues (average cost method)."""

    symbol: str
    quantity: DecimalStr = Field(description="How much you hold now.")
    avg_cost: DecimalStr = Field(description="Average price paid per unit: cost_basis / quantity.")
    cost_basis: DecimalStr = Field(description="Total money paid for the quantity you hold.")
    realized_pnl: DecimalStr = Field(description="Profit or loss locked in by selling so far.")
    trade_count: int = Field(description="Number of trades recorded for this symbol.")
    updated_at: datetime = Field(description="When the position last changed, in UTC.")


class SymbolPnl(BaseModel):
    """Profit and loss for one symbol."""

    symbol: str
    quote_currency: str | None = Field(
        description="Currency the PnL is in: `USD` for `BTC-USD`. `null` if the symbol has "
        "no `-`, `/` or `_` separator."
    )
    quantity: DecimalStr = Field(description="How much you hold now.")
    avg_cost: DecimalStr = Field(description="Average price paid per unit you still hold.")
    cost_basis: DecimalStr = Field(description="Total money paid for the quantity you hold.")
    realized_pnl: DecimalStr = Field(description="Profit or loss locked in by selling.")
    mark_price: DecimalStr | None = Field(
        description="Latest price from `PUT /prices/{symbol}`. `null` if never set."
    )
    market_value: DecimalStr | None = Field(
        description="What you hold is worth now: quantity * mark_price."
    )
    unrealized_pnl: DecimalStr | None = Field(
        description="Profit or loss on what you still hold: market_value - cost_basis. "
        "`null` if no price is set."
    )
    total_pnl: DecimalStr | None = Field(
        description="realized_pnl + unrealized_pnl. `null` if no price is set."
    )


class CurrencyTotals(BaseModel):
    """All symbols with the same quote currency, added up."""

    quote_currency: str | None
    realized_pnl: DecimalStr
    unrealized_pnl: DecimalStr = Field(
        description="Sum over symbols that have a price. Symbols without one are not counted."
    )
    total_pnl: DecimalStr
    symbols_without_price: list[str] = Field(
        description="Symbols you still hold but have no price for, so their unrealized PnL "
        "is missing from this total."
    )


class PnlReport(BaseModel):
    as_of: datetime = Field(description="When the report was calculated, in UTC.")
    positions: list[SymbolPnl] = Field(description="One entry per symbol.")
    totals: list[CurrencyTotals] = Field(
        description="Added up per quote currency. USD and BTC amounts are never added together."
    )
