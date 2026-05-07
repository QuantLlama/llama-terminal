import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple, List, Optional
from collections import deque
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.preprocessing import StandardScaler
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("⚠️  pip install scikit-learn")

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False
    print("⚠️  pip install yfinance  (necesario para modo multi-ETF)")


# =============================================================================
# SISTEMA CUANTITATIVO ETFs - v6.0 PRO - Quantum LLAMA IA
# Autor original (R): Pablo Ez. Moscardo (Punto&Coma Trading - NBM-Systemas)
# Conversión Python + Multi-ETF: 2026
#
# DOS MODOS DE USO:
#   1. CustomStrategy        → un solo símbolo (para tu plataforma, vela a vela)
#   2. QuantumLlamaPortfolio → los 10 ETFs simultáneos (análisis completo de cartera)
# =============================================================================


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO COMPARTIDO: features + modelo RF  (usado por ambas clases)
# ─────────────────────────────────────────────────────────────────────────────

ETF_DEFAULT = ["VTI", "VIG", "VNQ", "BND", "GLD", "SPY", "IEF", "VCIT", "XLK", "TLT"]

CFG_DEFAULT = dict(
    ventana_train        = 378,    # 252 * 1.5
    ventana_test         = 63,
    retrain_interval     = 63,
    min_obs_ml           = 120,
    n_arboles            = 100,
    min_node_size        = 10,
    pred_threshold       = 0.005,
    confidence_threshold = 0.60,
    umbral_volatilidad   = 0.30,
    stop_loss            = 2.0,
    take_profit          = 4.0,
    max_position_pct     = 0.25,
    max_dd_tolerance     = 0.20,
    capital_inicial      = 100_000,
    tasa_libre_riesgo    = 0.02,
)


def _rsi_series(price: pd.Series, n: int = 14) -> pd.Series:
    delta = price.diff()
    gain  = delta.where(delta > 0, 0.0).rolling(n).mean()
    loss  = (-delta.where(delta < 0, 0.0)).rolling(n).mean()
    return 100 - (100 / (1 + gain / (loss + 1e-10)))


def crear_features(log_returns: pd.Series) -> Optional[pd.DataFrame]:
    """Replica exacta de crear_features_single() del sistema R."""
    try:
        ret       = log_returns.copy()
        price_cum = (1 + ret).cumprod()
        df = pd.DataFrame(index=ret.index)
        df['ret']      = ret
        df['lag1']     = ret.shift(1)
        df['lag2']     = ret.shift(2)
        df['lag3']     = ret.shift(3)
        df['lag5']     = ret.shift(5)
        df['ma5_p']    = price_cum.rolling(5).mean()
        df['ma10_p']   = price_cum.rolling(10).mean()
        df['ma20_p']   = price_cum.rolling(20).mean()
        df['ma50_p']   = price_cum.rolling(50).mean()
        rsi            = _rsi_series(price_cum, 14)
        df['rsi']      = rsi
        df['rsi_ma']   = rsi.rolling(5).mean()
        df['vol10']    = ret.rolling(10).std()
        df['vol20']    = ret.rolling(20).std()
        df['vol_ratio']= df['vol10'] / (df['vol20'] + 1e-6)
        df['mom5']     = ret.rolling(5).sum()
        df['mom10']    = ret.rolling(10).sum()
        df['mom21']    = ret.rolling(21).sum()
        df['trend_5']  = (price_cum - price_cum.shift(5))  / (price_cum.shift(5)  + 1e-6)
        df['trend_20'] = (price_cum - price_cum.shift(20)) / (price_cum.shift(20) + 1e-6)
        df['target']   = ret.shift(-1)
        df.dropna(inplace=True)
        return df
    except Exception as e:
        print(f"⚠️ Error features: {e}")
        return None


