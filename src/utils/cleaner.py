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