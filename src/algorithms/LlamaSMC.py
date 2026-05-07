import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple, List, Optional


class LlamaSMC:
    """
    🦙 LLAMA SMC — Smart Money Concepts Strategy
    ================================================
    Estrategia institucional basada en estructura de mercado,
    zonas de oferta/demanda (SnD), retrocesos Fibonacci,
    Fair Value Gaps (FVGs) y trailing EMA21.

    Diseñada para operar futuros micro MNQ/NQ con capital
    de $1,000–$2,000 USD y 1 micro contrato.

    LÓGICA:
    ───────────────────────────────────────────────────
    1. Detecta Swing Highs/Lows relevantes.
    2. Identifica BOS (Break of Structure) y CHoCH (Change of Character).
    3. Marca zonas SnD responsables de rupturas estructurales.
    4. Traza Fibonacci (70%, 50%, 30%) desde liquidez al origen.
    5. Detecta FVGs (Fair Value Gaps) como zonas de ineficiencia.
    6. Sincroniza entradas con velas de 15 minutos.
    7. Confirma entrada: precio toca 50% Fib + cierre con cuerpo > 60%.
    8. SL en extremo de zona SnD, TP en extensión Fibonacci.
    9. Trailing stop dinámico con EMA21.
    10. Cambio de dirección automático en zona SnD contraria.
    """

    # ──────────────────────────────────────────────────
    # CONFIGURACIÓN
    # ──────────────────────────────────────────────────
    def __init__(self, config: Dict = None):
        self.config = config or {}

        # --- ESTRUCTURA DE MERCADO ---
        self.swing_lookback     = int(self.config.get('swing_lookback', 5))
        self.min_swing_size     = float(self.config.get('min_swing_size', 2.0))  # puntos mínimos

        # --- FIBONACCI ---
        self.fib_entry_level    = float(self.config.get('fib_entry_level', 0.5))
        self.fib_tp_extension   = float(self.config.get('fib_tp_extension', 1.618))

        # --- CONFIRMACIÓN DE ENTRADA ---
        self.body_ratio_min     = float(self.config.get('body_ratio_min', 0.55))

        # --- EMA TRAILING ---
        self.ema_trail_period   = int(self.config.get('ema_trail_period', 21))

        # --- ATR / RIESGO ---
        self.atr_period         = int(self.config.get('atr_period', 14))
        self.atr_sl_mult        = float(self.config.get('atr_sl_multiplier', 1.5))

        # --- PROTECCIÓN ---
        self.max_consec_losses  = int(self.config.get('max_consecutive_losses', 3))
        self.use_dd_protection  = bool(self.config.get('use_drawdown_protection', True))
        self.max_daily_loss_pct = float(self.config.get('max_daily_loss_pct', 3.0))

        # --- VOLUMEN ---
        self.vol_confirm        = bool(self.config.get('volume_confirmation', True))
        self.vol_mult           = float(self.config.get('volume_multiplier', 1.1))
        self.vol_period         = int(self.config.get('volume_period', 20))

        # --- ESTADO INTERNO ---
        self._swings: List[Dict] = []
        self._snd_zones: List[Dict] = []
        self._fvg_zones: List[Dict] = []
        self._trend = 0           # 1 = alcista, -1 = bajista
        self._last_bos = None
        self._last_choch = None
        self._active_zone = None  # Zona SnD activa donde esperamos retroceso

        self._entry_price = None
        self._active_sl = None
        self._active_tp = None
        self._active_dir = None   # 'BUY' | 'SELL'
        self._ema21_breaks = 0    # Contador de quiebres bajo EMA21

        self._consec_losses = 0
        self._trading_enabled = True
        self._current_day = None
        self._last_signal = 'HOLD'

    # ──────────────────────────────────────────────────
    # MÉTODO PRINCIPAL: update()
    # ──────────────────────────────────────────────────
    def update(self, df: pd.DataFrame) -> Tuple[str, Dict]:
        """
        Recibe DataFrame OHLCV con indicadores pre-calculados.
        Retorna (signal, metadata).
        """
        min_bars = max(self.swing_lookback * 3, self.atr_period, self.ema_trail_period,
                       self.vol_period) + 10
        if len(df) < min_bars:
            return 'HOLD', {'status': 'waiting_data', 'bars_needed': min_bars}

        # ── Reset diario ───────────────────────
        self._check_daily_reset(df)

        if self.use_dd_protection and not self._trading_enabled:
            return 'HOLD', {'status': 'trading_disabled', 'reason': 'drawdown_protection'}

        # ── Calcular indicadores clave ─────────
        ema21 = self._calc_ema(df['Close'], self.ema_trail_period)
        atr = self._calc_atr(df)

        # ── Detectar estructura de mercado ─────
        swings = self._detect_swings(df)
        structure = self._analyze_structure(swings, df)
        snd_zones = self._identify_snd_zones(swings, structure, df)
        fvg_zones = self._detect_fvg(df)

        # ── Precios actuales ───────────────────
        price = float(df['Close'].iloc[-1])
        high = float(df['High'].iloc[-1])
        low = float(df['Low'].iloc[-1])
        open_price = float(df['Open'].iloc[-1])
        bar_range = high - low
        body = abs(price - open_price)
        body_ratio = body / bar_range if bar_range > 0.01 else 0

        is_bullish = price > open_price
        is_bearish = price < open_price

        vol_ok = self._check_volume(df) if self.vol_confirm else True

        # ── LÓGICA DE SEÑALES ──────────────────
        signal = 'HOLD'
        sl_price = None
        tp_price = None
        entry_reason = ''

        # 1. Buscar entrada en zonas SnD con confirmación
        if self._entry_price is None:
            best_zone = self._find_active_zone(price, snd_zones, structure)

            if best_zone is not None:
                zone_type = best_zone['type']  # 'demand' or 'supply'
                fib_levels = best_zone.get('fib_levels', {})
                fib_50 = fib_levels.get('50', None)

                # ¿Precio toca el 50% del Fibonacci?
                in_fib_zone = False
                if fib_50 is not None:
                    fib_30 = fib_levels.get('30', fib_50 - 1)
                    fib_70 = fib_levels.get('70', fib_50 + 1)

                    if zone_type == 'demand':
                        in_fib_zone = low <= fib_50 <= high or (fib_30 <= price <= fib_70)
                    elif zone_type == 'supply':
                        in_fib_zone = low <= fib_50 <= high or (fib_30 <= price <= fib_70)

                if in_fib_zone and body_ratio >= self.body_ratio_min and vol_ok:
                    if zone_type == 'demand' and is_bullish and self._trend >= 0:
                        # ── SEÑAL BUY ──
                        sl_price = best_zone['low'] - (atr * 0.3 if atr else 0.5)
                        tp_dist = abs(price - sl_price) * self.fib_tp_extension
                        tp_price = price + tp_dist

                        signal = 'BUY'
                        self._entry_price = price
                        self._active_sl = sl_price
                        self._active_tp = tp_price
                        self._active_dir = 'BUY'
                        self._active_zone = best_zone
                        self._ema21_breaks = 0
                        entry_reason = f"Demand zone + Fib50 retest + Bullish body {body_ratio:.0%}"

                    elif zone_type == 'supply' and is_bearish and self._trend <= 0:
                        # ── SEÑAL SELL ──
                        sl_price = best_zone['high'] + (atr * 0.3 if atr else 0.5)
                        tp_dist = abs(sl_price - price) * self.fib_tp_extension
                        tp_price = price - tp_dist

                        signal = 'SELL'
                        self._entry_price = price
                        self._active_sl = sl_price
                        self._active_tp = tp_price
                        self._active_dir = 'SELL'
                        self._active_zone = best_zone
                        self._ema21_breaks = 0
                        entry_reason = f"Supply zone + Fib50 retest + Bearish body {body_ratio:.0%}"

                # FVG confluencia como señal alternativa
                elif self._check_fvg_entry(price, fvg_zones, structure, body_ratio,
                                           is_bullish, is_bearish, vol_ok, atr, df):
                    fvg_result = self._get_fvg_entry(price, fvg_zones, structure, body_ratio,
                                                     is_bullish, is_bearish, atr, df)
                    if fvg_result:
                        signal, sl_price, tp_price, entry_reason = fvg_result

        else:
            # ── TRAILING STOP con EMA21 ────────
            current_ema = ema21[-1] if len(ema21) > 0 and not np.isnan(ema21[-1]) else None

            if current_ema is not None:
                self._update_ema_trailing(price, low, high, current_ema)

            # ── Cambio de dirección en zona SnD contraria ──
            flip = self._check_direction_flip(price, snd_zones)
            if flip:
                signal = flip['signal']
                sl_price = flip['sl']
                tp_price = flip['tp']
                entry_reason = flip['reason']

        # ── Construir metadata ─────────────────
        metadata = {
            'current_price': price,
            'trend': 'BULLISH' if self._trend > 0 else 'BEARISH' if self._trend < 0 else 'NEUTRAL',
            'entry_price': self._entry_price,
            'stop_loss_price': float(self._active_sl) if self._active_sl else (float(sl_price) if sl_price else None),
            'take_profit_price': float(self._active_tp) if self._active_tp else (float(tp_price) if tp_price else None),
            'direction': self._active_dir,
            'ema21': float(ema21[-1]) if len(ema21) > 0 and not np.isnan(ema21[-1]) else None,
            'atr': float(atr) if atr else None,
            'active_snd_zones': len(snd_zones),
            'active_fvg_zones': len(fvg_zones),
            'last_bos': self._last_bos,
            'last_choch': self._last_choch,
            'entry_reason': entry_reason,
            'consecutive_losses': self._consec_losses,
            'trading_enabled': self._trading_enabled,
            'status': 'signal_generated' if signal != 'HOLD' else 'no_signal',
        }

        self._last_signal = signal
        return signal, metadata

    # ──────────────────────────────────────────────────
    # SWING DETECTION
    # ──────────────────────────────────────────────────
    def _detect_swings(self, df: pd.DataFrame) -> List[Dict]:
        """Detecta swing highs y lows usando ventana de lookback."""
        highs = df['High'].values
        lows = df['Low'].values
        closes = df['Close'].values
        n = self.swing_lookback
        swings = []

        for i in range(n, len(df) - n):
            # Swing High
            if highs[i] == max(highs[i-n:i+n+1]):
                swings.append({
                    'type': 'high',
                    'price': float(highs[i]),
                    'index': i,
                    'broken': False
                })
            # Swing Low
            if lows[i] == min(lows[i-n:i+n+1]):
                swings.append({
                    'type': 'low',
                    'price': float(lows[i]),
                    'index': i,
                    'broken': False
                })

        # Filtrar swings demasiado cercanos al final (no confirmados)
        confirmed = [s for s in swings if s['index'] < len(df) - 2]
        self._swings = confirmed
        return confirmed

    # ──────────────────────────────────────────────────
    # BOS / CHoCH DETECTION
    # ──────────────────────────────────────────────────
    def _analyze_structure(self, swings: List[Dict], df: pd.DataFrame) -> Dict:
        """Analiza estructura de mercado: BOS y CHoCH."""
        if len(swings) < 4:
            return {'bos': None, 'choch': None, 'trend': 0}

        price = float(df['Close'].iloc[-1])

        # Últimos swing highs y lows
        swing_highs = [s for s in swings if s['type'] == 'high']
        swing_lows = [s for s in swings if s['type'] == 'low']

        bos = None
        choch = None
        trend = self._trend

        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            last_sh = swing_highs[-1]
            prev_sh = swing_highs[-2]
            last_sl = swing_lows[-1]
            prev_sl = swing_lows[-2]

            # BOS Alcista: precio rompe swing high anterior
            if price > last_sh['price'] and not last_sh['broken']:
                bos = {'type': 'bullish', 'level': last_sh['price'],
                       'index': last_sh['index']}
                last_sh['broken'] = True
                trend = 1

            # BOS Bajista: precio rompe swing low anterior
            elif price < last_sl['price'] and not last_sl['broken']:
                bos = {'type': 'bearish', 'level': last_sl['price'],
                       'index': last_sl['index']}
                last_sl['broken'] = True
                trend = -1

            # CHoCH: cambio de carácter (primer quiebre contra tendencia)
            if self._trend > 0 and price < last_sl['price']:
                choch = {'type': 'bearish', 'level': last_sl['price']}
                trend = -1
            elif self._trend < 0 and price > last_sh['price']:
                choch = {'type': 'bullish', 'level': last_sh['price']}
                trend = 1

            # Estructura Higher Highs / Lower Lows
            if (last_sh['price'] > prev_sh['price'] and
                    last_sl['price'] > prev_sl['price']):
                trend = max(trend, 1)
            elif (last_sh['price'] < prev_sh['price'] and
                  last_sl['price'] < prev_sl['price']):
                trend = min(trend, -1)

        self._trend = trend
        self._last_bos = bos
        self._last_choch = choch

        return {'bos': bos, 'choch': choch, 'trend': trend}

    # ──────────────────────────────────────────────────
    # SUPPLY & DEMAND ZONES
    # ──────────────────────────────────────────────────
    def _identify_snd_zones(self, swings: List[Dict], structure: Dict,
                            df: pd.DataFrame) -> List[Dict]:
        """Identifica zonas SnD responsables de rupturas estructurales."""
        zones = []
        highs = df['High'].values
        lows = df['Low'].values
        opens = df['Open'].values
        closes = df['Close'].values

        bos = structure.get('bos')
        trend = structure.get('trend', 0)

        # Crear zonas desde movimientos impulsivos recientes
        lookback_window = min(50, len(df) - 1)

        for i in range(max(1, len(df) - lookback_window), len(df) - 1):
            # Buscar velas impulsivas que iniciaron un movimiento fuerte
            move = closes[i] - opens[i]
            bar_range = highs[i] - lows[i]

            if bar_range < self.min_swing_size * 0.5:
                continue

            body_ratio = abs(move) / bar_range if bar_range > 0.01 else 0

            # Demanda (origin de subida): vela bajista antes de subida significativa
            if (i + 3 < len(df) and
                    move < 0 and body_ratio > 0.5 and
                    closes[i + 1] > closes[i] and
                    closes[i + 2] > closes[i + 1]):
                # Trazar Fibonacci desde low (liquidez) hasta high del movimiento
                liq_point = float(lows[i])
                origin = float(max(highs[i + 1], highs[i + 2]))
                fib_range = origin - liq_point
                if fib_range > self.min_swing_size:
                    zones.append({
                        'type': 'demand',
                        'high': float(highs[i]),
                        'low': liq_point,
                        'origin': origin,
                        'index': i,
                        'fib_levels': {
                            '30': origin - fib_range * 0.30,
                            '50': origin - fib_range * 0.50,
                            '70': origin - fib_range * 0.70,
                        },
                        'invalidated': False,
                        'strength': body_ratio + (0.3 if bos and bos.get('type') == 'bullish' else 0)
                    })

            # Oferta (origin de bajada): vela alcista antes de bajada significativa
            elif (i + 3 < len(df) and
                  move > 0 and body_ratio > 0.5 and
                  closes[i + 1] < closes[i] and
                  closes[i + 2] < closes[i + 1]):
                liq_point = float(highs[i])
                origin = float(min(lows[i + 1], lows[i + 2]))
                fib_range = liq_point - origin
                if fib_range > self.min_swing_size:
                    zones.append({
                        'type': 'supply',
                        'high': liq_point,
                        'low': float(lows[i]),
                        'origin': origin,
                        'index': i,
                        'fib_levels': {
                            '30': origin + fib_range * 0.30,
                            '50': origin + fib_range * 0.50,
                            '70': origin + fib_range * 0.70,
                        },
                        'invalidated': False,
                        'strength': body_ratio + (0.3 if bos and bos.get('type') == 'bearish' else 0)
                    })

        # Invalidar zonas ya penetradas
        current_price = float(closes[-1])
        for z in zones:
            if z['type'] == 'demand' and current_price < z['low']:
                z['invalidated'] = True
            elif z['type'] == 'supply' and current_price > z['high']:
                z['invalidated'] = True

        valid_zones = [z for z in zones if not z['invalidated']]
        # Ordenar por fuerza (más fuerte primero)
        valid_zones.sort(key=lambda x: x['strength'], reverse=True)

        self._snd_zones = valid_zones[:10]  # Mantener top 10
        return self._snd_zones

    # ──────────────────────────────────────────────────
    # FAIR VALUE GAPS
    # ──────────────────────────────────────────────────
    def _detect_fvg(self, df: pd.DataFrame) -> List[Dict]:
        """Detecta Fair Value Gaps (ineficiencias del mercado)."""
        fvg_list = []
        highs = df['High'].values
        lows = df['Low'].values

        look = min(30, len(df) - 2)
        for i in range(max(1, len(df) - look), len(df) - 1):
            # FVG alcista: gap entre high[i-1] y low[i+1]
            if i + 1 < len(df) and lows[i + 1] > highs[i - 1]:
                gap = float(lows[i + 1] - highs[i - 1])
                if gap > 0.5:
                    mid = float((highs[i - 1] + lows[i + 1]) / 2)
                    fvg_list.append({
                        'type': 'bullish',
                        'top': float(lows[i + 1]),
                        'bottom': float(highs[i - 1]),
                        'mid': mid,
                        'index': i,
                        'filled': False
                    })

            # FVG bajista: gap entre low[i-1] y high[i+1]
            if i + 1 < len(df) and highs[i + 1] < lows[i - 1]:
                gap = float(lows[i - 1] - highs[i + 1])
                if gap > 0.5:
                    mid = float((lows[i - 1] + highs[i + 1]) / 2)
                    fvg_list.append({
                        'type': 'bearish',
                        'top': float(lows[i - 1]),
                        'bottom': float(highs[i + 1]),
                        'mid': mid,
                        'index': i,
                        'filled': False
                    })

        self._fvg_zones = fvg_list
        return fvg_list

    # ──────────────────────────────────────────────────
    # ZONE & FVG ENTRY HELPERS
    # ──────────────────────────────────────────────────
    def _find_active_zone(self, price: float, snd_zones: List[Dict],
                          structure: Dict) -> Optional[Dict]:
        """Encuentra la mejor zona SnD activa donde el precio está retrocediendo."""
        trend = structure.get('trend', 0)

        for zone in snd_zones:
            if zone['invalidated']:
                continue

            fib50 = zone['fib_levels']['50']
            fib30 = zone['fib_levels']['30']
            fib70 = zone['fib_levels']['70']

            if zone['type'] == 'demand' and trend >= 0:
                # El precio debe estar en la zona Fibonacci
                if fib70 <= price <= fib30 or zone['low'] <= price <= zone['high']:
                    return zone

            elif zone['type'] == 'supply' and trend <= 0:
                if fib30 <= price <= fib70 or zone['low'] <= price <= zone['high']:
                    return zone

        return None

    def _check_fvg_entry(self, price, fvg_zones, structure, body_ratio,
                         is_bullish, is_bearish, vol_ok, atr, df):
        """Verifica si hay una entrada válida basada en FVG."""
        trend = structure.get('trend', 0)
        for fvg in fvg_zones:
            if fvg['filled']:
                continue
            if fvg['type'] == 'bullish' and trend >= 0:
                if fvg['bottom'] <= price <= fvg['top'] and is_bullish and body_ratio >= self.body_ratio_min and vol_ok:
                    return True
            elif fvg['type'] == 'bearish' and trend <= 0:
                if fvg['bottom'] <= price <= fvg['top'] and is_bearish and body_ratio >= self.body_ratio_min and vol_ok:
                    return True
        return False

    def _get_fvg_entry(self, price, fvg_zones, structure, body_ratio,
                       is_bullish, is_bearish, atr, df):
        """Retorna la señal de entrada FVG si es válida."""
        trend = structure.get('trend', 0)
        for fvg in fvg_zones:
            if fvg['filled']:
                continue
            if fvg['type'] == 'bullish' and trend >= 0 and is_bullish and body_ratio >= self.body_ratio_min:
                if fvg['bottom'] <= price <= fvg['top']:
                    sl = fvg['bottom'] - (atr * 0.3 if atr else 0.5)
                    tp = price + abs(price - sl) * self.fib_tp_extension
                    self._entry_price = price
                    self._active_sl = sl
                    self._active_tp = tp
                    self._active_dir = 'BUY'
                    self._ema21_breaks = 0
                    return 'BUY', sl, tp, f"Bullish FVG retest at {fvg['mid']:.2f}"

            elif fvg['type'] == 'bearish' and trend <= 0 and is_bearish and body_ratio >= self.body_ratio_min:
                if fvg['bottom'] <= price <= fvg['top']:
                    sl = fvg['top'] + (atr * 0.3 if atr else 0.5)
                    tp = price - abs(sl - price) * self.fib_tp_extension
                    self._entry_price = price
                    self._active_sl = sl
                    self._active_tp = tp
                    self._active_dir = 'SELL'
                    self._ema21_breaks = 0
                    return 'SELL', sl, tp, f"Bearish FVG retest at {fvg['mid']:.2f}"
        return None

    # ──────────────────────────────────────────────────
    # EMA21 TRAILING STOP
    # ──────────────────────────────────────────────────
    def _update_ema_trailing(self, price: float, low: float, high: float,
                             ema21: float):
        """
        Trailing stop dinámico con EMA21.
        Regla: si el precio cierra bajo EMA21, pero la siguiente vela
        recupera, el stop se coloca debajo de ese mínimo.
        Tras 3-4 quiebres, el stop debe estar muy pegado al precio.
        """
        if self._active_dir == 'BUY':
            if price < ema21:
                # Quiebre bajo EMA21
                self._ema21_breaks += 1
            elif price > ema21 and self._ema21_breaks > 0:
                # Recuperación — ajustar SL debajo del mínimo
                new_sl = low - 0.25  # Un tick debajo
                if new_sl > self._active_sl:
                    self._active_sl = new_sl

            # Después de múltiples quiebres, trailing agresivo
            if self._ema21_breaks >= 3:
                aggressive_sl = ema21 - 0.5
                if aggressive_sl > self._active_sl:
                    self._active_sl = aggressive_sl

        elif self._active_dir == 'SELL':
            if price > ema21:
                self._ema21_breaks += 1
            elif price < ema21 and self._ema21_breaks > 0:
                new_sl = high + 0.25
                if new_sl < self._active_sl:
                    self._active_sl = new_sl

            if self._ema21_breaks >= 3:
                aggressive_sl = ema21 + 0.5
                if aggressive_sl < self._active_sl:
                    self._active_sl = aggressive_sl

    # ──────────────────────────────────────────────────
    # DIRECTION FLIP
    # ──────────────────────────────────────────────────
    def _check_direction_flip(self, price: float, snd_zones: List[Dict]) -> Optional[Dict]:
        """
        Si el precio toca una zona SnD contraria, cerrar y revertir.
        """
        if not self._active_dir or not self._snd_zones:
            return None

        for zone in snd_zones:
            if zone['invalidated']:
                continue

            if self._active_dir == 'BUY' and zone['type'] == 'supply':
                if zone['low'] <= price <= zone['high']:
                    # Cerrar BUY, abrir SELL
                    sl = zone['high'] + 0.5
                    tp = price - abs(sl - price) * self.fib_tp_extension
                    self._entry_price = price
                    self._active_sl = sl
                    self._active_tp = tp
                    self._active_dir = 'SELL'
                    self._ema21_breaks = 0
                    return {'signal': 'SELL', 'sl': sl, 'tp': tp,
                            'reason': 'Direction flip at supply zone'}

            elif self._active_dir == 'SELL' and zone['type'] == 'demand':
                if zone['low'] <= price <= zone['high']:
                    sl = zone['low'] - 0.5
                    tp = price + abs(price - sl) * self.fib_tp_extension
                    self._entry_price = price
                    self._active_sl = sl
                    self._active_tp = tp
                    self._active_dir = 'BUY'
                    self._ema21_breaks = 0
                    return {'signal': 'BUY', 'sl': sl, 'tp': tp,
                            'reason': 'Direction flip at demand zone'}

        return None

    # ──────────────────────────────────────────────────
    # UTILIDADES INTERNAS
    # ──────────────────────────────────────────────────
    def _calc_ema(self, series: pd.Series, period: int) -> np.ndarray:
        """Calcula EMA."""
        return series.ewm(span=period, adjust=False).mean().values

    def _calc_atr(self, df: pd.DataFrame) -> Optional[float]:
        """Calcula ATR."""
        if 'ATR' in df.columns:
            val = df['ATR'].iloc[-1]
            return float(val) if not np.isnan(val) else None

        highs = df['High'].values
        lows = df['Low'].values
        closes = df['Close'].values
        tr_list = []
        for i in range(1, len(df)):
            tr = max(highs[i] - lows[i],
                     abs(highs[i] - closes[i-1]),
                     abs(lows[i] - closes[i-1]))
            tr_list.append(tr)

        if len(tr_list) < self.atr_period:
            return None

        atr = np.mean(tr_list[-self.atr_period:])
        return float(atr)

    def _check_volume(self, df: pd.DataFrame) -> bool:
        """Verifica confirmación de volumen."""
        if 'Volume' not in df.columns:
            return True
        recent = df['Volume'].iloc[-(self.vol_period + 1):]
        avg_vol = recent.iloc[:-1].mean()
        curr_vol = recent.iloc[-1]
        if avg_vol == 0:
            return True
        return curr_vol >= avg_vol * self.vol_mult

    def _check_daily_reset(self, df: pd.DataFrame):
        """Resetea estado diario."""
        try:
            current_day = df.index[-1].date()
        except AttributeError:
            return

        if self._current_day != current_day:
            self._current_day = current_day
            self._snd_zones = []
            self._fvg_zones = []
            if self.use_dd_protection and not self._trading_enabled:
                self._trading_enabled = True

    # ──────────────────────────────────────────────────
    # CALLBACKS (llamados por la plataforma)
    # ──────────────────────────────────────────────────
    def notify_trade_closed(self, profit: float):
        """Notificación de cierre de operación."""
        if profit < 0:
            self._consec_losses += 1
            if self._consec_losses >= self.max_consec_losses:
                self._trading_enabled = False
        else:
            self._consec_losses = 0

        self._entry_price = None
        self._active_sl = None
        self._active_tp = None
        self._active_dir = None
        self._active_zone = None
        self._ema21_breaks = 0

    def reset(self):
        """Reinicia estado (backtesting)."""
        self._swings = []
        self._snd_zones = []
        self._fvg_zones = []
        self._trend = 0
        self._last_bos = None
        self._last_choch = None
        self._active_zone = None
        self._entry_price = None
        self._active_sl = None
        self._active_tp = None
        self._active_dir = None
        self._ema21_breaks = 0
        self._consec_losses = 0
        self._trading_enabled = True
        self._current_day = None
        self._last_signal = 'HOLD'
