import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta, timezone
import pytz
import os
import time
import traceback
import logging
logger = logging.getLogger(__name__)
import threading
class MT5Connector:
    _instance = None
    _lock = threading.RLock()
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MT5Connector, cls).__new__(cls)
            cls._instance.connected = False
            cls._instance.path = None
            cls._instance.timezone = pytz.timezone("Etc/UTC")
            cls._instance._book_subscriptions = set()
        return cls._instance
    def __init__(self):
        pass
    def connect(self, path=None):
        with self._lock:
            if self.connected:
                return True
            if path:
                self.path = path
            if self.path:
                init_res = mt5.initialize(path=self.path, timeout=2000)
            else:
                init_res = mt5.initialize()
            if not init_res:
                 err = mt5.last_error()
                 logger.error(f"MT5_CONN: Error in initialize(): {err}")
                 return False
            self.connected = True
            return True
    def shutdown(self):
        self.connected = False
        with self._lock:
            self._book_subscriptions.clear()
    def symbol_info(self, symbol):
        with self._lock:
            return mt5.symbol_info(symbol)
    def symbol_select(self, symbol, select=True):
        with self._lock:
            return mt5.symbol_select(symbol, select)
    def copy_ticks_range(self, symbol, date_from, date_to, flags):
        with self._lock:
            return mt5.copy_ticks_range(symbol, date_from, date_to, flags)
    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        with self._lock:
            return mt5.copy_rates_from_pos(symbol, timeframe, start_pos, count)
    def copy_rates_range(self, symbol, timeframe, date_from, date_to):
        with self._lock:
            return mt5.copy_rates_range(symbol, timeframe, date_from, date_to)
    def last_error(self):
        with self._lock:
            return mt5.last_error()
    def get_balance(self):
        with self._lock:
            if not self.connected:
                return 0.0
            info = mt5.account_info()
            return info.balance if info else 0.0
    def get_account_info(self):
        with self._lock:
            if not self.connected:
                return None
            info = mt5.account_info()
            if not info:
                return None
            return {
                "balance": info.balance,
                "equity": info.equity,
                "margin": info.margin,
                "margin_free": info.margin_free,
                "margin_level": info.margin_level,
                "leverage": info.leverage,
                "currency": info.currency,
                "profit": info.profit,
                "account": info.login,
                "name": info.name,
                "server": info.server,
                "platform": "mt5"
            }
    def get_equity(self):
        with self._lock:
            if not self.connected:
                return 0.0
            info = mt5.account_info()
            return info.equity if info else 0.0
    def get_latest_candles(self, symbol, timeframe=mt5.TIMEFRAME_M1, n=100):
        with self._lock:
            if not self.connected:
                pass 
            if not self.connected:
                init_res = mt5.initialize()
                if not init_res: return None
                self.connected = True
            if isinstance(timeframe, str):
                tf_map = {
                    "1m": mt5.TIMEFRAME_M1,
                    "5m": mt5.TIMEFRAME_M5,
                    "10m": mt5.TIMEFRAME_M10,
                    "15m": mt5.TIMEFRAME_M15,
                    "30m": mt5.TIMEFRAME_M30,
                    "1h": mt5.TIMEFRAME_H1,
                    "4h": mt5.TIMEFRAME_H4,
                    "1d": mt5.TIMEFRAME_D1,
                }
                timeframe = tf_map.get(timeframe, mt5.TIMEFRAME_M1)
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return None
            if not symbol_info.visible:
                if not mt5.symbol_select(symbol, True):
                    return None
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n)
            if rates is None:
                return None
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            if 'real_volume' in df.columns and df['real_volume'].sum() > 0:
                df['Volume'] = df['real_volume']
            else:
                df['Volume'] = df['tick_volume']
            df.rename(columns={
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close'
            }, inplace=True)
            return df[['time', 'Open', 'High', 'Low', 'Close', 'Volume']]
    def get_current_price(self, symbol):
        with self._lock:
            if not self.connected:
                if not self.connect():
                    return None
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
            return tick.last if tick.last > 0 else (tick.bid + tick.ask) / 2
    def get_recent_ticks(self, symbol, n=1000):
        with self._lock:
            if not self.connected:
                if not self.connect():
                    return None
            ticks = None
            if hasattr(mt5, 'copy_ticks_from_pos'):
                # Fast path: position-based tick copy (MT5 5.0.44+)
                ticks = mt5.copy_ticks_from_pos(symbol, 0, n, mt5.COPY_TICKS_ALL)
            else:
                # Fallback: copy_ticks_from_pos unavailable — request ticks
                # from a time window large enough to contain ~n ticks.
                window = timedelta(minutes=max(1, min(60, n // 100)))
                from_dt = datetime.now(timezone.utc) - window
                ticks = mt5.copy_ticks_from(symbol, from_dt, n, mt5.COPY_TICKS_ALL)
            if ticks is None or len(ticks) == 0:
                return None
            df = pd.DataFrame(ticks)
            if len(df) > n:
                df = df.tail(n).reset_index(drop=True)
            return df
    def get_ticks_since(self, symbol, from_msc):
        with self._lock:
            if not self.connected:
                return None
            from_seconds = from_msc / 1000.0
            from_dt = datetime.fromtimestamp(from_seconds, tz=timezone.utc)
            ticks = mt5.copy_ticks_from(symbol, from_dt, 1000, mt5.COPY_TICKS_ALL)
            if ticks is None or len(ticks) == 0:
                return None
            df = pd.DataFrame(ticks)
            if df.empty: return None
            if 'time_msc' in df.columns:
                df = df[df['time_msc'] > from_msc]
            return df if not df.empty else None
    def get_book_snapshot(self, symbol, limit=100):
        with self._lock:
            symbol = symbol.upper()
            if not self.connected:
                if not self.connect():
                    return None
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                if not mt5.symbol_select(symbol, True):
                    return None
                symbol_info = mt5.symbol_info(symbol) 
                if symbol_info is None: return None
            if not symbol_info.visible:
                if not mt5.symbol_select(symbol, True):
                    return None
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            log_path = os.path.join(project_root, "dom_debug.log")
            if not hasattr(self, '_log_path_announced') or not self._log_path_announced:
                 print(f"INFO: [MT5] DOM Engine using log: {log_path}")
                 self._log_path_announced = True
            if symbol not in self._book_subscriptions:
                if not mt5.market_book_add(symbol):
                    err = mt5.last_error()
                    if not hasattr(self, '_last_book_err_time') or (time.time() - self._last_book_err_time > 10):
                        print(f"WARN: [MT5] FAILED market_book_add for {symbol}: {err}")
                        self._last_book_err_time = time.time()
                    return None
                self._book_subscriptions.add(symbol)
            book = mt5.market_book_get(symbol)
            if book is None:
                with open(log_path, "a") as f:
                    f.write(f"{datetime.now()} [MT5] FAILED market_book_get for {symbol} (None returned): {mt5.last_error()}\n")
                return None
            if not book:
                with open(log_path, "a") as f:
                    f.write(f"{datetime.now()} [MT5] EMPTY BOOK for {symbol}\n")
                return None
            bids = []
            asks = []
            for entry in book:
                vol = getattr(entry, 'volume_real', 0)
                if float(vol) == 0:
                    vol = getattr(entry, 'volume', 0)
                if float(vol) == 0:
                    vol = getattr(entry, 'volume_dbl', 0)
                level = {
                    "price": float(entry.price), 
                    "size": float(vol), 
                    "count": 1 
                }
                if entry.type == 1: 
                    asks.append(level)
                elif entry.type == 2: 
                    bids.append(level)
            bids.sort(key=lambda x: x["price"], reverse=True)
            asks.sort(key=lambda x: x["price"])
            return {
                "symbol": symbol,
                "timestamp": time.time(),
                "bids": bids,
                "asks": asks
            }
    def get_positions(self, symbol=None, ticket=None):
        with self._lock:
            if not self.connected:
                return []
            if ticket is not None:
                positions = mt5.positions_get(ticket=int(ticket))
            elif symbol:
                positions = mt5.positions_get(symbol=symbol)
            else:
                positions = mt5.positions_get()
            if positions is None:
                return []
            return positions
    def get_pending_orders(self, symbol=None):
        with self._lock:
            if not self.connected:
                return []
            if symbol:
                orders = mt5.orders_get(symbol=symbol)
            else:
                orders = mt5.orders_get()
            if orders is None:
                return []
            result = []
            for o in orders:
                result.append({
                    "ticket": o.ticket,
                    "symbol": o.symbol,
                    "type": o.type, 
                    "volume": o.volume_current,
                    "price_open": o.price_open,
                    "sl": o.sl,
                    "tp": o.tp,
                    "time_setup": o.time_setup
                })
            return result
    def place_order(self, symbol, order_type=None, volume=None, sl=None, tp=None, price=None, mode="MKT", **kwargs):
        # Handle aliases for consistency
        if order_type is None:
            order_type = kwargs.get('side')
        if volume is None:
            volume = kwargs.get('amount')
            
        if order_type is None or volume is None:
            logger.error(f"MT5_ORDER: Missing required parameters: order_type={order_type}, volume={volume}")
            return None

        if not self.connected:
            return None
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return None
        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                return None
        mt5_action = mt5.TRADE_ACTION_DEAL
        mt5_type = 0
        order_price = 0.0
        tick = mt5.symbol_info_tick(symbol)
        if not tick: return None
        if mode == "MKT":
            mt5_action = mt5.TRADE_ACTION_DEAL
            if order_type == "BUY":
                mt5_type = mt5.ORDER_TYPE_BUY
                order_price = price if price and float(price) > 0 else tick.ask
            elif order_type == "SELL":
                mt5_type = mt5.ORDER_TYPE_SELL
                order_price = price if price and float(price) > 0 else tick.bid
        else:
            mt5_action = mt5.TRADE_ACTION_PENDING
            order_price = float(price) if price else 0.0
            normalized_mode = mode.upper()
            if normalized_mode == "LMT":
                normalized_mode = "LIMIT"
            elif normalized_mode == "STP":
                normalized_mode = "STOP"
            if order_type == "BUY":
                if normalized_mode == "LIMIT": 
                    mt5_type = mt5.ORDER_TYPE_BUY_LIMIT
                elif normalized_mode == "STOP": 
                    mt5_type = mt5.ORDER_TYPE_BUY_STOP
            elif order_type == "SELL":
                if normalized_mode == "LIMIT": 
                    mt5_type = mt5.ORDER_TYPE_SELL_LIMIT
                elif normalized_mode == "STOP": 
                    mt5_type = mt5.ORDER_TYPE_SELL_STOP
        point = symbol_info.point
        digits = symbol_info.digits
        tick_size = symbol_info.trade_tick_size
        if tick_size == 0: tick_size = point
        def round_to_tick(p):
            return round(round(p / tick_size) * tick_size, digits)
        if mode != "MKT":
            order_price = round_to_tick(order_price)
        filling_type = mt5.ORDER_FILLING_IOC if mode == "MKT" else mt5.ORDER_FILLING_RETURN
        if symbol_info.filling_mode:
            if mode == "MKT":
                if symbol_info.filling_mode & 1:  
                    filling_type = mt5.ORDER_FILLING_IOC
                elif symbol_info.filling_mode & 2:  
                    filling_type = mt5.ORDER_FILLING_FOK
                else:
                    if symbol_info.filling_mode & 4: filling_type = mt5.ORDER_FILLING_RETURN
            else:  
                if symbol_info.filling_mode & 4:  
                    filling_type = mt5.ORDER_FILLING_RETURN
                elif symbol_info.filling_mode & 2:  
                    filling_type = mt5.ORDER_FILLING_FOK
                elif symbol_info.filling_mode & 1:  
                    filling_type = mt5.ORDER_FILLING_IOC
        request = {
            "action": mt5_action,
            "symbol": symbol,
            "volume": float(volume),
            "type": mt5_type,
            "price": order_price,
            "deviation": 20,
            "magic": 234000,
            "comment": "QuantumGAN-AI",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_type,
        }
        if mode != "MKT":
             if sl is not None and float(sl) > 0:
                 request["sl"] = round_to_tick(float(sl))
             if tp is not None and float(tp) > 0:
                 request["tp"] = round_to_tick(float(tp))
        print(f"[CONNECTOR-DEBUG] Sending Request: {request}")
        result = mt5.order_send(request)
        if result and result.retcode == 10030: 
            print(f"[CONNECTOR-DEBUG] 10030 Error: Invalid Filling. Retrying with inverse...")
            if request["type_filling"] == mt5.ORDER_FILLING_IOC:
                request["type_filling"] = mt5.ORDER_FILLING_FOK
            elif request["type_filling"] == mt5.ORDER_FILLING_FOK:
                request["type_filling"] = mt5.ORDER_FILLING_IOC
            else:
                request["type_filling"] = mt5.ORDER_FILLING_IOC 
            print(f"[CONNECTOR-DEBUG] Retry Request: {request}")
            result = mt5.order_send(request)
        if result:
            print(f"[CONNECTOR-DEBUG] Result Retcode: {result.retcode}")
            print(f"[CONNECTOR-DEBUG] Result Comment: {result.comment}")
            if result.retcode != 10009:
                print(f"[CONNECTOR-DEBUG] Result Full: {result._asdict() if hasattr(result, '_asdict') else result}")
        else:
            print("[CONNECTOR-DEBUG] Result is NONE")
        if result and result.retcode == 10009 and mode == "MKT" and (sl is not None or tp is not None):
             rounded_sl = round_to_tick(float(sl)) if sl is not None and float(sl) > 0 else 0.0
             rounded_tp = round_to_tick(float(tp)) if tp is not None and float(tp) > 0 else 0.0
             if rounded_sl > 0 or rounded_tp > 0:
                 actual_fill = getattr(result, 'price', 0.0) or order_price
                 slippage = actual_fill - order_price   
                 if abs(slippage) > tick_size and order_price > 0:
                     print(f"[CONNECTOR-DEBUG] 2-STEP SLIPPAGE DETECTED: requested={order_price}, fill={actual_fill}, slip={slippage:.4f}")
                     if rounded_sl > 0:
                         rounded_sl = round_to_tick(rounded_sl + slippage)
                     if rounded_tp > 0:
                         rounded_tp = round_to_tick(rounded_tp + slippage)
                     print(f"[CONNECTOR-DEBUG] 2-STEP Adjusted SL={rounded_sl}, TP={rounded_tp}")
                 if order_type == "SELL":
                     if rounded_sl > 0 and rounded_sl <= actual_fill:
                         print(f"[CONNECTOR-DEBUG] 2-STEP WARN: SL {rounded_sl} is not above fill {actual_fill} for SELL \u2014 skipping SL")
                         rounded_sl = 0.0
                     if rounded_tp > 0 and rounded_tp >= actual_fill:
                         print(f"[CONNECTOR-DEBUG] 2-STEP WARN: TP {rounded_tp} is not below fill {actual_fill} for SELL \u2014 skipping TP")
                         rounded_tp = 0.0
                 elif order_type == "BUY":
                     if rounded_sl > 0 and rounded_sl >= actual_fill:
                         print(f"[CONNECTOR-DEBUG] 2-STEP WARN: SL {rounded_sl} is not below fill {actual_fill} for BUY \u2014 skipping SL")
                         rounded_sl = 0.0
                     if rounded_tp > 0 and rounded_tp <= actual_fill:
                         print(f"[CONNECTOR-DEBUG] 2-STEP WARN: TP {rounded_tp} is not above fill {actual_fill} for BUY \u2014 skipping TP")
                         rounded_tp = 0.0
                 if rounded_sl > 0 or rounded_tp > 0:
                     print(f"[CONNECTOR-DEBUG] 2-STEP MKT: Filled at {actual_fill}, now modifying to add SL={rounded_sl}, TP={rounded_tp}")
                     time.sleep(0.15) 
                     positions = mt5.positions_get(symbol=symbol)
                     pos_ticket = positions[0].ticket if positions else result.order
                     if pos_ticket:
                         mod_res = self.modify_position(pos_ticket, rounded_sl if rounded_sl > 0 else None, rounded_tp if rounded_tp > 0 else None, symbol=symbol)
                         if mod_res:
                             print(f"[CONNECTOR-DEBUG] 2-STEP Step 2 Result: {mod_res.retcode if hasattr(mod_res, 'retcode') else 'OK'}")
                             if hasattr(mod_res, 'retcode') and mod_res.retcode != 10009:
                                 print(f"[CONNECTOR-DEBUG] 2-STEP FAILED ({mod_res.retcode}): {getattr(mod_res, 'comment', '')}")
        return result
    def modify_order(self, ticket, price=0.0, sl=0.0, tp=0.0):
        if not self.connected: return False
        orders = mt5.orders_get(ticket=int(ticket))
        if orders is None or len(orders) == 0:
            return False
        order = orders[0]
        symbol = order.symbol
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            console.print(f"[red]S\u00edmbolo {symbol} no encontrado[/red]")
            return False
        def round_to_tick(value):
            if value is None or value == 0: return 0.0
            tick_size = symbol_info.trade_tick_size
            return round(value / tick_size) * tick_size
        rounded_price = round_to_tick(float(price)) if (price is not None and price > 0) else order.price_open
        rounded_sl = round_to_tick(float(sl)) if (sl is not None and sl > 0) else order.sl
        rounded_tp = round_to_tick(float(tp)) if (tp is not None and tp > 0) else order.tp
        request = {
            "action": mt5.TRADE_ACTION_MODIFY,
            "order": int(ticket),
            "price": rounded_price,
            "sl": rounded_sl,
            "tp": rounded_tp,
            "symbol": symbol,
            "type": order.type,
            "volume": order.volume_current
        }
        result = mt5.order_send(request)
        return result
    def modify_position(self, ticket, sl, tp, symbol=None):
        if not self.connected: 
            if not self.connect():
                return False
        positions = mt5.positions_get(ticket=int(ticket))
        if positions is None or len(positions) == 0:
            return False
        position = positions[0]
        pos_symbol = symbol or position.symbol
        symbol_info = mt5.symbol_info(pos_symbol)
        if symbol_info is None:
            return False
        point = symbol_info.point
        digits = symbol_info.digits
        tick_size = symbol_info.trade_tick_size
        if tick_size == 0: tick_size = point
        def round_to_tick(p):
            if p == 0: return 0.0
            return round(round(p / tick_size) * tick_size, digits)
        if sl is None:
            sl_rounded = position.sl  
        else:
            sl_rounded = round_to_tick(float(sl)) if float(sl) > 0 else 0.0
        if tp is None:
            tp_rounded = position.tp  
        else:
            tp_rounded = round_to_tick(float(tp)) if float(tp) > 0 else 0.0
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos_symbol,
            "position": int(ticket),
            "sl": sl_rounded,
            "tp": tp_rounded
        }
        result = mt5.order_send(request)
        return result
    def close_position(self, ticket, symbol=None, volume: float = None):
        if not self.connected:
            return False
        positions = mt5.positions_get(ticket=int(ticket))
        if positions is None or len(positions) == 0:
            from collections import namedtuple
            Result = namedtuple('OrderSendResult', ['retcode', 'comment', 'request'])
            return Result(10013, "Position not found", {}) 
        position = positions[0]
        symbol = position.symbol
        lot = float(volume) if (volume is not None and volume > 0) else position.volume
        if lot > position.volume:
            lot = position.volume
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            from collections import namedtuple
            Result = namedtuple('OrderSendResult', ['retcode', 'comment', 'request'])
            return Result(10014, f"Could not get tick data for {symbol}", {})
        if position.type == mt5.ORDER_TYPE_BUY:
            type_order = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            type_order = mt5.ORDER_TYPE_BUY
            price = tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": type_order,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": 234000,
            "comment": "QuantumGAN-Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        return result
    def delete_order(self, ticket):
        if not self.connected:
            return False
        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": int(ticket)
        }
        result = mt5.order_send(request)
        return result
    def get_deals(self, date_from=None, date_to=None):
        with self._lock:
            try:
                if not self.connected:
                    if not self.connect(): 
                        logger.error("MT5_HISTORY: Failed to connect to terminal.")
                        return []
                if date_to is None:
                    date_to = datetime.now() + timedelta(days=1)
                if date_from is None:
                    date_from = datetime.now() - timedelta(days=365*5)
                df_ts = date_from.timestamp() if hasattr(date_from, 'timestamp') else date_from
                dt_ts = date_to.timestamp() if hasattr(date_to, 'timestamp') else date_to
                
                # Fetch a huge window because the frontend expects UTC timestamps
                # We will convert broker time to UTC so the frontend can filter accurately!
                five_years_ago = (datetime.now() - timedelta(days=365 * 5)).timestamp()
                query_from = 0 if df_ts < five_years_ago else df_ts - 86400 * 2 # buffer for tz
                
                deals = mt5.history_deals_get(int(query_from), int(dt_ts + 86400 * 2))
                if deals is None or len(deals) == 0:
                    d_from_huge = datetime.now() - timedelta(days=365 * 5)
                    deals = mt5.history_deals_get(int(d_from_huge.timestamp()), int(dt_ts + 86400 * 2))
                if deals is None:
                    return []
                    
                # Calculate Broker Timezone Offset to true UTC
                import time
                sys_utc = int(time.time())
                broker_now = 0
                symbols = mt5.symbols_get()
                if symbols:
                    for s in symbols[:20]:
                        tick = mt5.symbol_info_tick(s.name)
                        if tick and tick.time > broker_now:
                            broker_now = tick.time
                            
                offset = 0
                if broker_now > 0:
                    raw_diff = broker_now - sys_utc
                    # If weekend, the tick might be from Friday. 
                    # We can use modulo 1 week if we really need to, but let's just 
                    # use datetime to get the hours difference if it's within 24h
                    if abs(raw_diff) < 86400 * 2:
                        offset = round(raw_diff / 1800) * 1800
                    else:
                        # Fallback for weekends: assume offset hasn't changed drastically
                        # We just take raw_diff modulo 24 hours
                        day_diff = raw_diff % 86400
                        if day_diff > 43200: day_diff -= 86400
                        offset = round(day_diff / 1800) * 1800
                        
                result = []
                for d in deals:
                    true_utc_time = d.time - offset
                    result.append({
                        "ticket": d.ticket,
                        "order": d.order,
                        "time": true_utc_time,
                        "time_msc": d.time_msc - (offset * 1000),
                        "type": d.type, 
                        "entry": d.entry, 
                        "magic": d.magic,
                        "position_id": d.position_id,
                        "reason": d.reason,
                        "volume": d.volume,
                        "price": d.price,
                        "commission": d.commission,
                        "swap": d.swap,
                        "profit": getattr(d, 'profit', 0.0) or 0.0,
                        "symbol": d.symbol
                    })
                return result
            except Exception as e:
                logger.error(f"MT5_HISTORY: {e}")
                return []
    def get_daily_pnl(self):
        with self._lock:
            if not self.connected:
                if not self.connect(): return 0.0
            
            import json
            import time
            from datetime import datetime, timedelta
            
            try:
                deals_log = []
                now_ts = int(time.time())
                all_deals = mt5.history_deals_get(now_ts - 86400 * 7, now_ts + 86400)
                
                if all_deals:
                    for d in all_deals:
                        deals_log.append({
                            "ticket": d.ticket,
                            "time": d.time,
                            "type": d.type,
                            "profit": d.profit,
                            "commission": d.commission,
                            "swap": d.swap
                        })
                
                acc = mt5.account_info()
                acc_data = {}
                if acc:
                    acc_data = {"balance": acc.balance, "equity": acc.equity, "profit": acc.profit}
                    
                with open("mt5_debug.json", "w") as f:
                    json.dump({"deals": deals_log, "account": acc_data}, f, indent=2)
                    
                # Standard calculation fallback without datetime conversions
                broker_now_ts = 0
                symbols = mt5.symbols_get()
                if symbols:
                    for s in symbols[:20]:
                        tick = mt5.symbol_info_tick(s.name)
                        if tick and tick.time > broker_now_ts:
                            broker_now_ts = tick.time
                            
                if broker_now_ts == 0:
                    broker_now_ts = now_ts
                    
                # Use absolute integer math for Broker Midnight
                broker_midnight = (broker_now_ts // 86400) * 86400
                deals_today = mt5.history_deals_get(int(broker_midnight), int(broker_now_ts + 86400))
                
                daily_realized = 0.0
                if deals_today:
                    for d in deals_today:
                        if d.type in [mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL]:
                            p = getattr(d, 'profit', 0.0) or 0.0
                            c = getattr(d, 'commission', 0.0) or 0.0
                            s = getattr(d, 'swap', 0.0) or 0.0
                            daily_realized += (p + c + s)
                
                return float(round(daily_realized, 2))
            except Exception as e:
                with open("mt5_debug_error.log", "w") as f:
                    f.write(str(e))
                return 0.0
    def get_available_symbols(self):
        with self._lock:
            if not self.connected:
                self.connect()
            symbols = mt5.symbols_get()
            if symbols is None:
                return []
            result = []
            for s in symbols:
                result.append({
                    "symbol": s.name,
                    "description": s.path,
                    "group": s.path.split('\\')[0] if '\\' in s.path else "General",
                    "digits": s.digits
                })
            return result
    def symbols_get(self, group=None, pattern=None):
        """Return the symbol catalogue as plain dicts, never raising.

        ``group`` is the MetaTrader5 glob filter (for example ``"*USD*"``) and is
        forwarded to the terminal. ``pattern`` is a plain case-insensitive
        substring filter applied to the symbol name or path; on its own it scans
        the whole catalogue instead of only the Market Watch list.
        """
        with self._lock:
            try:
                if not self.connected:
                    self.connect()
                if group:
                    symbols = mt5.symbols_get(group=group)
                elif pattern:
                    symbols = mt5.symbols_get(group="*")
                else:
                    symbols = mt5.symbols_get()
                if symbols is None:
                    return []
                needle = pattern.strip().lower() if pattern else None
                result = []
                for s in symbols:
                    name = getattr(s, "name", None)
                    if not name:
                        continue
                    path = getattr(s, "path", "") or ""
                    if needle and needle not in name.lower() and needle not in path.lower():
                        continue
                    result.append({
                        "name": name,
                        "description": getattr(s, "description", "") or "",
                        "path": path,
                        "visible": bool(getattr(s, "visible", False)),
                        "trade_mode": int(getattr(s, "trade_mode", 0) or 0),
                        "expiration_time": int(getattr(s, "expiration_time", 0) or 0),
                    })
                return result
            except Exception as e:
                logger.error(f"MT5 symbols_get error: {e}")
                return []
    def get_symbol_details(self, symbol):
        with self._lock:
            if not self.connected:
                self.connect()
            info = mt5.symbol_info(symbol)
            if info:
                EXCHANGE_EXEC = 3
                is_futures = getattr(info, 'trade_exemode', -1) == EXCHANGE_EXEC or "=" in symbol or symbol.endswith("F")
                broker_type = "futures" if is_futures else "cfd"
                return {
                    "point": info.point,
                    "digits": info.digits,
                    "tick_size": info.trade_tick_size if info.trade_tick_size > 0 else info.point,
                    "stops_level": info.trade_stops_level,
                    "broker_type": broker_type,
                    "trade_exemode": getattr(info, 'trade_exemode', -1),
                }
            return {"point": 0.0001, "digits": 5, "tick_size": 0.0001, "stops_level": 0, "broker_type": "cfd", "trade_exemode": -1}
_global_mt5_instance = None
def get_mt5_connector():
    global _global_mt5_instance
    if _global_mt5_instance is None:
        _global_mt5_instance = MT5Connector()
    return _global_mt5_instance