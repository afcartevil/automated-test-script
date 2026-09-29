from __future__ import annotations

import importlib.util
from pathlib import Path

DEFAULT_REPEAT_COUNT = 1


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


def _load_runner():
    script = Path(__file__).resolve().parent / "bst_runner.py"
    if not script.is_file():
        raise FileNotFoundError(f"bitflip runner 不存在: {script}")
    spec = importlib.util.spec_from_file_location("bst_runner", script)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 bitflip runner: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(device_info=None, step_update=None, **_context):
    info = device_info or {}
    try:
        serial = _device_serial(info)
    except ValueError as exc:
        return {"status": "fail", "message": str(exc), "full_automation": True}

    try:
        runner = _load_runner()
    except Exception as exc:
        return {"status": "fail", "message": str(exc), "full_automation": True}

    repeat_count = runner.normalize_repeat_count(
        info.get("bitflipRepeatCount", DEFAULT_REPEAT_COUNT)
    )
    result_dir = str(info.get("resultDir") or "").strip() or None
    return runner.run_bitflip_test(
        serial=serial,
        repeat_count=repeat_count,
        on_step=step_update,
        result_dir=result_dir,
    )
