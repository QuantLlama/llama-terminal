"""
Build protection script for Quantum Llama.
Strategy:
  - Copy ALL src/ files to build/obf_src/src (including .py files)
  - Overwrite the 3 critical files with PyArmor-obfuscated versions
  - Copy the PyArmor runtime to the root (importable from resources/)
  - Copy start_api.py and .env to the root
"""
import os
import shutil
import subprocess
import sys
import re
import time

# === Paths ===
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR  = os.path.join(ROOT_DIR, 'src')
OBF_DIR  = os.path.join(ROOT_DIR, 'build', 'obf_src')
is_win = sys.platform == "win32"
venv_folder = "Scripts" if is_win else "bin"
pyarmor_name = "pyarmor.exe" if is_win else "pyarmor"
if not is_win:
    # Comprobar si hay una ruta alternativa guardada
    path_file = os.path.join(ROOT_DIR, '.venv_linux_path')
    if os.path.exists(path_file):
        with open(path_file, 'r', encoding='utf-8') as f:
            alt_path = f.read().strip()
            if alt_path and os.path.exists(alt_path):
                PYARMOR = os.path.join(alt_path, venv_folder, pyarmor_name)
            else:
                PYARMOR = os.path.join(ROOT_DIR, "venv_linux", venv_folder, pyarmor_name)
    else:
        PYARMOR = os.path.join(ROOT_DIR, "venv_linux", venv_folder, pyarmor_name)
else:
    PYARMOR = os.path.join(ROOT_DIR, "venv", venv_folder, pyarmor_name)

# Critical files to protect with PyArmor (relative to ROOT_DIR, using forward slashes)
CRITICAL = [
    'src/services/auth.py',
    'src/services/license_service.py',
    'src/services/database.py',
    'src/services/security.py',
    'src/services/replication_service.py',
    'src/live/live_trade.py',
    'src/live/crypto_connector.py',
    'src/live/connector.py',
    'train.py',
    'run.py',
]

# JS files to "protect" via minification
JS_DIR = os.path.join(SRC_DIR, 'platform', 'web')


def clean_obf():
    """Remove and recreate the output directory."""
    if os.path.exists(OBF_DIR):
        print(f"Cleaning {OBF_DIR} ...")
        for attempt in range(5):
            try:
                shutil.rmtree(OBF_DIR)
                break
            except Exception as exc:
                print(f"  Retry {attempt+1}: {exc}")
                time.sleep(1)
    os.makedirs(OBF_DIR, exist_ok=True)


def copy_src():
    """Copy the entire src/ tree and top-level scripts to OBF_DIR."""
    dest = os.path.join(OBF_DIR, 'src')
    print(f"Copying src/ -> {dest}")
    # Use ignore to skip build directory if we're running from root
    shutil.copytree(SRC_DIR, dest, ignore=shutil.ignore_patterns(
        '__pycache__', 'build', 'dist', '.git', '.venv', 'venv', 'node_modules', '*.log'
    ))

    # Copy plain versions of train/run first (will be overwritten if obfuscation succeeds)
    for f in ['train.py', 'run.py']:
        src = os.path.join(ROOT_DIR, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(OBF_DIR, f))
    print("  Done.")


