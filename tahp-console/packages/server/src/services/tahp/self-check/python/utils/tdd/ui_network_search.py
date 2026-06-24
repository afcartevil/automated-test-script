"""设置「选择网络」界面：点击菜单进入、自动选择网络开关、搜网结果检查。"""

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Union

from utils.tdd.ui_automatic import (
    DEFAULT_MAX_SCROLLS,
    DEFAULT_SLEEP_AFTER_SWIPE,
    DEFAULT_SWIPE,
    _ensure_device_scroll_index,
    _get_wm_size,
    click_by_match_keywords,
    click_dialog_confirm,
    dump_current_ui,
)

EnableTarget = Union[bool, int, str]

CHOOSE_NETWORK_KEYWORDS = ("选择网络",)
AUTO_SELECT_NETWORK_KEYWORDS = (
    "自动选择网络",
    "自动选取网络",
    "Automatically select network",
)
NETWORK_SELECT_PAGE_MARKERS = ("选择网络",)
UI_EXCLUDE_MARKERS = (
    "选择网络",
    "自动选择网络",
    "自动选取网络",
    "网络运营商",
    "正在搜索",
    "搜索中",
    "已断开连接",
    "禁止的网络",
    "forbidden",
    "register_automatically",
    "Automatically select network",
)
PRIMARY_CARRIER_MARKERS = ("中国移动", "中国联通")
SECONDARY_CARRIER_MARKERS = (
    "中国电信",
    "CMCC",
    "CUCC",
    "CTCC",
    "CHINA MOBILE",
    "CHINA UNICOM",
    "CHINA TELECOM",
)
RAT_PATTERN = re.compile(r"(2G|3G|4G|5G|LTE|NR)", re.IGNORECASE)

PAGE_SETTLE_SECONDS = 1.0
SETTLE_AFTER_TAP = 0.8
DIALOG_SETTLE_SECONDS = 0.6
NETWORK_SCAN_POLL_INTERVAL_SECONDS = 10
NETWORK_SCAN_POLL_MAX_ATTEMPTS = 6
NETWORK_SCAN_INITIAL_DELAY_SECONDS = 10
NETWORK_SEARCHING_MARKERS = (
    "正在搜索",
    "搜索中",
    "searching",
    "Searching",
)


