"""TP 触摸报点检测：通过 adb getevent -ltr 观察 ABS_MT 坐标事件。"""

import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Generator, Optional

GETEVENT_COLLECT_SEC = 15.0
SCREEN_ON_KEYCODE = "224"
SCREEN_OFF_KEYCODE = "223"
POWER_CYCLE_COUNT = 5
USER_SWIPE_TIMEOUT_SEC = 12.0

# 兼容不同内核/驱动：带 label、仅 hex、单点坐标
_MT_X_MARKERS = (
    "ABS_MT_POSITION_X",
    "MT_POSITION_X",
    "ABS_X",
    "0035",
    "0035 ",
)
_MT_Y_MARKERS = (
    "ABS_MT_POSITION_Y",
    "MT_POSITION_Y",
    "ABS_Y",
    "0036",
    "0036 ",
)
_SYN_MARKERS = ("EV_SYN", "SYN_REPORT", "SYN_MT_REPORT")


def _run_adb(device_id: str, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["adb", "-s", device_id, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def go_home(device_id: str) -> bool:
    """返回桌面；防误触场景连按两次 Home。"""
    for _ in range(2):
        if _run_adb(device_id, ["shell", "input", "keyevent", "3"], timeout=10).returncode != 0:
            return False
        time.sleep(0.35)
    return True


def screen_on(device_id: str) -> bool:
    return _keyevent(device_id, SCREEN_ON_KEYCODE)


def screen_off(device_id: str) -> bool:
    return _keyevent(device_id, SCREEN_OFF_KEYCODE)


def _keyevent(device_id: str, code: str) -> bool:
    return _run_adb(
        device_id, ["shell", "input", "keyevent", code], timeout=10
    ).returncode == 0


def _stop_getevent(proc: subprocess.Popen[str], device_id: str = "") -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
    if device_id and proc.poll() is None:
        _run_adb(device_id, ["shell", "pkill", "-f", "getevent"], timeout=5)


@contextmanager
def _getevent_lines(device_id: str) -> Generator[list[str], None, None]:
    proc = subprocess.Popen(
        ["adb", "-s", device_id, "shell", "getevent", "-ltr"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: list[str] = []
    stop = threading.Event()

    def _reader() -> None:
        if proc.stdout is None:
            return
        try:
            for line in iter(proc.stdout.readline, ""):
                if stop.is_set():
                    break
                lines.append(line)
        except (OSError, ValueError):
            pass

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    try:
        yield lines
    finally:
        stop.set()
        _stop_getevent(proc, device_id)
        thread.join(timeout=2)


def _has_any_marker(text: str, markers: tuple[str, ...]) -> bool:
    upper = text.upper()
    for marker in markers:
        if marker in text or marker.upper() in upper:
            return True
    return False


def _touch_ok(output: str, *, require_syn: bool = True) -> tuple[bool, str]:
    text = output or ""
    if not text.strip():
        return False, "getevent 无输出，未检测到触摸事件"
    has_x = _has_any_marker(text, _MT_X_MARKERS)
    has_y = _has_any_marker(text, _MT_Y_MARKERS)
    if not has_x or not has_y:
        missing = []
        if not has_x:
            missing.append("X 坐标")
        if not has_y:
            missing.append("Y 坐标")
        return False, f"缺少触摸坐标事件: {', '.join(missing)}"
    if require_syn and not _has_any_marker(text, _SYN_MARKERS):
        return False, "有坐标事件但未检测到 SYN 同步帧"
    return True, "检测到触摸坐标与 SYN，TP 报点正常"


def _save_log(result_dir: Optional[str], output: str, filename: str) -> None:
    if not result_dir or not output.strip():
        return
    try:
        path = Path(result_dir) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8")
    except OSError:
        pass


def _result(ok: bool, message: str) -> dict:
    return {"status": "pass" if ok else "fail", "message": message}


def capture_getevent_until(
    device_id: str,
    wait_sec: float,
    poll_fn: Callable[[], bool],
    poll_interval: float = 1.5,
) -> str:
    with _getevent_lines(device_id) as lines:
        deadline = time.time() + wait_sec
        while time.time() < deadline:
            if poll_fn():
                break
            time.sleep(poll_interval)
        return "".join(lines)


def wait_touch_events(
    device_id: str, timeout_sec: float = USER_SWIPE_TIMEOUT_SEC
) -> tuple[bool, str, str]:
    with _getevent_lines(device_id) as lines:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            if _touch_ok("".join(lines), require_syn=False)[0]:
                out = "".join(lines)
                return True, _touch_ok(out)[1], out
            time.sleep(0.15)
        out = "".join(lines)
    return False, f"{int(timeout_sec)} 秒内未检测到触摸报点", out


def check_tp_touch_reporting(
    device_id: str,
    *,
    result_dir: Optional[str] = None,
    on_step: Optional[Callable[[str, bool], None]] = None,
    before_parse: Optional[Callable[[], None]] = None,
    collect_sec: float = GETEVENT_COLLECT_SEC,
) -> dict:
    if not (device_id or "").strip():
        return _result(False, "device_id 为空")

    if callable(before_parse):
        before_parse()

    if not _keyevent(device_id, SCREEN_ON_KEYCODE):
        return _result(False, "亮屏失败")

    wait_sec = max(float(collect_sec), 3.0)
    if callable(on_step):
        on_step("启动 getevent -ltr", True)
        on_step(f"等待手动触摸报点({int(wait_sec)}s)", True)

    ok, detail, output = wait_touch_events(device_id, timeout_sec=wait_sec)
    _save_log(result_dir, output, "tp_getevent_ltr.log")
    if callable(on_step):
        on_step("解析触摸事件", ok)
    return _result(ok, detail)


def check_tp_touch_after_power_cycles(
    device_id: str,
    *,
    cycles: int = POWER_CYCLE_COUNT,
    result_dir: Optional[str] = None,
    on_step: Optional[Callable[[str, bool], None]] = None,
    before_cycles: Optional[Callable[[], None]] = None,
) -> dict:
    if not (device_id or "").strip():
        return _result(False, "device_id 为空")

    if callable(before_cycles):
        before_cycles()

    for n in range(1, cycles + 1):
        tag = f"第{n}/{cycles}轮"

        def step(label: str, ok: bool) -> None:
            if callable(on_step):
                on_step(f"{tag} {label}", ok)

        step("灭屏(keyevent 223)", True)
        if not screen_off(device_id):
            return _result(False, f"{tag} 灭屏失败")
        time.sleep(0.5)

        step("亮屏(keyevent 224)", True)
        if not screen_on(device_id):
            return _result(False, f"{tag} 亮屏失败")
        time.sleep(0.5)

        step(f"请手动触摸屏幕({int(USER_SWIPE_TIMEOUT_SEC)}s内)", True)
        ok, detail, output = wait_touch_events(device_id)
        _save_log(result_dir, output, f"tp_power_cycle_round{n}_getevent.log")
        if not ok:
            step("检测报点", False)
            return _result(False, f"{tag} {detail}")
        step("检测报点", True)

    return _result(True, f"{cycles} 轮亮灭屏后触摸报点均正常")
