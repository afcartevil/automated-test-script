"""Build searchable text from a Jira issue for log URL extraction."""

from __future__ import annotations

from typing import Any, Dict, List

# Pipeline auto-comment markers — lines containing these are skipped when harvesting URLs.
_EXPORT_FLAGS = (
    "ModemLogPipelineExportFlag",
    "QcomModemLogPipelineExportFlag",
    "SprdModemLogPipelineExportFlag",
    "LogInsight:checked",
)


def text_without_export_flag_lines(text: str) -> str:
    if not text:
        return ""
    kept = [line for line in text.splitlines() if not any(flag in line for flag in _EXPORT_FLAGS)]
    return "\n".join(kept)


def build_issue_log_text(issue_detail: Dict[str, Any]) -> str:
    """
    Combine summary, description, and comments into one blob for URL classification.
    Mirrors modem-analysis-local fetch_issue_context text gathering.
    """
    parts: List[str] = []
    summary = str(issue_detail.get("title") or issue_detail.get("summary") or "")
    description = str(issue_detail.get("description") or "")
    if summary:
        parts.append(summary)
    if description:
        parts.append(description)

    for comment in issue_detail.get("comments") or []:
        body = str((comment or {}).get("body") or "")
        if not body:
            continue
        if any(flag in body for flag in _EXPORT_FLAGS):
            body = text_without_export_flag_lines(body)
            if not body.strip():
                continue
        parts.append(body)

    return text_without_export_flag_lines("\n".join(p for p in parts if p))
