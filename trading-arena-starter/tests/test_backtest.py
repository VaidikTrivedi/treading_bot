import json, shutil, sqlite3, tempfile, unittest
from datetime import date
from decimal import Decimal as D

import numpy as np
import pandas as pd

from arena.market.data import DataStore
from arena.supervisor.runner import Arena

UNIVERSE = ["XIU.TO", "XIC.TO", "VFV.TO", "XEQT.TO", "ZAG.TO", "RY.TO", "TD.TO", "BNS.TO", "ENB.TO", "CNQ.TO", "SHOP.TO"]
CFG = dict(start_capital="50.00", slippage="0.001", commission="0.00", top_up_policy="to_50",
           min_weeks_before_elimination=2, min_trades_for_winner=3, daily_loss_halt=0.10,
           drawdown_halt_floor=0.60, seed=42, universe=UNIVERSE, min_dollar_volume=1_000_000)


def synth(symbol, days, seed):
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0004, 0.015, len(days))
    close = 20 * np.exp(np.cumsum(r))
    open_ = close * (1 + rng.normal(0, 0.003, len(days)))
    return pd.DataFrame({"open": open_, "high": close * 1.01, "low": close * 0.99, "close": close,
                         "volume": 500_000}, index=days)


def make_store(tmp, spy=None):
    days = pd.bdate_range("2025-01-06", "2025-12-31")
    store = DataStore(tmp)
    for i, s in enumerate(UNIVERSE):
        store._mem[s] = synth(s, days, 100 + i)
    if spy is not None:
        orig = store.history
        def watched(symbol, end):
            spy.append((end, orig(symbol, end).index.max()))
            return orig(symbol, end)
        store.history = watched
    return store


def run(tmp, spy=None, cfg=None):
    store = make_store(tmp + "/cache", spy)
    a = Arena(cfg or CFG, store, tmp + "/arena.db", tmp + "/reports", tmp + "/genomes")
    a.init_bots(date(2025, 1, 6))
    a.backtest(date(2025, 1, 6), date(2025, 12, 31))
    return a


class BacktestTests(unittest.TestCase):
    def test_full_year_invariants(self):
        with tempfile.TemporaryDirectory() as tmp:
            spy = []
            a = run(tmp, spy)
            db = sqlite3.connect(tmp + "/arena.db")
            # no lookahead: every history read ended on/before the requested date
            self.assertTrue(all(mx is pd.NaT or mx <= pd.Timestamp(end) for end, mx in spy))
            # exactly 3 live bots at the end (+ any liquidating one at most)
            alive = [b for b in a.bots.values() if b.status == "active"]
            self.assertEqual(len(alive), 3)
            # at least one evolution happened in a year, and every child came from a parent
            evo = db.execute("SELECT count(*) FROM events WHERE type='evolution'").fetchone()[0]
            self.assertGreater(evo, 0)
            # cash never negative; equity rows exist
            neg = db.execute("SELECT count(*) FROM daily_equity WHERE CAST(cash AS REAL) < 0").fetchone()[0]
            self.assertEqual(neg, 0)
            # weekly results: 3 bots ranked each week with rank 1..3 present
            weeks = db.execute("SELECT week, count(*) FROM weekly_results GROUP BY week").fetchall()
            self.assertTrue(all(c == 3 for _, c in weeks), weeks)
            # funding rule: every child's first equity row is >= 50.00 when top-up policy is to_50 and freed < 50
            for (bid, amt) in db.execute("SELECT bot_id, amount FROM deposits"):
                row = db.execute("SELECT equity FROM daily_equity WHERE bot_id=? ORDER BY date LIMIT 1", (bid,)).fetchone()
                self.assertEqual(D(row[0]), D("50.00"))
            # genome files written; children differ from parent
            for bid, parent in db.execute("SELECT bot_id, parent_id FROM bots WHERE parent_id IS NOT NULL"):
                with open(f"{tmp}/genomes/{bid}.json") as fc, open(f"{tmp}/genomes/{parent}.json") as fp:
                    child, par = json.load(fc)["genome"], json.load(fp)["genome"]
                self.assertNotEqual(child, par)
            print("evolutions:", evo, "| bots ever created:", db.execute("SELECT count(*) FROM bots").fetchone()[0],
                  "| fills:", db.execute("SELECT count(*) FROM fills").fetchone()[0],
                  "| deposits:", db.execute("SELECT count(*) FROM deposits").fetchone()[0])

    def test_reproducible_with_same_seed(self):
        out = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmp:
                run(tmp)
                db = sqlite3.connect(tmp + "/arena.db")
                out.append((db.execute("SELECT * FROM weekly_results ORDER BY week, bot_id").fetchall(),
                            db.execute("SELECT bot_id, genome_json FROM bots ORDER BY bot_id").fetchall()))
        self.assertEqual(out[0], out[1])

    def test_commission_run_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = dict(CFG, commission="1.00")
            a = run(tmp, cfg=cfg)
            self.assertEqual(len([b for b in a.bots.values() if b.status == "active"]), 3)

    def test_resume_from_saved_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp + "/cache")
            a = Arena(CFG, store, tmp + "/arena.db", tmp + "/reports", tmp + "/genomes")
            a.init_bots(date(2025, 1, 6))
            a.backtest(date(2025, 1, 6), date(2025, 6, 30))
            b = Arena(CFG, make_store(tmp + "/cache2"), tmp + "/arena.db", tmp + "/reports", tmp + "/genomes")  # reload
            self.assertEqual(b.meta["last_day"], a.meta["last_day"])
            b.backtest(date(2025, 7, 1), date(2025, 12, 31))
            self.assertEqual(len([x for x in b.bots.values() if x.status == "active"]), 3)


