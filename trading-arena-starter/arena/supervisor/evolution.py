"""Mutation + weekly selection. Pure functions: easy to unit-test."""
import random
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional, Tuple

from arena.genomes import GENES

MUTATE_PROB = 0.6
MULT_RANGE = 0.20      # multiplicative genes: value * (1 + U(-0.20, +0.20))
ADD_RANGE = 0.10       # additive genes (min <= 0): value + U(-0.10, +0.10) * (max - min)


def mutate_genome(strategy: str, parent: dict, seed_text: str) -> dict:
    """Return a mutated copy. Deterministic for the same (parent, seed_text)."""
    rng = random.Random(seed_text)
    specs = GENES[strategy]
    for _attempt in range(1000):
        child = dict(parent)
        for name, (typ, _init, lo, hi) in specs.items():
            if rng.random() >= MUTATE_PROB:
                continue                                   # gene not selected
            old = parent[name]
            if lo <= 0:                                    # additive gene (value may be 0 or negative)
                new = old + rng.uniform(-ADD_RANGE, ADD_RANGE) * (hi - lo)
            else:
                new = old * (1 + rng.uniform(-MULT_RANGE, MULT_RANGE))
            new = min(max(new, lo), hi)
            if typ == "int":
                new = int(round(new))
                if new == old:                             # force a change of at least 1
                    step = rng.choice([-1, 1])
                    new = old + step
                    if not (lo <= new <= hi):
                        new = old - step
                new = min(max(new, lo), hi)
            else:
                new = round(new, 4)
            child[name] = new
        if child != parent:
            return child
    raise RuntimeError("could not produce a different child")   # practically unreachable


@dataclass
class WeekResult:
    bot_id: str
    e_start: Decimal
    e_end: Decimal
    trades: int
    max_drawdown: Decimal          # fraction, e.g. 0.07 = 7 percent, measured inside the week
    risk_halted: bool
    completed_weeks: int           # including this week

    @property
    def return_pct(self) -> Decimal:
        r = (self.e_end - self.e_start) / self.e_start * Decimal("100")
        return r.quantize(Decimal("0.01"))

    @property
    def number(self) -> int:
        return int(self.bot_id.split("_")[1])


def decide_evolution(results: List[WeekResult], min_weeks: int = 2,
                     min_trades: int = 3) -> Tuple[Optional[str], Optional[str], str]:
    """Returns (weakest_id, strongest_id, reason). If no action: (None, None, reason)."""
    eliminable = [r for r in results if r.completed_weeks >= min_weeks]
    winners = [r for r in results if r.trades >= min_trades and not r.risk_halted]
    if not eliminable:
        return None, None, "no bot has completed the minimum weeks yet"
    if not winners:
        return None, None, "no bot is eligible to be strongest"
    weakest = sorted(eliminable, key=lambda r: (r.return_pct, -r.max_drawdown, -r.number))[0]
    strongest = sorted(winners, key=lambda r: (-r.return_pct, r.max_drawdown, r.number))[0]
    if weakest.bot_id == strongest.bot_id:
        return None, None, "weakest and strongest are the same bot"
    return weakest.bot_id, strongest.bot_id, "ok"


def max_drawdown(equities: List[Decimal]) -> Decimal:
    """Largest peak-to-trough fall as a fraction, over the given equity series (include week-start equity)."""
    peak, worst = equities[0], Decimal("0")
    for e in equities:
        peak = max(peak, e)
        if peak > 0:
            worst = max(worst, (peak - e) / peak)
    return worst
