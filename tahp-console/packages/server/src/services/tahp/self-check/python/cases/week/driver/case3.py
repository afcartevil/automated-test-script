"""驱动周版本自检：TP 触摸报点检测（getevent -ltr）。"""

from utils.driver.tp_touch import (
    GETEVENT_COLLECT_SEC,
    check_tp_touch_reporting,
    go_home,
)


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

    def before_parse():
        wait_sec = int(GETEVENT_COLLECT_SEC)
        notify_text = (
            f"点击「知道了」后，请在 {wait_sec} 秒内手动触摸屏幕（建议滑动 2 次），"
            "脚本将采集触摸报点。"
        )
        if callable(operator_notify):
            operator_notify(notify_text)
            return
        nonlocal sub_steps
        sub_steps += f"\n{notify_text}"
        if callable(step_update):
            step_update(sub_steps)

    home_ok = go_home(dut_id)
    on_step("返回主界面", home_ok)
    if not home_ok:
        return {"status": "fail", "message": "返回主界面失败"}

    result = check_tp_touch_reporting(
        dut_id,
        result_dir=context.get("result_dir"),
        on_step=on_step,
        before_parse=before_parse,
    )
    return {"status": result["status"], "message": result["message"]}
