"""SIM 卡 PIN 锁定：adb 进入 IccLockSettings，开关与重启解锁。

PIN 弹框/锁屏输入逻辑对齐 scripts/sim_pin_lock_ui.py + scripts/hotspot_ui.py。
"""

import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from utils.tdd.ui_automatic import dump_current_ui
from utils.tdd.ui_settings_activity import enter_sim_pin_lock_settings_by_adb
from utils.tdd.ui_xml import build_parent_map, resolve_tap_node, tap_element_bounds

SIM_PIN = "1234"

# 设置弹框「确定」（与 scripts CONFIRM_KEYWORDS 一致，不含「输入」避免误点）
PIN_DIALOG_CONFIRM = frozenset({"确定", "确认", "OK", "Ok", "完成"})
PIN_DIALOG_CONFIRM_RIDS = (
    "com.android.settings:id/btn_positive",
    "android:id/button1",
)

# 锁屏 SystemUI PIN 键盘「输入/确定」（scripts PIN_KEYPAD_CONFIRM_KEYWORDS）
PIN_KEYPAD_CONFIRM = (
    "输入",
    "确定",
    "确认",
    "OK",
    "Ok",
    "解锁",
    "Unlock",
    "完成",
    "Done",
    "Enter",
)
PIN_KEYPAD_CONFIRM_RIDS = (
    "key_enter",
    "key_ok",
    "btn_positive",
    "button_positive",
)

SYSTEMUI_KEY_RID_PREFIX = "com.android.systemui:id/key"

PAGE_SETTLE_SECONDS = 1.0
PIN_DIALOG_SETTLE_SECONDS = 0.55
POST_BOOT_WAIT_SECONDS = 60
# 输入前清空：SIM PIN 最长 8 位，多删几位避免残留（如误触先出现 2）
PIN_CLEAR_DEL_COUNT = 10
PUK_MARKERS = ("PUK", "puk", "已锁定", "locked")


