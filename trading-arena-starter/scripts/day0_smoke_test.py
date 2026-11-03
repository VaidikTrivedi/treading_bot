"""Day-0 check: can this computer download TSX daily data from Yahoo (via yfinance)?
Run:  python scripts/day0_smoke_test.py
Exit code 0 = OK, 1 = problem (read the printed message)."""
import sys
from datetime import date, timedelta

sys.path.insert(0, ".")
from arena.market.data import YahooProvider  # noqa: E402

SYMBOLS = ["XIU.TO", "VFV.TO", "RY.TO"]
ok = True
prov = YahooProvider(pause_seconds=1.0, retries=2)
for s in SYMBOLS:
    try:
        df = prov.fetch(s, date.today() - timedelta(days=45), date.today())
        print(f"{s}: {len(df)} rows, last date {df.index[-1].date()}, last close {df['close'].iloc[-1]:.2f}")
        if len(df) < 15:
            print(f"  WARNING: expected about 20+ rows for 45 calendar days, got {len(df)}")
            ok = False
    except Exception as e:  # noqa: BLE001
        print(f"{s}: FAILED -> {e}")
        ok = False
print("RESULT:", "OK" if ok else "PROBLEM (see troubleshooting table in the guide)")
sys.exit(0 if ok else 1)
