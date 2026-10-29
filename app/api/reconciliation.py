from typing import Annotated

from fastapi import APIRouter, Path

from app.api.deps import ReconciliationServiceDep
from app.domain.reconciliation import Mismatch
from app.schemas.common import ErrorResponse, Venue
from app.schemas.reconciliation import (
    FieldDifferenceOut,
    MismatchOut,
    ReconciliationReport,
    ReconciliationSummary,
    StatementIn,
    StatementTradeOut,
)

router = APIRouter(prefix="/reconciliations", tags=["reconciliation"])


def _mismatch_out(mismatch: Mismatch) -> MismatchOut:
    return MismatchOut(
        trade_id=mismatch.trade_id,
        differences=[
            FieldDifferenceOut(
                field="timestamp" if d.field == "executed_at" else d.field,
                recorded=d.recorded,
                statement=d.statement,
            )
            for d in mismatch.differences
        ],
    )


@router.post(
    "/{venue}",
    response_model=ReconciliationReport,
    responses={
        422: {
            "model": ErrorResponse,
            "description": "The statement is invalid or lists the same `trade_id` twice.",
        }
    },
    summary="Compare a venue's statement with our records",
)
async def reconcile_venue(
    venue: Annotated[
        Venue, Path(description="The venue that sent the statement.", examples=["binance"])
    ],
    statement: StatementIn,
    service: ReconciliationServiceDep,
) -> ReconciliationReport:
    """Send the list of trades the venue says happened. Trades are matched by `trade_id`
    and each one ends up in one bucket:

    * **matched**: same on both sides.
    * **missing**: on the statement, but we never recorded it.
    * **extra**: we recorded it, but it is not on the statement.
    * **mismatched**: on both sides with different values; each differing field is listed.

    This only reports. It never changes stored trades or positions.

    Use `period_start` / `period_end` when the statement covers a limited time window, so
    our older or newer trades are not reported as `extra`.
    """
    result, recorded_count = await service.reconcile_venue(
        venue,
        [t.to_record() for t in statement.trades],
        statement.period_start,
        statement.period_end,
    )
    return ReconciliationReport(
        venue=venue,
        is_clean=result.is_clean,
        summary=ReconciliationSummary(
            statement_trades=len(statement.trades),
            recorded_trades=recorded_count,
            matched=len(result.matched),
            missing=len(result.missing),
            extra=len(result.extra),
            mismatched=len(result.mismatched),
        ),
        missing=[StatementTradeOut.from_record(t) for t in result.missing],
        extra=[StatementTradeOut.from_record(t) for t in result.extra],
        mismatched=[_mismatch_out(m) for m in result.mismatched],
    )
