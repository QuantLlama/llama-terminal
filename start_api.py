"""
Startup script for the Quantum Llama Platform API
This script ensures the correct Python path is set before starting the server
"""
import sys
import os
import subprocess

def get_venv_python():
    """Detecta la ruta al ejecutable de python en el venv."""
    root = os.path.dirname(os.path.abspath(__file__))
    if sys.platform == "win32":
        return os.path.join(root, "venv", "Scripts", "python.exe")
    return os.path.join(root, "venv", "bin", "python")

def check_venv():
    """Asegura que el script corra en el venv y repara pyvenv.cfg si es necesario."""
    root = os.path.dirname(os.path.abspath(__file__))
    venv_path = os.path.join(root, 'venv')
    venv_python = get_venv_python()
    
    # En producción (con PyInstaller), no hay venv
    if getattr(sys, 'frozen', False):
        return

    # Check if we are in a virtual env
    is_venv = sys.prefix != sys.base_prefix
    
    if not is_venv:
        if os.path.exists(venv_python):
            # Reparar pyvenv.cfg si el path 'home' es invalido (viniendo de otra PC)
            cfg_path = os.path.join(venv_path, "pyvenv.cfg")
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    system_py_dir = os.path.dirname(sys.executable)
                    changed = False
                    for i, line in enumerate(lines):
                        if line.startswith('home ='):
                            old_path = line.split('=')[1].strip()
                            if old_path.lower() != system_py_dir.lower():
                                lines[i] = f'home = {system_py_dir}\n'
                                changed = True
                    if changed:
                        with open(cfg_path, 'w', encoding='utf-8') as f:
                            f.writelines(lines)
                except:
                    pass

            try:
                # Re-ejecutar usando el python del venv
                subprocess.call([venv_python, sys.argv[0]] + sys.argv[1:])
                sys.exit(0)
            except:
                sys.exit(1)
        else:
            print(f"ERROR: No se encontro el venv en {venv_path}")
            sys.exit(1)

# Ejecutar proteccion de entorno antes de cualquier otra cosa (SOLO en desarrollo)
if not getattr(sys, 'frozen', False):
    check_venv()

# ── Fix for --noconsole mode (sys.stdout/stderr are None) ──
# Uvicorn's formatter calls stream.isatty() which crashes on None
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

# Add the project root to Python path
if getattr(sys, 'frozen', False):
    # If running as an executable bundle
    ROOT_DIR = os.path.dirname(sys.executable)
    # Also add the internal extraction directory to path (for bundled modules)
    BUNDLED_DIR = getattr(sys, '_MEIPASS', ROOT_DIR)
    if BUNDLED_DIR not in sys.path:
        sys.path.insert(0, BUNDLED_DIR)
    
    # ── Add _MEIPASS to DLL search path (for CUDA DLLs) ──
    if hasattr(os, 'add_dll_directory'):
        try:
            os.add_dll_directory(BUNDLED_DIR)
        except OSError:
            pass
    os.environ['PATH'] = BUNDLED_DIR + os.pathsep + os.environ.get('PATH', '')
else:
    # If running in development (via python.exe)
    ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Now import and run the API
if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description='Quantum Llama Platform Backend')
    parser.add_argument('--train', action='store_true', help='Run training mode')
    parser.add_argument('--live', action='store_true', help='Run live trading mode')
    
    # Training arguments
    parser.add_argument('--ticker', type=str)
    parser.add_argument('--period', type=str)
    parser.add_argument('--epochs', type=int)
    parser.add_argument('--asset_type', type=str)
    parser.add_argument('--train_timeframe', type=str)
    parser.add_argument('--trade_timeframe', type=str)
    parser.add_argument('--seq_length', type=int)
    parser.add_argument('--hidden_dim', type=int)
    parser.add_argument('--num_layers', type=int)
    
    # Live arguments
    parser.add_argument('--platform', type=str)
    parser.add_argument('--algorithm', type=str)
    parser.add_argument('--account_id', type=str)
    parser.add_argument('--timeframe', type=str)
    parser.add_argument('--config', type=str)
    
    args, unknown = parser.parse_known_args()
    
    if args.train:
        from train import train_model
        train_model(
            args.ticker, args.period, args.epochs, args.asset_type,
            args.train_timeframe, args.trade_timeframe, 
            args.seq_length, args.hidden_dim, args.num_layers
        )
    elif args.live:
        from src.live.live_trade import run_live_trading
        try:
            algo_config = json.loads(args.config) if args.config else {}
        except:
            algo_config = {}
        run_live_trading(
            args.ticker, args.asset_type, args.platform, 
            args.timeframe, args.algorithm, algo_config, args.account_id
        )
    else:
        import uvicorn
        # Run the API server
        uvicorn.run(
            "src.platform.api.main:app",
            host="127.0.0.1",
            port=8050,
            reload=False,
            log_level="info"
        )
