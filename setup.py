import os
import sys
import subprocess

def setup_environment():
    """
    Crea un entorno virtual si no existe e instala las dependencias
    desde requirements.txt.
    """
    base_path = os.path.abspath(os.path.dirname(__file__))
    venv_path = os.path.join(base_path, 'venv')
    
    print("----------------------------------------------------------------")
    print("      QUANTUM LLAMA Beta 0.1.7 Stable - SCRIPT DE CONFIGURACION      ")
    print("----------------------------------------------------------------")

    # --- 1. Creación del Entorno Virtual ---
    print("[1/2] Verificando y/o creando el entorno virtual 'venv'...")
    if not os.path.exists(venv_path):
        print("   - El entorno 'venv' no existe. Creandolo ahora...")
        try:
            subprocess.run([sys.executable, '-m', 'venv', venv_path], check=True, capture_output=True, text=True)
            print("   - ¡Entorno virtual creado con éxito!")
        except subprocess.CalledProcessError as e:
            print("\n[ERROR] Ocurrió un error al crear el entorno virtual.")
            print(f"   - DETALLE: {e.stderr}")
            return
    else:
        print("   - El entorno virtual 'venv' ya existe.")

    # --- 2. Instalación de Dependencias ---
    print("\n[2/2] Instalando dependencias desde 'requirements.txt'...")
    
    # Construir rutas a pip y requirements.txt
    is_win = sys.platform == "win32"
    pip_folder = 'Scripts' if is_win else 'bin'
    pip_exe = 'pip.exe' if is_win else 'pip'
    pip_executable = os.path.join(venv_path, pip_folder, pip_exe)
    requirements_file = os.path.join(base_path, 'requirements.txt')

    if not os.path.exists(requirements_file):
        print(f"\n[ERROR] No se pudo encontrar el archivo '{requirements_file}'.")
        print("   - Por favor, asegúrese de que 'requirements.txt' esté en el directorio principal.")
        return

    try:
        # Usamos capture_output para un log más limpio. Mostramos el output si hay error.
        subprocess.run(
            [pip_executable, 'install', '-r', requirements_file], 
            check=True, 
            text=True,
            encoding='utf-8'
        )
        print("   - ¡Dependencias instaladas correctamente!")
    except subprocess.CalledProcessError as e:
        print("\n[ERROR] Ocurrió un error al instalar las dependencias.")
        print("   - Es posible que un paquete haya fallado. Revisa el detalle a continuación.")
        print("-" * 60)
        print(e.stdout)
        print(e.stderr)
        print("-" * 60)
        return

    print("\n----------------------------------------------------------------")
    print("✅ ¡Configuración completada! Ya puedes ejecutar el sistema.")
    print("----------------------------------------------------------------")


if __name__ == "__main__":
    setup_environment()
    os.system("pause")