"""驱动周版本自检：开机状态充电（复用 case14 标准充电结果 + 人工插拔确认）。"""

from utils.driver.tranfacmode_config import USB_STANDARD_CHARGE_ITEM_KEYWORDS
from utils.driver.ui_tranfacmode import run_reuse_usb_group_item


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

    _, error = _get_dut_device_id(device_info)
    if error:
        if callable(step_update):
            step_update(error)
        return {"status": "fail", "message": error}

    sub_steps = ""

    def update(message: str) -> None:
        if callable(step_update):
            step_update(message)

    def on_reuse_step(message: str) -> None:
        nonlocal sub_steps
        sub_steps = message
        update(sub_steps)

    reuse_result = run_reuse_usb_group_item(
        context,
        USB_STANDARD_CHARGE_ITEM_KEYWORDS,
        item_label="标准充电",
        step_update=on_reuse_step,
    )
    if reuse_result["status"] != "pass":
        return reuse_result

    operation_text = "请多次插拔USB，确认是否正常识别"
    if callable(operator_notify):
        operator_notify(operation_text)
    sub_steps += f"\n需人工操作：{operation_text}\n需人工评判"
    update(sub_steps)

    if callable(manual_confirm):
        status = manual_confirm("请确认多次插拔USB后均能正常识别")
        return {"status": status, "message": f"人工评判{status}"}
    return {"status": "pending", "message": "需人工评判"}
