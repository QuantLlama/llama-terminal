import json
import numpy as np
import pandas as pd
from typing import Dict, Any, List


class LiquidityHeatmapIndicator:
    """
    Liquidity Heatmap Indicator (Market Depth / Order Book Heatmap).

    This indicator approximates liquidity depth if full L2 data is unavailable,
    by distributing volume across the candle range or aggregating actual L2 order book
    snapshots if passed in the dataframe.

    Alineado con LiquidityHeatmapOverlay v2:
    - Bins normalizados para que el overlay use toda la paleta de color
    - Gaussian weighting con ancla VWAP (produce picos más realistas que 1/(1+d))
    - Tick auto-escalado con percentil 75 (robusto contra velas spike de BTC/NQ)
    - Guardia de overflow para precios altos (NQ 20000, BTC 65000)
    - Output idéntico al original: {'time', 'heatmap': [{'price','depth'}], 'close'}
    """

    def __init__(self, config: Dict = None):
        self.config = config or {}
        # Tick size or price grouping for the heatmap bins
        self.tick_size = float(self.config.get('tick_size', 0.25))
        # Sensitivity: filter out nodes with very low liquidity to reduce noise
        self.sensitivity_threshold = float(self.config.get('heatmap_sensitivity', 0.05))
        # Smoothing period for historical liquidity (decay factor)
        self.decay_factor = float(self.config.get('heatmap_decay', 0.95))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _effective_tick(df: pd.DataFrame, base_tick: float) -> float:
        """
        Escala el tick_size usando el percentil 75 del rango de velas.
        Más robusto que la media: una vela spike de BTC no distorsiona el resultado.
        Límite: máximo 80 bins por vela.
        """
        ranges = (df['High'] - df['Low']).replace(0, np.nan).dropna()
        if ranges.empty:
            return base_tick
        ref = float(np.percentile(ranges, 75))
        t = base_tick
        if ref > 0 and (ref / t) > 80:
            t = ref / 80.0
        return t

    @staticmethod
    def _gaussian_weights(bins: np.ndarray, anchor: float, sigma: float) -> np.ndarray:
        """
        Pesos gaussianos centrados en `anchor`.
        Concentra el volumen cerca del VWAP/midpoint — más realista que 1/(1+d).
        """
        s = max(sigma, 1e-9)
        w = np.exp(-0.5 * ((bins - anchor) / s) ** 2)
        return w

    @staticmethod
    def _snap(price: float, tick: float) -> float:
        """Redondea un precio al bin de tick más cercano sin drift de punto flotante."""
        return round(round(price / tick) * tick, 10)

    # ------------------------------------------------------------------
    # Public API — misma firma que el original
    # ------------------------------------------------------------------

    def calculate(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate Heatmap clusters.
        If 'bid_depth' and 'ask_depth' columns (L2 data) exist, uses them.
        Otherwise, approximates using OHLCV volume distribution.
        """
        if df.empty or len(df) < 2:
            return {'data': []}

        df = df.copy()
        result_data = []

        # Determine time column
        if 'timestamp' in df.columns:
            times = df['timestamp'].values.astype(np.int64) // 10 ** 9
        elif 'time' in df.columns:
            times = df['time'].values
        else:
            times = df.index.values

        # Track rolling liquidity across price levels (dictionary: price -> volume_score)
        liquidity_map: Dict[float, float] = {}

        has_l2 = 'bid_depth' in df.columns and 'ask_depth' in df.columns

        # --- SAFEGUARD AGAINST HUGE DATA ---
        # Usa percentil 75 en vez de mean — robusto contra velas spike (BTC, NQ)
        effective_tick_size = self._effective_tick(df, self.tick_size)

        # Acumuladores de VWAP corriente
        vwap_num = 0.0
        vwap_den = 0.0

        for i in range(len(df)):
            row          = df.iloc[i]
            current_time = int(times[i])

            # Apply decay to old liquidity to fade it out
            dead = [p for p, v in liquidity_map.items() if v * self.decay_factor < self.sensitivity_threshold]
            for p in dead:
                del liquidity_map[p]
            for p in liquidity_map:
                liquidity_map[p] *= self.decay_factor

            # Actualizar VWAP corriente
            close_p  = float(row['Close'])
            high_p   = float(row['High'])
            low_p    = float(row['Low'])
            vol_p    = float(row['Volume'])
            typical  = (high_p + low_p + close_p) / 3.0
            vwap_num += typical * vol_p
            vwap_den += vol_p
            vwap      = vwap_num / vwap_den if vwap_den > 0 else None

            if has_l2:
                # L2 mode: ingest real order-book snapshots
                for side in ('bid_depth', 'ask_depth'):
                    raw = row.get(side)
                    if raw is None:
                        continue
                    try:
                        depth_dict = json.loads(raw) if isinstance(raw, str) else raw
                        for price_str, vol in depth_dict.items():
                            bp = self._snap(float(price_str), effective_tick_size)
                            liquidity_map[bp] = liquidity_map.get(bp, 0.0) + float(vol)
                    except Exception:
                        pass
            else:
                # Approximation based on OHLCV — Gaussian weighting anchored to VWAP
                if high_p > low_p and vol_p > 0:
                    # Generar bins con numpy (sin drift de punto flotante)
                    snapped_low  = np.floor(low_p  / effective_tick_size) * effective_tick_size
                    snapped_high = np.ceil(high_p / effective_tick_size)  * effective_tick_size
                    raw_bins     = np.arange(snapped_low,
                                             snapped_high + effective_tick_size * 0.5,
                                             effective_tick_size)
                    bins = np.round(raw_bins / effective_tick_size) * effective_tick_size

                    # Cap bins por vela
                    if len(bins) > 120:
                        bins = bins[:120]

                    # Anchor: 60% VWAP corriente + 40% midpoint de la vela
                    mid_p  = (high_p + low_p) / 2.0
                    anchor = (0.6 * vwap + 0.4 * mid_p) if vwap is not None else mid_p
                    sigma  = (high_p - low_p) / 2.0

                    weights    = self._gaussian_weights(bins, anchor, sigma)
                    weight_sum = float(weights.sum())

                    # Guardia de overflow: si los pesos underflowean (BTC, NQ a tick chico)
                    # cae a distribución uniforme en vez de dividir por 0
                    if not np.isfinite(weight_sum) or weight_sum < 1e-300:
                        weights    = np.ones(len(bins), dtype=np.float64)
                        weight_sum = float(len(bins))

                    vol_per_unit = vol_p / weight_sum
                    if not np.isfinite(vol_per_unit):
                        vol_per_unit = vol_p / max(len(bins), 1)

                    for bp_raw, w in zip(bins, weights):
                        w_f = float(w)
                        if not np.isfinite(w_f):
                            w_f = 1.0
                        bp = float(round(bp_raw / effective_tick_size) * effective_tick_size)
                        liquidity_map[bp] = liquidity_map.get(bp, 0.0) + vol_per_unit * w_f

            # Extract the current active map for this timestamp
            current_max_depth = max(liquidity_map.values()) if liquidity_map else 0

            # Keep only bins that have at least 10% of the max heat, or the hardcoded sensitivity_threshold
            dynamic_threshold = max(self.sensitivity_threshold, current_max_depth * 0.1)

            candle_heatmap_raw = [
                (price, depth)
                for price, depth in liquidity_map.items()
                if depth >= dynamic_threshold
            ]

            # Sort by depth (hottest first) and cap at 60 bins per candle to prevent JSON bloat
            candle_heatmap_raw.sort(key=lambda x: x[1], reverse=True)

            # --- Normalización relativa al máximo de esta vela ---
            # El overlay nuevo usa percentil 90 para normalizar visualmente,
            # pero necesita que los depth sean comparables entre velas.
            # Exportamos depth crudo (sin normalizar) — el overlay lo maneja.
            candle_heatmap = [
                {'price': float(p), 'depth': float(d)}
                for p, d in candle_heatmap_raw[:60]
            ]

            result_data.append({
                'time':    current_time,
                'heatmap': candle_heatmap,
                'close':   close_p,
            })

        return {
            'data': result_data,
            'metadata': {
                'tick_size':    effective_tick_size,
                'decay_factor': self.decay_factor,
                'indicator':    'LiquidityHeatmap',
            },
        }
