import os
import sys
import time
import subprocess
import psutil
import logging
import threading
from typing import Optional, Dict, Any
from enum import Enum
logger = logging.getLogger(__name__)
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes
    SW_HIDE = 0
    SW_SHOW = 5
    SW_MINIMIZE = 6
    GW_OWNER = 4
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SWP_HIDEWINDOW = 0x0080
    SWP_SHOWWINDOW = 0x0040
    user32 = ctypes.windll.user32
    EnumWindows = user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    GetWindowText = user32.GetWindowTextW
    GetWindowTextLength = user32.GetWindowTextLengthW
    IsWindowVisible = user32.IsWindowVisible
    ShowWindow = user32.ShowWindow
    GetWindow = user32.GetWindow
    GetClassName = user32.GetClassNameW
    GetWindowThreadProcessId = user32.GetWindowThreadProcessId
    ShowWindowAsync = user32.ShowWindowAsync
    SetWindowPos = user32.SetWindowPos
class MT5Status(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    HIDDEN = "hidden"
    ERROR = "error"
class MT5Launcher:
    def __init__(self, project_root: str = None):
        self.project_root = project_root or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../..")
        )
        self.mt5_exe = self._find_mt5_executable()
        self.mt5_folder = os.path.dirname(self.mt5_exe) if self.mt5_exe else None
        self.process: Optional[subprocess.Popen] = None
        self.status = MT5Status.STOPPED
        self.pid: Optional[int] = None
        self.hidden = False
        self._hiding_loop_active = False
        if self.mt5_exe:
            logger.info(f"MT5Launcher inicializado - Ejecutable encontrado en: {self.mt5_exe}")
        else:
            logger.error("MT5Launcher ERROR: No se pudo encontrar terminal64.exe en ninguna ubicación conocida")
    def _find_mt5_executable(self) -> Optional[str]:
        search_paths = [
            r"C:\Program Files\MetaTrader 5\terminal64.exe",
            r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
            os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\terminal64.exe")
        ]
        for path in search_paths:
            if os.path.exists(path):
                return path
        return None
    def launch_mt5_hidden(self, config_path: str = None, timeout: int = 30, hidden: bool = False) -> bool:
        if not self.mt5_exe:
            self.mt5_exe = self._find_mt5_executable()
            if self.mt5_exe:
                self.mt5_folder = os.path.dirname(self.mt5_exe)
        if not self.mt5_exe or not os.path.exists(self.mt5_exe):
            print(f"CRITICAL ERROR: No se encuentra MT5 en {self.mt5_exe or 'ningun lugar'}")
            logger.error(f"MT5 executable not found: {self.mt5_exe}")
            self.status = MT5Status.ERROR
            return False
        self.hidden_target = hidden
        if self._is_mt5_running():
            logger.info("MT5 ya está corriendo")
            if hidden:
                self._hide_mt5_windows()
                self.status = MT5Status.HIDDEN
            else:
                self.show_mt5_windows()
                self.status = MT5Status.RUNNING
            return True
        try:
            self.status = MT5Status.STARTING
            logger.info(f"Lanzando MT5 desde: {self.mt5_exe} (Hidden={hidden})")
            args = [self.mt5_exe]
            if config_path and os.path.exists(config_path):
                args.extend(["/config", config_path])
            kwargs = {}
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = SW_HIDE if hidden else SW_SHOW
                creation_flags = 0
                if hidden:
                    CREATE_NO_WINDOW = 0x08000000
                    creation_flags |= CREATE_NO_WINDOW
                DETACHED_PROCESS = 0x00000008
                creation_flags |= DETACHED_PROCESS
                kwargs["startupinfo"] = startupinfo
                kwargs["creationflags"] = creation_flags

            self.process = subprocess.Popen(
                args,
                cwd=self.mt5_folder,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                **kwargs
            )
            self.pid = self.process.pid
            print(f"WS_STATUS: MT5 disparado con éxito (PID: {self.pid}, Hidden: {hidden})")
            logger.info(f"MT5 lanzado con éxito (PID: {self.pid})")
            if hidden:
                self.start_hiding_loop(interval=1.0)
                self.status = MT5Status.HIDDEN
            else:
                self.status = MT5Status.RUNNING
            return True
        except Exception as e:
            logger.error(f"Error crítico lanzando MT5: {e}")
            import traceback
            traceback.print_exc()
            self.status = MT5Status.ERROR
            return False
    def wait_for_ready(self, timeout: int = 30) -> bool:
        import MetaTrader5 as mt5
        start_time = time.time()
        logger.info(f"Waiting for MT5 to be ready (timeout: {timeout}s)...")
        while time.time() - start_time < timeout:
            try:
                if mt5.initialize(path=self.mt5_exe, timeout=2000):
                    logger.info("MT5 API connection successful")
                    mt5.shutdown()
                    return True
                if self.process and self.process.poll() is not None:
                    logger.error("MT5 process died during startup")
                    return False
            except Exception as e:
                logger.debug(f"MT5 not ready yet: {e}")
            time.sleep(1)
        logger.error(f"MT5 failed to be ready within {timeout}s")
        return False
    def _is_mt5_running(self) -> bool:
        try:
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                if proc.info['name'] and 'terminal64.exe' in proc.info['name'].lower():
                    self.pid = proc.info['pid']
                    logger.info(f"Found running MT5 process: PID {self.pid}")
                    return True
        except Exception as e:
            logger.error(f"Error checking for MT5 process: {e}")
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                if any(k in proc.info['name'].lower() for k in ['terminal64', 'metatrader']):
                    self.pid = proc.info['pid']
                    logger.info(f"Found MT5 process by name fallback: {proc.info['name']} (PID {self.pid})")
                    return True
        except:
            pass
        return False
    def _hide_mt5_windows(self, force_by_name: bool = False) -> bool:
        if sys.platform != "win32":
            logger.warning("Window hiding only supported on Windows")
            return False
        if not self.pid:
            self._is_mt5_running()
        hidden_count = 0
        def enum_callback(hwnd, lparam):
            nonlocal hidden_count
            window_pid = wintypes.DWORD()
            GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            length = GetWindowTextLength(hwnd)
            title = ""
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                GetWindowText(hwnd, buff, length + 1)
                title = buff.value
            class_name_buff = ctypes.create_unicode_buffer(256)
            GetClassName(hwnd, class_name_buff, 256)
            class_name = class_name_buff.value
            should_hide = False
            if self.pid and window_pid.value == self.pid:
                should_hide = True
            elif force_by_name or (not self.pid):
                if any(kw in title.lower() for kw in ['metatrader', 'terminal64', 'terminal 5', 'mt5', 'metaquotes', 'netting', 'hedged', 'demo', 'account']):
                    should_hide = True
                elif any(kw in class_name.lower() for kw in ['metaquotes', 'metatrader']):
                    should_hide = True
            if should_hide:
                SetWindowPos(hwnd, 0, -32000, -32000, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_HIDEWINDOW)
                ShowWindow(hwnd, SW_MINIMIZE)
                ShowWindow(hwnd, SW_HIDE)
                if (title or class_name) and IsWindowVisible(hwnd): 
                    logger.info(f"Attempts to Hide: '{title}' (Class: {class_name}) - Result: Visible? {IsWindowVisible(hwnd)}")
                else:
                    pass
                hidden_count += 1
            return True
        try:
            EnumWindows(EnumWindowsProc(enum_callback), 0)
            if hidden_count > 0:
                self.hidden = True
                if not self.pid: 
                    self._is_mt5_running()
            return self.hidden
        except Exception as e:
            logger.error(f"Error hiding MT5 windows: {e}")
            return False
    def start_hiding_loop(self, interval: float = 1.0):
        if self._hiding_loop_active:
            return None
        self._hiding_loop_active = True
        def _hider():
            logger.info("Iniciando bucle de ocultación persistente de MT5")
            start_time = time.time()
            self._hide_mt5_windows(force_by_name=True)
            while self._hiding_loop_active:
                try:
                    elapsed = time.time() - start_time
                    if elapsed < 30:
                        current_interval = 0.1   
                    else:
                        current_interval = 0.5   
                    self._hide_mt5_windows(force_by_name=True)
                    time.sleep(current_interval)
                except Exception as e:
                    logger.debug(f"Hiding loop error: {e}")
        thread = threading.Thread(target=_hider, daemon=True)
        thread.start()
        return thread
    def stop_hiding_loop(self):
        self._hiding_loop_active = False
        logger.info("MT5 hiding loop stopped")
    def show_mt5_windows(self) -> bool:
        if sys.platform != "win32":
            return False
        if not self.pid:
            return False
        shown_count = 0
        def enum_callback(hwnd, lparam):
            nonlocal shown_count
            window_pid = wintypes.DWORD()
            GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            if window_pid.value == self.pid:
                length = GetWindowTextLength(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    GetWindowText(hwnd, buff, length + 1)
                    title = buff.value
                    if any(keyword in title.lower() for keyword in ['metatrader', 'terminal', 'mt5']):
                        ShowWindow(hwnd, SW_SHOW)
                        logger.info(f"Shown MT5 window: {title}")
                        shown_count += 1
            return True
        try:
            EnumWindows(EnumWindowsProc(enum_callback), 0)
            self.hidden = False
            logger.info(f"Shown {shown_count} MT5 windows")
            return shown_count > 0
        except Exception as e:
            logger.error(f"Error showing MT5 windows: {e}")
            return False
    def stop(self) -> bool:
        if not self.process and not self.pid:
            self._is_mt5_running()
            if not self.pid:
                logger.info("No MT5 process to stop")
                return True
        try:
            logger.info(f"Stopping MT5 process (PID: {self.pid or 'Unknown'})...")
            if self.pid:
                try:
                    proc = psutil.Process(self.pid)
                    if proc.is_running():
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except psutil.TimeoutExpired:
                            logger.warning("MT5 didn't terminate, killing...")
                            proc.kill()
                            proc.wait(timeout=2)
                except psutil.NoSuchProcess:
                    pass
            if self.process:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=1)
                except:
                    pass
            for proc in psutil.process_iter(['name']):
                try:
                    if proc.info['name'] and 'terminal64.exe' in proc.info['name'].lower():
                        logger.info(f"Killing orphan MT5 process: {proc.pid}")
                        proc.kill()
                except:
                    pass
            self.process = None
            self.pid = None
            self.status = MT5Status.STOPPED
            self.hidden = False
            logger.info("MT5 process stopped successfully")
            return True
        except Exception as e:
            logger.error(f"Error stopping MT5: {e}")
            return False
    def get_status(self) -> Dict[str, Any]:
        is_running = False
        if self.pid:
            try:
                proc = psutil.Process(self.pid)
                is_running = proc.is_running()
            except psutil.NoSuchProcess:
                is_running = False
        return {
            "status": self.status.value,
            "pid": self.pid,
            "is_running": is_running,
            "hidden": self.hidden,
            "mt5_path": self.mt5_exe,
            "mt5_exists": os.path.exists(self.mt5_exe)
        }
_launcher: Optional[MT5Launcher] = None
def get_launcher() -> MT5Launcher:
    global _launcher
    if _launcher is None:
        _launcher = MT5Launcher()
    return _launcher