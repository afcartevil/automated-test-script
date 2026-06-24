"""驱动周版本自检：TP 触摸报点检测（getevent -ltr）。"""

import subprocess

from utils.driver.tp_touch import check_tp_touch_reporting


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

    def before_parse():
        notify_text = (
            "模拟屏幕滑动已成功。\n"
            "点击「知道了」后，请滑动两下屏幕，脚本将解析触摸报点。"
        )
        if callable(operator_notify):
            operator_notify(notify_text)
            return
        nonlocal sub_steps
        sub_steps += f"\n{notify_text}"
        if callable(step_update):
            step_update(sub_steps)

    result = check_tp_touch_reporting(
        dut_id,
        result_dir=context.get("result_dir"),
        on_step=on_step,
        before_parse=before_parse,
    )
    return {"status": result["status"], "message": result["message"]}
