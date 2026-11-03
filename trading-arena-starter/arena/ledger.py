"""SQLite ledger (Section 9 of the spec). Plain sqlite3, no ORM."""
import json
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS bots(bot_id TEXT PRIMARY KEY, strategy TEXT, parent_id TEXT, generation INTEGER,
    genome_json TEXT, created_week TEXT, status TEXT, eliminated_week TEXT);
CREATE TABLE IF NOT EXISTS orders(order_id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id TEXT, symbol TEXT,
    side TEXT, notional TEXT, decision_date TEXT, status TEXT, reject_reason TEXT);
CREATE TABLE IF NOT EXISTS fills(fill_id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id TEXT, symbol TEXT, side TEXT,
    fill_date TEXT, price TEXT, quantity TEXT, commission TEXT);
CREATE TABLE IF NOT EXISTS daily_equity(bot_id TEXT, date TEXT, cash TEXT, positions_value TEXT, equity TEXT,
    PRIMARY KEY(bot_id, date));
CREATE TABLE IF NOT EXISTS weekly_results(bot_id TEXT, week TEXT, e_start TEXT, e_end TEXT, return_pct TEXT,
    trades INTEGER, max_drawdown TEXT, risk_halted INTEGER, rank INTEGER, PRIMARY KEY(bot_id, week));
CREATE TABLE IF NOT EXISTS deposits(deposit_id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id TEXT, week TEXT,
    amount TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS events(event_id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, type TEXT, detail_json TEXT);
CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT);
"""


class Ledger:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def q(self, sql, args=()):
        cur = self.db.execute(sql, args)
        self.db.commit()
        return cur

    def event(self, type_: str, **detail):
        self.q("INSERT INTO events(timestamp,type,detail_json) VALUES(?,?,?)",
               (datetime.now(timezone.utc).isoformat(), type_, json.dumps(detail, default=str)))

    def put_state(self, key, obj):
        self.q("INSERT OR REPLACE INTO state(key,value) VALUES(?,?)", (key, json.dumps(obj, default=str)))

    def get_state(self, key, default=None):
        row = self.db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default
