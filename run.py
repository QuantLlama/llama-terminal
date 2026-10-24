import sys
import os
import subprocess
import shutil

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import print as rprint
import time
import webbrowser

# Heavy imports moved inside functions for Lazy Loading
# import torch
# from train import train_model
from src.utils.config_manager import configure_symbols
from src.utils.cleaner import clean_system_data

console = Console()

# ── OS-Aware Path Management ──
def get_venv_python(venv_base="venv"):
    """Returns the path to the python executable in the given venv base directory."""
    is_win = sys.platform == "win32"
    # En Linux preferimos venv_linux
    if not is_win and venv_base == "venv":
        venv_base = "venv_linux"
        
    executable = "python.exe" if is_win else "python"
    subfolder = "Scripts" if is_win else "bin"
    
    root_dir = os.path.dirname(os.path.abspath(__file__))
    # Si estamos en producción, el root es donde esté el ejecutable o el _MEIPASS
    if getattr(sys, 'frozen', False):
        root_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        
    return os.path.join(root_dir, venv_base, subfolder, executable)

def get_gpu_env_dir():
    """Returns a cross-platform directory for the GPU environment."""
    if sys.platform == "win32":
        base = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
    else:
        # Use ~/.local/share/QuantumLlama on Linux
        base = os.path.join(os.path.expanduser('~'), '.local', 'share')
    
    return os.path.join(base, 'QuantumLlama', 'gpu_env')

GPU_ENV_DIR = get_gpu_env_dir()
GPU_PYTHON = get_venv_python(GPU_ENV_DIR) # This also works for the GPU env if follows venv structure
GPU_MARKER = os.path.join(GPU_ENV_DIR, '.gpu_ready')

def _has_nvidia_gpu():
    """Check if an NVIDIA GPU is present via nvidia-smi."""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0 and result.stdout.strip() != ''
    except Exception:
        return False

def _gpu_env_exists():
    """Check if the GPU environment is already set up."""
    return os.path.isfile(GPU_MARKER) and os.path.isfile(GPU_PYTHON)

def _sync_sources():
    """Sync latest obfuscated source files and PyArmor runtime to the GPU env."""
    if not getattr(sys, 'frozen', False):
        return
        
    console.print("[cyan]🔄 Sincronizando código ofuscado y runtime...[/cyan]")
    meipass = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    
    items_to_sync = ['train.py', 'run.py', 'src', '.env']
    
    # Find pyarmor runtime folders
    for entry in os.listdir(meipass):
        if entry.startswith('pyarmor_runtime_') and os.path.isdir(os.path.join(meipass, entry)):
            items_to_sync.append(entry)

    for item in items_to_sync:
        src_path = os.path.join(meipass, item)
        dst_path = os.path.join(GPU_ENV_DIR, item)
        if os.path.exists(src_path):
            if os.path.isdir(src_path):
                if os.path.exists(dst_path):
                    shutil.rmtree(dst_path)
                shutil.copytree(src_path, dst_path)
                
                # Fix PyArmor ImportError by reconstructing __init__.py if missing
                if item.startswith('pyarmor_runtime_'):
                    init_file = os.path.join(dst_path, '__init__.py')
                    if not os.path.exists(init_file):
                        with open(init_file, 'w') as f:
                            f.write("from .pyarmor_runtime import __pyarmor__\n")
            else:
                shutil.copy2(src_path, dst_path)

