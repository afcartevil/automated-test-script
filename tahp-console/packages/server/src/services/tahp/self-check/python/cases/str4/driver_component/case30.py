"""STR4 驱动器件：抬手亮屏人工测试。"""

import subprocess
import time

SCREEN_OFF_KEYCODE = "223"
WAKE_GESTURE_SETTING = "wake_gesture_enabled"


def _get_dut_device_id(device_info):
    dut_list = (device_info or {}).get("DUT") or []
    if not dut_list:
        return None, "未获取到测试机设备信息"
    dut_id = (dut_list[0].get("device_id") or "").strip()
    if not dut_id:
        return None, "测试机 device_id 为空"
    return dut_id, ""


def _adb_run(device_id: str, *args: str, timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["adb", "-s", device_id, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _go_home(device_id: str) -> bool:
    return _adb_run(device_id, "shell", "input", "keyevent", "3").returncode == 0


def _screen_off(device_id: str) -> bool:
    return _adb_run(
        device_id, "shell", "input", "keyevent", SCREEN_OFF_KEYCODE
    ).returncode == 0


def _get_wake_gesture_enabled(device_id: str) -> tuple[bool, str]:
    ret = _adb_run(device_id, "shell", "settings", "get", "secure", WAKE_GESTURE_SETTING)
    if ret.returncode != 0:
        detail = (ret.stderr or ret.stdout or "").strip()
        return False, detail or "读取 wake_gesture_enabled 失败"
    return True, (ret.stdout or "").strip()


def _is_wake_gesture_enabled(value: str) -> bool:
    return (value or "").strip() == "1"


def _enable_wake_gesture(device_id: str) -> bool:
    return (
        _adb_run(
            device_id,
            "shell",
            "settings",
            "put",
            "secure",
            WAKE_GESTURE_SETTING,
            "1",
        ).returncode
        == 0
    )


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    operator_notify = context.get("operator_notify")
    manual_confirm = context.get("manual_confirm")
    device_info = device_info or context.get("device_info") or {}

    dut_id, error = _get_dut_device_id(device_info)
    if not dut_id:
        if callable(step_update):
            step_update(error)
        return {"status": "fail", "message": error}

    sub_steps = ""

    def update(message: str) -> None:
        if callable(step_update):
            step_update(message)

    def on_step(label: str, ok: bool) -> None:
        nonlocal sub_steps
        sub_steps += f"\n{label}" + ("-成功" if ok else "-失败")
        update(sub_steps)

    read_ok, current_val = _get_wake_gesture_enabled(dut_id)
    on_step("读取抬手亮屏开关", read_ok)
    if not read_ok:
        return {"status": "fail", "message": current_val}

    sub_steps += f"\nwake_gesture_enabled={current_val or '<空>'}"
    update(sub_steps)

    if _is_wake_gesture_enabled(current_val):
        on_step("抬手亮屏已开启", True)
    else:
        enable_ok = _enable_wake_gesture(dut_id)
        on_step("开启抬手亮屏", enable_ok)
        if not enable_ok:
            return {"status": "fail", "message": "开启抬手亮屏失败"}

        verify_ok, verify_val = _get_wake_gesture_enabled(dut_id)
        on_step("校验抬手亮屏已开启", verify_ok and _is_wake_gesture_enabled(verify_val))
        if not verify_ok or not _is_wake_gesture_enabled(verify_val):
            return {
                "status": "fail",
                "message": f"开启后校验失败: {verify_val or '<空>'}",
            }
        sub_steps += f"\n开启后 wake_gesture_enabled={verify_val}"
        update(sub_steps)

    home_ok = _go_home(dut_id)
    on_step("回到桌面", home_ok)
    if not home_ok:
        return {"status": "fail", "message": "回到桌面失败"}

    time.sleep(0.5)

    screen_off_ok = _screen_off(dut_id)
    on_step("灭屏", screen_off_ok)
    if not screen_off_ok:
        return {"status": "fail", "message": "灭屏失败"}

    operation_text = "抬手亮屏已开启，请测试抬手亮屏功能。"
    if callable(operator_notify):
        operator_notify(operation_text)
    sub_steps += f"\n需人工操作：{operation_text}\n需人工评判"
    update(sub_steps)
    if callable(manual_confirm):
        status = manual_confirm("请根据抬手亮屏效果评判本用例是否通过。")
        return {"status": status, "message": f"人工评判{status}"}
    return {"status": "pending", "message": "需人工评判"}
