"""工模 UI 底层：dump / 点击 / 滑动 / 轮询。"""

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable, Optional, TypeVar

from utils.tdd.ui_automatic import dump_current_ui
from utils.tdd.ui_xml import collect_texts_from_xml

T = TypeVar("T")
TAP_DELAY = 0.35


def adb(device_id: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["adb", "-s", device_id, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


def poll_bool(fn: Callable[[], bool], timeout: float, interval: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


def poll_value(fn: Callable[[], Optional[T]], timeout: float, interval: float) -> Optional[T]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(interval)
    return None


def dump(device_id: str) -> Optional[Path]:
    return dump_current_ui(device_id)


def ui_has_keywords(xml: Path, keywords: tuple[str, ...]) -> bool:
    return any(kw in "\n".join(collect_texts_from_xml(xml)) for kw in keywords)


def _parent_map(root: ET.Element) -> dict:
    parent: dict = {}
    for node in root.iter():
        for child in list(node):
            parent[child] = node
    return parent


def _clickable(node: ET.Element, parent: dict) -> ET.Element:
    cur: Optional[ET.Element] = node
    for _ in range(10):
        if cur is None:
            return node
        if cur.attrib.get("clickable") == "true":
            return cur
        cur = parent.get(cur)
    return node


def _tap_bounds(device_id: str, bounds: str, *, x_ratio: float = 0.5) -> bool:
    parts = bounds.replace("][", ",").replace("[", "").replace("]", "").split(",")
    if len(parts) != 4:
        return False
    x1, y1, x2, y2 = (int(v) for v in parts)
    cx = x1 + int((x2 - x1) * x_ratio)
    cy = (y1 + y2) // 2
    return adb(device_id, "shell", "input", "tap", str(cx), str(cy)).returncode == 0


_XPATH_RESOURCE_ID = re.compile(r'@resource-id=["\']([^"\']+)["\']', re.I)


def tap_xpath(device_id: str, xml: Path, xpath: str) -> bool:
    """按 resource-id xpath 点击；先点右侧再点中心（适配开关布局）。"""
    match = _XPATH_RESOURCE_ID.search((xpath or "").strip())
    if not match:
        return False
    rid = match.group(1)
    rid_suffix = rid.split("/")[-1]
    for el in ET.parse(xml).getroot().iter("node"):
        node_rid = el.attrib.get("resource-id") or ""
        if rid not in node_rid and not node_rid.endswith("/" + rid_suffix):
            continue
        bounds = el.attrib.get("bounds") or ""
        if not bounds:
            continue
        for ratio in (0.88, 0.5):
            if _tap_bounds(device_id, bounds, x_ratio=ratio):
                time.sleep(TAP_DELAY)
                return True
    return False


def tap_xml(
    device_id: str,
    xml: Path,
    *,
    resource_id: str = "",
    content_desc: tuple[str, ...] = (),
    text_equals: tuple[str, ...] = (),
) -> bool:
    root = ET.parse(xml).getroot()
    parent = _parent_map(root)
    rid_suffix = resource_id.split("/")[-1] if resource_id else ""
    for el in root.iter("node"):
        if resource_id:
            rid = el.attrib.get("resource-id") or ""
            if resource_id not in rid and not rid.endswith("/" + rid_suffix):
                continue
        elif text_equals:
            if (el.attrib.get("text") or "").strip() not in text_equals:
                continue
        else:
            desc = (el.attrib.get("content-desc") or "").strip()
            if not desc or not any(k in desc for k in content_desc):
                continue
        target = _clickable(el, parent)
        bounds = target.attrib.get("bounds") or ""
        if bounds and _tap_bounds(device_id, bounds):
            time.sleep(TAP_DELAY)
            return True
    return False


def tap_text(device_id: str, texts: tuple[str, ...]) -> bool:
    xml = dump(device_id)
    return bool(xml and tap_xml(device_id, xml, text_equals=texts))


def tap_list_item(device_id: str, texts: tuple[str, ...], *, rid_suffix: str = "adapter_title") -> bool:
    """点击工模列表项：匹配 text 或 adapter_title，并点击可点击父节点。"""
    if tap_text(device_id, texts):
        return True
    xml = dump(device_id)
    if not xml:
        return False
    root = ET.parse(xml).getroot()
    parent = _parent_map(root)
    for el in root.iter("node"):
        rid = el.attrib.get("resource-id") or ""
        if rid_suffix and rid_suffix not in rid:
            continue
        label = (el.attrib.get("text") or "").strip()
        if label not in texts:
            continue
        target = _clickable(el, parent)
        bounds = target.attrib.get("bounds") or ""
        if bounds and _tap_bounds(device_id, bounds):
            time.sleep(TAP_DELAY)
            return True
    return False


def swipe_resource(
    device_id: str,
    xml: Path,
    resource_id: str,
    *,
    times: int = 1,
    direction: str = "left",
) -> bool:
    rid_suffix = resource_id.split("/")[-1]
    for el in ET.parse(xml).getroot().iter("node"):
        rid = el.attrib.get("resource-id") or ""
        if resource_id not in rid and not rid.endswith("/" + rid_suffix):
            continue
        parts = (el.attrib.get("bounds") or "").replace("][", ",").replace("[", "").replace("]", "").split(",")
        if len(parts) != 4:
            continue
        x1, y1, x2, y2 = (int(v) for v in parts)
        cy = (y1 + y2) // 2
        margin = max((x2 - x1) // 5, 20)
        for _ in range(times):
            sx, ex = (x2 - margin, x1 + margin) if direction == "left" else (x1 + margin, x2 - margin)
            if adb(device_id, "shell", "input", "swipe", str(sx), str(cy), str(ex), str(cy), "280").returncode != 0:
                return False
            time.sleep(TAP_DELAY)
        return True
    return False


def textview_result(
    xml: Path, pass_text: tuple[str, ...], fail_text: tuple[str, ...]
) -> Optional[str]:
    """仅扫描 TextView（不含 Button），避免把结果按钮误判为结果。"""
    saw_pass = saw_fail = False
    for el in ET.parse(xml).getroot().iter("node"):
        node_class = el.attrib.get("class") or ""
        if "TextView" not in node_class:
            continue
        text = (el.attrib.get("text") or "").strip()
        if text in fail_text:
            saw_fail = True
        elif text in pass_text:
            saw_pass = True
    if saw_fail:
        return "fail"
    return "pass" if saw_pass else None


def tranfacmode_item_result(
    xml: Path,
    pass_text: tuple[str, ...],
    fail_text: tuple[str, ...],
    *,
    status_rid: str = "",
) -> Optional[str]:
    """读取工模 Other 单项结果：只读 test_status_tv，不兜底扫全页。

    test_status_tv 未出现 / 文本为空时返回 None（继续轮询），
    有明确通过/失败文本后才返回结果。
    """
    rid_suffix = status_rid.split("/")[-1] if status_rid else ""
    if not rid_suffix:
        return textview_result(xml, pass_text, fail_text)
    for el in ET.parse(xml).getroot().iter("node"):
        rid = el.attrib.get("resource-id") or ""
        if rid_suffix not in rid:
            continue
        text = (el.attrib.get("text") or "").strip()
        if text in fail_text:
            return "fail"
        if text in pass_text:
            return "pass"
    return None
