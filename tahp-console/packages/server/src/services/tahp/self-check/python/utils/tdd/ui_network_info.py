"""快捷设置（下拉状态栏）中读取指定 SIM 卡网络状态信息。"""

from __future__ import annotations

import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from utils.tdd.ui_automatic import (
    close_quick_settings,
    dump_current_ui,
    open_quick_settings,
)

QS_STATUS_ICONS_RID = "com.android.systemui:id/qs_status_icons"
SLOT_CONTAINER_RIDS = (
    (0, "com.android.systemui:id/start_side_container_one"),
    (1, "com.android.systemui:id/start_side_container_second"),
)
MOBILE_COMBO_RID = "com.android.systemui:id/mobile_combo"

NETWORK_TYPE_PATTERN = re.compile(
    r"\b(5G|4G\+?|LTE|3G|2G|NR)\b",
    re.IGNORECASE,
)

VOLTE_RID_KEYWORDS = ("ims_indicator", "volte", "vonr", "hd_voice")
VOWIFI_RID_KEYWORDS = ("vowifi", "wfc_indicator", "iwlan", "wifi_calling")
VOWIFI_DESC_PATTERN = re.compile(
    r"vowifi|vo\s*wifi|wifi\s*calling|wi-?fi\s*通话|wlan\s*通话",
    re.IGNORECASE,
)
AIRPLANE_ICON_RID_KEYWORDS = ("airplane", "flight")
AIRPLANE_CONTAINER_RID = "com.android.systemui:id/airplane_container"
AIRPLANE_TEXT_PATTERN = re.compile(
    r"飞行模式|飞行|airplane|flight\s*mode|plane\s*mode",
    re.IGNORECASE,
)

CARRIER_DESC_SPLIT = re.compile(r"[，,]")


@dataclass
class SimNetworkInfo:
    slot_index: int
    carrier_name: str = ""
    network_type: str = ""
    volte: bool = False
    vowifi: bool = False
    raw_texts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_index": self.slot_index,
            "carrier_name": self.carrier_name,
            "network_type": self.network_type,
            "volte": self.volte,
            "vowifi": self.vowifi,
            "raw_texts": list(self.raw_texts),
        }


def normalize_sim_slot(sim_slot) -> Optional[int]:
    """卡1/SIM1/1/0 -> 0；卡2/SIM2/2/1 -> 1（与 call.py 卡槽编号一致）。"""
    if sim_slot in (0, "0", "卡1", "SIM1", "sim1"):
        return 0
    if sim_slot in (1, "1", "卡1", "SIM1", "sim1"):
        return 0
    if sim_slot in (2, "2", "卡2", "SIM2", "sim2"):
        return 1
    text = str(sim_slot or "").strip()
    upper = text.upper()
    if upper in ("SIM1", "SLOT0", "SUB0") or text == "卡1":
        return 0
    if upper in ("SIM2", "SLOT1", "SUB1") or text == "卡2":
        return 1
    try:
        value = int(text)
    except ValueError:
        return None
    if value in (0, 1):
        return 0
    if value == 2:
        return 1
    return None


def _parse_bounds(bounds: str) -> Optional[tuple[int, int, int, int]]:
    if not bounds:
        return None
    chunks = bounds.replace("][", ",").replace("[", "").replace("]", "").split(",")
    if len(chunks) != 4:
        return None
    try:
        return tuple(int(v) for v in chunks)
    except ValueError:
        return None


def _is_visible_bounds(bounds: str) -> bool:
    parsed = _parse_bounds(bounds)
    if parsed is None:
        return False
    x1, y1, x2, y2 = parsed
    return (x2 - x1) > 0 and (y2 - y1) > 0


def _find_first_by_rid(root: ET.Element, rid: str) -> Optional[ET.Element]:
    for el in root.iter("node"):
        if (el.attrib.get("resource-id") or "") == rid:
            return el
    return None


