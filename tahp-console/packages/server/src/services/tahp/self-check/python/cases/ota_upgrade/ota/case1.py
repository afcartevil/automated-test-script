from __future__ import annotations

import subprocess
import time


BOOT_WAIT_SECONDS = 300
BOOT_POLL_INTERVAL = 3


def _device_serial(device_info: dict) -> str:
    dut = device_info.get("DUT") if isinstance(device_info, dict) else None
    if isinstance(dut, list) and dut:
        serial = dut[0].get("device_id") or dut[0].get("deviceId")
        if serial:
            return str(serial)
    if isinstance(device_info, dict):
        serial = device_info.get("deviceId") or device_info.get("device_id")
        if serial:
            return str(serial)
    raise ValueError("缺少测试机设备序列号")


def _adb_shell(serial: str, command: str, timeout: int = 20) -> str:
    result = subprocess.run(
        ["adb", "-s", serial, "shell", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return (result.stdout or result.stderr or "").strip()


def _getprop(serial: str, name: str) -> str:
    return _adb_shell(serial, f"getprop {name}")


def _is_boot_completed(serial: str) -> bool:
    boot = _getprop(serial, "sys.boot_completed")
    complete = _getprop(serial, "dev.bootcomplete")
    return boot == "1" or complete == "1"


def run(device_info=None, step_update=None, **_context):
    serial = _device_serial(device_info or {})
    steps: list[str] = []

    def add_step(text: str) -> None:
        steps.append(text)
        if step_update:
            step_update("\n".join(steps))

    add_step(f"连续OTA升级后校验设备开机，序列号: {serial}")
    deadline = time.time() + BOOT_WAIT_SECONDS
    while time.time() < deadline:
        try:
            if _is_boot_completed(serial):
                add_step("sys.boot_completed=1-成功")
                break
        except subprocess.TimeoutExpired:
            add_step("等待开机时 adb 超时，继续重试")
        time.sleep(BOOT_POLL_INTERVAL)
    else:
        add_step("等待系统开机超时-失败")
        return {
            "status": "fail",
            "message": f"连续OTA升级后设备未在 {BOOT_WAIT_SECONDS}s 内完成开机",
            "full_automation": True,
        }

    release = _getprop(serial, "ro.build.version.release") or "未知"
    display = _getprop(serial, "ro.build.display.id") or "未知"
    add_step(f"当前 Android {release}，display={display}-成功")
    return {
        "status": "pass",
        "message": f"连续OTA升级完成，Android {release}，{display}",
        "full_automation": True,
    }
