from __future__ import annotations

import subprocess
import sys
from pathlib import Path


DEFAULT_DURATION = "7d"


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


def run(device_info=None, step_update=None, **_context):
    info = device_info or {}
    duration = str(info.get("monkeyDuration") or DEFAULT_DURATION).strip() or DEFAULT_DURATION
    serial = _device_serial(info)

    script = (
        Path(__file__).resolve().parents[3]
        / "tools"
        / "monkey_usd"
        / "monkey_test.py"
    )
    if not script.is_file():
        return {
            "status": "fail",
            "message": f"Monkey 脚本不存在: {script}",
            "full_automation": True,
        }

    steps: list[str] = []

    def add_step(text: str) -> None:
        steps.append(text)
        if step_update:
            step_update("\n".join(steps))

    add_step(f"准备启动 Monkey 测试，设备: {serial}，时长: {duration}")
    cmd = [
        sys.executable,
        str(script),
        "-s",
        serial,
        "start",
        "-d",
        duration,
        "--save-log",
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(script.parent),
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "fail",
            "message": "Monkey 启动超时",
            "full_automation": True,
        }

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.returncode != 0:
        add_step("Monkey 启动失败-失败")
        return {
            "status": "fail",
            "message": stderr or stdout or f"退出码: {result.returncode}",
            "full_automation": True,
        }

    add_step("Monkey 已后台启动-成功")
    return {
        "status": "pass",
        "message": stdout or f"Monkey 测试已启动，时长 {duration}",
        "full_automation": True,
    }
