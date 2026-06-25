"""驱动周版本自检：TP 双击亮灭屏检测。"""

from utils.driver.tp_tapping_wake import USER_DOUBLE_TAP_WAIT_SEC, run_tp_tapping_wake_test


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

    def before_double_tap():
        wait_sec = int(USER_DOUBLE_TAP_WAIT_SEC)
        notify_text = (
            f"测试机已灭屏，点击「知道了」后，在 {wait_sec} 秒内双击屏幕亮屏。"
        )
        if callable(operator_notify):
            operator_notify(notify_text)
            on_step(f"请在 {wait_sec} 秒内双击屏幕亮屏", True)
            return
        nonlocal sub_steps
        sub_steps += f"\n请在 {wait_sec} 秒内双击屏幕亮屏"
        if callable(step_update):
            step_update(sub_steps)

    result = run_tp_tapping_wake_test(
        dut_id,
        result_dir=context.get("result_dir"),
        on_step=on_step,
        before_double_tap=before_double_tap,
    )
    return {"status": result["status"], "message": result["message"]}
