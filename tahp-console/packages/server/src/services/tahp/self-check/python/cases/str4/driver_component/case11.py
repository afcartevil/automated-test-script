"""STR4 驱动器件：开机工模背光子项测试。"""

from utils.driver.tranfacmode_config import SCREEN_BACKLIGHT_ITEM_KEYWORDS
from utils.driver.ui_tranfacmode import run_screen_group_item_test


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

    result = run_screen_group_item_test(
        dut_id,
        SCREEN_BACKLIGHT_ITEM_KEYWORDS,
        item_label="背光",
        result_dir=context.get("result_dir"),
        on_step=on_step,
        manual_confirm=context.get("manual_confirm"),
    )
    return {"status": result["status"], "message": result["message"]}
