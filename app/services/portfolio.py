from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, localcontext

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Position, Price
from app.domain.cost_basis import AverageCostPosition
from app.domain.money import MONEY_CONTEXT, ZERO, quantize
from app.domain.types import quote_currency
from app.services.errors import NotFoundError


@dataclass(frozen=True, slots=True)
class SymbolPnlView:
    symbol: str
    quote_currency: str | None
    quantity: Decimal
    avg_cost: Decimal
    cost_basis: Decimal
    realized_pnl: Decimal
    mark_price: Decimal | None
    market_value: Decimal | None
    unrealized_pnl: Decimal | None
    total_pnl: Decimal | None


@dataclass(frozen=True, slots=True)
class CurrencyTotalsView:
    quote_currency: str | None
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    symbols_without_price: list[str]


@dataclass(frozen=True, slots=True)
class PnlView:
    as_of: datetime
    positions: list[SymbolPnlView]
    totals: list[CurrencyTotalsView]


def _symbol_pnl(symbol: str, position: AverageCostPosition, mark: Decimal | None) -> SymbolPnlView:
    unrealized = market_value = total = None
    if mark is not None:
        unrealized = position.unrealized_pnl(mark)
        with localcontext(MONEY_CONTEXT):
            market_value = quantize(mark * position.quantity)
            total = position.realized_pnl + unrealized
    return SymbolPnlView(
        symbol=symbol,
        quote_currency=quote_currency(symbol),
        quantity=position.quantity,
        avg_cost=position.avg_cost,
        cost_basis=position.cost_basis,
        realized_pnl=position.realized_pnl,
        mark_price=mark,
        market_value=market_value,
        unrealized_pnl=unrealized,
        total_pnl=total,
    )


def _totals(rows: list[SymbolPnlView]) -> list[CurrencyTotalsView]:
    groups: dict[str | None, list[SymbolPnlView]] = defaultdict(list)
    for row in rows:
        groups[row.quote_currency].append(row)

    totals = []
    for currency, members in sorted(groups.items(), key=lambda item: item[0] or ""):
        realized = sum((m.realized_pnl for m in members), ZERO)
        unrealized = sum((m.unrealized_pnl for m in members if m.unrealized_pnl is not None), ZERO)
        totals.append(
            CurrencyTotalsView(
                quote_currency=currency,
                realized_pnl=realized,
                unrealized_pnl=unrealized,
                total_pnl=realized + unrealized,
                # Open positions with no mark are called out rather than silently valued at 0.
                symbols_without_price=[
                    m.symbol for m in members if m.mark_price is None and m.quantity > 0
                ],
            )
        )
    return totals


class PortfolioService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_positions(self) -> list[Position]:
        return list(await self._session.scalars(select(Position).order_by(Position.symbol)))

    async def get_position(self, symbol: str) -> Position:
        position = await self._session.get(Position, symbol)
        if position is None:
            raise NotFoundError(f"No position for {symbol}")
        return position

    async def set_price(self, symbol: str, price: Decimal) -> Price:
        stmt = (
            pg_insert(Price)
            .values(symbol=symbol, price=price)
            .on_conflict_do_update(
                index_elements=[Price.symbol],
                set_={"price": price, "updated_at": datetime.now(UTC)},
            )
            .returning(Price)
            .execution_options(populate_existing=True)
        )
        async with self._session.begin():
            return (await self._session.scalars(stmt)).one()

    async def pnl(self, symbol: str | None = None) -> PnlView:
        position_stmt = select(Position).where(Position.trade_count > 0).order_by(Position.symbol)
        price_stmt = select(Price.symbol, Price.price)
        if symbol:
            position_stmt = position_stmt.where(Position.symbol == symbol)
            price_stmt = price_stmt.where(Price.symbol == symbol)
        marks = {sym: price for sym, price in await self._session.execute(price_stmt)}

        rows = [
            _symbol_pnl(
                p.symbol,
                AverageCostPosition(p.quantity, p.cost_basis, p.realized_pnl),
                marks.get(p.symbol),
            )
            for p in await self._session.scalars(position_stmt)
        ]
        return PnlView(as_of=datetime.now(UTC), positions=rows, totals=_totals(rows))
