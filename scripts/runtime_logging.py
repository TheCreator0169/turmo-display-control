import sys
import os
import traceback
import threading
import subprocess
import time
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

# ============================================================================
# CENTRALIZED RUNTIME LOGGING - Captures all exceptions, callbacks, worker output
# ============================================================================

_RUNTIME_LOG_FILE: Optional[Path] = None
_RUNTIME_LOG_LOCK = threading.Lock()
_ENABLED = True  # v0.3.5: Settings > Logs > "Write logs"; applies once the settings are read (the first start-up lines are still written)


def set_enabled(on: bool) -> None:
    global _ENABLED
    _ENABLED = bool(on)


def is_enabled() -> bool:
    return _ENABLED


def init_runtime_log() -> Path:
    """Initialize persistent runtime log under %LOCALAPPDATA%\\TURMO\\logs\\"""
    folder = log_dir()
    folder.mkdir(parents=True, exist_ok=True)
    log_file = folder / f"runtime_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    global _RUNTIME_LOG_FILE
    _RUNTIME_LOG_FILE = log_file
    return log_file

def log_runtime(component: str, event: str, message: str = "", exc: Optional[Exception] = None, level: str = "INFO", **kwargs):
    """Write a runtime diagnostic entry with timestamp, PID, thread, component, event."""
    global _RUNTIME_LOG_FILE
    if not _ENABLED:
        return
    if _RUNTIME_LOG_FILE is None:
        init_runtime_log()
    assert _RUNTIME_LOG_FILE is not None
    
    try:
        pid = os.getpid()
        thread_name = threading.current_thread().name
        thread_id = threading.get_ident()
        frozen = getattr(sys, 'frozen', False)
        
        lines = [
            f"[{datetime.now().isoformat()}] [{level}] PID={pid} TID={thread_id} Thread={thread_name} Component={component} Event={event}",
            f"  Frozen: {frozen} | Python: {sys.version.split()[0]}",
            f"  {message}",
        ]
        
        if kwargs:
            for k, v in kwargs.items():
                lines.append(f"  {k}: {v}")
        
        if exc:
            lines.append(f"  EXCEPTION: {type(exc).__name__}: {exc}")
            lines.append(f"  TRACEBACK: {''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))}")
        
        with _RUNTIME_LOG_LOCK:
            _continue_in_new_file_if_full()
            with open(_RUNTIME_LOG_FILE, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n\n")
    except Exception:
        # Never let logging failures crash the app
        pass

def _continue_in_new_file_if_full():
    """A runtime log past RUNTIME_LOG_MAX_BYTES goes on in a new file (the caller holds the lock)."""
    global _RUNTIME_LOG_FILE
    try:
        if _RUNTIME_LOG_FILE.stat().st_size <= RUNTIME_LOG_MAX_BYTES:
            return
        stamp, n = datetime.now().strftime('%Y%m%d_%H%M%S'), 1
        path = _RUNTIME_LOG_FILE.with_name(f"runtime_{stamp}.log")
        while path.exists():
            n += 1
            path = _RUNTIME_LOG_FILE.with_name(f"runtime_{stamp}_{n}.log")
        _RUNTIME_LOG_FILE = path
    except OSError:
        pass  # no file yet, or it cannot be read: keep writing to the same name

def log_exception(component: str, event: str, exc: Exception, **kwargs):
    """Convenience: log an exception with ERROR level."""
    log_runtime(component, event, f"Exception: {exc}", exc=exc, level="ERROR", **kwargs)

def log_callback(component: str, callback_name: str, **kwargs):
    """Convenience: log a GUI callback invocation."""
    log_runtime(component, f"CALLBACK_{callback_name}", "GUI callback invoked", level="DEBUG", **kwargs)

def log_worker_start(component: str, cmd: list, **kwargs):
    """Convenience: log worker process start."""
    log_runtime(component, "WORKER_START", f"Starting worker: {' '.join(map(str, cmd))}", level="INFO", command=cmd, **kwargs)

def log_worker_result(component: str, cmd: list, returncode: int, stdout: str = "", stderr: str = "", **kwargs):
    """Convenience: log worker process result."""
    log_runtime(component, "WORKER_RESULT", f"Worker exited with code {returncode}", level="INFO", 
                command=cmd, returncode=returncode, 
                stdout_tail=stdout[-2000:] if stdout else "",
                stderr_tail=stderr[-2000:] if stderr else "", **kwargs)

def log_com_error(component: str, operation: str, port: str, error: Exception, **kwargs):
    """Convenience: log COM port errors."""
    log_runtime(component, "COM_ERROR", f"COM error during {operation} on {port}: {error}", exc=error, level="ERROR", port=port, operation=operation, **kwargs)

def get_runtime_log_path() -> Optional[Path]:
    """Get the current runtime log file path."""
    return _RUNTIME_LOG_FILE

# ============================================================================
# LOG REGULATOR (v0.3.0): the logs folder stays small, nothing else is ever touched
# ============================================================================

KEEP_DAYS_CHOICES = (1, 3, 7, 14, 30)  # Settings > Logs
MAX_MB_CHOICES = (10, 20, 50, 100)
RUNTIME_LOG_MAX_BYTES = 2 * 1024 * 1024  # a runtime log that grows past this continues in a new file
STARTUP_LOG_MAX_BYTES = 1024 * 1024      # startup.log is renamed startup.1.log, then startup.2.log, when it passes this
_OWN_LOG = re.compile(r"^((runtime|lifecycle)_\d{8}_\d{6}(_\d+)?|startup(_\d{8}_\d{6})?(\.\d)?)\.log$")
_ERROR_MARKS = ("[ERROR]", "[CRITICAL]", "EXCEPTION:")


def valid_choice(value, choices, default):
    """`value` when it is one of `choices` (a whole number, not a bool), else `default`: a hand-edited settings.json
    may hold anything, and the window and the sweep must read it the same way."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value in choices else default


def log_dir() -> Path:
    if sys.platform == "win32":
        localappdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
    else:
        localappdata = os.path.expanduser("~/.local/share")
    return Path(localappdata) / "TURMO" / "logs"


def _own_logs(directory):
    """(kind, path, size, mtime) of TURMO's own log files in `directory`: regular files only (a link is never
    followed), and only names this module writes. Anything else in the folder is not ours and is left alone."""
    found = []
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                try:
                    if _OWN_LOG.match(entry.name) and entry.is_file(follow_symlinks=False):
                        info = entry.stat(follow_symlinks=False)
                        kind = re.match(r"[a-z]+", entry.name).group(0)  # runtime, startup or lifecycle
                        found.append((kind, Path(entry.path), info.st_size, info.st_mtime))
                except OSError:
                    continue
    except OSError:
        pass
    return found


def log_folder_stats(directory=None):
    """(number of files, bytes) of TURMO's own logs, for Settings > Logs."""
    files = _own_logs(directory or log_dir())
    return len(files), sum(f[2] for f in files)


