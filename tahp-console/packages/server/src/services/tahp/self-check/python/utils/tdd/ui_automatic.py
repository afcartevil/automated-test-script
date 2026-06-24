import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Optional

from utils.tdd.ui_paths import device_ui_dir as _device_ui_dir
from utils.tdd.ui_u2 import (
    acquire_u2,
    click_dialog_positive,
    dump_current_ui,
    release_uiautomator2,
)
from utils.tdd.ui_xml import (
    build_parent_map as _build_parent_map,
    node_reported_displayed as _node_reported_displayed,
    parse_bounds_center as _parse_bounds_center,
    resolve_tap_node as _resolve_tap_node,
)

DEFAULT_MAX_SCROLLS = 10
DEFAULT_TOP_DEAD_ZONE = 200
DEFAULT_BOTTOM_DEAD_ZONE = 200
DEFAULT_SWIPE = ("360", "1100", "360", "700", 300)
# 亮屏解锁上滑（与 apk/init、ui_sim_pin 一致，适配约 1080 宽屏）
KEYGUARD_UNLOCK_SWIPE = ("540", "1800", "540", "500", 250)
DEFAULT_SLEEP_AFTER_SWIPE = 0.65
DEFAULT_SLEEP_AFTER_TAP = 0.55
MIN_PHONE_MATCH_DIGITS = 7


def _ui_json_path(device_id: str) -> Path:
    return _device_ui_dir(device_id) / "ui.json"


def _load_ui_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


def _save_ui_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_phone_digits(value: str) -> str:
    """去掉号码中的空格、横线等非数字字符。"""
    return re.sub(r"\D", "", value or "")


def _cache_key_for_match(match_content: dict) -> str:
    """
    ui.json 的 key。
    keyword 模式与 scripts 一致，直接用 keyword 字符串；
    text/content-desc 组合模式使用 ``text:...|desc:...``，避免与 scripts 多步导航格式混用。
    """
    keyword = (match_content.get("keyword") or "").strip()
    if keyword:
        if match_content.get("match_phone_digits"):
            digits = extract_phone_digits(keyword)
            if digits:
                return f"phone:{digits}"
        return keyword
    parts: list[str] = []
    if match_content.get("text") is not None:
        parts.append(f"text:{str(match_content['text']).strip()}")
    if match_content.get("content-desc") is not None:
        parts.append(f"desc:{str(match_content['content-desc']).strip()}")
    return "|".join(parts)


def _entry_from_cached_ui(ui_data: dict[str, Any], cache_key: str) -> Optional[dict[str, Any]]:
    """
    读取单步点击缓存项。格式（每设备一个 ui.json）::

        {
          "SIM卡与网络设置": {
            "slide_down_times": 0,
            "location": [540, 1200]
          }
        }
    """
    ent = ui_data.get(cache_key)
    if not isinstance(ent, dict):
        return None
    loc = ent.get("location")
    if not isinstance(loc, list) or len(loc) != 2:
        return None
    try:
        cx, cy = int(loc[0]), int(loc[1])
    except (TypeError, ValueError):
        return None
    slide = ent.get("slide_down_times", 0)
    try:
        slide_i = int(slide)
    except (TypeError, ValueError):
        slide_i = 0
    return {"slide_down_times": slide_i, "location": [cx, cy]}


def _persist_cache_entry(device_id: str, cache_key: str, entry: dict[str, Any]) -> None:
    if not cache_key:
        return
    path = _ui_json_path(device_id)
    ui_data = _load_ui_json(path)
    ui_data[cache_key] = {
        "slide_down_times": int(entry["slide_down_times"]),
        "location": [int(entry["location"][0]), int(entry["location"][1])],
    }
    _save_ui_json(path, ui_data)


