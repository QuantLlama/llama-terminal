import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from torch.utils.data import Dataset, DataLoader
import torch
import yfinance as yf

# ── Indicator backend ────────────────────────────────────────────────────────
# Prefer TA-Lib (fast, battle-tested, no edge-case NaN). Fall back to pure
# pandas when TA-Lib is not installed.
try:
    import talib as _talib
    _HAS_TALIB = True
except (ImportError, OSError):
    _HAS_TALIB = False
    _talib = None


def _rsi(close, period=14):
    if _HAS_TALIB:
        return pd.Series(_talib.RSI(close.values.astype(float), timeperiod=period),
                         index=close.index)
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _adx(high, low, close, period=14):
    if _HAS_TALIB:
        return pd.Series(_talib.ADX(high.values.astype(float),
                                    low.values.astype(float),
                                    close.values.astype(float),
                                    timeperiod=period), index=close.index)
    # Pure-pandas ADX – safe against div-by-zero
    up   = high.diff()
    down = -low.diff()
    plus_dm  = np.where((up > down) & (up > 0),  up,   0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = pd.concat([high - low,
                    (high - close.shift()).abs(),
                    (low  - close.shift()).abs()], axis=1).max(axis=1)
    atr_s = tr.rolling(period).mean()
    plus_di  = 100 * (pd.Series(plus_dm,  index=high.index).rolling(period).mean() / atr_s)
    minus_di = 100 * (pd.Series(minus_dm, index=high.index).rolling(period).mean() / atr_s)
    di_sum   = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / di_sum
    dx = dx.fillna(0)
    return dx.rolling(period).mean()


def _atr(high, low, close, period=14):
    if _HAS_TALIB:
        return pd.Series(_talib.ATR(high.values.astype(float),
                                    low.values.astype(float),
                                    close.values.astype(float),
                                    timeperiod=period), index=close.index)
    tr = pd.concat([high - low,
                    (high - close.shift()).abs(),
                    (low  - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ── Dataset ──────────────────────────────────────────────────────────────────

class FuturesDataset(Dataset):
    """Sliding-window time-series dataset.

    Each sample is (seq[t : t+L], seq[t+1 : t+L+1]) so the model learns
    to predict the next time step given the current window.
    """

    def __init__(self, data, seq_length):
        self.data       = torch.FloatTensor(data)
        self.seq_length = seq_length

    def __len__(self):
        return len(self.data) - self.seq_length

    def __getitem__(self, index):
        return (self.data[index : index + self.seq_length],
                self.data[index + 1 : index + self.seq_length + 1])


# ── Data loading ─────────────────────────────────────────────────────────────

#: Symbols Yahoo publishes under a different code than the trading platform.
#: Checked before the crypto rule, because XAUUSD also ends in USD.
YAHOO_ALIASES = {
    "XAUUSD": "GC=F",   # gold spot -> gold futures
    "XAGUSD": "SI=F",   # silver spot -> silver futures
    "XPTUSD": "PL=F",   # platinum -> platinum futures
    "XPDUSD": "PA=F",   # palladium -> palladium futures
}

#: Stable quotes a platform appends to a crypto base asset.
STABLE_QUOTES = ("USDT", "USDC", "FDUSD", "TUSD", "BUSD", "USD")


def yahoo_symbol(ticker):
    """Translate a platform symbol into the one Yahoo Finance publishes.

    The wizard sends the symbol the chart is showing, so crypto arrives as
    ``BTCUSDT`` / ``BTC/USDT:USDT`` (Yahoo knows it as ``BTC-USD``) and MT5 metal
    spot pairs arrive as ``XAUUSD`` (Yahoo publishes ``GC=F``). Passing those
    through untouched made the download answer "Quote not found for symbol" and
    every training run died before the first epoch.
    """
    if not ticker or not ticker.strip():
        return ticker
    raw = ticker.strip()
    upper = raw.upper()

    # Already a Yahoo symbol: index caret, explicit quote suffix (=F, =X) or a
    # hyphenated pair such as BTC-USD. Returning early also keeps this idempotent.
    if upper.startswith("^") or "=" in upper or "-" in upper:
        return raw

    # Broker decorations: EURUSD.r, BTCUSDT.P. The settle suffix of a perpetual
    # contract is not part of the base pair: BTC/USDT:USDT is BTC/USDT.
    base = upper.split(".", 1)[0].split(":", 1)[0]

    if base in YAHOO_ALIASES:
        return YAHOO_ALIASES[base]

    compact = base.replace("/", "").replace(":", "").replace("_", "")
    for quote in STABLE_QUOTES:
        if compact.endswith(quote) and len(compact) > len(quote):
            return f"{compact[:-len(quote)]}-USD"
    return raw


def load_data(ticker, period='2y', interval='1h'):
    """Download OHLCV data from Yahoo Finance with automatic period adjustment."""
    symbol = yahoo_symbol(ticker)
    print(f"Downloading data for {ticker}..." if symbol == ticker
          else f"Downloading data for {ticker} (Yahoo: {symbol})...")

    intraday_intervals = ['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h']
    if interval in intraday_intervals:
        if period in ['1y', '2y', '5y', '10y', 'max']:
            print(f"Warning: Intraday data ({interval}) limited to last 60 days "
                  f"by source. Adjusting period from {period} to 59d.")
            period = "59d"

    df = yf.download(symbol, period=period, interval=interval, progress=False)

    if df.empty:
        raise ValueError(
            f"No data found for ticker {ticker}. "
            "Check internet connection or ticker symbol.")

    # Flatten MultiIndex columns that yfinance sometimes returns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if 'Close' not in df.columns:
        if 'Adj Close' in df.columns:
            df['Close'] = df['Adj Close']
        else:
            raise ValueError("Data does not contain a 'Close' price column.")

    print(f"Data loaded successfully: {len(df)} records.")
    return df


# ── Pre-processing ────────────────────────────────────────────────────────────
# Design rule: ALL column computations are guarded by "only if not already
# present", so calling this function twice on the same df is safe.

# Re-export for existing preprocessing consumers.
from src.models.artifacts import FEATURE_COLS


def preprocess_data(df, seq_length):
    """Compute features, scale to [-1, 1] and return a FuturesDataset + scaler."""

    # ── 1. Technical indicators (skip if already computed) ───────────────────
    if len(df) > 30:
        if 'RSI' not in df.columns:
            df['RSI'] = _rsi(df['Close'])
        if 'ADX' not in df.columns:
            df['ADX'] = _adx(df['High'], df['Low'], df['Close'])
        if 'ATR' not in df.columns:
            df['ATR'] = _atr(df['High'], df['Low'], df['Close'])
        if 'EMA' not in df.columns:
            df['EMA'] = df['Close'].ewm(span=20, adjust=False).mean()

    # ── 2. Log returns (skip if already computed) ────────────────────────────
    if 'Log_Ret_Close' not in df.columns:
        df['Log_Ret_Close'] = np.log(df['Close'] / df['Close'].shift(1))
    if 'Log_Ret_High' not in df.columns:
        df['Log_Ret_High']  = np.log(df['High']  / df['High'].shift(1))
    if 'Log_Ret_Low' not in df.columns:
        df['Log_Ret_Low']   = np.log(df['Low']   / df['Low'].shift(1))
    if 'Log_Vol' not in df.columns:
        df['Log_Vol'] = np.log1p(df['Volume'])

    # ── 3. Remove Inf / NaN ──────────────────────────────────────────────────
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=FEATURE_COLS)

    # ── 4. Fill any missing feature columns with 0 ───────────────────────────
    for col in FEATURE_COLS:
        if col not in df.columns:
            print(f"Warning: feature '{col}' missing – filling with 0.")
            df[col] = 0.0

    # ── 5. Final NaN guard before scaling ───────────────────────────────────
    raw = df[FEATURE_COLS].values.astype(np.float32)
    if np.any(~np.isfinite(raw)):
        n_bad = np.sum(~np.isfinite(raw))
        print(f"Warning: {n_bad} non-finite values found after cleaning – "
              "replacing with 0.")
        raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)

    # ── 6. Scale to [-1, 1] and build dataset ───────────────────────────────
    scaler  = MinMaxScaler(feature_range=(-1, 1))
    data    = scaler.fit_transform(raw)

    # Paranoid final check
    if np.any(np.isnan(data)):
        print("CRITICAL: NaN still present after scaling – replacing with 0.")
        data = np.nan_to_num(data, nan=0.0)

    dataset = FuturesDataset(data, seq_length)
    return dataset, scaler