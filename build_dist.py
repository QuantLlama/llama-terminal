"""Compatibility entry point: delegate to the authoritative PyInstaller backend build.

Nuitka and --cleanup-only were retired. Use npm run pack / npm run dist for
Electron packages; this entry point builds backend, Trainer and BrowserMode only.
"""
import subprocess
import sys
from pathlib import Path

if __name__ == '__main__':
    sys.exit(subprocess.call([sys.executable, str(
        Path(__file__).resolve().parent / 'scripts/build_backend.py'), *sys.argv[1:]]))