def _find_mobile_combo_in(container: ET.Element) -> Optional[ET.Element]:
    for el in container.iter("node"):
        if (el.attrib.get("resource-id") or "") == MOBILE_COMBO_RID:
            return el
    return None


def _normalize_network_type(*values: str) -> str:
    for value in values:
        if not value:
            continue
        match = NETWORK_TYPE_PATTERN.search(value.replace(" ", ""))
        if match:
            token = match.group(1).upper()
            return "5G" if token == "NR" else token
    return ""


def _carrier_from_combo_desc(desc: str) -> str:
    if not desc:
        return ""
    head = CARRIER_DESC_SPLIT.split(desc.strip())[0].strip()
    if NETWORK_TYPE_PATTERN.search(head.replace(" ", "")):
        return ""
    if re.search(r"信号|signal|battery|电池|百分之", head, re.I):
        return ""
    return head


def _parse_mobile_combo(combo: ET.Element, slot_index: int) -> SimNetworkInfo:
    """解析单个 mobile_combo（状态栏 SIM 行，含图标节点）。"""
    carrier = ""
    network_type = ""
    volte = False
    vowifi = False
    texts: list[str] = []

    combo_desc = (combo.attrib.get("content-desc") or "").strip()
    if combo_desc:
        texts.append(combo_desc)
        carrier = _carrier_from_combo_desc(combo_desc)

    for el in combo.iter("node"):
        rid = (el.attrib.get("resource-id") or "").lower()
        text = (el.attrib.get("text") or "").strip()
        desc = (el.attrib.get("content-desc") or "").strip()
        bounds = (el.attrib.get("bounds") or "").strip()
        if not _is_visible_bounds(bounds):
            continue

        if text:
            texts.append(text)
        if desc:
            texts.append(desc)

        if "stat_carrier_name" in rid and text:
            carrier = text
        if "mobile_type" in rid:
            network_type = _normalize_network_type(desc, text) or network_type

        rid_blob = rid
        desc_blob = (desc or "").lower()
        if any(key in rid_blob for key in VOLTE_RID_KEYWORDS):
            volte = True
        if any(key in rid_blob for key in VOWIFI_RID_KEYWORDS):
            vowifi = True
        if VOWIFI_DESC_PATTERN.search(desc):
            vowifi = True

    network_type = network_type or _normalize_network_type(*texts)
    if not carrier:
        carrier = _carrier_from_combo_desc(combo_desc)

    return SimNetworkInfo(
        slot_index=slot_index,
        carrier_name=carrier,
        network_type=network_type,
        volte=volte,
        vowifi=vowifi,
        raw_texts=sorted(set(texts)),
    )


def _airplane_icon_visible_in_status_icons(status_icons: ET.Element) -> bool:
    """状态栏区域是否显示飞行模式图标（非空的 airplane 图标节点）。"""
    container = _find_first_by_rid(status_icons, AIRPLANE_CONTAINER_RID)
    if container is not None:
        for el in container.iter("node"):
            if el is container:
                continue
            rid = (el.attrib.get("resource-id") or "").lower()
            if "container" in rid:
                continue
            if not any(key in rid for key in AIRPLANE_ICON_RID_KEYWORDS):
                continue
            if _is_visible_bounds(el.attrib.get("bounds") or ""):
                return True
    for el in status_icons.iter("node"):
        rid = (el.attrib.get("resource-id") or "").lower()
        if "container" in rid:
            continue
        if not any(key in rid for key in AIRPLANE_ICON_RID_KEYWORDS):
            continue
        if _is_visible_bounds(el.attrib.get("bounds") or ""):
            return True
    return False


def _qs_airplane_tile_enabled(root: ET.Element) -> bool:
    """快捷设置里飞行模式磁贴已打开（checked=true）。"""
    for el in root.iter("node"):
        if el.attrib.get("checkable") != "true" or el.attrib.get("checked") != "true":
            continue
        blob = f"{el.attrib.get('text') or ''} {el.attrib.get('content-desc') or ''}"
        if AIRPLANE_TEXT_PATTERN.search(blob):
            return True
    return False


