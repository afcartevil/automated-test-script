"""设置页带标签的 Switch 行：读状态、切换至目标。"""

import subprocess
import time
import xml.etree.ElementTree as ET
from typing import Any, Callable, Optional, Union

from utils.tdd.ui_u2 import (
    acquire_u2,
    dump_hierarchy_xml,
    release_uiautomator2,
)
from utils.tdd.ui_xml import (
    find_labeled_switch_in_root,
    switch_is_checked,
    tap_target_center,
)

SETTLE_AFTER_TAP = 0.65
EnableTarget = Union[bool, int, str]


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


def _adb_tap(device_id: str, x: int, y: int) -> bool:
    result = subprocess.run(
        ["adb", "-s", device_id, "shell", "input", "tap", str(x), str(y)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.returncode == 0


def _tap_switch(device_id: str, device: Any, tap_target: ET.Element, switch_node: ET.Element) -> bool:
    """点击指定 Switch 的 bounds 中心（不用 resourceId，避免多个 switch_widget 误点）。"""
    _ = device, tap_target
    center = tap_target_center(tap_target, switch_node)
    if center is None:
        return False
    return _adb_tap(device_id, center[0], center[1])


def _set_labeled_switch_enable_adb(
    device_id: str,
    target: bool,
    label_pred: Callable[[str], bool],
    *,
    max_scrolls: int = 0,
    swipe_down: Optional[Callable[[str], bool]] = None,
    settle_after_scroll: float = 0.5,
) -> bool:
    for slide in range(max(0, max_scrolls) + 1):
        xml = dump_hierarchy_xml(device_id, compressed=False)
        if not xml:
            return False
        root = ET.fromstring(xml)
        pair = find_labeled_switch_in_root(root, label_pred)
        if pair is not None:
            tap_target, switch_node, _ = pair
            checked = switch_is_checked(switch_node)
            if checked == target:
                return True
            center = tap_target_center(tap_target, switch_node)
            if center is None:
                return False
            if not _adb_tap(device_id, center[0], center[1]):
                return False
            if SETTLE_AFTER_TAP > 0:
                time.sleep(SETTLE_AFTER_TAP)
            xml_after = dump_hierarchy_xml(device_id, compressed=False)
            if not xml_after:
                return False
            pair_after = find_labeled_switch_in_root(
                ET.fromstring(xml_after), label_pred
            )
            if pair_after is None:
                return False
            return switch_is_checked(pair_after[1]) == target
        if slide >= max_scrolls:
            return False
        if swipe_down is None or not swipe_down(device_id):
            return False
        if settle_after_scroll > 0:
            time.sleep(settle_after_scroll)
    return False


def set_labeled_switch_enable(
    device_id: str,
    enable: EnableTarget,
    label_pred: Callable[[str], bool],
    *,
    max_scrolls: int = 0,
    swipe_down: Optional[Callable[[str], bool]] = None,
    settle_after_scroll: float = 0.5,
) -> bool:
    """
    在当前页按标签谓词找到 Switch 并切至目标状态。

    单 u2 会话内 dump（完整 hierarchy）→ 点击 Switch → 校验。
    u2 不可用时回退 adb dump + adb tap。
    """
    if not device_id:
        return False
    target = normalize_enable(enable)
    if target is None:
        return False

    device = acquire_u2(device_id)
    if device is None:
        return _set_labeled_switch_enable_adb(
            device_id,
            target,
            label_pred,
            max_scrolls=max_scrolls,
            swipe_down=swipe_down,
            settle_after_scroll=settle_after_scroll,
        )

    try:
        pair = None
        for slide in range(max(0, max_scrolls) + 1):
            xml = dump_hierarchy_xml(device_id, compressed=False, device=device)
            if not xml:
                return False
            root = ET.fromstring(xml)
            pair = find_labeled_switch_in_root(root, label_pred)
            if pair is not None:
                break
            if slide >= max_scrolls:
                return False
            if swipe_down is None or not swipe_down(device_id):
                return False
            if settle_after_scroll > 0:
                time.sleep(settle_after_scroll)

        if pair is None:
            return False

        tap_target, switch_node, _ = pair
        checked = switch_is_checked(switch_node)
        if checked == target:
            return True

        if not _tap_switch(device_id, device, tap_target, switch_node):
            return False
        if SETTLE_AFTER_TAP > 0:
            time.sleep(SETTLE_AFTER_TAP)

        xml_after = dump_hierarchy_xml(device_id, compressed=False, device=device)
        if not xml_after:
            return False
        pair_after = find_labeled_switch_in_root(
            ET.fromstring(xml_after), label_pred
        )
        if pair_after is None:
            return False
        return switch_is_checked(pair_after[1]) == target
    except Exception:
        return False
    finally:
        release_uiautomator2(device_id, wait_ready=False)
