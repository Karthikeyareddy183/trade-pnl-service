from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.deps import PortfolioServiceDep
from app.db.models import Position
from app.domain.cost_basis import AverageCostPosition
from app.schemas.common import ErrorResponse, Symbol
from app.schemas.portfolio import (
    CurrencyTotals,
    PnlReport,
    PositionOut,
    PriceIn,
    PriceOut,
    SymbolPnl,
)

router = APIRouter(tags=["portfolio"])

SymbolPath = Annotated[
    Symbol, Path(description="What was traded, `BASE-QUOTE`.", examples=["BTC-USD"])
]


def _position_out(position: Position) -> PositionOut:
    return PositionOut(
        symbol=position.symbol,
        quantity=position.quantity,
        avg_cost=AverageCostPosition(position.quantity, position.cost_basis).avg_cost,
        cost_basis=position.cost_basis,
        realized_pnl=position.realized_pnl,
        trade_count=position.trade_count,
        updated_at=position.updated_at,
    )


@router.get("/positions", response_model=list[PositionOut], summary="List what you hold")
async def list_positions(service: PortfolioServiceDep) -> list[PositionOut]:
    """One entry per symbol that has at least one trade, summed across all venues.
    Uses the average cost method. For profit/loss at the latest price, use `GET /pnl`."""
    return [_position_out(p) for p in await service.list_positions() if p.trade_count > 0]


@router.get(
    "/positions/{symbol}",
    response_model=PositionOut,
    responses={404: {"model": ErrorResponse, "description": "No trades for this symbol yet."}},
    summary="Get what you hold of one symbol",
)
async def get_position(symbol: SymbolPath, service: PortfolioServiceDep) -> PositionOut:
    """Quantity, average cost and realized profit/loss for one symbol (average cost method)."""
    return _position_out(await service.get_position(symbol))


@router.put(
    "/prices/{symbol}",
    response_model=PriceOut,
    responses={422: {"model": ErrorResponse, "description": "The price is invalid."}},
    summary="Set the latest price of a symbol",
)
async def set_price(symbol: SymbolPath, body: PriceIn, service: PortfolioServiceDep) -> PriceOut:
    """Store the current market price. `GET /pnl` uses it to value what you still hold
    (unrealized PnL). Setting it again replaces the previous price."""
    price = await service.set_price(symbol, body.price)
    return PriceOut(symbol=price.symbol, price=price.price, updated_at=price.updated_at)


@router.get("/pnl", response_model=PnlReport, summary="Profit and loss report")
async def get_pnl(
    service: PortfolioServiceDep,
    symbol: Annotated[
        Symbol | None,
        Query(description="Only this symbol. Leave empty for all.", examples=["BTC-USD"]),
    ] = None,
) -> PnlReport:
    """Per symbol, using the average cost method: **realized** PnL (locked in by selling)
    and **unrealized** PnL (on what you still hold, at the price set with
    `PUT /prices/{symbol}`).

    * If no price is set for a symbol, its unrealized PnL is `null` and the symbol is listed
      in `totals[].symbols_without_price`.
    * `totals` adds symbols up per quote currency (USD separately from BTC, and so on).
    """
    view = await service.pnl(symbol)
    return PnlReport(
        as_of=view.as_of,
        positions=[SymbolPnl.model_validate(row, from_attributes=True) for row in view.positions],
        totals=[CurrencyTotals.model_validate(t, from_attributes=True) for t in view.totals],
    )
