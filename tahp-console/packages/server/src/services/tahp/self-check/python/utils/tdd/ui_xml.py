"""从 u2 dump 的 UI 层次 XML 解析控件。"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable, Optional


def parse_bounds_center(bounds: str) -> tuple[int, int]:
    chunks = bounds.replace("][", ",").replace("[", "").replace("]", "").split(",")
    if len(chunks) != 4:
        raise ValueError(f"invalid bounds: {bounds}")
    x1, y1, x2, y2 = (int(v) for v in chunks)
    return (x1 + x2) // 2, (y1 + y2) // 2


def build_parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    parent: dict[ET.Element, ET.Element] = {}
    for node in root.iter():
        for child in list(node):
            parent[child] = node
    return parent


def node_reported_displayed(node: ET.Element) -> bool:
    value = node.attrib.get("displayed")
    if value is None:
        return True
    return value.strip().lower() != "false"


def clickable_tap_target(
    el: ET.Element, parent_map: dict[ET.Element, ET.Element], *, max_depth: int = 8
) -> ET.Element:
    tap_el: Optional[ET.Element] = el
    for _ in range(max_depth):
        if tap_el is None:
            break
        if tap_el.attrib.get("clickable") == "true":
            return tap_el
        tap_el = parent_map.get(tap_el)
    return el


def resolve_tap_node(match: ET.Element, parent: dict[ET.Element, ET.Element]) -> ET.Element:
    current: Optional[ET.Element] = match
    while current is not None:
        if current.attrib.get("clickable") == "true":
            return current
        current = parent.get(current)
    return match


def switch_in_subtree(root_el: ET.Element) -> Optional[ET.Element]:
    if "Switch" in (root_el.attrib.get("class") or ""):
        return root_el
    for child in root_el.iter("node"):
        if child is root_el:
            continue
        if "Switch" in (child.attrib.get("class") or ""):
            return child
    return None


def switches_in_subtree(root_el: ET.Element) -> list[ET.Element]:
    return [
        n
        for n in root_el.iter("node")
        if "Switch" in (n.attrib.get("class") or "")
    ]


def find_labeled_switch_in_root(
    root: ET.Element,
    label_pred: Callable[[str], bool],
) -> Optional[tuple[ET.Element, ET.Element, str]]:
    """
    按标题行定位 Switch：取包含该标题且子树内仅有一个 Switch 的最近父节点，
    避免在 RecyclerView 层级误点到其它行的 switch_widget。
    """
    parent_map = build_parent_map(root)
    for el in root.iter("node"):
        rid = (el.attrib.get("resource-id") or "").strip()
        if rid.endswith("/summary") or rid == "android:id/summary":
            continue
        label = (el.attrib.get("text") or "") + (el.attrib.get("content-desc") or "")
        if not label_pred(label):
            continue
        label_text = (el.attrib.get("text") or el.attrib.get("content-desc") or "").strip()
        switch_node: Optional[ET.Element] = None
        row_root: Optional[ET.Element] = None
        cur: Optional[ET.Element] = el
        for _ in range(12):
            if cur is None:
                break
            row_switches = switches_in_subtree(cur)
            if len(row_switches) == 1:
                switch_node = row_switches[0]
                row_root = cur
                break
            cur = parent_map.get(cur)
        if switch_node is None or row_root is None:
            continue
        return clickable_tap_target(row_root, parent_map), switch_node, label_text
    return None


def switch_is_checked(switch_node: ET.Element) -> bool:
    return switch_node.attrib.get("checked") == "true"


def tap_element_bounds(bounds: str) -> Optional[tuple[int, int]]:
    if not bounds:
        return None
    try:
        return parse_bounds_center(bounds)
    except ValueError:
        return None


def tap_target_center(
    tap_target: ET.Element, switch_node: ET.Element
) -> Optional[tuple[int, int]]:
    """点击坐标：优先 Switch 本体 bounds，其次可点击行。"""
    bounds = switch_node.attrib.get("bounds") or tap_target.attrib.get("bounds") or ""
    return tap_element_bounds(bounds)


def collect_texts_from_xml(xml_path: Path) -> list[str]:
    if not xml_path.is_file():
        return []
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError:
        return []
    out: list[str] = []
    for el in root.iter("node"):
        for attr in ("text", "content-desc"):
            text = (el.attrib.get(attr) or "").strip()
            if text:
                out.append(text)
    return out
