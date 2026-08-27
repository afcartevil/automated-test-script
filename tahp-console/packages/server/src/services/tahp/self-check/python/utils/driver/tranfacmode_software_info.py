"""从工模「软件信息」页读取 IMEI（供 pipeline_adapt/tdd 用例复用）。

链路：MainActivity → menu_drawer → 软件信息 → 解析 IMEI号。
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from utils.driver.tranfacmode_ui import (
    TAP_DELAY,
    adb,
    dump,
    poll_bool,
    tap_xml,
)
from utils.driver.ui_tranfacmode import close_tranfacmode, start_main
from utils.tdd.ui_automatic import ensure_screen_on_and_unlocked

PKG = "com.transsion.tranfacmode"
RID_MENU_DRAWER = f"{PKG}:id/menu_drawer"
RID_SOFTWARE_INFO = f"{PKG}:id/menu_software_info"
RID_ADAPTER_TITLE = f"{PKG}:id/adapter_title"
RID_ADAPTER_SUMMARY = f"{PKG}:id/adapter_summary"
TITLE_SOFTWARE_INFO = ("软件信息", "Software info", "Software Info")
IMEI_TITLE = ("IMEI号", "IMEI", "IMEI Number")
IMEI_LINE_RE = re.compile(r"IMEI\s*([12])\s*[:：]\s*([0-9]{14,17})", re.I)
IMEI_DIGIT_RE = re.compile(r"\b([0-9]{14,17})\b")


def _ui_has_title(xml: Path, titles: tuple[str, ...]) -> bool:
    for el in ET.parse(xml).getroot().iter("node"):
        text = (el.attrib.get("text") or "").strip()
        if text in titles:
            return True
    return False


def _parent_map(root: ET.Element) -> dict:
    parent: dict = {}
    for node in root.iter():
        for child in list(node):
            parent[child] = node
    return parent


def _parse_imei_from_xml(xml: Path) -> str:
    """从软件信息页 XML 提取 IMEI；优先「IMEI号」旁的 summary。"""
    root = ET.parse(xml).getroot()
    parent = _parent_map(root)

    for el in root.iter("node"):
        rid = el.attrib.get("resource-id") or ""
        text = (el.attrib.get("text") or "").strip()
        if "adapter_title" not in rid:
            continue
        if text not in IMEI_TITLE and "IMEI" not in text.upper():
            continue
        node = parent.get(el)
        if node is None:
            continue
        for child in node.iter("node"):
            crid = child.attrib.get("resource-id") or ""
            if "adapter_summary" not in crid:
                continue
            summary = (child.attrib.get("text") or "").strip()
            if summary:
                return _normalize_imei_text(summary)

    # 兜底：整页文本里找 IMEI1/IMEI2
    blob = "\n".join(
        (n.attrib.get("text") or "").strip()
        for n in root.iter("node")
        if (n.attrib.get("text") or "").strip()
    )
    return _normalize_imei_text(blob)


def _normalize_imei_text(raw: str) -> str:
    pairs: list[tuple[str, str]] = []
    for m in IMEI_LINE_RE.finditer(raw):
        pairs.append((m.group(1), m.group(2)))
    if pairs:
        # 去重保序
        seen = set()
        lines = []
        for idx, val in pairs:
            key = f"{idx}:{val}"
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"IMEI{idx}: {val}")
        return "\n".join(lines)

    digits = []
    seen = set()
    for m in IMEI_DIGIT_RE.finditer(raw):
        val = m.group(1)
        if val in seen:
            continue
        # 排除明显是 SN（常见以机型 SN 长度混入）；IMEI 一般为 15 位
        if len(val) < 14:
            continue
        seen.add(val)
        digits.append(val)
    if not digits:
        return ""
    if len(digits) == 1:
        return f"IMEI1: {digits[0]}"
    return "\n".join(f"IMEI{i}: {v}" for i, v in enumerate(digits[:2], start=1))


def extract_imei_values(imei_text: str) -> list[str]:
    """从规范化 IMEI 文本中提取数字串列表。"""
    text = (imei_text or "").strip()
    if not text:
        return []
    values: list[str] = []
    for m in IMEI_LINE_RE.finditer(text):
        values.append(m.group(2))
    if values:
        return values
    return [m.group(1) for m in IMEI_DIGIT_RE.finditer(text)]


def is_imei_value_valid(value: str) -> bool:
    """IMEI 有效：非空数字串，且不能全是 0。"""
    digits = re.sub(r"\D", "", value or "")
    if not digits:
        return False
    return any(ch != "0" for ch in digits)


def validate_imei_text(imei_text: str) -> tuple[bool, str]:
    """
    校验读取到的 IMEI 文本。
    通过：(非空) 且每组号码均非空、不全为 0。
    返回 (ok, reason)；ok 时 reason 为空。
    """
    values = extract_imei_values(imei_text)
    if not values:
        return False, "未读取到IMEI号"
    invalid = [v for v in values if not is_imei_value_valid(v)]
    if invalid:
        return False, f"IMEI号无效（为空或全是0）: {', '.join(invalid)}"
    return True, ""


def _open_software_info(device_id: str) -> bool:
    xml = dump(device_id)
    if not xml:
        return False
    if not tap_xml(device_id, xml, resource_id=RID_MENU_DRAWER):
        return False
    time.sleep(TAP_DELAY)

    xml = dump(device_id)
    if not xml:
        return False
    if tap_xml(device_id, xml, resource_id=RID_SOFTWARE_INFO):
        return True
    return tap_xml(device_id, xml, text_equals=TITLE_SOFTWARE_INFO)


def _scroll_for_imei(device_id: str) -> Optional[Path]:
    """若当前屏无 IMEI，向下滑几次再 dump。"""
    for _ in range(4):
        xml = dump(device_id)
        if not xml:
            return None
        if _parse_imei_from_xml(xml):
            return xml
        # 上滑内容（手指从下往上）
        adb(device_id, "shell", "input", "swipe", "540", "1800", "540", "800", "350")
        time.sleep(TAP_DELAY)
    return dump(device_id)


def get_imei_from_factory_software_info(device_id: str, result_dir=None) -> str:
    """
    工模主界面 → 右上角更多 → 软件信息 → 读取 IMEI号。
    成功返回规范化文本（含 IMEI1/IMEI2）；失败返回空串。
    """
    if result_dir:
        from utils.tdd.ui_paths import set_ui_result_dir
        set_ui_result_dir(result_dir)

    ensure_screen_on_and_unlocked(device_id)
    close_tranfacmode(device_id)
    time.sleep(0.3)

    if not start_main(device_id):
        return ""

    if not _open_software_info(device_id):
        return ""

    def software_info_ready() -> bool:
        xml = dump(device_id)
        return bool(xml and _ui_has_title(xml, TITLE_SOFTWARE_INFO))

    if not poll_bool(software_info_ready, 8.0, 0.4):
        return ""

    xml = _scroll_for_imei(device_id)
    if not xml:
        return ""
    return _parse_imei_from_xml(xml)
