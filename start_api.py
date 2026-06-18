"""
Startup script for the Quantum Llama Platform API
This script ensures the correct Python path is set before starting the server
"""
import sys
import os
import subprocess
import time

def get_venv_python():
    """Detecta la ruta al ejecutable de python en el venv."""
    root = os.path.dirname(os.path.abspath(__file__))
    
    # Lista de nombres de venv a probar
    candidates = []
    if sys.platform == "win32":
        # Local venv
        candidates.append(os.path.join(root, "venv", "Scripts", "python.exe"))
        # User home venv (Wine mapping)
        candidates.append(os.path.expanduser("~/venv_quantllama/Scripts/python.exe"))
    else:
        # Local venv
        candidates.append(os.path.join(root, "venv", "bin", "python"))
        # User home venv
        candidates.append(os.path.expanduser("~/venv_quantllama/bin/python"))
    
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
            
    return None

def check_venv():
    """Asegura que el script corra en el venv y repara pyvenv.cfg si es necesario."""
    if getattr(sys, 'frozen', False):
        return

    # Si ya estamos en un venv, no hacemos nada
    if sys.prefix != sys.base_prefix:
        return

    venv_python = get_venv_python()
    
    if venv_python:
        # Intentar reparar pyvenv.cfg si existe
        venv_path = os.path.dirname(os.path.dirname(venv_python))
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
            print(f"INFO: Reiniciando plataforma usando venv: {venv_python}")
            subprocess.call([venv_python, sys.argv[0]] + sys.argv[1:])
            sys.exit(0)
        except Exception as e:
            print(f"ERROR al reiniciar con venv: {e}")
            sys.exit(1)
    else:
        # No salimos si no hay venv, solo avisamos
        print("WARNING: No se encontro el venv local o en ~/venv_quantllama. Continuando con python actual.")

# Ejecutar proteccion de entorno antes de cualquier otra cosa (SOLO en desarrollo)
if not getattr(sys, 'frozen', False):
    check_venv()

# ── Fix for --noconsole mode (sys.stdout/stderr are None) ──
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

# Add the project root to Python path
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
    
    # Port configuration
    parser.add_argument('--port', type=int, default=8050, help='Port to run the API on')
    
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
        import socket
        
        # Determine port
        port = args.port
        # If default port is selected (8050) but might be in use, we try to bind or find a free one.
        # But since the user specifically requested dynamic port when 8050 is in use,
        # we can ensure we bind to a free port.
        if port == 8050:
            def get_free_port(start_port=8050):
                for p in range(start_port, start_port + 100):
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        if s.connect_ex(('127.0.0.1', p)) != 0:
                            return p
                return start_port
            port = get_free_port(8050)
            
        print(f"Starting API server on port {port}...")
        
        # Run the API server
        uvicorn.run(
            "src.platform.api.main:app",
            host="127.0.0.1",
            port=port,
            reload=False,
            log_level="info"
        )
