"""STR4 驱动器件：hal sensor（Sensor 工模 HAL Sensor 测试）。"""

from utils.driver.support_confirm import (
    ask_feature_support,
    is_item_not_found_message,
    missing_item_notice,
)
from utils.driver.tranfacmode_config import HAL_SENSOR_CALI_KEYWORDS, SENSOR
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

    dut_id, error = _get_dut_device_id(device_info)
    if not dut_id:
        update(error)
        return {"status": "fail", "message": error}

    result = run_tranfacmode_group_items_test(
        dut_id,
        SENSOR,
        (("hal sensor", HAL_SENSOR_CALI_KEYWORDS),),
        group_label="hal sensor",
        result_dir=context.get("result_dir"),
        on_step=on_step,
    )
    if result["status"] == "pass":
        return {"status": "pass", "message": f"hal sensor: {result['message']}"}
    if not is_item_not_found_message(result.get("message")):
        return result

    notice = missing_item_notice("HAL Sensor")
    sub_steps += f"\n需人工确认：{notice}"
    update(sub_steps)
    status = ask_feature_support(manual_confirm, notice)
    if status == "pending":
        return {"status": "pending", "message": notice}
    on_step("人工确认 HAL Sensor 支持", status == "pass")
    if status == "pass":
        return {
            "status": "fail",
            "message": f"{result['message']}（人工确认支持 HAL Sensor）",
        }
    return {"status": "skip", "message": "设备不支持 HAL Sensor，已跳过"}
