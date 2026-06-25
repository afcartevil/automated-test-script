"""STR4 驱动器件：心率血氧（Sensor 工模血氧传感器测试）。"""

from utils.driver.tranfacmode_config import PULSE_OXIMETER_ITEM_KEYWORDS, SENSOR
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

    dut_id, error = _get_dut_device_id(device_info)
    if not dut_id:
        update(error)
        return {"status": "fail", "message": error}

    result = run_tranfacmode_group_items_test(
        dut_id,
        SENSOR,
        (("血氧传感器测试", PULSE_OXIMETER_ITEM_KEYWORDS),),
        group_label="血氧传感器",
        result_dir=context.get("result_dir"),
        on_step=on_step,
    )
    if result["status"] == "pass":
        return {"status": "pass", "message": f"血氧传感器测试: {result['message']}"}
    if "未找到血氧传感器测试测试项" not in result.get("message", ""):
        return result

    notice = "Sensor 工模未找到血氧传感器测试项，请确认本机是否支持血氧传感器。"
    if callable(operator_notify):
        operator_notify(notice)
    sub_steps += f"\n需人工确认：{notice}"
    update(sub_steps)
    if not callable(manual_confirm):
        return {"status": "pending", "message": "需确认设备是否支持血氧传感器"}
    status = manual_confirm(
        "Sensor 工模未找到血氧传感器测试项，请确认本机是否支持血氧传感器。",
        pass_label="支持",
        fail_label="不支持",
    )
    on_step("人工确认血氧传感器支持", status == "pass")
    if status == "pass":
        return {
            "status": "fail",
            "message": f"{result['message']}（人工确认支持血氧传感器）",
        }
    return {"status": "skip", "message": "设备不支持血氧传感器，已跳过"}
