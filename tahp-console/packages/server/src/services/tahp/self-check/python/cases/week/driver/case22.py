"""驱动周版本自检：加速度功能（先人工完成 sensor 校准项，再自动测试全部非 cali 项）。"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from collections.abc import Callable

from utils.driver.tranfacmode_config import ADAPTER_TITLE_RID_SUFFIX, SENSOR
from utils.driver.tranfacmode_group_result import FAIL_TEXTS, PASS_TEXTS
from utils.driver.tranfacmode_ui import (
    adb,
    dump,
    poll_bool,
    poll_value,
    tap_list_item,
    tap_xml,
    textview_result,
    ui_has_keywords,
)
from utils.driver.sensor_items_result import save_sensor_items_result
from utils.driver.ui_tranfacmode import (
    enter_group,
    skip_rf_calibration,
    start_main,
    tranfacmode_prep_steps,
)
from utils.tdd.ui_automatic import click_by_match_keywords


SWIPE_DELAY = 1.0
RESULT_BUTTONS = {
    "pass": (
        "com.transsion.tranfacmode:id/result_btn_pass",
        ("通过", "成功", "PASS", "Pass"),
    ),
    "fail": (
        "com.transsion.tranfacmode:id/result_btn_fail",
        ("失败", "FAIL", "Fail"),
    ),
}


def _get_dut_device_id(device_info):
    dut_list = (device_info or {}).get("DUT") or []
    if not dut_list:
        return None, "未获取到测试机设备信息"
    dut_id = (dut_list[0].get("device_id") or "").strip()
    if not dut_id:
        return None, "测试机 device_id 为空"
    return dut_id, ""


def _is_cali_item(name: str) -> bool:
    lower_name = (name or "").lower()
    return "cali" in lower_name or "校准" in (name or "")


def _is_non_cali_item(name: str) -> bool:
    return not _is_cali_item(name)


def _is_accel_item(name: str) -> bool:
    lower_name = (name or "").lower()
    return "加速度" in (name or "") or "acceler" in lower_name or "accel" in lower_name


def _is_fingerprint_item(name: str) -> bool:
    lower_name = (name or "").lower()
    return "指纹" in (name or "") or "fingerprint" in lower_name or "finger" in lower_name


def _item_state_label(status: str) -> str:
    if status == "pass":
        return "通过"
    if status == "fail":
        return "失败"
    return (status or "").strip()


def _collect_visible_sensor_items(device_id: str) -> list[str]:
    xml = dump(device_id)
    if not xml:
        return []
    items: list[str] = []
    for node in ET.parse(xml).getroot().iter("node"):
        rid = node.attrib.get("resource-id") or ""
        if ADAPTER_TITLE_RID_SUFFIX not in rid:
            continue
        text = (node.attrib.get("text") or "").strip()
        if text:
            items.append(text)
    return items


def _swipe_sensor_list(device_id: str, *, direction: str = "up") -> bool:
    if direction == "down":
        sx, sy, ex, ey = "540", "700", "540", "1750"
    else:
        sx, sy, ex, ey = "540", "1750", "540", "700"
    return (
        adb(device_id, "shell", "input", "swipe", sx, sy, ex, ey, "480").returncode
        == 0
    )


def _scroll_sensor_to_top(device_id: str) -> None:
    stable_rounds = 0
    previous_first = None
    for _ in range(10):
        visible = _collect_visible_sensor_items(device_id)
        current_first = visible[0] if visible else None
        if current_first and current_first == previous_first:
            stable_rounds += 1
        else:
            stable_rounds = 0
        if stable_rounds >= 2:
            break
        if not _swipe_sensor_list(device_id, direction="down"):
            break
        previous_first = current_first
        time.sleep(SWIPE_DELAY)


def _discover_sensor_items(
    device_id: str,
    *,
    include_filter: Callable[[str], bool] | None = None,
) -> list[str]:
    _scroll_sensor_to_top(device_id)
    discovered: list[str] = []
    stable_rounds = 0
    for _ in range(12):
        visible = _collect_visible_sensor_items(device_id)
        changed = False
        for name in visible:
            if include_filter is not None and not include_filter(name):
                continue
            if name not in discovered:
                discovered.append(name)
                changed = True
        if changed:
            stable_rounds = 0
        else:
            stable_rounds += 1
        if stable_rounds >= 2:
            break
        if not _swipe_sensor_list(device_id, direction="up"):
            break
        time.sleep(SWIPE_DELAY)
    return discovered


def _back_to_sensor_page(device_id: str) -> bool:
    for _ in range(3):
        xml = dump(device_id)
        if xml and ui_has_keywords(xml, SENSOR.page_keywords):
            return True
        adb(device_id, "shell", "input", "keyevent", "4")
        time.sleep(0.45)
    xml = dump(device_id)
    return bool(xml and ui_has_keywords(xml, SENSOR.page_keywords))


def _confirm_sensor_item_result(device_id: str, state: str) -> bool:
    xml = dump(device_id)
    if not xml:
        return False
    button_rid, text_fallback = RESULT_BUTTONS[state]
    return tap_xml(device_id, xml, resource_id=button_rid) or tap_xml(
        device_id, xml, text_equals=text_fallback
    )


def _run_sensor_item(device_id: str, item_name: str) -> tuple[str, str]:
    if not tap_list_item(device_id, (item_name,), rid_suffix=ADAPTER_TITLE_RID_SUFFIX):
        if not click_by_match_keywords(
            device_id,
            (item_name,),
            max_scrolls=12,
            sleep_after_swipe=0.6,
            sleep_after_tap=0.45,
            prefer_cached_ui=False,
        ):
            return "fail", f"{item_name}(未找到测试项)"
    if _is_fingerprint_item(item_name):
        entered = poll_bool(
            lambda: (x := dump(device_id)) is not None
            and not ui_has_keywords(x, SENSOR.page_keywords),
            3.0,
            0.35,
        )
        if not entered:
            return "fail", f"{item_name}(未成功进入测试项，已跳过)"
    state = poll_value(
        lambda: (x := dump(device_id))
        and textview_result(x, tuple(PASS_TEXTS), tuple(FAIL_TEXTS)),
        120.0,
        0.6,
    )
    if state in ("pass", "fail"):
        _confirm_sensor_item_result(device_id, state)
    if not _back_to_sensor_page(device_id):
        return "fail", f"{item_name}(测试后未返回 Sensor 页面)"
    if state == "pass":
        return "pass", f"{item_name}(通过)"
    if state == "fail":
        return "fail", f"{item_name}(失败)"
    return "fail", f"{item_name}(超时未出结果)"


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

    pre_steps = [
        *tranfacmode_prep_steps(dut_id),
        ("启动工模主界面", lambda: start_main(dut_id), "启动工模 MainActivity 失败"),
        ("跳过射频参数校准", lambda: skip_rf_calibration(dut_id), "跳过射频参数校准失败"),
        (
            "进入sensor测试组",
            lambda: enter_group(dut_id, SENSOR),
            f"未找到测试组入口: {SENSOR.entry_keywords}",
        ),
        (
            "校验sensor测试组界面",
            lambda: poll_bool(
                lambda: (x := dump(dut_id)) is not None
                and ui_has_keywords(x, SENSOR.page_keywords),
                8.0,
                0.35,
            ),
            f"未进入测试组界面: {SENSOR.page_keywords}",
        ),
    ]
    for label, action, fail_msg in pre_steps:
        ok = action()
        on_step(label, ok)
        if not ok:
            return {"status": "fail", "message": fail_msg}

    discovered_cali_items = _discover_sensor_items(dut_id, include_filter=_is_cali_item)
    cali_status = ""
    if discovered_cali_items:
        cali_text = (
            "请在 Sensor 工模列表中完成以下传感器校准项："
            + "、".join(discovered_cali_items)
        )
        on_step(f"发现校准项({len(discovered_cali_items)}项)", True)
    else:
        cali_text = (
            "请在 Sensor 工模列表中完成各传感器校准项（名称含 Cali/校准）。"
        )
        on_step("发现校准项(0项, 使用通用提示)", True)

    if callable(operator_notify):
        operator_notify(cali_text)
    sub_steps += f"\n需人工操作：{cali_text}\n需人工评判"
    update(sub_steps)
    if callable(manual_confirm):
        cali_status = manual_confirm("请确认各传感器校准项均已完成。")
        on_step("确认传感器校准完成", cali_status == "pass")
        if cali_status != "pass":
            return {"status": "fail", "message": "传感器校准未确认完成"}
    else:
        return {"status": "pending", "message": "需确认传感器校准是否完成"}

    cali_saved_items = [
        {"name": name, "state": _item_state_label(cali_status)}
        for name in discovered_cali_items
    ]

    sensor_items = _discover_sensor_items(dut_id, include_filter=_is_non_cali_item)
    on_step(
        f"筛选sensor测试项({len(sensor_items)}项, 已过滤cali/校准)",
        bool(sensor_items),
    )
    if not sensor_items:
        return {"status": "fail", "message": "sensor组无可测项（已过滤 cali/校准）"}

    _scroll_sensor_to_top(dut_id)
    on_step("回到sensor列表顶部", True)

    details: list[str] = []
    failed: list[str] = []
    saved_items: list[dict[str, str]] = []
    accel_items: list[str] = []
    accel_failed: list[str] = []
    for item_name in sensor_items:
        item_status, item_detail = _run_sensor_item(dut_id, item_name)
        details.append(item_detail)
        saved_items.append(
            {"name": item_name, "state": _item_state_label(item_status)}
        )
        ok = item_status == "pass"
        on_step(f"测试 {item_name}", ok)
        if not ok:
            failed.append(item_detail)
        if _is_accel_item(item_name):
            accel_items.append(item_name)
            if item_status != "pass":
                accel_failed.append(item_detail)

    save_sensor_items_result(
        context.get("result_dir"),
        saved_items,
        cali_items=cali_saved_items,
    )
    on_step("保存sensor测试与校准结果", bool(saved_items or cali_saved_items))

    if not accel_items:
        return {"status": "fail", "message": "未找到加速度测试项，无法按加速度结果判定"}
    if accel_failed:
        msg = f"加速度项失败: {'; '.join(accel_failed)}"
        if failed and len(failed) != len(accel_failed):
            ignored = [x for x in failed if x not in accel_failed]
            if ignored:
                msg += f"；其他项结果(不影响判定): {'; '.join(ignored)}"
        return {"status": "fail", "message": msg}
    if failed:
        return {
            "status": "pass",
            "message": (
                f"加速度项通过；其他项结果(不影响判定): {'; '.join(failed)}"
            ),
        }
    return {
        "status": "pass",
        "message": f"加速度项通过，sensor测试全部完成（{len(details)}项）: {'; '.join(details)}",
    }
