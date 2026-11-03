# Arena starter kit

Evolutionary paper-trading bot arena (3 bots, weekly elimination, profit-percentage ranking).
Read `trading-bot-arena-spec-and-prompt.md` first. Quick start:

    python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    python -m unittest discover -s tests -v                 # must end with OK
    python scripts/day0_smoke_test.py                       # must print RESULT: OK
    python -m arena.cli fetch --start 2025-01-01
    python -m arena.cli backtest --start 2026-03-02 --end 2026-09-30 --fresh

Run the local dashboard with `python -m arena.dashboard` and open http://127.0.0.1:8765.
It reads the paper/backtest ledgers and can run isolated historical replays from `data_cache/`.

PAPER TRADING ONLY. There is deliberately no broker connection in this code.
