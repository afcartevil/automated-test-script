import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from utils.tdd.ui_u2 import dump_current_ui
from utils.tdd.ui_xml import build_parent_map

DATA_CARD_KEYWORD = "上网卡"
DIAL_CARD_KEYWORD = "拨号卡"


def _row_state_for_keyword(xml_path: Path, keyword: str) -> Optional[bool]:
    if not xml_path.is_file():
        return None
    root = ET.parse(xml_path).getroot()
    parent_map = build_parent_map(root)

    for el in root.iter("node"):
        text = (el.attrib.get("text") or "").strip()
        desc = (el.attrib.get("content-desc") or "").strip()
        label = f"{text} {desc}".strip()
        if keyword not in label:
            continue

        # 列表项通常在父节点上体现 enable/clickable 状态，优先检查父节点。
        row = parent_map.get(el) or el
        enabled = (row.attrib.get("enabled") or "").strip().lower()
        if enabled in ("true", "false"):
            return enabled == "true"

        clickable = (row.attrib.get("clickable") or "").strip().lower()
        if clickable in ("true", "false"):
            return clickable == "true"

        # 未读到明确状态时，默认认为可用。
        return True
    return None


def check_data_and_dial_card_enabled(device_id: str, expected_enabled: bool) -> bool:
    """
    检查「SIM卡与网络设置」页面中：
    - 上网卡
    - 拨号卡
    两项是否处于期望状态。

    expected_enabled=True 表示应不置灰（可用）
    expected_enabled=False 表示应置灰（不可用）
    """
    if not device_id:
        return False
    xml_path = dump_current_ui(device_id)
    if xml_path is None:
        return False

    data_enabled = _row_state_for_keyword(xml_path, DATA_CARD_KEYWORD)
    dial_enabled = _row_state_for_keyword(xml_path, DIAL_CARD_KEYWORD)
    if data_enabled is None or dial_enabled is None:
        return False
    return data_enabled == expected_enabled and dial_enabled == expected_enabled


def check_data_card_enabled(device_id: str, expected_enabled: bool) -> tuple[bool, str]:
    """
    检查「SIM卡与网络设置」页面「上网卡」菜单是否处于期望状态。

    expected_enabled=True 表示应不置灰（可用）。
    """
    if not device_id:
        return False, "device_id 为空"

    xml_path = dump_current_ui(device_id)
    if xml_path is None:
        return False, "无法通过 u2 dump 当前界面"

    data_enabled = _row_state_for_keyword(xml_path, DATA_CARD_KEYWORD)
    if data_enabled is None:
        return False, "未找到上网卡菜单"

    if data_enabled == expected_enabled:
        return True, ""

    if expected_enabled:
        return False, "上网卡菜单仍为置灰"
    return False, "上网卡菜单应置灰但仍可操作"
