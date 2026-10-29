from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status

from app.api.deps import TradeServiceDep
from app.schemas.common import ErrorResponse, Symbol, Venue
from app.schemas.trades import TradeIn, TradeIngestResult, TradeList, TradeOut

router = APIRouter(prefix="/trades", tags=["trades"])


@router.post(
    "",
    response_model=TradeIngestResult,
    status_code=status.HTTP_201_CREATED,
    summary="Record a trade",
    response_description="The trade was new and has been recorded.",
    responses={
        200: {
            "model": TradeIngestResult,
            "description": "This exact trade was already recorded. Nothing changed.",
        },
        409: {
            "model": ErrorResponse,
            "description": "A trade with this `venue` + `trade_id` exists with different data.",
        },
        422: {
            "model": ErrorResponse,
            "description": "The trade is invalid, or it is a SELL larger than the position.",
        },
    },
)
async def ingest_trade(
    trade: TradeIn, service: TradeServiceDep, response: Response
) -> TradeIngestResult:
    """Save one trade and update the position for its symbol.

    * **New trade** → `201`. The position changes.
    * **Same trade sent again** (same `venue` + `trade_id`, same data) → `200` with
      `duplicate: true`. Nothing changes, so retries are safe.
    * **Same `venue` + `trade_id`, different data** → `409`. Recorded trades are never
      overwritten.
    * **SELL larger than what you hold** → `422 INSUFFICIENT_POSITION`. Nothing is saved,
      so you can send the same `trade_id` again later.
    """
    outcome = await service.ingest(trade)
    if outcome.duplicate:
        response.status_code = status.HTTP_200_OK
    return TradeIngestResult(
        trade=TradeOut.model_validate(outcome.trade), duplicate=outcome.duplicate
    )


@router.get(
    "",
    response_model=TradeList,
    summary="List recorded trades",
    response_description="One page of trades, oldest first.",
)
async def list_trades(
    service: TradeServiceDep,
    venue: Annotated[
        Venue | None, Query(description="Only trades from this venue.", examples=["binance"])
    ] = None,
    symbol: Annotated[
        Symbol | None, Query(description="Only trades of this symbol.", examples=["BTC-USD"])
    ] = None,
    after_id: Annotated[
        int | None,
        Query(
            ge=0,
            description="For the next page: pass `next_after_id` from the previous response.",
        ),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Page size (1 to 1000).")] = 100,
) -> TradeList:
    """Trades in the order they were received. Filters are optional and can be combined.

    To page through everything, call again with `after_id` set to the `next_after_id` of
    the previous response, until `next_after_id` is `null`.
    """
    trades = await service.list_trades(venue=venue, symbol=symbol, after_id=after_id, limit=limit)
    return TradeList(
        items=[TradeOut.model_validate(t) for t in trades],
        next_after_id=trades[-1].id if len(trades) == limit else None,
    )


@router.get(
    "/{venue}/{trade_id}",
    response_model=TradeOut,
    responses={404: {"model": ErrorResponse, "description": "No such trade."}},
    summary="Get one trade",
)
async def get_trade(
    venue: Annotated[Venue, Path(description="Venue the trade came from.", examples=["binance"])],
    trade_id: Annotated[str, Path(description="The venue's id for the trade.", examples=["T1"])],
    service: TradeServiceDep,
) -> TradeOut:
    """Look up a trade by `venue` + `trade_id`, the same pair that identifies it on
    `POST /trades`."""
    return TradeOut.model_validate(await service.get(venue, trade_id))
