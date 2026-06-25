"""驱动周版本自检：开机状态充电（工模 USB 标准充电 + 人工插拔确认）。"""

from utils.driver.tranfacmode_config import USB, USB_STANDARD_CHARGE_ITEM_KEYWORDS
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

    standard_charge_result = run_tranfacmode_group_items_test(
        dut_id,
        USB,
        [("标准充电", USB_STANDARD_CHARGE_ITEM_KEYWORDS)],
        group_label="标准充电",
        result_dir=context.get("result_dir"),
        on_step=on_step,
    )
    if standard_charge_result["status"] != "pass":
        return {
            "status": standard_charge_result["status"],
            "message": standard_charge_result["message"],
        }

    operation_text = "请多次插拔USB，确认是否正常识别"
    if callable(operator_notify):
        operator_notify(operation_text)
    sub_steps += f"\n需人工操作：{operation_text}\n需人工评判"
    update(sub_steps)

    if callable(manual_confirm):
        status = manual_confirm("请确认多次插拔USB后均能正常识别")
        return {"status": status, "message": f"人工评判{status}"}
    return {"status": "pending", "message": "需人工评判"}
