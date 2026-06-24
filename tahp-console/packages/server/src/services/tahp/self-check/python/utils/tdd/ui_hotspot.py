"""个人热点：开关与单次流量限额。"""

import subprocess
import time
import xml.etree.ElementTree as ET
from typing import Optional

from utils.tdd.ui_automatic import click_by_match_keywords
from utils.tdd.ui_switch import set_labeled_switch_enable
from utils.tdd.ui_u2 import adb_dump_hierarchy_xml, dump_current_ui
from utils.tdd.ui_xml import (
    build_parent_map,
    find_labeled_switch_in_root,
    parse_bounds_center,
    resolve_tap_node,
    tap_element_bounds,
)

WIFI_TETHER_SETTINGS_ACTION = "com.android.settings.WIFI_TETHER_SETTINGS"
HOTSPOT_KEYWORDS = (
    "个人热点",
    "便携式热点",
    "Portable hotspot",
    "Wi-Fi hotspot",
    "WLAN热点",
    "WLAN 热点",
)
CONNECTION_MANAGE_KEYWORDS = ("连接管理", "Connection management", "Connected devices")
LIMIT_MENU_KEYWORDS = ("单次流量限额", "单词流量限额", "Single session")
LIMIT_SIZE_KEYWORDS = ("流量限额大小", "限额大小", "Limit size", "Data limit")
MB_OPTION_KEYWORDS = ("MB", "兆")
CONFIRM_KEYWORDS = ("确定", "确认", "保存", "OK")
LIMIT_VALUE_RESOURCE_IDS = (
    "com.transsion.settings.wifi:id/limitvalue",
    "android:id/edit",
)
UNIT_MB_RESOURCE_IDS = (
    "com.transsion.settings.wifi:id/unit_mb",
)
CONFIRM_BUTTON_RESOURCE_IDS = (
    "com.transsion.settings.wifi:id/btn_positive",
    "com.android.settings:id/btn_positive",
    "android:id/button1",
)
PAGE_SETTLE_SECONDS = 1.2


