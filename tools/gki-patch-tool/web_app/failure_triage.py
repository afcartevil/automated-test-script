"""LLM triage after conflict-merge or build-fix failure: retry once or advise manual."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

_VERDICT_RETRY = "retry"
_VERDICT_MANUAL = "manual"


@dataclass
class FailureTriage:
    verdict: str
    reason: str
    advice: str
    retry_hint: str
    auto_retried: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def parse_failure_triage(text: str) -> FailureTriage:
    raw = (text or "").strip()
    if not raw:
        return FailureTriage(_VERDICT_MANUAL, "未能解析诊断结果", "请根据原始错误本机处理。", "")

    fenced = re.search(r"```(?:yaml|yml)?\s*\n(.*?)\n```", raw, re.DOTALL | re.IGNORECASE)
    body = fenced.group(1) if fenced else raw

    fields: Dict[str, str] = {}
    current: Optional[str] = None
    chunks: Dict[str, list[str]] = {}
    for line in body.splitlines():
        m = re.match(r"^(verdict|reason|advice|retry_hint)\s*:\s*(.*)$", line.strip(), re.IGNORECASE)
        if m:
            current = m.group(1).lower()
            fields[current] = (m.group(2) or "").strip().strip("'\"")
            chunks[current] = []
            continue
        if current and line.strip() and not re.match(r"^[a-z_]+\s*:", line.strip(), re.IGNORECASE):
            chunks.setdefault(current, []).append(line.rstrip())

    for key, extra in chunks.items():
        if extra:
            base = fields.get(key) or ""
            fields[key] = "\n".join([base] + extra).strip() if base else "\n".join(extra).strip()

    verdict = (fields.get("verdict") or "").strip().lower()
    if verdict not in (_VERDICT_RETRY, _VERDICT_MANUAL):
        verdict = _VERDICT_MANUAL
    reason = (fields.get("reason") or "").strip() or "诊断未给出明确原因"
    advice = (fields.get("advice") or "").strip()
    retry_hint = (fields.get("retry_hint") or "").strip()
    if verdict == _VERDICT_RETRY and not retry_hint:
        retry_hint = reason
    if verdict == _VERDICT_MANUAL:
        retry_hint = ""
    if not advice:
        advice = "请结合失败日志在本机检查后处理。"
    return FailureTriage(verdict, reason, advice, retry_hint)


def analyze_upgrade_failure(
    *,
    kind: str,
    errors: str,
    extra: str = "",
) -> FailureTriage:
    from web_app.llm_service import _call_llm, get_llm_config, is_llm_configured
    from web_app.prompt_loader import load_prompt

    if not is_llm_configured():
        return FailureTriage(
            _VERDICT_MANUAL,
            "LLM 未配置，无法自动诊断",
            "请在设置中配置模型后重试，或根据下方错误本机处理。",
            "",
        )

    kind_label = "冲突合入" if kind == "conflict" else "编译错误修复"
    system = load_prompt("failure_triage")
    user = (
        f"失败类型: {kind_label} ({kind})\n\n"
        f"【失败信息】\n{(errors or '').strip()[:12000] or '（无）'}\n"
    )
    extra_text = (extra or "").strip()
    if extra_text:
        user += f"\n【补充上下文】\n{extra_text[:4000]}\n"

    try:
        content, _usage = _call_llm(system, user, get_llm_config(), timeout=90, max_tokens=1200)
    except Exception as exc:
        return FailureTriage(
            _VERDICT_MANUAL,
            f"失败诊断调用模型失败: {exc}",
            "请根据原始错误本机处理，或稍后重试。",
            "",
        )
    return parse_failure_triage(content)


def format_conflict_failure_errors(files: Dict[str, Any], limit: int = 8) -> str:
    lines: list[str] = []
    for path, ent in (files or {}).items():
        if not isinstance(ent, dict) or ent.get("status") != "failed":
            continue
        err = str(ent.get("error") or "").strip()
        summary = str(ent.get("summary") or "").strip()
        src = str(ent.get("source_path") or path)
        lines.append(f"- {src}: {err or summary or '合入失败'}")
        if len(lines) >= limit:
            break
    return "\n".join(lines) if lines else "冲突合入全部失败，无单文件详情。"