class _RFEngine:
    """Motor de Random Forest reutilizable para un solo activo."""

    def __init__(self, cfg: dict):
        self.cfg           = cfg
        self.model         = None
        self.scaler        = None
        self.feature_cols  = None
        self.pred_history  = deque(maxlen=cfg['ventana_test'])
        self.n_retrains    = 0
        self._since_retrain= 0

    def maybe_retrain(self, log_returns: pd.Series) -> bool:
        self._since_retrain += 1
        if self.model is None or self._since_retrain >= self.cfg['retrain_interval']:
            ok = self._train(log_returns)
            self._since_retrain = 0
            return ok
        return self.model is not None

    def _train(self, log_returns: pd.Series) -> bool:
        if not ML_AVAILABLE:
            return False
        try:
            df = crear_features(log_returns)
            if df is None or len(df) < self.cfg['min_obs_ml']:
                return False
            train = df.iloc[-self.cfg['ventana_train']:].copy()
            train = train[train['target'].abs() < self.cfg['umbral_volatilidad']]
            if len(train) < self.cfg['min_obs_ml']:
                return False
            fcols = [c for c in train.columns if c not in ('target', 'ret')]
            fcols = [c for c in fcols
                     if train[c].notna().all()
                     and not np.isinf(train[c]).any()
                     and train[c].var() > 1e-10]
            if len(fcols) < 3:
                return False
            X = train[fcols].values
            y = train['target'].values
            if np.var(y) < 1e-10:
                return False
            self.scaler = StandardScaler()
            Xs = self.scaler.fit_transform(X)
            self.model = RandomForestRegressor(
                n_estimators    = self.cfg['n_arboles'],
                max_features    = max(1, int(np.sqrt(len(fcols)))),
                min_samples_leaf= self.cfg['min_node_size'],
                random_state    = 2025,
                n_jobs          = -1
            )
            self.model.fit(Xs, y)
            self.feature_cols = fcols
            self.n_retrains  += 1
            return True
        except Exception as e:
            print(f"⚠️ Train error: {e}")
            return False

    def predict(self, features_df: pd.DataFrame) -> Tuple[str, float, float]:
        """Retorna (señal, prediccion, confianza)."""
        if self.model is None or self.feature_cols is None:
            return 'HOLD', 0.0, 0.0
        try:
            cols = [c for c in self.feature_cols if c in features_df.columns]
            if len(cols) < 3:
                return 'HOLD', 0.0, 0.0
            X = features_df[cols].iloc[[-1]].values
            if np.any(np.isnan(X)) or np.any(np.isinf(X)):
                return 'HOLD', 0.0, 0.0
            pred = float(self.model.predict(self.scaler.transform(X))[0])
            self.pred_history.append(abs(pred))
            max_pred = max(self.pred_history) if self.pred_history else 1e-6
            conf = min(abs(pred) / (max_pred + 1e-6), 1.0)
            if conf >= self.cfg['confidence_threshold']:
                if pred > self.cfg['pred_threshold']:
                    return 'BUY', pred, conf
                elif pred < -self.cfg['pred_threshold']:
                    return 'SELL', pred, conf
            return 'HOLD', pred, conf
        except Exception as e:
            print(f"⚠️ Predict error: {e}")
            return 'HOLD', 0.0, 0.0


# ─────────────────────────────────────────────────────────────────────────────
# MODO 1: INDIVIDUAL  — un solo ETF, vela a vela para la plataforma
# ─────────────────────────────────────────────────────────────────────────────