def _run_adb(device_id, args, timeout=30):
    if not device_id:
        raise ValueError("device_id 不能为空")
    cmd = ["adb", "-s", device_id, *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def open_quick_settings(device_id: str, *, sleep_after: float = 0.5) -> bool:
    """
    展开快捷开关（Quick Settings）界面。

    等价命令：``adb shell cmd statusbar expand-settings``
    """
    if not device_id:
        return False
    try:
        result = _run_adb(
            device_id,
            ["shell", "cmd", "statusbar", "expand-settings"],
        )
        if result.returncode != 0:
            return False
        output = f"{result.stdout or ''}{result.stderr or ''}"
        if "Error" in output or "Exception" in output:
            return False
        if sleep_after > 0:
            time.sleep(sleep_after)
        return True
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return False


def close_quick_settings(device_id: str, *, sleep_after: float = 0.5) -> bool:
    """
    收起快捷开关 / 状态栏下拉界面。

    等价命令：``adb shell cmd statusbar collapse``
    """
    if not device_id:
        return False
    try:
        result = _run_adb(
            device_id,
            ["shell", "cmd", "statusbar", "collapse"],
        )
        if result.returncode != 0:
            return False
        output = f"{result.stdout or ''}{result.stderr or ''}"
        if "Error" in output or "Exception" in output:
            return False
        if sleep_after > 0:
            time.sleep(sleep_after)
        return True
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return False


def set_airplane_mode(device_id: str, enabled: bool, *, sleep_after: float = 0.5) -> bool:
    """
    打开或关闭飞行模式。

    等价命令：``adb shell cmd connectivity airplane-mode enable|disable``
    """
    if not device_id:
        return False
    try:
        cmd_value = "enable" if enabled else "disable"
        result = _run_adb(
            device_id,
            ["shell", "cmd", "connectivity", "airplane-mode", cmd_value],
        )
        if result.returncode != 0:
            return False
        output = f"{result.stdout or ''}{result.stderr or ''}"
        if "Error" in output or "Exception" in output:
            return False
        if sleep_after > 0:
            time.sleep(sleep_after)
        return True
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return False


def enable_airplane_mode(device_id: str, *, sleep_after: float = 0.5) -> bool:
    """打开飞行模式。"""
    return set_airplane_mode(device_id, True, sleep_after=sleep_after)


def disable_airplane_mode(device_id: str, *, sleep_after: float = 0.5) -> bool:
    """关闭飞行模式。"""
    return set_airplane_mode(device_id, False, sleep_after=sleep_after)


def _is_device_locked(device_id: str) -> bool:
    trust = _run_adb(device_id, ["shell", "dumpsys", "trust"])
    trust_text = f"{trust.stdout or ''}\n{trust.stderr or ''}".lower()
    if "devicelocked=true" in trust_text or "devicelocked=1" in trust_text:
        return True

    policy = _run_adb(device_id, ["shell", "dumpsys", "window", "policy"])
    text = f"{policy.stdout or ''}\n{policy.stderr or ''}".lower()
    lock_markers = (
        "isstatusbarkeyguard=true",
        "mshowinglockscreen=true",
        "keyguardshowing=true",
    )
    return any(marker in text for marker in lock_markers)


def _unlock_keyguard_after_wake(device_id: str, *, max_attempts: int = 3) -> bool:
    """亮屏后上滑解锁（MENU + swipe + dismiss-keyguard，与 init/sim_pin 一致）。"""
    x1, y1, x2, y2, duration_ms = KEYGUARD_UNLOCK_SWIPE
    for _ in range(max_attempts):
        _run_adb(device_id, ["shell", "input", "keyevent", "82"])
        _run_adb(
            device_id,
            [
                "shell",
                "input",
                "swipe",
                x1,
                y1,
                x2,
                y2,
                str(duration_ms),
            ],
        )
        _run_adb(device_id, ["shell", "wm", "dismiss-keyguard"])
        time.sleep(0.5)
        if not _is_device_locked(device_id):
            return True
    return not _is_device_locked(device_id)


def get_screen_state(device_id: str) -> str:
    """读取屏幕状态：ON / OFF / UNKNOWN（dumpsys display mScreenState）。"""
    if not device_id:
        return "UNKNOWN"
    try:
        result = _run_adb(device_id, ["shell", "dumpsys", "display"], timeout=20)
        text = f"{result.stdout or ''}{result.stderr or ''}"
        if re.search(r"mScreenState\s*=\s*ON\b", text, re.I):
            return "ON"
        if re.search(r"mScreenState\s*=\s*OFF\b", text, re.I):
            return "OFF"
    except (subprocess.TimeoutExpired, OSError, ValueError):
        pass
    return "UNKNOWN"


def wake_and_unlock_if_screen_off(device_id: str) -> bool:
    """未亮屏时执行 WAKEUP + 上滑解锁；已亮屏则不操作。"""
    if not device_id:
        return False
    if get_screen_state(device_id) == "ON":
        return True
    try:
        wake_result = _run_adb(device_id, ["shell", "input", "keyevent", "224"])
        if wake_result.returncode != 0:
            return False
        time.sleep(0.3)
        return _unlock_keyguard_after_wake(device_id)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return False


def ensure_screen_on_and_unlocked(device_id: str) -> bool:
    """确保屏幕已亮屏且已解锁（工模等自动化前置）。"""
    if not device_id:
        return False
    try:
        if get_screen_state(device_id) != "ON":
            wake_result = _run_adb(device_id, ["shell", "input", "keyevent", "224"])
            if wake_result.returncode != 0:
                return False
            time.sleep(0.3)
        if _is_device_locked(device_id):
            return _unlock_keyguard_after_wake(device_id)
        return True
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return False


# 兼容旧导入名
ensure_screen_on_and_unlock = ensure_screen_on_and_unlocked


def ensure_auxiliary_devices_awake(device_info) -> tuple[bool, str]:
    """检查 device_info 中各辅测机是否亮屏，未亮屏则亮屏解锁。"""
    aux_list = (device_info or {}).get("Auxiliary") or []
    for aux in aux_list:
        if not isinstance(aux, dict):
            continue
        device_id = (aux.get("device_id") or "").strip()
        if not device_id:
            continue
        if wake_and_unlock_if_screen_off(device_id):
            continue
        label = (aux.get("name") or aux.get("label") or device_id).strip()
        return False, f"辅测机 {label} 亮屏解锁失败"
    return True, ""


def screen_off_and_wake(
    device_id: str,
    *,
    off_seconds: float = 2.0,
    sleep_after_wake: float = 0.5,
) -> bool:
    """
    灭屏后亮屏并上滑解锁。

    KEYCODE_SLEEP → 等待 → KEYCODE_WAKEUP → 上滑解锁（最多 3 次）。
    """
    if not device_id:
        return False
    try:
        sleep_result = _run_adb(device_id, ["shell", "input", "keyevent", "223"])
        if sleep_result.returncode != 0:
            return False
        if off_seconds > 0:
            time.sleep(off_seconds)
        wake_result = _run_adb(device_id, ["shell", "input", "keyevent", "224"])
        if wake_result.returncode != 0:
            return False
        time.sleep(0.3)
        if not _unlock_keyguard_after_wake(device_id):
            return False
        if sleep_after_wake > 0:
            time.sleep(sleep_after_wake)
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def set_wifi_enable(device_id: str, enabled: bool, *, sleep_after: float = 0.5) -> bool:
    """
    打开或关闭 Wi-Fi 开关。

    等价命令：``adb shell svc wifi enable|disable``
    """
    if not device_id:
        return False
    try:
        state = "enable" if enabled else "disable"
        result = _run_adb(device_id, ["shell", "svc", "wifi", state])
        if result.returncode != 0:
            return False
        output = f"{result.stdout or ''}{result.stderr or ''}"
        if "Error" in output or "Exception" in output:
            return False
        if sleep_after > 0:
            time.sleep(sleep_after)
        return True
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return False


WIFI_SETTINGS_ACTION = "android.settings.WIFI_SETTINGS"
WIFI_SETTINGS_SETTLE_SECONDS = 1.0


def open_wifi_settings(device_id: str, *, settle_seconds: float = WIFI_SETTINGS_SETTLE_SECONDS) -> bool:
    """进入系统 Wi-Fi 设置界面。"""
    if not device_id:
        return False
    try:
        result = _run_adb(
            device_id,
            ["shell", "am", "start", "-a", WIFI_SETTINGS_ACTION],
            timeout=20,
        )
        if result.returncode != 0:
            return False
        output = f"{result.stdout or ''}{result.stderr or ''}"
        if "Error:" in output or "Exception" in output:
            return False
        if settle_seconds > 0:
            time.sleep(settle_seconds)
        return True
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return False


def set_mobile_data_enable(device_id: str, enabled: bool, *, sleep_after: float = 0.5) -> bool:
    """
    打开或关闭移动数据开关。

    等价命令：``adb shell svc data enable|disable``
    """
    if not device_id:
        return False
    try:
        state = "enable" if enabled else "disable"
        result = _run_adb(device_id, ["shell", "svc", "data", state])
        if result.returncode != 0:
            return False
        output = f"{result.stdout or ''}{result.stderr or ''}"
        if "Error" in output or "Exception" in output:
            return False
        if sleep_after > 0:
            time.sleep(sleep_after)
        return True
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return False


def _get_wm_size(device_id: str) -> tuple[int, int]:
    out = _run_adb(device_id, ["shell", "wm", "size"])
    if out.returncode != 0:
        return 1080, 2400
    text = (out.stdout or "") + (out.stderr or "")
    match = re.search(r":\s*(\d+)\s*x\s*(\d+)", text, re.I)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.search(r"\b(\d+)\s*x\s*(\d+)\b", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return 1080, 2400


def _bounds_center_y(bounds: str) -> int:
    return _parse_bounds_center(bounds)[1]


def _tap_center_in_vertical_dead_zone(
    bounds: str, screen_h: int, top_dead_zone_px: int, bottom_dead_zone_px: int
) -> bool:
    cy = _bounds_center_y(bounds)
    if top_dead_zone_px > 0 and cy < top_dead_zone_px:
        return True
    if bottom_dead_zone_px > 0 and cy >= screen_h - bottom_dead_zone_px:
        return True
    return False


def _node_matches_keyword(
    node: ET.Element,
    keyword: str,
    *,
    match_phone_digits: bool = False,
) -> bool:
    if not keyword:
        return False
    text = (node.attrib.get("text") or "").strip()
    desc = (node.attrib.get("content-desc") or "").strip()
    if keyword in text or keyword in desc:
        return True
    if not match_phone_digits:
        return False
    kw_digits = extract_phone_digits(keyword)
    if len(kw_digits) < MIN_PHONE_MATCH_DIGITS:
        return False
    return kw_digits in extract_phone_digits(text) or kw_digits in extract_phone_digits(desc)


def _node_matches_content(node: ET.Element, match_content: dict) -> bool:
    text = (node.attrib.get("text") or "").strip()
    desc = (node.attrib.get("content-desc") or "").strip()

    expected_text = match_content.get("text")
    if expected_text is not None and str(expected_text).strip() not in text:
        return False

    expected_desc = match_content.get("content-desc")
    if expected_desc is not None and str(expected_desc).strip() not in desc:
        return False

    return expected_text is not None or expected_desc is not None


def _find_tap_node_by_keyword(
    xml_path: Path,
    keyword: str,
    screen_h: int,
    top_dead_zone_px: int,
    bottom_dead_zone_px: int,
    *,
    match_phone_digits: bool = False,
) -> Optional[ET.Element]:
    root = ET.parse(xml_path).getroot()
    parent_map = _build_parent_map(root)
    for node in root.iter("node"):
        if not _node_matches_keyword(
            node, keyword, match_phone_digits=match_phone_digits
        ):
            continue
        if not _node_reported_displayed(node):
            continue
        tap_node = _resolve_tap_node(node, parent_map)
        if not _node_reported_displayed(tap_node):
            continue
        bounds = tap_node.attrib.get("bounds") or ""
        if not bounds:
            continue
        try:
            if _tap_center_in_vertical_dead_zone(
                bounds, screen_h, top_dead_zone_px, bottom_dead_zone_px
            ):
                continue
        except ValueError:
            continue
        return tap_node
    return None


def _find_tap_node_by_content(
    xml_path: Path,
    match_content: dict,
    screen_h: int,
    top_dead_zone_px: int,
    bottom_dead_zone_px: int,
) -> Optional[ET.Element]:
    if not xml_path.is_file():
        return None

    root = ET.parse(xml_path).getroot()
    parent_map = _build_parent_map(root)
    for node in root.iter("node"):
        if not _node_matches_content(node, match_content):
            continue
        if not _node_reported_displayed(node):
            continue
        tap_node = _resolve_tap_node(node, parent_map)
        if not _node_reported_displayed(tap_node):
            continue
        bounds = tap_node.attrib.get("bounds") or ""
        if not bounds:
            continue
        try:
            if _tap_center_in_vertical_dead_zone(
                bounds, screen_h, top_dead_zone_px, bottom_dead_zone_px
            ):
                continue
        except ValueError:
            continue
        return tap_node
    return None


def _tap_screen(device_id: str, x: int, y: int) -> bool:
    result = _run_adb(device_id, ["shell", "input", "tap", str(x), str(y)])
    return result.returncode == 0


def _swipe_down(device_id: str, swipe: tuple[str, str, str, str, int]) -> bool:
    x1, y1, x2, y2, duration_ms = swipe
    result = _run_adb(
        device_id,
        ["shell", "input", "swipe", x1, y1, x2, y2, str(duration_ms)],
    )
    return result.returncode == 0


def _ensure_device_scroll_index(
    device_id: str,
    target_slide: int,
    device_scroll_count: int,
    swipe: tuple[str, str, str, str, int],
    sleep_after_swipe: float,
) -> int:
    while device_scroll_count < target_slide:
        if not _swipe_down(device_id, swipe):
            break
        if sleep_after_swipe > 0:
            time.sleep(sleep_after_swipe)
        device_scroll_count += 1
    return device_scroll_count


def _find_tap_node_in_xml(
    xml_path: Path,
    match_content: dict,
    screen_h: int,
    top_dead: int,
    bottom_dead: int,
) -> Optional[ET.Element]:
    keyword = (match_content.get("keyword") or "").strip()
    if keyword:
        return _find_tap_node_by_keyword(
            xml_path,
            keyword,
            screen_h,
            top_dead,
            bottom_dead,
            match_phone_digits=bool(match_content.get("match_phone_digits")),
        )
    return _find_tap_node_by_content(
        xml_path, match_content, screen_h, top_dead, bottom_dead
    )


def _locate_match_on_screen(
    device_id: str,
    match_content: dict,
    screen_h: int,
    top_dead_zone: int,
    bottom_dead_zone: int,
    max_scrolls: int,
    swipe: tuple[str, str, str, str, int],
    sleep_after_swipe: float,
) -> dict[str, Any]:
    """在当前屏下滑查找匹配控件，返回缓存项 {slide_down_times, location}。"""
    device_scroll_count = 0
    for slide in range(max_scrolls + 1):
        xml_path = dump_current_ui(device_id)
        if xml_path is None:
            raise RuntimeError("uiautomator2 dump failed")

        tap_node = _find_tap_node_in_xml(
            xml_path,
            match_content,
            screen_h,
            top_dead_zone,
            bottom_dead_zone,
        )
        if tap_node is not None:
            bounds = tap_node.attrib.get("bounds") or ""
            if bounds:
                cx, cy = _parse_bounds_center(bounds)
                return {"slide_down_times": slide, "location": [cx, cy]}

        if slide >= max_scrolls:
            break
        device_scroll_count = _ensure_device_scroll_index(
            device_id,
            slide + 1,
            device_scroll_count,
            swipe,
            sleep_after_swipe,
        )

    cache_key = _cache_key_for_match(match_content)
    raise RuntimeError(
        f"match {cache_key!r} not found on current screen after {max_scrolls} scrolls"
    )


def _tap_cached_entry(
    device_id: str,
    entry: dict[str, Any],
    swipe: tuple[str, str, str, str, int],
    sleep_after_swipe: float,
    sleep_after_tap: float,
) -> bool:
    slide = int(entry["slide_down_times"])
    cx, cy = int(entry["location"][0]), int(entry["location"][1])
    _ensure_device_scroll_index(device_id, slide, 0, swipe, sleep_after_swipe)
    if not _tap_screen(device_id, cx, cy):
        return False
    if sleep_after_tap > 0:
        time.sleep(sleep_after_tap)
    return True


def click_by_match(
    device_id: str,
    match_content: dict,
    *,
    max_scrolls: int = DEFAULT_MAX_SCROLLS,
    top_dead_zone: int = DEFAULT_TOP_DEAD_ZONE,
    bottom_dead_zone: int = DEFAULT_BOTTOM_DEAD_ZONE,
    sleep_after_swipe: float = DEFAULT_SLEEP_AFTER_SWIPE,
    sleep_after_tap: float = DEFAULT_SLEEP_AFTER_TAP,
    prefer_cached_ui: bool = True,
) -> bool:
    """
    在当前页面根据匹配内容查找控件并点击一次。

    match_content 示例:
      {"keyword": "SIM卡与网络设置"}
      {"keyword": "13800138000", "match_phone_digits": True}
      {"text": "SIM1"}
      {"text": "SIM1", "content-desc": "SIM 卡 1"}

    keyword 匹配规则与 scripts/get_button_tool 一致：text 或 content-desc 子串包含即命中。
    match_phone_digits 为 True 时，比较前会去掉界面文案与 keyword 中的非数字字符（规避号码带空格）。
    成功点击后坐标写入 result_dir/ui/<device_id>/ui.json；下次优先使用缓存坐标。
    每次 dump 写入 result_dir/ui/<device_id>/_latest.xml（复用 u2 连接，减少 connect/stop）。
    """
    if not device_id:
        return False
    if not isinstance(match_content, dict) or not match_content:
        return False

    cache_key = _cache_key_for_match(match_content)
    if not cache_key:
        return False

    _, screen_h = _get_wm_size(device_id)
    swipe = (*DEFAULT_SWIPE[:4], DEFAULT_SWIPE[4])

    if prefer_cached_ui:
        ui_data = _load_ui_json(_ui_json_path(device_id))
        cached = _entry_from_cached_ui(ui_data, cache_key)
        if cached is not None and _tap_cached_entry(
            device_id, cached, swipe, sleep_after_swipe, sleep_after_tap
        ):
            _persist_cache_entry(device_id, cache_key, cached)
            return True

    if acquire_u2(device_id) is None:
        return False
    try:
        try:
            entry = _locate_match_on_screen(
                device_id,
                match_content,
                screen_h,
                top_dead_zone,
                bottom_dead_zone,
                max_scrolls,
                swipe,
                sleep_after_swipe,
            )
        except RuntimeError:
            return False

        cx, cy = int(entry["location"][0]), int(entry["location"][1])
        if not _tap_screen(device_id, cx, cy):
            return False
        if sleep_after_tap > 0:
            time.sleep(sleep_after_tap)

        _persist_cache_entry(device_id, cache_key, entry)
        return True
    finally:
        release_uiautomator2(device_id, wait_ready=False)


def click_by_match_keywords(
    device_id: str,
    keywords,
    *,
    phone_keywords: Optional[set[str]] = None,
    **click_kwargs,
) -> bool:
    """按顺序尝试多个 keyword，任一匹配并点击成功则返回 True。"""
    phone_set = phone_keywords or set()
    for keyword in keywords:
        text = (keyword or "").strip()
        if not text:
            continue
        match_content: dict[str, Any] = {"keyword": text}
        if text in phone_set:
            match_content["match_phone_digits"] = True
        if click_by_match(device_id, match_content, **click_kwargs):
            return True
    return False


# --- 弹框匹配（首选网络类型等，逻辑对齐 scripts/preferred_network_ui.py）---

DIALOG_CONFIRM_KEYWORDS = ("确定", "确认", "OK", "Ok")
DIALOG_CANCEL_TEXTS = frozenset({"取消", "Cancel"})
DIALOG_SETTLE_BEFORE_CONFIRM = 0.35
DIALOG_SETTLE_AFTER_CONFIRM = 0.45


def pred_5g_auto_row(text: str) -> bool:
    return "5G" in text and ("自动" in text or "自動" in text or "自动选择" in text)


def pred_lte234_auto_row(text: str) -> bool:
    auto = "自动" in text or "自動" in text or "自动选择" in text
    if not auto or "5G" in text:
        return False
    if "2G/3G/4G" in text or "2G / 3G / 4G" in text:
        return True
    if ("4G" in text or "LTE" in text) and ("3G" in text or "WCDMA" in text) and (
        "2G" in text or "GSM" in text
    ):
        return True
    return False


def pred_23g_auto_row(text: str) -> bool:
    auto = "自动" in text or "自動" in text or "自动选择" in text
    if not auto or "5G" in text or "4G" in text or "LTE" in text:
        return False
    if "2G/3G" in text or "2G / 3G" in text:
        return True
    return ("2G" in text or "GSM" in text) and ("3G" in text or "WCDMA" in text)


def pred_3g_only_row(text: str) -> bool:
    t = (text or "").strip()
    if "仅 3G" in t or "仅3G" in t.replace(" ", ""):
        return True
    return t in ("3G only", "Only 3G")


def pred_2g_only_row(text: str) -> bool:
    t = (text or "").strip()
    if "仅 2G" in t or "仅2G" in t.replace(" ", ""):
        return True
    return t in ("2G only", "Only 2G")


def _pred_dialog_confirm_button(text: str) -> bool:
    t = (text or "").strip()
    if not t or t in DIALOG_CANCEL_TEXTS:
        return False
    if t in DIALOG_CONFIRM_KEYWORDS:
        return True
    return t.upper() == "OK"


def _tap_node_center(device_id: str, node: ET.Element) -> bool:
    bounds = node.attrib.get("bounds") or ""
    if not bounds:
        return False
    try:
        x, y = _parse_bounds_center(bounds)
    except ValueError:
        return False
    if not _tap_screen(device_id, x, y):
        return False
    return True


def _resolve_clickable_node(
    el: ET.Element, parent_map: dict[ET.Element, ET.Element]
) -> Optional[ET.Element]:
    tap: Optional[ET.Element] = el
    for _ in range(10):
        if tap is None:
            return None
        if tap.attrib.get("clickable") == "true":
            return tap
        tap = parent_map.get(tap)
    return None


def _xml_has_matching_clickable_row(
    xml_path: Path,
    pred: Callable[[str], bool],
    *,
    screen_h: int,
    top_dead_zone: int,
    bottom_dead_zone: int,
) -> bool:
    if not xml_path.is_file():
        return False
    root = ET.parse(xml_path).getroot()
    parent_map = _build_parent_map(root)
    for el in root.iter("node"):
        label = (el.attrib.get("text") or "") + (el.attrib.get("content-desc") or "")
        if not pred(label):
            continue
        if not _node_reported_displayed(el):
            continue
        tap_node = _resolve_clickable_node(el, parent_map)
        if tap_node is None or not _node_reported_displayed(tap_node):
            continue
        bounds = tap_node.attrib.get("bounds") or ""
        if not bounds:
            continue
        try:
            if _tap_center_in_vertical_dead_zone(
                bounds, screen_h, top_dead_zone, bottom_dead_zone
            ):
                continue
        except ValueError:
            continue
        return True
    return False


def _tap_first_clickable_in_xml(
    device_id: str,
    xml_path: Path,
    pred: Callable[[str], bool],
    *,
    screen_h: int,
    top_dead_zone: int,
    bottom_dead_zone: int,
) -> bool:
    if not xml_path.is_file():
        return False
    root = ET.parse(xml_path).getroot()
    parent_map = _build_parent_map(root)
    for el in root.iter("node"):
        label = (el.attrib.get("text") or "") + (el.attrib.get("content-desc") or "")
        if not pred(label):
            continue
        if not _node_reported_displayed(el):
            continue
        tap_node = _resolve_clickable_node(el, parent_map)
        if tap_node is None or not _node_reported_displayed(tap_node):
            continue
        bounds = tap_node.attrib.get("bounds") or ""
        if not bounds:
            continue
        try:
            if _tap_center_in_vertical_dead_zone(
                bounds, screen_h, top_dead_zone, bottom_dead_zone
            ):
                continue
        except ValueError:
            continue
        return _tap_node_center(device_id, tap_node)
    return False


def dialog_has_matching_row(
    device_id: str,
    row_pred: Callable[[str], bool],
    *,
    max_scrolls: int = 3,
    top_dead_zone: int = DEFAULT_TOP_DEAD_ZONE,
    bottom_dead_zone: int = DEFAULT_BOTTOM_DEAD_ZONE,
    sleep_after_swipe: float = DEFAULT_SLEEP_AFTER_SWIPE,
) -> bool:
    """在当前弹框中检测是否存在可点击的匹配行（不点击）。"""
    if not device_id:
        return False

    _, screen_h = _get_wm_size(device_id)
    swipe = (*DEFAULT_SWIPE[:4], DEFAULT_SWIPE[4])
    device_scroll_count = 0

    if acquire_u2(device_id) is None:
        return False
    try:
        for slide in range(max_scrolls + 1):
            xml_path = dump_current_ui(device_id)
            if xml_path is None:
                return False
            if _xml_has_matching_clickable_row(
                xml_path,
                row_pred,
                screen_h=screen_h,
                top_dead_zone=top_dead_zone,
                bottom_dead_zone=bottom_dead_zone,
            ):
                return True
            if slide >= max_scrolls:
                break
            device_scroll_count = _ensure_device_scroll_index(
                device_id,
                slide + 1,
                device_scroll_count,
                swipe,
                sleep_after_swipe,
            )
        return False
    finally:
        release_uiautomator2(device_id, wait_ready=False)


def click_dialog_by_predicate(
    device_id: str,
    row_pred: Callable[[str], bool],
    *,
    max_scrolls: int = 3,
    top_dead_zone: int = DEFAULT_TOP_DEAD_ZONE,
    bottom_dead_zone: int = DEFAULT_BOTTOM_DEAD_ZONE,
    sleep_after_swipe: float = DEFAULT_SLEEP_AFTER_SWIPE,
) -> bool:
    """在当前弹框中按谓词匹配列表行并点击（可下滑）。"""
    if not device_id:
        return False

    _, screen_h = _get_wm_size(device_id)
    swipe = (*DEFAULT_SWIPE[:4], DEFAULT_SWIPE[4])
    device_scroll_count = 0

    if acquire_u2(device_id) is None:
        return False
    try:
        for slide in range(max_scrolls + 1):
            xml_path = dump_current_ui(device_id)
            if xml_path is None:
                return False
            if _tap_first_clickable_in_xml(
                device_id,
                xml_path,
                row_pred,
                screen_h=screen_h,
                top_dead_zone=top_dead_zone,
                bottom_dead_zone=bottom_dead_zone,
            ):
                return True
            if slide >= max_scrolls:
                break
            device_scroll_count = _ensure_device_scroll_index(
                device_id,
                slide + 1,
                device_scroll_count,
                swipe,
                sleep_after_swipe,
            )
        return False
    finally:
        release_uiautomator2(device_id, wait_ready=False)


def click_dialog_confirm(
    device_id: str,
    *,
    top_dead_zone: int = DEFAULT_TOP_DEAD_ZONE,
    bottom_dead_zone: int = DEFAULT_BOTTOM_DEAD_ZONE,
) -> bool:
    """点击弹框底部「确定/确认」；优先 u2 点 btn_positive，否则解析 dump。"""
    if not device_id:
        return False

    device = acquire_u2(device_id)
    if device is None:
        return False
    try:
        try:
            if click_dialog_positive(device, settle_after=DIALOG_SETTLE_AFTER_CONFIRM):
                return True
        except Exception:
            pass

        xml_path = dump_current_ui(device_id)
        if xml_path is None:
            return False

        root = ET.parse(xml_path).getroot()
        parent_map = _build_parent_map(root)
        for el in root.iter("node"):
            rid = el.attrib.get("resource-id") or ""
            if "btn_positive" not in rid and not rid.endswith("/button1"):
                continue
            tap_node = _resolve_clickable_node(el, parent_map)
            if tap_node is None:
                continue
            if _tap_node_center(device_id, tap_node):
                if DIALOG_SETTLE_AFTER_CONFIRM > 0:
                    time.sleep(DIALOG_SETTLE_AFTER_CONFIRM)
                return True

        _, screen_h = _get_wm_size(device_id)
        if _tap_first_clickable_in_xml(
            device_id,
            xml_path,
            _pred_dialog_confirm_button,
            screen_h=screen_h,
            top_dead_zone=top_dead_zone,
            bottom_dead_zone=bottom_dead_zone,
        ):
            if DIALOG_SETTLE_AFTER_CONFIRM > 0:
                time.sleep(DIALOG_SETTLE_AFTER_CONFIRM)
            return True
        return False
    finally:
        release_uiautomator2(device_id, wait_ready=False)


def select_dialog_row_and_confirm(
    device_id: str,
    row_pred: Callable[[str], bool],
    *,
    max_scrolls: int = 3,
) -> bool:
    """弹框内点选一行后点击确认。"""
    if not click_dialog_by_predicate(device_id, row_pred, max_scrolls=max_scrolls):
        return False
    if DIALOG_SETTLE_BEFORE_CONFIRM > 0:
        time.sleep(DIALOG_SETTLE_BEFORE_CONFIRM)
    return click_dialog_confirm(device_id)
