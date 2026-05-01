import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple


class CustomStrategy:
    """
    🚀 VOLBREAK SYSTEM — Estrategia de Breakout Dinámico
    ======================================================
    Autor original (MQ5): Pablo Ez. Moscardo - Punto & Coma trading
    Adaptación Python: Compatible con plataformas algorítmicas

    LÓGICA DE LA ESTRATEGIA:
    ─────────────────────────────────────────────────────────────────
    1. Calcula el máximo y mínimo de las últimas N velas (lookback).
    2. Si el precio rompe el máximo  →  señal BUY  (breakout alcista)
    3. Si el precio rompe el mínimo  →  señal SELL (breakout bajista)
    4. El rango (max - min) debe superar un umbral R para evitar ruido.
    5. Confirmación con volumen: la vela actual debe tener volumen
       superior al promedio de las últimas 'volume_period' velas.
    6. Stop loss dinámico basado en ATR (Average True Range).
    7. Take profit calculado como SL × risk_reward_ratio.
    8. Protección de drawdown diario y pérdidas consecutivas.
    9. Filtro de horario configurable (horas de alta liquidez).

    ESTRUCTURA:
    ─────────────────────────────────────────────────────────────────
    1. __init__ : Parámetros, gestión de riesgo, estado interno.
    2. update   : Recibe un DataFrame y retorna señal + metadata.
    """

    # ──────────────────────────────────────────────────────────────
    # BLOQUE 1: CONFIGURACIÓN Y RIESGO
    # ──────────────────────────────────────────────────────────────
    def __init__(self, config: Dict = None):
        self.config = config or {}

        # --- ESTRATEGIA: PARÁMETROS DE BREAKOUT ---
        self.n_lookback      = int(self.config.get('n_lookback', 5))       # Barras lookback
        self.min_range       = float(self.config.get('min_range', 1.0))    # Rango mínimo R

        # --- FILTRO DE VOLUMEN ---
        self.use_volume_filter    = bool(self.config.get('use_volume_filter', True))
        self.volume_period        = int(self.config.get('volume_period', 20))
        self.min_volume_mult      = float(self.config.get('min_volume_multiplier', 1.2))

        # --- ATR (STOP LOSS DINÁMICO) ---
        self.use_atr_filter  = bool(self.config.get('use_atr_filter', True))
        self.atr_period      = int(self.config.get('atr_period', 14))
        self.atr_multiplier  = float(self.config.get('atr_multiplier', 1.5))

        # --- GESTIÓN DE RIESGO ---
        self.stop_loss       = float(self.config.get('stop_loss', 15.0))   # Puntos SL fijo (fallback)
        self.risk_reward     = float(self.config.get('risk_reward', 2.0))  # Ratio RR
        self.take_profit     = self.stop_loss * self.risk_reward            # Calculado automáticamente

        # --- FILTRO DE HORARIO (hora del broker, 0-23) ---
        self.use_time_filter = bool(self.config.get('use_time_filter', False))
        self.start_hour      = int(self.config.get('start_hour', 9))
        self.start_minute    = int(self.config.get('start_minute', 30))
        self.end_hour        = int(self.config.get('end_hour', 16))
        self.end_minute      = int(self.config.get('end_minute', 0))

        # --- PROTECCIÓN DE DRAWDOWN ---
        self.use_dd_protection      = bool(self.config.get('use_drawdown_protection', True))
        self.max_daily_loss_pct     = float(self.config.get('max_daily_loss_pct', 3.0))
        self.max_consecutive_losses = int(self.config.get('max_consecutive_losses', 3))

        # --- TRAILING STOP ---
        self.use_trailing_stop      = bool(self.config.get('use_trailing_stop', True))
        self.trailing_start_pts     = float(self.config.get('trailing_start_points', 20.0))
        self.trailing_step_pts      = float(self.config.get('trailing_step_points', 5.0))

        # ── ESTADO INTERNO ──────────────────────────────────────
        self._last_signal         = 'HOLD'
        self._signal_triggered    = False   # Una sola entrada por sesión (wakeupTriggered)
        self._current_day         = None
        self._daily_start_balance = None
        self._consecutive_losses  = 0
        self._trading_enabled     = True

        # Niveles de la operación activa
        self._entry_price         = None
        self._active_sl           = None
        self._active_tp           = None
        self._active_direction    = None  # 'BUY' | 'SELL'

    # ──────────────────────────────────────────────────────────────
    # BLOQUE 2: TOMA DE DECISIONES (método principal)
    # ──────────────────────────────────────────────────────────────
    def update(self, df: pd.DataFrame) -> Tuple[str, Dict]:
        """
        Se ejecuta con cada nueva vela.

        Parámetros
        ----------
        df : pd.DataFrame
            Columnas requeridas: 'Open', 'High', 'Low', 'Close', 'Volume'.
            El índice puede ser datetime (recomendado) o entero.

        Retorna
        -------
        señal    : 'BUY' | 'SELL' | 'HOLD'
        metadata : dict con niveles, indicadores y estado de la estrategia.
        """
        min_bars = max(self.n_lookback, self.atr_period, self.volume_period) + 2
        if len(df) < min_bars:
            return 'HOLD', {'status': 'waiting_data', 'bars_needed': min_bars}

        # ── Paso 1: Reset diario ─────────────────────────────────
        self._check_daily_reset(df)

        # ── Paso 2: Protección de drawdown ───────────────────────
        if self.use_dd_protection and not self._trading_enabled:
            return 'HOLD', {
                'status': 'trading_disabled',
                'reason': 'drawdown_protection',
                'consecutive_losses': self._consecutive_losses,
            }

        # ── Paso 3: Filtro de horario ─────────────────────────────
        if self.use_time_filter and not self._is_time_to_trade(df):
            return 'HOLD', {'status': 'outside_trading_hours'}

        # ── Paso 4: Indicadores ───────────────────────────────────
        atr_value     = self._calculate_atr(df)
        volume_ok     = self._check_volume(df)

        # Lookback: máx y mín de las N velas anteriores (excluye la actual)
        lookback      = df.iloc[-(self.n_lookback + 1):-1]
        max_high      = lookback['High'].max()
        min_low       = lookback['Low'].min()
        price_range   = max_high - min_low
        current_price = df['Close'].iloc[-1]

        # ── Paso 5: Lógica de breakout ────────────────────────────
        signal   = 'HOLD'
        sl_price = None
        tp_price = None

        if price_range > self.min_range and not self._signal_triggered:

            if current_price > max_high:
                # ── BREAKOUT ALCISTA ──
                if not self.use_volume_filter or volume_ok:
                    sl_price = self._calc_sl(current_price, atr_value, is_long=True)
                    tp_price = self._calc_tp(current_price, sl_price, is_long=True)
                    signal   = 'BUY'
                    self._signal_triggered = True
                    self._entry_price      = current_price
                    self._active_sl        = sl_price
                    self._active_tp        = tp_price
                    self._active_direction = 'BUY'

            elif current_price < min_low:
                # ── BREAKOUT BAJISTA ──
                if not self.use_volume_filter or volume_ok:
                    sl_price = self._calc_sl(current_price, atr_value, is_long=False)
                    tp_price = self._calc_tp(current_price, sl_price, is_long=False)
                    signal   = 'SELL'
                    self._signal_triggered = True
                    self._entry_price      = current_price
                    self._active_sl        = sl_price
                    self._active_tp        = tp_price
                    self._active_direction = 'SELL'

        # ── Paso 6: Trailing stop (actualiza SL si hay posición activa) ──
        updated_sl = None
        if self.use_trailing_stop and self._entry_price is not None:
            updated_sl = self._update_trailing_stop(current_price)

        self._last_signal = signal

        # ── Paso 7: Armar metadata ────────────────────────────────
        metadata = {
            'current_price'        : float(current_price),
            'range_high'           : float(max_high),
            'range_low'            : float(min_low),
            'range_size'           : float(price_range),
            'min_range_required'   : float(self.min_range),
            'atr'                  : float(atr_value) if atr_value else None,
            'volume_confirmation'  : bool(volume_ok),
            'signal_triggered'     : self._signal_triggered,
            'trading_enabled'      : self._trading_enabled,
            'consecutive_losses'   : self._consecutive_losses,
            # Niveles de la operación (si hay señal activa)
            'entry_price'          : float(self._entry_price) if self._entry_price else None,
            'stop_loss_price'      : float(updated_sl or self._active_sl) if self._active_sl else None,
            'take_profit_price'    : float(self._active_tp) if self._active_tp else None,
            'risk_reward_ratio'    : self.risk_reward,
            'direction'            : self._active_direction,
            # Resumen legible
            'risk_info'            : (
                f"SL: {self._active_sl:.2f} | TP: {self._active_tp:.2f}"
                if self._active_sl else f"SL: {self.stop_loss} pts | RR: {self.risk_reward}"
            ),
            'status'               : 'signal_generated' if signal != 'HOLD' else 'no_signal',
        }

        return signal, metadata

    # ──────────────────────────────────────────────────────────────
    # MÉTODOS AUXILIARES (privados)
    # ──────────────────────────────────────────────────────────────

    def _check_daily_reset(self, df: pd.DataFrame) -> None:
        """Resetea el flag de señal al comenzar un nuevo día."""
        try:
            current_day = df.index[-1].date()
        except AttributeError:
            return  # índice no es datetime, no aplica

        if self._current_day != current_day:
            self._current_day      = current_day
            self._signal_triggered = False
            # Reactivar trading al inicio del día (solo bloqueo diario)
            if self.use_dd_protection and not self._trading_enabled:
                self._trading_enabled = True

    def _is_time_to_trade(self, df: pd.DataFrame) -> bool:
        """Verifica si la hora actual está dentro de la ventana de trading."""
        try:
            ts = df.index[-1]
            current_minutes = ts.hour * 60 + ts.minute
            start_minutes   = self.start_hour * 60 + self.start_minute
            end_minutes     = self.end_hour   * 60 + self.end_minute
            return start_minutes <= current_minutes < end_minutes
        except AttributeError:
            return True  # Sin índice datetime, no filtramos

    def _calculate_atr(self, df: pd.DataFrame) -> float:
        """Calcula el ATR (Average True Range) de las últimas 'atr_period' velas."""
        highs  = df['High'].values
        lows   = df['Low'].values
        closes = df['Close'].values

        tr_list = []
        for i in range(1, len(df)):
            tr = max(
                highs[i]  - lows[i],
                abs(highs[i]  - closes[i - 1]),
                abs(lows[i]   - closes[i - 1]),
            )
            tr_list.append(tr)

        tr_series = pd.Series(tr_list)
        atr = tr_series.rolling(window=self.atr_period).mean().iloc[-1]
        return float(atr) if not np.isnan(atr) else None

    def _check_volume(self, df: pd.DataFrame) -> bool:
        """Verifica que el volumen actual supere el promedio × multiplicador."""
        if 'Volume' not in df.columns:
            return True  # Sin datos de volumen, no bloqueamos
        recent    = df['Volume'].iloc[-(self.volume_period + 1):]
        avg_vol   = recent.iloc[:-1].mean()
        curr_vol  = recent.iloc[-1]
        if avg_vol == 0:
            return True
        return curr_vol >= avg_vol * self.min_volume_mult

    def _calc_sl(self, price: float, atr: float, is_long: bool) -> float:
        """Calcula el nivel de Stop Loss (ATR dinámico o fijo)."""
        if self.use_atr_filter and atr is not None:
            sl_dist = max(atr * self.atr_multiplier, self.stop_loss)
        else:
            sl_dist = self.stop_loss
        return price - sl_dist if is_long else price + sl_dist

    def _calc_tp(self, price: float, sl: float, is_long: bool) -> float:
        """Calcula el nivel de Take Profit usando el ratio Risk/Reward."""
        sl_dist = abs(price - sl)
        tp_dist = sl_dist * self.risk_reward
        return price + tp_dist if is_long else price - tp_dist

    def _update_trailing_stop(self, current_price: float) -> float | None:
        """
        Actualiza el SL activo si el precio se mueve a favor.
        Retorna el nuevo SL si fue ajustado, o None.
        """
        if self._entry_price is None or self._active_sl is None:
            return None

        if self._active_direction == 'BUY':
            profit_pts = current_price - self._entry_price
            if profit_pts >= self.trailing_start_pts:
                new_sl = current_price - self.trailing_step_pts
                if new_sl > self._active_sl:
                    self._active_sl = new_sl
                    return new_sl

        elif self._active_direction == 'SELL':
            profit_pts = self._entry_price - current_price
            if profit_pts >= self.trailing_start_pts:
                new_sl = current_price + self.trailing_step_pts
                if new_sl < self._active_sl:
                    self._active_sl = new_sl
                    return new_sl

        return None

    # ──────────────────────────────────────────────────────────────
    # MÉTODOS PÚBLICOS (llamados por la plataforma o backtest)
    # ──────────────────────────────────────────────────────────────

    def notify_trade_closed(self, profit: float) -> None:
        """
        Notificar a la estrategia que una operación fue cerrada.
        La plataforma debe llamar este método con el P&L de la operación.
        """
        if profit < 0:
            self._consecutive_losses += 1
            if (self.use_dd_protection and
                    self._consecutive_losses >= self.max_consecutive_losses):
                self._trading_enabled = False
        else:
            self._consecutive_losses = 0

        # Resetear posición activa
        self._entry_price      = None
        self._active_sl        = None
        self._active_tp        = None
        self._active_direction = None
        self._signal_triggered = False

    def notify_balance(self, current_balance: float, daily_start: float) -> None:
        """
        Verificar drawdown diario.
        La plataforma debe llamar este método con el balance actual y el del inicio del día.
        """
        if not self.use_dd_protection or daily_start == 0:
            return
        loss_pct = (daily_start - current_balance) / daily_start * 100.0
        if loss_pct >= self.max_daily_loss_pct:
            self._trading_enabled = False

    def reset(self) -> None:
        """Reinicia el estado interno (útil para backtesting por períodos)."""
        self._last_signal         = 'HOLD'
        self._signal_triggered    = False
        self._current_day         = None
        self._consecutive_losses  = 0
        self._trading_enabled     = True
        self._entry_price         = None
        self._active_sl           = None
        self._active_tp           = None
        self._active_direction    = None