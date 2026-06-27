import re

with open("src/live/crypto_connector.py", "r") as f:
    content = f.read()

# Replace get_pending_orders block
old_get_orders = """                    result = []
                    for o in orders:
                        result.append({
                            "ticket": o.get('id', ''),
                            "symbol": o.get('symbol', ''),
                            "type": o.get('side', '').upper(), 
                            "volume": float(o.get('amount') or 0) - float(o.get('filled') or 0),
                            "price_open": float(o.get('price') or 0),
                            "sl": 0.0,
                            "tp": 0.0,
                            "time_setup": o.get('timestamp', 0) // 1000 if o.get('timestamp') else 0
                        })"""

new_get_orders = """                    result = []
                    # Check for orphan orders if position is already closed
                    pos_symbols = {p['symbol'] for p in self.get_positions()}
                    for o in orders:
                        o_sym = o.get('symbol', '')
                        o_type = o.get('type', '').upper()
                        info = o.get('info', {})
                        is_reduce_only = o.get('reduceOnly') is True or str(info.get('reduceOnly', '')).lower() == 'true' or str(info.get('closePosition', '')).lower() == 'true'
                        
                        if (is_reduce_only or o_type in ['STOP_MARKET', 'TAKE_PROFIT_MARKET', 'STOP', 'TAKE_PROFIT']) and o_sym and o_sym not in pos_symbols:
                            try:
                                logger.info(f"[{self.exchange_id}] Cancelling orphan order {o.get('id')} for {o_sym}")
                                self.exchange.cancel_order(o.get('id'), o_sym)
                                continue
                            except Exception as oe:
                                logger.error(f"[{self.exchange_id}] Failed to cancel orphan order {o.get('id')}: {oe}")

                        result.append({
                            "ticket": o.get('id', ''),
                            "symbol": o.get('symbol', ''),
                            "type": o.get('side', '').upper(), 
                            "volume": float(o.get('amount') or 0) - float(o.get('filled') or 0),
                            "price_open": float(o.get('price') or 0),
                            "sl": 0.0,
                            "tp": 0.0,
                            "time_setup": o.get('timestamp', 0) // 1000 if o.get('timestamp') else 0
                        })"""

content = content.replace(old_get_orders, new_get_orders)

old_close = """            # CRITICAL: reduceOnly=True tells Binance this is closing, not opening a new position
            params = {'reduceOnly': True}
            logger.info(f"[{self.exchange_id}] Closing position: {target_pos['symbol']} side={side} amount={amount}")
            self.exchange.create_order(target_pos['symbol'], 'market', side, amount, params=params)
            return True"""

new_close = """            # CRITICAL: reduceOnly=True tells Binance this is closing, not opening a new position
            params = {'reduceOnly': True}
            logger.info(f"[{self.exchange_id}] Closing position: {target_pos['symbol']} side={side} amount={amount}")
            self.exchange.create_order(target_pos['symbol'], 'market', side, amount, params=params)
            
            # --- Cleanup conditional orders ---
            try:
                open_orders = self.exchange.fetch_open_orders(target_pos['symbol'])
                for o in open_orders:
                    o_type = o.get('type', '').upper()
                    info = o.get('info', {})
                    is_reduce_only = o.get('reduceOnly') is True or str(info.get('reduceOnly', '')).lower() == 'true' or str(info.get('closePosition', '')).lower() == 'true'
                    if is_reduce_only or o_type in ['STOP_MARKET', 'TAKE_PROFIT_MARKET', 'STOP', 'TAKE_PROFIT']:
                        self.exchange.cancel_order(o.get('id'), target_pos['symbol'])
                        logger.info(f"[{self.exchange_id}] Cancelled conditional order {o.get('id')} for {target_pos['symbol']} after closing position")
            except Exception as oe:
                logger.error(f"[{self.exchange_id}] Failed to cleanup conditional orders for {target_pos['symbol']}: {oe}")
                
            self._clear_acc_cache()
            return True"""

content = content.replace(old_close, new_close)

with open("src/live/crypto_connector.py", "w") as f:
    f.write(content)

print("Patched!")
