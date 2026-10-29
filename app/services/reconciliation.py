from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Trade
from app.domain.reconciliation import ReconciliationResult, reconcile
from app.domain.types import TradeRecord
from app.services.trades import trade_to_record


class ReconciliationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reconcile_venue(
        self,
        venue: str,
        statement: list[TradeRecord],
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> tuple[ReconciliationResult, int]:
        """Returns the result and the number of stored trades it was compared against."""
        stmt = select(Trade).where(Trade.venue == venue).order_by(Trade.id)
        if period_start is not None:
            stmt = stmt.where(Trade.executed_at >= period_start)
        if period_end is not None:
            stmt = stmt.where(Trade.executed_at < period_end)
        recorded = [trade_to_record(t) for t in await self._session.scalars(stmt)]
        return reconcile(recorded, statement), len(recorded)
