#!/usr/bin/env python3
"""Shared expected-vs-actual evidence printer for SPD self-check scripts.

Scripts should call ``print_comparison`` / ``print_check_result`` so Console
结论 and step logs always show why a case PASS/FAIL/BLOCKED.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple


@dataclass
class EvidenceRow:
    name: str
    expected: str
    actual: str
    ok: bool

    def as_line(self) -> str:
        mark = "OK" if self.ok else "FAIL"
        # 多行便于 Console 结论阅读（勿压成「|」单行）
        return (
            f"- [{mark}] {self.name}\n"
            f"  预期: {self.expected}\n"
            f"  实际: {self.actual}"
        )


def row(name: str, expected: object, actual: object, ok: bool) -> EvidenceRow:
    return EvidenceRow(
        name=str(name),
        expected=_fmt(expected),
        actual=_fmt(actual),
        ok=bool(ok),
    )


def _fmt(value: object) -> str:
    if value is None:
        return "(missing)"
    text = str(value).strip()
    if not text:
        return "(empty)"
    # Keep one-line for Console 结论; truncate long proc dumps.
    text = " ".join(text.split())
    if len(text) > 160:
        return text[:157] + "..."
    return text


def print_comparison(rows: Sequence[EvidenceRow], *, title: str = "预期 vs 实际") -> None:
    print(f"\n=== {title} ===")
    if not rows:
        print("- (无对比项)")
        return
    for item in rows:
        print(item.as_line())


def print_check_result(
    status: str,
    rows: Sequence[EvidenceRow] | None = None,
    *,
    extra_lines: Iterable[str] | None = None,
) -> None:
    """Print comparison (optional) then CHECK RESULT + bullets."""
    status_u = str(status).strip().upper()
    if rows:
        print_comparison(rows)
    print(f"\n=== CHECK RESULT: {status_u} ===")
    if rows:
        ok_n = sum(1 for r in rows if r.ok)
        fail_n = len(rows) - ok_n
        print(f"- 对比项: {ok_n} OK / {fail_n} FAIL / 共 {len(rows)}")
    if extra_lines:
        for line in extra_lines:
            text = str(line).rstrip()
            if not text:
                continue
            print(text if text.lstrip().startswith("-") else f"- {text}")


def summarize_check_output(stdout: str, returncode: int) -> str:
    """Build Console ``message`` from script stdout: verdict + expected/actual."""
    lines = [ln.rstrip() for ln in (stdout or "").splitlines()]
    label = {0: "PASS", 1: "FAIL", 2: "BLOCKED"}.get(returncode, f"EXIT_{returncode}")

    result_idx = -1
    result_line = ""
    for i, line in enumerate(lines):
        upper = line.upper()
        if "CHECK RESULT" in upper:
            result_idx = i
            result_line = line.strip()
        elif "检查结果:" in line or "检查结果：" in line:
            result_idx = i
            result_line = line.strip()
        elif "VERSION RESULT" in upper:
            result_idx = i
            result_line = line.strip()

    # Prefer dedicated comparison block (anywhere).
    cmp_start = -1
    for i, line in enumerate(lines):
        if "预期 vs 实际" in line or "EXPECTED vs ACTUAL" in line.upper():
            cmp_start = i
            break

    evidence: List[str] = []
    if cmp_start >= 0:
        for line in lines[cmp_start + 1 :]:
            s = line.rstrip()
            if s.strip().startswith("==="):
                break
            if not s.strip():
                continue
            # 保留缩进续行（预期/实际）
            evidence.append(s if s.lstrip().startswith("-") or s.startswith(" ") else f"- {s.strip()}")
    elif result_idx >= 0:
        for line in lines[result_idx + 1 :]:
            s = line.rstrip()
            if s.strip().startswith("==="):
                break
            if not s.strip():
                continue
            if s.strip().startswith("-") or s.strip().startswith("说明") or s.startswith(" "):
                evidence.append(s if (s.lstrip().startswith("-") or s.startswith(" ")) else f"- {s.strip()}")
            elif evidence:
                evidence.append(f"  {s.strip()}")

    # Fallback: last few meaningful bullets in whole log
    if not evidence:
        bullets = [ln.rstrip() for ln in lines if ln.strip().startswith("- ")]
        evidence = bullets[-30:]

    head = result_line or f"=== CHECK RESULT: {label} ==="
    if not evidence:
        return head

    # Bound for UI 结论 / CSV
    max_lines = 80
    clipped = evidence[:max_lines]
    if len(evidence) > max_lines:
        clipped.append(f"- …另有 {len(evidence) - max_lines} 行明细已省略")

    body = "\n".join(clipped)
    # 结论多行展示：标题 + 每条对比独占行（UI 需 pre-wrap）
    text = f"{head}\n--- 判定明细 ---\n{body}"
    if len(text) > 6000:
        text = text[:5990] + "\n…"
    return text


__all__ = [
    "EvidenceRow",
    "row",
    "print_comparison",
    "print_check_result",
    "summarize_check_output",
]
