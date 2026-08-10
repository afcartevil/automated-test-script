from __future__ import annotations

import signal
import subprocess
import sys
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


def _stop_proc(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            timeout=30,
        )
        return
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def run(device_info=None, step_update=None, **_context):
    info = device_info or {}
    try:
        serial = _device_serial(info)
    except ValueError as exc:
        return {"status": "fail", "message": str(exc), "full_automation": True}

    tool_root = (
        Path(__file__).resolve().parents[3] / "tools" / "tpytest_dzppt_therm"
    )
    launcher = (
        tool_root / "launchers" / "dzppt" / "therm" / "start_therm_cli_python.py"
    )
    if not launcher.is_file():
        return {
            "status": "fail",
            "message": f"温升方案脚本不存在: {launcher}",
            "full_automation": True,
        }

    steps: list[str] = []
    stopped = False

    def add_step(text: str) -> None:
        line = (text or "").strip()
        if not line:
            return
        steps.append(line)
        if step_update:
            step_update("\n".join(steps[-80:]))

    def request_stop(*_args) -> None:
        nonlocal stopped
        stopped = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, request_stop)
        except (AttributeError, ValueError, OSError):
            pass

    add_step(f"准备启动温升方案自检，设备: {serial}")
    add_step(f"启动 tpytest_dzppt_therm: {launcher.name}")

    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", str(launcher), "--device-id", serial],
            cwd=str(tool_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except OSError as exc:
        add_step(f"启动失败: {exc}")
        return {"status": "fail", "message": str(exc), "full_automation": True}

    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            if stopped:
                add_step("收到终止请求，正在停止温升方案测试…")
                _stop_proc(proc)
                break
            add_step(raw)
        if not stopped:
            proc.wait()
    except Exception as exc:
        _stop_proc(proc)
        add_step(f"执行异常: {exc}")
        return {"status": "fail", "message": str(exc), "full_automation": True}

    exit_code = proc.returncode if proc.returncode is not None else -1
    if stopped:
        add_step("测试已手动终止")
        return {
            "status": "fail",
            "message": "测试已终止",
            "full_automation": True,
        }

    if exit_code == 0:
        add_step("温升方案自检通过")
        return {
            "status": "pass",
            "message": "tpytest_dzppt_therm 执行完成",
            "full_automation": True,
        }

    message = f"tpytest_dzppt_therm 异常退出，码 {exit_code}"
    add_step(f"{message}-失败")
    return {"status": "fail", "message": message, "full_automation": True}
