"""STR4 驱动器件：乘车模式导入（QSensorTest 检测 vehicle: vehicle: transsion）。"""

from utils.driver.qsensor_mode_check import (
    VEHICLE_MODE_MARKER,
    VEHICLE_MODE_SUPPORT_PROP,
    run_qsensor_mode_import_check,
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
    manual_confirm = context.get("manual_confirm")
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

    def append_note(note: str) -> None:
        nonlocal sub_steps
        sub_steps += f"\n{note}"
        if callable(step_update):
            step_update(sub_steps)

    return run_qsensor_mode_import_check(
        dut_id,
        marker=VEHICLE_MODE_MARKER,
        mode_label="乘车模式",
        support_prop=VEHICLE_MODE_SUPPORT_PROP,
        on_step=on_step,
        append_note=append_note,
        manual_confirm=manual_confirm,
    )