def fresh_arena(tmp):
    store = make_store(tmp + "/cache")
    a = Arena(CFG, store, tmp + "/arena.db", tmp + "/reports", tmp + "/genomes")
    a.init_bots(date(2025, 1, 6))
    return a


class RulesTests(unittest.TestCase):
    def test_initial_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fresh_arena(tmp)
            self.assertEqual(sorted(a.bots), ["bot_001", "bot_002", "bot_003"])
            for st in a.bots.values():
                self.assertEqual((D(st.cash), st.positions, st.status), (D("50.00"), {}, "active"))

    def test_risk_halts(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fresh_arena(tmp)
            day = date(2025, 3, 3)
            close = D(str(a.store.history("XIU.TO", day)["close"].iloc[-1]))
            st = a.bots["bot_001"]
            st.cash = "0.00"
            st.positions = {"XIU.TO": dict(shares=str(D("100") / close), avg_cost=str(close), entry_date="2025-01-06")}
            # Case 1: equity ~100, previous close 130 (-23% day) and peak 200 (equity < 60% of peak) -> both halts
            st.prev_close_equity, st.peak = "130.00", "200.00"
            a._value_and_risk(day)
            self.assertTrue(st.daily_halt_today and st.dd_halt and st.risk_halted_week)
            a._decide(day)
            self.assertEqual([(o["symbol"], o["side"]) for o in st.pending], [("XIU.TO", "sell")])   # sell-all, no buys
            # Case 2: only the daily-loss halt -> buys are removed, sells allowed
            st.dd_halt, st.risk_halted_week, st.peak, st.prev_close_equity = False, False, "100.00", "130.00"
            a._value_and_risk(day)
            self.assertTrue(st.daily_halt_today and not st.dd_halt)
            a._decide(day)
            self.assertTrue(all(o["side"] == "sell" for o in st.pending))

    def _birth(self, freed):
        with tempfile.TemporaryDirectory() as tmp:
            a = fresh_arena(tmp)
            a.bots["bot_003"].status, a.bots["bot_003"].cash = "liquidating", freed
            a.meta["pending_births"].append(dict(source="bot_003", parent="bot_001", week="2025-W10"))
            a._process_births(date(2025, 3, 10))
            child = a.bots["bot_004"]
            deposits = a.ledger.q("SELECT amount FROM deposits").fetchall()
            return child, deposits, a.bots["bot_003"]

    def test_funding_with_topup(self):                      # freed 44.00 -> child 50.00, deposit 6.00
        child, deposits, old = self._birth("44.00")
        self.assertEqual((D(child.cash), D(child.week_start_equity), deposits, old.status),
                         (D("50.00"), D("50.00"), [("6.00",)], "eliminated"))
        self.assertEqual((child.parent_id, child.generation, child.strategy), ("bot_001", 1, "momentum"))

    def test_funding_without_topup(self):                   # freed 57.00 -> child 57.00, no deposit
        child, deposits, _ = self._birth("57.00")
        self.assertEqual((D(child.cash), deposits), (D("57.00"), []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
