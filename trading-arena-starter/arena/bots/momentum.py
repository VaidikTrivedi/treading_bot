from decimal import Decimal
from typing import Dict, List

import pandas as pd

from arena.bots.base import Bot
from arena.models import Order, Portfolio


class MomentumBot(Bot):
    def decide(self, history: Dict[str, pd.DataFrame], portfolio: Portfolio, today) -> List[Order]:
        g = self.genome
        lb = int(g["lookback_days"])
        prices = self.last_close(history)
        equity = portfolio.equity(prices)
        orders: List[Order] = []

        def lookback_return(df):
            if len(df) <= lb:
                return None
            return float(df["close"].iloc[-1] / df["close"].iloc[-1 - lb] - 1.0)

        # 1) exits
        selling = set()
        for sym, pos in portfolio.positions.items():
            px = prices[sym]
            r = lookback_return(history[sym])
            stop = pos.avg_cost * (Decimal("1") - Decimal(str(g["stop_loss"])))
            take = pos.avg_cost * (Decimal("1") + Decimal(str(g["take_profit"])))
            if px <= stop or px >= take or (r is not None and r < 0):
                orders.append(Order(sym, "sell"))
                selling.add(sym)

        # 2) entries
        open_after_exits = len(portfolio.positions) - len(selling)
        slots = int(g["max_open_positions"]) - open_after_exits
        if slots > 0:
            cands = []
            for sym, df in history.items():
                if sym in portfolio.positions:
                    continue
                r = lookback_return(df)
                if r is not None and r >= g["entry_threshold"]:
                    cands.append((r, sym))
            cands.sort(key=lambda t: (-t[0], t[1]))               # highest return first, ties by symbol
            notional = equity * Decimal(str(g["max_position_pct"]))
            for _, sym in cands[:slots]:
                orders.append(Order(sym, "buy", notional=notional.quantize(Decimal("0.01"))))
        return orders