def _has_error(path) -> bool:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return False
    return any(mark in text for mark in _ERROR_MARKS)


def sweep_logs(directory=None, keep_days=7, max_mb=20, now=None):
    """Delete the old logs: older than `keep_days`, then the oldest first while the folder is over `max_mb`.
    Always kept: the newest log of each kind, and the newest log of each kind that holds an error (so the last crash
    is never erased, even when it is old). Returns (files removed, bytes removed); a file that cannot be removed
    (in use) is skipped. Never raises."""
    keep_days = valid_choice(keep_days, KEEP_DAYS_CHOICES, 7)
    max_mb = valid_choice(max_mb, MAX_MB_CHOICES, 20)
    now = time.time() if now is None else now
    files = sorted(_own_logs(directory or log_dir()), key=lambda f: f[3], reverse=True)  # newest first
    newest = {}
    for item in files:
        newest.setdefault(item[0], item)
    spared = set(item[1] for item in newest.values())
    for kind in newest:  # the newest log of each kind that holds an error survives, whatever its age
        for item in (f for f in files if f[0] == kind and f[1] not in spared):
            if _has_error(item[1]):
                spared.add(item[1])
                break
    doomed = [f for f in files if f[1] not in spared and now - f[3] > keep_days * 86400]
    left = sum(f[2] for f in files) - sum(f[2] for f in doomed)
    for item in reversed(files):  # oldest first
        if left <= max_mb * 1024 * 1024:
            break
        if item[1] not in spared and item not in doomed:
            doomed.append(item)
            left -= item[2]
    removed = size = 0
    for _kind, path, nbytes, _mtime in doomed:
        try:
            os.remove(path)
            removed += 1
            size += nbytes
        except OSError:
            continue
    if removed:
        log_runtime("LOGS", "SWEEP", f"removed {removed} files, {size / 1048576:.1f} MB (keep {keep_days} days, cap {max_mb} MB)")
    return removed, size


def rotate_startup_log(path, max_bytes=STARTUP_LOG_MAX_BYTES):
    """startup.log -> startup.1.log -> startup.2.log (the oldest is dropped) once the file passes `max_bytes`."""
    try:
        path = Path(path)
        if path.stat().st_size <= max_bytes:
            return
        first, second = path.with_name("startup.1.log"), path.with_name("startup.2.log")
        if first.exists():
            os.replace(first, second)
        os.replace(path, first)
    except OSError:
        pass  # a missing file is nothing to rotate; a locked one is tried again at the next start

