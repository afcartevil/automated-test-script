# -*- coding: utf-8 -*-
import logging
import os
import re
import time
import xml.etree.ElementTree as ET

import pytest

from src.utils.adb.adb_utils import (
    adb_shell,
    execute_command,
    getprop,
    is_GO_device,
)
from src.utils.test_case_util.CommonUtil import CommonUtil


# ──────────────────────────── 期望列表 ────────────────────────────
# 非 Go 设备：完整列表
EXPECT_APPS_NORMAL = [
    "Google",
    "Chrome",
    "Gmail",
    "Maps",
    "YouTube",
    "Drive",
    "YT Music",
    "Google TV",
    "Meet",
    "Photos",
]
# Go 设备：完整列表
EXPECT_APPS_GO = [
    "Google",
    "Chrome",
    "Gmail",
    "Maps",
    "YouTube",
    "Drive",
    "YT Music",
    "Google TV",
    "Meet",
    "Gallery",
]

_UI_DUMP_REMOTE = "/sdcard/sdd_google_folder_ui_dump.xml"
_FOLDER_CONTENT_ID = "com.transsion.launcher3:id/folder_content"
_SCROLL_VIEW_ID = "com.transsion.launcher3:id/scroll_view"
_GOOGLE_FOLDER_DESC_PREFIX = "Folder: Google"
_MAX_FOLDER_SCROLLS = 10


def _parse_bounds(bounds_str: str):
    match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str or "")
    if not match:
        raise ValueError(f"invalid bounds: {bounds_str}")
    return tuple(int(v) for v in match.groups())


def _wake_and_go_home(device_serial: str) -> None:
    adb_shell(device_serial, "input keyevent 224")
    time.sleep(0.5)
    adb_shell(device_serial, "input keyevent 3")
    time.sleep(2)


def _dump_ui_xml(device_serial: str) -> str:
    adb_shell(device_serial, f"uiautomator dump {_UI_DUMP_REMOTE}")
    time.sleep(0.5)
    local_dir = CommonUtil.create_dir(device_serial, "ui_dump")
    local_path = os.path.join(local_dir, "window_dump.xml")
    pull_cmd = f'adb -s {device_serial} pull "{_UI_DUMP_REMOTE}" "{local_path}"'
    pull_result = execute_command(pull_cmd)
    if not pull_result["success"] or not os.path.exists(local_path):
        pytest.fail(f"pull ui dump failed: {pull_result}")
    with open(local_path, encoding="utf-8") as f:
        return f.read()


def _tap_bounds_center(device_serial: str, bounds_str: str) -> None:
    x1, y1, x2, y2 = _parse_bounds(bounds_str)
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    adb_shell(device_serial, f"input tap {cx} {cy}")


def _find_google_folder_node(root: ET.Element):
    for node in root.iter("node"):
        content_desc = node.get("content-desc") or ""
        if content_desc.startswith(_GOOGLE_FOLDER_DESC_PREFIX):
            return node
    return None


def _find_folder_scroll_bounds(root: ET.Element):
    """返回文件夹内可滚动区域 bounds，用于执行上/下滑。"""
    for node in root.iter("node"):
        if node.get("resource-id") == _SCROLL_VIEW_ID and node.get("scrollable") == "true":
            return node.get("bounds")
    for node in root.iter("node"):
        if node.get("resource-id") == _FOLDER_CONTENT_ID:
            return node.get("bounds")
    return None


def _scroll_folder_down(device_serial: str, bounds_str: str) -> None:
    """在文件夹滚动区域内上划，显示下方更多应用。"""
    x1, y1, x2, y2 = _parse_bounds(bounds_str)
    cx = (x1 + x2) // 2
    upper_y = y1 + int((y2 - y1) * 0.25)
    lower_y = y1 + int((y2 - y1) * 0.75)
    adb_shell(device_serial, f"input swipe {cx} {lower_y} {cx} {upper_y} 300")


def _scroll_folder_to_top_once(device_serial: str, bounds_str: str) -> None:
    """下滑一次，尽量滚回列表顶部，保证首屏读取顺序稳定（替代原先连续 3 次）。"""
    x1, y1, x2, y2 = _parse_bounds(bounds_str)
    cx = (x1 + x2) // 2
    upper_y = y1 + int((y2 - y1) * 0.25)
    lower_y = y1 + int((y2 - y1) * 0.75)
    adb_shell(device_serial, f"input swipe {cx} {upper_y} {cx} {lower_y} 300")


