"""Stage allowlisted release inputs, then compile critical modules in isolation."""
import os
import shutil
import subprocess
import sys
from check_build_inputs import parser, stage

# === Paths ===
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR  = os.path.join(ROOT_DIR, 'src')
OBF_DIR  = os.path.join(ROOT_DIR, 'build', 'obf_src')

# Critical Cython inputs, relative to the sanitized staging root.
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
        src_file = os.path.join(OBF_DIR, rel)
        
        if not os.path.exists(src_file):
            print(f"  WARNING: File to compile not found: {rel}")
            continue

        # For entry points, we skip Cython compilation because PyInstaller needs .py entry points
        if fname in ['train.py', 'run.py', 'start_api.py', 'browser_launcher.py']:
            print(f"  [INFO] Skipping Cython compilation for entry point: {rel}")
            continue

        print(f"  Cythonizing {rel} ...")
        
        # Cython is a prerequisite, never installed or upgraded by this command.
        # Copy to temp dir first so we don't pollute src/
        temp_src = os.path.join(temp, fname)
        shutil.copy2(src_file, temp_src)
        
        # Use the venv's cythonize executable to ensure correct ABI (e.g. cpython-311 instead of 314)
        cythonize_bin = os.path.join(os.path.dirname(sys.executable), 'cythonize')
        if not os.path.exists(cythonize_bin):
            cythonize_bin = 'cythonize' # fallback
            
        cmd = [cythonize_bin, '-i', '-3', temp_src]
        
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=temp)
        
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
            
            # Fallback: the staged plain source is already in place.
            print(f"    [INFO] Packaged regular version for {rel}")

    if os.path.exists(temp):
        shutil.rmtree(temp)


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
    cli = parser(__doc__)
    cli.add_argument('--stage-only', action='store_true', help='Copy safe inputs without compiling')
    args = cli.parse_args()
    try:
        OBF_DIR = str(stage(args.project_root.resolve()))
        if not args.stage_only:
            obfuscate_critical()
            protect_js()
        print('Safe staging complete: build/obf_src')
    except (ValueError, KeyError, OSError) as exc:
        print(f'Packaging error: {exc}', file=sys.stderr)
        sys.exit(1)
