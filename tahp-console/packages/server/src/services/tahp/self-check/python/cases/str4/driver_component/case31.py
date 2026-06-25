"""STR4 驱动器件：陀螺仪零飘测试（工模陀螺仪校准与测试）。"""

from utils.driver.tranfacmode_config import (
    GYRO_ITEM_KEYWORDS,
    SENSOR,
    SENSOR_CALI_EXCLUDE_KEYWORDS,
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
    sub_steps = ""

    def update(message: str) -> None:
        if callable(step_update):
            step_update(message)

    def on_step(label: str, ok: bool) -> None:
        nonlocal sub_steps
        sub_steps += f"\n{label}" + ("-成功" if ok else "-失败")
        update(sub_steps)

    def prompt_gyro_calibration():
        nonlocal sub_steps
        operation_text = "请在 Sensor 工模列表中点击陀螺仪校准项，并按界面提示完成校准。"
        if callable(operator_notify):
            operator_notify(operation_text)
        sub_steps += f"\n需人工操作：{operation_text}\n需人工确认"
        update(sub_steps)
        if not callable(manual_confirm):
            return {"status": "pending", "message": "需确认陀螺仪校准是否完成"}
        status = manual_confirm("请确认陀螺仪校准是否已完成。")
        on_step("确认陀螺仪校准完成", status == "pass")
        if status != "pass":
            return {"status": "fail", "message": "陀螺仪校准未确认完成"}
        return None

    dut_id, error = _get_dut_device_id(device_info)
    if not dut_id:
        update(error)
        return {"status": "fail", "message": error}

    gyro_result = run_tranfacmode_group_items_test(
        dut_id,
        SENSOR,
        (("陀螺仪", GYRO_ITEM_KEYWORDS, SENSOR_CALI_EXCLUDE_KEYWORDS),),
        group_label="陀螺仪",
        result_dir=context.get("result_dir"),
        on_step=on_step,
        before_items=prompt_gyro_calibration,
    )
    if gyro_result["status"] != "pass":
        return gyro_result

    return {
        "status": "pass",
        "message": f"陀螺仪零飘测试: 陀螺仪校准已确认完成; {gyro_result['message']}",
    }
