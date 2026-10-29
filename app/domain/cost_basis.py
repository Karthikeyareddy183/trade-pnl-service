"""Position and PnL maths using the average cost method.

``AverageCostPosition`` is an immutable value object: ``apply`` returns a new position and
raises ``OversellError`` instead of ever producing a negative quantity.

* BUY: quantity and cost basis grow; the average price moves.
* SELL: realized PnL = sell proceeds - the average cost of what was sold; the average
  price does not change.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, localcontext

from app.domain.errors import OversellError
from app.domain.money import MONEY_CONTEXT, ZERO, quantize
from app.domain.types import Fill, Side


@dataclass(frozen=True, slots=True)
class AverageCostPosition:
    quantity: Decimal = ZERO
    cost_basis: Decimal = ZERO
    realized_pnl: Decimal = ZERO

    @property
    def avg_cost(self) -> Decimal:
        if self.quantity.is_zero():
            return ZERO
        with localcontext(MONEY_CONTEXT):
            return quantize(self.cost_basis / self.quantity)

    def apply(self, fill: Fill) -> "AverageCostPosition":
        with localcontext(MONEY_CONTEXT):
            if fill.side is Side.BUY:
                return AverageCostPosition(
                    quantity=self.quantity + fill.quantity,
                    cost_basis=quantize(self.cost_basis + fill.quantity * fill.price),
                    realized_pnl=self.realized_pnl,
                )

            if fill.quantity > self.quantity:
                raise OversellError(available=self.quantity, requested=fill.quantity)
            remaining = self.quantity - fill.quantity
            # Release cost pro rata. Closing the whole position releases the entire cost
            # basis, so no rounding residue survives a round trip to flat.
            released = (
                self.cost_basis
                if remaining.is_zero()
                else quantize(self.cost_basis * fill.quantity / self.quantity)
            )
            return AverageCostPosition(
                quantity=remaining,
                cost_basis=self.cost_basis - released,
                realized_pnl=quantize(self.realized_pnl + fill.quantity * fill.price - released),
            )

    def unrealized_pnl(self, mark_price: Decimal) -> Decimal:
        # Market value minus what the open quantity cost. Using the total cost basis rather
        # than ``(mark - avg_cost) * quantity`` avoids re-introducing the rounding of avg_cost.
        with localcontext(MONEY_CONTEXT):
            return quantize(mark_price * self.quantity - self.cost_basis)


def replay(fills: Iterable[Fill]) -> AverageCostPosition:
    """Rebuild a position from scratch by applying fills in order."""
    position = AverageCostPosition()
    for fill in fills:
        position = position.apply(fill)
    return position
