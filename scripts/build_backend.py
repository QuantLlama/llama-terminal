"""
Build the Python backend into multiple executables using PyInstaller.
Targets: backend.exe (Server), Trainer.exe (CLI), BrowserMode.exe (GUI)
"""
import subprocess
import sys
import os
import shutil
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def get_venv_python():
    is_win = sys.platform == "win32"
    executable = "python.exe" if is_win else "python"
    subfolder = "Scripts" if is_win else "bin"
    return os.path.join(ROOT, 'venv', subfolder, executable)

VENV_PYTHON = get_venv_python()
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
    'sqlite3', 'talib', 'talib.stream', 'ccxt', 'torch', 'vectorbt', 'numba', 'xgboost',
    'xgboost.training', 'xgboost.core', 'xgboost.libpath', 'xgboost.callback',
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

# Collect everything for xgboost
xg_datas, xg_binaries, xg_hidden = collect_all('xgboost')
FULL_HIDDEN_IMPORTS.extend(xg_hidden)
FULL_DATA_ITEMS = [
    (os.path.join(OBF_DIR, '.env'), '.'),
    (os.path.join(OBF_DIR, 'src'), 'src'),
    (os.path.join(OBF_DIR, 'train.py'), '.'),
    (os.path.join(OBF_DIR, 'run.py'), '.'),
    (os.path.join(ROOT, 'images'), 'images'),
]

FULL_DATA_ITEMS.extend(xg_datas)

FULL_BINARY_ITEMS = list(xg_binaries)

PATHS = [OBF_DIR, ROOT]

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
        '--specpath', os.path.join(ROOT, 'build'),
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

    exe_path = os.path.join(ROOT, 'build', 'pyinstaller_dist', f'{exe_name}.exe')
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"[OK] {exe_name}.exe created - Size: {size_mb:.1f} MB")
    else:
        print(f"\nERROR: PyInstaller failed for {exe_name}")
        sys.exit(1)

def generate_all_icons():
    print("Generating high-quality ICO files...")
    try:
        from PIL import Image, ImageDraw
        base_img_path = os.path.join(ROOT, 'images', 'QuantumLLama.png')
        if not os.path.exists(base_img_path):
            print(f"Warning: {base_img_path} not found. Skipping icon generation.")
            return

        base = Image.open(base_img_path).convert("RGBA")
        size = base.size
        icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

        # 1. Main Icon
        base.save(os.path.join(ROOT, 'images', 'QuantumLLama.ico'), format='ICO', sizes=icon_sizes)
        
        # 2. Browser Icon
        browser_img = base.copy()
        draw = ImageDraw.Draw(browser_img)
        r = size[0] // 4
        center = (size[0] - r - 10, size[1] - r - 10)
        draw.ellipse([center[0]-r, center[1]-r, center[0]+r, center[1]+r], fill=(0, 122, 255, 255), outline=(255, 255, 255, 255), width=5)
        draw.line([center[0]-r+10, center[1], center[0]+r-10, center[1]], fill=(255, 255, 255, 255), width=3)
        draw.line([center[0], center[1]-r+10, center[0], center[1]+r-10], fill=(255, 255, 255, 255), width=3)
        browser_img.save(os.path.join(ROOT, 'images', 'QuantumLLama_Browser.ico'), format='ICO', sizes=icon_sizes)

        # 3. Trainer Icon
        trainer_img = base.copy()
        draw = ImageDraw.Draw(trainer_img)
        r = size[0] // 4
        center = (size[0] - r - 10, size[1] - r - 10)
        draw.ellipse([center[0]-r, center[1]-r, center[0]+r, center[1]+r], fill=(255, 170, 0, 255), outline=(255, 255, 255, 255), width=5)
        draw.line([center[0]-r+15, center[1]+r-15, center[0]-5, center[1], center[0]+r-15, center[1]-r+15], fill=(255, 255, 255, 255), width=5)
        trainer_img.save(os.path.join(ROOT, 'images', 'QuantumLLama_Trainer.ico'), format='ICO', sizes=icon_sizes)
        
        print("[OK] Icons generated successfully.")
    except Exception as e:
        print(f"Warning: Could not generate icons automatically: {e}")

def build():
    generate_all_icons()
    subprocess.run([VENV_PYTHON, os.path.join(ROOT, 'scripts', 'obfuscate.py')], check=True)

    FULL_DATA_ITEMS = [
        (os.path.join(OBF_DIR, '.env'), '.'),
        (os.path.join(OBF_DIR, 'src'), 'src'),
        (os.path.join(OBF_DIR, 'train.py'), '.'),
        (os.path.join(OBF_DIR, 'run.py'), '.'),
        (os.path.join(ROOT, 'images'), 'images'),
    ]
    FULL_DATA_ITEMS.extend(xg_datas)

    # Add PyArmor Runtime folders after they are generated by obfuscate.py
    if os.path.exists(OBF_DIR):
        for item in os.listdir(OBF_DIR):
            if item.startswith('pyarmor_runtime'):
                rt_path = os.path.join(OBF_DIR, item)
                if os.path.isdir(rt_path):
                    FULL_DATA_ITEMS.append((rt_path, item))
                    print(f"Adding PyArmor runtime: {item}")

    shutil.copy2(os.path.join(ROOT, 'browser_launcher.py'), os.path.join(OBF_DIR, 'browser_launcher.py'))

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
    build()