class StrategyETF_Individual:
    """
    🦙 MODO INDIVIDUAL — un solo símbolo
    =====================================
    Uso desde plataforma:

        strategy = CustomStrategy(config={'stop_loss': 2.0, 'take_profit': 4.0})
        signal, meta = strategy.update(df)   # df con columna 'Close'
    """

    def __init__(self, config: Dict = None):
        self.config = {**CFG_DEFAULT, **(config or {})}
        self._engine       = _RFEngine(self.config)
        self._entry_price  = None
        self._position     = 'NONE'   # 'LONG' | 'SHORT' | 'NONE'

    # ── API principal ──────────────────────────────────────────────────
    def update(self, df: pd.DataFrame) -> Tuple[str, Dict]:
        min_bars = max(self.config['ventana_train'], 60)
        if len(df) < min_bars:
            return 'HOLD', {
                'status': 'waiting_data',
                'bars_needed': min_bars,
                'bars_available': len(df),
                'risk_info': f"SL:{self.config['stop_loss']}% TP:{self.config['take_profit']}%"
            }

        close       = df['Close'].astype(float)
        log_ret     = np.log(close / close.shift(1)).dropna()
        vol_anual   = float(log_ret.rolling(20).std().iloc[-1] * np.sqrt(252))

        self._engine.maybe_retrain(log_ret)
        feat_df = crear_features(log_ret)

        if feat_df is None or len(feat_df) == 0:
            return 'HOLD', {'status': 'feature_error'}

        signal, pred, conf = self._engine.predict(feat_df)

        # Filtro de volatilidad extrema
        if vol_anual > self.config['umbral_volatilidad']:
            signal, pred = 'HOLD', 0.0

        # Stops
        current_price = float(close.iloc[-1])
        signal = self._check_stops(signal, current_price)
        self._update_position(signal, current_price)

        return signal, {
            'status':          'active',
            'modo':            'INDIVIDUAL',
            'prediccion_ret':  round(pred, 6),
            'confianza':       round(conf, 4),
            'confianza_pct':   f"{conf*100:.1f}%",
            'volatilidad':     f"{vol_anual*100:.1f}%",
            'rsi_14':          round(float(_rsi_series(close, 14).iloc[-1]), 2),
            'ma_20':           round(float(close.rolling(20).mean().iloc[-1]), 4),
            'momentum_5d':     round(float(log_ret.rolling(5).sum().iloc[-1]), 6),
            'precio_actual':   round(current_price, 4),
            'posicion':        self._position,
            'reentrenamientos':self._engine.n_retrains,
            'modelo_activo':   self._engine.model is not None,
            'risk_info':       f"SL:{self.config['stop_loss']}% | TP:{self.config['take_profit']}% | MaxPos:{self.config['max_position_pct']*100:.0f}%",
        }

    def _check_stops(self, signal: str, price: float) -> str:
        if self._entry_price is None or self._position == 'NONE':
            return signal
        chg = (price - self._entry_price) / self._entry_price * 100
        if self._position == 'LONG':
            if chg <= -self.config['stop_loss']:   return 'SELL'
            if chg >=  self.config['take_profit']:  return 'SELL'
        elif self._position == 'SHORT':
            if chg >=  self.config['stop_loss']:    return 'BUY'
            if chg <= -self.config['take_profit']:  return 'BUY'
        return signal

    def _update_position(self, signal: str, price: float):
        if signal == 'BUY'  and self._position != 'LONG':
            self._position = 'LONG';  self._entry_price = price
        elif signal == 'SELL' and self._position != 'SHORT':
            self._position = 'SHORT'; self._entry_price = price


# ─────────────────────────────────────────────────────────────────────────────
# MODO 2: PORTAFOLIO COMPLETO — los 10 ETFs simultáneos
# ─────────────────────────────────────────────────────────────────────────────

