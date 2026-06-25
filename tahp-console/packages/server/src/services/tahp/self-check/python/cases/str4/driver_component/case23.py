"""STR4 驱动器件：加速度功能（工模加速度测试）。"""

from utils.driver.tranfacmode_config import (
    ACCELEROMETER_GROUP_ITEM_SPECS,
    ACCELEROMETER_GROUP_LABEL,
    SENSOR,
)
from utils.driver.ui_tranfacmode import run_tranfacmode_group_items_test


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

    def prompt_accelerometer_calibration():
        nonlocal sub_steps
        operation_text = "请在 Sensor 工模列表中点击加速度校准项，并按界面提示完成校准。"
        if callable(operator_notify):
            operator_notify(operation_text)
        sub_steps += f"\n需人工操作：{operation_text}\n需人工确认"
        update(sub_steps)
        if not callable(manual_confirm):
            return {"status": "pending", "message": "需确认加速度校准是否完成"}
        status = manual_confirm("请确认加速度校准是否已完成。")
        on_step("确认加速度校准完成", status == "pass")
        if status != "pass":
            return {"status": "fail", "message": "加速度校准未确认完成"}
        return None

    result = run_tranfacmode_group_items_test(
        dut_id,
        SENSOR,
        ACCELEROMETER_GROUP_ITEM_SPECS,
        group_label=ACCELEROMETER_GROUP_LABEL,
        result_dir=context.get("result_dir"),
        on_step=on_step,
        before_items=prompt_accelerometer_calibration,
    )
    return {"status": result["status"], "message": result["message"]}
