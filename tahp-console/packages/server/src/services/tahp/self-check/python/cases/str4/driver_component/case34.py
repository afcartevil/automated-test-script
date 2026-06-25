"""STR4 驱动器件：红外功能（Sensor 工模红外测试）。"""

from utils.driver.tranfacmode_config import INFRARED_ITEM_KEYWORDS, SENSOR
from utils.driver.ui_tranfacmode import (
    _build_enter_group_steps,
    _collect_group_item_names,
    _group_page_ready,
    _run_selected_screen_item,
    _run_steps,
    _tap_group_item,
    _tap_group_item_name,
)
from utils.tdd.ui_automatic import click_by_match_keywords


def _get_dut_device_id(device_info):
    dut_list = (device_info or {}).get("DUT") or []
    if not dut_list:
        return None, "未获取到测试机设备信息"
    dut_id = (dut_list[0].get("device_id") or "").strip()
    if not dut_id:
        return None, "测试机 device_id 为空"
    return dut_id, ""


def _tap_infrared_item(device_id: str) -> bool:
    """先按 adapter_title 精确匹配，失败再滚动查找（放宽底部 dead zone）。"""
    item_names = _collect_group_item_names(device_id, INFRARED_ITEM_KEYWORDS)
    if item_names and _tap_group_item_name(device_id, item_names[0]):
        return True
    if _tap_group_item(device_id, INFRARED_ITEM_KEYWORDS):
        return True
    return click_by_match_keywords(
        device_id,
        INFRARED_ITEM_KEYWORDS,
        max_scrolls=8,
        prefer_cached_ui=False,
        top_dead_zone=0,
        bottom_dead_zone=0,
    )


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

    if err := _run_steps(on_step, _build_enter_group_steps(dut_id, SENSOR)):
        return err

    result = _run_selected_screen_item(
        dut_id,
        "红外",
        lambda: _tap_infrared_item(dut_id),
        INFRARED_ITEM_KEYWORDS,
        on_step=on_step,
        page_ready=lambda: _group_page_ready(dut_id, SENSOR),
    )
    if result["status"] == "pass":
        return {"status": "pass", "message": result["message"]}
    if "未找到红外测试项" not in result.get("message", ""):
        return result

    notice = "Sensor 工模未找到红外测试项，请确认本机是否支持红外。"
    if callable(operator_notify):
        operator_notify(notice)
    sub_steps += f"\n需人工确认：{notice}"
    update(sub_steps)
    if not callable(manual_confirm):
        return {"status": "pending", "message": "需确认设备是否支持红外"}
    status = manual_confirm(
        "Sensor 工模未找到红外测试项，请确认本机是否支持红外。",
        pass_label="支持",
        fail_label="不支持",
    )
    on_step("人工确认红外支持", status == "pass")
    if status == "pass":
        return {"status": "fail", "message": f"{result['message']}（人工确认支持红外）"}
    return {"status": "skip", "message": "设备不支持红外，已跳过"}
