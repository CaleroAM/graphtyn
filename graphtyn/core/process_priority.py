"""Background priority for long-running Graphtyn processes.

The dashboard and the memory watchers run all day next to the user's own work. They lower their own
priority so the operating system gives them only CPU that nothing else wants. The same code runs on
Linux, macOS and Windows, whatever launched the process (systemd, a scheduled task or a terminal).
On Linux the default I/O priority follows the CPU niceness, so disk access yields too.
"""

from __future__ import annotations

import os
import sys
from typing import Any

BACKGROUND_NICE = 10
WINDOWS_BELOW_NORMAL = 0x00004000
WINDOWS_PRIORITY_NAMES = {0x20: "normal", 0x40: "idle", 0x4000: "below_normal", 0x8000: "above_normal",
                          0x80: "high", 0x100: "realtime"}
MODES = ("low", "normal")
_applied: dict[str, Any] = {}


def priority_mode(value: str | None = None) -> str:
    mode = str(value or os.environ.get("GRAPHTYN_PRIORITY") or "low").strip().casefold()
    if mode not in MODES:
        raise ValueError("GRAPHTYN_PRIORITY debe ser low o normal")
    return mode


def lower_process_priority(mode: str | None = None, *, platform: str | None = None,
                           kernel32: Any = None) -> dict[str, Any]:
    """Lower this process to background priority unless the mode is ``normal``.

    Only an unknown mode raises. A process that cannot change its priority keeps running at the one
    it has, and an already lower one (``nice 19``, idle class) is never raised.
    """
    mode = priority_mode(mode)
    platform = platform or sys.platform
    if mode == "normal":
        result: dict[str, Any] = {"mode": mode, "changed": False}
    elif platform == "win32":
        result = _lower_windows(mode, kernel32)
    else:
        try:
            current = os.nice(0)
            result = ({"mode": mode, "changed": False, "nice": current} if current >= BACKGROUND_NICE
                      else {"mode": mode, "changed": True, "nice": os.nice(BACKGROUND_NICE - current)})
        except (AttributeError, OSError) as exc:
            result = {"mode": mode, "changed": False, "error": f"{type(exc).__name__}: {exc}"}
    _applied.clear(); _applied.update(result)
    return result


def current_priority() -> str | None:
    """The mode this process applied at start ("low" or "normal"), or None if it never did."""
    return _applied.get("mode")


def windows_kernel32() -> Any:
    """kernel32 with typed prototypes, in a private handle so global ``ctypes.windll`` is untouched.

    Untyped, ctypes passes the pseudo-handle of ``GetCurrentProcess`` (-1, 64 bits) as a 32-bit int
    and every call fails with an invalid handle.
    """
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetPriorityClass.argtypes = [wintypes.HANDLE]
    kernel32.GetPriorityClass.restype = wintypes.DWORD
    kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.SetPriorityClass.restype = wintypes.BOOL
    return kernel32


def _lower_windows(mode: str, kernel32: Any) -> dict[str, Any]:
    try:
        kernel32 = kernel32 or windows_kernel32()
        process = kernel32.GetCurrentProcess()
        current = int(kernel32.GetPriorityClass(process))
        if not current:
            return {"mode": mode, "changed": False, "error": "GetPriorityClass falló"}
        if current in (WINDOWS_BELOW_NORMAL, 0x40):
            return {"mode": mode, "changed": False, "priority_class": WINDOWS_PRIORITY_NAMES[current]}
        if not kernel32.SetPriorityClass(process, WINDOWS_BELOW_NORMAL):
            return {"mode": mode, "changed": False, "error": "SetPriorityClass rechazado"}
        return {"mode": mode, "changed": True, "priority_class": "below_normal"}
    except (AttributeError, ImportError, OSError) as exc:
        return {"mode": mode, "changed": False, "error": f"{type(exc).__name__}: {exc}"}
