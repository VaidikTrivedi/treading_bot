"""Paper broker: fills orders at the next day's open +/- slippage. No lookahead."""
from datetime import date
from decimal import Decimal
from typing import Dict, List

from arena.models import Order, Portfolio, Position, floor_shares, money


class PaperBroker:
    def __init__(self, slippage: Decimal = Decimal("0.001"), commission: Decimal = Decimal("0.00"),
                 min_order: Decimal = Decimal("1.00")):
        self.slippage = slippage
        self.commission = commission
        self.min_order = min_order

    def execute(self, portfolio: Portfolio, orders: List[Order], fill_date: date,
                opens: Dict[str, Decimal]):
        """Fill `orders` at `fill_date` open prices. Sells are processed BEFORE buys.
        Returns (fills, rejects). Each fill is a dict; each reject is (order, reason)."""
        fills, rejects, seen = [], [], set()
        ordered = [o for o in orders if o.side == "sell"] + [o for o in orders if o.side == "buy"]
        for o in ordered:
            if o.symbol in seen:
                rejects.append((o, "duplicate order for symbol on same day"))
                continue
            seen.add(o.symbol)
            if o.symbol not in opens:
                rejects.append((o, "no open price"))
                continue
            px = Decimal(str(opens[o.symbol]))
            if o.side == "sell":
                pos = portfolio.positions.get(o.symbol)
                if pos is None:
                    rejects.append((o, "nothing to sell"))
                    continue
                if pos.entry_date >= fill_date:
                    rejects.append((o, "minimum holding period"))
                    continue
                fill_px = px * (Decimal("1") - self.slippage)
                gross = pos.shares * fill_px
                portfolio.cash = money(portfolio.cash + gross - self.commission)
                fills.append(dict(symbol=o.symbol, side="sell", price=fill_px, shares=pos.shares,
                                  commission=self.commission, date=fill_date))
                del portfolio.positions[o.symbol]
            else:
                if o.symbol in portfolio.positions:
                    rejects.append((o, "already holding"))
                    continue
                spend = min(o.notional, portfolio.cash)          # shrink to available cash
                if spend - self.commission < self.min_order:
                    rejects.append((o, "order under minimum after shrink"))
                    continue
                fill_px = px * (Decimal("1") + self.slippage)
                shares = floor_shares((spend - self.commission) / fill_px)
                if shares <= 0:
                    rejects.append((o, "zero shares"))
                    continue
                cost = shares * fill_px + self.commission
                portfolio.cash = money(portfolio.cash - cost)
                portfolio.positions[o.symbol] = Position(shares, fill_px, fill_date)
                fills.append(dict(symbol=o.symbol, side="buy", price=fill_px, shares=shares,
                                  commission=self.commission, date=fill_date))
        return fills, rejects