def _install_gpu_env():
    """Create a venv with torch+CUDA and relaunch the trainer."""
    console.print("\n[bold cyan]📥 Configurando entorno GPU...[/bold cyan]")
    console.print(f"   Ubicación: [dim]{GPU_ENV_DIR}[/dim]")
    console.print("   [yellow]Esto puede tardar varios minutos (~2.5 GB descarga).[/yellow]\n")
    
    # Find system Python
    py_cmd = sys.executable if not getattr(sys, 'frozen', False) else shutil.which('python') or shutil.which('python3')
    if not py_cmd:
        console.print("[red]❌ No se encontró Python en el sistema.[/red]")
        console.print("   Instale Python 3.10+ desde https://python.org")
        return False
    
    # Step 1: Create venv
    console.print("[bold]1/3[/bold] Creando entorno virtual...")
    os.makedirs(GPU_ENV_DIR, exist_ok=True)
    result = subprocess.run([py_cmd, '-m', 'venv', GPU_ENV_DIR], capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"[red]❌ Error creando venv: {result.stderr}[/red]")
        return False
    console.print("   ✅ Entorno creado")
    
    # Step 2: Install torch+CUDA
    console.print("[bold]2/3[/bold] Descargando PyTorch con CUDA 12.1...")
    is_win = sys.platform == "win32"
    pip_cmd = os.path.join(GPU_ENV_DIR, 'Scripts' if is_win else 'bin', 'pip.exe' if is_win else 'pip')
    
    # On Linux, we might need different indices or versions depending on hardware
    torch_url = 'https://download.pytorch.org/whl/cu121'
    result = subprocess.run(
        [pip_cmd, 'install', 'torch==2.2.2', '--index-url', torch_url],
        capture_output=False  # Show progress to user
    )
    if result.returncode != 0:
        console.print("[red]❌ Error instalando PyTorch CUDA.[/red]")
        return False
    
    # Step 3: Install other needed packages
    console.print("[bold]3/3[/bold] Instalando dependencias adicionales...")
    deps = [
        'rich', 'pandas', 'numpy<2', 'yfinance', 'matplotlib',
        'scikit-learn', 'statsmodels', 'requests',
        'joblib', 'python-dotenv', 'supabase', 'ccxt', 'MetaTrader5',
        'pytz', 'python-dateutil', 'websockets', 'ta-lib', 'seaborn',
        'mplfinance', 'cryptography'
    ]
    # We use a single call for speed, but split if it fails
    try:
        subprocess.run([pip_cmd, 'install'] + deps, capture_output=True, check=True)
    except subprocess.CalledProcessError:
        # Fallback to individual installs if one fails (like ta-lib)
        for dep in deps:
            subprocess.run([pip_cmd, 'install', dep], capture_output=True)
    
    # Copy source files
    _sync_sources()
    
    # Mark as ready
    with open(GPU_MARKER, 'w') as f:
        f.write('ok')
    
    console.print("\n[bold green]✅ ¡Entorno GPU instalado exitosamente![/bold green]")
    return True

def _relaunch_with_gpu():
    """Relaunch the trainer using the GPU environment's Python."""
    # Ensure sources are updated (critical for app updates!)
    _sync_sources()
    
    console.print("[cyan]🔄 Re-iniciando con GPU...[/cyan]\n")
    time.sleep(1)
    
    # Determine which run.py to execute
    if getattr(sys, 'frozen', False):
        run_py = os.path.join(GPU_ENV_DIR, 'run.py')
        if not os.path.isfile(run_py):
            meipass = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            run_py = os.path.join(meipass, 'run.py')
    else:
        # If running from source, always use the current script
        run_py = os.path.abspath(__file__)

    
    # Use subprocess.call instead of execv to avoid issues on some Windows systems
    # and to ensure the process exits cleanly.
    subprocess.call([GPU_PYTHON, run_py])
    sys.exit(0)

def check_venv():
    """Verifica si el script se esta ejecutando dentro del entorno virtual correcto."""
    # En producción (con PyInstaller), no hay venv y el runtime ya está incluido
    if getattr(sys, 'frozen', False):
        return

    venv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'venv')
    venv_python = get_venv_python()
    
    # Check if we are in a virtual env
    is_venv = sys.prefix != sys.base_prefix
    
    if not is_venv:
        console.print(f"[bold yellow]⚠️ Entorno no activo. Cambiando automáticamente al entorno virtual en {venv_path}...[/bold yellow]")
        if os.path.exists(venv_python):
            # Reparar pyvenv.cfg si viene de otra computadora hardcodeada
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
                        console.print("[dim cyan]🔧 pyvenv.cfg auto-reparado para este sistema.[/dim cyan]")
                except Exception as e:
                    console.print(f"[dim red]No se pudo revisar pyvenv.cfg: {e}[/dim red]")

            try:
                # Reiniciar el script usando el python del venv
                subprocess.call([venv_python, sys.argv[0]] + sys.argv[1:])
                sys.exit(0)
            except Exception as e:
                console.print(f"[bold red]❌ Error al reiniciar con venv: {e}[/bold red]")
                sys.exit(1)
        else:
            console.print("[bold red]❌ ERROR CRITICO: No se encontró el ejecutable del entorno virtual.[/bold red]")
            console.print(f"Instala o verifica el entorno en: [cyan]{venv_path}[/cyan]")
            sys.exit(1)
    else:
        console.print(f"[green]✅ Entorno Virtual detectado:[/green] {sys.prefix}")

