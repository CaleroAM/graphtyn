import os
import subprocess
import sys

import pytest

from graphtyn.core import deployment
from graphtyn.core.process_priority import (BACKGROUND_NICE, WINDOWS_BELOW_NORMAL, current_priority,
                                            lower_process_priority, priority_mode)


class FakeKernel32:
    def __init__(self, current=0x20, accept=True):
        self.current, self.accept, self.calls = current, accept, []

    def GetCurrentProcess(self):
        return -1

    def GetPriorityClass(self, process):
        return self.current

    def SetPriorityClass(self, process, value):
        self.calls.append(value)
        if self.accept:
            self.current = value
        return int(self.accept)


def test_mode_comes_from_argument_then_environment(monkeypatch):
    monkeypatch.delenv("GRAPHTYN_PRIORITY", raising=False)
    assert priority_mode() == "low"
    monkeypatch.setenv("GRAPHTYN_PRIORITY", "Normal")
    assert priority_mode() == "normal"
    assert priority_mode("low") == "low"
    with pytest.raises(ValueError):
        priority_mode("high")


def test_normal_mode_leaves_the_process_alone():
    kernel = FakeKernel32()
    assert lower_process_priority("normal", platform="win32", kernel32=kernel)["changed"] is False
    assert kernel.calls == []
    assert current_priority() == "normal"


def test_windows_drops_to_below_normal_once():
    kernel = FakeKernel32()
    result = lower_process_priority("low", platform="win32", kernel32=kernel)
    assert result == {"mode": "low", "changed": True, "priority_class": "below_normal"}
    assert kernel.calls == [WINDOWS_BELOW_NORMAL]
    assert current_priority() == "low"


@pytest.mark.parametrize("already", [WINDOWS_BELOW_NORMAL, 0x40])
def test_windows_never_raises_a_lower_class(already):
    kernel = FakeKernel32(current=already)
    assert lower_process_priority("low", platform="win32", kernel32=kernel)["changed"] is False
    assert kernel.calls == []


def test_windows_refusal_keeps_running():
    result = lower_process_priority("low", platform="win32", kernel32=FakeKernel32(accept=False))
    assert result["changed"] is False and "rechazado" in result["error"]


@pytest.mark.skipif(not hasattr(os, "nice"), reason="POSIX niceness")
def test_posix_child_ends_at_background_niceness_and_never_rises():
    code = ("import os; from graphtyn.core.process_priority import lower_process_priority as l; "
            "a = l('low'); os.nice(5); b = l('low'); print(a['nice'], b['changed'], os.nice(0))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                         env={**os.environ, "GRAPHTYN_PRIORITY": "low"}).stdout.split()
    low = max(os.nice(0), BACKGROUND_NICE)
    assert out == [str(low), "False", str(min(low + 5, 19))]


@pytest.mark.skipif(sys.platform != "win32", reason="real Windows priority classes")
def test_real_windows_process_reaches_below_normal():
    code = ("import ctypes; from graphtyn.core.process_priority import lower_process_priority as l; "
            "r = l('low'); k = ctypes.windll.kernel32; print(r['changed'], k.GetPriorityClass(k.GetCurrentProcess()))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                         env={**os.environ, "GRAPHTYN_PRIORITY": "low"}).stdout.split()
    assert out == ["True", str(WINDOWS_BELOW_NORMAL)]


def test_generated_systemd_unit_yields_cpu_and_disk(tmp_path):
    unit = deployment.service_artifact(tmp_path, kind="systemd", output=tmp_path / "graphtyn-dashboard.service")
    text = unit.read_text(encoding="utf-8")
    assert "CPUWeight=20\n" in text and "IOWeight=20\n" in text and "CPUQuota" not in text
