from __future__ import annotations

import subprocess
import sys
from pathlib import Path

MODE = "shutdown"
MODE_LABEL = "关机"
DEFAULT_TOOL_DIR = r"D:\rd_tool\alarm_v2.1.029"
DEFAULT_LOOPS = 1000
DEFAULT_POWERON_TIME = 120
DEFAULT_SHUTDOWN_TIME = 300


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
    alarm = info.get("alarm") if isinstance(info.get("alarm"), dict) else {}
    tool_dir = str(alarm.get("tool_dir") or DEFAULT_TOOL_DIR).strip() or DEFAULT_TOOL_DIR
    params = alarm.get(MODE) if isinstance(alarm.get(MODE), dict) else {}
    loops = int(params.get("loops") or DEFAULT_LOOPS)
    poweron_time = int(params.get("poweronTime") or DEFAULT_POWERON_TIME)
    shutdown_time = int(params.get("shutdownTime") or DEFAULT_SHUTDOWN_TIME)
    serial = _device_serial(info)

    script = (
        Path(__file__).resolve().parents[3]
        / "tools"
        / "alarm"
        / "alarm_tool.py"
    )
    if not script.is_file():
        return {
            "status": "fail",
            "message": f"alarm 工具脚本不存在: {script}",
            "full_automation": True,
        }

    steps: list[str] = []

    def add_step(text: str) -> None:
        steps.append(text)
        if step_update:
            step_update("\n".join(steps))

    add_step(
        f"准备启动{MODE_LABEL}压测，设备: {serial}，循环: {loops} 次，"
        f"开机等待: {poweron_time}s，关机时长: {shutdown_time}s"
    )
    cmd = [
        sys.executable,
        str(script),
        "-s",
        serial,
        "start",
        "--mode",
        MODE,
        "--tool-dir",
        tool_dir,
        "--loops",
        str(loops),
        "--poweron-time",
        str(poweron_time),
        "--shutdown-time",
        str(shutdown_time),
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(script.parent),
            capture_output=True,
            text=True,
            timeout=600,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "fail",
            "message": f"{MODE_LABEL}启动超时",
            "full_automation": True,
        }

    output = "\n".join(
        x for x in [(result.stdout or "").strip(), (result.stderr or "").strip()] if x
    )
    if result.returncode != 0:
        add_step(f"{MODE_LABEL}启动失败-失败")
        return {
            "status": "fail",
            "message": output or f"退出码: {result.returncode}",
            "full_automation": True,
        }

    add_step(f"{MODE_LABEL}已后台启动-成功")
    return {
        "status": "pass",
        "message": (
            f"{MODE_LABEL}压测已启动（loops={loops}, poweronTime={poweron_time}s, "
            f"shutdownTime={shutdown_time}s），设备将自治运行，可断开 USB；"
            "停止请在设备详情点「结束测试」"
        ),
        "full_automation": True,
    }
