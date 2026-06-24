"""STK（SIM 卡工具包）菜单随机点击，离开 STK 包则失败。"""

import random
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from utils.tdd.ui_paths import device_ui_dir
from utils.tdd.ui_u2 import dump_current_ui
from utils.tdd.ui_xml import build_parent_map, parse_bounds_center

STK_PACKAGE = "com.android.stk"
STK_MAIN = "com.android.stk/.StkMain"
STK_LAUNCHER = "com.android.stk/.StkLauncherActivity"
REMOTE_UI_DUMP = "/sdcard/autotest_stk_ui.xml"

CANCEL_KEYWORDS = ("取消", "Cancel", "否", "NO", "Not now", "稍后")
CANCEL_BUTTON_RESOURCE_IDS = (
    "android:id/button2",
    "com.android.stk:id/button2",
)
SKIP_LABELS = frozenset(
    {
        "SIM Toolkit",
        "SIM卡工具包",
        "SIM 卡工具包",
        "STK",
        "返回",
        "Back",
        "转到上一层级",
    }
)
MENU_ITEM_RESOURCE_IDS = (
    "com.android.stk:id/stk_list_menu_item",
    "android:id/list_item",
)


def _run_adb(device_id: str, *args: str, timeout: int = 30):
    return subprocess.run(
        ["adb", "-s", device_id, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _latest_dump_path(device_id: str) -> Path:
    return device_ui_dir(device_id) / "_latest.xml"


def _is_stk_foreground(device_id: str) -> bool:
    return STK_PACKAGE in _foreground_package(device_id)


def _foreground_package(device_id: str) -> str:
    """读取当前前台包名；STK 在前台时返回 com.android.stk。"""
    for cmd in (
        ("shell", "dumpsys", "window"),
        ("shell", "dumpsys", "activity", "top"),
    ):
        ret = _run_adb(device_id, *cmd, timeout=15)
        text = f"{ret.stdout or ''}\n{ret.stderr or ''}"
        for line in text.splitlines():
            if "mCurrentFocus" in line or "mFocusedApp" in line or "topResumedActivity" in line:
                if STK_PACKAGE in line:
                    return STK_PACKAGE
                match = re.search(r"(com\.android\.stk(?:\.[\w]+)?)", line)
                if match:
                    return match.group(1)
    return ""


def _adb_dump_ui(device_id: str) -> Optional[Path]:
    """u2 不可用时，用 adb uiautomator dump 落盘。"""
    ret = _run_adb(
        device_id,
        "shell",
        "uiautomator",
        "dump",
        REMOTE_UI_DUMP,
        timeout=30,
    )
    output = f"{ret.stdout or ''}{ret.stderr or ''}"
    if ret.returncode != 0 and "dumped to" not in output.lower():
        return None
    cat = _run_adb(device_id, "shell", "cat", REMOTE_UI_DUMP, timeout=30)
    xml = (cat.stdout or "").strip()
    if not xml.startswith("<?xml") and "<hierarchy" not in xml:
        return None
    try:
        path = _latest_dump_path(device_id)
        path.write_text(xml, encoding="utf-8")
        return path
    except OSError:
        return None


def _dump_stk_ui(device_id: str) -> Optional[Path]:
    path = dump_current_ui(device_id)
    if path is not None and path.is_file():
        return path
    return _adb_dump_ui(device_id)


def launch_stk(device_id: str, settle_seconds: float = 2.0) -> bool:
    _run_adb(device_id, "shell", "am", "force-stop", STK_PACKAGE, timeout=15)
    time.sleep(0.3)
    for component in (STK_MAIN, STK_LAUNCHER):
        ret = _run_adb(
            device_id,
            "shell",
            "am",
            "start",
            "-W",
            "-f",
            "0x10008000",
            "-n",
            component,
            timeout=30,
        )
        output = f"{ret.stdout or ''}{ret.stderr or ''}"
        if ret.returncode == 0 and "Error" not in output:
            time.sleep(settle_seconds)
            if _is_stk_foreground(device_id):
                return True
    _run_adb(
        device_id,
        "shell",
        "monkey",
        "-p",
        STK_PACKAGE,
        "-c",
        "android.intent.category.LAUNCHER",
        "1",
        timeout=20,
    )
    time.sleep(settle_seconds)
    return _is_stk_foreground(device_id)


def _node_label(node: ET.Element) -> str:
    rid = node.attrib.get("resource-id") or ""
    if "lil_title" in rid or rid == "android:id/title":
        text = (node.attrib.get("text") or "").strip()
        if text:
            return text
    for child in node.iter("node"):
        child_rid = child.attrib.get("resource-id") or ""
        if "lil_title" in child_rid or child_rid == "android:id/title":
            text = (child.attrib.get("text") or "").strip()
            if text:
                return text
    for attr in ("text", "content-desc"):
        text = (node.attrib.get(attr) or "").strip()
        if text:
            return text
    return ""


def _is_skip_label(label: str) -> bool:
    t = (label or "").strip()
    if not t or len(t) > 40:
        return True
    if t in SKIP_LABELS:
        return True
    if len(t) == 1 and not t.isalnum():
        return True
    return False


def _is_cancel_text(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if t in CANCEL_KEYWORDS:
        return True
    low = t.lower()
    return low in {"cancel", "no", "not now"}


def _resolve_clickable_node(
    node: ET.Element, parent: dict[ET.Element, ET.Element]
) -> Optional[ET.Element]:
    """从带文案的节点向上找到 STK 包内可点击控件。"""
    cur: Optional[ET.Element] = node
    while cur is not None:
        pkg = cur.attrib.get("package") or ""
        if STK_PACKAGE in pkg and cur.attrib.get("clickable") == "true":
            if cur.attrib.get("enabled") != "false":
                return cur
        cur = parent.get(cur)
    return None


def _node_tap_center(node: ET.Element) -> Optional[tuple[int, int]]:
    bounds = node.attrib.get("bounds") or ""
    if not bounds:
        return None
    try:
        return parse_bounds_center(bounds)
    except ValueError:
        return None


def _find_cancel_tap_target(xml_path: Path) -> Optional[tuple[int, int]]:
    """界面有取消类按钮时返回其点击坐标（必点，不随机）。"""
    if not xml_path.is_file():
        return None
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError:
        return None

    parent = build_parent_map(root)

    for node in root.iter("node"):
        pkg = node.attrib.get("package") or ""
        if STK_PACKAGE not in pkg:
            continue
        rid = node.attrib.get("resource-id") or ""
        label = (node.attrib.get("text") or node.attrib.get("content-desc") or "").strip()
        is_cancel = _is_cancel_text(label) or rid in CANCEL_BUTTON_RESOURCE_IDS
        if not is_cancel:
            continue
        tap_node = node if node.attrib.get("clickable") == "true" else _resolve_clickable_node(node, parent)
        if tap_node is None:
            continue
        center = _node_tap_center(tap_node)
        if center is not None:
            return center
    return None


def _collect_stk_tap_targets(xml_path: Path) -> list[tuple[str, int, int]]:
    """从 STK 界面 XML 收集可随机点击的菜单项 (label, x, y)。"""
    if not xml_path.is_file():
        return []
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError:
        return []

    targets: list[tuple[str, int, int]] = []
    seen: set[tuple[str, int, int]] = set()

    for node in root.iter("node"):
        pkg = node.attrib.get("package") or ""
        if STK_PACKAGE not in pkg:
            continue
        if node.attrib.get("clickable") != "true":
            continue
        if node.attrib.get("enabled") == "false":
            continue

        label = _node_label(node)
        rid = node.attrib.get("resource-id") or ""
        if _is_cancel_text(label) or rid in CANCEL_BUTTON_RESOURCE_IDS:
            continue
        if _is_skip_label(label):
            if not any(token in rid for token in MENU_ITEM_RESOURCE_IDS):
                continue
            label = _node_label(node)
            if _is_skip_label(label):
                continue

        center = _node_tap_center(node)
        if center is None:
            continue
        x, y = center

        key = (label or rid, x, y)
        if key in seen:
            continue
        seen.add(key)
        targets.append((label or rid, x, y))

    return targets


def _pick_tap_target(device_id: str) -> Optional[tuple[int, int]]:
    xml_path = _dump_stk_ui(device_id)
    if xml_path is None:
        return None
    cancel = _find_cancel_tap_target(xml_path)
    if cancel is not None:
        return cancel
    targets = _collect_stk_tap_targets(xml_path)
    if not targets:
        return None
    _, x, y = random.choice(targets[: min(12, len(targets))])
    return x, y


def _tap_screen(device_id: str, x: int, y: int) -> bool:
    ret = _run_adb(device_id, "shell", "input", "tap", str(x), str(y), timeout=15)
    return ret.returncode == 0


def _press_back(device_id: str) -> bool:
    ret = _run_adb(device_id, "shell", "input", "keyevent", "4", timeout=10)
    return ret.returncode == 0


def random_stk_traverse(
    device_id: str,
    *,
    clicks: int = 50,
    settle_after_tap: float = 0.75,
) -> tuple[bool, str]:
    """
    在 STK 内随机点击；界面有取消按钮时先点取消；若离开 STK 前台则失败。

    返回 (成功, 说明)。
    """
    if not launch_stk(device_id):
        return False, "无法启动 STK"
    for i in range(max(1, clicks)):
        if not _is_stk_foreground(device_id):
            return False, f"第{i + 1}次点击前已离开 STK"
        target = _pick_tap_target(device_id)
        if target is not None:
            _tap_screen(device_id, target[0], target[1])
        else:
            _press_back(device_id)
        time.sleep(settle_after_tap)
        if not _is_stk_foreground(device_id):
            return False, f"第{i + 1}次点击后离开 STK 包"
    return True, f"完成 {clicks} 次随机点击且未离开 STK"