def show_header():
    # console.clear() # Eliminado para evitar bloqueos de terminal
    console.print(Panel.fit(
        "[bold cyan]LLAMA QUANTUM GAN V2.0.0 - SISTEMA DE PREDICCIÓN MULTI-MERCADO[/bold cyan]\n"
        "[white]Powered by PyTorch & Deep Learning Ing. Pablo Ez. M[/white]",
        subtitle="v2.0.0",
        border_style="blue"
    ))

def check_hardware():
    import torch
    console.print("\n[bold yellow]Paso 1: Verificación de Hardware[/bold yellow]")
    if torch.cuda.is_available():
        device_name = torch.cuda.get_device_name(0)
        console.print(f"✅ [green]GPU Detectada:[/green] {device_name}")
        return "cuda"
    else:
        console.print("⚠️ [yellow]GPU no detectada. Se utilizará la CPU.[/yellow]")
        console.print("   (El entrenamiento será más lento pero funcional)")
        
        # Check if GPU env already exists → offer to relaunch or reinstall
        if _gpu_env_exists():
            console.print("\n[green]💡 Se encontró un entorno GPU instalado.[/green]")
            choice = Prompt.ask("¿Qué desea hacer?", choices=["Iniciar", "Reinstalar", "Cancelar"], default="Iniciar")
            if choice == "Iniciar":
                _relaunch_with_gpu()
            elif choice == "Reinstalar":
                if Confirm.ask("[red]¿Está seguro? Esto eliminará y volverá a descargar el entorno (~2.5 GB).[/red]"):
                    shutil.rmtree(GPU_ENV_DIR)
                    if _install_gpu_env():
                        _relaunch_with_gpu()
        
        # Check if NVIDIA GPU hardware is present → offer to install
        elif _has_nvidia_gpu():
            console.print("\n[cyan]💡 Se detectó una GPU NVIDIA compatible.[/cyan]")
            console.print("   Se puede instalar soporte CUDA automáticamente (~2.5 GB)")
            if Confirm.ask("¿Desea instalar soporte GPU ahora?", default=True):
                if _install_gpu_env():
                    _relaunch_with_gpu()
        
        return "cpu"

def select_asset_class():
    console.print("\n[bold yellow]Paso 2: Selección de Clase de Activo[/bold yellow]")
    asset_type = Prompt.ask(
        "Seleccione el tipo de mercado", 
        choices=["Futures", "Stocks", "Crypto", "ETF"], 
        default="Futures"
    )
    return asset_type

def select_ticker(asset_type):
    console.print(f"\n[bold yellow]Paso 3: Selección de Ticker ({asset_type})[/bold yellow]")
    
    if asset_type == "Futures":
        default_ticker = "MNQ=F"
        suggestions = "MNQ=F (Micro Nasdaq), MES=F (Micro S&P), NQ=F (Nasdaq), ES=F (S&P), GC=F (Gold), CL=F (Oil)"
    elif asset_type == "Stocks":
        default_ticker = "AAPL"
        suggestions = "AAPL, TSLA, NVDA, MSFT, AMZN, GOOGL"
    elif asset_type == "Crypto":
        default_ticker = "BTC-USD"
        suggestions = "BTC-USD, ETH-USD, SOL-USD, DOGE-USD, BNB-USD"
    elif asset_type == "ETF":
        default_ticker = "QQQ"
        suggestions = "QQQ (Nasdaq), SPY (S&P 500), GLD (Gold), ARKK (Innovation), SOXL (Semis)"
        
    console.print(f"[italic]Sugerencias: {suggestions}[/italic]")
    ticker = Prompt.ask("Ingrese el símbolo del activo", default=default_ticker)
    return ticker

