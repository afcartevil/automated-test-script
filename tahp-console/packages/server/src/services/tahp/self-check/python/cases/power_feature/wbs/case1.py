from __future__ import annotations

import importlib.util
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


def _load_checker_class():
    script = (
        Path(__file__).resolve().parents[3]
        / "tools"
        / "wbs_checker"
        / "wbs_checker.py"
    )
    if not script.is_file():
        raise FileNotFoundError(f"WBS checker 不存在: {script}")
    spec = importlib.util.spec_from_file_location("wbs_checker_tool", script)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 WBS checker: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PowerChecker


def run(device_info=None, step_update=None, **_context):
    info = device_info or {}
    try:
        serial = _device_serial(info)
    except ValueError as exc:
        return {"status": "fail", "message": str(exc), "full_automation": True}

    steps: list[str] = []

    def add_step(text: str) -> None:
        steps.append(text)
        if step_update:
            step_update("\n".join(steps))

    try:
        PowerChecker = _load_checker_class()
    except Exception as exc:
        add_step(f"加载 WBS checker 失败: {exc}")
        return {"status": "fail", "message": str(exc), "full_automation": True}

    add_step(f"准备执行功耗特性自检，设备: {serial}")
    checker = PowerChecker(serial=serial, on_step=add_step)
    result = checker.run_all()

    if result.get("error") and not result.get("items"):
        add_step(f"设备检查失败: {result['error']}")
        return {
            "status": "fail",
            "message": str(result["error"]),
            "full_automation": True,
        }

    total = int(result.get("total") or 0)
    passed = int(result.get("passed") or 0)
    failed = int(result.get("failed") or 0)
    failed_items = [
        f"{item.get('name')}: {item.get('info')}"
        for item in (result.get("items") or [])
        if str(item.get("status", "")).lower() != "pass"
    ]

    summary = f"{passed} 通过 / {failed} 失败 / 共 {total} 项"
    if failed == 0 and total > 0:
        add_step(f"功耗特性自检通过 — {summary}")
        return {
            "status": "pass",
            "message": summary,
            "full_automation": True,
        }

    detail = "; ".join(failed_items[:8])
    if len(failed_items) > 8:
        detail += f" …等共 {len(failed_items)} 项失败"
    message = f"{summary}" + (f"；失败项: {detail}" if detail else "")
    add_step(f"功耗特性自检失败 — {message}")
    return {
        "status": "fail",
        "message": message,
        "full_automation": True,
    }
