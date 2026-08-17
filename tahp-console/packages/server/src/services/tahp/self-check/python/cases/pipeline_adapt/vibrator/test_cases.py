"""pipeline_adapt / 马达用例列表（由 case1 顺序编排执行）。"""

from __future__ import annotations

import re
import time
from typing import Any

from _common import (
    StepFn,
    adb_shell,
    emit,
    open_settings,
    swipe_back_gesture,
    try_adb_root,
)
from utils.tdd.ui_automatic import ensure_screen_on_and_unlocked

_LINEAR_LEDS = frozenset({"vibrator_single", "vibrator_l", "vibrator_r"})
_IRQ_LINE_RE = re.compile(r"^\s*\d+:\s*(.*)$")
_STATUS_SUFFIX = {
    "pass": "成功",
    "fail": "失败",
    "skip": "跳过",
}


def _item(name: str, status: str, message: str) -> dict[str, Any]:
    return {"name": name, "status": status, "message": message}


def _led_names(serial: str) -> set[str]:
    out = adb_shell(serial, "ls /sys/class/leds 2>/dev/null")
    return {name.strip() for name in out.split() if name.strip()}


def haptic_interrupt_text(serial: str) -> str:
    raw = adb_shell(serial, "cat /proc/interrupts")
    return "\n".join(ln for ln in raw.splitlines() if "haptic" in ln.lower())


def parse_haptic_irq_count(text: str) -> int | None:
    """汇总 /proc/interrupts 中含 haptic 行的各 CPU 计数。"""
    total = 0
    found = False
    for raw in (text or "").splitlines():
        line = raw.strip()
        if "haptic" not in line.lower():
            continue
        found = True
        rest = _IRQ_LINE_RE.sub(r"\1", line)
        nums: list[int] = []
        for token in rest.split():
            if token.isdigit():
                nums.append(int(token))
            else:
                break
        total += sum(nums)
    return total if found else None


def detect_motor_kind(serial: str) -> str:
    """linear / rotor / unknown。有 haptic 中断或线性 LED 视为线性；仅 vibrator LED 视为转子。"""
    has_linear_irq = bool(haptic_interrupt_text(serial).strip())
    leds = _led_names(serial)
    has_linear_led = bool(leds & _LINEAR_LEDS)
    has_rotor_led = "vibrator" in leds and not has_linear_led
    if has_linear_irq or has_linear_led:
        return "unknown" if has_rotor_led else "linear"
    if has_rotor_led:
        return "rotor"
    return "unknown"


def _enter_settings(serial: str, *, steps: list[str], step_update: StepFn | None) -> tuple[bool, str]:
    emit(step_update, steps, "[设置] 亮屏解锁")
    if not ensure_screen_on_and_unlocked(serial):
        emit(step_update, steps, "[设置] 亮屏解锁-失败")
        return False, "亮屏解锁失败"
    emit(step_update, steps, "[设置] 亮屏解锁-成功")
    emit(step_update, steps, "[设置] 进入设置应用")
    if not open_settings(serial):
        emit(step_update, steps, "[设置] 进入设置应用-失败")
        return False, "进入设置应用失败"
    time.sleep(1.5)
    nav = adb_shell(serial, "settings get secure navigation_mode")
    emit(step_update, steps, f"[设置] navigation_mode={nav or '<空>'}（2=全面屏手势）")
    emit(step_update, steps, "[设置] 进入设置应用-成功")
    return True, ""


def _swipe_back(serial: str, *, from_right: bool, steps: list[str], step_update: StepFn | None) -> bool:
    side = "右侧" if from_right else "左侧"
    emit(step_update, steps, f"[返回滑动] 从屏幕{side}边缘向内滑动")
    ok = swipe_back_gesture(serial, from_right=from_right)
    emit(step_update, steps, f"[返回滑动]-{'成功' if ok else '失败'}（{side}）")
    if ok:
        time.sleep(0.9)
    return ok


def _dmesg_clear(serial: str) -> tuple[bool, str]:
    out = adb_shell(serial, "dmesg -C 2>&1")
    low = (out or "").lower()
    if "permission denied" in low or "operation not permitted" in low:
        return False, out or "dmesg -C permission denied"
    if "unknown option" in low or "invalid option" in low:
        out = adb_shell(serial, "dmesg -c >/dev/null 2>&1")
        low = (out or "").lower()
        if "permission denied" in low or "operation not permitted" in low:
            return False, out or "dmesg -c permission denied"
    return True, out


def _dmesg_read(serial: str) -> str:
    return adb_shell(serial, "dmesg 2>/dev/null", timeout=20)


def _has_vibr_enable_disable(text: str) -> bool:
    low = (text or "").lower()
    return "vibr enable" in low and "vibr disable" in low


