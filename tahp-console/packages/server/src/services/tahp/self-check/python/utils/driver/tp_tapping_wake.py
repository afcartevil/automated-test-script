"""TP 双击亮灭屏：设置开关、灭屏后人工双击、检测亮屏与 C6(KEY_F26) 键值。"""

import re
import time
from typing import Callable, Optional

from utils.driver.tp_touch import _run_adb, _save_log, capture_getevent_until
from utils.driver.tranfacmode_ui import dump, tap_xpath
from utils.tdd.ui_automatic import _unlock_keyguard_after_wake, dump_current_ui

SETTINGS_KEY = "os_action_tapping_wake"
TAPPING_WAKE_ACTIVITY = (
    "com.transsion.microintelligence/com.transsion.microintelligence.TappingWakeActivity"
)
TAPPING_WAKE_SWITCH_XPATH = (
    '//*[@resource-id="com.transsion.microintelligence:id/switch_layout"]'
)
SCREEN_OFF_KEYCODE = "223"

USER_DOUBLE_TAP_WAIT_SEC = 45.0
POLL_DISPLAY_INTERVAL_SEC = 1.5

_C6_PATTERNS = (
    re.compile(r"\b00c6\b", re.I),
    re.compile(r"0001\s+00c6", re.I),
    re.compile(r"KEY_F26", re.I),
)


def get_tapping_wake_setting(device_id: str) -> str:
    result = _run_adb(
        device_id,
        ["shell", "settings", "get", "system", SETTINGS_KEY],
        timeout=15,
    )
    return ((result.stdout or "") + (result.stderr or "")).strip()


def is_tapping_wake_enabled(device_id: str) -> bool:
    return get_tapping_wake_setting(device_id).lower() in ("1", "true")


def open_tapping_wake_settings(device_id: str) -> bool:
    result = _run_adb(
        device_id,
        ["shell", "am", "start", "-n", TAPPING_WAKE_ACTIVITY],
        timeout=20,
    )
    if result.returncode != 0:
        return False
    output = f"{result.stdout or ''}{result.stderr or ''}"
    return "Error" not in output and "Exception" not in output


def click_tapping_wake_toggle(device_id: str) -> bool:
    time.sleep(2.0)
    for _ in range(2):
        xml_path = dump_current_ui(device_id) or dump(device_id)
        if xml_path and tap_xpath(device_id, xml_path, TAPPING_WAKE_SWITCH_XPATH):
            return True
        time.sleep(1.0)
    return False


def screen_off(device_id: str) -> bool:
    result = _run_adb(
        device_id,
        ["shell", "input", "keyevent", SCREEN_OFF_KEYCODE],
        timeout=10,
    )
    return result.returncode == 0


def go_home(device_id: str) -> bool:
    """亮屏后上滑解锁并发送 Home 键回桌面。"""
    _unlock_keyguard_after_wake(device_id)
    result = _run_adb(device_id, ["shell", "input", "keyevent", "3"], timeout=10)
    return result.returncode == 0


def get_screen_state(device_id: str) -> str:
    result = _run_adb(device_id, ["shell", "dumpsys", "display"], timeout=20)
    text = (result.stdout or "") + (result.stderr or "")
    if re.search(r"mScreenState\s*=\s*ON\b", text, re.I):
        return "ON"
    if re.search(r"mScreenState\s*=\s*OFF\b", text, re.I):
        return "OFF"
    return "UNKNOWN"


def has_c6_key_in_getevent(output: str) -> bool:
    return any(p.search(output or "") for p in _C6_PATTERNS)


def verify_wake_after_double_tap(
    device_id: str,
    *,
    result_dir: Optional[str] = None,
    wait_sec: float = USER_DOUBLE_TAP_WAIT_SEC,
) -> dict:
    """监测 getevent 直至亮屏，返回亮屏与 C6 键值检测结果（不含解锁回桌面）。"""
    getevent_log = capture_getevent_until(
        device_id,
        wait_sec,
        poll_fn=lambda: get_screen_state(device_id) == "ON",
        poll_interval=POLL_DISPLAY_INTERVAL_SEC,
    )
    _save_log(result_dir, getevent_log, "tp_tapping_wake_getevent_ltr.log")

    screen_state = get_screen_state(device_id)
    screen_ok = screen_state == "ON"
    c6_ok = has_c6_key_in_getevent(getevent_log)
    return {
        "screen_ok": screen_ok,
        "c6_ok": c6_ok,
        "screen_state": screen_state,
    }


