import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../../"))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if __name__ == "__main__":
    current_file = os.path.abspath(__file__) 
    src_live_dir = os.path.dirname(current_file) 
    src_dir = os.path.dirname(src_live_dir) 
    root_dir = os.path.dirname(src_dir) 
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
import time
import json
import torch
from src.utils.device_utils import get_best_device

import numpy as np
import traceback
import pandas as pd
from datetime import datetime
from rich.console import Console
from rich.live import Live
from rich.table import Table
from src.services.order_gateway.gateway import get_order_gateway
from src.services.order_gateway.models import OrderRequest, OrderSource, OrderSide, OrderType
try:
    from src.live.connector import get_mt5_connector
    from src.utils.config_manager import load_symbol_map
    from src.models.generator import Generator
    from src.data.loader import preprocess_data
    from src.analysis.market_filter import MarketFilter
    from src.algorithms import get_algorithm, ALGORITHMS
    from src.services.database import get_outputs_dir
except ImportError as e:
    print(f"CRITICAL IMPORT ERROR: {e}")
    print(f"Current File: {__file__}")
    print(f"Calculated Root: {project_root}")
    print(f"Sys Path: {sys.path}")
    raise e
import argparse
import joblib
console = Console()
def load_model_and_scaler(ticker, timeframe="1h"):
    safe_ticker = ticker.replace("=", "").replace("-", "")
    from src.services.database import get_outputs_dir
    outputs_dir = get_outputs_dir()
    models_dir = os.path.join(outputs_dir, "models")
    model_prefix = os.path.join(models_dir, f"{safe_ticker}_{timeframe}")
    model_path = f"{model_prefix}_generator.pth"
    scaler_path = f"{model_prefix}_scaler.pkl"
    config_path = f"{model_prefix}_config.json"
    if not os.path.exists(model_path):
        console.print(f"[yellow]Modelo específico no encontrado: {model_path}. Intentando fallback...[/yellow]")
        model_path = os.path.join(outputs_dir, "generator.pth")
        scaler_path = os.path.join(outputs_dir, "scaler.pkl")
        config_path = os.path.join(outputs_dir, "model_config.json")
    if not os.path.exists(model_path) or not os.path.exists(scaler_path):
        raise FileNotFoundError(f"No se encontraron los archivos del modelo para {ticker} ({timeframe}). Ejecute un entrenamiento primero.")
    scaler = joblib.load(scaler_path)
    hidden_dim = 128
    num_layers = 2
    trade_timeframe = "1m" 
    seq_length = 60
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                model_conf = json.load(f)
                hidden_dim = model_conf.get("hidden_dim", 128)
                num_layers = model_conf.get("num_layers", 2)
                if timeframe:
                    trade_timeframe = timeframe
                else:
                    trade_timeframe = model_conf.get("trade_timeframe", "1m")
                seq_length = model_conf.get("seq_length", 60)
        except Exception as e:
            console.print(f"[yellow]Advertencia: No se pudo cargar config ({e}). Usando valores por defecto.[/yellow]")
    device = get_best_device()
    INPUT_DIM = 8 
    model = Generator(INPUT_DIM, hidden_dim, num_layers, INPUT_DIM).to(device)
    model.load_state_dict(torch.load(model_path, map_location=device, weights_only=True))
    model.eval()
    return model, scaler, device, trade_timeframe, seq_length
