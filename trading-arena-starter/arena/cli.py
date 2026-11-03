"""Command line entry point:  python -m arena.cli <command> ..."""
import argparse
import logging
import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

import yaml

from arena.market.data import DataStore, YahooProvider
from arena.supervisor.runner import Arena

WARMUP_DAYS = 400      # calendar days of history needed before the first decision day


def load_cfg(path):
    return yaml.safe_load(open(path))


def build(cfg, db, fetcher=True, tag=""):
    store = DataStore(cfg["data_cache_dir"], YahooProvider() if fetcher else None)
    return store, Arena(cfg, store, db, f"{cfg['report_dir']}{tag}", f"{cfg['genome_dir']}{tag}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="arena")
    ap.add_argument("--config", default="config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch");    f.add_argument("--start", required=True); f.add_argument("--end", default=date.today().isoformat())
    i = sub.add_parser("init");     i.add_argument("--start", default=date.today().isoformat())
    b = sub.add_parser("backtest"); b.add_argument("--start", required=True); b.add_argument("--end", required=True)
    b.add_argument("--fresh", action="store_true", help="delete backtest.db first")
    b.add_argument("--seed", type=int, help="override config seed (for robustness runs)")
    b.add_argument("--commission", help='override commission per trade, e.g. "1.00"')
    sub.add_parser("run-day")
    r = sub.add_parser("report");   r.add_argument("--week", required=True)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_cfg(a.config)

    if a.cmd == "fetch":
        store, _ = build(cfg, ":memory:")
        store.refresh(cfg["universe"], date.fromisoformat(a.start), date.fromisoformat(a.end))
    elif a.cmd == "init":
        _, arena = build(cfg, "arena.db")
        arena.init_bots(date.fromisoformat(a.start))
        print("initialised 3 bots with", cfg["start_capital"], cfg["currency"], "each")
    elif a.cmd == "backtest":
        if a.seed is not None:
            cfg["seed"] = a.seed
        if a.commission is not None:
            cfg["commission"] = a.commission
        if a.fresh and os.path.exists("backtest.db"):
            os.remove("backtest.db")
        if os.path.exists("backtest.db"):
            raise SystemExit("backtest.db already exists. Re-run with --fresh to overwrite it.")
        store, arena = build(cfg, "backtest.db", fetcher=False, tag="_backtest")
        start, end = date.fromisoformat(a.start), date.fromisoformat(a.end)
        arena.init_bots(start)
        arena.backtest(start, end)
        print("backtest finished; see reports_backtest/ and backtest.db")
    elif a.cmd == "run-day":
        store, arena = build(cfg, "arena.db")
        now = datetime.now(ZoneInfo("America/Toronto"))
        # Only process a day once its daily bar is final: TSX closes 16:00 ET; we wait until 17:30 ET.
        end_day = now.date() if now.time() >= time(17, 30) else now.date() - timedelta(days=1)
        last = arena.meta["last_day"]
        first_new = date.fromisoformat(last) + timedelta(days=1) if last else end_day
        store.refresh(cfg["universe"], end_day - timedelta(days=WARMUP_DAYS), end_day)
        days = store.trading_days(cfg["universe"], first_new, end_day)
        for ts in days:
            arena.process_day(ts.date())
            print("processed", ts.date())
        if not days:
            print("nothing new to process")
    elif a.cmd == "report":
        print(Path(cfg["report_dir"], f"weekly_{a.week}.md").read_text())


if __name__ == "__main__":
    main()
