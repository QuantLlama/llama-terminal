import os
import importlib.util

# Indicators Registry
# This module provides a registry for quantitative indicators

from .imbalance_impulse import ImbalanceImpulseIndicator
from .caza_stop import CazaStopIndicator
from .order_flow import OrderFlowIndicator
from .liquidity_heatmap import LiquidityHeatmapIndicator

# Registry of available indicators
CORE_INDICATORS = {
    'imbalance_impulse': {
        'class': ImbalanceImpulseIndicator,
        'name': 'Imbalance Impulse',
        'description': 'Detecta impulsos de mercado basados en imbalance de order flow',
        'category': 'Order Flow'
    },
    'caza_stop': {
        'class': CazaStopIndicator,
        'name': 'CazaStop PRO',
        'description': 'Identifica zonas de stop-hunting y puntos de entrada seguros',
        'category': 'Smart Money'
    },
    'order_flow': {
        'class': OrderFlowIndicator,
        'name': 'Order Flow Suite',
        'description': 'Advanced Volume Analysis (Delta, VWAP, Imbalances)',
        'category': 'Order Flow'
    },
    'liquidity_heatmap': {
        'class': LiquidityHeatmapIndicator,
        'name': 'Liquidity Heatmap',
        'description': 'Order Book & Market Depth visualization',
        'category': 'Order Flow'
    }
}

def list_indicators():
    """List all available indicators, merging core and custom ones discovered on disk."""
    indicators = CORE_INDICATORS.copy()
    
    # Discover custom indicators in the current directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for file in os.listdir(base_dir):
        if file.endswith(".py") and file != "__init__.py" and file[:-3] not in indicators:
            name = file[:-3]
            indicators[name] = {
                'class': None, # Will be loaded dynamically if needed
                'name': f'Custom: {name.replace("_", " ").title()}',
                'description': f'User-created indicator: {file}',
                'category': 'Custom'
            }

    return {k: {key: v for key, v in info.items() if key != 'class'} 
            for k, info in indicators.items()}

def get_indicator(name: str, config: dict = None):
    """Get an indicator instance by name, with support for dynamic loading."""
    # Check core indicators first
    if name in CORE_INDICATORS:
        return CORE_INDICATORS[name]['class'](config or {})
    
    # Try to load custom indicator dynamically
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, f"{name}.py")
        if os.path.exists(file_path):
            spec = importlib.util.spec_from_file_location(name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Look for a class that might be the indicator (e.g. name + "Indicator")
            # This follows the naming convention used in core indicators
            class_name = "".join(x.title() for x in name.split("_")) + "Indicator"
            indicator_class = getattr(module, class_name, None)
            
            if indicator_class:
                return indicator_class(config or {})
            else:
                # Fallback to the first class found if naming convention fails
                import inspect
                for _, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and obj.__module__ == name:
                        return obj(config or {})
                        
    except Exception as e:
        print(f"Error loading custom indicator {name}: {e}")
        
    raise ValueError(f"Unknown indicator: {name}")

# For backward compatibility
INDICATORS = list_indicators()
