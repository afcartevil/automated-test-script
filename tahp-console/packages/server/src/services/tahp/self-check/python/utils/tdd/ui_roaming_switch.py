"""SIM 详情页「数据漫游」开关：打开（含确认弹框）或关闭。"""

import subprocess
import time
from typing import Optional, Union

from utils.tdd.ui_automatic import (
    DEFAULT_MAX_SCROLLS,
    DEFAULT_SWIPE,
    click_dialog_confirm,
)
from utils.tdd.ui_switch import EnableTarget, normalize_enable
from utils.tdd.ui_u2 import dump_current_ui
from utils.tdd.ui_xml import (
    build_parent_map,
    clickable_tap_target,
    find_labeled_switch_in_root,
    switch_in_subtree,
    switch_is_checked,
    tap_target_center,
)

SETTLE_AFTER_TAP = 0.8
SETTLE_AFTER_SCROLL = 0.85

ROAMING_LABEL_KEYWORDS = ("数据漫游", "国际漫游", "漫游")
ROAMING_SWITCH_RID_MARKERS = ("button_roaming", "roaming_key", "data_roaming")


def _is_roaming_row_label(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) > 24:
        return False
    if any(k in t for k in ROAMING_LABEL_KEYWORDS):
        return True
    low = t.lower()
    return low == "roaming" or low.startswith("roaming ")


def _find_roaming_switch_in_root(root):
    parent_map = build_parent_map(root)
    for el in root.iter("node"):
        rid = (el.attrib.get("resource-id") or "").lower()
        if switch_in_subtree(el) and any(m in rid for m in ROAMING_SWITCH_RID_MARKERS):
            switch_node = switch_in_subtree(el)
            if switch_node is not None:
                label = (el.attrib.get("text") or el.attrib.get("content-desc") or "漫游").strip()
                return clickable_tap_target(el, parent_map), switch_node, label

    return find_labeled_switch_in_root(root, _is_roaming_row_label)


def _swipe_page_down(device_id: str) -> bool:
    x1, y1, x2, y2, duration_ms = DEFAULT_SWIPE
    result = subprocess.run(
        ["adb", "-s", device_id, "shell", "input", "swipe", x1, y1, x2, y2, str(duration_ms)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.returncode == 0


def _dump_find_roaming_switch(
    device_id: str,
    *,
    max_scrolls: int = DEFAULT_MAX_SCROLLS,
):
    import xml.etree.ElementTree as ET

    for slide in range(max(0, max_scrolls) + 1):
        xml_path = dump_current_ui(device_id)
        if xml_path is None:
            return None, None
        root = ET.parse(xml_path).getroot()
        pair = _find_roaming_switch_in_root(root)
        if pair is not None:
            return pair, xml_path
        if slide >= max_scrolls:
            break
        _swipe_page_down(device_id)
        if SETTLE_AFTER_SCROLL > 0:
            time.sleep(SETTLE_AFTER_SCROLL)
    return None, None


def _tap_screen(device_id: str, x: int, y: int) -> bool:
    result = subprocess.run(
        ["adb", "-s", device_id, "shell", "input", "tap", str(x), str(y)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.returncode == 0


def _tap_roaming_switch(device_id: str, pair) -> bool:
    center = tap_target_center(pair[0], pair[1])
    if center is None:
        return False
    return _tap_screen(device_id, center[0], center[1])


def set_roaming_enable(
    device_id: str,
    enable: EnableTarget,
    *,
    max_scrolls: int = DEFAULT_MAX_SCROLLS,
) -> bool:
    """
    在当前 SIM 详情页切换「数据漫游」至目标状态。

    打开漫游时会尝试点击确认弹框；关闭漫游无需确认。
    """
    if not device_id:
        return False

    target = normalize_enable(enable)
    if target is None:
        return False

    pair, _ = _dump_find_roaming_switch(device_id, max_scrolls=max_scrolls)
    if pair is None:
        return False

    checked = switch_is_checked(pair[1])
    if checked == target:
        return True

    if not _tap_roaming_switch(device_id, pair):
        return False
    if SETTLE_AFTER_TAP > 0:
        time.sleep(SETTLE_AFTER_TAP)

    if target:
        click_dialog_confirm(device_id)

    verify_pair, _ = _dump_find_roaming_switch(device_id, max_scrolls=max_scrolls)
    if verify_pair is None:
        return False
    return switch_is_checked(verify_pair[1]) == target
