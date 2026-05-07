import os
import importlib.util

# ==========================================
# LAZY LOADING DE ESTRATEGIAS
# Se evita importar las clases directamente aquí 
# para que Wine/Linux no se cuelguen si las 
# librerías subyacentes (torch, CUDA) escanean la GPU.
# Se instancian dinámicamente en `get_algorithm()`.
# ==========================================

# Registry of available algorithms
CORE_ALGORITHMS = {
    'EvolutionaryGAN': {
        'name': 'Evolutionary GAN',
        'description': 'Neural network (LSTM) trained on historical returns with early stopping. Uses RandomForest for feature selection and Autoencoder for latent features.',
        'class': None, # Managed by existing logic in live_trade.py for now
        'requires_training': True,
        'config_schema': {
            'seq_length': {'type': 'int', 'default': 60},
            'hidden_dim': {'type': 'int', 'default': 128}
        }
    },
    'FourierCycle': {
        'name': 'Fourier Cycle Detection',
        'description': 'Advanced FFT-based harmonic analysis. Detects dominant market cycles and projects future price movement.',
        'class': 'FourierCycleStrategy',
        'requires_training': False,
        'config_schema': {
            'fourier_period': {'type': 'int', 'default': 120, 'min': 60, 'max': 300},
            'harmonics_count': {'type': 'int', 'default': 8, 'min': 3, 'max': 15},
            'projection_bars': {'type': 'int', 'default': 20, 'min': 10, 'max': 50},
            'signal_threshold': {'type': 'float', 'default': 0.5, 'min': 0.1, 'max': 2.0},
            'cooldown_bars': {'type': 'int', 'default': 5, 'min': 1, 'max': 20}
        }
    },
    'StrategyETF_Individual': {
        'name': 'ETF Pro: Individual',
        'description': 'Estrategia de Random Forest optimizada para un solo ETF con gestión de riesgo avanzada.',
        'class': 'StrategyETF_Individual',
        'requires_training': False,
        'config_schema': {
            'stop_loss': {'type': 'float', 'default': 2.0, 'min': 0.5, 'max': 5.0},
            'take_profit': {'type': 'float', 'default': 4.0, 'min': 1.0, 'max': 10.0},
            'retrain_interval': {'type': 'int', 'default': 63, 'min': 20, 'max': 252},
            'n_arboles': {'type': 'int', 'default': 100, 'min': 50, 'max': 500}
        }
    },
    'StrategyETF_Portfolio': {
        'name': 'ETF Pro: Portfolio Multi-ETF',
        'description': 'Analiza y opera simultáneamente 10 ETFs. Usa el ticker "ALL_ETF" para iniciar.',
        'class': 'StrategyETF_Portfolio',
        'requires_training': False,
        'config_schema': {
            'stop_loss': {'type': 'float', 'default': 2.0},
            'take_profit': {'type': 'float', 'default': 4.0},
            'max_position_pct': {'type': 'float', 'default': 0.25, 'min': 0.05, 'max': 1.0},
            'capital_inicial': {'type': 'float', 'default': 100000}
        }
    },
    'StrategyOrderFlow': {
        'name': 'Order Flow (Delta + VWAP)',
        'description': 'Evalúa Delta Divergencia, Delta Acumulado y VWAP para detectar desequilibrios de flujo de órdenes.',
        'class': '_StrategyOrderFlow',
        'requires_training': False,
        'config_schema': {
            'delta_threshold':     {'type': 'int',   'default': 100,  'min': 10,  'max': 1000},
            'lookback_period':     {'type': 'int',   'default': 10,   'min': 3,   'max': 50},
            'imbalance_threshold': {'type': 'float', 'default': 0.7,  'min': 0.1, 'max': 1.0},
            'stop_loss_ticks':     {'type': 'int',   'default': 8,    'min': 2,   'max': 50},
            'take_profit_ticks':   {'type': 'int',   'default': 12,   'min': 2,   'max': 100},
            'rr_ratio':            {'type': 'float', 'default': 1.5,  'min': 0.5, 'max': 5.0},
            'min_volume':          {'type': 'int',   'default': 1000, 'min': 0,   'max': 100000},
            'atr_multiplier':      {'type': 'float', 'default': 1.5,  'min': 0.5, 'max': 5.0}
        }
    },
    'LlamaSMC': {
        'name': 'Llama SMC (Smart Money)',
        'description': 'Estrategia institucional SMC: BOS/CHoCH, zonas SnD, Fibonacci, FVGs, trailing EMA21. Diseñada para MNQ/NQ con $1K-$2K.',
        'class': '_LlamaSMC',
        'requires_training': False,
        'config_schema': {
            'swing_lookback':        {'type': 'int',   'default': 5,     'min': 3,   'max': 15},
            'min_swing_size':        {'type': 'float', 'default': 3.0,   'min': 0.5, 'max': 10.0},
            'fib_entry_level':       {'type': 'float', 'default': 0.5,   'min': 0.3, 'max': 0.7},
            'fib_tp_extension':      {'type': 'float', 'default': 1.618, 'min': 1.0, 'max': 3.0},
            'body_ratio_min':        {'type': 'float', 'default': 0.52,  'min': 0.3, 'max': 0.8},
            'ema_trail_period':      {'type': 'int',   'default': 21,    'min': 10,  'max': 50},
            'atr_period':            {'type': 'int',   'default': 14,    'min': 5,   'max': 30},
            'atr_sl_multiplier':     {'type': 'float', 'default': 1.0,   'min': 0.5, 'max': 4.0},
            'max_consecutive_losses':{'type': 'int',   'default': 2,     'min': 1,   'max': 10},
            'volume_confirmation':   {'type': 'bool',  'default': True},
            'volume_multiplier':     {'type': 'float', 'default': 1.05,  'min': 0.5, 'max': 3.0},
        }
    },
    'StrategyLive': {
        'name': 'VectorBT: Live Absorption',
        'description': 'Estrategia de absorción de volumen y cruces de EMA usando lógica VectorBT para señales en tiempo real.',
        'class': None, # Loaded dynamically via get_algorithm
        'requires_training': False,
        'config_schema': {
            'window_long': {'type': 'int', 'default': 20},
            'window_short': {'type': 'int', 'default': 5},
            'stop_loss': {'type': 'float', 'default': 0.02},
            'take_profit': {'type': 'float', 'default': 0.04}
        }
    }
}

