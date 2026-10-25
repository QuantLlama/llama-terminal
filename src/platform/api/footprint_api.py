import time
import logging
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query, HTTPException
import pandas as pd
import numpy as np
from src.live.connector import get_mt5_connector
from src.services.market_data_engine.engine import get_market_data_engine
from src.services.auth import get_authenticated_user_id
import os
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/footprint", tags=["Footprint Chart"])
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
def _get_tick_size(symbol: str) -> float:
    try:
        import MetaTrader5 as mt5
        info = mt5.symbol_info(symbol)
        if info:
            return info.trade_tick_size if info.trade_tick_size > 0 else info.point
    except Exception:
        pass
    return 0.25
def _get_digits(symbol: str) -> int:
    try:
        import MetaTrader5 as mt5
        info = mt5.symbol_info(symbol)
        if info:
            return info.digits
    except Exception:
        pass
    return 2
def _round_to_tick(price: float, tick_size: float, digits: int) -> float:
    if tick_size <= 0:
        return round(price, digits)
    return round(round(price / tick_size) * tick_size, digits)
def _timeframe_to_seconds(tf: str) -> int:
    mapping = {
        "1m": 60,    "5m": 300,   "10m": 600,
        "15m": 900,  "30m": 1800, "1h": 3600,
        "4h": 14400, "1d": 86400,
    }
    return mapping.get(tf, 60)
def _resolve_volume_column(df: pd.DataFrame) -> str:
    if "volume_real" in df.columns and df["volume_real"].sum() > 0:
        return "volume_real"
    return "volume"
def _compute_incremental_volume(df: pd.DataFrame, v_col: str, group_col: str) -> pd.Series:
    raw = df[v_col].astype(float)
    def _group_diff(g: pd.Series) -> pd.Series:
        d = g.diff()
        d.iloc[0] = g.iloc[0]
        reset_mask = d < 0
        d[reset_mask] = g[reset_mask]
        return d
    result = df.groupby(group_col)[v_col].transform(_group_diff)
    neg = result < 0
    result[neg] = raw[neg]
    return result
