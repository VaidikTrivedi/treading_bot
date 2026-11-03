"""OPTIONAL fallback provider (Alpha Vantage). UNVERIFIED for TSX symbols: run scripts/day0_alpha_vantage.py first.
Free tier is small (about 25 requests/day per third-party reviews), so use it only for the daily top-up
(outputsize=compact returns about the latest 100 daily bars) and keep yfinance for the long warm-up download."""
import io
import time
from datetime import date

import pandas as pd

from arena.market.data import normalize


class AlphaVantageProvider:
    def __init__(self, api_key: str, symbol_map: dict, pause_seconds: float = 13.0):
        self.key, self.map, self.pause = api_key, symbol_map, pause_seconds   # 13s keeps us under 5 calls/min

    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        import requests
        av_symbol = self.map.get(symbol, symbol)
        r = requests.get("https://www.alphavantage.co/query", timeout=30, params=dict(
            function="TIME_SERIES_DAILY", symbol=av_symbol, outputsize="compact",
            datatype="csv", apikey=self.key))
        r.raise_for_status()
        if r.text.lstrip().startswith("{"):                     # JSON error / rate-limit message instead of CSV
            raise RuntimeError(f"Alpha Vantage said: {r.text[:200]}")
        df = pd.read_csv(io.StringIO(r.text), index_col="timestamp", parse_dates=True)
        time.sleep(self.pause)
        return normalize(df).loc[pd.Timestamp(start):pd.Timestamp(end)]
