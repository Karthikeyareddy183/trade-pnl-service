from typing import Any

from app.domain.errors import DomainError


class TradeConflictError(DomainError):
    """The (venue, trade_id) is already recorded with different data.

    A true retry carries identical data and is answered idempotently. Different data under
    the same id means either a venue correction or an upstream bug; silently keeping one
    version would hide it, so the caller is told explicitly.
    """

    code = "IDEMPOTENCY_CONFLICT"

    def __init__(self, venue: str, trade_id: str, differences: dict[str, dict[str, str]]):
        self.venue = venue
        self.trade_id = trade_id
        self.differences = differences
        super().__init__(
            f"Trade {venue}/{trade_id} is already recorded with different "
            f"{', '.join(differences)}. Recorded trades are immutable."
        )

    def details(self) -> dict[str, Any]:
        return {"venue": self.venue, "trade_id": self.trade_id, "differences": self.differences}


class NotFoundError(DomainError):
    code = "NOT_FOUND"
