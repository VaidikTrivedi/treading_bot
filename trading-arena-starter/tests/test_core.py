import tempfile, unittest
from datetime import date
from decimal import Decimal as D

import numpy as np
import pandas as pd

from arena.bots.factory import make_bot
from arena.genomes import GENES, INITIAL_BOTS, initial_genome
from arena.market.data import DataStore, is_liquid, normalize
from arena.market.paper_broker import PaperBroker
from arena.models import Order, Portfolio, Position, money
from arena.supervisor.evolution import WeekResult, decide_evolution, max_drawdown, mutate_genome


def frame(closes, start="2026-01-05", vol=1_000_000, opens=None):
    idx = pd.bdate_range(start, periods=len(closes))
    c = np.array(closes, dtype=float)
    o = np.array(opens, dtype=float) if opens is not None else c
    return pd.DataFrame({"open": o, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": vol}, index=idx)


class BrokerTests(unittest.TestCase):
    def test_buy_fill_slippage_and_cash(self):
        pf = Portfolio(cash=D("50.00"))
        b = PaperBroker()
        fills, rej = b.execute(pf, [Order("AAA", "buy", D("25.00"))], date(2026, 1, 6), {"AAA": D("10")})
        self.assertEqual(rej, [])
        self.assertEqual(fills[0]["price"], D("10.01"))                # 10 * 1.001
        self.assertEqual(fills[0]["shares"], D("2.4975"))              # floor(25/10.01, 4dp)
        self.assertEqual(pf.cash, money(D("50") - D("2.4975") * D("10.01")))

    def test_commission_applied(self):
        pf = Portfolio(cash=D("50.00"))
        b = PaperBroker(commission=D("1.00"))
        b.execute(pf, [Order("AAA", "buy", D("50.00"))], date(2026, 1, 6), {"AAA": D("10")})
        self.assertLessEqual(pf.cash, D("0.01"))
        self.assertGreaterEqual(pf.cash, D("0.00"))

    def test_buy_shrinks_to_cash(self):
        pf = Portfolio(cash=D("20.00"))
        fills, _ = PaperBroker().execute(pf, [Order("AAA", "buy", D("100.00"))], date(2026, 1, 6), {"AAA": D("10")})
        self.assertEqual(len(fills), 1)
        self.assertGreaterEqual(pf.cash, D("0"))

    def test_skip_when_under_one_dollar(self):
        pf = Portfolio(cash=D("0.50"))
        fills, rej = PaperBroker().execute(pf, [Order("AAA", "buy", D("10.00"))], date(2026, 1, 6), {"AAA": D("10")})
        self.assertEqual(fills, []); self.assertEqual(len(rej), 1)

    def test_sells_before_buys_and_min_holding(self):
        pf = Portfolio(cash=D("0.00"), positions={"AAA": Position(D("5"), D("10"), date(2026, 1, 5))})
        orders = [Order("BBB", "buy", D("40.00")), Order("AAA", "sell")]
        fills, rej = PaperBroker().execute(pf, orders, date(2026, 1, 6), {"AAA": D("10"), "BBB": D("20")})
        self.assertEqual([f["side"] for f in fills], ["sell", "buy"])   # sells first frees cash
        self.assertIn("BBB", pf.positions)
        # same-day sell of a just-bought position is rejected
        fills2, rej2 = PaperBroker().execute(pf, [Order("BBB", "sell")], date(2026, 1, 6), {"BBB": D("20")})
        self.assertEqual(fills2, []); self.assertEqual(rej2[0][1], "minimum holding period")

    def test_duplicate_symbol_rejected(self):
        pf = Portfolio(cash=D("50.00"))
        fills, rej = PaperBroker().execute(pf, [Order("AAA", "buy", D("10")), Order("AAA", "buy", D("10"))],
                                           date(2026, 1, 6), {"AAA": D("10")})
        self.assertEqual(len(fills), 1); self.assertEqual(len(rej), 1)


class DataTests(unittest.TestCase):
    def test_history_never_returns_future_rows(self):
        with tempfile.TemporaryDirectory() as d:
            ds = DataStore(d)
            ds._mem["AAA"] = frame(range(1, 31))
            h = ds.history("AAA", date(2026, 1, 20))
            self.assertLessEqual(h.index.max(), pd.Timestamp("2026-01-20"))

    def test_refresh_merges_and_survives_failure(self):
        class P:
            def fetch(self, s, a, b):
                if s == "BAD":
                    raise RuntimeError("boom")
                return frame([10, 11, 12])
        with tempfile.TemporaryDirectory() as d:
            ds = DataStore(d, P())
            ds.refresh(["AAA", "BAD"], date(2026, 1, 5), date(2026, 1, 9))
            self.assertEqual(len(ds.load("AAA")), 3)
            self.assertEqual(len(ds.load("BAD")), 0)
            ds2 = DataStore(d, P())                                     # reload from disk
            self.assertEqual(len(ds2.load("AAA")), 3)

    def test_normalize_handles_tz_and_names(self):
        idx = pd.date_range("2026-01-05", periods=3, tz="America/Toronto")
        raw = pd.DataFrame({"Open": [1, 2, 3.], "High": [1, 2, 3.], "Low": [1, 2, 3.], "Close": [1, 2, 3.],
                            "Volume": [1, 1, 1]}, index=idx)
        n = normalize(raw)
        self.assertIsNone(n.index.tz); self.assertEqual(list(n.columns), ["open", "high", "low", "close", "volume"])

    def test_liquidity_filter(self):
        self.assertTrue(is_liquid(frame([10] * 25, vol=200_000)))      # 2,000,000 CAD per day
        self.assertFalse(is_liquid(frame([10] * 25, vol=1_000)))


class BotTests(unittest.TestCase):
    def test_momentum_buys_strongest(self):
        g = initial_genome("momentum")
        bot = make_bot("bot_001", "momentum", g, date(2026, 1, 5))
        hist = {"UP": frame(list(np.linspace(10, 12, 30))), "FLAT": frame([10] * 30)}
        orders = bot.decide(hist, Portfolio(cash=D("50")), date(2026, 2, 13))
        self.assertEqual([(o.symbol, o.side) for o in orders], [("UP", "buy")])
        self.assertEqual(orders[0].notional, D("25.00"))               # 50% of 50

    def test_momentum_stop_loss_sells(self):
        g = initial_genome("momentum")
        bot = make_bot("bot_001", "momentum", g, date(2026, 1, 5))
        pf = Portfolio(cash=D("0"), positions={"UP": Position(D("1"), D("20"), date(2026, 1, 6))})
        hist = {"UP": frame(list(np.linspace(10, 12, 30)))}            # price ~12 vs cost 20 -> stop hit
        orders = bot.decide(hist, pf, date(2026, 2, 13))
        self.assertEqual([(o.symbol, o.side) for o in orders], [("UP", "sell")])

    def test_mean_reversion_buys_dip(self):
        g = initial_genome("mean_reversion")
        bot = make_bot("bot_002", "mean_reversion", g, date(2026, 1, 5))
        closes = [10.0] * 19 + [7.0]
        orders = bot.decide({"DIP": frame(closes), "OK": frame([10.0] * 19 + [10.1])}, Portfolio(cash=D("50")), date(2026, 2, 2))
        self.assertEqual([(o.symbol, o.side) for o in orders], [("DIP", "buy")])

    def test_rotation_only_on_rebalance_days(self):
        g = initial_genome("rotation")                                 # rebalance every 5 days, top_n 1
        h = {"A": frame(list(np.linspace(10, 14, 40))), "B": frame([10] * 40)}
        created = h["A"].index[30].date()
        bot = make_bot("bot_003", "rotation", g, created)
        day1 = h["A"].index[30]                                         # days_alive == 1 -> rebalance
        o1 = bot.decide({k: v.loc[:day1] for k, v in h.items()}, Portfolio(cash=D("50")), day1.date())
        self.assertEqual([(o.symbol, o.side) for o in o1], [("A", "buy")])
        day2 = h["A"].index[31]
        o2 = bot.decide({k: v.loc[:day2] for k, v in h.items()}, Portfolio(cash=D("50")), day2.date())
        self.assertEqual(o2, [])
        day6 = h["A"].index[35]                                         # days_alive == 6 -> rebalance
        o6 = bot.decide({k: v.loc[:day6] for k, v in h.items()}, Portfolio(cash=D("50")), day6.date())
        self.assertEqual(len(o6), 1)


class EvolutionTests(unittest.TestCase):
    def wr(self, bid, s, e, trades=5, dd="0.02", halted=False, weeks=2):
        return WeekResult(bid, D(s), D(e), trades, D(dd), halted, weeks)

    def test_example_from_spec(self):
        res = [self.wr("bot_001", "50", "53"), self.wr("bot_002", "50", "49"), self.wr("bot_003", "50", "44")]
        self.assertEqual([r.return_pct for r in res], [D("6.00"), D("-2.00"), D("-12.00")])
        self.assertEqual(decide_evolution(res)[:2], ("bot_003", "bot_001"))

    def test_percentage_not_dollars(self):
        res = [self.wr("bot_001", "100", "104"),            # +4% (+$4)
               self.wr("bot_002", "50", "52.5"),            # +5% (+$2.5) -> strongest by percent
               self.wr("bot_003", "50", "49")]
        self.assertEqual(decide_evolution(res)[1], "bot_002")

    def test_grace_period(self):
        res = [self.wr("bot_001", "50", "53", weeks=1), self.wr("bot_002", "50", "49", weeks=1),
               self.wr("bot_003", "50", "44", weeks=1)]
        self.assertEqual(decide_evolution(res)[:2], (None, None))
        res[2] = self.wr("bot_003", "50", "44", weeks=2)               # only bot_003 eliminable
        self.assertEqual(decide_evolution(res)[:2], ("bot_003", "bot_001"))

    def test_winner_needs_trades_and_no_halt(self):
        res = [self.wr("bot_001", "50", "60", trades=2), self.wr("bot_002", "50", "58", halted=True),
               self.wr("bot_003", "50", "51"), self.wr("bot_004", "50", "47")]
        w, s, _ = decide_evolution(res)
        self.assertEqual((w, s), ("bot_004", "bot_003"))
        # edge case: the only eligible winner is also the weakest -> no action
        res2 = [self.wr("bot_001", "50", "60", trades=2), self.wr("bot_002", "50", "58", halted=True),
                self.wr("bot_003", "50", "51")]
        self.assertEqual(decide_evolution(res2)[:2], (None, None))

    def test_tie_breaks(self):
        res = [self.wr("bot_001", "50", "55", dd="0.03"), self.wr("bot_002", "50", "55", dd="0.01"),
               self.wr("bot_003", "50", "45", dd="0.05"), self.wr("bot_004", "50", "45", dd="0.09")]
        w, s, _ = decide_evolution(res)
        self.assertEqual(s, "bot_002")                                 # same return, smaller drawdown
        self.assertEqual(w, "bot_004")                                 # same return, larger drawdown
        res2 = [self.wr("bot_001", "50", "55"), self.wr("bot_002", "50", "55"),
                self.wr("bot_003", "50", "45"), self.wr("bot_004", "50", "45")]
        w2, s2, _ = decide_evolution(res2)
        self.assertEqual((w2, s2), ("bot_004", "bot_001"))             # full ties: higher id out, lower id wins

    def test_same_bot_skips(self):
        res = [self.wr("bot_001", "50", "55", weeks=2, trades=5)]
        self.assertEqual(decide_evolution(res)[:2], (None, None))

    def test_max_drawdown(self):
        self.assertEqual(max_drawdown([D("50"), D("55"), D("44"), D("50")]), D("0.2"))

    def test_mutation_valid_and_reproducible(self):
        for strat in GENES:
            parent = initial_genome(strat)
            for i in range(200):
                child = mutate_genome(strat, parent, f"seed:{i}")
                self.assertNotEqual(child, parent)
                for name, (typ, _, lo, hi) in GENES[strat].items():
                    self.assertTrue(lo <= child[name] <= hi, (strat, name, child[name]))
                    if typ == "int":
                        self.assertIsInstance(child[name], int)
            self.assertEqual(mutate_genome(strat, parent, "x"), mutate_genome(strat, parent, "x"))

    def test_zero_valued_genes_can_move(self):
        parent = initial_genome("mean_reversion")                       # exit_z starts at 0.0
        moved = any(mutate_genome("mean_reversion", parent, f"s{i}")["exit_z"] != 0.0 for i in range(50))
        self.assertTrue(moved)


class FundingMathTests(unittest.TestCase):
    def test_topup_does_not_change_return(self):
        # child funded with 44 + 6 top-up: e_start must be 50 (funding incl. deposit); end 52.5 -> +5%
        r = WeekResult("bot_004", D("50.00"), D("52.50"), 4, D("0"), False, 1)
        self.assertEqual(r.return_pct, D("5.00"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