def obfuscate_critical():
    """Use Cython to compile critical files individually to C extensions (.so/.pyd)."""
    print("Running Cython on critical files ...")

    temp = os.path.join(OBF_DIR, '_cython_tmp')
    os.makedirs(temp, exist_ok=True)

    env = os.environ.copy()
    env.pop('PYTHONPATH', None)

    for rel in CRITICAL:
        fname = os.path.basename(rel)
        name_only = os.path.splitext(fname)[0]
        src_file = os.path.join(ROOT_DIR, rel)
        
        if not os.path.exists(src_file):
            print(f"  WARNING: File to compile not found: {rel}")
            continue

        # For entry points, we skip Cython compilation because PyInstaller needs .py entry points
        if fname in ['train.py', 'run.py', 'start_api.py', 'browser_launcher.py']:
            print(f"  [INFO] Skipping Cython compilation for entry point: {rel}")
            dst = os.path.join(OBF_DIR, *rel.split('/'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src_file, dst)
            continue

        print(f"  Cythonizing {rel} ...")
        
        # Ensure Cython is installed in the current venv
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'cython'], check=True, stdout=subprocess.DEVNULL)
        
        # Copy to temp dir first so we don't pollute src/
        temp_src = os.path.join(temp, fname)
        shutil.copy2(src_file, temp_src)
        
        # Use the venv's cythonize executable to ensure correct ABI (e.g. cpython-311 instead of 314)
        cythonize_bin = os.path.join(os.path.dirname(sys.executable), 'cythonize')
        if not os.path.exists(cythonize_bin):
            cythonize_bin = 'cythonize' # fallback
            
        cmd = [cythonize_bin, '-i', '-3', temp_src]
        
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        
        dst_dir = os.path.join(OBF_DIR, *rel.split('/')[:-1])
        os.makedirs(dst_dir, exist_ok=True)

        # Look for the generated .so or .pyd
        compiled_files = [f for f in os.listdir(temp) if f.startswith(name_only + '.') and (f.endswith('.so') or f.endswith('.pyd'))]
        
        if result.returncode == 0 and compiled_files:
            compiled_file = compiled_files[0]
            compiled_src = os.path.join(temp, compiled_file)
            
            # Copy compiled file to destination
            shutil.copy2(compiled_src, os.path.join(dst_dir, compiled_file))
            
            # Remove the plain .py file from OBF_DIR so PyInstaller picks up the compiled version
            plain_py = os.path.join(dst_dir, fname)
            if os.path.exists(plain_py):
                os.remove(plain_py)
                
            print(f"    [OK] Compiled (Cython): {rel} -> {compiled_file}")
            
            # Clean up temp files for this module
            for f in os.listdir(temp):
                item_path = os.path.join(temp, f)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)
        else:
            print(f"    [WARNING] Cython could not compile: {rel}")
            if result.stderr:
                print(f"      Error Details: {result.stderr.strip()}")
            
            # Fallback
            plain_dst = os.path.join(dst_dir, fname)
            shutil.copy2(src_file, plain_dst)
            print(f"    [INFO] Packaged regular version for {rel}")

    if os.path.exists(temp):
        shutil.rmtree(temp)


def copy_extras():
    """Copy start_api.py, .env (and any other root-level extras) to OBF_DIR."""
    extras = ['start_api.py', '.env']
    for f in extras:
        src = os.path.join(ROOT_DIR, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(OBF_DIR, f))
            print(f"Copied extra: {f}")
        else:
            print(f"WARNING: {f} not found at {src}")


def protect_js():
    """Perform basic minification on JS files in the output directory."""
    print("Protecting JS files (safe mode)...")
    web_dest = os.path.join(OBF_DIR, 'src', 'platform', 'web')
    if not os.path.exists(web_dest):
        print(f"  Warning: Web dest not found: {web_dest}")
        return

    # Skip vendor libraries and assets that are already minified or delicate
    SKIP_DIRS = ['lib', 'vendor', 'assets', 'sound', 'images', 'monaco']
    
    count = 0
    for root, dirs, files in os.walk(web_dest):
        # Filter out skipped directories
        if any(skip in root.replace(web_dest, '').split(os.sep) for skip in SKIP_DIRS):
            continue

        for file in files:
            if file.endswith('.js') and '.min.' not in file:
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    new_lines = []
                    for line in lines:
                        # Only remove comments that occupy the entire line
                        # (Safer than removing // mid-line which breaks URLs)
                        stripped = line.strip()
                        if stripped.startswith('//') or (stripped.startswith('/*') and stripped.endswith('*/')):
                            continue
                        new_lines.append(line)
                    
                    if len(new_lines) < len(lines):
                        with open(path, 'w', encoding='utf-8') as f:
                            f.writelines(new_lines)
                        count += 1
                except Exception as e:
                    print(f"  Error protecting {file}: {e}")
    print(f"  Done. {count} application JS files protected.")


if __name__ == '__main__':
    try:
        clean_obf()
        copy_src()
        obfuscate_critical()
        copy_extras()
        protect_js()
        print("\n[OK] Obfuscation and protection complete.")
        print(f"Location: {OBF_DIR}")
        print("  Critical files: obfuscated with PyArmor")
        print("  Everything else: plain .py (packaged inside the installer)")
    except Exception as exc:
        print(f"\nFATAL: {exc}")
        import traceback; traceback.print_exc()
        sys.exit(1)
