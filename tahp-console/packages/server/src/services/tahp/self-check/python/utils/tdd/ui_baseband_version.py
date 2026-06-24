"""读取设置「我的手机」→「Android 版本」页中的基带版本号。"""

import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from utils.tdd.ui_automatic import (
    DEFAULT_MAX_SCROLLS,
    DEFAULT_SLEEP_AFTER_SWIPE,
    DEFAULT_SWIPE,
    _ensure_device_scroll_index,
    _get_wm_size,
    click_by_match_keywords,
    dump_current_ui,
)
from utils.tdd.ui_settings_activity import enter_my_phone_settings_by_adb

ANDROID_VERSION_KEYWORDS = ("Android 版本", "Android version")
BASEBAND_TITLE_MARKERS = ("基带版本", "基頻版本", "Baseband version")
INVALID_SUMMARY_VALUES = frozenset(
    {
        "",
        "未知",
        "Unknown",
        "Unavailable",
        "N/A",
    }
)
PAGE_SETTLE_SECONDS = 1.0


def _build_parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    parent: dict[ET.Element, ET.Element] = {}
    for node in root.iter():
        for child in list(node):
            parent[child] = node
    return parent


def _is_baseband_title(text: str) -> bool:
    label = (text or "").strip()
    if not label:
        return False
    return any(marker in label for marker in BASEBAND_TITLE_MARKERS)


def _normalize_summary(text: str) -> str:
    value = (text or "").strip()
    if value in INVALID_SUMMARY_VALUES:
        return ""
    return value


def _pick_summary_candidate(candidates: list[str]) -> str:
    if not candidates:
        return ""
    for item in candidates:
        if re.search(r"[\d.A-Za-z_-]", item):
            return item
    return candidates[0]


def _summary_from_preference_row(
    title_el: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
) -> str:
    row = parent_map.get(title_el)
    if row is None:
        return ""

    summary_by_rid: list[str] = []
    fallback: list[str] = []
    title_label = (title_el.attrib.get("text") or "").strip()

    for el in row.iter("node"):
        text = (el.attrib.get("text") or "").strip()
        if not text or text == title_label or _is_baseband_title(text):
            continue
        rid = el.attrib.get("resource-id") or ""
        if "summary" in rid:
            summary_by_rid.append(text)
        elif "title" not in rid:
            fallback.append(text)

    for item in summary_by_rid:
        normalized = _normalize_summary(item)
        if normalized:
            return normalized
    return _normalize_summary(_pick_summary_candidate(fallback))


def _parse_baseband_from_xml(xml_path: Path) -> str:
    if not xml_path.is_file():
        return ""

    root = ET.parse(xml_path).getroot()
    parent_map = _build_parent_map(root)
    for el in root.iter("node"):
        text = (el.attrib.get("text") or "").strip()
        if not _is_baseband_title(text):
            continue
        return _summary_from_preference_row(el, parent_map)
    return ""


def _read_baseband_on_screen(device_id: str, *, max_scrolls: int) -> str:
    _, screen_h = _get_wm_size(device_id)
    swipe = (*DEFAULT_SWIPE[:4], DEFAULT_SWIPE[4])
    device_scroll_count = 0

    for slide in range(max_scrolls + 1):
        xml_path = dump_current_ui(device_id)
        if xml_path is not None:
            value = _parse_baseband_from_xml(xml_path)
            if value:
                return value
        if slide >= max_scrolls:
            break
        device_scroll_count = _ensure_device_scroll_index(
            device_id,
            slide + 1,
            device_scroll_count,
            swipe,
            DEFAULT_SLEEP_AFTER_SWIPE,
        )
    return ""


def get_baseband_version(device_id: str) -> str:
    """
    进入「我的手机」→「Android 版本」，读取「基带版本」摘要文本。

    参数:
        device_id: 设备 adb 序列号。

    返回:
        读到的基带版本字符串；未读到返回空字符串。
    """
    if not device_id:
        return ""

    if not enter_my_phone_settings_by_adb(device_id):
        return ""
    if PAGE_SETTLE_SECONDS > 0:
        time.sleep(PAGE_SETTLE_SECONDS)

    if not click_by_match_keywords(
        device_id,
        ANDROID_VERSION_KEYWORDS,
        prefer_cached_ui=False,
        max_scrolls=DEFAULT_MAX_SCROLLS,
    ):
        return ""
    if PAGE_SETTLE_SECONDS > 0:
        time.sleep(PAGE_SETTLE_SECONDS)

    return _read_baseband_on_screen(device_id, max_scrolls=DEFAULT_MAX_SCROLLS)
