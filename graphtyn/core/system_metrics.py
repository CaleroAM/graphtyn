"""Portable process and host-memory measurements used by benchmarks."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _windows_memory() -> tuple[int, int, int | None]:
    try:
        import ctypes
        from ctypes import wintypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", wintypes.DWORD), ("load", wintypes.DWORD),
                ("total_physical", ctypes.c_ulonglong), ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong), ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        class ProcessMemory(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD), ("page_faults", wintypes.DWORD),
                ("peak_working_set", ctypes.c_size_t), ("working_set", ctypes.c_size_t),
                ("peak_paged_pool", ctypes.c_size_t), ("paged_pool", ctypes.c_size_t),
                ("peak_nonpaged_pool", ctypes.c_size_t), ("nonpaged_pool", ctypes.c_size_t),
                ("pagefile", ctypes.c_size_t), ("peak_pagefile", ctypes.c_size_t),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return 0, 0, None
        counters = ProcessMemory()
        counters.cb = ctypes.sizeof(counters)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        measured = ctypes.windll.psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        )
        return int(status.total_physical), int(status.available_physical), (
            int(counters.peak_working_set) if measured else None
        )
    except (AttributeError, ImportError, OSError, TypeError, ValueError):
        return 0, 0, None


def memory_info() -> dict[str, int]:
    """Return physical memory totals without assuming Linux ``/proc``."""
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            values[key] = int(raw.strip().split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    if values:
        return {"total_bytes": values.get("MemTotal", 0), "available_bytes": values.get("MemAvailable", 0)}
    if sys.platform == "win32":
        total, available, _peak = _windows_memory()
        return {"total_bytes": total, "available_bytes": available}
    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        return {
            "total_bytes": page_size * int(os.sysconf("SC_PHYS_PAGES")),
            "available_bytes": page_size * int(os.sysconf("SC_AVPHYS_PAGES")),
        }
    except (AttributeError, OSError, TypeError, ValueError):
        return {"total_bytes": 0, "available_bytes": 0}


def peak_rss_bytes() -> int | None:
    """Return peak resident memory, lazily using platform-specific APIs."""
    if sys.platform == "win32":
        return _windows_memory()[2]
    try:
        import resource
    except (ImportError, ModuleNotFoundError):
        return None
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return peak if sys.platform == "darwin" else peak * 1024
