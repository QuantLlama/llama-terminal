import time
import logging
import json
import os
from typing import Optional, Dict, Any, List
from datetime import datetime
from collections import deque
import threading
from .models import (
    OrderRequest, ValidationResult, RiskLimits, RejectionReason, 
    OrderSource, OrderSide
)
logger = logging.getLogger(__name__)
class RiskValidator:
    def __init__(self, limits: RiskLimits = None, config_path: str = None):
        self._limits = limits or RiskLimits()
        self._config_path = config_path
        self._lock = threading.RLock()
        self._daily_orders: int = 0
        self._daily_algo_orders: int = 0
        self._daily_manual_orders: int = 0
        self._daily_pnl: float = 0.0
        self._current_date: str = datetime.now().strftime("%Y-%m-%d")
        self._recent_orders: deque = deque(maxlen=1000)
        self._positions: Dict[str, float] = {}  
        self._load_config()
        logger.info("RiskValidator inicializado")
    def _load_config(self) -> None:
        if self._config_path and os.path.exists(self._config_path):
            try:
                with open(self._config_path, 'r') as f:
                    data = json.load(f)
                    risk_config = data.get('risk_limits', {})
                    self._limits = RiskLimits.from_dict(risk_config)
                    logger.info(f"Configuración de riesgo cargada desde {self._config_path}")
            except Exception as e:
                logger.error(f"Error cargando configuración de riesgo: {e}")
    def validate(self, order: OrderRequest, current_price: float = None) -> ValidationResult:
        validation_start = time.time()
        warnings: List[str] = []
        with self._lock:
            self._check_daily_reset()
            result = self._validate_symbol(order)
            if not result.is_valid:
                return result
            result = self._validate_size(order)
            if not result.is_valid:
                return result
            if current_price and order.price > 0:
                result = self._validate_price(order, current_price)
                if not result.is_valid:
                    return result
            result = self._validate_daily_limits(order)
            if not result.is_valid:
                return result
            result = self._validate_daily_loss()
            if not result.is_valid:
                return result
            result = self._validate_rate_limit(order)
            if not result.is_valid:
                return result
            result = self._validate_trading_hours(order.symbol)
            if not result.is_valid:
                return result
            result = self._validate_position_size(order)
            if not result.is_valid:
                return result
            if order.source == OrderSource.ALGO:
                if self._daily_algo_orders >= self._limits.algo_max_orders_per_day * 0.8:
                    warnings.append(f"Cerca del límite de órdenes ALGO ({self._daily_algo_orders}/{self._limits.algo_max_orders_per_day})")
            validation_time = (time.time() - validation_start) * 1000
            logger.info(
                f"Orden validada OK: {order.symbol} {order.side.value} {order.quantity} "
                f"[{order.source.value}] - {validation_time:.1f}ms"
            )
            return ValidationResult(
                is_valid=True,
                message="Orden válida",
                warnings=warnings
            )
    def _check_daily_reset(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._current_date:
            logger.info(f"Reset diario de contadores ({self._current_date} -> {today})")
            self._current_date = today
            self._daily_orders = 0
            self._daily_algo_orders = 0
            self._daily_manual_orders = 0
            self._daily_pnl = 0.0
            self._recent_orders.clear()
    def _validate_symbol(self, order: OrderRequest) -> ValidationResult:
        if self._limits.allowed_symbols and order.symbol not in self._limits.allowed_symbols:
            return ValidationResult(
                is_valid=False,
                rejection_reason=RejectionReason.RISK_SYMBOL_NOT_ALLOWED,
                message=f"Símbolo {order.symbol} no está en la lista de permitidos"
            )
        if not order.symbol or len(order.symbol) < 1:
            return ValidationResult(
                is_valid=False,
                rejection_reason=RejectionReason.VALIDATION_INVALID_SYMBOL,
                message="Símbolo inválido"
            )
        return ValidationResult(is_valid=True)
    def _validate_size(self, order: OrderRequest) -> ValidationResult:
        if order.quantity <= 0:
            return ValidationResult(
                is_valid=False,
                rejection_reason=RejectionReason.VALIDATION_INVALID_SIZE,
                message="Cantidad debe ser mayor a 0"
            )
        min_size = self._limits.min_order_size
        if order.quantity < min_size:
            return ValidationResult(
                is_valid=False,
                rejection_reason=RejectionReason.VALIDATION_INVALID_SIZE,
                message=f"Cantidad mínima: {min_size}"
            )
        max_size = self._limits.max_position_size
        if order.source == OrderSource.ALGO:
            max_size = self._limits.algo_max_position_size
        if order.quantity > max_size:
            return ValidationResult(
                is_valid=False,
                rejection_reason=RejectionReason.RISK_MAX_POSITION_SIZE,
                message=f"Cantidad excede límite ({order.quantity} > {max_size})"
            )
        return ValidationResult(is_valid=True)
    def _validate_price(self, order: OrderRequest, current_price: float) -> ValidationResult:
        if order.price <= 0:
            return ValidationResult(
                is_valid=False,
                rejection_reason=RejectionReason.VALIDATION_INVALID_PRICE,
                message="Precio inválido"
            )
        deviation_pct = abs(order.price - current_price) / current_price * 100
        if deviation_pct > self._limits.max_price_deviation_pct:
            return ValidationResult(
                is_valid=False,
                rejection_reason=RejectionReason.RISK_PRICE_DEVIATION,
                message=f"Desviación de precio muy alta ({deviation_pct:.1f}% > {self._limits.max_price_deviation_pct}%)"
            )
        return ValidationResult(is_valid=True)
    def _validate_daily_limits(self, order: OrderRequest) -> ValidationResult:
        if self._daily_orders >= self._limits.max_orders_per_day:
            return ValidationResult(
                is_valid=False,
                rejection_reason=RejectionReason.RISK_MAX_ORDERS,
                message=f"Límite diario de órdenes alcanzado ({self._limits.max_orders_per_day})"
            )
        if order.source == OrderSource.ALGO:
            if self._daily_algo_orders >= self._limits.algo_max_orders_per_day:
                return ValidationResult(
                    is_valid=False,
                    rejection_reason=RejectionReason.RISK_MAX_ORDERS,
                    message=f"Límite diario de órdenes ALGO alcanzado ({self._limits.algo_max_orders_per_day})"
                )
        return ValidationResult(is_valid=True)
    def _validate_daily_loss(self) -> ValidationResult:
        if self._daily_pnl <= -self._limits.max_daily_loss:
            return ValidationResult(
                is_valid=False,
                rejection_reason=RejectionReason.RISK_MAX_DAILY_LOSS,
                message=f"Límite de pérdida diaria alcanzado (${abs(self._daily_pnl):.2f})"
            )
        return ValidationResult(is_valid=True)
    def _validate_rate_limit(self, order: OrderRequest) -> ValidationResult:
        now = time.time()
        one_minute_ago = now - 60
        recent_count = sum(1 for t in self._recent_orders if t > one_minute_ago)
        if recent_count >= self._limits.max_orders_per_minute:
            return ValidationResult(
                is_valid=False,
                rejection_reason=RejectionReason.RISK_MAX_ORDERS,
                message=f"Rate limit excedido ({self._limits.max_orders_per_minute}/min)"
            )
        return ValidationResult(is_valid=True)
    def _get_market_type(self, symbol: str) -> str:
        symbol_upper = symbol.upper()
        crypto_indicators = ['BTC', 'ETH', 'SOL', 'USDT', 'USDC', 'ADA', 'XRP', 'DOT', 'DOGE', 'SHIB', 'LTC', 'LINK', 'BNB', 'AVAX', 'MATIC', 'XLM', 'ATOM', 'UNI']
        is_crypto = False
        if any(x in symbol_upper for x in crypto_indicators) or "/" in symbol_upper or "-" in symbol_upper:
            is_crypto = True
        elif symbol_upper.endswith("USD") or symbol_upper.endswith("USDT") or symbol_upper.endswith("USDC"):
            fiat_bases = ['EUR', 'GBP', 'AUD', 'NZD', 'CAD', 'CHF', 'JPY', 'XAU', 'XAG']
            if not any(symbol_upper.startswith(fiat) for fiat in fiat_bases):
                is_crypto = True
        if is_crypto:
            if not (len(symbol_upper) == 6 and any(pair in symbol_upper for pair in ['EUR', 'GBP', 'JPY', 'AUD', 'NZD', 'CAD', 'CHF'])):
                return 'crypto'
        futures_indicators = ['MNQ', 'MES', 'NQ', 'ES', 'YM', 'RTY', 'CL', 'GC', 'SI', 'HG']
        if any(x in symbol_upper for x in futures_indicators):
            return 'futures'
        if any(x in symbol_upper for x in ['MNQ', 'MES', 'NQ', 'ES', 'YM', 'RTY', 'CL', 'GC', 'SI']):
            return 'futures'
        forex_base = ['EUR', 'GBP', 'JPY', 'AUD', 'NZD', 'CAD', 'CHF', 'USD', 'XAU', 'XAG']
        if any(pair in symbol_upper for pair in forex_base) and len(symbol_upper) >= 6:
            return 'forex'
        return 'stocks'
    def _get_current_session(self, symbol: str = "") -> str:
        try:
            import pytz
            from datetime import datetime
            et_tz = pytz.timezone('America/New_York')
            now_et = datetime.now(et_tz)
        except Exception as e:
            from datetime import datetime, timezone, timedelta
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc - timedelta(hours=4) 
            logger.warning(f"Usando fallback manual para ET: {now_et}")
        current_time = now_et.strftime("%H:%M")
        current_hour = now_et.hour
        day_of_week = now_et.weekday()  
        market_type = self._get_market_type(symbol) if symbol else 'stocks'
        if market_type == 'crypto':
            return "CRYPTO"
        if market_type == 'futures':
            if (day_of_week == 4 and current_hour >= 17) or day_of_week == 5 or (day_of_week == 6 and current_hour < 18):
                return "CLOSED"
            if current_hour == 17:
                return "CLOSED"
            if "09:30" <= current_time < "16:00":
                return "REGULAR"  
            elif "08:00" <= current_time < "09:30":
                return "PRE_MARKET"
            elif "03:00" <= current_time < "08:00":
                return "LONDON"
            elif current_hour >= 18 or current_hour < 3:
                return "ASIAN"
            else:
                return "REGULAR"
        elif market_type == 'forex':
            if (day_of_week == 4 and current_hour >= 17) or day_of_week == 5 or (day_of_week == 6 and current_hour < 17):
                return "CLOSED"
            if "08:00" <= current_time < "17:00":
                return "NEW_YORK"
            elif "03:00" <= current_time < "12:00":
                return "LONDON"
            elif current_hour >= 19 or current_hour < 4:
                return "ASIAN"
            else:
                return "LONDON"
        else:
            if day_of_week >= 5:
                return "CLOSED"
            if "04:00" <= current_time < "09:30":
                return "PRE_MARKET"
            elif "09:30" <= current_time < "16:00":
                return "REGULAR"
            elif "16:00" <= current_time < "20:00":
                return "AFTER_HOURS"
            else:
                return "CLOSED"
    def _validate_trading_hours(self, symbol: str = "") -> ValidationResult:
        session = self._get_current_session(symbol)
        if session == "CLOSED":
            return ValidationResult(
                is_valid=False,
                rejection_reason=RejectionReason.RISK_OUTSIDE_TRADING_HOURS,
                message="Mercado cerrado",
                current_session=session
            )
        if session in ["PRE_MARKET", "AFTER_HOURS"] and not self._limits.allow_extended_hours:
            return ValidationResult(
                is_valid=False,
                rejection_reason=RejectionReason.RISK_OUTSIDE_TRADING_HOURS,
                message=f"Trading en {session} no permitido (habilitar allow_extended_hours)",
                current_session=session
            )
        return ValidationResult(
            is_valid=True,
            current_session=session
        )
    def _validate_position_size(self, order: OrderRequest) -> ValidationResult:
        current_pos = self._positions.get(order.symbol, 0.0)
        if order.side == OrderSide.BUY:
            new_pos = current_pos + order.quantity
        else:
            new_pos = current_pos - order.quantity
        max_size = self._limits.max_position_size
        if order.source == OrderSource.ALGO:
            max_size = self._limits.algo_max_position_size
        if abs(new_pos) > max_size:
            return ValidationResult(
                is_valid=False,
                rejection_reason=RejectionReason.RISK_MAX_POSITION_SIZE,
                message=f"Posición resultante excede límite ({abs(new_pos):.2f} > {max_size})"
            )
        return ValidationResult(is_valid=True)
    def record_order(self, order: OrderRequest) -> None:
        with self._lock:
            self._daily_orders += 1
            self._recent_orders.append(time.time())
            if order.source == OrderSource.ALGO:
                self._daily_algo_orders += 1
            else:
                self._daily_manual_orders += 1
    def update_pnl(self, pnl_change: float) -> None:
        with self._lock:
            self._daily_pnl += pnl_change
    def update_position(self, symbol: str, quantity: float) -> None:
        with self._lock:
            self._positions[symbol] = quantity
    def set_limits(self, limits: RiskLimits) -> None:
        with self._lock:
            self._limits = limits
            logger.info("Límites de riesgo actualizados")
    def get_limits(self) -> RiskLimits:
        return self._limits
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "current_date": self._current_date,
                "daily_orders": self._daily_orders,
                "daily_algo_orders": self._daily_algo_orders,
                "daily_manual_orders": self._daily_manual_orders,
                "daily_pnl": round(self._daily_pnl, 2),
                "positions": self._positions.copy(),
                "limits": self._limits.to_dict()
            }