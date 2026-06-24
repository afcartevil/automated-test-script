import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Union

from utils.tdd.ui_automatic import click_dialog_confirm, dump_current_ui

SETTLE_AFTER_TAP = 0.8
DIALOG_CONFIRM_TIMEOUT_SECONDS = 5.0
DIALOG_CONFIRM_POLL_SECONDS = 0.45
DIALOG_SETTLE_AFTER_ADD_SECONDS = 0.35
EnableTarget = Union[bool, int, str]
SWIPE = ("540", "1800", "540", "700", "280")
MAX_SCROLLS = 6
UNKNOWN_CALL_ROW_RID = "com.android.server.telecom:id/blocked_none_contacts_number_btn"
GENERIC_SWITCH_RID = "com.android.server.telecom:id/switch_btn"
BLACKLIST_ENTRY_RID = "com.android.server.telecom:id/block_numbers_btn"
BLACKLIST_ADD_RID = "com.android.server.telecom:id/add_blocked"
LIST_ADD_POLL_ATTEMPTS = 8
LIST_ADD_POLL_INTERVAL_SECONDS = 0.45
WHITELIST_ENTRY_RID = "com.android.server.telecom:id/private_numbers_btn"
WHITELIST_ADD_RID = "com.android.server.telecom:id/add_private_number_btn"
WHITELIST_ADD_RID_CANDIDATES = (
    WHITELIST_ADD_RID,
    "com.android.server.telecom:id/add_private_number",
    "com.android.server.telecom:id/blocked_add_icon",
)
PROMPT_MESSAGE_RID = "com.android.server.telecom:id/text_message"
WHITELIST_NUMBER_RID = "com.android.server.telecom:id/private_name_number"
WHITELIST_REMOVE_RID = "com.android.server.telecom:id/delete_private_number_btn"
BLACKLIST_NUMBER_INPUT_RIDS = (
    "com.android.server.telecom:id/number",
    "com.android.server.telecom:id/phone_number",
    "com.android.server.telecom:id/edit_text",
    "com.android.server.telecom:id/oet_edit_text",
    "android:id/edit",
    "android:id/input",
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


def _clickable_tap_target(el: ET.Element, parent_map: dict[ET.Element, ET.Element]) -> ET.Element:
    tap_el: Optional[ET.Element] = el
    for _ in range(8):
        if tap_el is None:
            break
        if tap_el.attrib.get("clickable") == "true":
            return tap_el
        tap_el = parent_map.get(tap_el)
    return el


def _switch_is_checked(switch_node: ET.Element) -> bool:
    return switch_node.attrib.get("checked") == "true"


def _find_unknown_call_switch(
    xml_path: Path,
) -> Optional[tuple[ET.Element, ET.Element]]:
    if not xml_path.is_file():
        return None
    root = ET.parse(xml_path).getroot()
    parent_map = _build_parent_map(root)
    # 仅按 resource-id 精准定位
    for row in root.iter("node"):
        if (row.attrib.get("resource-id") or "") != UNKNOWN_CALL_ROW_RID:
            continue
        switch_node: Optional[ET.Element] = None
        for child in row.iter("node"):
            rid = child.attrib.get("resource-id") or ""
            cls = child.attrib.get("class") or ""
            if rid == GENERIC_SWITCH_RID and "Switch" in cls:
                switch_node = child
                break
        if switch_node is not None:
            return _clickable_tap_target(row, parent_map), switch_node
    return None


def _read_unknown_call_checked(xml_path: Path) -> Optional[bool]:
    pair = _find_unknown_call_switch(xml_path)
    if pair is None:
        return None
    _, switch_node = pair
    return _switch_is_checked(switch_node)


def _tap_unknown_call_switch(device_id: str, xml_path: Path) -> bool:
    pair = _find_unknown_call_switch(xml_path)
    if pair is None:
        return False
    _row_target, switch_node = pair
    bounds = switch_node.attrib.get("bounds") or _row_target.attrib.get("bounds") or ""
    if not bounds:
        return False
    try:
        x, y = _parse_bounds_center(bounds)
    except ValueError:
        return False
    return _tap_screen(device_id, x, y)


def _swipe_down(device_id: str) -> bool:
    return (
        _run_adb(
            device_id,
            "shell",
            "input",
            "swipe",
            SWIPE[0],
            SWIPE[1],
            SWIPE[2],
            SWIPE[3],
            SWIPE[4],
        ).returncode
        == 0
    )


def _locate_switch_with_scroll(device_id: str) -> Optional[Path]:
    for i in range(MAX_SCROLLS + 1):
        xml_path = dump_current_ui(device_id)
        if xml_path is None:
            return None
        if _find_unknown_call_switch(xml_path) is not None:
            return xml_path
        if i < MAX_SCROLLS:
            _swipe_down(device_id)
            time.sleep(0.5)
    return None


def _tap_by_resource_id_with_scroll(device_id: str, rid: str) -> bool:
    for i in range(MAX_SCROLLS + 1):
        if _tap_by_resource_id(device_id, rid):
            return True
        if i < MAX_SCROLLS:
            _swipe_down(device_id)
            time.sleep(0.5)
    return False


def _tap_dialog_confirm(device_id: str) -> bool:
    """轮询点击弹框「确定」（u2 优先，dump 兜底）。"""
    deadline = time.time() + DIALOG_CONFIRM_TIMEOUT_SECONDS
    while time.time() < deadline:
        if click_dialog_confirm(device_id):
            return True
        time.sleep(DIALOG_CONFIRM_POLL_SECONDS)
    return False


def _tap_by_resource_id(device_id: str, rid: str) -> bool:
    xml_path = dump_current_ui(device_id)
    if xml_path is None or not xml_path.is_file():
        return False
    root = ET.parse(xml_path).getroot()
    parent_map = _build_parent_map(root)
    for el in root.iter("node"):
        if (el.attrib.get("resource-id") or "") != rid:
            continue
        tap_target = _clickable_tap_target(el, parent_map)
        bounds = tap_target.attrib.get("bounds") or el.attrib.get("bounds") or ""
        if not bounds:
            continue
        try:
            x, y = _parse_bounds_center(bounds)
        except ValueError:
            continue
        return _tap_screen(device_id, x, y)
    return False


def _tap_list_add_button(device_id: str, rids: tuple[str, ...]) -> bool:
    """名单页点击添加：按 resource-id 轮询直至控件出现。"""
    for attempt in range(LIST_ADD_POLL_ATTEMPTS):
        for rid in rids:
            if _tap_by_resource_id(device_id, rid):
                return True
        if attempt < LIST_ADD_POLL_ATTEMPTS - 1:
            time.sleep(LIST_ADD_POLL_INTERVAL_SECONDS)
    return False


def _tap_blacklist_add_button(device_id: str) -> bool:
    return _tap_list_add_button(device_id, (BLACKLIST_ADD_RID,))


def _tap_whitelist_add_button(device_id: str) -> bool:
    return _tap_list_add_button(device_id, WHITELIST_ADD_RID_CANDIDATES)


def _normalize_phone_for_input(phone_number: str) -> str:
    return "".join(ch for ch in (phone_number or "") if ch.isdigit() or ch == "+")


def _digits_only(text: str) -> str:
    return "".join(ch for ch in (text or "") if ch.isdigit())


def _ui_contains_text(
    device_id: str,
    text_keyword: str,
    rid: str = "",
) -> bool:
    if not text_keyword:
        return False
    xml_path = dump_current_ui(device_id)
    if xml_path is None or not xml_path.is_file():
        return False
    root = ET.parse(xml_path).getroot()
    for el in root.iter("node"):
        if rid and (el.attrib.get("resource-id") or "") != rid:
            continue
        text = el.attrib.get("text") or ""
        if text_keyword in text:
            return True
    return False


def _find_node_by_phone_digits(
    root: ET.Element,
    phone_number: str,
) -> Optional[ET.Element]:
    target = _digits_only(phone_number)
    if not target:
        return None
    for el in root.iter("node"):
        text = el.attrib.get("text") or ""
        text_digits = _digits_only(text)
        if not text_digits:
            continue
        if target.endswith(text_digits) or text_digits.endswith(target) or target in text_digits:
            return el
    return None


def _current_page_has_phone_number(device_id: str, phone_number: str) -> bool:
    target = _digits_only(phone_number)
    if not target:
        return False
    xml_path = dump_current_ui(device_id)
    if xml_path is None or not xml_path.is_file():
        return False
    root = ET.parse(xml_path).getroot()
    for el in root.iter("node"):
        text = el.attrib.get("text") or ""
        text_digits = _digits_only(text)
        if not text_digits:
            continue
        if target.endswith(text_digits) or text_digits.endswith(target) or target in text_digits:
            return True
    return False


def _find_delete_node_for_number(
    number_node: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
) -> Optional[ET.Element]:
    """
    从号码节点向上回溯容器，寻找同一行右侧删除按钮。
    """
    cur: Optional[ET.Element] = number_node
    while cur is not None:
        for child in cur.iter("node"):
            if (child.attrib.get("resource-id") or "") == WHITELIST_REMOVE_RID:
                return child
        cur = parent_map.get(cur)
    return None


def _input_blacklist_number(device_id: str, phone_number: str) -> bool:
    text = _normalize_phone_for_input(phone_number)
    if not text:
        return False

    xml_path = dump_current_ui(device_id)
    if xml_path is None or not xml_path.is_file():
        return False
    root = ET.parse(xml_path).getroot()
    parent_map = _build_parent_map(root)

    edit_node: Optional[ET.Element] = None
    for el in root.iter("node"):
        if (el.attrib.get("resource-id") or "") in BLACKLIST_NUMBER_INPUT_RIDS:
            edit_node = el
            break
    if edit_node is None:
        for el in root.iter("node"):
            cls = el.attrib.get("class") or ""
            if "EditText" in cls:
                edit_node = el
                break
    if edit_node is None:
        return False

    tap_target = _clickable_tap_target(edit_node, parent_map)
    bounds = tap_target.attrib.get("bounds") or edit_node.attrib.get("bounds") or ""
    if not bounds:
        return False
    try:
        x, y = _parse_bounds_center(bounds)
    except ValueError:
        return False
    if not _tap_screen(device_id, x, y):
        return False
    time.sleep(0.2)
    # 黑名单号码输入框默认为空，这里直接输入号码。
    if _run_adb(device_id, "shell", "input", "text", text, timeout=15).returncode != 0:
        return False
    time.sleep(0.2)
    return True


def set_block_unknown_call_enable(device_id: str, enable: EnableTarget) -> bool:
    """
    在当前「骚扰拦截」页面设置“拦截陌生号码来电”开关。
    打开时会弹确认框需点「确定」；关闭无弹框。
    """
    if not device_id:
        return False

    target = normalize_enable(enable)
    if target is None:
        return False

    xml_path = _locate_switch_with_scroll(device_id)
    if xml_path is None:
        return False

    checked = _read_unknown_call_checked(xml_path)
    if checked is None:
        return False
    if checked == target:
        return True

    if not _tap_unknown_call_switch(device_id, xml_path):
        return False
    if target:
        time.sleep(0.35)
        if not _tap_dialog_confirm(device_id):
            return False
    if SETTLE_AFTER_TAP > 0:
        time.sleep(SETTLE_AFTER_TAP)

    xml_path = _locate_switch_with_scroll(device_id)
    if xml_path is None:
        return False
    checked_after = _read_unknown_call_checked(xml_path)
    if checked_after is None:
        return False
    return checked_after == target


def tap_blacklist_entry(device_id: str) -> bool:
    """
    在当前「骚扰拦截」页面点击「黑名单」入口。
    """
    if not device_id:
        return False
    return _tap_by_resource_id_with_scroll(device_id, BLACKLIST_ENTRY_RID)


def add_number_to_blacklist(device_id: str, phone_number: str) -> bool:
    """
    在黑名单页面执行：
    1) 点击添加按钮；
    2) 第一个弹框点击确认；
    3) 第二个弹框输入号码并点击确认。
    """
    if not device_id:
        return False
    if not _normalize_phone_for_input(phone_number):
        return False

    if SETTLE_AFTER_TAP > 0:
        time.sleep(SETTLE_AFTER_TAP)
    if not _tap_blacklist_add_button(device_id):
        return False
    time.sleep(DIALOG_SETTLE_AFTER_ADD_SECONDS)
    if not _tap_dialog_confirm(device_id):
        return False
    time.sleep(0.4)
    if not _input_blacklist_number(device_id, phone_number):
        return False
    time.sleep(0.2)
    if not _tap_dialog_confirm(device_id):
        return False
    time.sleep(0.4)
    return True


def tap_whitelist_entry(device_id: str) -> bool:
    """
    在当前「骚扰拦截」页面点击「白名单」入口。
    """
    if not device_id:
        return False
    return _tap_by_resource_id_with_scroll(device_id, WHITELIST_ENTRY_RID)


def add_number_to_whitelist_and_check_blacklist_conflict(device_id: str, phone_number: str) -> bool:
    """
    在白名单页面添加号码并检查冲突弹框是否提示“号码已在黑名单中”。
    """
    if not device_id:
        return False
    if not _normalize_phone_for_input(phone_number):
        return False
    if SETTLE_AFTER_TAP > 0:
        time.sleep(SETTLE_AFTER_TAP)
    if not _tap_whitelist_add_button(device_id):
        return False
    time.sleep(DIALOG_SETTLE_AFTER_ADD_SECONDS)
    if not _tap_dialog_confirm(device_id):
        return False
    time.sleep(0.4)
    if not _input_blacklist_number(device_id, phone_number):
        return False
    time.sleep(0.2)
    if not _tap_dialog_confirm(device_id):
        return False
    time.sleep(0.4)
    return _ui_contains_text(device_id, "号码已在黑名单中", rid=PROMPT_MESSAGE_RID)


def confirm_blacklist_conflict_dialog(device_id: str) -> bool:
    """
    校验当前冲突弹框文案含“号码已在黑名单中”并点击“确定”。
    """
    if not device_id:
        return False
    if not _ui_contains_text(device_id, "号码已在黑名单中", rid=PROMPT_MESSAGE_RID):
        return False
    if not _tap_dialog_confirm(device_id):
        return False
    time.sleep(0.4)
    return True


def remove_number_from_whitelist(device_id: str, phone_number: str) -> bool:
    """
    在白名单页面删除指定号码。
    """
    if not device_id:
        return False
    if not _normalize_phone_for_input(phone_number):
        return False
    xml_path = dump_current_ui(device_id)
    if xml_path is None or not xml_path.is_file():
        return False
    root = ET.parse(xml_path).getroot()
    parent_map = _build_parent_map(root)
    number_node: Optional[ET.Element] = None
    for el in root.iter("node"):
        if (el.attrib.get("resource-id") or "") != WHITELIST_NUMBER_RID:
            continue
        text = el.attrib.get("text") or ""
        target = _digits_only(phone_number)
        text_digits = _digits_only(text)
        if target and text_digits and (
            target.endswith(text_digits) or text_digits.endswith(target) or target in text_digits
        ):
            number_node = el
            break
    if number_node is None:
        number_node = _find_node_by_phone_digits(root, phone_number)
    if number_node is None:
        return False
    delete_node = _find_delete_node_for_number(number_node, parent_map)
    if delete_node is None:
        return False
    delete_target = _clickable_tap_target(delete_node, parent_map)
    bounds = delete_target.attrib.get("bounds") or delete_node.attrib.get("bounds") or ""
    if not bounds:
        return False
    try:
        x, y = _parse_bounds_center(bounds)
    except ValueError:
        return False
    if not _tap_screen(device_id, x, y):
        return False
    time.sleep(0.3)
    # 点右侧删除后若出现确认框则确认。
    _tap_dialog_confirm(device_id)
    time.sleep(0.3)
    # 在白名单页二次检查是否仍有该号码。
    return not _current_page_has_phone_number(device_id, phone_number)


def blacklist_has_number(device_id: str, phone_number: str) -> bool:
    """
    当前黑名单页是否仍包含指定号码。
    """
    if not device_id:
        return False
    return _current_page_has_phone_number(device_id, phone_number)