class StrategyETF_Portfolio:
    """
    🦙 MODO PORTAFOLIO — réplica con los 10 ETFs
    ===========================================================
    Analiza todos los ETFs simultáneamente, muestra señales consolidadas
    y calcula la asignación de capital óptima por activo.

    USO BÁSICO:
    -----------
        portfolio = QuantumLlamaPortfolio()
        portfolio.cargar_datos()              # descarga Yahoo Finance
        resultado = portfolio.ejecutar()      # análisis completo
        portfolio.mostrar_dashboard()         # tabla de señales estilo R

    USO CON DATOS PROPIOS:
    ----------------------
        dfs = {'SPY': df_spy, 'GLD': df_gld, ...}   # cada df con col 'Close'
        portfolio = QuantumLlamaPortfolio()
        portfolio.cargar_datos_propios(dfs)
        resultado = portfolio.ejecutar()
    """

    def __init__(self, symbols: List[str] = None, config: Dict = None):
        self.symbols  = symbols or ETF_DEFAULT
        self.config   = {**CFG_DEFAULT, **(config or {})}
        
        # Para cumplir con el motor de live_trade
        self.name     = "StrategyETF_Portfolio"
        self.ticker   = "ALL_ETF" 

        # Un motor RF por activo
        self._engines : Dict[str, _RFEngine]   = {s: _RFEngine(self.config) for s in self.symbols}
        self._data    : Dict[str, pd.DataFrame] = {}   # Close prices
        self._log_ret : Dict[str, pd.Series]    = {}

        # Estado de posiciones y NAV
        self._positions    : Dict[str, str]   = {s: 'NONE' for s in self.symbols}
        self._entry_prices : Dict[str, float] = {s: 0.0    for s in self.symbols}
        self._capital      = float(self.config['capital_inicial'])
        self._nav_history  : List[float]      = [self._capital]
        self._max_nav      = self._capital
        self._trade_log    : List[Dict]        = []

        # Resultados del último análisis
        self.last_signals  : Dict[str, str]   = {}
        self.last_conf     : Dict[str, float] = {}
        self.last_pred     : Dict[str, float] = {}
        self.last_alloc    : Dict[str, float] = {}

    # ──────────────────────────────────────────────────────────────────
    # CARGA DE DATOS
    # ──────────────────────────────────────────────────────────────────

    def cargar_datos(self, desde: str = '2019-01-01') -> bool:
        """
        Descarga precios históricos de Yahoo Finance para todos los ETFs.
        Equivalente a descargar_retornos() del sistema R.
        """
        if not YF_AVAILABLE:
            print("❌ yfinance no instalado. Usar cargar_datos_propios(dfs).")
            return False

        print(f"\n📥 Descargando {len(self.symbols)} ETFs desde Yahoo Finance ({desde} → hoy)...")
        ok_count = 0

        for sym in self.symbols:
            for intento in range(3):
                try:
                    raw = yf.download(sym, start=desde, progress=False, auto_adjust=True)
                    if raw is None or len(raw) < 60:
                        raise ValueError("Datos insuficientes")
                    close = raw['Close'].squeeze().dropna()
                    self._data[sym]    = close
                    self._log_ret[sym] = np.log(close / close.shift(1)).dropna()
                    print(f"   ✓ {sym:<6} {len(close)} barras")
                    ok_count += 1
                    break
                except Exception as e:
                    if intento == 2:
                        print(f"   ✗ {sym}: {e}")

        print(f"\n   → {ok_count}/{len(self.symbols)} activos cargados")
        return ok_count > 0

    def cargar_datos_propios(self, dfs: Dict[str, pd.DataFrame]) -> None:
        """
        Carga datos propios. Cada valor del dict debe ser un DataFrame
        con columna 'Close' (o una pd.Series directamente).
        """
        for sym, data in dfs.items():
            if isinstance(data, pd.Series):
                close = data.astype(float).dropna()
            else:
                close = data['Close'].astype(float).dropna()
            self._data[sym]    = close
            self._log_ret[sym] = np.log(close / close.shift(1)).dropna()
            print(f"   ✓ {sym:<6} {len(close)} barras (datos propios)")

    # ──────────────────────────────────────────────────────────────────
    # ANÁLISIS PRINCIPAL
    # ──────────────────────────────────────────────────────────────────

    def ejecutar(self) -> Dict:
        """
        Corre el análisis completo sobre todos los ETFs.
        Replica entrenar_walkforward() + simulate_portfolio() del R.
        Retorna dict con señales, confianzas y asignación de capital.
        """
        if not self._data:
            print("❌ Sin datos. Llamar a cargar_datos() primero.")
            return {}

        print(f"\n🤖 Entrenando modelos walk-forward para {len(self._data)} ETFs...")
        signals, confs, preds = {}, {}, {}

        for sym, log_ret in self._log_ret.items():
            if len(log_ret) < self.config['min_obs_ml']:
                signals[sym] = 'HOLD'; confs[sym] = 0.0; preds[sym] = 0.0
                continue

            engine = self._engines[sym]
            engine.maybe_retrain(log_ret)
            feat_df = crear_features(log_ret)

            if feat_df is None or len(feat_df) == 0:
                signals[sym] = 'HOLD'; confs[sym] = 0.0; preds[sym] = 0.0
                continue

            sig, pred, conf = engine.predict(feat_df)

            # Filtro de volatilidad
            vol = float(log_ret.rolling(20).std().iloc[-1] * np.sqrt(252))
            if vol > self.config['umbral_volatilidad']:
                sig, pred = 'HOLD', 0.0

            # Stops
            current_price = float(self._data[sym].iloc[-1])
            sig = self._check_stops_sym(sym, sig, current_price)
            self._update_pos_sym(sym, sig, current_price)

            signals[sym] = sig
            confs[sym]   = conf
            preds[sym]   = pred
            print(f"   {'✓' if sig != 'HOLD' else '·'} {sym:<6}  {sig:<4}  conf:{conf*100:.1f}%  pred:{pred:+.5f}  vol:{vol*100:.1f}%")

        # Calcular asignación de capital
        allocation = self._calcular_asignacion(signals, confs)

        self.last_signals = signals
        self.last_conf    = confs
        self.last_pred    = preds
        self.last_alloc   = allocation

        return {
            'signals':    signals,
            'confidence': confs,
            'prediction': preds,
            'allocation': allocation,
            'timestamp':  datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

    def update_vela(self, sym: str, df: pd.DataFrame) -> Tuple[str, Dict]:
        """
        Punto de entrada vela-a-vela para un ETF específico del portafolio.
        Permite que la plataforma llame al portafolio para un solo símbolo
        y luego llamar a resumen_portafolio() para ver el cuadro completo.
        """
        if sym not in self._engines:
            return 'HOLD', {'error': f'{sym} no está en el portafolio'}

        close   = df['Close'].astype(float)
        log_ret = np.log(close / close.shift(1)).dropna()

        if len(log_ret) < self.config['min_obs_ml']:
            return 'HOLD', {'status': 'waiting_data', 'symbol': sym}

        engine = self._engines[sym]
        engine.maybe_retrain(log_ret)
        feat_df = crear_features(log_ret)
        sig, pred, conf = engine.predict(feat_df) if feat_df is not None else ('HOLD', 0.0, 0.0)

        vol = float(log_ret.rolling(20).std().iloc[-1] * np.sqrt(252))
        if vol > self.config['umbral_volatilidad']:
            sig, pred = 'HOLD', 0.0

        current_price = float(close.iloc[-1])
        sig = self._check_stops_sym(sym, sig, current_price)
        self._update_pos_sym(sym, sig, current_price)

        self._data[sym]      = close
        self._log_ret[sym]   = log_ret
        self.last_signals[sym] = sig
        self.last_conf[sym]    = conf
        self.last_pred[sym]    = pred

        return sig, {
            'symbol':      sym,
            'signal':      sig,
            'confianza':   f"{conf*100:.1f}%",
            'prediccion':  round(pred, 6),
            'volatilidad': f"{vol*100:.1f}%",
            'posicion':    self._positions[sym],
            'precio':      round(current_price, 4),
        }

    # ──────────────────────────────────────────────────────────────────
    # ASIGNACIÓN DE CAPITAL
    # ──────────────────────────────────────────────────────────────────

    def _calcular_asignacion(self, signals: Dict, confs: Dict) -> Dict[str, float]:
        """
        Asignación de capital proporcional a la confianza,
        respetando el límite max_position_pct.
        Replica la lógica de alloc_mean_variance() del sistema R.
        """
        activos_activos = {s: c for s, c in confs.items()
                           if signals.get(s) in ('BUY', 'SELL') and c > 0}

        if not activos_activos:
            return {s: 0.0 for s in signals}

        total_conf = sum(activos_activos.values())
        max_pct    = self.config['max_position_pct']
        alloc      = {}

        for sym in signals:
            if sym in activos_activos:
                peso = (activos_activos[sym] / total_conf)
                peso = min(peso, max_pct)  # Cap individual
                alloc[sym] = round(peso, 4)
            else:
                alloc[sym] = 0.0

        # Re-normalizar si la suma supera 1
        total = sum(alloc.values())
        if total > 1.0:
            alloc = {s: round(v / total, 4) for s, v in alloc.items()}

        return alloc

    # ──────────────────────────────────────────────────────────────────
    # STOPS POR SÍMBOLO
    # ──────────────────────────────────────────────────────────────────

    def _check_stops_sym(self, sym: str, signal: str, price: float) -> str:
        ep  = self._entry_prices.get(sym, 0.0)
        pos = self._positions.get(sym, 'NONE')
        if ep == 0.0 or pos == 'NONE':
            return signal
        chg = (price - ep) / ep * 100
        if pos == 'LONG':
            if chg <= -self.config['stop_loss']:  return 'SELL'
            if chg >=  self.config['take_profit']: return 'SELL'
        elif pos == 'SHORT':
            if chg >=  self.config['stop_loss']:  return 'BUY'
            if chg <= -self.config['take_profit']: return 'BUY'
        return signal

    def _update_pos_sym(self, sym: str, signal: str, price: float):
        if signal == 'BUY'  and self._positions[sym] != 'LONG':
            self._positions[sym] = 'LONG';  self._entry_prices[sym] = price
        elif signal == 'SELL' and self._positions[sym] != 'SHORT':
            self._positions[sym] = 'SHORT'; self._entry_prices[sym] = price

    # ──────────────────────────────────────────────────────────────────
    # DASHBOARD / REPORTES  (estilo Shiny del sistema)
    # ──────────────────────────────────────────────────────────────────

    def mostrar_dashboard(self) -> pd.DataFrame:
        """
        Muestra la tabla completa de señales estilo dashboard del sistema R.
        Retorna también el DataFrame para uso programático.
        """
        if not self.last_signals:
            print("❌ Sin señales. Ejecutar ejecutar() primero.")
            return pd.DataFrame()

        filas = []
        for sym in self.symbols:
            if sym not in self.last_signals:
                continue
            sig   = self.last_signals[sym]
            conf  = self.last_conf.get(sym, 0.0)
            pred  = self.last_pred.get(sym, 0.0)
            alloc = self.last_alloc.get(sym, 0.0)
            pos   = self._positions.get(sym, 'NONE')
            price = float(self._data[sym].iloc[-1]) if sym in self._data else 0.0
            vol   = float(self._log_ret[sym].rolling(20).std().iloc[-1] * np.sqrt(252)) \
                    if sym in self._log_ret else 0.0

            # Colores de texto en terminal
            sig_color = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '⚪'}.get(sig, '⚪')
            pos_icon  = {'LONG': '📈', 'SHORT': '📉', 'NONE': '➖'}.get(pos, '➖')

            filas.append({
                'ETF':          sym,
                'Señal':        f"{sig_color} {sig}",
                'Confianza':    f"{conf*100:.1f}%",
                'Predicción':   f"{pred:+.5f}",
                'Volatilidad':  f"{vol*100:.1f}%",
                'Posición':     f"{pos_icon} {pos}",
                'Asignación':   f"{alloc*100:.1f}%",
                'Capital $':    f"${alloc * self._capital:,.0f}",
                'Precio':       f"{price:.2f}",
                'Retrains':     self._engines[sym].n_retrains,
            })

        df = pd.DataFrame(filas)

        # Resumen de señales
        n_buy  = sum(1 for s in self.last_signals.values() if s == 'BUY')
        n_sell = sum(1 for s in self.last_signals.values() if s == 'SELL')
        n_hold = sum(1 for s in self.last_signals.values() if s == 'HOLD')
        total_allocated = sum(self.last_alloc.values()) * 100

        sep = "═" * 85
        print(f"\n{sep}")
        print(f"  🦙 QUANTUM LLAMA IA — DASHBOARD ETF PRO v6.0")
        print(f"  📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}   💰 Capital: ${self._capital:,.0f}")
        print(sep)
        print(df.to_string(index=False))
        print(sep)
        print(f"  🟢 BUY: {n_buy}  |  🔴 SELL: {n_sell}  |  ⚪ HOLD: {n_hold}  |  Capital asignado: {total_allocated:.1f}%")
        print(sep)

        return df

    def resumen_portafolio(self) -> pd.DataFrame:
        """Alias de mostrar_dashboard(). Para llamar desde la plataforma."""
        return self.mostrar_dashboard()

    def get_ordenes_activas(self) -> List[Dict]:
        """
        Retorna solo las señales accionables (BUY/SELL) con su asignación.
        Ideal para ejecutar órdenes desde la plataforma.
        """
        ordenes = []
        for sym, sig in self.last_signals.items():
            if sig in ('BUY', 'SELL'):
                ordenes.append({
                    'symbol':      sym,
                    'signal':      sig,
                    'confianza':   self.last_conf.get(sym, 0.0),
                    'asignacion':  self.last_alloc.get(sym, 0.0),
                    'capital_usd': self.last_alloc.get(sym, 0.0) * self._capital,
                    'precio':      float(self._data[sym].iloc[-1]) if sym in self._data else 0.0,
                })
        return ordenes


    def update(self, df: pd.DataFrame) -> Tuple[str, Dict]:
        """
        Método de compatibilidad con live_trade.py. 
        En modo Portfolio, el ticker debería ser 'ALL_ETF' o similar.
        """
        # Si recibimos un DF, asumimos que es del ticker principal (ej. SPY)
        # pero el portfolio internamente gestiona sus propios datos si se desea.
        # Para esta integración, delegamos a ejecutar() si es el ticker 'ALL_ETF'.
        return "HOLD", {"status": "portfolio_mode_active", "info": "Use ejecutar() o update_vela()"}

if __name__ == '__main__':
    pass  # Importar y usar directamente: ver referencia de uso en los comentarios de arriba