
import os
import shutil
import subprocess
import sys
import glob
import time

# Configuration
APP_NAME = "QuantumLlama"
MAIN_SCRIPT = "start_api.py"
DIST_DIR = "dist"
BUILD_DIR = "build_nuitka"
ASSETS_TO_COPY = [
    "images",
    "src/platform/web",
    "src/config",
    "MT5",
    "requirements.txt",
    ".env.example",
    "train.py",
    "run.py",
    "src"
]

DEV_PATTERNS = [
    "test_*.py",
    "check_*.py",
    "debug_*.py",
    "diagnose_*.py",
    "local_test.py",
    "final_verify_*.py",
    "*.log",
    "*debug.txt",
    "*output.txt",
    "*.bat",
    "*.vbs",
    "*.pyw" # We will compile the main ones, but others might be dev
]

EXCLUDE_FROM_CLEANUP = ["start_api.py", "QuantumLlama.pyw", "run.py"]

def clean_all():
    print("--- Cleaning previous builds ---")
    
    def on_error(func, path, exc_info):
        import stat
        # Handle read-only files
        if not os.access(path, os.W_OK):
            os.chmod(path, stat.S_IWRITE)
            func(path)
        else:
            raise

    for directory in [DIST_DIR, BUILD_DIR]:
        if os.path.exists(directory):
            max_retries = 3
            for i in range(max_retries):
                try:
                    shutil.rmtree(directory, onerror=on_error)
                    break 
                except Exception as e:
                    if i < max_retries - 1:
                        print(f"Retry {i+1} deleting {directory} due to: {e}")
                        time.sleep(1)
                    else:
                        print(f"Warning: Could not fully clean {directory}. Ensure no files are in use.")
    
    os.makedirs(DIST_DIR, exist_ok=True)

def cleanup_dev_files(target_dir):
    print(f"--- Cleaning up development files in {target_dir} ---")
    for pattern in DEV_PATTERNS:
        files = glob.glob(os.path.join(target_dir, pattern))
        for f in files:
            basename = os.path.basename(f)
            if basename not in EXCLUDE_FROM_CLEANUP:
                print(f"Removing dev file: {f}")
                try:
                    if os.path.isfile(f):
                        os.remove(f)
                    elif os.path.isdir(f):
                        shutil.rmtree(f)
                except Exception as e:
                    print(f"Error removing {f}: {e}")

def run_nuitka():
    print("--- Running Nuitka Compilation (Obfuscation + Standalone) ---")
    
    python_exe = os.path.join("venv", "Scripts", "python.exe")
    if not os.path.exists(python_exe):
        python_exe = sys.executable

    cmd = [
        python_exe, "-m", "nuitka",
        "--standalone",
        "--onefile",
        "--windows-disable-console",
        f"--windows-icon-from-ico=images/QuantumLLama.ico" if os.path.exists("images/QuantumLLama.ico") else "",
        "--plugin-enable=tk-inter",
        "--plugin-enable=numpy",
        "--include-package=fastapi",
        "--include-package=uvicorn",
        "--include-package=supabase",
        "--output-dir=" + DIST_DIR,
        "--output-filename=" + APP_NAME,
        f"--onefile-tempdir-spec={{TEMP}}/nuitka_{APP_NAME}",
        MAIN_SCRIPT
    ]
    
    # Remove empty arguments
    cmd = [c for c in cmd if c]
    
    print(f"Executing: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

def finalize_dist():
    print("--- Finalizing Distribution ---")
    # Copy essential source files that are not compiled (if any) or assets
    for asset in ASSETS_TO_COPY:
        if os.path.exists(asset):
            dest = os.path.join(DIST_DIR, asset)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if os.path.isdir(asset):
                shutil.copytree(asset, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(asset, dest)
    
    # Also copy the whole 'src' but without compiled parts if necessary?
    # Actually, standalone includes everything needed in the exe.
    # But for FastAPI to work (if it's not fully bundled), we might need src.
    # We'll see after the first build.

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cleanup-only":
        cleanup_dev_files(".")
    else:
        clean_all()
        # cleanup_dev_files(".") # Optional: cleanup before build
        try:
            run_nuitka()
            finalize_dist()
            print("\nBUILD SUCCESSFUL! Distribution folder: " + DIST_DIR)
        except Exception as e:
            print(f"\nBUILD FAILED: {e}")
            sys.exit(1)
