"""Data layer: provider (network) + CSV cache (disk) + date-clipped reads (no lookahead)."""
import logging
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

log = logging.getLogger("arena.data")
COLS = ["open", "high", "low", "close", "volume"]


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Return df with lowercase OHLCV columns, tz-naive midnight DatetimeIndex, sorted, clean."""
    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    df = df[COLS]
    idx = pd.to_datetime(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    df.index = idx.normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna()
    df = df[(df["close"] > 0) & (df["open"] > 0)]
    return df


class YahooProvider:
    """Free, unofficial (yfinance). Personal use only. Can break or rate-limit without notice."""
    def __init__(self, pause_seconds: float = 1.0, retries: int = 3):
        self.pause, self.retries = pause_seconds, retries

    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        import yfinance as yf                                   # imported here so tests need no network lib
        last_err: Optional[Exception] = None
        for attempt in range(self.retries):
            try:
                df = yf.Ticker(symbol).history(start=start.isoformat(),
                                               end=(end + timedelta(days=1)).isoformat(),  # end is exclusive
                                               auto_adjust=True, actions=False)
                time.sleep(self.pause)
                if df is None or df.empty:
                    raise ValueError(f"empty result for {symbol}")
                return normalize(df)
            except Exception as e:                              # noqa: BLE001
                last_err = e
                wait = 5 * (3 ** attempt)                       # 5s, 15s, 45s
                log.warning("fetch %s failed (%s); retry in %ss", symbol, e, wait)
                time.sleep(wait)
        raise RuntimeError(f"giving up on {symbol}: {last_err}")


class DataStore:
    def __init__(self, cache_dir: str, provider=None):
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.provider = provider
        self._mem: Dict[str, pd.DataFrame] = {}

    def _path(self, symbol: str) -> Path:
        return self.dir / f"{symbol.replace('/', '_')}.csv"

    def load(self, symbol: str) -> pd.DataFrame:
        if symbol in self._mem:
            return self._mem[symbol]
        p = self._path(symbol)
        if p.exists():
            df = normalize(pd.read_csv(p, index_col=0, parse_dates=True))
        else:
            df = pd.DataFrame(columns=COLS, index=pd.DatetimeIndex([]))
        self._mem[symbol] = df
        return df

    def refresh(self, symbols: List[str], start: date, end: date) -> None:
        """Download [start, end] for each symbol and merge into the cache. Failures keep the old cache."""
        for s in symbols:
            try:
                new = self.provider.fetch(s, start, end)
            except Exception as e:                              # noqa: BLE001
                log.error("refresh failed for %s: %s (using cache)", s, e)
                continue
            merged = pd.concat([self.load(s), new])
            merged = merged[~merged.index.duplicated(keep="last")].sort_index()
            merged.to_csv(self._path(s))
            self._mem[s] = merged

    def history(self, symbol: str, end: date) -> pd.DataFrame:
        """NO-LOOKAHEAD: only rows dated <= end are ever returned."""
        return self.load(symbol).loc[:pd.Timestamp(end)]

    def open_price(self, symbol: str, day: date):
        df = self.load(symbol)
        ts = pd.Timestamp(day)
        return None if ts not in df.index else df.loc[ts, "open"]

    def trading_days(self, symbols: List[str], start: date, end: date) -> List[pd.Timestamp]:
        """Union of dates present in the cache for the given symbols (TSX holidays are simply absent)."""
        days = set()
        for s in symbols:
            idx = self.load(s).loc[pd.Timestamp(start):pd.Timestamp(end)].index
            days |= set(idx)
        return sorted(days)


def is_liquid(df: pd.DataFrame, min_dollar_volume: float = 1_000_000.0, window: int = 20) -> bool:
    if len(df) < window:
        return False
    return float((df["close"] * df["volume"]).iloc[-window:].mean()) >= min_dollar_volume
