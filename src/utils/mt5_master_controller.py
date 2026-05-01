import os
import time
import psutil
import subprocess
import threading
import tempfile
from pathlib import Path
from typing import Tuple, Optional
class MT5MasterController:
    _instance = None
    _lock = threading.RLock()
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    def __init__(self):
        if self._initialized:
            return
        self.project_root = Path(__file__).parent.parent.parent.absolute()
        self.mt5_exe_path = self.project_root / "MT5" / "terminal64.exe"
        self.global_lock_file = Path(tempfile.gettempdir()) / "quantum_llama_mt5_master.lock"
        self.mt5_process = None
        self.mt5_pid = None
        self.is_invisible = True
        self.monitor_running = False
        self.window_monitor_thread = None
        self._initialized = True
        print(f"[MT5_MASTER] Controller initialized for {self.mt5_exe_path}")
    def get_or_start_mt5(self, invisible: bool = True) -> Tuple[bool, Optional[int]]:
        with self._lock:
            print(f"[MT5_MASTER] Request to get/start MT5 (invisible={invisible})")
            running, existing_pid = self.is_mt5_running()
            if running and existing_pid:
                print(f"[MT5_MASTER] MT5 already running (PID: {existing_pid})")
                self.mt5_pid = existing_pid
                if invisible and not self.monitor_running:
                    self._start_window_monitor()
                return True, existing_pid
            if not self._acquire_global_lock():
                print("[MT5_MASTER] Could not acquire global lock")
                return False, None
            try:
                print("[MT5_MASTER] Killing ALL existing MT5 instances...")
                killed_count = self._kill_all_mt5_instances()
                if killed_count > 0:
                    time.sleep(5)
                print("[MT5_MASTER] Starting NEW MT5 instance...")
                success, pid = self._start_mt5_instance(invisible)
                if success:
                    self.mt5_pid = pid
                    self.is_invisible = invisible
                    time.sleep(2)
                    instance_count = self._count_mt5_instances()
                    if instance_count > 1:
                        print(f"[MT5_MASTER] WARNING: {instance_count} instances! Fixing...")
                        self._ensure_single_instance()
                    if invisible:
                        self._start_window_monitor()
                    print(f"[MT5_MASTER] MT5 started successfully (PID: {self.mt5_pid})")
                    return True, self.mt5_pid
                else:
                    print("[MT5_MASTER] Failed to start MT5")
                    return False, None
            finally:
                self._release_global_lock()
    def stop_mt5(self) -> bool:
        with self._lock:
            print("[MT5_MASTER] Stopping MT5...")
            self._stop_window_monitor()
            killed_count = self._kill_all_mt5_instances()
            self.mt5_process = None
            self.mt5_pid = None
            print(f"[MT5_MASTER] MT5 stopped ({killed_count} instances killed)")
            return killed_count > 0
    def is_mt5_running(self) -> Tuple[bool, Optional[int]]:
        try:
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                if proc.info['name'] and 'terminal64.exe' in proc.info['name'].lower():
                    exe_path = proc.info.get('exe', '')
                    if str(self.mt5_exe_path) in exe_path:
                        return True, proc.info['pid']
            return False, None
        except Exception:
            return False, None
    def make_visible(self) -> bool:
        if not self.mt5_pid:
            return False
        try:
            import win32gui
            import win32con
            made_visible = False
            def enum_windows_callback(hwnd, windows):
                nonlocal made_visible
                if not win32gui.IsWindowVisible(hwnd):
                    window_text = win32gui.GetWindowText(hwnd)
                    if "MetaTrader" in window_text or "terminal64" in window_text.lower():
                        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                        win32gui.SetForegroundWindow(hwnd)
                        made_visible = True
                        windows.append(hwnd)
                return True
            windows = []
            win32gui.EnumWindows(enum_windows_callback, windows)
            if made_visible:
                self.is_invisible = False
                self._stop_window_monitor()
                print("[MT5_MASTER] MT5 made visible")
            return made_visible
        except Exception as e:
            print(f"[MT5_MASTER] Error making MT5 visible: {e}")
            return False
    def make_invisible(self) -> bool:
        if not self.mt5_pid:
            return False
        print("[MT5_MASTER] Restarting MT5 in invisible mode...")
        self.stop_mt5()
        time.sleep(2)
        success, pid = self.get_or_start_mt5(invisible=True)
        return success
    def _count_mt5_instances(self) -> int:
        count = 0
        try:
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                if proc.info['name'] and 'terminal64.exe' in proc.info['name'].lower():
                    exe_path = proc.info.get('exe', '')
                    if str(self.mt5_exe_path) in exe_path:
                        count += 1
        except Exception:
            pass
        return count
    def _kill_all_mt5_instances(self) -> int:
        killed_count = 0
        for attempt in range(3):
            current_killed = 0
            try:
                for proc in psutil.process_iter(['pid', 'name']):
                    if proc.info['name'] and 'terminal64.exe' in proc.info['name'].lower():
                        try:
                            print(f"[MT5_MASTER] Killing MT5 PID: {proc.info['pid']}")
                            proc.kill()
                            current_killed += 1
                            killed_count += 1
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
            except Exception:
                pass
            if current_killed == 0:
                break
            time.sleep(1)
        return killed_count
    def _ensure_single_instance(self):
        mt5_processes = []
        try:
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                if proc.info['name'] and 'terminal64.exe' in proc.info['name'].lower():
                    exe_path = proc.info.get('exe', '')
                    if str(self.mt5_exe_path) in exe_path:
                        mt5_processes.append(proc)
        except Exception:
            return
        if len(mt5_processes) > 1:
            print(f"[MT5_MASTER] Found {len(mt5_processes)} instances, keeping only the first")
            for i, proc in enumerate(mt5_processes):
                if i == 0:
                    self.mt5_pid = proc.info['pid']
                    print(f"[MT5_MASTER] Keeping MT5 PID: {proc.info['pid']}")
                else:
                    try:
                        proc.kill()
                        print(f"[MT5_MASTER] Killed duplicate MT5 PID: {proc.info['pid']}")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
    def _start_mt5_instance(self, invisible: bool) -> Tuple[bool, Optional[int]]:
        try:
            kwargs = {}
            import sys
            if invisible:
                if sys.platform == "win32":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    kwargs["startupinfo"] = startupinfo
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                self.mt5_process = subprocess.Popen([
                    str(self.mt5_exe_path)
                ], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                **kwargs)
            else:
                self.mt5_process = subprocess.Popen([
                    str(self.mt5_exe_path)
                ])
            print("[MT5_MASTER] Waiting for MT5 to initialize...")
            time.sleep(8)
            for attempt in range(10):
                running, pid = self.is_mt5_running()
                if running:
                    print(f"[MT5_MASTER] MT5 started successfully (PID: {pid})")
                    return True, pid
                time.sleep(1)
            print("[MT5_MASTER] MT5 failed to start within timeout")
            return False, None
        except Exception as e:
            print(f"[MT5_MASTER] Error starting MT5: {e}")
            return False, None
    def _acquire_global_lock(self, timeout: int = 30) -> bool:
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                with open(self.global_lock_file, 'x') as f:
                    f.write(f"PID: {os.getpid()}\nTime: {time.time()}\n")
                print(f"[MT5_MASTER] Global lock acquired by PID {os.getpid()}")
                return True
            except FileExistsError:
                try:
                    if self.global_lock_file.exists():
                        lock_age = time.time() - self.global_lock_file.stat().st_mtime
                        if lock_age > 60:
                            print("[MT5_MASTER] Removing stale global lock")
                            self.global_lock_file.unlink()
                            continue
                except Exception:
                    pass
                print("[MT5_MASTER] Global lock held, waiting...")
                time.sleep(1)
        print(f"[MT5_MASTER] Failed to acquire global lock after {timeout}s")
        return False
    def _release_global_lock(self):
        try:
            if self.global_lock_file.exists():
                self.global_lock_file.unlink()
                print(f"[MT5_MASTER] Global lock released by PID {os.getpid()}")
        except Exception as e:
            print(f"[MT5_MASTER] Error releasing global lock: {e}")
    def _start_window_monitor(self):
        if self.monitor_running:
            return
        def monitor_windows():
            try:
                import win32gui
                import win32con
                self.monitor_running = True
                print("[MT5_MASTER] Window monitor started")
                while self.monitor_running:
                    if not self.is_mt5_running()[0]:
                        break
                    def enum_windows_callback(hwnd, windows):
                        if win32gui.IsWindowVisible(hwnd):
                            window_text = win32gui.GetWindowText(hwnd)
                            if ("MetaTrader" in window_text or 
                                "terminal64" in window_text.lower() or
                                "Demo Account" in window_text):
                                if "Quantum" not in window_text and "Python" not in window_text:
                                    win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
                                    windows.append(hwnd)
                        return True
                    windows = []
                    win32gui.EnumWindows(enum_windows_callback, windows)
                    time.sleep(2)
            except Exception as e:
                print(f"[MT5_MASTER] Window monitor error: {e}")
            finally:
                self.monitor_running = False
                print("[MT5_MASTER] Window monitor stopped")
        self.window_monitor_thread = threading.Thread(target=monitor_windows, daemon=True)
        self.window_monitor_thread.start()
    def _stop_window_monitor(self):
        if self.monitor_running:
            self.monitor_running = False
            print("[MT5_MASTER] Stopping window monitor...")
            if self.window_monitor_thread and self.window_monitor_thread.is_alive():
                self.window_monitor_thread.join(timeout=5)
def get_mt5_master() -> MT5MasterController:
    return MT5MasterController()
def start_mt5(invisible: bool = True) -> Tuple[bool, Optional[int]]:
    return get_mt5_master().get_or_start_mt5(invisible)
def stop_mt5() -> bool:
    return get_mt5_master().stop_mt5()
def is_mt5_running() -> Tuple[bool, Optional[int]]:
    return get_mt5_master().is_mt5_running()