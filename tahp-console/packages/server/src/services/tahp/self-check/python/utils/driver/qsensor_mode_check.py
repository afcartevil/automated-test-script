"""QSensorTest 传感器模式导入检测（电梯 / 乘车等）。"""

import time
import xml.etree.ElementTree as ET
from typing import Callable

from utils.driver.support_confirm import ask_feature_support, missing_item_notice, missing_prop_notice
from utils.driver.tranfacmode_ui import adb, dump, tap_xml
from utils.tdd.ui_automatic import (
    DEFAULT_SLEEP_AFTER_SWIPE,
    DEFAULT_SWIPE,
    _ensure_device_scroll_index,
    acquire_u2,
    dump_current_ui,
    release_uiautomator2,
)

QSENSOR_PACKAGE = "com.qualcomm.qti.sensors.qsensortest"
QSENSOR_ACTIVITY = (
    "com.qualcomm.qti.sensors.qsensortest/"
    "com.qualcomm.qti.sensors.ui.qsensortest.TabControl"
)

ELEVATOR_MODE_MARKER = "elevator: elevator: transsion"
VEHICLE_MODE_MARKER = "vehicle: vehicle: transsion"
GYRO_SENSOR_MARKER = "GYRO: lsm6dso_gyro: st"
ELEVATOR_MODE_SUPPORT_PROP = "ro.tr_telephony.disable_elevator_mode.feature.support"
VEHICLE_MODE_SUPPORT_PROP = "ro.tr_sensor.vehicle_mode.feature.support"

MAX_UI_SCROLL_ROUNDS = 12
_LIST_SWIPE = (*DEFAULT_SWIPE[:4], DEFAULT_SWIPE[4])


def _is_prop_supported(value: str) -> bool:
    val = (value or "").strip().lower()
    return bool(val) and val not in ("0", "false", "no", "off")


def _read_prop(device_id: str, prop: str) -> tuple[bool, str]:
    ret = adb(device_id, "shell", "getprop", prop)
    if ret.returncode != 0:
        return False, (ret.stderr or ret.stdout or "").strip()
    return True, (ret.stdout or "").strip()


def _confirm_mode_support_when_prop_disabled(
    device_id: str,
    support_prop: str,
    mode_label: str,
    *,
    on_step: Callable[[str, bool], None] | None,
    append_note: Callable[[str], None] | None,
    manual_confirm,
) -> dict[str, str] | None:
    """属性未声明支持时人工确认；不支持则 skip，支持则继续检测。"""
    read_ok, value = _read_prop(device_id, support_prop)
    if callable(on_step):
        on_step(f"读取属性 {support_prop}", read_ok)
    if callable(append_note):
        append_note(f"{support_prop}={value or '<空>'}")

    if read_ok and _is_prop_supported(value):
        if callable(on_step):
            on_step(f"属性声明支持{mode_label}", True)
        return None

    if callable(on_step):
        on_step(f"属性声明不支持{mode_label}", False)
    notice = missing_prop_notice(mode_label)
    if callable(append_note):
        append_note(f"需人工确认：{notice}")

    status = ask_feature_support(manual_confirm, notice)
    if status == "pending":
        return {"status": "pending", "message": notice}
    if status != "pass":
        return {"status": "skip", "message": f"设备不支持{mode_label}，已跳过"}
    return None


def is_qsensor_installed(device_id: str) -> bool:
    ret = adb(device_id, "shell", "pm", "path", QSENSOR_PACKAGE)
    return ret.returncode == 0 and "package:" in (ret.stdout or "")


def launch_qsensor(device_id: str) -> tuple[bool, str]:
    ret = adb(device_id, "shell", "am", "start", "-n", QSENSOR_ACTIVITY)
    if ret.returncode != 0:
        detail = (ret.stderr or ret.stdout or "").strip()
        return False, detail or "启动 QSensorTest 失败"
    time.sleep(1.5)
    return True, ""


def _ui_has_marker(device_id: str, marker: str) -> bool:
    xml = dump_current_ui(device_id) or dump(device_id)
    if not xml:
        return False
    target = marker.strip()
    try:
        for node in ET.parse(xml).getroot().iter("node"):
            if (node.attrib.get("text") or "").strip() == target:
                return True
    except (ET.ParseError, OSError):
        pass
    return False


def _swipe_list_once(device_id: str) -> None:
    x1, y1, x2, y2, duration_ms = _LIST_SWIPE
    adb(device_id, "shell", "input", "swipe", x1, y1, x2, y2, str(duration_ms))
    time.sleep(DEFAULT_SLEEP_AFTER_SWIPE)


