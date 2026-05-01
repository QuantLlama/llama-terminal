import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from torch.utils.data import Dataset, DataLoader
import torch
import yfinance as yf
from src.utils.indicators import get_rsi, get_adx, get_atr, get_ema

class FuturesDataset(Dataset):
    def __init__(self, data, seq_length):
        self.data = torch.FloatTensor(data)
        self.seq_length = seq_length
    def __len__(self):
        return len(self.data) - self.seq_length
    def __getitem__(self, index):
        return (self.data[index:index+self.seq_length], self.data[index+1:index+self.seq_length+1])

def load_data(ticker, period='2y', interval='1h'):
    print(f"Downloading data for {ticker}...")
    intraday_intervals = ['1m', '2m', '5m', '10m', '15m', '30m', '60m', '90m', '1h']
    
    # yfinance does not support 10m directly — download 5m and resample
    resample_from_5m = False
    actual_interval = interval
    if interval == '10m':
        actual_interval = '5m'
        resample_from_5m = True
    
    if actual_interval in ['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h']:
        if period in ['1y', '2y', '5y', '10y', 'max']:
             print(f"Warning: Intraday data ({actual_interval}) limited to last 60 days by source. Adjusting period from {period} to 59d.")
             period = "59d"
    df = yf.download(ticker, period=period, interval=actual_interval, progress=False)
    if df.empty:
        raise ValueError(f"No data found for ticker {ticker}. Check internet connection or ticker symbol.")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if 'Close' not in df.columns:
         if 'Adj Close' in df.columns:
             df['Close'] = df['Adj Close']
         else:
             raise ValueError("Data does not contain 'Close' price column.")
    
    # Resample 5m -> 10m if needed
    if resample_from_5m and len(df) > 0:
        print(f"Resampling {len(df)} bars from 5m to 10m...")
        df = df.resample('10min').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()
        print(f"Resampled to {len(df)} bars (10m).")
    
    print(f"Data loaded successfully: {len(df)} records.")
    return df

def preprocess_data(df, seq_length):
    if len(df) > 30:
        df['RSI'] = get_rsi(df['Close'])
        df['ADX'] = get_adx(df['High'], df['Low'], df['Close'])
        df['ATR'] = get_atr(df['High'], df['Low'], df['Close'])
    
    df['Log_Ret_Close'] = np.log(df['Close'] / df['Close'].shift(1))
    df['Log_Ret_High']  = np.log(df['High'] / df['High'].shift(1))
    df['Log_Ret_Low']   = np.log(df['Low'] / df['Low'].shift(1))
    df['Log_Vol'] = np.log1p(df['Volume'])
    df = df.dropna()
    
    scaler = MinMaxScaler(feature_range=(-1, 1))
    if 'EMA' not in df.columns:
        df['EMA'] = get_ema(df['Close'], period=20)
    
    cols = ['Log_Ret_Close', 'Log_Ret_High', 'Log_Ret_Low', 'Log_Vol', 'RSI', 'ADX', 'ATR', 'EMA']
    missing_cols = [c for c in cols if c not in df.columns]
    if missing_cols:
        print(f"Warning: Missing columns {missing_cols}. Filling with 0.")
        for c in missing_cols:
            df[c] = 0.0
            
    data = scaler.fit_transform(df[cols].values)
    dataset = FuturesDataset(data, seq_length)
    return dataset, scaler