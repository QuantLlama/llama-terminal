"""
Build the Python backend into multiple executables using PyInstaller.
Targets: backend.exe (Server), Trainer.exe (CLI), BrowserMode.exe (GUI)
"""
import subprocess
import sys
import os
from pathlib import Path
from check_build_inputs import check, new_output, parser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBF_DIR = os.path.join(ROOT, 'build', 'obf_src')

# ── Full hidden imports for backend.exe and Trainer.exe ──
FULL_HIDDEN_IMPORTS = [
    'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
    'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off',
    'fastapi', 'fastapi.middleware', 'fastapi.middleware.cors',
    'fastapi.responses', 'fastapi.staticfiles', 'fastapi.security',
    'pydantic', 'starlette', 'starlette.routing', 'starlette.middleware',
    'starlette.responses', 'starlette.websockets', 'anyio',
    'anyio._backends', 'anyio._backends._asyncio', 'httptools',
    'dotenv', 'supabase', 'gotrue', 'postgrest', 'httpx',
    'aiohttp', 'certifi', 'psutil', 'GPUtil', 'pandas', 'numpy',
    'MetaTrader5', 'pytz', 'dateutil', 'requests', 'websockets',
    'sqlite3', 'talib', 'talib.stream', 'ccxt', 'torch', 'vectorbt', 'numba',
    'statsmodels', 'statsmodels.tsa.arima.model', 'yfinance',
    'sklearn', 'sklearn.utils._cython_blas', 'sklearn.utils._typedefs',
    'sklearn.neighbors._partition_nodes', 'sklearn.neighbors._quad_tree',
    'sklearn.tree._utils', 'joblib', 'matplotlib', 'matplotlib.pyplot',
    'pynvml',
    'src', 'src.platform', 'src.platform.api',
    'src.platform.api.main', 'src.platform.api.accounts_api',
    'src.platform.api.services_api', 'src.platform.api.footprint_api',
    'src.platform.api.utils', 'src.services', 'src.services.auth',
    'src.services.database', 'src.services.license_service',
    'src.services.crypto_manager', 'src.services.mt5_launcher',
    'src.services.mt5_manager', 'src.services.ninjatrader_manager',
    'src.services.tradovate_manager', 'src.services.security',
    'src.services.replication_service', 'src.services.big_llama',
    'src.services.big_llama.engine', 'src.services.algo_engine',
    'src.services.algo_engine.engine', 'src.services.market_data_engine',
    'src.services.market_data_engine.engine', 'src.services.market_data_engine.buffer',
    'src.services.market_data_engine.models', 'src.services.order_gateway',
    'src.services.order_gateway.gateway', 'src.services.order_gateway.models',
    'src.services.order_gateway.risk_validator', 'src.utils',
    'src.utils.cleaner', 'src.utils.config_manager', 'src.utils.dashboard_gen',
    'src.utils.mt5_global_lock', 'src.utils.mt5_master_controller',
    'src.utils.visualizer', 'src.live', 'src.live.connector',
    'src.live.crypto_connector', 'src.features', 'src.features.indicators',
]

# ── Minimal imports for BrowserMode.exe (just a launcher) ──
BROWSER_HIDDEN_IMPORTS = ['requests']

FULL_DATA_ITEMS = []
FULL_BINARY_ITEMS = []
PATHS = [OBF_DIR]

def build_target(script_name, exe_name, hide_console=False,
                 hidden_imports=None, data_items=None, binary_items=None, icon_path=None):
    print(f"\n--- Building {exe_name} from {script_name} ---")

    hi_list = hidden_imports if hidden_imports is not None else FULL_HIDDEN_IMPORTS
    data_list = data_items if data_items is not None else FULL_DATA_ITEMS
    bin_list = binary_items if binary_items is not None else FULL_BINARY_ITEMS
    
    # Default icon if none provided
    if not icon_path:
        icon_path = os.path.join(ROOT, 'images', 'QuantumLLama.ico')

    args_lines = [
        '--onefile',
        '--name', exe_name,
        '--icon', icon_path,
        '--distpath', os.path.join(ROOT, 'build', 'pyinstaller_dist'),
        '--workpath', os.path.join(ROOT, 'build', 'pyinstaller_work'),
        '--specpath', os.path.join(ROOT, 'build', 'specs'),
        '--noconfirm',
        '--clean',
    ]

    if hide_console:
        args_lines.append('--noconsole')
    else:
        args_lines.append('--console')

    for hi in hi_list:
        args_lines.extend(['--hidden-import', hi])

    sep = ';' if sys.platform == 'win32' else ':'
    for src, dest in data_list:
        if os.path.exists(src):
            args_lines.extend(['--add-data', f'{src}{sep}{dest}'])

    for src, dest in bin_list:
        if os.path.exists(src):
            args_lines.extend(['--add-binary', f'{src}{sep}{dest}'])

    for p in PATHS:
        args_lines.extend(['--paths', p])

    args_lines.append(os.path.join(OBF_DIR, script_name))

    print(f"Running PyInstaller for {exe_name}...")

    import PyInstaller.__main__
    old_argv = sys.argv
    sys.argv = ['pyinstaller'] + args_lines
    try:
        PyInstaller.__main__.run(args_lines)
    finally:
        sys.argv = old_argv

    ext = '.exe' if sys.platform == 'win32' else ''
    exe_path = os.path.join(ROOT, 'build', 'pyinstaller_dist', f'{exe_name}{ext}')
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"[OK] {exe_name}{ext} created - Size: {size_mb:.1f} MB")
    else:
        print(f"\nERROR: PyInstaller failed for {exe_name}{ext}")
        sys.exit(1)

def build():
    global FULL_DATA_ITEMS, FULL_BINARY_ITEMS
    root = Path(ROOT)
    check(root)
    for directory in ('build/obf_src', 'build/pyinstaller_dist',
                      'build/pyinstaller_work', 'build/specs'):
        new_output(root, directory)
    subprocess.run([sys.executable, str(root / 'scripts/obfuscate.py')], check=True)
    FULL_DATA_ITEMS = [(str(root / 'build/obf_src' / name), dest) for name, dest in
                       [('src', 'src'), ('images', 'images'), ('train.py', '.'),
                        ('run.py', '.'), ('package.json', '.')]]
    FULL_BINARY_ITEMS = []

    # Build Target 1: backend.exe (full stack) - Uses main icon
    build_target('start_api.py', 'backend', hide_console=True, 
                 icon_path=os.path.join(ROOT, 'images', 'QuantumLLama.ico'))

    # Build Target 2: Trainer.exe (full stack) - Uses Trainer icon
    build_target('run.py', 'Trainer', hide_console=False,
                 icon_path=os.path.join(ROOT, 'images', 'QuantumLLama_Trainer.ico'))

    # Build Target 3: BrowserMode.exe (minimal launcher) - Uses Browser icon
    build_target('browser_launcher.py', 'BrowserMode', hide_console=True,
                 hidden_imports=BROWSER_HIDDEN_IMPORTS,
                 data_items=[], binary_items=[],
                 icon_path=os.path.join(ROOT, 'images', 'QuantumLLama_Browser.ico'))

    print("\n[SUCCESS] All production targets built.")

if __name__ == '__main__':
    args = parser(__doc__).parse_args()
    ROOT = str(args.project_root.resolve())
    OBF_DIR = os.path.join(ROOT, 'build', 'obf_src')
    PATHS = [OBF_DIR]
    try:
        build()
    except (ValueError, KeyError, OSError) as exc:
        print(f'Packaging error: {exc}', file=sys.stderr)
        sys.exit(1)
