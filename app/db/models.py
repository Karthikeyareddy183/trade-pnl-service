"""SQLAlchemy ORM models.

Money and quantities are ``NUMERIC(38, 18)``: 20 integer digits and 18 fractional digits,
enough for crypto base units (wei-level precision) without ever touching binary floats.
Invariants that must hold no matter which code path writes are enforced by CHECK
constraints as well as in the application, so the database is the last line of defence.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

MONEY = Numeric(38, 18)


class Base(DeclarativeBase):
    pass


class Trade(Base):
    """Append-only trade ledger: the source of truth. Positions are derived from it."""

    __tablename__ = "trades"
    __table_args__ = (
        UniqueConstraint("venue", "trade_id", name="uq_trades_venue_trade_id"),
        CheckConstraint("side IN ('BUY', 'SELL')", name="ck_trades_side"),
        CheckConstraint("quantity > 0", name="ck_trades_quantity_positive"),
        CheckConstraint("price > 0", name="ck_trades_price_positive"),
        Index("ix_trades_symbol_id", "symbol", "id"),
        Index("ix_trades_venue_executed_at", "venue", "executed_at"),
    )

    # Monotonic arrival sequence. Positions are applied in this order, so replaying
    # trades ordered by ``id`` reproduces the stored positions exactly.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    venue: Mapped[str] = mapped_column(String(32))
    trade_id: Mapped[str] = mapped_column(String(128))
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[Decimal] = mapped_column(MONEY)
    price: Mapped[Decimal] = mapped_column(MONEY)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Position(Base):
    """Running average-cost position per symbol, aggregated across venues.

    ``cost_basis`` (total cost of the open quantity) is stored instead of the average
    price so that buys stay exact and a fully closed position returns to zero cost
    with no rounding dust. ``avg_cost`` is derived as ``cost_basis / quantity``.
    """

    __tablename__ = "positions"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_positions_quantity_non_negative"),
        CheckConstraint("cost_basis >= 0", name="ck_positions_cost_basis_non_negative"),
    )

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    quantity: Mapped[Decimal] = mapped_column(MONEY)
    cost_basis: Mapped[Decimal] = mapped_column(MONEY)
    realized_pnl: Mapped[Decimal] = mapped_column(MONEY)
    trade_count: Mapped[int] = mapped_column(BigInteger, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Price(Base):
    """Latest mark price per symbol, used for unrealized PnL."""

    __tablename__ = "prices"
    __table_args__ = (CheckConstraint("price > 0", name="ck_prices_price_positive"),)

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    price: Mapped[Decimal] = mapped_column(MONEY)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
