from decimal import Decimal
from typing import Dict, List

import pandas as pd

from arena.bots.base import Bot
from arena.models import Order, Portfolio


class MeanReversionBot(Bot):
    @staticmethod
    def zscore(df: pd.DataFrame, n: int):
        if len(df) < n:
            return None
        w = df["close"].iloc[-n:]
        sd = float(w.std(ddof=0))
        if sd == 0:
            return None
        return float((w.iloc[-1] - w.mean()) / sd)

    def decide(self, history: Dict[str, pd.DataFrame], portfolio: Portfolio, today) -> List[Order]:
        g = self.genome
        n = int(g["ma_days"])
        prices = self.last_close(history)
        equity = portfolio.equity(prices)
        orders: List[Order] = []
        selling = set()

        for sym, pos in portfolio.positions.items():
            z = self.zscore(history[sym], n)
            stop = pos.avg_cost * (Decimal("1") - Decimal(str(g["stop_loss"])))
            if prices[sym] <= stop or (z is not None and z >= g["exit_z"]):
                orders.append(Order(sym, "sell"))
                selling.add(sym)

        slots = int(g["max_open_positions"]) - (len(portfolio.positions) - len(selling))
        if slots > 0:
            cands = []
            for sym, df in history.items():
                if sym in portfolio.positions:
                    continue
                z = self.zscore(df, n)
                if z is not None and z <= -g["entry_z"]:
                    cands.append((z, sym))                         # most negative z first
            cands.sort(key=lambda t: (t[0], t[1]))
            notional = (equity * Decimal(str(g["max_position_pct"]))).quantize(Decimal("0.01"))
            for _, sym in cands[:slots]:
                orders.append(Order(sym, "buy", notional=notional))
        return orders