def select_parameters():
    console.print("\n[bold yellow]Paso 4: Configuración de Estrategia y Entrenamiento[/bold yellow]")
    
    console.print("\n[bold cyan]Seleccione el Modo de Estrategia (Timeframe & Arquitectura GAN):[/bold cyan]")
    console.print("1. [green]Scalping (1m)[/green] - GAN Ligera (Win: 60, Hidden: 64)")
    console.print("2. [blue]Intradía (5m)[/blue] - GAN Media (Win: 48, Hidden: 128)")
    console.print("3. [magenta]Intradía (15m)[/magenta] - GAN Estable (Win: 32, Hidden: 128)")
    console.print("4. [red]Swing (1h)[/red] - GAN Profunda (Win: 24, Hidden: 256)")
    console.print("5. [white]Personalizado[/white] - Configuración Manual")
    
    mode_choice = Prompt.ask("Opción", choices=["1", "2", "3", "4", "5"], default="4")
    
    # Defaults
    train_timeframe = "1h"
    trade_timeframe = "1h"
    seq_length = 60
    hidden_dim = 128
    num_layers = 2
    
    if mode_choice == "1": # Scalping 1m
        train_timeframe = "1m"
        trade_timeframe = "1m"
        seq_length = 60
        hidden_dim = 64
        num_layers = 2
    elif mode_choice == "2": # Intraday 5m
        train_timeframe = "5m"
        trade_timeframe = "5m"
        seq_length = 48
        hidden_dim = 128
        num_layers = 2
    elif mode_choice == "3": # Intraday 15m
        train_timeframe = "15m"
        trade_timeframe = "15m"
        seq_length = 32
        hidden_dim = 128
        num_layers = 2
    elif mode_choice == "4": # Swing 1h
        train_timeframe = "1h"
        trade_timeframe = "1h"
        seq_length = 24
        hidden_dim = 256
        num_layers = 3
    elif mode_choice == "5": # Custom
        train_timeframe = Prompt.ask("Timeframe de Entrenamiento", choices=["1m", "5m", "15m", "1h", "1d"], default="1h")
        trade_timeframe = Prompt.ask("Timeframe de Trading en Vivo", choices=["1m", "5m", "15m", "1h", "1d"], default="1m")
        seq_length = IntPrompt.ask("Ventana de Datos (Seq Length)", default=60)
        hidden_dim = IntPrompt.ask("Dimensión Oculta (Hidden Dim)", default=128)
        num_layers = IntPrompt.ask("Número de Capas LSTM", default=2)

    period = Prompt.ask("Periodo de datos históricos", choices=["1y", "2y", "5y", "max"], default="2y")
    epochs = IntPrompt.ask("Número de Épocas (Iteraciones)", default=50)
    
    return period, epochs, train_timeframe, trade_timeframe, seq_length, hidden_dim, num_layers

def get_available_timeframes(ticker):
    """Scans outputs/models for available timeframes for the given ticker"""
    from src.services.database import get_outputs_dir
    safe_ticker = ticker.replace("=", "").replace("-", "")
    models_dir = os.path.join(get_outputs_dir(), "models")
    
    if not os.path.exists(models_dir):
        return []
        
    timeframes = []
    # Look for files like {safe_ticker}_{timeframe}_generator.pth
    for filename in os.listdir(models_dir):
        if filename.startswith(safe_ticker) and filename.endswith("_generator.pth"):
            # Extract timeframe: safe_ticker_TIMEFRAME_generator.pth
            try:
                parts = filename.split("_")
                # parts[0] is safe_ticker
                # parts[-1] is generator.pth (or parts[-2] if split by _)
                # The timeframe is in between. 
                # Example: MNQF_1h_generator.pth -> parts=["MNQF", "1h", "generator.pth"]
                if len(parts) >= 3:
                    tf = parts[1]
                    timeframes.append(tf)
            except:
                continue
                
    return sorted(list(set(timeframes)))

def select_timeframe(ticker):
    """Prompts user to select a timeframe if multiple exist"""
    timeframes = get_available_timeframes(ticker)
    
    if not timeframes:
        console.print(f"[yellow]⚠️ No se encontraron modelos específicos para {ticker}. Se intentará usar el modelo por defecto (1h).[/yellow]")
        return None
        
    if len(timeframes) == 1:
        console.print(f"[green]✅ Modelo encontrado: {timeframes[0]}[/green]")
        return timeframes[0]
        
    console.print(f"\n[bold cyan]Modelos disponibles para {ticker}:[/bold cyan]")
    for i, tf in enumerate(timeframes):
        console.print(f"{i+1}. {tf}")
        
    choice = Prompt.ask("Seleccione el timeframe a operar", choices=[str(i+1) for i in range(len(timeframes))], default="1")
    return timeframes[int(choice)-1]

