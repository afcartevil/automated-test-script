"""驱动周版本自检：亮灭屏后 TP 触摸报点检测（getevent -ltr，5 轮）。"""

import subprocess

from utils.driver.tp_touch import (
    POWER_CYCLE_COUNT,
    USER_SWIPE_TIMEOUT_SEC,
    check_tp_touch_after_power_cycles,
)


def _go_home(device_id: str) -> bool:
    r = subprocess.run(
        ["adb", "-s", device_id, "shell", "input", "keyevent", "3"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return r.returncode == 0


def _get_dut_device_id(device_info):
    dut_list = (device_info or {}).get("DUT") or []
    if not dut_list:
        return None, "未获取到测试机设备信息"
    dut_id = (dut_list[0].get("device_id") or "").strip()
    if not dut_id:
        return None, "测试机 device_id 为空"
    return dut_id, ""


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    operator_notify = context.get("operator_notify")
    device_info = device_info or context.get("device_info") or {}

    dut_id, error = _get_dut_device_id(device_info)
    if not dut_id:
        if callable(step_update):
            step_update(error)
        return {"status": "fail", "message": error}

    sub_steps = ""

    def on_step(label: str, ok: bool) -> None:
        nonlocal sub_steps
        sub_steps += f"\n{label}" + ("-成功" if ok else "-失败")
        if callable(step_update):
            step_update(sub_steps)

    ok = _go_home(dut_id)
    on_step("回到主界面", ok)

    def before_cycles():
        wait_sec = int(USER_SWIPE_TIMEOUT_SEC)
        notify_text = (
            f"接下来将进行 {POWER_CYCLE_COUNT} 次亮灭屏测试。\n"
            f"每次亮屏后请在 {wait_sec} 秒内滑动屏幕，以检测触摸报点。\n"
            "点击「知道了」后开始测试。"
        )
        if callable(operator_notify):
            operator_notify(notify_text)
            return
        nonlocal sub_steps
        sub_steps += f"\n{notify_text}"
        if callable(step_update):
            step_update(sub_steps)

    result = check_tp_touch_after_power_cycles(
        dut_id,
        result_dir=context.get("result_dir"),
        on_step=on_step,
        before_cycles=before_cycles,
    )
    return {"status": result["status"], "message": result["message"]}
