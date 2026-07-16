"""Squash patch 准确性校验：对比 git 基准 diff 与落盘文件。"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.patch_analyzer import (
    count_deletions,
    count_insertions,
    extract_files,
    run_git,
)


@dataclass
class SquashCheck:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class SquashValidationResult:
    ok: bool
    checks: List[SquashCheck] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        failed = [c for c in self.checks if not c.passed]
        if not self.ok and failed:
            return "; ".join(f"{c.name}: {c.detail}" for c in failed)
        if self.warnings:
            return "通过（" + "；".join(self.warnings) + "）"
        return "通过"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "summary": self.summary,
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in self.checks
            ],
            "warnings": list(self.warnings),
        }


def extract_diff_body_from_squash(text: str) -> str:
    """Strip format-patch 邮件头，保留 unified diff 正文。"""
    if not text:
        return ""
    marker = "diff --git "
    idx = text.find(marker)
    if idx < 0:
        return text.strip()
    return text[idx:].strip()


def extract_diff_body_from_squash_file(path: Path) -> str:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise FileNotFoundError(str(path)) from exc
    return extract_diff_body_from_squash(raw)


def _git_returncode(repo_dir: Path, args: List[str]) -> int:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return int(proc.returncode)


def _parse_shortstat(text: str) -> Dict[str, int]:
    """Parse ``N files changed, X insertions(+), Y deletions(-)``."""
    out = {"files": 0, "insertions": 0, "deletions": 0}
    if not text or not text.strip():
        return out
    m = re.search(
        r"(\d+)\s+files?\s+changed(?:,\s*(\d+)\s+insertions?\(\+\))?(?:,\s*(\d+)\s+deletions?\(-\))?",
        text.strip(),
    )
    if not m:
        return out
    out["files"] = int(m.group(1) or 0)
    out["insertions"] = int(m.group(2) or 0)
    out["deletions"] = int(m.group(3) or 0)
    return out


def validate_squash_patch(
    repo_dir: Path,
    from_tag: str,
    to_tag: str,
    squash_path: Path,
    *,
    expected_commit_count: Optional[int] = None,
) -> SquashValidationResult:
    """校验 squash 文件是否与 ``git diff -W -M from..to`` 一致。

    检查项：
    1. from_tag 是 to_tag 的祖先（线性区间）
    2. 区间 commit 数（可选）与声明一致
    3. 变更文件集合一致
    4. 增删行统计一致
    5. diff 正文与 git 实时输出一致
    6. 两 tag 的 tree 不同（有变更时 squash 不应为空）
    """
    checks: List[SquashCheck] = []
    warnings: List[str] = []
    repo_dir = Path(repo_dir)

    if not squash_path.is_file():
        checks.append(SquashCheck("file_exists", False, f"文件不存在: {squash_path}"))
        return SquashValidationResult(ok=False, checks=checks, warnings=warnings)

    # ── 1. 祖先关系 ─────────────────────────────────────
    ancestor_ok = _git_returncode(repo_dir, ["merge-base", "--is-ancestor", from_tag, to_tag]) == 0
    same_ref = from_tag.strip() == to_tag.strip()
    if same_ref:
        checks.append(SquashCheck("ancestor", True, "from_tag 与 to_tag 相同"))
    elif ancestor_ok:
        checks.append(SquashCheck("ancestor", True, f"{from_tag} → {to_tag} 线性区间"))
    else:
        checks.append(
            SquashCheck(
                "ancestor",
                False,
                f"{from_tag} 不是 {to_tag} 的祖先，squash diff 可能不能代表完整区间净变更",
            )
        )
        warnings.append("非祖先区间，结果仅供参考")

    # ── 2. commit 数 ────────────────────────────────────
    try:
        rev_count = int(
            run_git(repo_dir, ["rev-list", "--count", f"{from_tag}..{to_tag}"]).strip() or "0"
        )
    except Exception as exc:
        rev_count = -1
        checks.append(SquashCheck("commit_count", False, f"无法统计 commit: {exc}"))
    else:
        if expected_commit_count is not None and expected_commit_count >= 0:
            passed = rev_count == expected_commit_count
            checks.append(
                SquashCheck(
                    "commit_count",
                    passed,
                    f"git rev-list={rev_count}, 期望={expected_commit_count}",
                )
            )
        else:
            checks.append(
                SquashCheck("commit_count", True, f"git rev-list={rev_count}")
            )

    # ── Git 基准 diff（与生成命令一致）────────────────
    try:
        reference = run_git(
            repo_dir, ["diff", "-W", "-M", f"{from_tag}..{to_tag}"],
        )
        shortstat_raw = run_git(
            repo_dir, ["diff", "-W", "-M", "--shortstat", f"{from_tag}..{to_tag}"],
        ).strip()
        ref_names = set(
            run_git(
                repo_dir, ["diff", "-W", "-M", "--name-only", f"{from_tag}..{to_tag}"],
            )
            .strip()
            .splitlines()
        )
        ref_names = {n.strip() for n in ref_names if n.strip()}
    except Exception as exc:
        checks.append(SquashCheck("git_reference", False, str(exc)))
        return SquashValidationResult(ok=False, checks=checks, warnings=warnings)

    try:
        squash_body = extract_diff_body_from_squash_file(squash_path)
    except OSError as exc:
        checks.append(SquashCheck("read_squash", False, str(exc)))
        return SquashValidationResult(ok=False, checks=checks, warnings=warnings)

    # ── 6. 空 diff 与 commit 数 ───────────────────────
    if rev_count > 0 and not reference.strip() and not squash_body:
        checks.append(SquashCheck("nonempty", True, "区间无文件变更（空 diff）"))
    elif rev_count > 0 and not squash_body and reference.strip():
        checks.append(SquashCheck("nonempty", False, "squash 文件 diff 正文为空，但 git 有变更"))
    else:
        checks.append(SquashCheck("nonempty", True, "diff 正文非空或区间无变更"))

    # ── 3. 文件集合 ─────────────────────────────────────
    body_names = set(extract_files(squash_body))
    if ref_names == body_names:
        checks.append(
            SquashCheck("file_set", True, f"{len(ref_names)} 个文件路径一致")
        )
    else:
        missing = sorted(ref_names - body_names)[:5]
        extra = sorted(body_names - ref_names)[:5]
        detail = f"git={len(ref_names)} squash={len(body_names)}"
        if missing:
            detail += f" 缺 {missing}"
        if extra:
            detail += f" 多 {extra}"
        checks.append(SquashCheck("file_set", False, detail))

    # ── 4. 增删统计 ─────────────────────────────────────
    ref_stat = _parse_shortstat(shortstat_raw)
    body_ins = count_insertions(squash_body)
    body_del = count_deletions(squash_body)
    stat_ok = (
        ref_stat["insertions"] == body_ins
        and ref_stat["deletions"] == body_del
    )
    checks.append(
        SquashCheck(
            "line_stats",
            stat_ok,
            (
                f"git +{ref_stat['insertions']}/-{ref_stat['deletions']} "
                f"squash +{body_ins}/-{body_del}"
            ),
        )
    )

    # ── 5. 正文逐字一致 ─────────────────────────────────
    content_ok = reference.strip() == squash_body.strip()
    if content_ok:
        checks.append(SquashCheck("content_match", True, "与 git diff -W -M 输出一致"))
    else:
        ref_len = len(reference.strip())
        body_len = len(squash_body.strip())
        checks.append(
            SquashCheck(
                "content_match",
                False,
                f"正文不一致 (git {ref_len} 字符 vs 文件 {body_len} 字符)",
            )
        )

    # ── tree 快照（辅助信息）────────────────────────────
    try:
        from_tree = run_git(repo_dir, ["rev-parse", f"{from_tag}^{{tree}}"]).strip()[:12]
        to_tree = run_git(repo_dir, ["rev-parse", f"{to_tag}^{{tree}}"]).strip()[:12]
        if from_tree == to_tree:
            warnings.append(f"tree 相同 ({from_tree})")
        else:
            warnings.append(f"tree {from_tree} → {to_tree}")
    except Exception:
        pass

    critical_names = {
        "file_exists",
        "read_squash",
        "git_reference",
        "nonempty",
        "file_set",
        "line_stats",
        "content_match",
        "ancestor",
    }
    ok = all(c.passed for c in checks if c.name in critical_names)
    if expected_commit_count is not None and expected_commit_count >= 0:
        cc = next((c for c in checks if c.name == "commit_count"), None)
        if cc and not cc.passed:
            ok = False

    return SquashValidationResult(ok=ok, checks=checks, warnings=warnings)