def test_rotor_vibrate(
    serial: str,
    *,
    steps: list[str],
    step_update: StepFn | None = None,
    motor_kind: str = "unknown",
    **_,
) -> dict[str, Any]:
    """
    转子马达振动功能检查
    测试步骤:
    1. 进入设置应用
    2. adb dmesg -C 清除日志
    3. 执行返回滑动操作
    4. 检测内核日志关键字
    预期结果: 有 vibr enable 和 vibr disable 输出
    """
    name = "转子马达振动功能检查"
    if motor_kind == "linear":
        emit(step_update, steps, f"[{name}] 当前为线性马达，跳过")
        return _item(name, "skip", "当前设备为线性马达，跳过转子检查")

    emit(step_update, steps, f"[{name}] 尝试 adb root（dmesg -C 需要）")
    root_ok, root_msg = try_adb_root(serial)
    emit(step_update, steps, f"[{name}] adb root: {root_msg or ('ok' if root_ok else '失败')}")

    for from_right in (False, True):
        ok, err = _enter_settings(serial, steps=steps, step_update=step_update)
        if not ok:
            return _item(name, "fail", err)
        emit(step_update, steps, "[转子] adb dmesg -C 清除日志")
        cleared, clear_msg = _dmesg_clear(serial)
        if not cleared:
            emit(step_update, steps, f"[转子] 清除日志失败: {clear_msg}")
            return _item(name, "fail", f"dmesg -C 失败: {clear_msg}")
        emit(step_update, steps, "[转子] 清除日志-成功")
        if not _swipe_back(serial, from_right=from_right, steps=steps, step_update=step_update):
            return _item(name, "fail", "返回滑动失败")
        log = _dmesg_read(serial)
        preview = (log or "")[-800:].replace("\n", " | ")
        emit(step_update, steps, f"[转子] dmesg 摘要: {preview or '<空>'}")
        if _has_vibr_enable_disable(log):
            emit(step_update, steps, f"[{name}]-成功")
            return _item(name, "pass", "dmesg 含 vibr enable 与 vibr disable")
        emit(step_update, steps, "[转子] 未同时找到 vibr enable/disable，尝试另一侧滑动")

    emit(step_update, steps, f"[{name}]-失败")
    return _item(name, "fail", "内核日志未同时出现 vibr enable 和 vibr disable")


def test_linear_vibrate(
    serial: str,
    *,
    steps: list[str],
    step_update: StepFn | None = None,
    motor_kind: str = "unknown",
    **_,
) -> dict[str, Any]:
    """
    线性振动功能检查
    测试步骤:
    1. 进入设置应用
    2. adb shell cat /proc/interrupts | grep haptic 记录当前中断
    3. 执行返回滑动操作
    4. 再次读取中断并与步骤 2 对比
    预期结果: 马达中断触发数增加
    """
    name = "线性振动功能检查"
    if motor_kind == "rotor":
        emit(step_update, steps, f"[{name}] 当前为转子马达，跳过")
        return _item(name, "skip", "当前设备为转子马达，跳过线性检查")

    for from_right in (False, True):
        ok, err = _enter_settings(serial, steps=steps, step_update=step_update)
        if not ok:
            return _item(name, "fail", err)
        emit(step_update, steps, "[线性] 读取 /proc/interrupts | grep haptic")
        before_text = haptic_interrupt_text(serial)
        before = parse_haptic_irq_count(before_text)
        emit(step_update, steps, f"[线性] 滑动前: count={before} raw={before_text or '<空>'}")
        if before is None:
            emit(step_update, steps, f"[{name}]-失败")
            return _item(name, "fail", "未找到 haptic 中断行")
        if not _swipe_back(serial, from_right=from_right, steps=steps, step_update=step_update):
            return _item(name, "fail", "返回滑动失败")
        after_text = haptic_interrupt_text(serial)
        after = parse_haptic_irq_count(after_text)
        emit(step_update, steps, f"[线性] 滑动后: count={after} raw={after_text or '<空>'}")
        if after is not None and after > before:
            emit(step_update, steps, f"[{name}]-成功")
            return _item(name, "pass", f"haptic 中断 {before} → {after}")
        emit(step_update, steps, "[线性] 中断未增加，尝试另一侧滑动")

    emit(step_update, steps, f"[{name}]-失败")
    return _item(name, "fail", "返回滑动后 haptic 中断计数未增加")


MOTOR_TEST_CASES = (
    test_rotor_vibrate,
    test_linear_vibrate,
)


def run_all_test_cases(
    serial: str,
    *,
    step_update: StepFn | None = None,
    result_dir=None,
) -> tuple[list[dict[str, Any]], list[str]]:
    steps = [f"设备: {serial}", "开始执行 马达流水线适配检查"]
    if callable(step_update):
        step_update("\n".join(steps))

    kind = detect_motor_kind(serial)
    kind_label = {"linear": "线性", "rotor": "转子"}.get(kind, "未知")
    emit(step_update, steps, f"识别马达类型: {kind_label} ({kind})")

    results: list[dict[str, Any]] = []
    for fn in MOTOR_TEST_CASES:
        result = fn(
            serial,
            steps=steps,
            step_update=step_update,
            result_dir=result_dir,
            motor_kind=kind,
        )
        results.append(result)
        suffix = _STATUS_SUFFIX.get(str(result.get("status")), str(result.get("status")))
        emit(step_update, steps, f"{result.get('name')}-{suffix}")

    if kind == "unknown":
        passed = [r for r in results if r.get("status") == "pass"]
        failed = [r for r in results if r.get("status") == "fail"]
        if passed and failed:
            for item in failed:
                item["status"] = "skip"
                item["message"] = f"未识别为该类型，已跳过（{item.get('message')}）"
                emit(step_update, steps, f"{item.get('name')}-跳过")

    return results, steps