def run_live_trading(sys_ticker, asset_type, platform="mt5", timeframe=None, algo_name="EvolutionaryGAN", algo_config=None, account_id=None):
    from src.utils.config_manager import load_symbol_map
    symbol_map = load_symbol_map(platform)  
    platform_symbol = None
    if asset_type in symbol_map and sys_ticker in symbol_map[asset_type]:
        platform_symbol = symbol_map[asset_type][sys_ticker]
    else:
        for cat in symbol_map:
            if sys_ticker in symbol_map[cat]:
                platform_symbol = symbol_map[cat][sys_ticker]
                asset_type = cat 
                break
    if not platform_symbol and sys_ticker == "ALL_ETF":
        platform_symbol = "ALL_ETF"
        asset_type = "ETF"
    if not platform_symbol:
        console.print(f"[red]No hay mapeo configurado para {sys_ticker} en {platform.upper()}. Vaya a Configuración.[/red]")
        return
    console.print(f"[green]Iniciando Trading en Vivo para {sys_ticker} ({platform.upper()}: {platform_symbol})[/green]")
    algo_instance = None
    model_info = {}
    if algo_name == 'FourierCycle':
        algo_instance = get_algorithm('FourierCycle', config=algo_config if algo_config else {})
        trade_timeframe = timeframe if timeframe else "1m"
        seq_length = algo_instance.fourier_period
        console.print(f"[green]Estrategia Fourier cargada. Timeframe: {trade_timeframe}[/green]")
    elif algo_name == 'EvolutionaryGAN':
        try:
            tf_to_load = timeframe if timeframe else "1h"
            model, scaler, device, trade_timeframe, seq_length = load_model_and_scaler(sys_ticker, timeframe=tf_to_load)
            model_info = {'model': model, 'scaler': scaler, 'device': device}
            console.print(f"[green]Modelo Evolutionary GAN cargado. Timeframe: {trade_timeframe}, SeqLength: {seq_length}[/green]")
        except Exception as e:
            console.print(f"[red]Error cargando modelo:[/red] {e}")
            return
    else:
        try:
            algo_instance = get_algorithm(algo_name, config=algo_config if algo_config else {})
            if algo_instance:
                trade_timeframe = timeframe if timeframe else "1h"
                seq_length = getattr(algo_instance, 'ventana_train', 60)
                console.print(f"[green]Algoritmo personalizado '{algo_name}' cargado.[/green] Timeframe: {trade_timeframe}")
            else:
                console.print(f"[red]No se pudo encontrar el algoritmo:[/red] {algo_name}")
                return
        except Exception as e:
            console.print(f"[red]Error cargando algoritmo personalizado:[/red] {e}")
            return
    if platform.lower() == "mt5":
        connector = get_mt5_connector()
    elif platform.lower() == "crypto":
        from src.live.crypto_connector import get_connector
        connector = get_connector(account_id)
    elif platform.lower() in ["tradovate", "nt8"]:
        from src.live.tradovate_connector import get_tradovate_connector
        connector = get_tradovate_connector(account_id)
    else:
        console.print(f"[red]Plataforma {platform} no tiene un conector configurado en live_trade.py[/red]")
        return
    if not connector or not connector.connect():
        console.print(f"[red]Fallo al conectar con {platform.upper()}[/red]")
        return
    market_filter = MarketFilter()
    last_trade_time = 0
    COOLDOWN_SECONDS = 300 
    console.print(f"[bold yellow]Esperando nueva vela ({trade_timeframe})... (Ctrl+C para detener)[/bold yellow]")
    current_date = datetime.now().date()
    daily_trades = 0
    current_date = datetime.now().date()
    daily_trades = 0
    initial_balance = connector.get_balance()
    last_raw_signal = "HOLD"
    consecutive_signals = 0
    gateway = get_order_gateway()
    gateway.switch_platform(platform)
    def safe_get(obj, key, default=None):
        return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

    try:
        while True:
            from src.utils.paths import get_data_path
            config_path = get_data_path("src", "config", "live_config.json")
            config = {
                "automation_enabled": False,
                "volume": 1.0,
                "max_daily_loss": 500.0,
                "daily_profit_target": 100.0,
                "max_trades_per_day": 5,
                "start_hour": "09:30",
                "end_hour": "16:00",
                "min_adx": 15, 
                "rsi_upper": 70,
                "rsi_lower": 30,
                "require_candle_confirmation": True,
                "consecutive_signals": 1,
                "use_ema_filter": False 
            }
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r') as f:
                        config.update(json.load(f)) 
                except:
                    pass
            
            if algo_config:
                config.update(algo_config)
                
            # Robust boolean parsing
            auto_str = str(config.get("automation_enabled", "False")).lower()
            config["automation_enabled"] = auto_str == "true" or auto_str == "1"
            
            acc_info = connector.get_account_info()
            if acc_info is None:
                console.print(f"[bold red][CONNECTOR] Error: No se pudo obtener la información de la cuenta de {platform.upper()}. Intentando reconectar...[/bold red]")
                try:
                    if connector.connect():
                        console.print(f"[green][CONNECTOR] Reconexión exitosa con {platform.upper()}[/green]")
                        acc_info = connector.get_account_info()
                except Exception as ex:
                    console.print(f"[red][CONNECTOR] Error durante el intento de reconexión: {ex}[/red]")
                
                if acc_info is None:
                    console.print("[yellow][CONNECTOR] Reintento de conexión fallido. Durmiendo 5 segundos...[/yellow]")
                    time.sleep(5)
                    continue

            current_balance = acc_info.get('balance', 0.0)
            current_equity = acc_info.get('equity', 0.0)
            realized_today = acc_info.get('daily_pnl', 0.0)
            
            now = datetime.now()
            if now.date() != current_date:
                current_date = now.date()
                daily_trades = 0
                initial_balance = current_balance
                
            floating = current_equity - current_balance
            daily_pnl = realized_today + floating
            time_str = now.strftime("%H:%M")
            is_time_valid = config.get("start_hour", "00:00") <= time_str <= config.get("end_hour", "23:59")
            is_loss_valid = daily_pnl > -float(config.get("max_daily_loss", 200.0))
            is_profit_target_reached = daily_pnl >= float(config.get("daily_profit_target", 200.0))
            is_trades_valid = daily_trades < int(config["max_trades_per_day"])
            on_cooldown = (time.time() - last_trade_time) < COOLDOWN_SECONDS
            can_trade = config["automation_enabled"] and is_time_valid and is_loss_valid and is_trades_valid and not is_profit_target_reached and not on_cooldown
            
            # Debug trade conditions periodically (every 60 iterations roughly)
            if int(time.time()) % 60 == 0:
                console.print(f"[dim]Auto:{config['automation_enabled']} Time:{is_time_valid} Loss:{is_loss_valid} Trades:{is_trades_valid} PT:{not is_profit_target_reached} CD:{not on_cooldown} -> CAN_TRADE: {can_trade}[/dim]")
            
            if platform_symbol == "ALL_ETF":
                df = pd.DataFrame([0]) 
            else:
                df = connector.get_latest_candles(platform_symbol, timeframe=trade_timeframe, n=seq_length + 100)
            if df is None or df.empty:
                console.print(f"[yellow]Advertencia: No se pudieron obtener velas para {platform_symbol}. Reintentando en 5 segundos...[/yellow]")
                time.sleep(5)
                continue
            
            if df is not None and not df.empty:
                df = market_filter.calculate_indicators(df)
                df = df.dropna()
                if len(df) >= seq_length + 1: 
                    df['Log_Ret_Close'] = np.log(df['Close'] / df['Close'].shift(1))
                    df['Log_Ret_High']  = np.log(df['High'] / df['High'].shift(1))
                    df['Log_Ret_Low']   = np.log(df['Low'] / df['Low'].shift(1))
                    df['Log_Vol']       = np.log1p(df['Volume'])
                    df['EMA']           = df['Close'].ewm(span=20, adjust=False).mean() 
                    if 'RSI' not in df.columns: df['RSI'] = 50.0
                    if 'ADX' not in df.columns: df['ADX'] = 20.0
                    if 'ATR' not in df.columns: df['ATR'] = 0.0
                    df_features = df.dropna()
                    if len(df_features) < seq_length:
                        console.print("[yellow]Not enough data after feature engineering[/yellow]")
                        time.sleep(5)
                        continue
                    current_price = df['Close'].iloc[-1] if 'Close' in df.columns else 0.0
                    prediction_real = current_price 
                    signal = "HOLD"
                    algo_metadata = {}
                    portfolio_signals = [] 
                    if algo_instance and algo_name != 'EvolutionaryGAN':
                        try:
                            if algo_name == 'StrategyETF_Portfolio':
                                if not getattr(algo_instance, '_data_loaded', False):
                                    dfs = {}
                                    for s in algo_instance.symbols:
                                        s_broker = s
                                        for cat in symbol_map:
                                            if s in symbol_map[cat]:
                                                s_broker = symbol_map[cat][s]
                                                break
                                        s_df = connector.get_latest_candles(s_broker, timeframe=trade_timeframe, n=500)
                                        if s_df is not None: dfs[s] = s_df
                                    algo_instance.cargar_datos_propios(dfs)
                                    algo_instance._data_loaded = True
                                for s in algo_instance.symbols:
                                    s_broker = s
                                    for cat in symbol_map:
                                        if s in symbol_map[cat]:
                                            s_broker = symbol_map[cat][s]
                                            break
                                    s_df = connector.get_latest_candles(s_broker, timeframe=trade_timeframe, n=seq_length + 100)
                                    if s_df is not None:
                                        algo_instance.update_vela(s, s_df) 
                                portfolio_signals = algo_instance.get_ordenes_activas()
                                signal = "HOLD" 
                                algo_metadata = {"portfolio": algo_instance.resumen_portafolio()}
                            else:
                                signal, algo_metadata = algo_instance.update(df)
                        except Exception as e:
                            console.print(f"[bold red]CRITICAL ALGO ERROR in {algo_name}:[/bold red] {e}")
                            import traceback
                            console.print(traceback.format_exc())
                            console.print("[yellow]Algo halted due to error. Check logs.[/yellow]")
                            time.sleep(10) # Give time to read the error
                            raise e
                        if algo_name == 'FourierCycle':
                            console.print(f"[cyan]Fourier Analysis: Proj {algo_metadata.get('projection', [{}])[0].get('value', 0):.2f} | Momentum {algo_metadata.get('momentum_score', 0):.2f} | Harmonics {len(algo_metadata.get('harmonics', []))}[/cyan]")
                            proj_list = algo_metadata.get('projection', [])
                            prediction_real = proj_list[0]['value'] if proj_list else current_price
                        else:
                            prediction_real = algo_metadata.get('precio_actual', current_price)
                        if signal == 'BUY': signal = 'BUY'
                        elif signal == 'SELL': signal = 'SELL'
                        else: signal = 'HOLD'
                    elif algo_name == 'EvolutionaryGAN':
                        last_sequence = df_features.tail(seq_length)[['Log_Ret_Close', 'Log_Ret_High', 'Log_Ret_Low', 'Log_Vol', 'RSI', 'ADX', 'ATR', 'EMA']].values
                        last_sequence_scaled = model_info['scaler'].transform(last_sequence)
                        input_tensor = torch.FloatTensor(last_sequence_scaled).unsqueeze(0).to(model_info['device'])
                        with torch.no_grad():
                            prediction_seq = model_info['model'](input_tensor)
                            prediction_scaled = prediction_seq[:, -1, :].cpu().numpy() 
                        dummy_pred = np.zeros((1, model_info['scaler'].n_features_in_))
                        dummy_pred[:, 0] = prediction_scaled[:, 0] 
                        prediction_real_features = model_info['scaler'].inverse_transform(dummy_pred)
                        predicted_log_return = prediction_real_features[0, 0]
                        prediction_real = current_price * np.exp(predicted_log_return)
                        threshold_return = 0.0001
                        if predicted_log_return > threshold_return:
                            signal = "BUY"
                        elif predicted_log_return < -threshold_return:
                            signal = "SELL"
                    required_consecutive = config.get("consecutive_signals", 1)
                    if required_consecutive > 1:
                        if signal == last_raw_signal and signal != "HOLD":
                            consecutive_signals += 1
                        else:
                            consecutive_signals = 1
                            last_raw_signal = signal
                        if consecutive_signals < required_consecutive:
                            signal = "HOLD"
                    else:
                        consecutive_signals = 1 
                    validation_msg = "OK"
                    volatility = df['ATR'].iloc[-1] if 'ATR' in df.columns else 0.0
                    if signal != "HOLD":
                        is_valid, validation_msg = market_filter.check_conditions(df, signal, config)
                        if not is_valid:
                            signal = "HOLD" 
                    positions = connector.get_positions(platform_symbol)
                    pending_orders = connector.get_pending_orders(platform_symbol)
                    console.print(f"[magenta]DEBUG: Pending Orders: {len(pending_orders)}[/magenta]")
                    has_position = len(positions) > 0
                    sl_price = 0.0
                    tp_price = 0.0
                    entry_price = 0.0
                    if has_position:
                        pos = positions[0] 
                        p_type = safe_get(pos, 'type', 0)
                        # Handle both MT5 (0=BUY, 1=SELL) and crypto (LONG/SHORT string)
                        if isinstance(p_type, str):
                            pos_type = "BUY" if p_type.upper() in ("LONG", "BUY") else "SELL"
                        else:
                            pos_type = "BUY" if p_type == 0 else "SELL"
                        entry_price = safe_get(pos, 'price_open', 0.0)
                        if config["automation_enabled"]:
                            if (pos_type == "BUY" and signal == "SELL") or (pos_type == "SELL" and signal == "BUY"):
                                console.print(f"[yellow]Señal opuesta detectada ({signal}). Cerrando posición {pos_type}...[/yellow]")
                                if connector.close_position(safe_get(pos, 'ticket'), symbol=platform_symbol):
                                    has_position = False 
                                    last_trade_time = time.time() 
                            else:
                                sl_price = safe_get(pos, 'sl', 0.0)
                                tp_price = safe_get(pos, 'tp', 0.0)
                        else:
                             sl_price = safe_get(pos, 'sl', 0.0)
                             tp_price = safe_get(pos, 'tp', 0.0)
                    if not has_position and signal != "HOLD":
                        if can_trade:
                            sl_points = df['ATR'].iloc[-1] * 2.0 if 'ATR' in df.columns else 20.0
                            tp_points = sl_points * 2.0
                            
                            volume = float(config.get("volume", 1.0))
                            
                            if "risk_percent" in config and float(config["risk_percent"]) > 0:
                                risk_pct = float(config["risk_percent"]) / 100.0
                                risk_amount = initial_balance * risk_pct
                                point_value = 1.0
                                if hasattr(connector, 'get_symbol_details'):
                                    det = connector.get_symbol_details(platform_symbol)
                                    if det and "point_value" in det:
                                        point_value = det["point_value"]
                                        
                                # Calcular SL y TP en base al volumen fijo y riesgo de la cuenta
                                if volume > 0 and point_value > 0:
                                    sl_points = risk_amount / (volume * point_value)
                                    tp_points = sl_points * 2.0 # Relación Riesgo:Recompensa 1:2
                                    console.print(f"[cyan]Riesgo ({config['risk_percent']}%): ${risk_amount:.2f} -> SL: {sl_points:.2f} pts, TP: {tp_points:.2f} pts[/cyan]")
                            elif "risk_pct" in config and float(config["risk_pct"]) > 0:
                                risk_pct = float(config["risk_pct"])
                                if risk_pct > 1: risk_pct = risk_pct / 100.0
                                risk_amount = initial_balance * risk_pct
                                point_value = 1.0
                                if hasattr(connector, 'get_symbol_details'):
                                    det = connector.get_symbol_details(platform_symbol)
                                    if det and "point_value" in det:
                                        point_value = det["point_value"]
                                if volume > 0 and point_value > 0:
                                    sl_points = risk_amount / (volume * point_value)
                                    tp_points = sl_points * 2.0
                                    console.print(f"[cyan]Riesgo ({risk_pct*100}%): ${risk_amount:.2f} -> SL: {sl_points:.2f} pts, TP: {tp_points:.2f} pts[/cyan]")

                            if signal == "BUY":
                                sl_price = current_price - sl_points
                                tp_price = current_price + tp_points
                            else:
                                sl_price = current_price + sl_points
                                tp_price = current_price - tp_points
                            console.print(f"[bold green]Ejecutando {signal} | Vol: {volume} | SL: {sl_price:.2f} | TP: {tp_price:.2f}[/bold green]")
                            
                            gateway = get_order_gateway()
                            req = OrderRequest(
                                platform=platform,
                                account_id=account_id,
                                symbol=platform_symbol,
                                side=OrderSide.BUY if signal == "BUY" else OrderSide.SELL,
                                quantity=volume,
                                sl=sl_price,
                                tp=tp_price,
                                source=OrderSource.ALGO,
                                order_type=OrderType.MARKET
                            )
                            res = gateway.submit_order(req)
                            if res.success:
                                daily_trades += 1
                                last_trade_time = time.time()
                                console.print(f"[bold green]Orden Exitosa! ID: {res.order_id}[/bold green]")
                            else:
                                err_msg = f"{res.rejection_reason} - {res.error_message}"
                                console.print(f"[bold red]Orden Fallida:[/bold red] {err_msg}")
                                # If rate limited, maybe increase sleep temporarily
                                if "rate" in err_msg.lower() or "limit" in err_msg.lower():
                                    time.sleep(5)
                        else:
                            reason = []
                            if not config['automation_enabled']: reason.append("Auto Off")
                            if not is_time_valid: reason.append("Time")
                            if not is_trades_valid: reason.append("Max Trades")
                            if on_cooldown: reason.append(f"Cooldown ({int(COOLDOWN_SECONDS - (time.time() - last_trade_time))}s)")
                            console.print(f"[dim]Señal {signal} ignorada ({', '.join(reason)})[/dim]")
                    
                    if portfolio_signals:
                        if not can_trade:
                             console.print(f"[dim]Señales de portfolio ignoradas, can_trade=False[/dim]")
                        else:
                            for item in portfolio_signals:
                                try:
                                    s = item['symbol']
                                    sig = item['signal']
                                    vol = item['asignacion'] 
                                    curr_p = item['precio']
                                    s_broker = s
                                    for cat in symbol_map:
                                        if s in symbol_map[cat]:
                                            s_broker = symbol_map[cat][s]
                                            break
                                    sl_p = curr_p * (1 - 0.02) if sig == "BUY" else curr_p * (1 + 0.02)
                                    tp_p = curr_p * (1 + 0.04) if sig == "BUY" else curr_p * (1 - 0.04)
                                    console.print(f"[bold blue]Portfolio Order: {s_broker} ({s}) {sig} | Vol: {vol:.2f}[/bold blue]")
                                    req = OrderRequest(
                                        platform=platform,
                                        account_id=account_id,
                                        symbol=s_broker,
                                        side=OrderSide.BUY if sig == "BUY" else OrderSide.SELL,
                                        quantity=float(config["volume"]) * vol * 5, 
                                        sl=sl_p,
                                        tp=tp_p,
                                        source=OrderSource.ALGO,
                                        order_type=OrderType.MARKET
                                    )
                                    res = gateway.submit_order(req)
                                    if res.success:
                                        daily_trades += 1
                                        last_trade_time = time.time()
                                    else:
                                        console.print(f"[bold red]Orden Portfolio Fallida ({s}):[/bold red] {res.rejection_reason} - {res.error_message}")
                                except Exception as ex:
                                    console.print(f"[red]Error procesando señal portfolio {s}: {ex}[/red]")
                        last_trade_time = time.time()
                    if hasattr(connector, 'get_account_info'):
                        acc_res = connector.get_account_info()
                        if acc_res:
                            current_balance = acc_res['balance']
                            current_equity = acc_res['equity']
                    sym_details = {}
                    if hasattr(connector, 'get_symbol_details'):
                        sym_details = connector.get_symbol_details(platform_symbol)
                    status = {
                        "type": "system_status", 
                        "data_type": "account_info",
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "ticker": sys_ticker,
                        "platform_symbol": platform_symbol,
                        "current_price": float(current_price),
                        "prediction": float(prediction_real),
                        "signal": signal,
                        "has_position": has_position,
                        "pending_orders": pending_orders,
                        "entry_price": float(entry_price),
                        "sl_price": round(float(sl_price), 2),
                        "tp_price": round(float(tp_price), 2),
                        "last_candles": df.tail(50).to_dict(orient='records'),
                        "account": {
                            "balance": float(current_balance),
                            "equity": float(current_equity),
                            "daily_pnl": float(daily_pnl),
                            "profit": float(floating), 
                            "realized_today": float(realized_today),
                            "daily_trades": daily_trades,
                            "positions": [
                                {
                                    "ticket": safe_get(p, 'ticket', 0),
                                    "symbol": safe_get(p, 'symbol', platform_symbol),
                                    "type": "BUY" if safe_get(p, 'type', 0) == 0 else "SELL",
                                    "volume": safe_get(p, 'volume', 0.0),
                                    "price_open": safe_get(p, 'price_open', 0.0),
                                    "sl": safe_get(p, 'sl', 0.0),
                                    "tp": safe_get(p, 'tp', 0.0),
                                    "profit": safe_get(p, 'profit', 0.0)
                                } for p in positions
                            ]
                        },
                        "strategy": {
                            "name": algo_name,
                            "timeframe": trade_timeframe,
                            "seq_length": seq_length,
                            "metadata": algo_metadata
                        },
                        "algorithm": algo_name,
                        "fourier_data": algo_metadata if algo_name == 'FourierCycle' else {},
                        "trading_mode": "ALGO",
                        "config": config,
                        "validation": validation_msg,
                        **sym_details 
                    }
                    outputs_dir = get_outputs_dir()
                    temp_file = os.path.join(outputs_dir, "live_status.tmp")
                    target_file = os.path.join(outputs_dir, "live_status.json")
                    success = False
                    for _ in range(3): 
                        try:
                            with open(temp_file, "w") as f:
                                json.dump(status, f, default=str)
                            if os.path.exists(target_file):
                                try:
                                    os.remove(target_file)
                                except: pass 
                            os.replace(temp_file, target_file)
                            success = True
                            break
                        except Exception as e:
                            time.sleep(0.1) 
                    if not success:
                        try:
                            with open(target_file, "w") as f:
                                json.dump(status, f, default=str)
                        except Exception as e:
                            console.print(f"[red]Error writing status: {e}[/red]")
                    console.print(f"P: {current_price:.2f} | S: {signal} | PnL: {daily_pnl:.2f} | Valid: {validation_msg}")
            time.sleep(1.0) 
    except KeyboardInterrupt:
        console.print("\n[yellow]Deteniendo Trading en Vivo...[/yellow]")
    finally:
        connector.shutdown()
