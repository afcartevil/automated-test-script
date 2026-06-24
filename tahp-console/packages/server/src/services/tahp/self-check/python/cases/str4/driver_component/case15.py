"""驱动周版本自检：工模 USB 测试组（先点 Sensor 标签再点 USB 标签后顺序执行）。"""

from utils.driver.tranfacmode_config import USB
from utils.driver.ui_tranfacmode import run_group_sequence


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

    result = run_group_sequence(
        dut_id,
        USB,
        result_dir=context.get("result_dir"),
        on_step=on_step,
    )
    return {"status": result["status"], "message": result["message"]}