def select_platform():
    console.print("\n[bold yellow]Selección de Plataforma de Trading[/bold yellow]")
    console.print("1. [blue]MetaTrader 5 (MT5)[/blue]")
    console.print("2. [green]NinjaTrader 8 (NT8)[/green]")
    
    choice = Prompt.ask("Seleccione la plataforma", choices=["1", "2"], default="1")
    
    if choice == "1":
        return "mt5"
    else:
        return "nt8"

def open_last_dashboard():
    from src.services.database import get_outputs_dir
    dashboard_path = os.path.join(get_outputs_dir(), "dashboard.html")
    if os.path.exists(dashboard_path):
        console.print(f"\n[green]Abriendo Dashboard:[/green] {dashboard_path}")
        webbrowser.open(f"file://{dashboard_path}")
    else:
        console.print("\n[red]❌ No se encontró ningún dashboard generado previamente.[/red]")
        console.print("Ejecute un entrenamiento primero para generar el reporte.")

# Import live trading logic
# Import live trading logic
# from src.live.live_trade import run_live_trading
import http.server
import socketserver
import threading
import json
import os

import socket
def find_free_port(start_port=8000):
    port = start_port
    while port < 8100:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
        port += 1
    return 8000

PORT = find_free_port(8000)
from src.utils.paths import get_data_path
CONFIG_PATH = get_data_path("src", "config", "live_config.json")

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        clean_path = path.split('?', 1)[0].split('#', 1)[0]
        if clean_path.startswith('/outputs/'):
            from src.services.database import get_outputs_dir
            return os.path.join(get_outputs_dir(), clean_path[9:])
        if clean_path == '/live_status.json':
            from src.services.database import get_outputs_dir
            return os.path.join(get_outputs_dir(), 'live_status.json')
        if clean_path.startswith('/src/'):
            from src.utils.paths import get_internal_path
            return get_internal_path(clean_path[1:])
        return super().translate_path(path)

    def _send_json(self, data, status=200):
        """Helper to send JSON response with CORS headers."""
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        if isinstance(data, bytes):
            self.wfile.write(data)
        else:
            self.wfile.write(json.dumps(data).encode())

    def _load_config(self):
        """Load live config with default values."""
        defaults = {
            "automation_enabled": False,
            "volume": 1.0,
            "max_daily_loss": 200.0,
            "daily_profit_target": 200.0,
            "max_trades_per_day": 2,
            "start_hour": "09:30",
            "end_hour": "16:00"
        }
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r') as f:
                    saved = json.load(f)
                defaults.update(saved)
            except:
                pass
        return defaults

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        clean_path = self.path.split('?')[0]
        
        # Config endpoint — soporta /config y /api/config
        if clean_path in ('/config', '/api/config'):
            self._send_json(self._load_config())
            return
        
        # Live status endpoint — API directa
        if clean_path in ('/api/status', '/api/live_status'):
            from src.services.database import get_outputs_dir
            status_path = os.path.join(get_outputs_dir(), 'live_status.json')
            if os.path.exists(status_path):
                with open(status_path, 'rb') as f:
                    self._send_json(f.read())
            else:
                self._send_json({"error": "No live data yet"})
            return
        
        super().do_GET()

    def do_POST(self):
        clean_path = self.path.split('?')[0]
        
        # Config save — soporta /update_config y /api/config
        if clean_path in ('/update_config', '/api/config'):
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                config_data = json.loads(post_data)
                os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
                existing_config = self._load_config()
                existing_config.update(config_data)
                with open(CONFIG_PATH, 'w') as f:
                    json.dump(existing_config, f, indent=4)
                self._send_json({"status": "success"})
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, 500)
        else:
            self.send_error(404)
    
    def log_message(self, format, *args):
        return # Suppress logs

def start_server():
    """Starts a custom HTTP server in a daemon thread"""
    try:
        with socketserver.TCPServer(("127.0.0.1", PORT), CustomHandler) as httpd:
            httpd.serve_forever()
    except OSError:
        pass

# El hilo del servidor se iniciará dentro de main() para evitar bloqueos
server_thread = threading.Thread(target=start_server, daemon=True)

