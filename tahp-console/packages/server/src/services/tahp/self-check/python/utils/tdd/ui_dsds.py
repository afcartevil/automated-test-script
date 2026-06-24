"""手机信息页 DSDS 开关操作与置灰检查（对齐 scripts/run_case2_dsds.py）。"""

import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from utils.tdd.ui_automatic import (
    DEFAULT_SLEEP_AFTER_SWIPE,
    _parse_bounds_center,
    _swipe_down,
    _tap_screen,
    dump_current_ui,
)

DSDS_SWITCH_ID = "com.android.phone:id/dsds_switch"

PAGE_SETTLE_SECONDS = 2.0
TOGGLE_SETTLE_SECONDS = 3.0
MAX_LOCATE_SCROLLS = 6
MAX_TOGGLE_RETRIES = 2
DSDS_SWIPE = ("360", "1300", "360", "500", 300)


def _find_dsds_switch(xml_path: Path) -> Optional[ET.Element]:
    if not xml_path.is_file():
        return None
    root = ET.parse(xml_path).getroot()
    for node in root.iter("node"):
        if node.attrib.get("resource-id") == DSDS_SWITCH_ID:
            return node
    return None


def _build_parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    parent: dict[ET.Element, ET.Element] = {}
    for node in root.iter():
        for child in list(node):
            parent[child] = node
    return parent


def _attrib_bool(node: ET.Element, key: str) -> Optional[bool]:
    value = (node.attrib.get(key) or "").strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def _is_switch_grayed(switch_node: ET.Element, parent_map: dict[ET.Element, ET.Element]) -> Optional[bool]:
    """
    判断开关是否置灰不可操作。

    返回 True=置灰，False=可操作，None=无法判定。
    """
    switch_enabled = _attrib_bool(switch_node, "enabled")
    if switch_enabled is False:
        return True
    if switch_enabled is True:
        return False

    row = parent_map.get(switch_node)
    if row is not None:
        row_enabled = _attrib_bool(row, "enabled")
        if row_enabled is False:
            return True
        if row_enabled is True:
            return False

    return None


def is_dsds_switch_grayed_out(device_id: str) -> bool:
    """
    在手机信息页检查 DSDS 开关是否为置灰（不可点击/不可用）状态。

    展锐平台用例要求：用户不可关闭 DSDS，开关应置灰。
    """
    if not device_id:
        return False

    node, xml_path = _locate_dsds_switch(device_id)
    if node is None or xml_path is None:
        return False

    root = ET.parse(xml_path).getroot()
    parent_map = _build_parent_map(root)
    grayed = _is_switch_grayed(node, parent_map)
    return grayed is True


def _locate_dsds_switch(device_id: str) -> tuple[Optional[ET.Element], Optional[Path]]:
    swipe = (*DSDS_SWIPE[:4], DSDS_SWIPE[4])
    for slide in range(MAX_LOCATE_SCROLLS + 1):
        xml_path = dump_current_ui(device_id)
        if xml_path is not None:
            node = _find_dsds_switch(xml_path)
            if node is not None:
                return node, xml_path
        if slide >= MAX_LOCATE_SCROLLS:
            break
        _swipe_down(device_id, swipe)
        if DEFAULT_SLEEP_AFTER_SWIPE > 0:
            time.sleep(DEFAULT_SLEEP_AFTER_SWIPE)
    return None, None


def ensure_dsds_switch_state(device_id: str, expected_checked: bool) -> bool:
    """
    将 DSDS 开关设为 expected_checked（True=开启 / False=关闭）。

    与 scripts/run_case2_dsds.ensure_state 行为一致。
    """
    if not device_id:
        return False

    for _attempt in range(MAX_TOGGLE_RETRIES + 1):
        node, _xml_path = _locate_dsds_switch(device_id)
        if node is None:
            continue

        current = node.attrib.get("checked") == "true"
        bounds = node.attrib.get("bounds", "")
        if not bounds:
            continue
        try:
            x, y = _parse_bounds_center(bounds)
        except ValueError:
            continue

        if current == expected_checked:
            return True

        if not _tap_screen(device_id, x, y):
            continue
        if TOGGLE_SETTLE_SECONDS > 0:
            time.sleep(TOGGLE_SETTLE_SECONDS)

        verify_node, _ = _locate_dsds_switch(device_id)
        if verify_node is None:
            continue
        if (verify_node.attrib.get("checked") == "true") == expected_checked:
            return True

    return False
