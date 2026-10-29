import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Position, Trade
from app.domain.cost_basis import AverageCostPosition
from app.domain.errors import OversellError
from app.domain.money import ZERO, format_decimal
from app.domain.reconciliation import compare_trades
from app.domain.types import Side, TradeRecord
from app.schemas.trades import TradeIn
from app.services.errors import NotFoundError, TradeConflictError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IngestOutcome:
    trade: Trade
    duplicate: bool


def trade_to_record(trade: Trade) -> TradeRecord:
    return TradeRecord(
        trade_id=trade.trade_id,
        symbol=trade.symbol,
        side=Side(trade.side),
        quantity=trade.quantity,
        price=trade.price,
        executed_at=trade.executed_at,
    )


def _incoming_record(trade: TradeIn) -> TradeRecord:
    return TradeRecord(
        trade_id=trade.trade_id,
        symbol=trade.symbol,
        side=trade.side,
        quantity=trade.quantity,
        price=trade.price,
        executed_at=trade.timestamp,
    )


def _render(value: object) -> str:
    if isinstance(value, Decimal):
        return format_decimal(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class TradeService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ingest(self, incoming: TradeIn) -> IngestOutcome:
        """Record a trade and update its position atomically.

        One transaction, in this order:

        1. Lock the symbol's position row (``SELECT ... FOR UPDATE``). Every write to a
           symbol is serialised behind this lock, which is what makes the oversell check
           safe under concurrency. Different symbols never block each other.
        2. ``INSERT ... ON CONFLICT (venue, trade_id) DO NOTHING``. The unique index is
           the idempotency guarantee, so two identical requests arriving at the same
           instant still produce exactly one row.
        3. Apply the fill to the position. An oversell raises, and the whole transaction,
           including the trade insert, rolls back: neither the ledger nor the position
           changes.
        """
        async with self._session.begin():
            position = await self._lock_position(incoming.symbol)

            trade = await self._insert_if_new(incoming)
            if trade is None:
                return await self._replay_duplicate(incoming)

            current = AverageCostPosition(
                quantity=position.quantity,
                cost_basis=position.cost_basis,
                realized_pnl=position.realized_pnl,
            )
            try:
                updated = current.apply(incoming.to_fill())
            except OversellError as exc:
                logger.warning(
                    "oversell rejected venue=%s trade_id=%s symbol=%s available=%s requested=%s",
                    incoming.venue,
                    incoming.trade_id,
                    incoming.symbol,
                    exc.available,
                    exc.requested,
                )
                raise OversellError(
                    available=exc.available, requested=exc.requested, symbol=incoming.symbol
                ) from None

            position.quantity = updated.quantity
            position.cost_basis = updated.cost_basis
            position.realized_pnl = updated.realized_pnl
            position.trade_count += 1
            logger.info(
                "trade recorded id=%s venue=%s trade_id=%s symbol=%s side=%s qty=%s px=%s",
                trade.id,
                trade.venue,
                trade.trade_id,
                trade.symbol,
                trade.side,
                trade.quantity,
                trade.price,
            )
            return IngestOutcome(trade=trade, duplicate=False)

    async def _lock_position(self, symbol: str) -> Position:
        # Make sure a row exists to lock. If two transactions race to create it, the loser's
        # ON CONFLICT waits for the winner to commit and then does nothing.
        await self._session.execute(
            pg_insert(Position)
            .values(symbol=symbol, quantity=ZERO, cost_basis=ZERO, realized_pnl=ZERO, trade_count=0)
            .on_conflict_do_nothing(index_elements=[Position.symbol])
        )
        return (
            await self._session.scalars(
                select(Position)
                .where(Position.symbol == symbol)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).one()

    async def _insert_if_new(self, incoming: TradeIn) -> Trade | None:
        stmt = (
            pg_insert(Trade)
            .values(
                venue=incoming.venue,
                trade_id=incoming.trade_id,
                symbol=incoming.symbol,
                side=incoming.side.value,
                quantity=incoming.quantity,
                price=incoming.price,
                executed_at=incoming.timestamp,
            )
            .on_conflict_do_nothing(constraint="uq_trades_venue_trade_id")
            .returning(Trade)
        )
        return (await self._session.scalars(stmt)).one_or_none()

    async def _replay_duplicate(self, incoming: TradeIn) -> IngestOutcome:
        existing = await self.get(incoming.venue, incoming.trade_id)
        differences = compare_trades(trade_to_record(existing), _incoming_record(incoming))
        if differences:
            raise TradeConflictError(
                incoming.venue,
                incoming.trade_id,
                {
                    d.field: {"recorded": _render(d.recorded), "received": _render(d.statement)}
                    for d in differences
                },
            )
        logger.info(
            "duplicate trade ignored venue=%s trade_id=%s", incoming.venue, incoming.trade_id
        )
        return IngestOutcome(trade=existing, duplicate=True)

    async def get(self, venue: str, trade_id: str) -> Trade:
        trade = await self._session.scalar(
            select(Trade).where(Trade.venue == venue, Trade.trade_id == trade_id)
        )
        if trade is None:
            raise NotFoundError(f"Trade {venue}/{trade_id} not found")
        return trade

    async def list_trades(
        self,
        *,
        venue: str | None = None,
        symbol: str | None = None,
        after_id: int | None = None,
        limit: int = 100,
    ) -> list[Trade]:
        stmt = select(Trade).order_by(Trade.id).limit(limit)
        if venue:
            stmt = stmt.where(Trade.venue == venue)
        if symbol:
            stmt = stmt.where(Trade.symbol == symbol)
        if after_id is not None:
            stmt = stmt.where(Trade.id > after_id)
        return list(await self._session.scalars(stmt))