def main():
    # Iniciar servidor local
    if not server_thread.is_alive():
        try:
            server_thread.start()
        except:
            pass
            
    show_header()
    check_venv()
    
    while True:
        console.print("\n[bold cyan]MENÚ PRINCIPAL[/bold cyan]")
        console.print("1. [bold green]🚀 Iniciar Nuevo Entrenamiento[/bold green]")
        console.print("2. [bold blue]📊 Ver Último Dashboard[/bold blue]")
        console.print("3. [bold gold1]⚙️ Configuración (Mapeo de Símbolos)[/bold gold1]")
        console.print("4. [bold red]🔴 Trading en Vivo[/bold red]")
        console.print("5. [bold magenta]🧹 Limpiar Datos y Reiniciar[/bold magenta]")
        console.print("6. [bold white]❌ Salir[/bold white]")
        
        try:
            # Uso de console.input para mayor compatibilidad en Linux
            prompt_text = "\n[bold yellow]Seleccione una opción [1-6] (1): [/bold yellow]"
            user_input = console.input(prompt_text).strip()
            choice = user_input if user_input else "1"
        except EOFError:
            break
        except KeyboardInterrupt:
            console.print("\n[red]Saliendo...[/red]")
            break
        
        if choice == "1":
            device = check_hardware()
            asset_type = select_asset_class()
            ticker = select_ticker(asset_type)
            period, epochs, train_timeframe, trade_timeframe, seq_length, hidden_dim, num_layers = select_parameters()
            
            console.print(f"\n[bold green]Resumen de Configuración:[/bold green]")
            console.print(f"• Clase: [cyan]{asset_type}[/cyan]")
            console.print(f"• Activo: [cyan]{ticker}[/cyan]")
            console.print(f"• Hardware: [magenta]{device.upper()}[/magenta]")
            console.print(f"• Periodo: [white]{period}[/white]")
            console.print(f"• Épocas: [white]{epochs}[/white]")
            console.print(f"• Timeframe Entrenamiento: [yellow]{train_timeframe}[/yellow]")
            console.print(f"• Timeframe Trading: [yellow]{trade_timeframe}[/yellow]")
            console.print(f"• Arquitectura GAN: [blue]Win={seq_length}, Hidden={hidden_dim}, Layers={num_layers}[/blue]")
            
            if Confirm.ask("\n¿Iniciar el proceso de entrenamiento?"):
                import torch
                from train import train_model
                console.print("\n[bold blue]Iniciando Motor de IA...[/bold blue]")
                
                # Call the training function
                try:
                    train_model(ticker, period, epochs, asset_type, train_timeframe, trade_timeframe, seq_length, hidden_dim, num_layers)
                    console.print("\n[bold green]✨ Proceso Completado Exitosamente![/bold green]")
                    console.print("El Dashboard se abrirá automáticamente en tu navegador.")
                except Exception as e:
                    console.print(f"\n[bold red]Error Crítico:[/bold red] {str(e)}")
                    import traceback
                    traceback.print_exc()
            else:
                console.print("[yellow]Operación cancelada por el usuario.[/yellow]")
                
        elif choice == "2":
            # Open via Localhost
            dashboard_url = f"http://localhost:{PORT}/outputs/dashboard.html"
            console.print(f"\n[green]Abriendo Dashboard:[/green] {dashboard_url}")
            webbrowser.open(dashboard_url)
            
        elif choice == "3":
            configure_symbols()

        elif choice == "4":
            console.print("\n[bold red]🔴 MODO LIVE TRADING[/bold red]")
            
            # Select Platform
            platform = select_platform()
            
            asset_type = select_asset_class()
            ticker = select_ticker(asset_type)
            
            # Select Timeframe
            trade_timeframe = select_timeframe(ticker)
            
            # Open Live Dashboard via Localhost
            dashboard_url = f"http://localhost:{PORT}/src/live/live_dashboard.html"
            console.print(f"[green]Abriendo Dashboard en Vivo...[/green]")
            webbrowser.open(dashboard_url)
            
            # Start Loop
            from src.live.live_trade import run_live_trading
            run_live_trading(ticker, asset_type, platform=platform, timeframe=trade_timeframe)
            
        elif choice == "5":
            clean_system_data()
            
        elif choice == "6":
            console.print("\n[yellow]¡Hasta luego![/yellow]")
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[red]Saliendo...[/red]")
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
