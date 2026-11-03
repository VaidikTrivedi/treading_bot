"""The Supervisor: runs the daily loop and the weekly evaluation. Same code for backtest and live-paper."""
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pandas as pd
from typing import Dict, List, Optional

from arena.bots.factory import make_bot
from arena.genomes import INITIAL_BOTS, initial_genome
from arena.ledger import Ledger
from arena.market.data import DataStore, is_liquid
from arena.market.paper_broker import PaperBroker
from arena.models import Order, Portfolio, Position, money
from arena.supervisor.evolution import WeekResult, decide_evolution, max_drawdown, mutate_genome


def week_key(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


@dataclass
class BotState:
    bot_id: str
    strategy: str
    genome: dict
    parent_id: Optional[str]
    generation: int
    created_date: str
    created_week: str
    status: str = "active"                       # active | liquidating | eliminated
    cash: str = "0.00"
    positions: Dict[str, dict] = field(default_factory=dict)   # sym -> {shares, avg_cost, entry_date}
    pending: List[dict] = field(default_factory=list)          # orders to fill at next open
    week_start_equity: str = "0.00"
    week_equities: List[str] = field(default_factory=list)
    week_trades: int = 0
    risk_halted_week: bool = False
    dd_halt: bool = False
    peak: str = "0.00"
    prev_close_equity: str = "0.00"
    completed_weeks: int = 0
    daily_halt_today: bool = False

    def portfolio(self) -> Portfolio:
        return Portfolio(cash=D(self.cash), positions={
            s: Position(D(p["shares"]), D(p["avg_cost"]), date.fromisoformat(p["entry_date"]))
            for s, p in self.positions.items()})

    def save_portfolio(self, pf: Portfolio):
        self.cash = str(pf.cash)
        self.positions = {s: dict(shares=str(p.shares), avg_cost=str(p.avg_cost), entry_date=p.entry_date.isoformat())
                          for s, p in pf.positions.items()}


class Arena:
    def __init__(self, cfg: dict, store: DataStore, db_path: str, report_dir: str = "reports",
                 genome_dir: str = "genomes"):
        self.cfg, self.store = cfg, store
        self.ledger = Ledger(db_path)
        self.broker = PaperBroker(D(str(cfg["slippage"])), D(str(cfg["commission"])))
        self.report_dir, self.genome_dir = Path(report_dir), Path(genome_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.genome_dir.mkdir(parents=True, exist_ok=True)
        self.bots: Dict[str, BotState] = {}
        self.meta = {"last_day": None, "next_bot_number": 1, "pending_births": []}
        self._load()

    # ---------- persistence ----------
    def _load(self):
        saved = self.ledger.get_state("bots")
        if saved:
            self.bots = {k: BotState(**v) for k, v in saved.items()}
            self.meta = self.ledger.get_state("meta")

    def _save(self):
        self.ledger.put_state("bots", {k: b.__dict__ for k, b in self.bots.items()})
        self.ledger.put_state("meta", self.meta)

    # ---------- setup ----------
    def init_bots(self, start: date):
        if self.bots:
            raise RuntimeError("already initialised")
        cap = money(self.cfg["start_capital"])
        for bot_id, strat in INITIAL_BOTS:
            self._create_bot(bot_id, strat, initial_genome(strat), None, 0, start, cap)
            self.meta["next_bot_number"] = max(self.meta["next_bot_number"], int(bot_id.split("_")[1]) + 1)
        self._save()

    def _create_bot(self, bot_id, strat, genome, parent, gen, created: date, funding):
        st = BotState(bot_id, strat, genome, parent, gen, created.isoformat(), week_key(created),
                      cash=str(funding), week_start_equity=str(funding), peak=str(funding),
                      prev_close_equity=str(funding))
        self.bots[bot_id] = st
        self.ledger.q("INSERT INTO bots VALUES(?,?,?,?,?,?,?,?)",
                      (bot_id, strat, parent, gen, json.dumps(genome), st.created_week, "active", None))
        (self.genome_dir / f"{bot_id}.json").write_text(json.dumps(
            dict(bot_id=bot_id, strategy=strat, parent_id=parent, generation=gen, genome=genome), indent=2))
        self.ledger.event("bot_created", bot_id=bot_id, parent=parent, funding=str(funding))

    # ---------- main entry ----------
    def process_day(self, day: date):
        last = self.meta["last_day"]
        if last and week_key(date.fromisoformat(last)) != week_key(day):
            self._weekly_evaluation(week_key(date.fromisoformat(last)))
        self._fill(day)
        self._value_and_risk(day)
        self._decide(day)
        self._daily_report(day)
        self.meta["last_day"] = day.isoformat()
        self._save()

    def backtest(self, start: date, end: date):
        for ts in self.store.trading_days(self.cfg["universe"], start, end):
            self.process_day(ts.date())

    # ---------- phases ----------
    def _fill(self, day: date):
        for st in list(self.bots.values()):
            if st.status == "eliminated" or not st.pending:
                continue
            orders = [Order(p["symbol"], p["side"], D(p["notional"]) if p["notional"] else None) for p in st.pending]
            opens = {}
            for o in orders:
                px = self.store.open_price(o.symbol, day)
                if px is not None:
                    opens[o.symbol] = D(str(px))
            pf = st.portfolio()
            fills, rejects = self.broker.execute(pf, orders, day, opens)
            st.save_portfolio(pf)
            st.week_trades += len(fills)
            for f in fills:
                self.ledger.q("INSERT INTO fills(bot_id,symbol,side,fill_date,price,quantity,commission) VALUES(?,?,?,?,?,?,?)",
                              (st.bot_id, f["symbol"], f["side"], day.isoformat(), str(f["price"]), str(f["shares"]), str(f["commission"])))
            for o, why in rejects:
                self.ledger.q("INSERT INTO orders(bot_id,symbol,side,notional,decision_date,status,reject_reason) VALUES(?,?,?,?,?,?,?)",
                              (st.bot_id, o.symbol, o.side, str(o.notional), day.isoformat(), "rejected", why))
                self.ledger.event("order_rejected", bot_id=st.bot_id, symbol=o.symbol, reason=why)
            st.pending = []
        self._process_births(day)

    def _process_births(self, day: date):
        still = []
        for b in self.meta["pending_births"]:
            src, parent = self.bots[b["source"]], self.bots[b["parent"]]
            if src.positions:                                    # liquidation incomplete: retry tomorrow
                src.pending = [dict(symbol=s, side="sell", notional=None) for s in src.positions]
                still.append(b)
                continue
            freed = money(src.cash)
            src.cash, src.status = "0.00", "eliminated"
            self.ledger.q("UPDATE bots SET status='eliminated', eliminated_week=? WHERE bot_id=?", (b["week"], src.bot_id))
            funding, topup = freed, D("0.00")
            if self.cfg["top_up_policy"] == "to_50" and freed < money(self.cfg["start_capital"]):
                topup = money(self.cfg["start_capital"]) - freed
                funding = money(self.cfg["start_capital"])
            new_id = f"bot_{self.meta['next_bot_number']:03d}"
            self.meta["next_bot_number"] += 1
            genome = mutate_genome(parent.strategy, parent.genome, f"{self.cfg['seed']}:{b['week']}:{parent.bot_id}")
            self._create_bot(new_id, parent.strategy, genome, parent.bot_id, parent.generation + 1, day, funding)
            if topup > 0:
                self.ledger.q("INSERT INTO deposits(bot_id,week,amount,reason) VALUES(?,?,?,?)",
                              (new_id, week_key(day), str(topup), "top-up to start capital"))
            self.ledger.event("evolution", eliminated=src.bot_id, parent=parent.bot_id, child=new_id,
                              freed=str(freed), topup=str(topup))
            diff = {k: (parent.genome[k], genome[k]) for k in genome if genome[k] != parent.genome[k]}
            with open(self.report_dir / f"weekly_{b['week']}.md", "a") as f:
                f.write(f"\n## Evolution (executed {day})\n- Eliminated: {src.bot_id}\n- Parent: {parent.bot_id}\n"
                        f"- Child: {new_id} (generation {parent.generation + 1}), funding {funding} CAD "
                        f"(freed {freed}, top-up {topup})\n- Genome diff (parent -> child): {diff}\n")
        self.meta["pending_births"] = still

    def _closes(self, st: BotState, day: date) -> Dict[str, D]:
        out = {}
        for s in st.positions:
            h = self.store.history(s, day)
            out[s] = D(str(h["close"].iloc[-1]))
        return out

    def _value_and_risk(self, day: date):
        for st in self.bots.values():
            if st.status != "active":
                continue
            pf = st.portfolio()
            eq = pf.equity(self._closes(st, day))
            self.ledger.q("INSERT OR REPLACE INTO daily_equity VALUES(?,?,?,?,?)",
                          (st.bot_id, day.isoformat(), str(pf.cash), str(money(eq - pf.cash)), str(eq)))
            st.week_equities.append(str(eq))
            st.peak = str(max(D(st.peak), eq))
            st.daily_halt_today = False
            prev = D(st.prev_close_equity)
            if prev > 0 and (prev - eq) / prev > D(str(self.cfg["daily_loss_halt"])):
                st.daily_halt_today, st.risk_halted_week = True, True
                self.ledger.event("daily_loss_halt", bot_id=st.bot_id, day=day.isoformat())
            if eq <= D(str(self.cfg["drawdown_halt_floor"])) * D(st.peak) and not st.dd_halt:
                st.dd_halt, st.risk_halted_week = True, True
                self.ledger.event("drawdown_halt", bot_id=st.bot_id, day=day.isoformat())
            st.prev_close_equity = str(eq)

    def _decide(self, day: date):
        ts = pd.Timestamp(day)
        tradable = []
        for s in self.cfg["universe"]:
            h = self.store.history(s, day)
            if len(h) and h.index[-1] == ts and is_liquid(h, self.cfg["min_dollar_volume"]):
                tradable.append(s)
        for st in self.bots.values():
            if st.status != "active":
                continue
            pf = st.portfolio()
            syms = list(dict.fromkeys(tradable + list(st.positions)))
            history = {s: self.store.history(s, day) for s in syms if len(self.store.history(s, day))}
            bot = make_bot(st.bot_id, st.strategy, st.genome, date.fromisoformat(st.created_date))
            orders = bot.decide(history, pf, day) if history else []   # warm-up: nothing tradable yet
            if st.dd_halt:
                orders = [Order(s, "sell") for s in st.positions]
            elif st.daily_halt_today:
                orders = [o for o in orders if o.side == "sell"]
            clean, seen = [], set()
            for o in orders:
                if o.symbol not in self.cfg["universe"] or o.symbol in seen:
                    self.ledger.event("order_dropped", bot_id=st.bot_id, symbol=o.symbol)
                    continue
                seen.add(o.symbol)
                clean.append(dict(symbol=o.symbol, side=o.side, notional=str(o.notional) if o.notional else None))
            st.pending = clean

    def _weekly_evaluation(self, week: str):
        active = [s for s in self.bots.values() if s.status == "active"]
        results = []
        for st in active:
            st.completed_weeks += 1
            e_start = D(st.week_start_equity)
            e_end = D(st.week_equities[-1]) if st.week_equities else e_start
            dd = max_drawdown([e_start] + [D(x) for x in st.week_equities])
            results.append(WeekResult(st.bot_id, e_start, e_end, st.week_trades, dd, st.risk_halted_week, st.completed_weeks))
        ranked = sorted(results, key=lambda r: (-r.return_pct, r.number))
        for rank, r in enumerate(ranked, 1):
            self.ledger.q("INSERT OR REPLACE INTO weekly_results VALUES(?,?,?,?,?,?,?,?,?)",
                          (r.bot_id, week, str(r.e_start), str(r.e_end), str(r.return_pct), r.trades,
                           str(r.max_drawdown), int(r.risk_halted), rank))
        weakest, strongest, reason = decide_evolution(results, self.cfg["min_weeks_before_elimination"],
                                                      self.cfg["min_trades_for_winner"])
        lines = [f"# Weekly report {week}\n", "| Rank | Bot | Strategy | Gen | E_start | E_end | Return % | Trades | Max DD | Halted |",
                 "|---|---|---|---|---|---|---|---|---|---|"]
        for rank, r in enumerate(ranked, 1):
            st = self.bots[r.bot_id]
            lines.append(f"| {rank} | {r.bot_id} | {st.strategy} | {st.generation} | {r.e_start} | {r.e_end} | "
                         f"{r.return_pct} | {r.trades} | {(r.max_drawdown * 100).quantize(D('0.01'))}% | {r.risk_halted} |")
        if weakest:
            lines.append(f"\nDecision: eliminate {weakest}; clone-and-mutate {strongest}. "
                         "Liquidation happens at the next trading day's open.")
            self.bots[weakest].status = "liquidating"
            self.bots[weakest].pending = [dict(symbol=s, side="sell", notional=None) for s in self.bots[weakest].positions]
            self.meta["pending_births"].append(dict(source=weakest, parent=strongest, week=week))
            self.ledger.event("weekly_decision", week=week, weakest=weakest, strongest=strongest)
        else:
            lines.append(f"\nDecision: no action this week ({reason}).")
            self.ledger.event("weekly_no_action", week=week, reason=reason)
        (self.report_dir / f"weekly_{week}.md").write_text("\n".join(lines) + "\n")
        for st in active:                                        # reset weekly counters
            e_end = D(st.week_equities[-1]) if st.week_equities else D(st.week_start_equity)
            st.week_start_equity, st.week_equities, st.week_trades = str(e_end), [], 0
            st.risk_halted_week, st.dd_halt, st.peak = False, False, str(e_end)

    def _daily_report(self, day: date):
        rows = ["bot_id,strategy,equity,positions,dd_halt,risk_halted_week"]
        for st in self.bots.values():
            if st.status == "active" and st.week_equities:
                rows.append(f"{st.bot_id},{st.strategy},{st.week_equities[-1]},{'|'.join(st.positions)},{st.dd_halt},{st.risk_halted_week}")
        (self.report_dir / f"daily_{day.isoformat()}.csv").write_text("\n".join(rows) + "\n")
