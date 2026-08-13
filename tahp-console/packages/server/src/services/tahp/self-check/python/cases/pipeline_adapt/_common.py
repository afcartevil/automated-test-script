"""pipeline_adapt 各模块共用：设备序列号与 adb 辅助。"""

from __future__ import annotations

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
    """尝试 adb root；成功 (True, 说明)，失败 (False, 原因)。"""
    ret = adb_run(device_id, "root", timeout=45)
    msg = f"{(ret.stdout or '').strip()}\n{(ret.stderr or '').strip()}".strip()
    low = msg.lower()
    if "cannot run as root" in low or "adbd cannot run as root" in low:
        return False, msg or "adbd cannot run as root"
    if (
        ret.returncode != 0
        and "restarting adbd as root" not in low
        and "already running as root" not in low
    ):
        return False, msg or f"adb root exit {ret.returncode}"
    time.sleep(3)
    adb_run(device_id, "wait-for-device", timeout=60)
    time.sleep(1)
    return True, msg or "adb root ok"


def emit(step_update: StepFn | None, steps: list[str], line: str) -> None:
    steps.append(line)
    if callable(step_update):
        step_update("\n".join(steps))
