import os
import time
import fcntl
import tempfile
from pathlib import Path
class MT5GlobalLock:
    def __init__(self):
        self.lock_file_path = Path(tempfile.gettempdir()) / "quantum_llama_mt5.lock"
        self.lock_file = None
        self.locked = False
    def __enter__(self):
        return self.acquire()
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
    def acquire(self, timeout=30):
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                self.lock_file = open(self.lock_file_path, 'w')
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.lock_file.write(f"PID: {os.getpid()}\n")
                self.lock_file.write(f"Time: {time.time()}\n")
                self.lock_file.flush()
                self.locked = True
                print(f"[MT5_GLOBAL_LOCK] Lock acquired by PID {os.getpid()}")
                return True
            except (IOError, OSError):
                if self.lock_file:
                    self.lock_file.close()
                    self.lock_file = None
                print(f"[MT5_GLOBAL_LOCK] Lock held by another process, waiting...")
                time.sleep(1)
                continue
        print(f"[MT5_GLOBAL_LOCK] Failed to acquire lock after {timeout}s timeout")
        return False
    def release(self):
        if self.locked and self.lock_file:
            try:
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                self.lock_file.close()
                if self.lock_file_path.exists():
                    self.lock_file_path.unlink()
                print(f"[MT5_GLOBAL_LOCK] Lock released by PID {os.getpid()}")
            except Exception as e:
                print(f"[MT5_GLOBAL_LOCK] Error releasing lock: {e}")
            finally:
                self.lock_file = None
                self.locked = False
    def is_locked(self):
        return self.locked
if os.name == 'nt':
    import msvcrt
    class MT5GlobalLock:
        def __init__(self):
            self.lock_file_path = Path(tempfile.gettempdir()) / "quantum_llama_mt5.lock"
            self.lock_file = None
            self.locked = False
        def __enter__(self):
            return self.acquire()
        def __exit__(self, exc_type, exc_val, exc_tb):
            self.release()
        def acquire(self, timeout=30):
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    self.lock_file = open(self.lock_file_path, 'w')
                    msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    self.lock_file.write(f"PID: {os.getpid()}\n")
                    self.lock_file.write(f"Time: {time.time()}\n")
                    self.lock_file.flush()
                    self.locked = True
                    print(f"[MT5_GLOBAL_LOCK] Lock acquired by PID {os.getpid()}")
                    return True
                except (IOError, OSError):
                    if self.lock_file:
                        self.lock_file.close()
                        self.lock_file = None
                    print(f"[MT5_GLOBAL_LOCK] Lock held by another process, waiting...")
                    time.sleep(1)
                    continue
            print(f"[MT5_GLOBAL_LOCK] Failed to acquire lock after {timeout}s timeout")
            return False
        def release(self):
            if self.locked and self.lock_file:
                try:
                    msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    self.lock_file.close()
                    if self.lock_file_path.exists():
                        self.lock_file_path.unlink()
                    print(f"[MT5_GLOBAL_LOCK] Lock released by PID {os.getpid()}")
                except Exception as e:
                    print(f"[MT5_GLOBAL_LOCK] Error releasing lock: {e}")
                finally:
                    self.lock_file = None
                    self.locked = False
        def is_locked(self):
            return self.locked