def _collect_visible_folder_apps(root: ET.Element):
    folder_content = None
    for node in root.iter("node"):
        if node.get("resource-id") == _FOLDER_CONTENT_ID:
            folder_content = node
            break
    if folder_content is None:
        return []

    apps = []
    for node in folder_content.iter("node"):
        if node.get("class") != "android.widget.TextView":
            continue
        if node.get("clickable") != "true":
            continue
        name = (node.get("content-desc") or node.get("text") or "").strip()
        if not name:
            continue
        bounds = node.get("bounds")
        if not bounds:
            continue
        x1, y1, _, _ = _parse_bounds(bounds)
        apps.append((y1, x1, name))

    apps.sort()
    return [name for _, _, name in apps]


def _collect_all_folder_apps(device_serial: str) -> list[str]:
    """
    文件夹应用过多时首屏无法显示全部，需上划后合并多次 dump 结果，
    逐屏上划直至没有新应用出现。
    打开后下滑一次回到顶部附近，避免上次滚动位置导致首屏图标顺序误判。
    """
    folder_root = ET.fromstring(_dump_ui_xml(device_serial))
    scroll_bounds = _find_folder_scroll_bounds(folder_root)
    if scroll_bounds:
        _scroll_folder_to_top_once(device_serial, scroll_bounds)
        time.sleep(0.35)

    all_apps: list[str] = []
    seen: set[str] = set()
    for scroll_idx in range(_MAX_FOLDER_SCROLLS):
        folder_root = ET.fromstring(_dump_ui_xml(device_serial))
        visible_apps = _collect_visible_folder_apps(folder_root)
        new_apps = [name for name in visible_apps if name not in seen]
        if scroll_idx > 0 and not new_apps:
            break
        for name in new_apps:
            seen.add(name)
            all_apps.append(name)
        # logging.info(
        #     "folder scroll %s: visible=%s, new=%s",
        #     scroll_idx,
        #     visible_apps,
        #     new_apps,
        # )
        if scroll_idx + 1 >= _MAX_FOLDER_SCROLLS:
            break
        scroll_bounds = _find_folder_scroll_bounds(folder_root) or scroll_bounds
        if not scroll_bounds:
            break
        _scroll_folder_down(device_serial, scroll_bounds)
        time.sleep(0.5)

    return all_apps


def _build_expected_apps(is_go: bool, actual_apps):
    template = EXPECT_APPS_GO if is_go else EXPECT_APPS_NORMAL
    has_chrome = "Chrome" in actual_apps
    has_google_tv = "Google TV" in actual_apps
    expected = []
    for app in template:
        if app == "Chrome" and not has_chrome:
            continue
        if app == "Google TV" and not has_google_tv:
            continue
        expected.append(app)
    return expected


def _open_google_folder(device_serial: str):
    _wake_and_go_home(device_serial)
    home_xml = _dump_ui_xml(device_serial)
    home_root = ET.fromstring(home_xml)
    folder_node = _find_google_folder_node(home_root)
    if folder_node is None:
        pytest.fail("Not find Google folder on DHS.")

    _tap_bounds_center(device_serial, folder_node.get("bounds"))
    time.sleep(3)

    actual_apps = _collect_all_folder_apps(device_serial)
    if not actual_apps:
        pytest.fail("Google folder opened but no app icons were found in UI dump.")
    return actual_apps


@pytest.mark.require_android_version_min(16)
def test_google_folder_apk_list(device_serial):
    """
    打开 Home 界面 Google 文件夹，校验预装 GMS 应用图标顺序。
    仅 en-US 语言环境下执行。
    """
    locale = (getprop("persist.sys.locale", device_serial) or "").strip()
    if locale != "en-US":
        pytest.skip(f"locale is {locale!r}, require en-US")

    try:
        actual_apps = _open_google_folder(device_serial)
        logging.info("Google folder apps: %s", actual_apps)

        is_go = is_GO_device(device_serial)
        expected_apps = _build_expected_apps(is_go, actual_apps)
        logging.info("Expected prefix: %s", expected_apps)

        if len(actual_apps) < len(expected_apps):
            pytest.fail(
                "Google folder has fewer apps than expected.\n"
                f"expected prefix ({len(expected_apps)}): {expected_apps}\n"
                f"actual ({len(actual_apps)}): {actual_apps}"
            )

        actual_prefix = actual_apps[: len(expected_apps)]
        if actual_prefix != expected_apps:
            device_type = "Go" if is_go else "normal"
            pytest.fail(
                f"The {device_type} application order in the Google folder is incorrect.\n"
                f"expected: {expected_apps}\n"
                f"actual:   {actual_prefix}"
            )
    finally:
        adb_shell(device_serial, "input keyevent 4")
        adb_shell(device_serial, "input keyevent 3")