def has_airplane_mode_icon_in_xml(xml_path: Path) -> bool:
    """
    从快捷设置 dump 检测飞行模式是否生效。

    传音 ROM 在关飞行时仍保留空的 ``airplane_container``，且 QS 页有
    「飞行模式」磁贴文案，旧逻辑会误报为已开飞行。
    """
    if not xml_path.is_file():
        return False
    root = ET.parse(xml_path).getroot()
    status_icons = _find_first_by_rid(root, QS_STATUS_ICONS_RID)
    if status_icons is not None and _airplane_icon_visible_in_status_icons(status_icons):
        return True
    return _qs_airplane_tile_enabled(root)


def _sim_status_bar_info_readable(info: SimNetworkInfo) -> bool:
    if info.volte or info.vowifi:
        return True
    if (info.network_type or "").strip():
        return True
    if (info.carrier_name or "").strip():
        return True
    for text in info.raw_texts:
        if NETWORK_TYPE_PATTERN.search((text or "").replace(" ", "")):
            return True
    return False


def read_quick_settings_status(
    device_id: str,
) -> Optional[tuple[bool, dict[int, SimNetworkInfo]]]:
    """
    下拉状态栏，返回 (是否显示飞行模式图标, 各卡槽 SimNetworkInfo)。

    打开/收起快捷设置由本函数负责。
    """
    if not device_id:
        return None
    if not open_quick_settings(device_id):
        return None
    try:
        xml_path = dump_current_ui(device_id)
        if xml_path is None:
            return None
        _archive_dump(xml_path, device_id)
        airplane = has_airplane_mode_icon_in_xml(xml_path)
        sims = parse_quick_settings_all_sims(xml_path)
        return airplane, sims
    finally:
        close_quick_settings(device_id)


def check_quick_settings_airplane_no_sim_info(
    device_id: str,
    expected_slots: int = 2,
) -> tuple[bool, str]:
    """
    飞行模式下：应显示飞行模式图标，且不应读到双卡驻网 SIM 信息（无 VoLTE/制式等）。
    """
    if not device_id or expected_slots < 1:
        return False, "device_id 无效"

    status = read_quick_settings_status(device_id)
    if status is None:
        return False, "无法读取状态栏信息"

    airplane_on, all_sims = status
    if not airplane_on:
        return False, "状态栏未显示飞行模式图标"

    readable_slots: list[str] = []
    for slot_index in range(expected_slots):
        info = all_sims.get(slot_index)
        if info is not None and _sim_status_bar_info_readable(info):
            readable_slots.append(f"卡{slot_index + 1}")

    if readable_slots:
        return False, f"飞行模式下不应读到SIM驻网信息，但读到：{'、'.join(readable_slots)}"
    return True, ""


def parse_quick_settings_all_sims(xml_path: Path) -> dict[int, SimNetworkInfo]:
    """
    从快捷设置界面 dump 解析 qs_status_icons 内各卡槽信息。

    传音/SystemUI 结构（见 network_info_qs_latest.xml）：
    - qs_status_icons / start_side_container_one  -> 卡1
    - qs_status_icons / start_side_container_second -> 卡2
    - mobile_combo 下 stat_carrier_name、mobile_type(content-desc)、ims_indicator(VoLTE 图标)
    """
    result: dict[int, SimNetworkInfo] = {}
    if not xml_path.is_file():
        return result

    root = ET.parse(xml_path).getroot()
    status_icons = _find_first_by_rid(root, QS_STATUS_ICONS_RID)
    if status_icons is None:
        return result

    for slot_index, container_rid in SLOT_CONTAINER_RIDS:
        container = _find_first_by_rid(status_icons, container_rid)
        if container is None:
            result[slot_index] = SimNetworkInfo(slot_index=slot_index)
            continue
        combo = _find_mobile_combo_in(container)
        if combo is None:
            result[slot_index] = SimNetworkInfo(slot_index=slot_index)
            continue
        result[slot_index] = _parse_mobile_combo(combo, slot_index)
    return result


