"""NL UI 动作原语：复用现有 ui_automatic / ui_u2。"""

from __future__ import annotations

import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Optional
from shlex import split as shlex_split

from utils.tdd.ui_automatic import click_by_match, wake_and_unlock_if_screen_off
from utils.tdd.ui_u2 import dump_current_ui, dump_hierarchy_xml, release_uiautomator2
from utils.tdd.ui_paths import device_ui_dir
from utils.tdd.ui_xml import (
    build_parent_map,
    clickable_tap_target,
    node_reported_displayed,
    resolve_tap_node,
    tap_element_bounds,
)

StepReporter = Callable[[str], None]


class OptionalStepSkip(Exception):
    """optional 步骤未命中控件时跳过（非失败）。"""


def _run_adb(device_id: str, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["adb", "-s", device_id, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def resolve_device_id(device_info: dict[str, Any] | None) -> str:
    dut_list = (device_info or {}).get("DUT") or []
    if dut_list and isinstance(dut_list[0], dict):
        return str(dut_list[0].get("device_id") or "").strip()
    return ""


# 拨号盘按键：text / content-desc 候选（* / # 常无 text，仅有无障碍描述）
DIAL_KEY_LABELS: dict[str, tuple[str, ...]] = {
    "0": ("0",),
    "1": ("1",),
    "2": ("2",),
    "3": ("3",),
    "4": ("4",),
    "5": ("5",),
    "6": ("6",),
    "7": ("7",),
    "8": ("8",),
    "9": ("9",),
    "*": ("*", "星号", "Star", "star", "Asterisk", "asterisk"),
    "#": ("#", "井号", "Pound", "pound", "Hash", "hash", "Number", "number"),
    "+": ("+", "加号", "Plus", "plus"),
}


def _tap_keyevent(device_id: str, keycode: str) -> bool:
    result = _run_adb(device_id, "shell", "input", "keyevent", keycode)
    return result.returncode == 0


def _adb_tap_xy(device_id: str, x: int, y: int) -> bool:
    result = _run_adb(device_id, "shell", "input", "tap", str(x), str(y))
    return result.returncode == 0


def _score_dial_key_node(el: ET.Element, key: str, label: str) -> int:
    text = (el.attrib.get("text") or "").strip()
    desc = (el.attrib.get("content-desc") or "").strip()
    rid = (el.attrib.get("resource-id") or "").lower()
    cls = (el.attrib.get("class") or "").lower()
    if "edittext" in cls:
        return -1
    score = 0
    if text == label or desc == label:
        score += 8
    elif label in text or label in desc:
        score += 3
    else:
        return -1
    if el.attrib.get("clickable") == "true":
        score += 4
    if "dialpad" in rid or "dial_pad" in rid or "keypad" in rid:
        score += 6
    if key.isdigit() and (f"key{key}" in rid or rid.endswith(f"/{key}") or f"_{key}" in rid):
        score += 5
    if key == "*" and ("star" in rid or "asterisk" in rid):
        score += 5
    if key == "#" and ("pound" in rid or "hash" in rid or "sharp" in rid):
        score += 5
    return score


def _find_dial_key_node(root: ET.Element, parent_map: dict, key: str) -> Optional[ET.Element]:
    labels = DIAL_KEY_LABELS.get(key)
    if not labels:
        return None
    candidates: list[tuple[int, ET.Element]] = []
    for el in root.iter("node"):
        if not node_reported_displayed(el):
            continue
        best = -1
        for label in labels:
            best = max(best, _score_dial_key_node(el, key, label))
        if best < 0:
            continue
        tap_node = resolve_tap_node(el, parent_map)
        candidates.append((best, tap_node))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _tap_dial_key(device_id: str, key: str) -> bool:
    xml = _dump_xml(device_id)
    if not xml:
        return False
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return False
    parent_map = build_parent_map(root)
    tap_node = _find_dial_key_node(root, parent_map, key)
    if tap_node is None:
        return False
    center = tap_element_bounds(tap_node.attrib.get("bounds") or "")
    if center is None:
        return False
    if not _adb_tap_xy(device_id, center[0], center[1]):
        return False
    time.sleep(0.25)
    return True


def _dial_keys(device_id: str, keys: str, *, report: StepReporter) -> None:
    sequence = (keys or "").strip()
    if not sequence:
        raise RuntimeError("dial_keys 为空")
    for index, ch in enumerate(sequence, start=1):
        if not _tap_dial_key(device_id, ch):
            raise RuntimeError(f"拨号盘未找到按键「{ch}」（第 {index}/{len(sequence)} 个）")
        report(f"已点击拨号键 {ch} ({index}/{len(sequence)})")
    time.sleep(0.3)


def _swipe_direction(device_id: str, direction: str) -> bool:
    presets = {
        "up": ("360", "1100", "360", "700", "300"),
        "down": ("360", "700", "360", "1100", "300"),
        "left": ("700", "900", "300", "900", "300"),
        "right": ("300", "900", "700", "900", "300"),
    }
    coords = presets.get(direction, presets["up"])
    result = _run_adb(device_id, "shell", "input", "swipe", *coords)
    return result.returncode == 0


def _ui_contains_text(xml: str, needle: str) -> bool:
    if not needle:
        return False
    return needle in xml


def _ui_contains_desc(xml: str, needle: str) -> bool:
    if not needle:
        return False
    return f'content-desc="{needle}"' in xml or f"content-desc='{needle}'" in xml or needle in xml


def _node_text_or_desc(node: ET.Element) -> str:
    return f"{node.attrib.get('text') or ''} {node.attrib.get('content-desc') or ''}"


def _is_node_enabled(node: ET.Element) -> bool:
    value = (node.attrib.get("enabled") or "true").strip().lower()
    return value != "false"


def _is_node_clickable(node: ET.Element) -> bool:
    return (node.attrib.get("clickable") or "").strip().lower() == "true"


def _class_is_button(cls: str) -> bool:
    low = (cls or "").lower()
    return "button" in low or low.endswith(".button")


def _score_text_tap_candidate(
    node: ET.Element,
    tap_node: ET.Element,
    needle: str,
    *,
    match_mode: str,
) -> int:
    """同文案多命中时打分：优先可点按钮，避免点到标题 TextView。"""
    text = (node.attrib.get("text") or "").strip()
    desc = (node.attrib.get("content-desc") or "").strip()
    cls = (node.attrib.get("class") or "")
    tap_cls = (tap_node.attrib.get("class") or "")
    score = 0

    if match_mode == "desc":
        exact = desc == needle
        contains = needle in desc or needle in text
    else:
        exact = text == needle or desc == needle
        contains = needle in text or needle in desc
    if exact:
        score += 25
    elif contains:
        score += 8
    else:
        return -10_000

    node_clickable = _is_node_clickable(node)
    tap_clickable = _is_node_clickable(tap_node)
    if node_clickable:
        score += 60
    if tap_clickable:
        score += 45
    if _class_is_button(cls) or _class_is_button(tap_cls):
        score += 35
    # 纯标题 TextView（自身与解析后的 tap 都不可点）大幅降权
    if "textview" in cls.lower() and not node_clickable and not tap_clickable:
        score -= 40
    if not _is_node_enabled(node) or not _is_node_enabled(tap_node):
        score -= 200
    return score


def _pick_best_text_tap_target(
    xml: str,
    *,
    text: str = "",
    desc: str = "",
) -> Optional[tuple[ET.Element, int]]:
    needle_text = (text or "").strip()
    needle_desc = (desc or "").strip()
    if not needle_text and not needle_desc:
        return None
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    parent_map = build_parent_map(root)
    match_mode = "desc" if needle_desc and not needle_text else "text"
    needle = needle_desc if match_mode == "desc" else needle_text

    matches: list[ET.Element] = []
    for node in root.iter():
        if not node_reported_displayed(node):
            continue
        node_text = node.attrib.get("text") or ""
        node_desc = node.attrib.get("content-desc") or ""
        if needle_text and needle_text not in node_text and needle_text not in node_desc:
            continue
        if needle_desc and needle_desc not in node_desc and needle_desc not in node_text:
            continue
        if needle_text or needle_desc:
            matches.append(node)
    if not matches:
        return None

    ranked: list[tuple[int, ET.Element]] = []
    for node in matches:
        tap_node = resolve_tap_node(node, parent_map)
        if not node_reported_displayed(tap_node):
            continue
        center = tap_element_bounds(tap_node.attrib.get("bounds") or "")
        if center is None:
            continue
        score = _score_text_tap_candidate(node, tap_node, needle, match_mode=match_mode)
        ranked.append((score, tap_node))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    best_score, best_tap = ranked[0]
    return best_tap, best_score


def _tap_prefer_clickable(
    device_id: str,
    *,
    text: str = "",
    desc: str = "",
    scroll: bool = True,
    report: Optional[StepReporter] = None,
) -> bool:
    """按文案点击，同文案多控件时优先可点按钮（不走 click_by_match 的首匹配/缓存）。"""
    max_scrolls = 10 if scroll else 0
    label = text or desc
    for attempt in range(max_scrolls + 1):
        xml = _dump_xml(device_id)
        if xml:
            picked = _pick_best_text_tap_target(xml, text=text, desc=desc)
            if picked is not None:
                tap_node, score = picked
                center = tap_element_bounds(tap_node.attrib.get("bounds") or "")
                if center is not None and _adb_tap_xy(device_id, center[0], center[1]):
                    if report:
                        cls = (tap_node.attrib.get("class") or "").split(".")[-1]
                        clickable = tap_node.attrib.get("clickable") or "false"
                        report(
                            f"已点击「{label}」→ {cls} clickable={clickable} "
                            f"@({center[0]},{center[1]}) score={score}"
                        )
                    time.sleep(0.5)
                    return True
        if attempt >= max_scrolls:
            break
        _swipe_direction(device_id, "up")
        time.sleep(0.45)
    # 兜底：旧逻辑（设置项等非 Button 场景）
    if text:
        return click_by_match(device_id, {"keyword": text}, max_scrolls=max_scrolls)
    if desc:
        return click_by_match(device_id, {"content-desc": desc}, max_scrolls=max_scrolls)
    return False


def _find_matching_nodes(xml: str, *, text: str = "", desc: str = "") -> list[ET.Element]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    matches: list[ET.Element] = []
    needle_text = (text or "").strip()
    needle_desc = (desc or "").strip()
    for node in root.iter():
        if not node_reported_displayed(node):
            continue
        node_text = node.attrib.get("text") or ""
        node_desc = node.attrib.get("content-desc") or ""
        if needle_text and needle_text not in node_text and needle_text not in node_desc:
            continue
        if needle_desc and needle_desc not in node_desc and needle_desc not in node_text:
            continue
        if needle_text or needle_desc:
            matches.append(node)
    return matches


def _text_is_clickable(xml: str, text: str) -> bool:
    matches = _find_matching_nodes(xml, text=text)
    if not matches:
        return False
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return False
    parent_map = build_parent_map(root)
    for node in matches:
        if not _is_node_enabled(node):
            continue
        tap = clickable_tap_target(node, parent_map)
        if _is_node_clickable(tap) and _is_node_enabled(tap):
            return True
        # 自身可点或 enabled
        if _is_node_clickable(node) and _is_node_enabled(node):
            return True
    # 兜底：文案已出现且 enabled（部分工模未标 clickable）
    for node in matches:
        if _is_node_enabled(node):
            return True
    return False


def _capture_screenshot(device_id: str, dest: Path) -> bool:
    proc = subprocess.run(
        ["adb", "-s", device_id, "exec-out", "screencap", "-p"],
        capture_output=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(proc.stdout)
    return dest.is_file() and dest.stat().st_size > 0


def _dump_xml(device_id: str) -> Optional[str]:
    xml = dump_hierarchy_xml(device_id)
    if xml:
        return xml
    path = dump_current_ui(device_id)
    if path and path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")
    return None


def _wait_until(device_id: str, step: dict[str, Any], *, report: StepReporter) -> None:
    condition = str(step.get("condition") or "").strip()
    timeout = float(step.get("timeout") or 30)
    poll = float(step.get("poll") or 0.5)
    text = str(step.get("text") or "").strip()
    desc = str(step.get("desc") or step.get("content-desc") or "").strip()
    deadline = time.time() + max(0.1, timeout)
    last_xml = ""

    while True:
        xml = _dump_xml(device_id) or ""
        last_xml = xml
        ok = False
        if condition == "text_present":
            ok = _ui_contains_text(xml, text)
        elif condition == "text_gone":
            ok = not _ui_contains_text(xml, text)
        elif condition == "desc_present":
            ok = _ui_contains_desc(xml, desc)
        elif condition == "desc_gone":
            ok = not _ui_contains_desc(xml, desc)
        elif condition == "clickable":
            ok = _text_is_clickable(xml, text)
        if ok:
            report(f"wait_until 满足: {condition}")
            return
        if time.time() >= deadline:
            break
        time.sleep(max(0.1, poll))

    detail = text or desc or condition
    raise RuntimeError(f"wait_until 超时({timeout}s): {condition} · {detail}")


def execute_step(device_id: str, step: dict[str, Any], *, report: StepReporter, evidence_dir: Path) -> None:
    op = str(step.get("op") or "").strip()
    optional = bool(step.get("optional"))
    if op == "wake":
        if not wake_and_unlock_if_screen_off(device_id):
            raise RuntimeError("亮屏解锁失败")
        return
    if op == "home":
        if not _tap_keyevent(device_id, "3"):
            raise RuntimeError("返回桌面失败")
        time.sleep(0.4)
        return
    if op == "back":
        if not _tap_keyevent(device_id, "4"):
            raise RuntimeError("返回键失败")
        time.sleep(0.4)
        return
    if op == "shell":
        cmd = str(step.get("cmd") or "").strip()
        shell_args = shlex_split(cmd)
        if not shell_args:
            raise RuntimeError("shell 命令为空")
        result = _run_adb(device_id, "shell", *shell_args, timeout=60)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(detail or f"shell 执行失败: {cmd}")
        time.sleep(0.6)
        return
    if op == "tap_text":
        text = str(step.get("text") or "").strip()
        scroll = bool(step.get("scroll", True))
        ok = _tap_prefer_clickable(device_id, text=text, scroll=scroll, report=report)
        if not ok:
            if optional:
                raise OptionalStepSkip(f"可选步骤跳过：未找到文本「{text}」")
            raise RuntimeError(f"未找到可点击文本: {text}")
        return
    if op == "tap_desc":
        desc = str(step.get("desc") or step.get("content-desc") or "").strip()
        ok = _tap_prefer_clickable(
            device_id,
            desc=desc,
            scroll=bool(step.get("scroll", True)),
            report=report,
        )
        if not ok:
            if optional:
                raise OptionalStepSkip(f"可选步骤跳过：未找到 content-desc「{desc}」")
            raise RuntimeError(f"未找到可点击 content-desc: {desc}")
        return
    if op == "swipe":
        direction = str(step.get("direction") or "up").lower()
        if not _swipe_direction(device_id, direction):
            raise RuntimeError(f"滑动失败: {direction}")
        time.sleep(0.5)
        return
    if op == "wait":
        seconds = float(step.get("seconds") or 1)
        time.sleep(max(0.0, seconds))
        return
    if op == "wait_until":
        try:
            _wait_until(device_id, step, report=report)
        except RuntimeError:
            if optional:
                raise OptionalStepSkip("可选步骤跳过：wait_until 未满足")
            raise
        return
    if op == "dial_keys":
        keys = str(step.get("keys") or step.get("text") or "").strip()
        try:
            _dial_keys(device_id, keys, report=report)
        except RuntimeError:
            if optional:
                raise OptionalStepSkip(f"可选步骤跳过：拨号盘输入失败「{keys}」")
            raise
        return
    if op == "uidump":
        path = dump_current_ui(device_id)
        if path is None:
            raise RuntimeError("界面 dump 失败")
        report(f"已保存 UI dump: {path.name}")
        return
    if op == "screenshot":
        name = str(step.get("name") or "screenshot").strip() or "screenshot"
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
        dest = evidence_dir / f"{safe}.png"
        if not _capture_screenshot(device_id, dest):
            raise RuntimeError("截图失败")
        report(f"已保存截图: {dest.name}")
        return
    if op in {"assert_text", "assert_desc"}:
        xml_path = dump_current_ui(device_id)
        if xml_path is None or not xml_path.is_file():
            raise RuntimeError("断言前界面 dump 失败")
        xml = xml_path.read_text(encoding="utf-8", errors="replace")
        present = step.get("present", True)
        if op == "assert_text":
            needle = str(step.get("text") or "").strip()
            found = _ui_contains_text(xml, needle)
            label = f"文本「{needle}」"
        else:
            needle = str(step.get("desc") or step.get("content-desc") or "").strip()
            found = _ui_contains_desc(xml, needle)
            label = f"描述「{needle}」"
        if present and not found:
            if optional:
                raise OptionalStepSkip(f"可选断言跳过：未出现 {label}")
            raise RuntimeError(f"断言失败：界面未出现 {label}")
        if not present and found:
            if optional:
                raise OptionalStepSkip(f"可选断言跳过：不应出现但仍出现 {label}")
            raise RuntimeError(f"断言失败：界面不应出现 {label}")
        return
    raise RuntimeError(f"未知操作: {op}")


def evidence_dir_for(device_id: str) -> Path:
    return device_ui_dir(device_id)


def cleanup_device(device_id: str) -> None:
    if device_id:
        release_uiautomator2(device_id, wait_ready=False)
