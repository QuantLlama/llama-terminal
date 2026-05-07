import json
import os
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table
console = Console()
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'symbols.json')
def get_config_path(platform="mt5"):
    base_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config')
    filename = f"symbols_{platform.lower()}.json"
    return os.path.join(base_dir, filename)
def load_symbol_map(platform="mt5"):
    target_path = get_config_path(platform)
    legacy_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'symbols.json')
    if not os.path.exists(target_path):
        default_map = {"Futures": {}, "Stocks": {}, "ETF": {}, "Crypto": {}}
        if os.path.exists(legacy_path):
            try:
                with open(legacy_path, 'r') as f:
                    legacy_data = json.load(f)
                    if isinstance(legacy_data, dict):
                        save_symbol_map(legacy_data, platform)
                        return legacy_data
            except:
                pass
        save_symbol_map(default_map, platform)
        return default_map
    try:
        with open(target_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        console.print(f"[red]Error cargando mapa de símbolos para {platform}: {e}[/red]")
        return {}
def save_symbol_map(data, platform="mt5"):
    config_path = get_config_path(platform)
    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(data, f, indent=4)
        console.print(f"[green]Configuración para {platform.upper()} guardada exitosamente.[/green]")
    except Exception as e:
        console.print(f"[red]Error guardando configuración para {platform}: {e}[/red]")
def configure_symbols():
    console.clear()
    console.print("[bold gold1]⚙️ CONFIGURACIÓN DE MAPEO DE SÍMBOLOS (MT5-ONLY)[/bold gold1]")
    platform_name = "MetaTrader 5"
    console.print(f"\n[cyan]Configurando símbolos para {platform_name}[/cyan]")
    console.print(f"Asocie los tickers del sistema (Yahoo Finance) con los símbolos de {platform_name}.\n")
    data = load_symbol_map()
    while True:
        table = Table(title="Mapeo Actual")
        table.add_column("Categoría", style="cyan")
        table.add_column("Ticker Sistema", style="white")
        table.add_column("Símbolo Broker", style="green")
        for category, symbols in data.items():
            for sys_ticker, broker_ticker in symbols.items():
                table.add_row(category, sys_ticker, broker_ticker)
        console.print(table)
        console.print("\n[1] Editar un Símbolo")
        console.print("[2] Agregar Nuevo Símbolo")
        console.print("[3] Volver al Menú Principal")
        choice = Prompt.ask("Seleccione una opción", choices=["1", "2", "3"], default="3")
        if choice == "3":
            break
        elif choice == "1":
            sys_ticker = Prompt.ask("Ingrese el Ticker del Sistema a editar (ej. MNQ=F)")
            found = False
            for cat in data:
                if sys_ticker in data[cat]:
                    new_broker = Prompt.ask(f"Nuevo símbolo Broker para {sys_ticker}", default=data[cat][sys_ticker])
                    data[cat][sys_ticker] = new_broker
                    found = True
                    save_symbol_map(data)
                    break
            if not found:
                console.print(f"[red]Ticker {sys_ticker} no encontrado.[/red]")
        elif choice == "2":
            cat = Prompt.ask("Categoría", choices=["Futures", "Stocks", "ETF"])
            sys_ticker = Prompt.ask("Ticker del Sistema (Yahoo Finance)")
            broker_ticker = Prompt.ask(f"Símbolo en {platform_name}")
            if cat not in data:
                data[cat] = {}
            data[cat][sys_ticker] = broker_ticker
            save_symbol_map(data)