def _archive_dump(xml_path: Path, device_id: str) -> None:
    try:
        from utils.tdd.ui_paths import device_ui_dir

        target = device_ui_dir(device_id) / "network_info_qs_latest.xml"
        shutil.copy2(xml_path, target)
    except OSError:
        pass


def read_all_quick_settings_sim_network_info(
    device_id: str,
    *,
    keep_open: bool = False,
) -> Optional[dict[int, SimNetworkInfo]]:
    """展开快捷设置一次，读取卡1/卡2状态栏信息。"""
    if not device_id:
        return None
    if not open_quick_settings(device_id):
        return None
    try:
        xml_path = dump_current_ui(device_id)
        if xml_path is None:
            return None
        _archive_dump(xml_path, device_id)
        return parse_quick_settings_all_sims(xml_path)
    finally:
        if not keep_open:
            close_quick_settings(device_id)


def check_dual_sim_volte_or_vonr_icons(
    device_id: str,
    expected_slots: int = 2,
) -> tuple[bool, str]:
    """
    下拉状态栏读取双卡 SIM 信息，要求每卡均显示 VoLTE 或 VoNR 图标。

    返回 (是否通过, 失败说明；通过时说明为空字符串)。
    """
    if not device_id or expected_slots < 1:
        return False, "device_id 无效"

    status = read_quick_settings_status(device_id)
    if status is None:
        return False, "无法读取状态栏 SIM 信息"

    airplane_on, all_sims = status
    if airplane_on:
        return False, "状态栏仍显示飞行模式图标"

    missing: list[str] = []
    for slot_index in range(expected_slots):
        info = all_sims.get(slot_index)
        if info is None:
            missing.append(f"卡{slot_index + 1}无状态栏条目")
            continue
        if not info.volte:
            carrier = info.carrier_name or "未知运营商"
            net = info.network_type or "未知网络"
            missing.append(
                f"卡{slot_index + 1}({carrier}/{net})未显示VoLTE或VoNR图标"
            )

    if missing:
        return False, "；".join(missing)
    return True, ""


def check_sim_volte_or_vonr_icon(device_id: str, sim_slot) -> tuple[bool, str]:
    """
    下拉状态栏检查指定 SIM 卡槽是否显示 VoLTE 或 VoNR 图标。

    sim_slot: 0/1、卡1/卡2、SIM1/SIM2 等（与 normalize_sim_slot 一致）。
    """
    if not device_id:
        return False, "device_id 无效"

    slot_index = normalize_sim_slot(sim_slot)
    if slot_index is None:
        return False, f"无效 SIM 槽位: {sim_slot!r}"

    status = read_quick_settings_status(device_id)
    if status is None:
        return False, "无法读取状态栏 SIM 信息"

    airplane_on, all_sims = status
    if airplane_on:
        return False, "状态栏仍显示飞行模式图标"

    info = all_sims.get(slot_index)
    if info is None:
        return False, f"卡{slot_index + 1}无状态栏条目"
    if info.volte:
        return True, ""

    carrier = info.carrier_name or "未知运营商"
    net = info.network_type or "未知网络"
    return False, f"卡{slot_index + 1}({carrier}/{net})未显示VoLTE或VoNR图标"


def read_quick_settings_sim_network_info(
    device_id: str,
    sim_slot,
    *,
    keep_open: bool = False,
) -> Optional[SimNetworkInfo]:
    """
    展开快捷设置 → dump UI → 解析指定 SIM 状态栏信息 → 收起。

    VoLTE/VoWiFi 通过 ims_indicator / vowifi 相关图标节点判断，而非仅文本。
    """
    if not device_id:
        return None
    slot_index = normalize_sim_slot(sim_slot)
    if slot_index is None:
        return None
    all_sims = read_all_quick_settings_sim_network_info(
        device_id, keep_open=keep_open
    )
    if all_sims is None:
        return None
    return all_sims.get(slot_index)