def search_sensor_marker_in_ui(device_id: str, marker: str) -> bool:
    """在 QSensorTest 列表中滑动查找 @text 精确匹配的 marker。"""
    use_u2 = acquire_u2(device_id) is not None
    scroll_count = 0
    try:
        for slide in range(MAX_UI_SCROLL_ROUNDS + 1):
            if _ui_has_marker(device_id, marker):
                return True
            if slide >= MAX_UI_SCROLL_ROUNDS:
                break
            if use_u2:
                scroll_count = _ensure_device_scroll_index(
                    device_id,
                    slide + 1,
                    scroll_count,
                    _LIST_SWIPE,
                    DEFAULT_SLEEP_AFTER_SWIPE,
                )
            else:
                _swipe_list_once(device_id)
        return _ui_has_marker(device_id, marker)
    finally:
        if use_u2:
            release_uiautomator2(device_id, wait_ready=False)


def tap_sensor_marker_in_ui(device_id: str, marker: str) -> bool:
    """在 QSensorTest 列表中滑动查找 @text 精确匹配的 marker 并点击。"""
    use_u2 = acquire_u2(device_id) is not None
    scroll_count = 0
    target = marker.strip()
    if not target:
        return False
    try:
        for slide in range(MAX_UI_SCROLL_ROUNDS + 1):
            xml = dump_current_ui(device_id) or dump(device_id)
            if xml and tap_xml(device_id, xml, text_equals=(target,)):
                return True
            if slide >= MAX_UI_SCROLL_ROUNDS:
                break
            if use_u2:
                scroll_count = _ensure_device_scroll_index(
                    device_id,
                    slide + 1,
                    scroll_count,
                    _LIST_SWIPE,
                    DEFAULT_SLEEP_AFTER_SWIPE,
                )
            else:
                _swipe_list_once(device_id)
        xml = dump_current_ui(device_id) or dump(device_id)
        return bool(xml and tap_xml(device_id, xml, text_equals=(target,)))
    finally:
        if use_u2:
            release_uiautomator2(device_id, wait_ready=False)


def search_sensor_marker(device_id: str, marker: str) -> tuple[bool, str]:
    if search_sensor_marker_in_ui(device_id, marker):
        return True, "QSensorTest 界面（滑动列表）"

    output = adb(device_id, "shell", "dumpsys", "sensorservice")
    text = (output.stdout or "") + (output.stderr or "")
    compact = marker.replace(": ", ":").replace(" ", "")
    if marker in text or compact in text:
        return True, "dumpsys sensorservice"
    return False, ""


def run_qsensor_mode_import_check(
    device_id: str,
    *,
    marker: str,
    mode_label: str,
    support_prop: str | None = None,
    on_step: Callable[[str, bool], None] | None = None,
    append_note: Callable[[str], None] | None = None,
    manual_confirm=None,
    **_unused,
) -> dict[str, str]:
    def step(label: str, ok: bool) -> None:
        if callable(on_step):
            on_step(label, ok)

    if support_prop:
        prop_result = _confirm_mode_support_when_prop_disabled(
            device_id,
            support_prop,
            mode_label,
            on_step=on_step,
            append_note=append_note,
            manual_confirm=manual_confirm,
        )
        if prop_result is not None:
            return prop_result

    installed = is_qsensor_installed(device_id)
    step("检查 QSensorTest 已安装", installed)
    if not installed:
        return {
            "status": "fail",
            "message": f"未安装 QSensorTest({QSENSOR_PACKAGE})，无法检测{mode_label}导入",
        }

    launched, launch_error = launch_qsensor(device_id)
    step("启动 QSensorTest", launched)
    if not launched:
        return {
            "status": "fail",
            "message": f"启动 QSensorTest 失败：{launch_error}",
        }

    found, source = search_sensor_marker(device_id, marker)
    step(f"滑动列表搜索 {marker}", found)
    if found:
        return {
            "status": "pass",
            "message": f"{mode_label}已导入（在 {source} 中找到 {marker}）",
        }

    notice = missing_item_notice(mode_label)
    if callable(append_note):
        append_note(f"需人工确认：{notice}")
    status = ask_feature_support(manual_confirm, notice)
    if status == "pending":
        return {"status": "pending", "message": notice}
    if status != "pass":
        return {"status": "skip", "message": f"设备不支持{mode_label}，已跳过"}
    return {
        "status": "fail",
        "message": f"未找到 {marker}，{mode_label}未导入（人工确认支持{mode_label}）",
    }
