"""Initial schema: trades ledger, positions, prices.

Revision ID: 0001
Revises:
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(38, 18)


def upgrade() -> None:
    op.create_table(
        "trades",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("venue", sa.String(32), nullable=False),
        sa.Column("trade_id", sa.String(128), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("quantity", MONEY, nullable=False),
        sa.Column("price", MONEY, nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("venue", "trade_id", name="uq_trades_venue_trade_id"),
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name="ck_trades_side"),
        sa.CheckConstraint("quantity > 0", name="ck_trades_quantity_positive"),
        sa.CheckConstraint("price > 0", name="ck_trades_price_positive"),
    )
    op.create_index("ix_trades_symbol_id", "trades", ["symbol", "id"])
    op.create_index("ix_trades_venue_executed_at", "trades", ["venue", "executed_at"])

    op.create_table(
        "positions",
        sa.Column("symbol", sa.String(32), primary_key=True),
        sa.Column("quantity", MONEY, nullable=False),
        sa.Column("cost_basis", MONEY, nullable=False),
        sa.Column("realized_pnl", MONEY, nullable=False),
        sa.Column("trade_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("quantity >= 0", name="ck_positions_quantity_non_negative"),
        sa.CheckConstraint("cost_basis >= 0", name="ck_positions_cost_basis_non_negative"),
    )

    op.create_table(
        "prices",
        sa.Column("symbol", sa.String(32), primary_key=True),
        sa.Column("price", MONEY, nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("price > 0", name="ck_prices_price_positive"),
    )


def downgrade() -> None:
    op.drop_table("prices")
    op.drop_table("positions")
    op.drop_index("ix_trades_venue_executed_at", table_name="trades")
    op.drop_index("ix_trades_symbol_id", table_name="trades")
    op.drop_table("trades")
