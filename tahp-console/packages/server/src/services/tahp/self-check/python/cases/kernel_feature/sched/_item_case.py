"""Shared runner for kernel_feature/sched caseN.py (one SPD check each)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE = "sched"


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
    script = (
        Path(__file__).resolve().parents[3]
        / "tools"
        / "spd_feature_runner.py"
    )
    if not script.is_file():
        raise FileNotFoundError(f"SPD runner 不存在: {script}")
    spec = importlib.util.spec_from_file_location("spd_feature_runner_tool", script)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 SPD runner: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_spd_item(item_id: int, device_info=None, step_update=None, module: str | None = None, **context):
    # run_case 会把 module 放进 context；显式参数优先，避免重复关键字
    resolved = module or context.get("module") or MODULE
    info = device_info or {}
    try:
        serial = _device_serial(info)
    except ValueError as exc:
        return {"status": "fail", "message": str(exc), "full_automation": True}

    steps: list[str] = []

    def add_step(text: str) -> None:
        # BFF 用 \n 拆子步骤：每条必须是单行，否则多行证据会被拆成几十条「重复」步骤
        one_line = " | ".join(ln.strip() for ln in str(text).splitlines() if ln.strip())
        if not one_line:
            return
        steps.append(one_line)
        if step_update:
            step_update("\n".join(steps))

    try:
        runner = _load_runner()
    except Exception as exc:
        add_step(f"加载 SPD runner 失败: {exc}")
        return {"status": "fail", "message": str(exc), "full_automation": True}

    name = runner.checklist_item_name(resolved, item_id)
    add_step(f"执行 {resolved} 检查项 {item_id}：{name}（设备 {serial}）")
    result = runner.run_spd_check(
        resolved,
        item_id,
        serial=serial,
        on_step=add_step,
    )
    status = str(result.get("status") or "").lower()
    detail = str(result.get("info") or "").strip()
    # 结论保留完整「预期 vs 实际」；子步骤只写短结果，不再把明细贴第三遍
    message = f"{name}\n{detail}" if detail else name

    if status == "pass":
        add_step(f"通过 — {name}")
        return {"status": "pass", "message": message, "full_automation": True}
    if status == "pending":
        # SPD BLOCKED（前置不满足/不在应检范围）：记 NA，不弹人工确认，继续下一项
        add_step(f"NA/BLOCKED — {name}")
        return {"status": "na", "message": message, "full_automation": True}

    add_step(f"失败 — {name}")
    return {"status": "fail", "message": message, "full_automation": True}