if __name__ == "__main__":
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
    parser = argparse.ArgumentParser(description='QuantumGAN Live Trading')
    parser.add_argument('--ticker', type=str, default="MNQ=F", help='Ticker del sistema (ej: MNQ=F)')
    parser.add_argument('--asset_type', type=str, default="Futures", help='Tipo de activo (Futures, Forex, CFD, Crypto)')
    parser.add_argument('--platform', type=str, default="mt5", help='Plataforma de trading (mt5, crypto, tradovate, nt8)')
    parser.add_argument('--account_id', type=str, default=None, help='ID de cuenta para plataformas multi-cuenta')
    parser.add_argument('--algorithm', type=str, default="EvolutionaryGAN", help='Algoritmo a usar')
    parser.add_argument('--timeframe', type=str, default="1h", help='Timeframe a usar')
    parser.add_argument('--config', type=str, default="{}", help='Configuración del algoritmo en JSON')
    args = parser.parse_args()
    try:
        algo_config = json.loads(args.config)
    except:
        algo_config = {}
    try:
        run_live_trading(args.ticker, args.asset_type, args.platform, args.timeframe, args.algorithm, algo_config, args.account_id)
    except Exception as e:
        with open("live_crash.log", "w") as f:
            f.write(str(e))
            traceback.print_exc(file=f)
        raise e