def _build_wake_test_result(
    *,
    screen_ok: bool,
    c6_ok: bool,
    screen_state: str,
) -> dict:
    if screen_ok and c6_ok:
        return {
            "status": "pass",
            "message": "屏幕已亮起且 getevent 检测到 C6(KEY_F26) 键值",
        }
    parts = []
    if not screen_ok:
        parts.append(f"屏幕未亮起(mScreenState={screen_state})")
    if not c6_ok:
        parts.append("getevent 未检测到 C6/KEY_F26 键值")
    return {"status": "fail", "message": "；".join(parts)}


def run_tp_tapping_wake_test(
    device_id: str,
    *,
    result_dir: Optional[str] = None,
    on_step: Optional[Callable[[str, bool], None]] = None,
    before_double_tap: Optional[Callable[[], None]] = None,
) -> dict:
    if not (device_id or "").strip():
        return {"status": "fail", "message": "device_id 为空"}

    def step(label: str, ok: bool) -> None:
        if callable(on_step):
            on_step(label, ok)

    step("检查双击唤醒设置", True)
    setting_val = get_tapping_wake_setting(device_id)

    if is_tapping_wake_enabled(device_id):
        step(f"双击唤醒已开启(settings={setting_val})，跳过设置", True)
    else:
        step(f"双击唤醒未开启(settings={setting_val})", True)
        step("进入双击唤醒设置页", True)
        if not open_tapping_wake_settings(device_id):
            step("启动 TappingWakeActivity", False)
            return {"status": "fail", "message": "无法打开双击唤醒设置界面"}
        step("启动 TappingWakeActivity", True)

        if not click_tapping_wake_toggle(device_id):
            step("点击双击唤醒开关", False)
            return {
                "status": "fail",
                "message": "未找到或无法点击双击唤醒开关(switch_layout)",
            }
        step("点击双击唤醒开关", True)
        time.sleep(0.8)

        if not is_tapping_wake_enabled(device_id):
            step("确认双击唤醒已开启", False)
            return {
                "status": "fail",
                "message": f"开启后 settings get 仍为: {get_tapping_wake_setting(device_id)!r}",
            }
        step("确认双击唤醒已开启", True)

    if not screen_off(device_id):
        step("灭屏(keyevent 223)", False)
        return {"status": "fail", "message": "发送灭屏按键失败"}
    step("灭屏(keyevent 223)", True)
    time.sleep(1.0)

    off_state = get_screen_state(device_id)
    if off_state == "ON":
        step(f"灭屏后屏幕状态({off_state})", False)
        return {"status": "fail", "message": "灭屏后 mScreenState 仍为 ON"}
    step(f"灭屏后屏幕状态({off_state})", True)

    if callable(before_double_tap):
        before_double_tap()
    else:
        step(f"请在 {int(USER_DOUBLE_TAP_WAIT_SEC)} 秒内双击屏幕亮屏", True)

    step("启动 getevent -ltr 并监测亮屏", True)
    wake_result = verify_wake_after_double_tap(device_id, result_dir=result_dir)
    screen_ok = bool(wake_result.get("screen_ok"))
    c6_ok = bool(wake_result.get("c6_ok"))
    screen_state = wake_result.get("screen_state") or "UNKNOWN"

    step("检测 C6(KEY_F26) 键值", c6_ok)
    step("检测到亮屏", screen_ok)

    home_ok = go_home(device_id) if screen_ok else False
    step("解锁并回到桌面", home_ok)
    result = _build_wake_test_result(
        screen_ok=screen_ok,
        c6_ok=c6_ok,
        screen_state=screen_state,
    )
    return result
