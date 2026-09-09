"""pipeline_adapt 各模块共用：设备序列号与 adb 辅助。"""

from __future__ import annotations

import re
import subprocess
import time
from typing import Callable

StepFn = Callable[[str], None]


def get_dut_device_id(device_info) -> tuple[str | None, str]:
    dut = (device_info or {}).get("DUT") or []
    if not dut:
        return None, "未获取到测试机设备信息"
    serial = (dut[0].get("device_id") or dut[0].get("deviceId") or "").strip()
    return (serial, "") if serial else (None, "测试机 device_id 为空")


def adb_run(device_id: str, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["adb", "-s", device_id, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def adb_shell(device_id: str, command: str, *, timeout: int = 30) -> str:
    ret = adb_run(device_id, "shell", command, timeout=timeout)
    out = (ret.stdout or "").strip()
    return out or (ret.stderr or "").strip()


def adb_cat(device_id: str, path: str, *, timeout: int = 15) -> str:
    return adb_shell(device_id, f"cat {path} 2>/dev/null", timeout=timeout)


def try_adb_root(device_id: str) -> tuple[bool, str]:
    """尝试 adb root；已是 root 时立刻返回，避免无谓等待。"""
    ret = adb_run(device_id, "root", timeout=15)
    msg = f"{(ret.stdout or '').strip()}\n{(ret.stderr or '').strip()}".strip()
    low = msg.lower()
    if "cannot run as root" in low or "adbd cannot run as root" in low:
        return False, msg or "adbd cannot run as root"
    if "already running as root" in low:
        return True, msg or "already running as root"
    if (
        ret.returncode != 0
        and "restarting adbd as root" not in low
    ):
        return False, msg or f"adb root exit {ret.returncode}"
    time.sleep(1.5)
    adb_run(device_id, "wait-for-device", timeout=30)
    return True, msg or "adb root ok"


def try_adb_unroot(device_id: str) -> tuple[bool, str]:
    """尝试 adb unroot；已是非 root 时立刻返回。settings put 需在非 root 下执行。"""
    ret = adb_run(device_id, "unroot", timeout=15)
    msg = f"{(ret.stdout or '').strip()}\n{(ret.stderr or '').strip()}".strip()
    low = msg.lower()
    if "not running as root" in low and "restarting" not in low:
        return True, msg or "adbd not running as root"
    if ret.returncode != 0 and "restarting adbd" not in low:
        return False, msg or f"adb unroot exit {ret.returncode}"
    time.sleep(1.5)
    adb_run(device_id, "wait-for-device", timeout=30)
    return True, msg or "adb unroot ok"


def emit(step_update: StepFn | None, steps: list[str], line: str) -> None:
    steps.append(line)
    if callable(step_update):
        step_update("\n".join(steps))


def get_screen_size(device_id: str) -> tuple[int, int] | None:
    out = adb_shell(device_id, "wm size")
    override = re.search(r"Override size:\s*(\d+)x(\d+)", out)
    if override:
        return int(override.group(1)), int(override.group(2))
    physical = re.search(r"Physical size:\s*(\d+)x(\d+)", out)
    if physical:
        return int(physical.group(1)), int(physical.group(2))
    return None


def input_swipe(
    device_id: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration_ms: int = 350,
) -> bool:
    ret = adb_run(
        device_id,
        "shell",
        "input",
        "swipe",
        str(x1),
        str(y1),
        str(x2),
        str(y2),
        str(duration_ms),
    )
    return ret.returncode == 0


def swipe_back_gesture(device_id: str, *, from_right: bool = False) -> bool:
    """从屏幕左/右边缘向内滑动，模拟系统返回手势。"""
    size = get_screen_size(device_id)
    if not size:
        return False
    width, height = size
    y = max(1, height // 2)
    if from_right:
        x0, x1 = max(width - 8, int(width * 0.99)), int(width * 0.65)
    else:
        x0, x1 = max(8, int(width * 0.01)), int(width * 0.35)
    return input_swipe(device_id, x0, y, x1, y, 350)


def open_settings(device_id: str) -> bool:
    adb_run(device_id, "shell", "am", "force-stop", "com.android.settings", timeout=10)
    time.sleep(0.3)
    ret = adb_run(device_id, "shell", "am", "start", "-a", "android.settings.SETTINGS")
    out = f"{ret.stdout or ''}{ret.stderr or ''}"
    if ret.returncode == 0 and "Error" not in out:
        return True
    monkey = adb_run(
        device_id,
        "shell",
        "monkey",
        "-p",
        "com.android.settings",
        "-c",
        "android.intent.category.LAUNCHER",
        "1",
        timeout=20,
    )
    return monkey.returncode == 0
