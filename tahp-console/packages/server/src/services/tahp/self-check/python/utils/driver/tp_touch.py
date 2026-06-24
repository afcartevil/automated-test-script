"""TP 触摸报点检测：通过 adb getevent -ltr 观察 ABS_MT 坐标事件。"""

import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Generator, Optional

GETEVENT_COLLECT_SEC = 6.0
SWIPE_START_DELAY_SEC = 0.6
SCREEN_ON_KEYCODE = "224"
SCREEN_OFF_KEYCODE = "223"
POWER_CYCLE_COUNT = 5
USER_SWIPE_TIMEOUT_SEC = 5.0

_MT_MARKERS = ("ABS_MT_POSITION_X", "ABS_MT_POSITION_Y")
_SYN_MARKER = "EV_SYN"


def _run_adb(device_id: str, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["adb", "-s", device_id, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def screen_on(device_id: str) -> bool:
    return _keyevent(device_id, SCREEN_ON_KEYCODE)


def screen_off(device_id: str) -> bool:
    return _keyevent(device_id, SCREEN_OFF_KEYCODE)


def _keyevent(device_id: str, code: str) -> bool:
    return _run_adb(
        device_id, ["shell", "input", "keyevent", code], timeout=10
    ).returncode == 0


def _stop_getevent(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=1)


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
        _stop_getevent(proc)
        thread.join(timeout=2)


def _touch_ok(output: str, *, require_syn: bool = True) -> tuple[bool, str]:
    text = output or ""
    if not text.strip():
        return False, "getevent 无输出，未检测到触摸事件"
    upper = text.upper()
    missing = [m for m in _MT_MARKERS if m not in text and m not in upper]
    if missing:
        return False, f"缺少触摸坐标事件: {', '.join(missing)}"
    if require_syn and _SYN_MARKER not in text and _SYN_MARKER not in upper:
        return False, "有坐标事件但未检测到 EV_SYN 同步帧"
    return True, "检测到 ABS_MT 坐标与 EV_SYN，TP 报点正常"


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
) -> dict:
    if not (device_id or "").strip():
        return _result(False, "device_id 为空")

    if callable(on_step):
        on_step("启动 getevent -ltr", True)

    with _getevent_lines(device_id) as lines:
        time.sleep(SWIPE_START_DELAY_SEC)
        _keyevent(device_id, SCREEN_ON_KEYCODE)
        time.sleep(0.25)
        swipe_ret = _run_adb(
            device_id,
            ["shell", "input", "swipe", "500", "1600", "500", "800", "250"],
            timeout=15,
        )
        swipe_ok = swipe_ret.returncode == 0
        if callable(on_step):
            on_step("模拟屏幕滑动", swipe_ok)
        if not swipe_ok:
            return _result(False, "模拟屏幕滑动失败")
        if callable(before_parse):
            before_parse()
        time.sleep(GETEVENT_COLLECT_SEC)
        output = "".join(lines)

    _save_log(result_dir, output, "tp_getevent_ltr.log")
    ok, detail = _touch_ok(output)
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

        step(f"请滑动屏幕({int(USER_SWIPE_TIMEOUT_SEC)}s内)", True)
        ok, detail, output = wait_touch_events(device_id)
        _save_log(result_dir, output, f"tp_power_cycle_round{n}_getevent.log")
        if not ok:
            step("检测报点", False)
            return _result(False, f"{tag} {detail}")
        step("检测报点", True)

    return _result(True, f"{cycles} 轮亮灭屏后触摸报点均正常")