def _run_adb(device_id: str, *args: str, timeout: int = 30):
    return subprocess.run(
        ["adb", "-s", device_id, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _adb_tap(device_id: str, x: int, y: int) -> bool:
    ret = _run_adb(device_id, "shell", "input", "tap", str(x), str(y), timeout=15)
    return ret.returncode == 0


def _adb_input_text(device_id: str, text: str) -> bool:
    """与 scripts/hotspot_ui.adb_input_text 一致：空格用 %s。"""
    escaped = (text or "").replace(" ", "%s")
    ret = _run_adb(device_id, "shell", "input", "text", escaped, timeout=10)
    return ret.returncode == 0


def _dump_root(device_id: str) -> Optional[ET.Element]:
    xml_path = dump_current_ui(device_id)
    if xml_path is None or not xml_path.is_file():
        return None
    try:
        return ET.parse(xml_path).getroot()
    except ET.ParseError:
        return None


def _is_device_locked(device_id: str) -> bool:
    trust = _run_adb(device_id, "shell", "dumpsys", "trust", timeout=15)
    trust_text = f"{trust.stdout or ''}\n{trust.stderr or ''}".lower()
    if "devicelocked=true" in trust_text or "devicelocked=1" in trust_text:
        return True

    policy = _run_adb(device_id, "shell", "dumpsys", "window", "policy", timeout=15)
    text = f"{policy.stdout or ''}\n{policy.stderr or ''}".lower()
    lock_markers = (
        "isstatusbarkeyguard=true",
        "mshowinglockscreen=true",
        "keyguardshowing=true",
    )
    return any(marker in text for marker in lock_markers)


def _is_pin_switch_row_label(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    return "锁定sim卡" in t.replace(" ", "") or "lock sim" in t


def _switch_in_subtree(root_el: ET.Element) -> Optional[ET.Element]:
    if "Switch" in (root_el.attrib.get("class") or ""):
        return root_el
    for child in root_el.iter("node"):
        if child is root_el:
            continue
        if "Switch" in (child.attrib.get("class") or ""):
            return child
    return None


def _find_pin_lock_switch(xml_path: Path) -> Optional[ET.Element]:
    if not xml_path.is_file():
        return None
    root = ET.parse(xml_path).getroot()
    parent_map = build_parent_map(root)
    for el in root.iter("node"):
        label = (el.attrib.get("text") or "") + (el.attrib.get("content-desc") or "")
        if not _is_pin_switch_row_label(label):
            continue
        parent = parent_map.get(el)
        for search_root in (parent, el):
            if search_root is None:
                continue
            switch_node = _switch_in_subtree(search_root)
            if switch_node is not None:
                return switch_node
    return None


def _read_pin_lock_checked(device_id: str) -> Optional[bool]:
    xml_path = dump_current_ui(device_id)
    if xml_path is None:
        return None
    switch_node = _find_pin_lock_switch(xml_path)
    if switch_node is None:
        return None
    return switch_node.attrib.get("checked") == "true"


def _open_sim_pin_page(device_id: str) -> bool:
    if not enter_sim_pin_lock_settings_by_adb(device_id):
        return False
    time.sleep(PAGE_SETTLE_SECONDS)
    return _read_pin_lock_checked(device_id) is not None


def _tap_pin_switch(device_id: str) -> bool:
    root = _dump_root(device_id)
    if root is None:
        return False
    parent_map = build_parent_map(root)
    for el in root.iter("node"):
        label = (el.attrib.get("text") or "") + (el.attrib.get("content-desc") or "")
        if not _is_pin_switch_row_label(label):
            continue
        tap_node = resolve_tap_node(el, parent_map)
        switch_node = _switch_in_subtree(tap_node) or _switch_in_subtree(el)
        bounds = ""
        if switch_node is not None:
            bounds = switch_node.attrib.get("bounds") or ""
        if not bounds:
            bounds = tap_node.attrib.get("bounds") or ""
        center = tap_element_bounds(bounds)
        if center is None:
            continue
        if _adb_tap(device_id, center[0], center[1]):
            return True
    return False


def _collect_edittext_nodes(root: ET.Element) -> list[ET.Element]:
    return [
        el
        for el in root.iter("node")
        if "EditText" in (el.attrib.get("class") or "")
    ]


def _tap_pin_field(device_id: str) -> bool:
    """对齐 scripts _tap_pin_field：点第一个 EditText 获取焦点。"""
    root = _dump_root(device_id)
    if root is None:
        return False
    edits = _collect_edittext_nodes(root)
    if not edits:
        return False
    center = tap_element_bounds(edits[0].attrib.get("bounds") or "")
    if center is None:
        return False
    _adb_tap(device_id, center[0], center[1])
    time.sleep(0.35)
    return True


def _clear_pin_field(device_id: str) -> bool:
    """聚焦 PIN 输入框后删光已有内容，避免残留字符与 1234 拼接。"""
    if not _tap_pin_field(device_id):
        return False
    time.sleep(0.2)
    # 光标移到末尾再退格，避免焦点在开头时删不干净
    _run_adb(device_id, "shell", "input", "keyevent", "123", timeout=10)
    time.sleep(0.08)
    for _ in range(PIN_CLEAR_DEL_COUNT):
        _run_adb(device_id, "shell", "input", "keyevent", "67", timeout=10)
        time.sleep(0.05)
    time.sleep(0.15)
    return True


def _click_dialog_confirm(device_id: str) -> bool:
    root = _dump_root(device_id)
    if root is None:
        return False
    parent_map = build_parent_map(root)
    for el in root.iter("node"):
        rid = (el.attrib.get("resource-id") or "").strip()
        if rid not in PIN_DIALOG_CONFIRM_RIDS:
            continue
        center = tap_element_bounds(el.attrib.get("bounds") or "")
        if center is not None and _adb_tap(device_id, center[0], center[1]):
            return True
    for el in root.iter("node"):
        text = (el.attrib.get("text") or "").strip()
        if text not in PIN_DIALOG_CONFIRM:
            continue
        tap_node = resolve_tap_node(el, parent_map)
        center = tap_element_bounds(tap_node.attrib.get("bounds") or "")
        if center is not None and _adb_tap(device_id, center[0], center[1]):
            return True
    return False


def _pin_dialog_still_open(device_id: str) -> bool:
    root = _dump_root(device_id)
    if root is None:
        return False
    if _collect_edittext_nodes(root):
        return True
    xml_path = dump_current_ui(device_id)
    if xml_path is None or not xml_path.is_file():
        return False
    body = xml_path.read_text(encoding="utf-8", errors="ignore")
    return "EditText" in body or "android:id/edit" in body


def enter_pin_in_dialog(device_id: str, pin: str = SIM_PIN, *, max_rounds: int = 2) -> bool:
    """
    点输入框 → 清空 → adb input text 整串 PIN → 点确定；若仍有 EditText 再输一轮。
    """
    if not pin or not pin.isdigit():
        return False
    for round_i in range(max_rounds):
        if not _clear_pin_field(device_id):
            return False
        if not _adb_input_text(device_id, pin):
            return False
        time.sleep(0.4)
        if not _click_dialog_confirm(device_id):
            return False
        time.sleep(0.9)
        xml_path = dump_current_ui(device_id)
        if xml_path and xml_path.is_file():
            body = xml_path.read_text(encoding="utf-8", errors="ignore")
            if any(m in body for m in PUK_MARKERS):
                return False
        if _pin_dialog_still_open(device_id) and round_i + 1 < max_rounds:
            continue
        return True
    return True


def _find_keypad_digit_node(
    root: ET.Element, parent_map: dict, digit: str
) -> Optional[ET.Element]:
    if len(digit) != 1 or not digit.isdigit():
        return None
    want_rid = f"{SYSTEMUI_KEY_RID_PREFIX}{digit}"
    for el in root.iter("node"):
        rid = (el.attrib.get("resource-id") or "").strip()
        if rid == want_rid or rid.endswith(f":id/key{digit}"):
            return resolve_tap_node(el, parent_map)

    candidates: list[tuple[int, ET.Element]] = []
    for el in root.iter("node"):
        t = (el.attrib.get("text") or "").strip()
        d = (el.attrib.get("content-desc") or "").strip()
        if t != digit and d != digit:
            continue
        cls = (el.attrib.get("class") or "").lower()
        rid = (el.attrib.get("resource-id") or "").lower()
        if "edittext" in cls or "simpinentry" in rid:
            continue
        score = 0
        if el.attrib.get("clickable") == "true":
            score += 4
        if f":id/key{digit}" in rid or rid.endswith(f"key{digit}"):
            score += 10
        candidates.append((score, resolve_tap_node(el, parent_map)))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _tap_keypad_digit(device_id: str, digit: str) -> bool:
    root = _dump_root(device_id)
    if root is None:
        return False
    parent_map = build_parent_map(root)
    tap_node = _find_keypad_digit_node(root, parent_map, digit)
    if tap_node is None:
        return False
    center = tap_element_bounds(tap_node.attrib.get("bounds") or "")
    if center is None:
        return False
    _adb_tap(device_id, center[0], center[1])
    time.sleep(0.35)
    return True


def _tap_keypad_confirm(device_id: str) -> bool:
    """对齐 scripts _tap_pin_keypad_confirm：优先 key_enter /「输入」。"""
    root = _dump_root(device_id)
    if root is None:
        return False
    parent_map = build_parent_map(root)
    for el in root.iter("node"):
        rid = (el.attrib.get("resource-id") or "").strip().lower()
        if rid.endswith(":id/key_enter") or rid == "com.android.systemui:id/key_enter":
            center = tap_element_bounds(el.attrib.get("bounds") or "")
            if center is not None and _adb_tap(device_id, center[0], center[1]):
                time.sleep(0.5)
                return True
    for el in root.iter("node"):
        rid = (el.attrib.get("resource-id") or "").lower()
        if not any(h in rid for h in PIN_KEYPAD_CONFIRM_RIDS):
            continue
        label = (el.attrib.get("text") or "") + (el.attrib.get("content-desc") or "")
        if not any(k in label for k in PIN_KEYPAD_CONFIRM):
            continue
        center = tap_element_bounds(resolve_tap_node(el, parent_map).attrib.get("bounds") or "")
        if center is not None and _adb_tap(device_id, center[0], center[1]):
            time.sleep(0.5)
            return True
    for el in root.iter("node"):
        text = (el.attrib.get("text") or "").strip()
        desc = (el.attrib.get("content-desc") or "").strip()
        if text not in PIN_KEYPAD_CONFIRM and desc not in PIN_KEYPAD_CONFIRM:
            continue
        center = tap_element_bounds(resolve_tap_node(el, parent_map).attrib.get("bounds") or "")
        if center is not None and _adb_tap(device_id, center[0], center[1]):
            time.sleep(0.5)
            return True
    return False


def enter_pin_via_keypad(device_id: str, pin: str = SIM_PIN) -> bool:
    """对齐 scripts enter_pin_via_keypad_buttons：锁屏点 UI 数字键，不用 keyevent/input text。"""
    if not pin or not pin.isdigit():
        return False
    for ch in pin:
        if not _tap_keypad_digit(device_id, ch):
            return False
    time.sleep(0.25)
    return _tap_keypad_confirm(device_id)


def _is_sim_pin_keyguard(device_id: str) -> bool:
    window = _run_adb(device_id, "shell", "dumpsys", "window", timeout=15)
    low = f"{window.stdout or ''}\n{window.stderr or ''}".lower()
    if "keyguard_sim_pin" in low or "keyguard_sim_pin_view" in low:
        return True
    activity = _run_adb(device_id, "shell", "dumpsys", "activity", "top", timeout=15)
    top_low = f"{activity.stdout or ''}\n{activity.stderr or ''}".lower()
    return "keyguard_sim_pin" in top_low


def open_sim_pin_lock_page(device_id: str) -> bool:
    """adb 进入「SIM 卡锁定」页，等待 PAGE_SETTLE_SECONDS 后返回。"""
    return _open_sim_pin_page(device_id)


def set_sim_pin_enabled(device_id: str, *, skip_page_open: bool = False) -> bool:
    """adb 进入「SIM卡锁定」并开启 SIM PIN（密码固定为 SIM_PIN）。"""
    if not device_id:
        return False
    if not skip_page_open and not _open_sim_pin_page(device_id):
        return False
    before = _read_pin_lock_checked(device_id)
    if before is True:
        return True
    if not _tap_pin_switch(device_id):
        return False
    time.sleep(PIN_DIALOG_SETTLE_SECONDS)
    if not enter_pin_in_dialog(device_id, SIM_PIN, max_rounds=2):
        return False
    after = _read_pin_lock_checked(device_id)
    return after is True


def set_sim_pin_disabled(device_id: str, *, skip_page_open: bool = False) -> bool:
    """adb 进入「SIM卡锁定」并关闭 SIM PIN（密码固定为 SIM_PIN）。"""
    if not device_id:
        return False
    if not skip_page_open and not _open_sim_pin_page(device_id):
        return False
    before = _read_pin_lock_checked(device_id)
    if before is False:
        return True
    if not _tap_pin_switch(device_id):
        return False
    time.sleep(PIN_DIALOG_SETTLE_SECONDS)
    if not enter_pin_in_dialog(device_id, SIM_PIN, max_rounds=2):
        return False
    after = _read_pin_lock_checked(device_id)
    return after is False


def reboot_and_unlock(
    device_id: str,
    timeout_seconds: int = 180,
    *,
    unlock_sim_pin: bool = False,
    post_boot_wait_seconds: int = POST_BOOT_WAIT_SECONDS,
) -> bool:
    """
    重启设备并等待开机完成后执行亮屏解锁。
    unlock_sim_pin 为 True 时在 SystemUI SIM PIN 键盘上点 1-2-3-4 + 输入。
    """
    if not device_id:
        return False
    reboot_ret = _run_adb(device_id, "reboot", timeout=15)
    if reboot_ret.returncode != 0:
        return False

    deadline = time.time() + max(30, timeout_seconds)
    while time.time() < deadline:
        state_ret = _run_adb(device_id, "get-state", timeout=10)
        if state_ret.returncode == 0 and "device" in (state_ret.stdout or "").lower():
            boot_ret = _run_adb(
                device_id,
                "shell",
                "getprop",
                "sys.boot_completed",
                timeout=10,
            )
            if boot_ret.returncode == 0 and (boot_ret.stdout or "").strip() == "1":
                break
        time.sleep(3)
    else:
        return False

    if post_boot_wait_seconds > 0:
        time.sleep(post_boot_wait_seconds)

    _run_adb(device_id, "shell", "input", "keyevent", "224", timeout=10)
    time.sleep(0.3)
    if unlock_sim_pin or _is_sim_pin_keyguard(device_id):
        if not enter_pin_via_keypad(device_id, SIM_PIN):
            return False
        time.sleep(0.8)

    for _ in range(3):
        _run_adb(device_id, "shell", "input", "keyevent", "82", timeout=10)
        _run_adb(
            device_id,
            "shell",
            "input",
            "swipe",
            "540",
            "1800",
            "540",
            "500",
            "250",
            timeout=10,
        )
        _run_adb(device_id, "shell", "wm", "dismiss-keyguard", timeout=10)
        time.sleep(0.8)
        if not _is_device_locked(device_id):
            return True
    return not _is_device_locked(device_id)
