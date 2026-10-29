import random
from decimal import Context, Decimal, localcontext

import pytest

from app.domain.cost_basis import AverageCostPosition, replay
from app.domain.errors import OversellError
from app.domain.types import Fill, Side

D = Decimal


def buy(qty: str, px: str) -> Fill:
    return Fill(Side.BUY, D(qty), D(px))


def sell(qty: str, px: str) -> Fill:
    return Fill(Side.SELL, D(qty), D(px))


# BUY 10 @ 100, BUY 10 @ 110, SELL 5 @ 120, latest price 125 (from the requirements).
WORKED_EXAMPLE = [buy("10", "100"), buy("10", "110"), sell("5", "120")]
MARK = D("125")


def test_worked_example() -> None:
    position = replay(WORKED_EXAMPLE)

    assert position.quantity == D("15")
    assert position.avg_cost == D("105")
    assert position.realized_pnl == D("75")
    assert position.unrealized_pnl(MARK) == D("300")


class TestOversell:
    def test_sell_more_than_held_is_rejected_and_position_unchanged(self) -> None:
        position = replay([buy("10", "100")])

        with pytest.raises(OversellError) as exc_info:
            position.apply(sell("15", "120"))

        assert exc_info.value.available == D("10")
        assert exc_info.value.requested == D("15")
        assert position.quantity == D("10")  # immutable: the original is untouched

    def test_sell_from_flat_is_rejected(self) -> None:
        with pytest.raises(OversellError):
            replay([sell("1", "100")])

    def test_selling_exactly_the_position_is_allowed(self) -> None:
        position = replay([buy("10", "100"), sell("10", "90")])

        assert position.quantity == 0
        assert position.cost_basis == 0
        assert position.avg_cost == 0
        assert position.realized_pnl == D("-100")


class TestAverageCost:
    def test_avg_cost_unchanged_by_sells(self) -> None:
        position = replay([buy("3", "100"), buy("3", "200"), sell("1", "500")])
        assert position.avg_cost == D("150")
        assert position.realized_pnl == D("350")

    def test_round_trip_to_flat_leaves_no_rounding_dust(self) -> None:
        # 1/3 splits produce repeating decimals; closing the position must still zero out.
        fills = [buy("3", "10"), buy("3", "11"), buy("3", "13")]
        fills += [sell("1", "12")] * 9
        position = replay(fills)

        assert position.quantity == 0
        assert position.cost_basis == 0
        assert position.realized_pnl == D("108") - D("102")

    def test_reopening_after_flat_starts_a_fresh_average(self) -> None:
        position = replay([buy("1", "100"), sell("1", "150"), buy("2", "10")])
        assert position.avg_cost == D("10")
        assert position.realized_pnl == D("50")

    def test_high_precision_values_are_not_rounded_to_28_digits(self) -> None:
        # Python's default context (28 significant digits) would round this product.
        qty = D("12345678.123456789012345678")
        px = D("98765.123456789012345678")
        position = AverageCostPosition().apply(Fill(Side.BUY, qty, px))

        with localcontext(prec=100):
            exact = qty * px
        assert exact != qty * px  # the default context really would have rounded
        assert position.cost_basis == exact.quantize(D("1e-18"), context=Context(prec=100))


@pytest.mark.parametrize("seed", range(25))
def test_random_sequences_keep_invariants(seed: int) -> None:
    """Whatever the sequence: the position never goes negative, and total PnL
    (realized + unrealized) always equals the cash view:
    value of what is held + money received from sells - money paid for buys."""
    rng = random.Random(seed)
    position = AverageCostPosition()
    paid = received = D(0)
    for _ in range(60):
        price = D(rng.randint(1, 100_000)) / 100
        if position.quantity > 0 and rng.random() < 0.45:
            qty = (position.quantity * D(rng.randint(1, 100)) / 100).quantize(D("0.0001"))
            if qty == 0:
                continue
            fill = Fill(Side.SELL, qty, price)
            received += qty * price
        else:
            fill = Fill(Side.BUY, D(rng.randint(1, 10_000)) / 1000, price)
            paid += fill.quantity * price
        position = position.apply(fill)

        assert position.quantity >= 0
        mark = D(rng.randint(1, 100_000)) / 100
        total_pnl = position.realized_pnl + position.unrealized_pnl(mark)
        cash_view = mark * position.quantity + received - paid
        assert abs(total_pnl - cash_view) <= D("1e-15")
