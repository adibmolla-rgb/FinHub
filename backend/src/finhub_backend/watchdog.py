"""Exit the backend when the desktop app that started it is gone, even if the app crashed.

The app passes its process id in FINHUB_PARENT_PID. Without this, a force-quit or crash would leave an
orphaned backend running in the background.
"""

from __future__ import annotations

import os
import sys
import threading
import time


def _alive(pid: int) -> bool:
    if sys.platform == "win32":
        # os.kill() on Windows terminates the process, so query it through the Win32 API instead.
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def start(interval: float = 1.0) -> None:
    raw = os.environ.get("FINHUB_PARENT_PID")
    if not raw:
        return  # started by hand, not by the app
    pid = int(raw)

    def watch() -> None:
        while _alive(pid):
            time.sleep(interval)
        os._exit(0)

    threading.Thread(target=watch, name="parent-watchdog", daemon=True).start()
