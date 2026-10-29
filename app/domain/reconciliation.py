"""Compare our ledger for one venue against that venue's statement.

Trades are matched on ``trade_id`` (unique within a venue) and then compared field by
field. The result is a report only: breaks are surfaced for a human to resolve and are
never auto-corrected, because the venue is not always the side that is wrong.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.domain.errors import DuplicateStatementEntryError
from app.domain.types import TradeRecord

RECONCILED_FIELDS = ("symbol", "side", "quantity", "price", "executed_at")


@dataclass(frozen=True, slots=True)
class FieldDifference:
    field: str
    recorded: Any
    statement: Any


@dataclass(frozen=True, slots=True)
class Mismatch:
    trade_id: str
    differences: tuple[FieldDifference, ...]
    recorded: TradeRecord
    statement: TradeRecord


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    matched: tuple[str, ...]
    missing: tuple[TradeRecord, ...]  # on the statement, not in our records
    extra: tuple[TradeRecord, ...]  # in our records, not on the statement
    mismatched: tuple[Mismatch, ...]

    @property
    def is_clean(self) -> bool:
        return not (self.missing or self.extra or self.mismatched)


def compare_trades(recorded: TradeRecord, statement: TradeRecord) -> tuple[FieldDifference, ...]:
    """Fields on which two versions of the same trade disagree (empty when identical)."""
    # Decimal equality is numeric (Decimal("100") == Decimal("100.00")) and aware
    # datetimes compare as instants, so formatting differences are not reported as breaks.
    return tuple(
        FieldDifference(name, getattr(recorded, name), getattr(statement, name))
        for name in RECONCILED_FIELDS
        if getattr(recorded, name) != getattr(statement, name)
    )


def reconcile(
    recorded: Iterable[TradeRecord], statement: Iterable[TradeRecord]
) -> ReconciliationResult:
    statement = list(statement)
    duplicates = sorted(tid for tid, n in Counter(t.trade_id for t in statement).items() if n > 1)
    if duplicates:
        raise DuplicateStatementEntryError(duplicates)

    ours = {trade.trade_id: trade for trade in recorded}
    theirs = {trade.trade_id: trade for trade in statement}

    matched: list[str] = []
    missing: list[TradeRecord] = []
    mismatched: list[Mismatch] = []
    for trade in statement:
        stored = ours.get(trade.trade_id)
        if stored is None:
            missing.append(trade)
        elif diffs := compare_trades(stored, trade):
            mismatched.append(Mismatch(trade.trade_id, diffs, stored, trade))
        else:
            matched.append(trade.trade_id)

    extra = [trade for trade_id, trade in ours.items() if trade_id not in theirs]

    return ReconciliationResult(
        matched=tuple(matched),
        missing=tuple(missing),
        extra=tuple(extra),
        mismatched=tuple(mismatched),
    )
