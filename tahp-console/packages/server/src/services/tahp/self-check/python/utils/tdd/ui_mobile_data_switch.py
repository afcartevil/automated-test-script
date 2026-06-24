"""「SIM 卡与网络设置」页「移动数据」开关置灰/可用检查。"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from utils.tdd.ui_automatic import dump_current_ui
from utils.tdd.ui_xml import build_parent_map as _build_parent_map
from utils.tdd.ui_xml import switch_in_subtree as _switch_in_subtree

# 仅匹配「移动数据」标题本身，避免命中「自动切换移动数据」「移动数据用量」等。
EXACT_MOBILE_DATA_LABELS = frozenset(
    {
        "移动数据",
        "Mobile data",
        "Cellular data",
        "行動數據",
    }
)

MOBILE_DATA_SWITCH_RID_MARKERS = (
    "mobile_data_enable",
    "mobile_data_switch",
    "switch_mobile_data",
)


def _attrib_bool(node: ET.Element, key: str) -> Optional[bool]:
    value = (node.attrib.get(key) or "").strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def _is_mobile_data_title(text: str) -> bool:
    return (text or "").strip() in EXACT_MOBILE_DATA_LABELS


def _is_switch_class(node: ET.Element) -> bool:
    return "Switch" in (node.attrib.get("class") or "")


def _is_switch_grayed(
    switch_node: ET.Element, parent_map: dict[ET.Element, ET.Element]
) -> Optional[bool]:
    """
    判断开关是否置灰。

    仅以 Switch 控件及紧邻 preference 行的 enabled 为准；
    不使用 clickable（Switch 行父节点常为 clickable=false，会误判置灰）。
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


def _find_mobile_data_switch_by_rid(root: ET.Element) -> Optional[ET.Element]:
    for el in root.iter("node"):
        if not _is_switch_class(el):
            continue
        rid = (el.attrib.get("resource-id") or "").lower()
        if any(marker in rid for marker in MOBILE_DATA_SWITCH_RID_MARKERS):
            return el
    return None


def _find_mobile_data_switch_by_label(
    root: ET.Element, parent_map: dict[ET.Element, ET.Element]
) -> Optional[ET.Element]:
    for el in root.iter("node"):
        label = (el.attrib.get("text") or "").strip()
        if not _is_mobile_data_title(label):
            continue
        parent = parent_map.get(el)
        for search_root in (parent, el):
            if search_root is None:
                continue
            switch_node = _switch_in_subtree(search_root)
            if switch_node is not None:
                return switch_node
    return None


def _find_mobile_data_switch(xml_path: Path) -> Optional[ET.Element]:
    if not xml_path.is_file():
        return None
    root = ET.parse(xml_path).getroot()
    parent_map = _build_parent_map(root)
    return _find_mobile_data_switch_by_rid(root) or _find_mobile_data_switch_by_label(
        root, parent_map
    )


def check_mobile_data_switch_grayed(
    device_id: str,
    expected_grayed: bool,
) -> tuple[bool, str]:
    """
    在当前「SIM 卡与网络设置」界面检查「移动数据」开关是否置灰。

    参数:
        expected_grayed: True 表示期望置灰，False 表示期望可操作（不置灰）。

    返回:
        (是否通过, 失败说明)。
    """
    if not device_id:
        return False, "device_id 为空"

    xml_path = dump_current_ui(device_id)
    if xml_path is None:
        return False, "无法通过 u2 dump 当前界面"

    switch_node = _find_mobile_data_switch(xml_path)
    if switch_node is None:
        return False, "未找到移动数据开关"

    root = ET.parse(xml_path).getroot()
    parent_map = _build_parent_map(root)
    grayed = _is_switch_grayed(switch_node, parent_map)
    if grayed is None:
        enabled_attr = switch_node.attrib.get("enabled", "")
        return False, f"无法判断移动数据开关是否置灰(enabled={enabled_attr!r})"

    if grayed == expected_grayed:
        return True, ""

    enabled_attr = switch_node.attrib.get("enabled", "")
    if expected_grayed:
        return False, f"移动数据开关未置灰(switch.enabled={enabled_attr!r})"
    return False, f"移动数据开关仍为置灰(switch.enabled={enabled_attr!r})"
