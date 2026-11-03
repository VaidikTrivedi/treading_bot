"""Shared data types and money helpers."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Dict, Optional

CENT = Decimal("0.01")
SHARE_STEP = Decimal("0.0001")


def money(x) -> Decimal:
    """Round any number to cents (half-up). Always build Decimals from str(), never from float."""
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def floor_shares(x) -> Decimal:
    """Round a share quantity DOWN to 4 decimal places."""
    return Decimal(str(x)).quantize(SHARE_STEP, rounding=ROUND_DOWN)


@dataclass
class Order:
    symbol: str
    side: str                              # "buy" or "sell"
    notional: Optional[Decimal] = None     # CAD to spend (buys only)
    # Sells always sell the WHOLE position. Partial sells are not allowed in v1.


@dataclass
class Position:
    shares: Decimal
    avg_cost: Decimal                      # average fill price incl. slippage
    entry_date: date


@dataclass
class Portfolio:
    cash: Decimal
    positions: Dict[str, Position] = field(default_factory=dict)

    def equity(self, last_prices: Dict[str, Decimal]) -> Decimal:
        total = self.cash
        for sym, pos in self.positions.items():
            total += pos.shares * Decimal(str(last_prices[sym]))
        return money(total)
