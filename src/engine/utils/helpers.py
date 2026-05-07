import pandas as pd
import numpy as np
from typing import Union, List, Optional


def calculate_tick_value(price: float, tick_size: float = 0.25) -> float:
    """Calcula valor del tick de MNQ."""
    return tick_size * 2.0


def calculate_position_risk(
    entry: float,
    stop_loss: float,
    contracts: int,
    tick_value: float = 0.5,
    tick_size: float = 0.25
) -> float:
    """Calcula riesgo monetario de la posición."""
    ticks = abs(entry - stop_loss) / tick_size
    return ticks * contracts * tick_value


def calculate_contracts(
    account_balance: float,
    risk_pct: float,
    entry: float,
    stop_loss: float,
    tick_value: float = 0.5,
    tick_size: float = 0.25
) -> int:
    """Calcula número de contratos basado en riesgo porcentual."""
    risk_per_trade = account_balance * risk_pct
    risk_per_contract = calculate_position_risk(entry, stop_loss, 1, tick_value, tick_size)
    return max(1, int(risk_per_trade / risk_per_contract))


def is_trading_session(session: str) -> bool:
    """Verifica si estamos en la sesión de trading."""
    from datetime import datetime
    import pytz
    
    tz = pytz.timezone('US/Central')
    now = datetime.now(tz)
    hour = now.hour
    
    if session == 'US_RTH':
        return True  # Permitido 24/7 para demo/testing
    elif session == 'OVERNIGHT':
        return 16 <= hour or hour < 9
    return True


def format_price(price: float) -> str:
    """Formatea precio a 2 decimales."""
    return f"{price:.2f}"
