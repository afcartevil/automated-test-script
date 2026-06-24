"""SIM 详情页「SIM卡名称」菜单：读取、校验与重命名。"""

import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from utils.tdd.ui_automatic import (
    DEFAULT_MAX_SCROLLS,
    DEFAULT_SWIPE,
    click_by_match_keywords,
)
from utils.tdd.ui_u2 import (
    acquire_u2,
    dump_current_ui,
    release_uiautomator2,
    click_dialog_positive,
)
from utils.tdd.ui_xml import (
    build_parent_map,
    clickable_tap_target,
    parse_bounds_center,
)

SIM_NAME_MENU_KEYWORDS = (
    "SIM卡名称",
    "SIM 名称",
    "SIM名称",
    "SIM name",
    "SIM name & color",
)
SIM_NAME_EDIT_RIDS = ("name_edittext", "oet_edit_text")
SIM_NAME_CANCEL_KEYWORDS = ("取消", "Cancel")
SETTLE_AFTER_TAP = 0.8
SETTLE_AFTER_RENAME = 1.0
SETTLE_AFTER_SCROLL = 0.85
SETTLE_AFTER_DISMISS = 0.35
U2_SET_TEXT_TIMEOUT = 2.0

_PUNCT_NORMALIZE_MAP = str.maketrans(
    {
        "。": ".",
        "，": ",",
        "！": "!",
        "？": "?",
        "：": ":",
        "；": ";",
        "（": "(",
        "）": ")",
        "【": "[",
        "】": "]",
        "＠": "@",
        "＃": "#",
        "－": "-",
        "—": "-",
        "＿": "_",
        "．": ".",
        "＋": "+",
        "＆": "&",
        "＊": "*",
        "＝": "=",
        "·": ".",
    }
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


def _normalize_sim_name_text(name: str) -> str:
    text = (name or "").translate(_PUNCT_NORMALIZE_MAP)
    normalized: list[str] = []
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            normalized.append(chr(code - 0xFEE0))
        else:
            normalized.append(ch)
    return "".join(normalized)


def _is_sim_name_menu_label(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if any(kw in t for kw in SIM_NAME_MENU_KEYWORDS):
        return True
    low = t.lower()
    return low in ("sim name", "sim name & color")


def _swipe_page_down(device_id: str) -> bool:
    x1, y1, x2, y2, duration_ms = DEFAULT_SWIPE
    return (
        _run_adb(
            device_id,
            "shell",
            "input",
            "swipe",
            x1,
            y1,
            x2,
            y2,
            str(duration_ms),
        ).returncode
        == 0
    )


def _row_root_for_label(el: ET.Element, parent_map: dict) -> ET.Element:
    row = el
    for _ in range(6):
        parent = parent_map.get(row)
        if parent is None:
            break
        cls = parent.attrib.get("class") or ""
        if parent.attrib.get("clickable") == "true" or "RecyclerView" in cls:
            return parent
        row = parent
    return parent_map.get(el) or el


def _read_name_from_row(row: ET.Element) -> str:
    title_texts = {
        (el.attrib.get("text") or "").strip()
        for el in row.iter("node")
        if _is_sim_name_menu_label(
            (el.attrib.get("text") or "") + (el.attrib.get("content-desc") or "")
        )
    }
    title_texts.discard("")

    candidates: list[str] = []
    for el in row.iter("node"):
        for attr in ("text", "content-desc"):
            text = (el.attrib.get(attr) or "").strip()
            if not text or text in title_texts:
                continue
            if _is_sim_name_menu_label(text):
                continue
            if text in (">", "›"):
                continue
            candidates.append(text)

    if not candidates:
        return ""
    return max(candidates, key=len)


def _find_sim_name_row(
    root: ET.Element,
) -> Optional[tuple[ET.Element, ET.Element, str]]:
    parent_map = build_parent_map(root)
    for el in root.iter("node"):
        label = (el.attrib.get("text") or "") + (el.attrib.get("content-desc") or "")
        if not _is_sim_name_menu_label(label):
            continue
        row = _row_root_for_label(el, parent_map)
        name = _read_name_from_row(row)
        tap_target = clickable_tap_target(row, parent_map)
        return tap_target, row, name
    return None


def _locate_sim_name_row(
    device_id: str,
    *,
    max_scrolls: int = DEFAULT_MAX_SCROLLS,
) -> tuple[Optional[tuple[ET.Element, ET.Element, str]], Optional[Path]]:
    xml_path: Optional[Path] = None
    for slide in range(max(0, max_scrolls) + 1):
        xml_path = dump_current_ui(device_id)
        if xml_path is None:
            return None, None
        pair = _find_sim_name_row(ET.parse(xml_path).getroot())
        if pair is not None:
            return pair, xml_path
        if slide >= max_scrolls:
            break
        _swipe_page_down(device_id)
        if SETTLE_AFTER_SCROLL > 0:
            time.sleep(SETTLE_AFTER_SCROLL)
    return None, xml_path


def read_sim_card_display_name(device_id: str) -> Optional[str]:
    """读取当前 SIM 子界面「SIM卡名称」菜单上显示的运营商/名称。"""
    if not device_id:
        return None
    pair, _ = _locate_sim_name_row(device_id)
    if pair is None:
        return None
    _, _, name = pair
    return (name or "").strip() or None


def check_sim_card_display_name(
    device_id: str,
    expected_name: str,
) -> tuple[bool, str]:
    """检查 SIM 卡名称菜单显示是否与期望一致。"""
    expected = (expected_name or "").strip()
    if not expected:
        return False, "期望名称为空"

    actual = read_sim_card_display_name(device_id)
    if actual is None:
        return False, "未找到SIM卡名称菜单或无法读取名称"

    if actual == expected or expected in actual or actual in expected:
        return True, ""

    return False, f"SIM卡名称不符，期望「{expected}」，实际「{actual}」"


def _tap_node(device_id: str, node: ET.Element) -> bool:
    bounds = node.attrib.get("bounds") or ""
    if not bounds:
        return False
    try:
        x, y = parse_bounds_center(bounds)
    except ValueError:
        return False
    return _tap_screen(device_id, x, y)


def _open_sim_name_dialog(device_id: str) -> bool:
    pair, _ = _locate_sim_name_row(device_id)
    if pair is None:
        return False
    tap_target, _, _ = pair
    if not _tap_node(device_id, tap_target):
        return False
    if SETTLE_AFTER_TAP > 0:
        time.sleep(SETTLE_AFTER_TAP)
    return True


def _find_dialog_edit(root: ET.Element) -> Optional[ET.Element]:
    for rid in SIM_NAME_EDIT_RIDS:
        for el in root.iter("node"):
            if rid in (el.attrib.get("resource-id") or ""):
                return el
    for el in root.iter("node"):
        if "EditText" in (el.attrib.get("class") or ""):
            return el
    return None


def _find_u2_dialog_edit(device):
    for rid in SIM_NAME_EDIT_RIDS:
        selector = device(resourceIdMatches=f".*{rid}")
        if selector.exists(timeout=U2_SET_TEXT_TIMEOUT):
            return selector
    for selector in (
        device(className="android.widget.EditText", focused=True),
        device(className="android.widget.EditText"),
    ):
        if selector.exists(timeout=0.8):
            return selector
    return None


def _read_dialog_edit_text(device_id: str) -> str:
    xml_path = dump_current_ui(device_id)
    if xml_path is None:
        return ""
    edit_node = _find_dialog_edit(ET.parse(xml_path).getroot())
    if edit_node is None:
        return ""
    return (edit_node.attrib.get("text") or "").strip()


def _input_confirm_via_u2(device_id: str, text: str) -> bool:
    """同一 u2 会话：写入文本并点确定，最后 release。"""
    device = acquire_u2(device_id)
    if device is None:
        return False
    content = (text or "").strip()
    if not content:
        release_uiautomator2(device_id, wait_ready=False)
        return True
    try:
        edit = _find_u2_dialog_edit(device)
        if edit is None:
            return False
        edit.click()
        time.sleep(0.15)
        edit.clear_text()
        time.sleep(0.1)
        edit.set_text(content)
        time.sleep(0.25)
        typed = content
        try:
            typed = (edit.get_text() or "").strip() or content
        except Exception:
            pass
        if not names_match_for_update(text, typed):
            return False
        if not click_dialog_positive(device, settle_after=SETTLE_AFTER_RENAME):
            return False
        return True
    except Exception:
        return False
    finally:
        release_uiautomator2(device_id, wait_ready=False)


def _read_dialog_edit_via_u2(device) -> str:
    edit = _find_u2_dialog_edit(device)
    if edit is None:
        return ""
    try:
        return (edit.get_text() or "").strip()
    except Exception:
        return ""


def _dismiss_sim_name_dialog(device_id: str) -> bool:
    if click_by_match_keywords(
        device_id,
        SIM_NAME_CANCEL_KEYWORDS,
        prefer_cached_ui=False,
        max_scrolls=0,
    ):
        if SETTLE_AFTER_DISMISS > 0:
            time.sleep(SETTLE_AFTER_DISMISS)
        return True
    ok = _run_adb(device_id, "shell", "input", "keyevent", "4").returncode == 0
    if ok and SETTLE_AFTER_DISMISS > 0:
        time.sleep(SETTLE_AFTER_DISMISS)
    return ok


def read_saved_sim_card_display_name(device_id: str) -> Optional[str]:
    """打开 SIM 卡名称弹框读取 EditText 中的已保存名称，随后取消关闭。"""
    if not device_id:
        return None
    if not _open_sim_name_dialog(device_id):
        return None
    device = acquire_u2(device_id)
    if device is None:
        value = _read_dialog_edit_text(device_id)
        _dismiss_sim_name_dialog(device_id)
        return value or None
    try:
        value = _read_dialog_edit_via_u2(device)
        if not value:
            value = _read_dialog_edit_text(device_id)
        return value or None
    finally:
        release_uiautomator2(device_id, wait_ready=False)
        _dismiss_sim_name_dialog(device_id)


def verify_sim_card_display_name_saved(
    device_id: str,
    expected_name: str,
) -> tuple[bool, str]:
    """保存后从弹框输入框校验名称（比列表摘要更准确）。"""
    expected = (expected_name or "").strip()
    if not expected:
        return False, "期望名称为空"
    actual = read_saved_sim_card_display_name(device_id)
    if actual is None:
        return False, "无法打开SIM卡名称弹框读取已保存名称"
    if names_match_for_update(expected, actual):
        return True, ""
    return False, f"SIM卡名称不符，期望「{expected}」，弹框内「{actual}」"


def set_sim_card_display_name(device_id: str, new_name: str) -> bool:
    """
    点击 SIM 卡名称菜单，在弹框中清空并输入新名称后保存。

    调用前需已在 SIM 子界面；保存后会短暂等待界面刷新。
    """
    if not device_id:
        return False
    if not _open_sim_name_dialog(device_id):
        return False
    name = (new_name or "").strip()
    return _input_confirm_via_u2(device_id, name)


def names_match_for_update(expected: str, actual: Optional[str]) -> bool:
    """判断重命名后名称是否与期望一致（含 IME 中文标点转换、截断）。"""
    exp = _normalize_sim_name_text((expected or "").strip())
    act = _normalize_sim_name_text((actual or "").strip())
    if not exp:
        return not act
    if act == exp:
        return True
    min_len = min(len(exp), len(act))
    if min_len >= 4 and (exp.startswith(act) or act.startswith(exp)):
        return True
    prefix = 0
    for left, right in zip(exp, act):
        if left == right:
            prefix += 1
        else:
            break
    return prefix >= max(4, int(min(len(exp), len(act)) * 0.75))