def list_algorithms():
    """Returns a merged registry of core and custom algorithms discovered on disk."""
    algorithms = CORE_ALGORITHMS.copy()
    
    # Discover custom algorithms in the current directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for file in os.listdir(base_dir):
        # Exclude core files, base classes, and internal utilities
        EXCLUDED = {
            '__init__.py', 'StrategyETF.py', 'strategy_base.py', 
            'StrategyLive.py', # StrategyLive is handled via CORE if added there, or manual. Let's see.
            'fourier_cycle.py', 'LlamaSMC.py', 'StrategyOrderFlow.py'
        }
        
        # Add core class names to exclusion if they match file names
        for core_key in CORE_ALGORITHMS.keys():
            EXCLUDED.add(f"{core_key}.py")

        if file.endswith(".py") and file not in EXCLUDED:
            name = file[:-3]
            if name not in algorithms:
                algorithms[name] = {
                    'name': f'Custom: {name}',
                    'description': f'User-created algorithm: {file}',
                    'class': None, # Will be loaded dynamically if needed
                    'requires_training': False,
                    'config_schema': {} 
                }
    return algorithms

# For backward compatibility
ALGORITHMS = list_algorithms()

def get_algorithm(name, config=None):
    algos = list_algorithms()
    if name not in algos:
        return None
    
    algo_info = algos[name]
    cls_ref = algo_info['class']
    
    # LAZY RESOLUTION: Resolvemos las clases dinámicamente
    if isinstance(cls_ref, str):
        if cls_ref == 'FourierCycleStrategy':
            from .fourier_cycle import FourierCycleStrategy
            cls_ref = FourierCycleStrategy
        elif cls_ref == 'StrategyETF_Individual':
            from .StrategyETF import StrategyETF_Individual
            cls_ref = StrategyETF_Individual
        elif cls_ref == 'StrategyETF_Portfolio':
            from .StrategyETF import StrategyETF_Portfolio
            cls_ref = StrategyETF_Portfolio
        elif cls_ref == '_StrategyOrderFlow':
            try:
                from .StrategyOrderFlow import StrategyOrderFlow as _StrategyOrderFlow
                cls_ref = _StrategyOrderFlow
            except Exception:
                cls_ref = None
        elif cls_ref == '_LlamaSMC':
            try:
                from .LlamaSMC import LlamaSMC as _LlamaSMC
                cls_ref = _LlamaSMC
            except Exception:
                cls_ref = None
                
    if cls_ref:
        return cls_ref(config)
    
    # Try to load custom class dynamically
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, f"{name}.py")
        if os.path.exists(file_path):
            spec = importlib.util.spec_from_file_location(name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Look for a class that has an 'update' method (standard for our strategies)
            import inspect
            for class_name, cls in inspect.getmembers(module, inspect.isclass):
                # Avoid importing classes from other modules
                if cls.__module__ == module.__name__:
                    # If it has an 'update' method, it's our target
                    if hasattr(cls, 'update') and callable(getattr(cls, 'update')):
                        sig = inspect.signature(cls.__init__)
                        # Case 1: Class takes a single 'config' parameter
                        if 'config' in sig.parameters and len([p for p in sig.parameters.values() if p.name != 'self']) == 1:
                            return cls(config)
                        
                        # Case 2: Class takes multiple parameters (e.g., custom strategies)
                        if isinstance(config, dict):
                            # Filter config to only include parameters the class accepts
                            valid_args = {k: v for k, v in config.items() if k in sig.parameters}
                            return cls(**valid_args)
                        
                        return cls(config)
            
            # Fallback: if no class with 'update', but the module itself has one (functional style)
            if hasattr(module, 'update') and callable(getattr(module, 'update')):
                return module
    except Exception as e:
        print(f"Error loading custom algorithm {name}: {e}")
        
    return None
