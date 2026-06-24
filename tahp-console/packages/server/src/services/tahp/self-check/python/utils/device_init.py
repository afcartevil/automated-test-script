"""设备初始化工具。"""

import subprocess
import time


def _adb(device_id: str, *args: str) -> str:
    """执行 ADB 命令（UTF-8，忽略编码错误）。"""
    r = subprocess.run(
        ["adb", "-s", device_id, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    return r.stdout.strip()


def wakeup_and_unlock(device_id: str) -> None:
    """唤醒屏幕并滑动解锁。"""
    try:
        _adb(device_id, "shell", "input", "keyevent", "KEYCODE_WAKEUP")
        time.sleep(0.5)
        _adb(device_id, "shell", "input", "keyevent", "KEYCODE_MENU")
        time.sleep(0.3)
        _adb(device_id, "shell", "input", "swipe", "540", "1800", "540", "500")
        time.sleep(0.5)
        print(f"[init] {device_id} 亮屏解锁完成")
    except Exception as e:
        print(f"[init] {device_id} 亮屏解锁失败（非致命）: {e}")


def set_screen_timeout(device_id: str, timeout_ms: int = 1800000) -> None:
    """设置亮屏时间（默认30分钟）。"""
    try:
        _adb(device_id, "shell", "settings", "put", "system", "screen_off_timeout", str(timeout_ms))
        print(f"[init] {device_id} 亮屏时间已设为 {timeout_ms // 60000} 分钟")
    except Exception as e:
        print(f"[init] {device_id} 设置亮屏时间失败（非致命）: {e}")


def init_devices_for_test(device_info: dict) -> None:
    """模块初始化：亮屏解锁所有测试设备。"""
    for dut in device_info.get("DUT", []):
        device_id = dut.get("device_id")
        if device_id:
            wakeup_and_unlock(device_id)
    for aux in device_info.get("Auxiliary", []):
        device_id = aux.get("device_id")
        if device_id:
            wakeup_and_unlock(device_id)