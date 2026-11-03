"""OPTIONAL. Tests whether your free Alpha Vantage key returns Toronto-listed symbols and in which format.
Run:  ALPHA_VANTAGE_KEY=yourkey python scripts/day0_alpha_vantage.py
Read the output, then fill `av_symbol_map` in config.yaml with the format that returned data."""
import os, sys
from datetime import date, timedelta
sys.path.insert(0, ".")
from arena.market.alpha_vantage import AlphaVantageProvider  # noqa: E402

key = os.environ.get("ALPHA_VANTAGE_KEY")
if not key:
    sys.exit("Set ALPHA_VANTAGE_KEY first (free key from alphavantage.co).")
for candidate in ["RY.TRT", "TSX:RY", "RY.TO"]:               # try three possible formats, one call each
    try:
        df = AlphaVantageProvider(key, {}).fetch(candidate, date.today() - timedelta(days=30), date.today())
        print(f"{candidate}: {len(df)} rows, last {df.index[-1].date() if len(df) else 'n/a'}")
    except Exception as e:  # noqa: BLE001
        print(f"{candidate}: no data -> {str(e)[:120]}")
