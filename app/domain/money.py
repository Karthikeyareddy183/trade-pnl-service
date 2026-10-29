"""Decimal arithmetic policy shared by every calculation in the service.

Python's default decimal context keeps only 28 significant digits, which silently rounds
products such as ``quantity * price`` once both operands carry 18 fractional digits.
All domain maths therefore runs inside ``MONEY_CONTEXT`` (80 digits, traps on) and results
are rounded half-even to the 18 fractional digits the database stores.
"""

from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
)

SCALE = 18
QUANTUM = Decimal(1).scaleb(-SCALE)
ZERO = Decimal(0)

MONEY_CONTEXT = Context(
    prec=80,
    rounding=ROUND_HALF_EVEN,
    traps=[InvalidOperation, DivisionByZero, Overflow],
)


def quantize(value: Decimal) -> Decimal:
    """Round to the storage scale (18 dp, banker's rounding)."""
    return value.quantize(QUANTUM, context=MONEY_CONTEXT)


def format_decimal(value: Decimal) -> str:
    """Render without exponent or trailing zeros: ``Decimal('105.000')`` -> ``'105'``."""
    if value.is_zero():
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
