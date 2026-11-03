"""Bot interface. A bot sees ONLY: price history up to the decision date, its own portfolio, the date."""
from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import Dict, List

import pandas as pd

from arena.models import Order, Portfolio


class Bot(ABC):
    def __init__(self, bot_id: str, genome: dict, created_date: date):
        self.bot_id = bot_id
        self.genome = genome
        self.created_date = created_date

    @abstractmethod
    def decide(self, history: Dict[str, pd.DataFrame], portfolio: Portfolio, today: date) -> List[Order]:
        """history[symbol] = DataFrame indexed by date (ascending, last row == today),
        columns: open, high, low, close, volume. Only tradable symbols are included."""

    # ---- helpers shared by all strategies ----
    @staticmethod
    def last_close(history: Dict[str, pd.DataFrame]) -> Dict[str, Decimal]:
        return {s: Decimal(str(df["close"].iloc[-1])) for s, df in history.items()}

    def equity(self, history, portfolio) -> Decimal:
        prices = self.last_close(history)
        # a held symbol may be missing from `history` (became illiquid): value it at 0 is wrong,
        # so the runner must always pass held symbols too. See runner guide.
        return portfolio.equity(prices)
