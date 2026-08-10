from __future__ import annotations

import json
import signal
import subprocess
import sys
import time
from pathlib import Path


def _device_serial(device_info: dict) -> str:
    dut = device_info.get("DUT") if isinstance(device_info, dict) else None
    if isinstance(dut, list) and dut:
        serial = dut[0].get("device_id") or dut[0].get("deviceId")
        if serial:
            return str(serial)
    if isinstance(device_info, dict):
        serial = device_info.get("deviceId") or device_info.get("device_id")
        if serial:
            return str(serial)
    raise ValueError("缺少测试机设备序列号")


def _summarize(runner: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(runner), "summarize-xlsx"],
        cwd=str(runner.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    stdout = (result.stdout or "").strip()
    if stdout:
        try:
            return json.loads(stdout.splitlines()[-1])
        except json.JSONDecodeError:
            pass
    return {"ok": False, "message": stdout or (result.stderr or "").strip() or "无法汇总报告"}


def run_scene(scene: str, device_info=None, step_update=None, **_context):
    info = device_info or {}
    serial = _device_serial(info)
    label = (scene or "").strip() or "场景功耗测量"

    runner = (
        Path(__file__).resolve().parents[3]
        / "tools"
        / "tpower_auto"
        / "run_power_env.py"
    )
    if not runner.is_file():
        return {
            "status": "fail",
            "message": f"功耗环境脚本不存在: {runner}",
            "full_automation": True,
        }

    steps: list[str] = []
    stopped = False

    def add_step(text: str) -> None:
        steps.append(text)
        if step_update:
            step_update("\n".join(steps))

    def request_stop(*_args) -> None:
        nonlocal stopped
        stopped = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, request_stop)
        except (AttributeError, ValueError, OSError):
            pass

    add_step(f"准备启动场景功耗测量（{label}），设备: {serial}")
    subprocess.run(
        [sys.executable, str(runner), "stop", "-s", serial],
        cwd=str(runner.parent),
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
        errors="replace",
    )

    log_path = runner.parent / "log" / "power_env_daemon.log"
    log_offset = log_path.stat().st_size if log_path.is_file() else 0

    add_step(f"TPower 子线程启动中（{label}）…")
    proc = subprocess.Popen(
        [sys.executable, str(runner), "run", "-s", serial, "--scene", label],
        cwd=str(runner.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def tail_log() -> None:
        nonlocal log_offset
        if not log_path.is_file():
            return
        size = log_path.stat().st_size
        if size <= log_offset:
            return
        with log_path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(log_offset)
            chunk = handle.read()
            log_offset = size
        for line in chunk.splitlines():
            text = line.strip()
            if text:
                add_step(text)

    while proc.poll() is None and not stopped:
        tail_log()
        time.sleep(2)

    if stopped and proc.poll() is None:
        add_step("收到终止请求，正在停止功耗环境…")
        subprocess.run(
            [sys.executable, str(runner), "stop", "-s", serial],
            cwd=str(runner.parent),
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
            errors="replace",
        )
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)

    tail_log()
    exit_code = proc.returncode if proc.returncode is not None else proc.wait(timeout=5)
    summary = _summarize(runner)
    report_path = summary.get("path") or ""
    if report_path:
        add_step(f"报告: {report_path}")

    total = int(summary.get("total") or 0)
    failed = int(summary.get("failed") or 0)
    message = str(summary.get("message") or "")

    if stopped:
        add_step("测试已手动终止")
        if total > 0:
            status = "pass" if failed == 0 else "fail"
            add_step(f"已执行项汇总: {message}-{'成功' if status == 'pass' else '失败'}")
            return {
                "status": status,
                "message": f"测试已终止；{label}；{message}",
                "full_automation": True,
            }
        return {
            "status": "fail",
            "message": message or f"{label} 已终止，暂无报告数据",
            "full_automation": True,
        }

    if exit_code not in (0, None) and total == 0:
        add_step(f"功耗环境异常退出(码 {exit_code})-失败")
        return {
            "status": "fail",
            "message": message or f"{label} 功耗环境异常退出，码 {exit_code}",
            "full_automation": True,
        }

    if total == 0:
        add_step("功耗环境结束，暂无测试数据-失败")
        return {
            "status": "fail",
            "message": message or f"{label} 未产生报告数据",
            "full_automation": True,
        }

    if failed == 0:
        add_step(f"{label} {message}-成功")
        return {
            "status": "pass",
            "message": f"{label}；{message}",
            "full_automation": True,
        }

    add_step(f"{label} {message}-失败")
    return {
        "status": "fail",
        "message": f"{label}；{message}",
        "full_automation": True,
    }
