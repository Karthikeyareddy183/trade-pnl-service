from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.errors import DuplicateStatementEntryError
from app.domain.reconciliation import reconcile
from app.domain.types import Side, TradeRecord

T0 = datetime(2026, 10, 29, 10, 0, tzinfo=UTC)


def trade(trade_id: str, qty: str, px: str, **overrides: object) -> TradeRecord:
    fields: dict[str, object] = {
        "trade_id": trade_id,
        "symbol": "BTC-USD",
        "side": Side.BUY,
        "quantity": Decimal(qty),
        "price": Decimal(px),
        "executed_at": T0,
    }
    fields.update(overrides)
    return TradeRecord(**fields)  # type: ignore[arg-type]


def test_worked_example_from_requirements() -> None:
    recorded = [trade("T1", "10", "100"), trade("T2", "5", "101")]
    statement = [trade("T1", "10", "100"), trade("T2", "6", "101"), trade("T3", "1", "99")]

    result = reconcile(recorded, statement)

    assert result.matched == ("T1",)
    assert [t.trade_id for t in result.missing] == ["T3"]
    assert result.extra == ()
    assert len(result.mismatched) == 1
    mismatch = result.mismatched[0]
    assert mismatch.trade_id == "T2"
    assert [(d.field, d.recorded, d.statement) for d in mismatch.differences] == [
        ("quantity", Decimal("5"), Decimal("6"))
    ]
    assert not result.is_clean


def test_extra_trades_are_ones_the_venue_does_not_know_about() -> None:
    result = reconcile([trade("T1", "1", "1"), trade("T9", "1", "1")], [trade("T1", "1", "1")])
    assert [t.trade_id for t in result.extra] == ["T9"]


def test_formatting_differences_are_not_breaks() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    recorded = [trade("T1", "10", "100")]
    statement = [trade("T1", "10.000", "100.00", executed_at=T0.astimezone(ist))]

    assert reconcile(recorded, statement).is_clean


def test_every_differing_field_is_reported() -> None:
    recorded = [trade("T1", "10", "100")]
    statement = [trade("T1", "10", "100.5", side=Side.SELL, executed_at=T0 + timedelta(seconds=1))]

    (mismatch,) = reconcile(recorded, statement).mismatched
    assert [d.field for d in mismatch.differences] == ["side", "price", "executed_at"]


def test_empty_statement_reports_everything_as_extra() -> None:
    result = reconcile([trade("T1", "1", "1")], [])
    assert len(result.extra) == 1
    assert result.missing == result.mismatched == ()


def test_duplicate_trade_ids_in_statement_are_rejected() -> None:
    with pytest.raises(DuplicateStatementEntryError) as exc_info:
        reconcile([], [trade("T1", "1", "1"), trade("T1", "2", "1")])
    assert exc_info.value.trade_ids == ["T1"]
