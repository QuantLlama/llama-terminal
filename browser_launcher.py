import os
import sys
import webbrowser
import subprocess
import time
import requests

# Port used by the backend
import socket

def find_running_backend():
    for port in range(8050, 8060):
        if is_backend_running(port, timeout=0.2):
            return port
    return None

def get_free_port(start_port=8050, max_port=8100):
    for port in range(start_port, max_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return start_port

API_PORT = 8050

API_URL = f"http://127.0.0.1:{API_PORT}"

def is_backend_running(port=None, timeout=1):
    if port is None:
        port = API_PORT
    try:
        response = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=timeout)
        if response.status_code != 200:
            return False
        health = response.json()
        return isinstance(health, dict) and health.get("ready_for_ui") is True
    except (requests.RequestException, ValueError):
        return False

def backend_executable(current_dir):
    """Resolve the packaged backend name for this platform.

    The PyInstaller builder emits ``backend.exe`` on Windows and ``backend``
    elsewhere, so the launcher must not assume the Windows suffix.
    """
    name = "backend.exe" if os.name == "nt" else "backend"
    path = os.path.join(current_dir, name)
    if not os.path.isfile(path):
        return None
    if os.name != "nt" and not os.access(path, os.X_OK):
        return None
    return path


def spawn_backend(backend_path, port, current_dir):
    """Start the backend with platform-appropriate process options."""
    argv = [backend_path, "--port", str(port)]
    if os.name == "nt":
        return subprocess.Popen(
            argv, creationflags=subprocess.CREATE_NO_WINDOW, cwd=current_dir
        )
    return subprocess.Popen(argv, cwd=current_dir)


def launch_browser():
    """
    Launch the browser in 'app mode' to hide the URL bar if using Chrome/Edge.
    Fallback to standard browser if app mode fails.
    """
    # The Windows registry lookup is the only app-mode path; other platforms
    # have no equivalent and must fall back without reporting a fake error.
    if os.name != "nt":
        webbrowser.open(API_URL)
        return
    try:
        import winreg
        chrome_path = None
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
            chrome_path, _ = winreg.QueryValueEx(key, "")
            winreg.CloseKey(key)
        except Exception:
            pass

        if chrome_path:
            # Launch in App Mode: hides address bar, tabs, etc.
            subprocess.Popen([chrome_path, f"--app={API_URL}"])
            return

        # Fallback to default browser
        webbrowser.open(API_URL)
    except Exception as e:
        print(f"Error launching browser: {e}")
        webbrowser.open(API_URL)

def main():
    global API_PORT, API_URL
    API_PORT = find_running_backend() or get_free_port(8050)
    API_URL = f"http://127.0.0.1:{API_PORT}"
    # If we are in the packaged app, the backend might be in the same folder as this launcher
    # or in the resources folder.
    if not is_backend_running():
        # In a frozen (PyInstaller --onefile) build, __file__ points to a temp dir.
        # sys.executable points to the actual EXE location on disk.
        if getattr(sys, 'frozen', False):
            current_dir = os.path.dirname(sys.executable)
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))
        backend_exe = backend_executable(current_dir)

        if backend_exe:
            spawn_backend(backend_exe, API_PORT, current_dir)
            
            # Wait for backend to be ready
            for _ in range(30):
                if is_backend_running():
                    break
                time.sleep(1)
            else:
                print("Backend readiness timed out; browser was not opened.")
                return
        else:
            print("Backend is not ready; browser was not opened.")
            return

    launch_browser()

if __name__ == "__main__":
    main()
