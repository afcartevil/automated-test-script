"""NL UI 动作计划执行器。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.nl_ui.actions import (
    OptionalStepSkip,
    cleanup_device,
    evidence_dir_for,
    execute_step,
    resolve_device_id,
)
from utils.nl_ui.schema import normalize_plan
from utils.nl_ui.step_format import format_step_summary

CASE_ROOT = Path(__file__).resolve().parents[2] / "cases" / "ai_generated" / "generated"
PLAN_DIR = CASE_ROOT / "plans"


def _load_plan(case_index: int) -> dict[str, Any]:
    plan_path = PLAN_DIR / f"case{case_index}.json"
    if not plan_path.is_file():
        raise FileNotFoundError(f"缺少动作计划: {plan_path.name}")
    raw = json.loads(plan_path.read_text(encoding="utf-8"))
    return normalize_plan(raw)


def run_plan_for_case(case_index: int, device_info=None, context=None) -> dict[str, Any]:
    context = context or {}
    step_update = context.get("step_update")
    device_id = resolve_device_id(device_info if isinstance(device_info, dict) else None)
    if not device_id:
        return {"status": "fail", "message": "未找到测试机 device_id", "full_automation": True}

    def report(message: str) -> None:
        if callable(step_update):
            step_update(message)

    try:
        plan = _load_plan(int(case_index))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "fail", "message": f"动作计划无效: {exc}", "full_automation": True}

    evidence_dir = evidence_dir_for(device_id)
    steps = plan.get("steps") or []
    sub_steps = ""
    try:
        for step in steps:
            label = format_step_summary(step)
            if bool(step.get("optional")):
                label += " (optional)"
            sub_steps += f"\n{label}"
            report(sub_steps)
            try:
                execute_step(device_id, step, report=lambda _msg: None, evidence_dir=evidence_dir)
            except OptionalStepSkip:
                sub_steps += "-成功"
                report(sub_steps)
                continue
            sub_steps += "-成功"
            report(sub_steps)
        return {"status": "pass", "message": "NL UI 自动化执行通过", "full_automation": True}
    except Exception as exc:
        sub_steps += "-失败"
        report(sub_steps)
        return {"status": "fail", "message": str(exc) or "执行失败", "full_automation": True}
    finally:
        cleanup_device(device_id)
