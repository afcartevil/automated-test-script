"""NL UI 动作步骤的人类可读摘要（与 Console 子步骤展示对齐）。"""

from __future__ import annotations

from typing import Any


def format_step_summary(step: dict[str, Any]) -> str:
    op = str(step.get("op") or "").strip()
    if op == "tap_text":
        return f"tap_text {str(step.get('text') or '').strip()}"
    if op == "tap_desc":
        desc = str(step.get("desc") or step.get("content-desc") or "").strip()
        return f"tap_desc {desc}"
    if op == "assert_text":
        text = str(step.get("text") or "").strip()
        present = step.get("present", True)
        if present is False:
            return f"assert_text 不应出现 {text}"
        return f"assert_text {text}"
    if op == "assert_desc":
        desc = str(step.get("desc") or step.get("content-desc") or "").strip()
        present = step.get("present", True)
        if present is False:
            return f"assert_desc 不应出现 {desc}"
        return f"assert_desc {desc}"
    if op == "shell":
        cmd = str(step.get("cmd") or "").strip()
        if len(cmd) > 56:
            cmd = cmd[:53] + "..."
        return f"shell {cmd}"
    if op == "wait_until":
        condition = str(step.get("condition") or "").strip()
        text = str(step.get("text") or "").strip()
        desc = str(step.get("desc") or step.get("content-desc") or "").strip()
        detail = text or desc
        if detail:
            return f"wait_until {condition} {detail}"
        return f"wait_until {condition}"
    if op == "dial_keys":
        keys = str(step.get("keys") or step.get("text") or "").strip()
        return f"dial_keys {keys}"
    if op == "swipe":
        direction = str(step.get("direction") or "up").strip()
        return f"swipe {direction}"
    if op == "wait":
        if "seconds" in step:
            seconds = float(step.get("seconds") or 0)
        else:
            seconds = float(step.get("ms") or 1000) / 1000.0
        return f"wait {seconds:g}s"
    if op == "screenshot":
        name = str(step.get("name") or "screenshot").strip() or "screenshot"
        return f"screenshot {name}"
    if op in {"wake", "home", "back", "uidump"}:
        return op
    return op or "(未知操作)"
