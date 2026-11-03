from decimal import Decimal
from typing import Dict, List

import pandas as pd

from arena.bots.base import Bot
from arena.models import Order, Portfolio


class RotationBot(Bot):
    def decide(self, history: Dict[str, pd.DataFrame], portfolio: Portfolio, today) -> List[Order]:
        g = self.genome
        lb, every, top_n = int(g["lookback_days"]), int(g["rebalance_days"]), int(g["top_n"])
        if not history:
            return []
        any_df = next(iter(history.values()))
        days_alive = int((any_df.index >= pd.Timestamp(self.created_date)).sum())   # includes today
        if days_alive < 1 or (days_alive - 1) % every != 0:
            return []                                          # not a rebalance day

        prices = self.last_close(history)
        equity = portfolio.equity(prices)
        scored = []
        for sym, df in history.items():
            if len(df) > lb:
                r = float(df["close"].iloc[-1] / df["close"].iloc[-1 - lb] - 1.0)
                if r >= g["min_return_to_hold"]:
                    scored.append((r, sym))
        scored.sort(key=lambda t: (-t[0], t[1]))
        target = [s for _, s in scored[:top_n]]

        orders: List[Order] = [Order(s, "sell") for s in portfolio.positions if s not in target]
        notional = (equity / Decimal(top_n)).quantize(Decimal("0.01"))
        orders += [Order(s, "buy", notional=notional) for s in target if s not in portfolio.positions]
        return orders