# ============================================================================
# THREAD EXCEPTION HOOK - Captures unhandled exceptions in all threads
# ============================================================================

_original_excepthook = sys.excepthook

def _runtime_excepthook(exc_type, exc_value: BaseException, exc_traceback):
    """Global exception hook - captures all unhandled exceptions."""
    log_runtime("SYSTEM", "UNHANDLED_EXCEPTION", 
                f"Unhandled exception in {threading.current_thread().name}",
                exc=exc_value if isinstance(exc_value, Exception) else Exception(str(exc_value)), level="CRITICAL")
    _original_excepthook(exc_type, exc_value, exc_traceback)

sys.excepthook = _runtime_excepthook

_thread_hook_installed = False

def install_thread_excepthook():
    """Install exception hook for threading.Thread.run(). Idempotent — safe to call multiple times."""
    global _thread_hook_installed
    if _thread_hook_installed:
        return
    _thread_hook_installed = True
    original_run = threading.Thread.run
    def wrapped_run(self):
        try:
            original_run(self)
        except Exception as e:
            log_runtime("SYSTEM", "THREAD_EXCEPTION", 
                        f"Uncaught exception in thread {self.name}",
                        exc=e, level="CRITICAL")
            raise
    threading.Thread.run = wrapped_run

# ============================================================================
# TKINTER CALLBACK WRAPPER - Captures exceptions in GUI callbacks
# ============================================================================

def safe_callback(callback, component: str = "GUI", callback_name: str = "unknown"):
    """Wrap a tkinter callback to catch exceptions and log them."""
    def wrapper(*args, **kwargs):
        try:
            log_callback(component, callback_name, args_count=len(args), kwargs_keys=list(kwargs.keys()))
            return callback(*args, **kwargs)
        except Exception as e:
            log_exception(component, f"CALLBACK_{callback_name}", e, args_count=len(args), kwargs_keys=list(kwargs.keys()))
            # Show error to user but don't crash
            try:
                import tkinter.messagebox as mb
                mb.showerror("TURMO Error", f"{callback_name} failed: {e}\n\nCheck logs at {get_runtime_log_path()}")
            except:
                pass
            raise
    return wrapper

# ============================================================================
# SUBPROCESS WRAPPER - Captures worker stdout/stderr and return codes
# ============================================================================

def run_worker(cmd: list, component: str = "WORKER", timeout: Optional[float] = None, **popen_kwargs) -> subprocess.CompletedProcess:
    """Run a worker process with full logging of stdout/stderr/returncode."""
    log_worker_start(component, cmd)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **popen_kwargs)
        log_worker_result(component, cmd, result.returncode, result.stdout or "", result.stderr or "")
        return result
    except subprocess.TimeoutExpired as e:
        log_runtime(component, "WORKER_TIMEOUT", f"Worker timed out after {timeout}s", exc=e, level="ERROR", command=cmd)
        raise
    except Exception as e:
        log_runtime(component, "WORKER_ERROR", f"Worker failed to start", exc=e, level="ERROR", command=cmd)
        raise

def popen_worker(cmd: list, component: str = "WORKER", **popen_kwargs) -> subprocess.Popen:
    """Start a worker process with logging."""
    log_worker_start(component, cmd)
    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
        log_runtime(component, "WORKER_POPEN", f"Started worker PID {proc.pid}", level="INFO", command=cmd, pid=proc.pid)
        return proc
    except Exception as e:
        log_runtime(component, "WORKER_POPEN_ERROR", f"Failed to start worker", exc=e, level="ERROR", command=cmd)
        raise

# ============================================================================
# SELF-TEST
# ============================================================================

if __name__ == "__main__":
    # Test the logging system
    init_runtime_log()
    install_thread_excepthook()
    
    log_runtime("TEST", "INIT", "Runtime logging initialized")
    log_callback("TEST", "on_button_click", button="test_btn")
    log_worker_start("TEST", ["echo", "hello"])
    log_worker_result("TEST", ["echo", "hello"], 0, "hello\n", "")
    log_com_error("TEST", "open", "COM4", Exception("Access denied"))
    
    # Test exception capture
    try:
        raise ValueError("test error")
    except Exception as e:
        log_exception("TEST", "MANUAL_TEST", e, extra_data="test")
    
    print(f"Runtime log written to: {get_runtime_log_path()}")
    print("Check the log file for entries.")