def _run_adb(device_id: str, *args: str, timeout: int = 30):
    return subprocess.run(
        ["adb", "-s", device_id, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def open_tether_settings(device_id: str) -> bool:
    _run_adb(
        device_id,
        "shell",
        "am",
        "force-stop",
        "com.transsion.settings.wifi",
        timeout=15,
    )
    time.sleep(0.3)
    ret = _run_adb(
        device_id,
        "shell",
        "am",
        "start",
        "-a",
        WIFI_TETHER_SETTINGS_ACTION,
        timeout=20,
    )
    time.sleep(PAGE_SETTLE_SECONDS)
    output = f"{ret.stdout or ''}{ret.stderr or ''}"
    if ret.returncode != 0 or "Error:" in output:
        return False
    return True


def _is_hotspot_row(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return any(k in t for k in HOTSPOT_KEYWORDS)


def _is_single_session_limit_switch_row(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return any(k in t for k in LIMIT_MENU_KEYWORDS)


def _adb_tap(device_id: str, x: int, y: int) -> bool:
    ret = _run_adb(device_id, "shell", "input", "tap", str(x), str(y), timeout=15)
    return ret.returncode == 0


def _adb_input_digits(device_id: str, value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    ret = _run_adb(device_id, "shell", "input", "text", text, timeout=15)
    return ret.returncode == 0


def _dump_ui_root(device_id: str) -> Optional[ET.Element]:
    path = dump_current_ui(device_id)
    if path is not None and path.is_file():
        try:
            return ET.parse(path).getroot()
        except ET.ParseError:
            pass
    xml = adb_dump_hierarchy_xml(device_id)
    if not xml:
        return None
    try:
        return ET.fromstring(xml)
    except ET.ParseError:
        return None


def _tap_node(device_id: str, node: ET.Element) -> bool:
    bounds = node.attrib.get("bounds") or ""
    center = tap_element_bounds(bounds)
    if center is None:
        return False
    return _adb_tap(device_id, center[0], center[1])


def _find_node_by_resource_ids(root: ET.Element, resource_ids: tuple[str, ...]) -> Optional[ET.Element]:
    id_set = set(resource_ids)
    for el in root.iter("node"):
        rid = (el.attrib.get("resource-id") or "").strip()
        if rid in id_set:
            return el
    return None


def _click_row_by_keywords_adb(
    device_id: str,
    keywords: tuple[str, ...],
    *,
    exact: bool = False,
) -> bool:
    root = _dump_ui_root(device_id)
    if root is None:
        return False
    parent = build_parent_map(root)
    candidates: list[tuple[int, ET.Element]] = []
    for el in root.iter("node"):
        label = (el.attrib.get("text") or el.attrib.get("content-desc") or "").strip()
        if not label:
            continue
        if exact:
            if not any(label == k for k in keywords):
                continue
        elif not any(k in label for k in keywords):
            continue
        rid = (el.attrib.get("resource-id") or "").strip()
        score = 0
        if rid == "android:id/title":
            score += 20
        if exact and any(label == k for k in keywords):
            score += 10
        elif any(k in label for k in keywords):
            score += 5
        if len(label) <= 20:
            score += 2
        tap_node = resolve_tap_node(el, parent)
        candidates.append((score, tap_node))
    if not candidates:
        return False
    candidates.sort(key=lambda item: item[0], reverse=True)
    for _, tap_node in candidates:
        if _tap_node(device_id, tap_node):
            return True
    return False


def _click_keywords(
    device_id: str,
    keywords: tuple[str, ...],
    *,
    max_scrolls: int = 5,
    exact: bool = False,
) -> bool:
    if click_by_match_keywords(
        device_id,
        keywords,
        max_scrolls=max_scrolls,
        prefer_cached_ui=False,
    ):
        return True
    return _click_row_by_keywords_adb(device_id, keywords, exact=exact)


def _tap_edittext(device_id: str) -> bool:
    root = _dump_ui_root(device_id)
    if root is None:
        return False
    edit_node = _find_node_by_resource_ids(root, LIMIT_VALUE_RESOURCE_IDS)
    if edit_node is None:
        for el in root.iter("node"):
            if "EditText" in (el.attrib.get("class") or ""):
                edit_node = el
                break
    if edit_node is None:
        return False
    return _tap_node(device_id, edit_node)


def _input_limit_size_mb_dialog(device_id: str, mb: int) -> bool:
    """弹框：输入限额数字 → 选 MB → 确定。"""
    root = _dump_ui_root(device_id)
    if root is not None:
        edit_node = _find_node_by_resource_ids(root, LIMIT_VALUE_RESOURCE_IDS)
        if edit_node is not None:
            if not _tap_node(device_id, edit_node):
                return False
            time.sleep(0.2)
            _run_adb(device_id, "shell", "input", "keyevent", "123", timeout=10)  # MOVE_END
            for _ in range(6):
                _run_adb(device_id, "shell", "input", "keyevent", "67", timeout=10)  # DEL
            time.sleep(0.1)
            if not _adb_input_digits(device_id, mb):
                return False
            time.sleep(0.25)
            mb_node = _find_node_by_resource_ids(root, UNIT_MB_RESOURCE_IDS)
            if mb_node is not None and _tap_node(device_id, mb_node):
                time.sleep(0.3)
            elif not _click_row_by_keywords_adb(device_id, MB_OPTION_KEYWORDS):
                pass
            root = _dump_ui_root(device_id)
            if root is not None:
                confirm = _find_node_by_resource_ids(root, CONFIRM_BUTTON_RESOURCE_IDS)
                if confirm is not None and _tap_node(device_id, confirm):
                    time.sleep(0.5)
                    return True
            if _click_row_by_keywords_adb(device_id, CONFIRM_KEYWORDS):
                time.sleep(0.5)
                return True

    if not _tap_edittext(device_id):
        return False
    time.sleep(0.2)
    if not _adb_input_digits(device_id, mb):
        return False
    time.sleep(0.3)
    if not _click_keywords(device_id, MB_OPTION_KEYWORDS, max_scrolls=5):
        return False
    time.sleep(0.3)
    return _click_keywords(device_id, CONFIRM_KEYWORDS, max_scrolls=3)


def _session_limit_switch_on_page(device_id: str) -> bool:
    """当前页是否已有「单次流量限额」开关行（WLAN热点设置子页）。"""
    root = _dump_ui_root(device_id)
    if root is None:
        return False
    return find_labeled_switch_in_root(root, _is_single_session_limit_switch_row) is not None


def setup_single_session_limit_mb(device_id: str, mb: int = 3) -> tuple[bool, int]:
    """
    个人热点 → 连接管理 →（进入）单次流量限额子页 → 打开开关 → 流量限额大小 → 设 MB。

    传音等平台在连接管理页为箭头入口，需再点「单次流量限额」进入子页才有开关。
    返回 (成功与否, 回到个人热点页需按返回的次数)。
    """
    backs_to_hotspot_main = 1
    if not _click_keywords(
        device_id, CONNECTION_MANAGE_KEYWORDS, max_scrolls=8, exact=True
    ):
        return False, backs_to_hotspot_main
    time.sleep(0.8)
    if not _session_limit_switch_on_page(device_id):
        if not _click_keywords(
            device_id, LIMIT_MENU_KEYWORDS, max_scrolls=8, exact=True
        ):
            return False, backs_to_hotspot_main
        time.sleep(0.8)
        backs_to_hotspot_main = 2
    if not set_labeled_switch_enable(
        device_id, True, _is_single_session_limit_switch_row
    ):
        return False, backs_to_hotspot_main
    time.sleep(0.5)
    if not _click_keywords(device_id, LIMIT_SIZE_KEYWORDS, max_scrolls=8, exact=True):
        return False, backs_to_hotspot_main
    time.sleep(0.6)
    if not _input_limit_size_mb_dialog(device_id, mb):
        return False, backs_to_hotspot_main
    return True, backs_to_hotspot_main


def _press_back(device_id: str, times: int = 1) -> None:
    for _ in range(max(0, times)):
        _run_adb(device_id, "shell", "input", "keyevent", "4", timeout=10)
        time.sleep(0.5)


def setup_personal_hotspot_with_session_limit_mb(device_id: str, mb: int = 3) -> bool:
    """
    完整流程：进个人热点 → 设单次流量限额 → 回到个人热点 → 打开个人热点开关。
    """
    if not open_tether_settings(device_id):
        return False
    ok, backs = setup_single_session_limit_mb(device_id, mb)
    if not ok:
        return False
    time.sleep(0.5)
    _press_back(device_id, backs)
    time.sleep(0.5)
    return set_labeled_switch_enable(device_id, True, _is_hotspot_row)


def enable_personal_hotspot(device_id: str) -> bool:
    if not open_tether_settings(device_id):
        return False
    return set_labeled_switch_enable(device_id, True, _is_hotspot_row)


def disable_personal_hotspot(device_id: str) -> bool:
    if not open_tether_settings(device_id):
        return False
    return set_labeled_switch_enable(device_id, False, _is_hotspot_row)
