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
        try:
            response = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=0.2)
            if response.status_code == 200:
                return port
        except:
            continue
    return None

def get_free_port(start_port=8050, max_port=8100):
    for port in range(start_port, max_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return start_port

API_PORT = find_running_backend()
if not API_PORT:
    API_PORT = get_free_port(8050)

API_URL = f"http://127.0.0.1:{API_PORT}"

def is_backend_running(port=None):
    if port is None:
        port = API_PORT
    try:
        response = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=1)
        return response.status_code == 200
    except:
        return False

def launch_browser():
    """
    Launch the browser in 'app mode' to hide the URL bar if using Chrome/Edge.
    Fallback to standard browser if app mode fails.
    """
    # Common browsers and their app mode flags
    # We prioritize Chrome/Edge for the 'app' flag which gives a clean terminal look
    try:
        # Try to find Chrome
        import winreg
        chrome_path = None
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
            chrome_path, _ = winreg.QueryValueEx(key, "")
            winreg.CloseKey(key)
        except:
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
    # If we are in the packaged app, the backend might be in the same folder as this launcher
    # or in the resources folder.
    if not is_backend_running():
        # In a frozen (PyInstaller --onefile) build, __file__ points to a temp dir.
        # sys.executable points to the actual EXE location on disk.
        if getattr(sys, 'frozen', False):
            current_dir = os.path.dirname(sys.executable)
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))
        backend_exe = os.path.join(current_dir, "backend.exe")
        
        if os.path.exists(backend_exe):
            subprocess.Popen([backend_exe, "--port", str(API_PORT)], 
                             creationflags=subprocess.CREATE_NO_WINDOW,
                             cwd=current_dir)
            
            # Wait for backend to be ready
            for _ in range(30):
                if is_backend_running():
                    break
                time.sleep(1)

    launch_browser()

if __name__ == "__main__":
    main()
