"""驱动周版本自检：工模单色灯（Mono LED）测试。"""

from utils.driver.tranfacmode_config import MONO_LED
from utils.driver.ui_tranfacmode import (
    open_other_tab,
    skip_rf_calibration,
    start_main,
    tap_other_list_item,
    tranfacmode_prep_steps,
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

    steps = [
        *tranfacmode_prep_steps(dut_id),
        ("启动工模主界面", lambda: start_main(dut_id), "启动工模 MainActivity 失败"),
        ("跳过射频参数校准", lambda: skip_rf_calibration(dut_id), "跳过射频参数校准失败"),
        ("进入 Other 分类", lambda: open_other_tab(dut_id), "进入 Other/其他 分类失败"),
        (
            f"选择{MONO_LED.label}测试项",
            lambda: tap_other_list_item(dut_id, MONO_LED.item_text),
            f"未找到 {MONO_LED.item_text} 测试项",
        ),
    ]
    for label, action, fail_msg in steps:
        ok = action()
        on_step(label, ok)
        if not ok:
            return {"status": "fail", "message": fail_msg}

    sub_steps += "\n需人工评判"
    if callable(step_update):
        step_update(sub_steps)
    if callable(manual_confirm):
        status = manual_confirm("请检查单色灯是否正常亮起")
        return {"status": status, "message": f"人工评判{status}"}
    return {"status": "pending", "message": "需人工评判"}
