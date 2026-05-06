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
PYARMOR  = os.path.join(ROOT_DIR, 'venv', 'Scripts', 'pyarmor.exe')

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
    """Use PyArmor to obfuscate the critical files, then place results correctly."""
    print("Running PyArmor on critical files ...")

    # PyArmor outputs to a temp dir so we can extract runtime separately
    temp = os.path.join(OBF_DIR, '_pyarmor_tmp')
    os.makedirs(temp, exist_ok=True)

    # Build command: gen -O <output> <file1> <file2> ...
    # Bypass corrupted pyarmor.exe wrapper on Windows by using module invocation
    cmd = [sys.executable, '-m', 'pyarmor.cli', 'gen', '-O', temp]
    for rel in CRITICAL:
        cmd.append(os.path.join(ROOT_DIR, rel))

    env = os.environ.copy()
    env.pop('PYTHONPATH', None)          # avoid PyArmor picking up wrong platform module
    print(f"  Command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        print(f"\n[FATAL ERROR] PyArmor failed with exit code {result.returncode}")
        print(f"STDOUT:\n{result.stdout}")
        print(f"STDERR:\n{result.stderr}")
        print("\nAborting build to prevent non-obfuscated deployment.")
        sys.exit(1)

    # Move obfuscated files to their final positions (overwrite plain copies)
    for rel in CRITICAL:
        fname = os.path.basename(rel)
        src   = os.path.join(temp, fname)
        dst   = os.path.join(OBF_DIR, *rel.split('/'))   # OBF_DIR/src/services/auth.py etc.
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"  Protected (PyArmor): {rel}")
        else:
            print(f"  WARNING: PyArmor did not produce {fname} – keeping plain .py")

    # Copy PyArmor runtime to ROOT of OBF_DIR so it ends up at resources root
    runtime_name = 'pyarmor_runtime_000000'
    runtime_src  = os.path.join(temp, runtime_name)
    if os.path.exists(runtime_src):
        runtime_dst = os.path.join(OBF_DIR, runtime_name)
        shutil.copytree(runtime_src, runtime_dst)
        print(f"  Runtime copied -> {runtime_dst}")
    else:
        print("  WARNING: PyArmor runtime folder not found in temp output.")

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
