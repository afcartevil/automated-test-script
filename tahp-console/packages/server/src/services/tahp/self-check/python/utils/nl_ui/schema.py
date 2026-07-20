"""NL UI 动作计划 schema 校验（与 Node ai-nl-ui-cases.ts 对齐）。"""

from __future__ import annotations

from typing import Any

ALLOWED_OPS = frozenset({
    "wake",
    "home",
    "back",
    "shell",
    "tap_text",
    "tap_desc",
    "tap_rid",
    "swipe",
    "wait",
    "wait_until",
    "dial_keys",
    "assert_text",
    "assert_desc",
    "screenshot",
    "uidump",
})

DIAL_KEYS_ALLOWED = frozenset("0123456789*#+")
DIAL_KEYS_MAX_LEN = 32

WAIT_UNTIL_CONDITIONS = frozenset({
    "text_present",
    "text_gone",
    "desc_present",
    "desc_gone",
    "clickable",
})

SHELL_PREFIX_WHITELIST = (
    "am start",
    "am force-stop",
    "input keyevent",
    "input tap",
    "input swipe",
    "input text",
    "uiautomator",
    "settings put",
    "settings get",
    "cmd statusbar",
    "monkey",
)

SHELL_FORBIDDEN_MARKERS = (
    "rm ",
    "reboot",
    " dd ",
    "mkfs",
    "format",
    "shutdown",
    "poweroff",
    "su ",
    "chmod ",
    "chown ",
    "pm uninstall",
    "pm clear ",
)


def validate_shell_cmd(cmd: str) -> str | None:
    normalized = (cmd or "").strip()
    if not normalized:
        return "shell 命令不能为空"
    lower = normalized.lower()
    for marker in SHELL_FORBIDDEN_MARKERS:
        if marker in lower:
            return f"禁止的 shell 命令: {normalized}"
    if not any(lower.startswith(prefix) for prefix in SHELL_PREFIX_WHITELIST):
        return f"shell 命令不在白名单: {normalized}"
    return None


def normalize_plan(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("动作计划必须是 JSON 对象")
    if raw.get("executable") is False:
        raise ValueError(str(raw.get("reason") or "该用例无法使用手机 UI 自动化执行"))
    steps = raw.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("动作计划缺少 steps")
    normalized_steps: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ValueError(f"第 {index} 步格式无效")
        op = str(step.get("op") or "").strip()
        if op not in ALLOWED_OPS:
            raise ValueError(f"第 {index} 步含不支持的操作: {op or '(空)'}")
        record = dict(step)
        record["op"] = op
        if "optional" in record:
            record["optional"] = bool(record.get("optional"))
        if op == "shell":
            cmd = str(record.get("cmd") or "")
            err = validate_shell_cmd(cmd)
            if err:
                raise ValueError(f"第 {index} 步: {err}")
            cmd_lower = cmd.lower()
            if "input text" in cmd_lower and any(ch in cmd for ch in "*#"):
                raise ValueError(
                    f"第 {index} 步禁止用 input text 输入含 */# 的工程码，请改用 dial_keys"
                )
        if op in {"tap_text", "assert_text"} and not str(record.get("text") or "").strip():
            raise ValueError(f"第 {index} 步缺少 text")
        if op in {"tap_desc", "assert_desc"}:
            desc = str(record.get("desc") or record.get("content-desc") or "").strip()
            if not desc:
                raise ValueError(f"第 {index} 步缺少 desc/content-desc")
            record["desc"] = desc
        if op == "tap_rid":
            rid = str(
                record.get("rid")
                or record.get("resource-id")
                or record.get("resourceId")
                or ""
            ).strip()
            if not rid:
                raise ValueError(f"第 {index} 步 tap_rid 缺少 rid")
            if len(rid) > 128:
                raise ValueError(f"第 {index} 步 tap_rid 过长（最多 128）")
            if not all(ch.isalnum() or ch in "._:/-" for ch in rid):
                raise ValueError(f"第 {index} 步 tap_rid 含不支持字符")
            record["rid"] = rid
        if op == "wait":
            if "seconds" in record:
                seconds = float(record.get("seconds") or 0)
            else:
                ms = float(record.get("ms") or 1000)
                seconds = ms / 1000.0
            if seconds < 0 or seconds > 120:
                raise ValueError(f"第 {index} 步 wait 时长无效")
            record["seconds"] = seconds
        if op == "wait_until":
            condition = str(record.get("condition") or "").strip()
            if condition not in WAIT_UNTIL_CONDITIONS:
                raise ValueError(
                    f"第 {index} 步 wait_until.condition 无效，允许: "
                    + ", ".join(sorted(WAIT_UNTIL_CONDITIONS))
                )
            record["condition"] = condition
            if condition in {"text_present", "text_gone", "clickable"}:
                if not str(record.get("text") or "").strip():
                    raise ValueError(f"第 {index} 步 wait_until 缺少 text")
            if condition in {"desc_present", "desc_gone"}:
                desc = str(record.get("desc") or record.get("content-desc") or "").strip()
                if not desc:
                    raise ValueError(f"第 {index} 步 wait_until 缺少 desc")
                record["desc"] = desc
            timeout = float(record.get("timeout") or record.get("seconds") or 30)
            if timeout <= 0 or timeout > 300:
                raise ValueError(f"第 {index} 步 wait_until.timeout 无效（1-300s）")
            record["timeout"] = timeout
            poll = float(record.get("poll") or 0.5)
            if poll <= 0 or poll > 10:
                raise ValueError(f"第 {index} 步 wait_until.poll 无效")
            record["poll"] = poll
        if op == "dial_keys":
            keys = str(record.get("keys") or record.get("text") or "").strip()
            if not keys:
                raise ValueError(f"第 {index} 步 dial_keys 缺少 keys")
            if len(keys) > DIAL_KEYS_MAX_LEN:
                raise ValueError(f"第 {index} 步 dial_keys 过长（最多 {DIAL_KEYS_MAX_LEN}）")
            bad = [ch for ch in keys if ch not in DIAL_KEYS_ALLOWED]
            if bad:
                raise ValueError(f"第 {index} 步 dial_keys 含不支持字符: {''.join(sorted(set(bad)))}")
            record["keys"] = keys
        if op == "swipe":
            direction = str(record.get("direction") or "up").lower()
            if direction not in {"up", "down", "left", "right"}:
                raise ValueError(f"第 {index} 步 swipe 方向无效")
            record["direction"] = direction
        normalized_steps.append(record)
    has_assert = any(str(s.get("op")) in {"assert_text", "assert_desc"} for s in normalized_steps)
    if not has_assert:
        raise ValueError("动作计划必须包含至少一步 UI 断言")
    return {"executable": True, "reason": str(raw.get("reason") or ""), "steps": normalized_steps}