def _run_adb(device_id: str, *args: str, timeout: int = 30):
    return subprocess.run(
        ["adb", "-s", device_id, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _tap_screen(device_id: str, x: int, y: int) -> bool:
    return _run_adb(device_id, "shell", "input", "tap", str(x), str(y)).returncode == 0


def _parse_bounds_center(bounds: str) -> tuple[int, int]:
    chunks = bounds.replace("][", ",").replace("[", "").replace("]", "").split(",")
    if len(chunks) != 4:
        raise ValueError(f"invalid bounds: {bounds}")
    x1, y1, x2, y2 = (int(v) for v in chunks)
    return (x1 + x2) // 2, (y1 + y2) // 2


def _build_parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    parent: dict[ET.Element, ET.Element] = {}
    for node in root.iter():
        for child in list(node):
            parent[child] = node
    return parent


def normalize_enable(target: EnableTarget) -> Optional[bool]:
    if isinstance(target, bool):
        return target
    if isinstance(target, int):
        return target != 0
    if isinstance(target, str):
        text = target.strip().lower()
        if text in ("1", "true", "on", "open", "enable", "打开", "开", "启用"):
            return True
        if text in ("0", "false", "off", "close", "disable", "关闭", "关"):
            return False
    return None


def _is_auto_select_label(text: str) -> bool:
    label = (text or "").strip()
    if not label:
        return False
    return any(keyword in label for keyword in AUTO_SELECT_NETWORK_KEYWORDS)


def _is_excluded_network_label(text: str) -> bool:
    label = (text or "").strip()
    if not label:
        return True
    low = label.lower()
    if any(marker.lower() in low for marker in UI_EXCLUDE_MARKERS):
        return True
    if any(marker in label for marker in UI_EXCLUDE_MARKERS):
        return True
    return False


def _has_primary_carrier(label: str) -> bool:
    text = (label or "").strip()
    if not text or _is_excluded_network_label(text):
        return False
    return any(marker in text for marker in PRIMARY_CARRIER_MARKERS)


def _looks_like_secondary_scanned_network(text: str) -> bool:
    label = (text or "").strip()
    if not label or _is_excluded_network_label(label):
        return False
    if any(marker in label for marker in SECONDARY_CARRIER_MARKERS):
        return True
    if RAT_PATTERN.search(label) and re.search(r"[\u4e00-\u9fffA-Za-z]", label):
        return True
    return False


def _switch_in_subtree(root_el: ET.Element) -> Optional[ET.Element]:
    if "Switch" in (root_el.attrib.get("class") or ""):
        return root_el
    for child in root_el.iter("node"):
        if child is root_el:
            continue
        if "Switch" in (child.attrib.get("class") or ""):
            return child
    return None


def _clickable_tap_target(el: ET.Element, parent_map: dict[ET.Element, ET.Element]) -> ET.Element:
    tap_el: Optional[ET.Element] = el
    for _ in range(8):
        if tap_el is None:
            break
        if tap_el.attrib.get("clickable") == "true":
            return tap_el
        tap_el = parent_map.get(tap_el)
    return el


def _find_auto_select_switch(
    xml_path: Path,
) -> Optional[tuple[ET.Element, ET.Element]]:
    if not xml_path.is_file():
        return None
    root = ET.parse(xml_path).getroot()
    parent_map = _build_parent_map(root)
    for el in root.iter("node"):
        label = (el.attrib.get("text") or "") + (el.attrib.get("content-desc") or "")
        if not _is_auto_select_label(label):
            continue
        switch_node: Optional[ET.Element] = None
        parent = parent_map.get(el)
        for search_root in (parent, el):
            if search_root is None:
                continue
            switch_node = _switch_in_subtree(search_root)
            if switch_node is not None:
                break
        if switch_node is None:
            continue
        row_root = parent if parent is not None else el
        return _clickable_tap_target(row_root, parent_map), switch_node
    return None


def _read_auto_select_checked(xml_path: Path) -> Optional[bool]:
    pair = _find_auto_select_switch(xml_path)
    if pair is None:
        return None
    _, switch_node = pair
    return switch_node.attrib.get("checked") == "true"


def _tap_auto_select_switch(device_id: str, xml_path: Path) -> bool:
    pair = _find_auto_select_switch(xml_path)
    if pair is None:
        return False
    tap_target, switch_node = pair
    bounds = tap_target.attrib.get("bounds") or switch_node.attrib.get("bounds") or ""
    if not bounds:
        return False
    try:
        x, y = _parse_bounds_center(bounds)
    except ValueError:
        return False
    return _tap_screen(device_id, x, y)


def _page_has_network_select_title(xml_path: Path) -> bool:
    if not xml_path.is_file():
        return False
    root = ET.parse(xml_path).getroot()
    for el in root.iter("node"):
        text = (el.attrib.get("text") or "").strip()
        if text in NETWORK_SELECT_PAGE_MARKERS:
            return True
    return False


def _collect_ui_labels(xml_path: Path) -> list[str]:
    if not xml_path.is_file():
        return []
    root = ET.parse(xml_path).getroot()
    labels: list[str] = []
    seen: set[str] = set()
    for el in root.iter("node"):
        text = (el.attrib.get("text") or "").strip()
        desc = (el.attrib.get("content-desc") or "").strip()
        for label in (text, desc):
            if label and label not in seen:
                seen.add(label)
                labels.append(label)
    return labels


def _scan_found_in_labels(labels: list[str]) -> bool:
    if any(_has_primary_carrier(label) for label in labels):
        return True
    return any(_looks_like_secondary_scanned_network(label) for label in labels)


def _is_network_searching(labels: list[str]) -> bool:
    for label in labels:
        text = (label or "").strip()
        if not text:
            continue
        low = text.lower()
        if any(marker.lower() in low for marker in NETWORK_SEARCHING_MARKERS):
            return True
    return False


def _read_scan_found_with_scroll(device_id: str, *, max_scrolls: int) -> bool:
    _, screen_h = _get_wm_size(device_id)
    swipe = (*DEFAULT_SWIPE[:4], DEFAULT_SWIPE[4])
    device_scroll_count = 0

    for slide in range(max_scrolls + 1):
        xml_path = dump_current_ui(device_id)
        if xml_path is not None:
            if _scan_found_in_labels(_collect_ui_labels(xml_path)):
                return True
        if slide >= max_scrolls:
            break
        device_scroll_count = _ensure_device_scroll_index(
            device_id,
            slide + 1,
            device_scroll_count,
            swipe,
            DEFAULT_SLEEP_AFTER_SWIPE,
        )
    return False


def _read_scan_complete_with_scroll(device_id: str, *, max_scrolls: int) -> bool:
    """
    搜网完成：界面能识别到运营商/制式结果，且当前不在「正在搜索」状态。

    关闭自动搜网后，页面可能仍短暂保留旧列表；若同时显示「正在搜索」则不算完成。
    """
    _, screen_h = _get_wm_size(device_id)
    swipe = (*DEFAULT_SWIPE[:4], DEFAULT_SWIPE[4])
    device_scroll_count = 0

    for slide in range(max_scrolls + 1):
        xml_path = dump_current_ui(device_id)
        if xml_path is not None:
            labels = _collect_ui_labels(xml_path)
            if not _is_network_searching(labels) and _scan_found_in_labels(labels):
                return True
        if slide >= max_scrolls:
            break
        device_scroll_count = _ensure_device_scroll_index(
            device_id,
            slide + 1,
            device_scroll_count,
            swipe,
            DEFAULT_SLEEP_AFTER_SWIPE,
        )
    return False


def enter_network_select_screen(device_id: str) -> bool:
    """
    在当前页面点击「选择网络」菜单，进入选择网络子界面。

    调用方需先自行进入对应 SIM 卡子界面。

    参数:
        device_id: 设备 adb 序列号。

    返回:
        成功进入选择网络页为 True，否则 False。
    """
    if not device_id:
        return False

    if not click_by_match_keywords(
        device_id,
        CHOOSE_NETWORK_KEYWORDS,
        prefer_cached_ui=False,
        max_scrolls=DEFAULT_MAX_SCROLLS,
    ):
        return False
    if PAGE_SETTLE_SECONDS > 0:
        time.sleep(PAGE_SETTLE_SECONDS)

    xml_path = dump_current_ui(device_id)
    if xml_path is None:
        return False
    return _page_has_network_select_title(xml_path)


def set_auto_select_network(device_id: str, enable: EnableTarget) -> bool:
    """
    切换「自动选择网络」开关至目标状态。

    关闭时会弹出确认框，本方法会自动点击「确定/确认」。
    打开时无确认框。

    参数:
        device_id: 设备 adb 序列号。
        enable: True 打开 / False 关闭（也支持 1/0、「打开」「关闭」等）。

    返回:
        最终状态符合目标为 True，否则 False。
    """
    if not device_id:
        return False

    target = normalize_enable(enable)
    if target is None:
        return False

    xml_path = dump_current_ui(device_id)
    if xml_path is None:
        return False

    checked = _read_auto_select_checked(xml_path)
    if checked is None:
        return False
    if checked == target:
        return True

    if not _tap_auto_select_switch(device_id, xml_path):
        return False
    if SETTLE_AFTER_TAP > 0:
        time.sleep(SETTLE_AFTER_TAP)

    if not target:
        if DIALOG_SETTLE_SECONDS > 0:
            time.sleep(DIALOG_SETTLE_SECONDS)
        if not click_dialog_confirm(device_id):
            return False
        if SETTLE_AFTER_TAP > 0:
            time.sleep(SETTLE_AFTER_TAP)

    xml_path = dump_current_ui(device_id)
    if xml_path is None:
        return False
    checked_after = _read_auto_select_checked(xml_path)
    if checked_after is None:
        return not target
    return checked_after == target


def check_network_scan_found(device_id: str) -> bool:
    """
    检查当前「选择网络」页面是否出现运营商/制式文案（不区分是否仍在搜网中）。

    优先匹配「中国移动」「中国联通」；未命中时再匹配其他运营商或带制式文案。
    手动搜网轮询请使用 ``check_network_scan_complete`` / ``poll_network_scan_found``。
    """
    if not device_id:
        return False
    return _read_scan_found_with_scroll(device_id, max_scrolls=DEFAULT_MAX_SCROLLS)


def check_network_scan_complete(device_id: str) -> bool:
    """
    检查手动搜网是否已完成：有运营商/制式结果，且界面不在「正在搜索」状态。
    """
    if not device_id:
        return False
    return _read_scan_complete_with_scroll(device_id, max_scrolls=DEFAULT_MAX_SCROLLS)


def poll_network_scan_found(
    device_id: str,
    *,
    interval_seconds: float = NETWORK_SCAN_POLL_INTERVAL_SECONDS,
    max_attempts: int = NETWORK_SCAN_POLL_MAX_ATTEMPTS,
    initial_delay_seconds: float = NETWORK_SCAN_INITIAL_DELAY_SECONDS,
) -> bool:
    """
    关闭自动搜网后轮询检查结果。

    先等待 initial_delay_seconds（默认 10s），再开始检查；之后每 interval_seconds
    检查一次，共 max_attempts 次。任意一次 ``check_network_scan_complete`` 为 True
    即成功。调用方应停留在「选择网络」页面。
    """
    if not device_id or max_attempts <= 0:
        return False
    if initial_delay_seconds > 0:
        time.sleep(initial_delay_seconds)
    for attempt in range(max_attempts):
        if check_network_scan_complete(device_id):
            return True
        if attempt < max_attempts - 1 and interval_seconds > 0:
            time.sleep(interval_seconds)
    return False