def _classify_sides(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["is_buy"]  = (df["flags"] & 32) > 0
    df["is_sell"] = (df["flags"] & 64) > 0
    ambiguous = (df["v"] > 0) & ~(df["is_buy"] | df["is_sell"])
    if ambiguous.any():
        prev_last = df["last"].shift(1).fillna(df["last"])
        df.loc[ambiguous, "is_buy"]  =  df.loc[ambiguous, "last"] >= prev_last.loc[ambiguous]
        df.loc[ambiguous, "is_sell"] =  df.loc[ambiguous, "last"] <  prev_last.loc[ambiguous]
    return df
def _aggregate_levels(
    group: pd.DataFrame,
    tick_size: float,
    digits: int,
    max_levels: int = 150,
) -> tuple[list, float, float, float]:
    if group.empty or group["v"].sum() == 0:
        return [], 0.0, 0.0, 0.0
    g = group.copy()
    if tick_size > 0:
        g["price_level"] = (g["last"] / tick_size).round() * tick_size
    else:
        g["price_level"] = g["last"].round(digits)
    g["price_level"] = g["price_level"].round(digits)
    g["v_bid"] = g["v"] * g["is_sell"].astype(float)
    g["v_ask"] = g["v"] * g["is_buy"].astype(float)
    agg = (
        g.groupby("price_level", sort=True)
        .agg(bid=("v_bid", "sum"), ask=("v_ask", "sum"), total=("v", "sum"))
        .reset_index()
    )
    levels   = []
    poc_vol  = 0.0
    poc_price= 0.0
    delta    = 0.0
    for _, row in agg.iterrows():
        p = float(row["price_level"])
        b = float(row["bid"])
        a = float(row["ask"])
        t = float(row["total"])
        if t <= 0:
            continue
        levels.append({"price": round(p, digits), "bid": round(b, digits), "ask": round(a, digits), "total": round(t, digits)})
        delta += a - b
        if t > poc_vol:
            poc_vol   = t
            poc_price = p
    if len(levels) > max_levels:
        poc_lvl    = next((l for l in levels if abs(l["price"] - round(poc_price, digits)) < 1e-9), None)
        others     = [l for l in levels if l is not poc_lvl]
        top_others = sorted(others, key=lambda x: x["total"], reverse=True)[: max_levels - 1]
        if poc_lvl:
            top_others.append(poc_lvl)
        levels = sorted(top_others, key=lambda x: x["price"])
    return levels, round(poc_price, digits), round(delta, digits), round(agg["total"].sum(), digits)
def _ticks_to_footprint_map(
    ticks_df: pd.DataFrame,
    tf_seconds: int,
    tick_size: float,
    digits: int,
) -> dict:
    if ticks_df is None or ticks_df.empty:
        return {}
    df = ticks_df.copy()
    df["candle_time"] = ((df["time"] // tf_seconds) * tf_seconds).astype(int)
    v_col = _resolve_volume_column(df)
    df["v"] = _compute_incremental_volume(df, v_col, "candle_time")
    df = df[df["v"] > 0].copy()
    if df.empty:
        return {}
    df = _classify_sides(df)
    result = {}
    for ts, group in df.groupby("candle_time"):
        levels, poc, delta, _ = _aggregate_levels(group, tick_size, digits)
        if not levels:
            continue
        result[int(ts)] = {
            "levels":   levels,
            "poc":      poc,
            "delta":    delta,
            "fidelity": "high",
        }
    return result
def _make_fallback_candle(c: pd.Series, tick_size: float, digits: int) -> dict:
    import math, random
    vol   = float(c.get("real_volume") or c.get("tick_volume", 0))
    high  = float(c["high"])
    low   = float(c["low"])
    close = float(c["close"])
    open_ = float(c["open"])
    levels     = []
    price_range = high - low
    actual_tick = tick_size if tick_size > 0 else 0.01
    if price_range > 0 and vol > 0:
        num_steps = min(int(price_range / actual_tick) + 1, 40)
        seed = int(c.get("time", 0)) % 10000
        rng = random.Random(seed)
        center_norm = (close - low) / price_range if price_range > 0 else 0.5
        sigma = 0.30 + rng.uniform(-0.08, 0.08)  
        raw_weights = []
        for i in range(num_steps):
            pos_norm = i / max(num_steps - 1, 1)
            gauss = math.exp(-0.5 * ((pos_norm - center_norm) / sigma) ** 2)
            noised = gauss * (0.85 + rng.random() * 0.30)
            raw_weights.append(max(1e-6, noised))
        total_w = sum(raw_weights)
        move_ratio = abs(close - open_) / max(price_range, 1e-9)
        base_bias = 0.55 + 0.15 * move_ratio  
        is_bull = close >= open_
        for i, w in enumerate(raw_weights):
            p = _round_to_tick(low + i * (price_range / num_steps), actual_tick, digits)
            vol_at_level = vol * (w / total_w)
            pos_norm = i / max(num_steps - 1, 1)
            proximity_to_close = 1.0 - abs(pos_norm - center_norm)
            level_bias = base_bias * (0.7 + 0.3 * proximity_to_close)
            level_bias = min(0.85, level_bias)  
            if is_bull:
                bias_buy  = level_bias
                bias_sell = 1.0 - level_bias
            else:
                bias_sell = level_bias
                bias_buy  = 1.0 - level_bias
            bid_vol = round(vol_at_level * bias_sell, max(digits, 4))
            ask_vol = round(vol_at_level * bias_buy,  max(digits, 4))
            tot_vol = round(vol_at_level, max(digits, 4))
            levels.append({
                "price": p,
                "bid":   bid_vol,
                "ask":   ask_vol,
                "total": tot_vol,
            })
    move  = close - open_
    delta = round(vol * (0.4 * (move / max(price_range, 1e-9))), max(digits, 4))
    poc_price = close  
    if levels:
        poc_price = max(levels, key=lambda x: x["total"])["price"]
    return {
        "time":     int(c["time"]),
        "open":     open_,
        "high":     high,
        "low":      low,
        "close":    close,
        "volume":   vol,
        "levels":   sorted(levels, key=lambda x: x["price"]),
        "poc":      poc_price,
        "delta":    delta,
        "fidelity": "fallback",
    }

def _trades_to_footprint_map(
    trades: List[Dict[str, Any]],
    tf_seconds: int,
    tick_size: float,
    digits: int,
) -> dict:
    if not trades:
        return {}

    rows = []
    for t in trades:
        try:
            ts = float(t.get("timestamp") or 0)
            if ts <= 0:
                continue
            if ts > 1e10:
                ts /= 1000.0
            price = float(t.get("price") or 0)
            amount = float(t.get("amount") or t.get("size") or t.get("last_size") or 0)
            if price <= 0 or amount <= 0:
                continue
            side = str(t.get("side") or "").lower()
            rows.append({
                "time": int(ts),
                "last": price,
                "v": amount,
                "side": side,
            })
        except Exception:
            continue

    if not rows:
        return {}

    df = pd.DataFrame(rows)
    df["candle_time"] = ((df["time"] // tf_seconds) * tf_seconds).astype(int)
    df["is_buy"] = df["side"].isin(["buy", "long"])
    df["is_sell"] = df["side"].isin(["sell", "short"])
    ambiguous = ~(df["is_buy"] | df["is_sell"])
    if ambiguous.any():
        prev_last = df["last"].shift(1).fillna(df["last"])
        df.loc[ambiguous, "is_buy"] = df.loc[ambiguous, "last"] >= prev_last.loc[ambiguous]
        df.loc[ambiguous, "is_sell"] = ~df.loc[ambiguous, "is_buy"]
    result = {}
    for ts, group in df.groupby("candle_time"):
        levels, poc, delta, total = _aggregate_levels(
            group.rename(columns={"v": "v", "last": "last"}),
            tick_size,
            digits,
        )
        if not levels:
            continue
        # Rebuild from grouped raw trades since _aggregate_levels expects v/last/is_buy/is_sell.
        # The group already has those columns.
        result[int(ts)] = {
            "levels": levels,
            "poc": poc,
            "delta": delta,
            "fidelity": "high",
            "volume": total,
        }
    return result
_footprint_cache: dict = {}
_crypto_trade_footprint_cache: dict = {}
_backfill_tasks: set = set()

def _get_crypto_footprint_ohlcv_limit(exchange_id: str, requested_limit: int) -> int:
    exchange_id = (exchange_id or "").lower()
    if exchange_id == "binance":
        return min(requested_limit, 1000)
    return min(requested_limit, 600)

async def get_mt5_footprint(symbol: str, timeframe: str, limit: int) -> list:
    import MetaTrader5 as mt5
    connector = get_mt5_connector()
    if not connector.connect():
        raise HTTPException(status_code=503, detail="MT5 not connected")
    tick_size  = _get_tick_size(symbol)
    digits     = _get_digits(symbol)
    tf_seconds = _timeframe_to_seconds(timeframe)
    now_ts     = time.time()
    cache_key = f"{symbol}_{timeframe}"
    cache_entry = _footprint_cache.get(cache_key)
    ttl = 0.1 if tf_seconds <= 60 else 0.5
    if cache_entry and (now_ts - cache_entry["last_update"]) < ttl:
        return cache_entry["candles"][-limit:]
    tf_map = {
        "1m":  mt5.TIMEFRAME_M1,  "5m":  mt5.TIMEFRAME_M5,
        "10m": mt5.TIMEFRAME_M10, "15m": mt5.TIMEFRAME_M15,
        "30m": mt5.TIMEFRAME_M30, "1h":  mt5.TIMEFRAME_H1,
        "4h":  mt5.TIMEFRAME_H4,  "1d":  mt5.TIMEFRAME_D1,
    }
    mt5_tf = tf_map.get(timeframe, mt5.TIMEFRAME_M1)
    symbol_info = connector.symbol_info(symbol)
    if symbol_info is None:
        return []
    if not symbol_info.visible:
        connector.symbol_select(symbol, True)
    rates = connector.copy_rates_from_pos(symbol, mt5_tf, 0, limit)
    if rates is None or len(rates) == 0:
        return []
    candles_df = pd.DataFrame(rates)
    fidelity_limit = 15  
    if cache_entry and len(cache_entry["candles"]) > 0:
        last_cached_ts = cache_entry["candles"][-1]["time"]
        fetch_start_ts = last_cached_ts - (tf_seconds * 2)
    else:
        n_recent       = min(len(candles_df), fidelity_limit)
        fetch_start_ts = int(candles_df["time"].iloc[-n_recent])
    has_enough_fidelity = (
        cache_entry
        and len([c for c in cache_entry.get("candles", []) if c.get("fidelity") == "high"])
        > limit * 0.5
    )
    if not has_enough_fidelity:
        asyncio.create_task(
            backfill_mt5_history(symbol, timeframe, limit, tf_seconds, tick_size, digits)
        )
    last_ts  = int(candles_df["time"].iloc[-1]) + tf_seconds + 1
    start_dt = datetime.utcfromtimestamp(
        max(int(candles_df["time"].iloc[0]), fetch_start_ts)
    )
    end_dt   = datetime.utcfromtimestamp(last_ts)
    raw_ticks = connector.copy_ticks_range(symbol, start_dt, end_dt, mt5.COPY_TICKS_ALL)
    ticks_df  = pd.DataFrame(raw_ticks) if raw_ticks is not None and len(raw_ticks) > 0 else pd.DataFrame()
    tick_groups = _ticks_to_footprint_map(ticks_df, tf_seconds, tick_size, digits)
    cached_map = {c["time"]: c for c in cache_entry["candles"]} if cache_entry else {}
    result     = []
    for _, c in candles_df.iterrows():
        ts   = int(c["time"])
        data = tick_groups.get(ts)
        if data:
            result.append({
                "time":     ts,
                "open":     float(c["open"]),
                "high":     float(c["high"]),
                "low":      float(c["low"]),
                "close":    float(c["close"]),
                "volume":   float(c.get("real_volume") or c.get("tick_volume", 0)),
                "levels":   data["levels"],
                "poc":      data["poc"],
                "delta":    data["delta"],
                "fidelity": "high",
            })
        elif ts in cached_map:
            result.append(cached_map[ts])
        else:
            result.append(_make_fallback_candle(c, tick_size, digits))
    _footprint_cache[cache_key] = {
        "timeframe":   timeframe,
        "last_update": now_ts,
        "candles":     result[-1000:],
    }
    return result[-limit:]
async def get_crypto_footprint(
    symbol: str, timeframe: str, limit: int, *, user_id: str
) -> list:
    """Build crypto footprint candles from one tenant's master account only."""
    from src.live.crypto_connector import get_connector
    from src.services.crypto_manager import get_crypto_manager
    manager = get_crypto_manager()
    accounts = manager.get_accounts(user_id=user_id)
    master = next((acc for acc in accounts if acc.get("is_master")), None)
    if not master and accounts:
        master = accounts[0]
    if not master:
        return []
    connector = await asyncio.to_thread(
        get_connector, master["id"], user_id=user_id
    )
    if not connector:
        return []
    resolved_symbol = None
    try:
        resolved_symbol = connector._resolve_sym(symbol)
    except Exception:
        resolved_symbol = None
    if not resolved_symbol:
        sym_up = (symbol or "").upper().replace("/", "").replace(":", "").replace("-", "")
        if 'BTC' in sym_up:
            sym_up = sym_up.replace('BTC', 'XBT')
        if sym_up.endswith("USDT") or sym_up.endswith("USD"):
            resolved_symbol = "XBTUSD"
        elif sym_up.endswith("ETH"):
            resolved_symbol = "ETHUSD"
        else:
            resolved_symbol = symbol

    info = connector.get_symbol_info(resolved_symbol)
    tick_size = info.get('tick_size', 0.01) if info else 0.01
    digits = info.get('digits', 2) if info else 2
    tf_seconds = _timeframe_to_seconds(timeframe)
    trade_map = {}
    trade_cache_key = f"{master['id']}:{resolved_symbol}:{timeframe}"
    now_ts = time.time()
    cached_trades = _crypto_trade_footprint_cache.get(trade_cache_key)
    if cached_trades and now_ts - cached_trades.get("ts", 0) < 5.0:
        trade_map = cached_trades.get("map", {})
    else:
        # Do not call the exchange trades endpoint from footprint. The live tape
        # already owns that polling path and stores recent trades in the market
        # data engine. Reusing the local buffer avoids duplicate polling.
        engine = get_market_data_engine()
        trades = engine.get_recent_trades(symbol, 250) or engine.get_recent_trades(resolved_symbol, 250)
        trade_map = _trades_to_footprint_map(trades, tf_seconds, tick_size, digits)
        _crypto_trade_footprint_cache[trade_cache_key] = {"ts": now_ts, "map": trade_map}

    ohlcv_limit = _get_crypto_footprint_ohlcv_limit(getattr(connector, "exchange_id", ""), limit)
    ohlcv = await asyncio.to_thread(connector.get_ohlcv, resolved_symbol, timeframe, limit=ohlcv_limit)
    if not ohlcv:
        return []
    result = []
    for bar in ohlcv:
        try:
            ts_ms, o, h, l, c, v = bar
            ts = int(ts_ms / 1000)
            trade_fp = trade_map.get(ts)
            s_bar = pd.Series({
                "time": ts,
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "real_volume": float(v)
            })
            candle = trade_fp if trade_fp else _make_fallback_candle(s_bar, tick_size, digits)
            candle.update({
                "time": ts,
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": float(v),
            })
            result.append(candle)
        except Exception:
            continue
    return result
@router.get("")
async def get_footprint(
    symbol:    str = Query(...,   description="Symbol to fetch footprint for"),
    timeframe: str = Query("1m", description="Candle timeframe"),
    limit:     int = Query(100,  description="Number of candles", ge=1, le=2000),
    platform:  Optional[str] = Query(None, description="Target platform"),
    user_id:   str = Depends(get_authenticated_user_id),
):
    try:
        target_platform = (platform or "").lower().strip() or "mt5"
        s_upper = symbol.upper()
        crypto_bases = ["BTC", "XBT", "ETH", "SOL", "BNB", "XRP", "ADA", "DOT", "LINK", "AVAX"]
        if target_platform not in ("crypto", "mt5"):
            if any(base in s_upper for base in crypto_bases) and ("USDT" in s_upper or "USD" in s_upper or "/" in s_upper or ":" in s_upper):
                target_platform = "crypto"
        if target_platform == "crypto":
            target_platform = "crypto"
            c_tick_size = 0.01
            c_digits = 2
            candles = await get_crypto_footprint(
                symbol, timeframe, limit, user_id=user_id
            )
            return {
                "symbol":    symbol,
                "timeframe": timeframe,
                "platform":  "crypto",
                "tick_size": c_tick_size,
                "digits":    c_digits,
                "candles":   candles,
            }
        else:
            candles = await get_mt5_footprint(symbol, timeframe, limit)
            return {
                "symbol":    symbol,
                "timeframe": timeframe,
                "platform":  "mt5",
                "tick_size": _get_tick_size(symbol),
                "digits":    _get_digits(symbol),
                "candles":   candles,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FOOTPRINT] API Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
async def backfill_mt5_history(
    symbol:     str,
    timeframe:  str,
    limit:      int,
    tf_seconds: int,
    tick_size:  float,
    digits:     int,
):
    import MetaTrader5 as mt5
    cache_key = f"{symbol}_{timeframe}"
    if cache_key in _backfill_tasks:
        return
    _backfill_tasks.add(cache_key)
    try:
        await asyncio.sleep(2.5)
        connector = get_mt5_connector()
        if not connector.connect():
            logger.warning(f"[FOOTPRINT_BACKFILL] MT5 not connected for {symbol}")
            return
        CHUNK = 50  
        for offset in range(30, limit + 100, CHUNK):
            entry = _footprint_cache.get(cache_key)
            if not entry:
                break
            candles = entry.get("candles", [])
            if not candles:
                break
            max_idx = len(candles) - 1
            e_idx   = max_idx - offset
            s_idx   = max(0, e_idx - CHUNK + 1)
            if e_idx < 0:
                break
            target_indices = [
                i for i in range(s_idx, e_idx + 1)
                if candles[i].get("fidelity") != "high"
            ]
            if not target_indices:
                continue
            start_ts = min(candles[i]["time"] for i in target_indices)
            end_ts   = max(candles[i]["time"] for i in target_indices) + tf_seconds
            start_dt = datetime.utcfromtimestamp(start_ts)
            end_dt   = datetime.utcfromtimestamp(end_ts)
            raw_ticks = connector.copy_ticks_range(
                symbol, start_dt, end_dt, mt5.COPY_TICKS_ALL
            )
            if raw_ticks is None or len(raw_ticks) == 0:
                continue
            ticks_df    = pd.DataFrame(raw_ticks)
            chunk_results = _ticks_to_footprint_map(ticks_df, tf_seconds, tick_size, digits)
            entry = _footprint_cache.get(cache_key)
            if entry:
                ts_map = {c["time"]: i for i, c in enumerate(entry["candles"])}
                for ts_val, res in chunk_results.items():
                    if ts_val in ts_map:
                        entry["candles"][ts_map[ts_val]].update(res)
                entry["last_update"] = time.time()
            await asyncio.sleep(1.5)
    except Exception as e:
        logger.error(f"[FOOTPRINT_BACKFILL] Error for {symbol}: {e}", exc_info=True)
    finally:
        _backfill_tasks.discard(cache_key)
