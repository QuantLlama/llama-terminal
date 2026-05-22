import os
import shutil
import glob
from rich.console import Console
from rich.prompt import Confirm
console = Console()
def clean_system_data(interactive=True):
    if interactive:
        console.print("\n[bold red]⚠️  ADVERTENCIA: ESTA ACCIÓN ES IRREVERSIBLE ⚠️[/bold red]")
        console.print("Esta opción eliminará:")
        console.print(" - Todos los modelos entrenados (.pth, .pkl, .json)")
        console.print(" - Todos los gráficos generados (.png)")
        console.print(" - Historial de entrenamiento (history.json)")
        console.print(" - Estado de trading en vivo (live_status.json)")
        if not Confirm.ask("\n¿Está SEGURO que desea eliminar todos los datos y reiniciar el sistema?"):
            console.print("[yellow]Operación cancelada.[/yellow]")
            return
    from src.services.database import get_outputs_dir
    outputs_dir = get_outputs_dir()
    dirs_to_clean = [
        os.path.join(outputs_dir, 'models'),
        os.path.join(outputs_dir, 'plots')
    ]
    files_to_delete = [
        os.path.join(outputs_dir, 'history.json'),
        os.path.join(outputs_dir, 'live_status.json'),
        os.path.join(outputs_dir, 'dashboard.html')
    ]
    deleted_count = 0
    for directory in dirs_to_clean:
        if os.path.exists(directory):
            files = glob.glob(f"{directory}/*")
            for f in files:
                try:
                    if os.path.isfile(f):
                        os.remove(f)
                        deleted_count += 1
                    elif os.path.isdir(f):
                        shutil.rmtree(f)
                        deleted_count += 1
                except Exception as e:
                    console.print(f"[red]Error eliminando {f}: {e}[/red]")
            console.print(f"[green]Directorio limpio:[/green] {directory}")
        else:
            try:
                os.makedirs(directory)
            except:
                pass
    for file_path in files_to_delete:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                deleted_count += 1
                console.print(f"[green]Archivo eliminado:[/green] {file_path}")
            except Exception as e:
                console.print(f"[red]Error eliminando {file_path}: {e}[/red]")
    console.print(f"\n[bold green]✨ Limpieza Completada. Se eliminaron {deleted_count} archivos/carpetas.[/bold green]")
    console.print("[cyan]El sistema está listo para arrancar desde cero.[/cyan]")

def auto_clean_logs(max_days=7, max_size_mb=1000):
    """
    Limpia automáticamente los logs antiguos o si la carpeta supera cierto tamaño.
    """
    import time
    from src.services.database import get_logs_dir
    
    log_dir = get_logs_dir()
    if not os.path.exists(log_dir):
        return

    now = time.time()
    max_age_seconds = max_days * 86400
    
    # 1. Eliminar archivos por antigüedad
    files = glob.glob(os.path.join(log_dir, "*.log"))
    files += glob.glob(os.path.join(log_dir, "*.txt"))
    
    for f in files:
        try:
            if os.path.isfile(f):
                file_age = now - os.path.getmtime(f)
                if file_age > max_age_seconds:
                    os.remove(f)
        except:
            pass

    # 2. Control de tamaño total (si sigue pesando mucho, borrar los más viejos)
    try:
        def get_dir_size(path):
            total = 0
            with os.scandir(path) as it:
                for entry in it:
                    if entry.is_file():
                        total += entry.stat().st_size
                    elif entry.is_dir():
                        total += get_dir_size(entry.path)
            return total

        current_size_mb = get_dir_size(log_dir) / (1024 * 1024)
        
        if current_size_mb > max_size_mb:
            # Ordenar archivos por fecha de modificación (más viejos primero)
            all_files = []
            for root, _, filenames in os.walk(log_dir):
                for filename in filenames:
                    path = os.path.join(root, filename)
                    all_files.append((path, os.path.getmtime(path)))
            
            all_files.sort(key=lambda x: x[1])
            
            # Borrar hasta que el tamaño sea aceptable (70% del max_size)
            target_size = max_size_mb * 0.7
            for path, _ in all_files:
                if current_size_mb <= target_size:
                    break
                try:
                    size = os.path.getsize(path)
                    os.remove(path)
                    current_size_mb -= (size / (1024 * 1024))
                except:
                    pass
    except Exception as e:
        print(f"Error in auto_clean_logs: {e}")