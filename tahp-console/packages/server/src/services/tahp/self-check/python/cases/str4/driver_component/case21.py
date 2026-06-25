"""驱动周版本自检：工模单色灯（Mono LED）/ SRGB 灯测试。"""

from utils.driver.tranfacmode_config import LED_ITEMS
from utils.driver.tranfacmode_ui import dump
from utils.driver.ui_tranfacmode import (
    open_other_tab,
    pick_other_tab_item,
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
    ]
    for label, action, fail_msg in steps:
        ok = action()
        on_step(label, ok)
        if not ok:
            return {"status": "fail", "message": fail_msg}

    xml = dump(dut_id)
    led_item = pick_other_tab_item(xml, LED_ITEMS) if xml else None
    on_step("识别 LED 类型", led_item is not None)
    if led_item is None:
        return {
            "status": "fail",
            "message": "未找到单色灯(Mono LED/单色灯)或 SRGB 灯(SRGB LED/SRGB灯)测试项",
        }

    on_step(f"识别为{led_item.label}", True)
    ok = tap_other_list_item(dut_id, led_item.item_text)
    on_step(f"选择{led_item.label}测试项", ok)
    if not ok:
        return {"status": "fail", "message": f"未找到 {led_item.item_text} 测试项"}

    sub_steps += "\n需人工评判"
    if callable(step_update):
        step_update(sub_steps)
    manual_prompt = f"请检查{led_item.label}是否正常亮起"
    if callable(manual_confirm):
        status = manual_confirm(manual_prompt)
        return {"status": status, "message": f"人工评判{status}"}
    return {"status": "pending", "message": "需人工评判"}
