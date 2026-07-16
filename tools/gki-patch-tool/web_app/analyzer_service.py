"""后台分析服务 - 在子线程中运行 patch_analyzer 并推送进度。"""
import json
import os
import random
import threading
import time
import uuid
from collections import Counter, defaultdict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from patch_analyzer import (
    analyze_commit,
    analyze_patch_data,
    build_dimension_reasons,
    build_platform_tags,
    build_summary,
    build_test_suggestions,
    choose_profile,
    detect_high_risk_paths,
    detect_test_signal,
    fetch_commits_between_tags,
    fetch_patch_data,
    fetch_single_commit,
    load_config,
    normalize_repo_url,
    parse_format_patch_output,
)

from web_app.database import (
    PatchBatchWriter,
    create_task,
    delete_task,
    get_patch,
    get_patches_by_shas,
    get_patches_by_task,
    get_task,
    get_task_patches,
    link_task_patch,
    patch_exists,
    save_patch,
    update_task,
    upsert_patch,
)
from web_app.interval_diff_service import (
    load_interval_diff_cache,
    save_interval_diff_cache,
)
from web_app.squash_patch_validator import SquashValidationResult, validate_squash_patch
from web_app.repo_config import get_local_repo_dir


# ── LLM analysis ────────────────────────────────────────
_llm_in_progress: Dict[str, bool] = {}
# 单笔 patch LLM：首次 + 最多 3 次重试（共 4 次），可通过 GKI_LLM_PATCH_MAX_ATTEMPTS 覆盖
_LLM_PATCH_MAX_ATTEMPTS = max(1, int(os.environ.get("GKI_LLM_PATCH_MAX_ATTEMPTS", "4")))
# API 成功但无有效 score/解读：额外重试 2~3 次（默认 3），GKI_LLM_EMPTY_RESULT_MAX_RETRIES
_LLM_EMPTY_RESULT_MAX_RETRIES = max(
    2,
    min(3, int(os.environ.get("GKI_LLM_EMPTY_RESULT_MAX_RETRIES", "3"))),
)

# ── 任务取消标记 ─────────
_cancelled_tasks: set = set()  # task_id set


def cancel_task(task_id: str) -> None:
    """Mark a task as cancelled so running threads can stop."""
    _cancelled_tasks.add(task_id)


def cancel_analysis_task(task_id: str) -> Tuple[bool, str]:
    """Cancel a running analysis task."""
    task = get_task(task_id)
    if not task:
        return False, "任务不存在"
    status = (task.get("status") or "").lower()
    if status in ("completed", "failed", "cancelled"):
        return False, f"任务已结束（{status}），无法取消"
    cancel_task(task_id)
    msg = "任务已取消"
    update_task(
        task_id,
        status="cancelled",
        error_msg=msg,
        completed_at=datetime.now().isoformat(),
    )
    _set_progress(task_id, {"status": "cancelled", "message": msg})
    return True, msg


def is_task_cancelled(task_id: str) -> bool:
    return task_id in _cancelled_tasks

# ── 任务开始时间映射（用于perf日志文件名） ──
_task_start_times: Dict[str, str] = {}  # task_id -> formatted start time

# ── 性能日志（本地持久化，用于分析瓶颈） ─────────────
_TIMING_DIR = Path(__file__).parent.parent / "outputs" / "perf_logs"
_TIMING_BUFFERS: Dict[str, List[str]] = {}
_TIMING_FLUSH_SIZE = int(os.environ.get("GKI_TIMING_BATCH_SIZE", "25"))
_DB_BATCH_SIZE = int(os.environ.get("GKI_DB_BATCH_SIZE", "20"))

# ── defect_scan git 结果缓存（同进程内复用） ─────────────
_FIXES_LOG_CACHE: Dict[Tuple[str, str], str] = {}
_TAG_SUBJECT_LOG_CACHE: Dict[str, str] = {}


# ── 开发模块分类（dev_modules.txt，见 dev_module_classifier.py） ──
from web_app.dev_module_classifier import (
    classify_and_assign_patch,
    classify_patch_dev_module,
    get_dev_module_descriptions,
    get_dev_module_names,
    load_dev_modules as _load_dev_modules,
    normalize_dev_module_name,
)


def _classify_dev_module(patch_data: dict, llm_suggestion: str = "") -> str:
    """兼容旧调用：严格按 dev_modules.txt 路径规则分类。"""
    return classify_patch_dev_module(patch_data, llm_suggestion=llm_suggestion)


def _run_git_with_heartbeat(repo_dir, git_args, report_fn, label, start_time):
    """Run git command in a thread while sending heartbeats every 3s.

    Args:
        repo_dir: Path to git repo
        git_args: list of git arguments
        report_fn: callable(phase, total, current, message) for heartbeats
        label: description for heartbeat messages
        start_time: time.monotonic() start reference
    Returns:
        stdout string from git command
    """
    import threading
    from tools.patch_analyzer import run_git
    result = {'output': None, 'error': None}

    def _worker():
        try:
            result['output'] = run_git(repo_dir, git_args)
        except Exception as e:
            result['error'] = e

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    while t.is_alive():
        t.join(timeout=3)
        if t.is_alive():
            elapsed = time.monotonic() - start_time
            report_fn('format_patch', 3, 0, f'{label} ({elapsed:.0f}s)')
    if result['error']:
        raise result['error']
    return result['output']



def list_repo_tags() -> List[str]:
    """List all tags in the local repo, sorted by version (newest first)."""
    from patch_analyzer import run_git

    repo_dir = get_local_repo_dir()
    if not repo_dir:
        return []
    try:
        output = run_git(repo_dir, ["tag", "--list", "--sort=-v:refname"])
        tags = [t.strip() for t in output.strip().split("\n") if t.strip()]
        return tags
    except Exception as exc:
        print(f"[TAGS] git tag 失败: {exc}", flush=True)
        return []


def find_subsequent_tags(to_tag: str, count: int = 3) -> List[str]:
    """Find the next `count` tags after to_tag in version order.
    Only returns tags from the same series (e.g., GKI monthly tags
    like android12-5.10-YYYY-MM_rN only match other monthly tags).
    """
    tags = list_repo_tags()  # newest first
    if not tags:
        return []

    # Extract series prefix to avoid mixing tag series
    # Monthly GKI: android12-5.10-2025-12_r4 → prefix "android12-5.10-"
    # Kernel ver:  android12-5.10.240_r00   → prefix "android12-5.10."
    import re as _re
    m = _re.match(r'(android\d+-\d+\.\d+[-.])', to_tag)
    prefix = m.group(1) if m else ''

    # Filter to same series only
    if prefix:
        same_series = [t for t in tags if t.startswith(prefix)]
    else:
        same_series = tags

    tags_asc = list(reversed(same_series))  # oldest first
    # Find to_tag index
    try:
        idx = tags_asc.index(to_tag)
    except ValueError:
        idx = -1
        for i, t in enumerate(tags_asc):
            if to_tag in t or t in to_tag:
                idx = i
                break
        if idx < 0:
            return []
    return tags_asc[idx + 1: idx + 1 + count]


def _tag_exists_in_repo(tag: str) -> bool:
    """Return True when tag resolves in the configured local repo."""
    from patch_analyzer import run_git

    repo_dir = get_local_repo_dir()
    if not repo_dir or not tag:
        return False
    try:
        run_git(repo_dir, ["rev-parse", "--verify", f"refs/tags/{tag}^{{}}"])
        return True
    except Exception:
        return False


def _list_upstream_month_subtags(
    repo_url: str,
    month_prefix: str,
) -> Tuple[Dict[int, str], Dict[str, str]]:
    """List ``month_prefix_rN`` tags from upstream via ``git ls-remote``."""
    import subprocess
    from tools.patch_analyzer import normalize_repo_url

    remote = normalize_repo_url(repo_url).rstrip("/")
    if not remote:
        return {}, {}
    pattern = f"{month_prefix}_r*"
    try:
        proc = subprocess.run(
            ["git", "ls-remote", "--tags", remote, pattern],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except Exception as exc:
        print(f"[TAGS] ls-remote 失败 ({pattern}): {exc}", flush=True)
        return {}, {}

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        if err:
            print(f"[TAGS] ls-remote 失败 ({pattern}): {err}", flush=True)
        return {}, {}

    r_map: Dict[int, str] = {}
    tag_commits: Dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        commit = parts[0].strip()
        ref = parts[1].strip()
        if ref.endswith("^{}"):
            tag = ref.removeprefix("refs/tags/").removesuffix("^{}")
        else:
            tag = ref.removeprefix("refs/tags/")
            if tag in tag_commits:
                continue
        tm = re.match(rf"^{re.escape(month_prefix)}_r(\d+)$", tag)
        if tm:
            r_num = int(tm.group(1))
            r_map[r_num] = tag
            tag_commits[tag] = commit
    return r_map, tag_commits


def _tags_resolvable_for_analysis(from_tag: str, to_tag: str) -> bool:
    """Return True when both tags can be used for range analysis."""
    repo_dir = get_local_repo_dir()
    if repo_dir:
        return _tag_exists_in_repo(from_tag) and _tag_exists_in_repo(to_tag)
    return bool(from_tag and to_tag)


def _peel_tag_commit(tag: str) -> str:
    """Resolve a tag to its peeled commit SHA using the local repo."""
    from patch_analyzer import run_git

    repo_dir = get_local_repo_dir()
    if not repo_dir or not tag:
        return ""
    try:
        return run_git(repo_dir, ["rev-parse", f"{tag}^{{commit}}"]).strip()
    except Exception:
        return ""


def _count_commits_between(from_tag: str, to_tag: str) -> Optional[int]:
    """Return commit count for ``from_tag..to_tag``, or None when unavailable."""
    from patch_analyzer import run_git

    repo_dir = get_local_repo_dir()
    if not repo_dir:
        return None
    try:
        out = run_git(repo_dir, ["rev-list", "--count", f"{from_tag}..{to_tag}"]).strip()
        return int(out)
    except Exception:
        return None


def _dedupe_subtags_by_commit(
    r_map: Dict[int, str],
    tag_commits: Optional[Dict[str, str]] = None,
) -> Dict[int, str]:
    """Keep the lowest ``rN`` for each unique commit (drop alias/no-op sub-tags)."""
    commits = tag_commits or {}
    commit_to_r: Dict[str, int] = {}
    for r_num in sorted(r_map):
        tag = r_map[r_num]
        commit = commits.get(tag) or _peel_tag_commit(tag)
        if not commit:
            continue
        prev = commit_to_r.get(commit)
        if prev is None or r_num < prev:
            commit_to_r[commit] = r_num

    deduped = {r_num: r_map[r_num] for r_num in sorted(commit_to_r.values())}
    dropped = sorted(set(r_map) - set(deduped))
    if dropped:
        print(
            f"[MONTHLY] 跳过同 commit 重复子 tag: "
            + ", ".join(r_map[n] for n in dropped),
            flush=True,
        )
    return deduped


def _build_month_subtag_map(
    month_prefix: str,
    repo_url: str = "",
) -> Tuple[Dict[int, str], Dict[str, str]]:
    """Build ``rN -> tag`` map for a month. Prefer upstream tags over local listing."""
    r_map: Dict[int, str] = {}
    tag_commits: Dict[str, str] = {}
    if repo_url:
        r_map, tag_commits = _list_upstream_month_subtags(repo_url, month_prefix)
        if r_map:
            nums = ", ".join(f"r{n}" for n in sorted(r_map))
            print(f"[MONTHLY] 远端 {month_prefix} 子 tag: {nums}", flush=True)

    if not r_map:
        for tag in list_repo_tags():
            tm = re.match(rf"^{re.escape(month_prefix)}_r(\d+)$", tag)
            if tm and _tag_exists_in_repo(tag):
                r_num = int(tm.group(1))
                r_map[r_num] = tag
                commit = _peel_tag_commit(tag)
                if commit:
                    tag_commits[tag] = commit
        if r_map:
            nums = ", ".join(f"r{n}" for n in sorted(r_map))
            print(f"[MONTHLY] 本地 {month_prefix} 子 tag: {nums}", flush=True)
        return r_map, tag_commits

    repo_dir = get_local_repo_dir()
    if repo_dir:
        stale_local: List[str] = []
        for tag in list_repo_tags():
            tm = re.match(rf"^{re.escape(month_prefix)}_r(\d+)$", tag)
            if not tm:
                continue
            r_num = int(tm.group(1))
            if r_num not in r_map and _tag_exists_in_repo(tag):
                stale_local.append(tag)
        if stale_local:
            print(
                f"[MONTHLY] 忽略本地多余子 tag（远端不存在）: {', '.join(stale_local)}",
                flush=True,
            )
        for tag in r_map.values():
            if tag not in tag_commits:
                commit = _peel_tag_commit(tag)
                if commit:
                    tag_commits[tag] = commit
    return r_map, tag_commits


def _append_subtag_interval(
    intervals: List[Tuple[str, str]],
    from_tag: str,
    to_tag: str,
) -> None:
    """Append a sub-tag interval when it has incremental commits."""
    if not _tags_resolvable_for_analysis(from_tag, to_tag):
        return
    count = _count_commits_between(from_tag, to_tag)
    if count == 0:
        print(
            f"[MONTHLY] 跳过空区间 {from_tag} -> {to_tag}（0 笔 commit）",
            flush=True,
        )
        return
    if count is not None:
        print(
            f"[MONTHLY] 子 tag 区间 {from_tag} -> {to_tag}（{count} 笔 commit）",
            flush=True,
        )
    intervals.append((from_tag, to_tag))


def _parse_month_subtag(tag: str) -> Optional[Tuple[str, int]]:
    """Return (month_prefix, r_num) for ``androidXX-X.XX-YYYY-MM_rN``, else None."""
    m = re.match(r"^(android\d+-\d+\.\d+-\d{4}-\d{2})_r(\d+)$", tag)
    if not m:
        return None
    return m.group(1), int(m.group(2))


def is_same_month_subtag_range(from_tag: str, to_tag: str) -> bool:
    """True when both tags are ``_rN`` sub-tags of the same calendar month prefix."""
    if not from_tag or not to_tag:
        return False
    from_parsed = _parse_month_subtag(str(from_tag).strip())
    to_parsed = _parse_month_subtag(str(to_tag).strip())
    return bool(from_parsed and to_parsed and from_parsed[0] == to_parsed[0])


def find_monthly_subtag_intervals(
    to_tag: str,
    from_tag: str = "",
    repo_url: str = "",
) -> List[Tuple[str, str]]:
    """Return cumulative sub-tag intervals from baseline r1 for monthly recommendation.

    Rules:
    - For the month in ``to_tag``, collect ``_rN`` tags from upstream ``git ls-remote``
      (preferred) or local repo, dedupe by commit, sort by N.
    - Emit **cumulative** intervals ``(r1, rN)`` for each existing sub-tag after baseline:
      e.g. r1+r2+r3+r4 -> r1->r2, r1->r3, r1->r4.
    - When ``from_tag`` and ``to_tag`` are both same-month ``_rN`` tags, **skip** monthly
      sub-tag analysis (return ``[]``): the main range task already covers that month's
      sub-tag delta, so pulling r1->r2 … r1->rMax again is redundant.
    - Skips pairs whose tags cannot be used for analysis or have 0 commits.
    """
    if from_tag and is_same_month_subtag_range(from_tag, to_tag):
        print(
            f"[MONTHLY] 跳过子 tag 分析：主任务已是同月区间 "
            f"{from_tag} -> {to_tag}",
            flush=True,
        )
        return []

    m = re.match(r"^(android\d+-\d+\.\d+-\d{4}-\d{2})(?:_r(\d+))?$", to_tag)
    if not m:
        return []
    month_prefix = m.group(1)

    r_map, tag_commits = _build_month_subtag_map(month_prefix, repo_url)
    r_map = _dedupe_subtags_by_commit(r_map, tag_commits)
    return _build_cumulative_subtag_intervals(r_map)


def _build_cumulative_subtag_intervals(r_map: Dict[int, str]) -> List[Tuple[str, str]]:
    """Build r1->r2, r1->r3, … intervals from the lowest existing sub-tag."""
    r_nums = sorted(r_map.keys())
    if len(r_nums) < 2:
        return []

    baseline_tag = r_map[r_nums[0]]
    intervals: List[Tuple[str, str]] = []
    for r_num in r_nums[1:]:
        _append_subtag_interval(intervals, baseline_tag, r_map[r_num])
    return intervals


_KEY_RISK_NONE_VALUES = frozenset({"无", "none", "n/a", "na", "-", "—"})


def is_key_risk_none(key_risk: Any) -> bool:
    """Return True when key_risk means no meaningful core risk."""
    raw = str(key_risk or "").strip()
    if not raw:
        return True
    return raw in _KEY_RISK_NONE_VALUES or raw.lower() in _KEY_RISK_NONE_VALUES


def patch_high_risk_reason(p: Dict[str, Any]) -> str:
    """Explain why a patch should be treated as high-risk; empty if it should not."""
    key_risk = str(p.get("key_risk") or "").strip()
    if key_risk and not is_key_risk_none(key_risk):
        return key_risk

    crash = str(p.get("crash_risk") or "").strip()
    if crash in ("高", "中"):
        tail = str(p.get("crash_risk_reason") or "").strip()
        return f"死机风险{crash}" + (f"：{tail}" if tail else "")

    if p.get("blocked"):
        rules = p.get("block_rules_hit") or []
        if rules:
            labels = [str(r) for r in rules[:3]]
            return f"触发阻断规则：{', '.join(labels)}"
        return "触发阻断规则"

    rec = str(p.get("recommendation") or "").strip()
    score = float(p.get("score", 0) or 0)
    if "不建议" in rec:
        return rec
    if score and score < 4:
        return rec or f"评分偏低（{score:g}）"

    if p.get("high_risk_paths"):
        if score and score < 6:
            return f"命中高风险路径且评分偏低（{score:g}）"
        return "命中高风险路径（scheduler/mm/drm 等核心目录）"

    introduced = str(p.get("introduced_risk") or p.get("introducer_analysis") or "").strip()
    if introduced and "未识别" not in introduced and "不适用" not in introduced:
        return introduced[:120]

    patterns = p.get("crash_patterns") or []
    if patterns:
        labels = []
        for pat in patterns[:2]:
            if isinstance(pat, dict):
                label = str(pat.get("label") or pat.get("name") or pat.get("type") or "").strip()
                if label:
                    labels.append(label)
            elif pat:
                labels.append(str(pat))
        if labels:
            return f"命中死机模式：{', '.join(labels)}"

    if p.get("fix_in_future"):
        return "后续版本存在修复提交，可能存在已知缺陷"

    return ""


def _build_high_risk_item(p: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """Structured high-risk patch entry for API/UI with explicit reason fields."""
    sha = str(p.get("sha") or p.get("commit") or "")[:12]
    score = p.get("score")
    blocked = bool(p.get("blocked"))
    crash = str(p.get("crash_risk") or "").strip()
    rec = str(p.get("recommendation") or "").strip()
    key_risk = str(p.get("key_risk") or "").strip()
    return {
        "sha": sha,
        "title": str(p.get("title") or "")[:60],
        "risk": reason,
        "reason": reason,
        "key_risk": key_risk,
        "score": score,
        "recommendation": rec,
        "blocked": blocked,
        "crash_risk": crash,
        "crash_risk_reason": str(p.get("crash_risk_reason") or "").strip(),
        "block_rules_hit": p.get("block_rules_hit") or [],
        "high_risk_paths": bool(p.get("high_risk_paths")),
    }


def collect_high_risk_patches(
    patch_list: List[Dict[str, Any]],
    *,
    limit: int = 15,
) -> List[Dict[str, Any]]:
    """Collect patches that genuinely need extra review, with human-readable reasons."""
    items: List[Dict[str, Any]] = []
    for p in patch_list:
        reason = patch_high_risk_reason(p)
        if not reason:
            continue
        items.append(_build_high_risk_item(p, reason))
    items.sort(key=lambda item: float(item.get("score") or 0))
    return items[:limit]


def _build_future_fix_item(p: Dict[str, Any]) -> Dict[str, Any]:
    """Structured entry for patches with known subsequent Fixes: commits."""
    fixes = p.get("fix_in_future") or []
    if not isinstance(fixes, list):
        fixes = []
    sha = str(p.get("sha") or p.get("commit") or "")[:12]
    intro_rich = p.get("problem_introducer_rich") or {}
    intro_summary = ""
    if isinstance(intro_rich, dict):
        intro_summary = str(intro_rich.get("summary") or "").strip()
    if not intro_summary:
        intro_summary = str(p.get("introducer_analysis") or p.get("introduced_risk") or "").strip()

    fix_tags: List[str] = []
    fix_shas: List[str] = []
    fix_subjects: List[str] = []
    for fix in fixes:
        if not isinstance(fix, dict):
            continue
        tag = str(fix.get("fix_tag") or "").strip()
        if tag and tag not in fix_tags:
            fix_tags.append(tag)
        fsha = str(fix.get("sha") or "").strip()
        if fsha:
            fix_shas.append(fsha[:12])
        subj = str(fix.get("subject") or fix.get("title") or "").strip()
        if subj:
            fix_subjects.append(subj[:80])

    return {
        "sha": sha,
        "title": str(p.get("title") or "")[:80],
        "score": p.get("score"),
        "dev_module": str(p.get("dev_module") or "").strip(),
        "fix_count": len(fixes),
        "fix_tags": fix_tags[:6],
        "fix_shas": fix_shas[:6],
        "fix_subjects": fix_subjects[:3],
        "introducer_summary": intro_summary[:220],
        "fixes": fixes[:8],
    }


def _unique_pool_patches(patch_by_sha: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """De-duplicate in-memory patch pool (full sha + short sha aliases)."""
    seen: Set[str] = set()
    out: List[Dict[str, Any]] = []
    for patch in patch_by_sha.values():
        if not isinstance(patch, dict):
            continue
        sid = (patch.get("commit") or patch.get("sha") or "").strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(patch)
    return out


def _parse_stored_future_fix_patches(task: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = task.get("future_fix_patches") or ""
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return []
    return data if isinstance(data, list) else []


def _persist_task_future_fix_snapshot(
    task_id: str,
    patch_by_sha: Dict[str, Dict[str, Any]],
    main_task_shas: Set[str],
    *,
    future_fixes: Optional[Dict[str, List[Dict[str, str]]]] = None,
) -> None:
    """Persist defect-scan Fixes summary on the task row (survives progress reset)."""
    pool = _unique_pool_patches(patch_by_sha)
    items = collect_future_fix_patches(pool, limit=50)
    pool_count = sum(1 for p in pool if p.get("fix_in_future"))
    if future_fixes and len(items) < len(future_fixes):
        seen_sha12 = {str(it.get("sha") or "")[:12] for it in items}
        for sha12, fixes in future_fixes.items():
            if sha12 in seen_sha12:
                continue
            patch = _resolve_patch_in_pool(patch_by_sha, sha12)
            if isinstance(patch, dict):
                merged = {**patch, "fix_in_future": fixes}
                items.append(_build_future_fix_item(merged))
            else:
                items.append({
                    "sha": sha12[:12],
                    "title": "",
                    "fix_count": len(fixes),
                    "fix_tags": [],
                    "fix_shas": [str(f.get("sha") or "")[:12] for f in fixes[:6]],
                    "fix_subjects": [
                        str(f.get("subject") or f.get("title") or "")[:80]
                        for f in fixes[:3]
                    ],
                    "introducer_summary": "",
                    "fixes": fixes[:8],
                })
            seen_sha12.add(sha12[:12])
        items.sort(key=lambda item: (-int(item.get("fix_count") or 0), float(item.get("score") or 0)))
        items = items[:50]
        pool_count = max(pool_count, len(future_fixes))
    task_count = 0
    for sid in main_task_shas:
        patch = _resolve_patch_in_pool(patch_by_sha, sid)
        if isinstance(patch, dict) and patch.get("fix_in_future"):
            task_count += 1
    if not pool_count and not items:
        return
    update_task(
        task_id,
        future_fix_pool_count=pool_count,
        future_fix_task_count=task_count,
        future_fix_patches=json.dumps(items, ensure_ascii=False) if items else "",
    )


def _enrich_patches_with_future_fix_snapshot(
    patch_list: List[Dict[str, Any]],
    task: Dict[str, Any],
) -> None:
    """Merge task-level future-fix snapshot into sampled patch rows for UI badges/detail."""
    stored = _parse_stored_future_fix_patches(task)
    if not stored:
        return
    by_sha12: Dict[str, Dict[str, Any]] = {}
    for item in stored:
        sha12 = str(item.get("sha") or "")[:12]
        if sha12:
            by_sha12[sha12] = item
    for patch in patch_list:
        sha12 = str(patch.get("sha") or patch.get("commit") or "")[:12]
        item = by_sha12.get(sha12)
        if not item:
            continue
        fixes = item.get("fixes") or []
        if fixes and not patch.get("fix_in_future"):
            patch["fix_in_future"] = fixes


def collect_future_fix_patches(
    patch_list: List[Dict[str, Any]],
    *,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """Collect patches that have subsequent Fixes: commits in later tags."""
    items: List[Dict[str, Any]] = []
    for p in patch_list:
        fixes = p.get("fix_in_future") or []
        if not fixes:
            continue
        items.append(_build_future_fix_item(p))
    items.sort(key=lambda item: (-int(item.get("fix_count") or 0), float(item.get("score") or 0)))
    return items[:limit]


def backfill_high_risk_patch_reason(
    patches: List[Dict[str, Any]],
    item: Dict[str, Any],
) -> Dict[str, Any]:
    """Ensure module/task high-risk entries always carry a concrete reason."""
    reason = str(item.get("reason") or item.get("risk") or "").strip()
    if reason and not is_key_risk_none(reason):
        item.setdefault("risk", reason)
        item.setdefault("reason", reason)
        return item

    sha = str(item.get("sha") or "").strip()
    match = None
    if sha:
        for p in patches:
            full_sha = str(p.get("sha") or p.get("commit") or "")
            if full_sha.startswith(sha) or full_sha[:12] == sha[:12]:
                match = p
                break

    if match:
        computed = patch_high_risk_reason(match)
        if computed:
            item["reason"] = computed
            item["risk"] = computed
            item.setdefault("score", match.get("score"))
            item.setdefault("recommendation", match.get("recommendation"))
            item.setdefault("blocked", match.get("blocked"))
            item.setdefault("crash_risk", match.get("crash_risk"))
            item.setdefault("key_risk", match.get("key_risk"))
            return item

    parts: List[str] = []
    if item.get("blocked"):
        parts.append("触发阻断")
    crash = str(item.get("crash_risk") or "").strip()
    if crash in ("高", "中"):
        parts.append(f"死机风险{crash}")
    score = item.get("score")
    if score is not None and score != "":
        parts.append(f"评分 {score}")
    rec = str(item.get("recommendation") or "").strip()
    if rec:
        parts.append(rec)
    fallback = " · ".join(parts) if parts else "需优先 review（详见单笔 patch 分析）"
    item["reason"] = fallback
    item["risk"] = fallback
    return item


def _build_fallback_summary_text(
    patch_list: List[Dict[str, Any]],
    *,
    avg_score: float,
    tag_counts: Dict[str, int],
    high_risk_list: List[Dict[str, Any]],
    blocked_count: int,
) -> str:
    """Build a concise script-based summary when LLM task summary is unavailable."""
    total = len(patch_list)
    lines = [f"共分析 {total} 笔 patch，平均分 {avg_score}。"]
    if blocked_count:
        lines.append(f"其中 {blocked_count} 笔被标记为阻断。")
    if tag_counts:
        top_tags = list(tag_counts.items())[:6]
        lines.append("标签分布：" + "、".join(f"{label}({count})" for label, count in top_tags))
    if high_risk_list:
        lines.append(f"高风险 patch {len(high_risk_list)} 笔，建议优先 review。")
        for item in high_risk_list[:3]:
            lines.append(f"- `{item.get('sha', '')}` {item.get('title', '')}：{item.get('risk', '')}")
    return "\n".join(lines)


def _build_task_result_summary(
    task: Dict[str, Any],
    patch_list: List[Dict[str, Any]],
    *,
    raw_patches: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build structured summary payload for API responses."""
    total = len(patch_list)
    llm_count = sum(1 for p in patch_list if p.get("llm_analyzed"))
    blocked_count = sum(1 for p in patch_list if p.get("blocked"))
    scores = [p.get("score", 0) or 0 for p in patch_list]
    avg_score = round(sum(scores) / total, 1) if total else 0.0

    tag_counts: Dict[str, int] = {}
    for p in patch_list:
        for t in (p.get("patch_tags") or []):
            if isinstance(t, dict):
                label = (t.get("label") or "").strip()
                if label:
                    tag_counts[label] = tag_counts.get(label, 0) + 1
            elif t:
                tag_counts[str(t)] = tag_counts.get(str(t), 0) + 1

    high_risk_list = collect_high_risk_patches(patch_list)

    live_future_fix = collect_future_fix_patches(patch_list)
    stored_future_fix = _parse_stored_future_fix_patches(task)
    if len(stored_future_fix) >= len(live_future_fix):
        future_fix_patches = stored_future_fix
    else:
        future_fix_patches = live_future_fix or stored_future_fix
    _prog = task.get("progress") if isinstance(task.get("progress"), dict) else {}
    future_fix_pool_count = (
        int(task.get("future_fix_pool_count") or 0)
        or int(_prog.get("defect_future_fix_pool") or 0)
        or max(len(stored_future_fix), len(live_future_fix))
    )
    future_fix_task_count = (
        int(task.get("future_fix_task_count") or 0)
        or len(live_future_fix)
    )

    TEST_FIELDS = [
        "unit_test", "integration_test", "regression_test",
        "manual_validation", "release_safeguard",
    ]
    all_test_suggestions: Dict[str, List[str]] = {f: [] for f in TEST_FIELDS}
    for p in patch_list:
        ts = p.get("test_suggestions", {}) or {}
        if isinstance(ts, dict):
            for field in TEST_FIELDS:
                val = ts.get(field, "")
                if val:
                    parts = [item.strip() for item in str(val).split("；") if item.strip()]
                    all_test_suggestions[field].extend(parts)

    summary_test: Dict[str, List[Dict[str, Any]]] = {}
    for field in TEST_FIELDS:
        items = all_test_suggestions.get(field, [])
        if items:
            counter = Counter(items)
            summary_test[field] = [
                {"text": text, "count": count}
                for text, count in counter.most_common(5)
            ]

    summary_text = task.get("summary") or ""
    if not isinstance(summary_text, str):
        summary_text = str(summary_text or "")
    test_summary_llm = task.get("test_summary_llm") or ""
    if not isinstance(test_summary_llm, str):
        test_summary_llm = str(test_summary_llm or "")
    squash_summary = task.get("squash_summary") or ""
    if not isinstance(squash_summary, str):
        squash_summary = str(squash_summary or "")

    if not summary_text.strip():
        summary_text = _build_fallback_summary_text(
            patch_list,
            avg_score=avg_score,
            tag_counts=tag_counts,
            high_risk_list=high_risk_list,
            blocked_count=blocked_count,
        )

    result: Dict[str, Any] = {
        "total": total,
        "llm_analyzed": llm_count,
        "script_analyzed": total - llm_count,
        "blocked": blocked_count,
        "avg_score": avg_score,
        "tag_counts": dict(sorted(tag_counts.items(), key=lambda x: -x[1])),
        "high_risk": high_risk_list[:15],
        "future_fix_patches": future_fix_patches,
        "future_fix_pool_count": future_fix_pool_count,
        "future_fix_task_count": future_fix_task_count,
        "text": summary_text,
        "test_suggestions": summary_test,
        "test_summary_llm": test_summary_llm,
        "squash_summary": squash_summary,
        "analysis_coverage": {},
    }

    _ms_raw = task.get("module_summaries", "") or ""
    if _ms_raw:
        try:
            ms_doc = json.loads(_ms_raw)
            if raw_patches is not None:
                from web_app.module_analysis_service import (
                    _parse_patch_data,
                    build_code_tree,
                    group_patches_by_module,
                )
                grouped = group_patches_by_module([_parse_patch_data(p) for p in raw_patches])
                for mod_name, mod in (ms_doc.get("modules") or {}).items():
                    mod_patches = grouped.get(mod_name) or []
                    if mod_patches:
                        mod["code_tree"] = build_code_tree(mod_patches)
            result["module_summaries"] = ms_doc
            result["analysis_coverage"] = {
                "module_count": ms_doc.get("module_count", 0),
                "total_patches": ms_doc.get("total_patches", total),
                "total_chunks": ms_doc.get("total_chunks", 0),
                "coverage_complete": ms_doc.get("coverage_complete", True),
            }
        except (json.JSONDecodeError, TypeError):
            result["module_summaries"] = {}

    return result


def _range_risk_sort_key(stats: Dict[str, Any]) -> Tuple[Any, ...]:
    risk = stats.get("risk_distribution") or {}
    return (
        int(risk.get("high", 0) or 0),
        int(risk.get("medium", 0) or 0),
        int(stats.get("has_future_fix_count", 0) or 0),
        int(risk.get("low", 0) or 0),
        int(stats.get("total_patches", 0) or 0),
        -float(stats.get("min_score", 0) or 0),
        -float(stats.get("avg_score", 0) or 0),
    )


def build_monthly_tag_recommendation(task_ids: List[str]) -> Dict[str, Any]:
    from web_app.database import get_range_comparison_stats, get_task

    if len(task_ids) == 1:
        task = get_task(task_ids[0]) or {}
        raw = task.get("monthly_subtag_results") or ""
        if raw:
            try:
                doc = json.loads(raw) if isinstance(raw, str) else dict(raw)
                if doc.get("embedded") and doc.get("intervals"):
                    from web_app.monthly_subtag_service import (
                        build_monthly_tag_recommendation_from_results,
                    )
                    return build_monthly_tag_recommendation_from_results(
                        doc.get("intervals") or [],
                    )
            except (json.JSONDecodeError, TypeError):
                pass

    stats = get_range_comparison_stats(task_ids)
    stats = [s for s in stats if int(s.get("total_patches") or 0) > 0]
    if not stats:
        return {"has_recommendation": False, "reason": "暂无可用于子 tag 分析的区间结果"}

    ranked = sorted(stats, key=_range_risk_sort_key)
    best = ranked[0]
    risk = best.get("risk_distribution") or {}
    target_tag = best.get("to_tag") or ""
    return {
        "has_recommendation": True,
        "recommended_tag": target_tag,
        "recommended_interval": {
            "from_tag": best.get("from_tag"),
            "to_tag": target_tag,
            "task_id": best.get("task_id"),
        },
        "reason": (
            f"子 tag 分析结论：优选 {target_tag}。"
            f"自 {best.get('from_tag') or 'r1'} 累计合入至该子 tag 时，"
            f"高风险 {risk.get('high', 0)} 个、中风险 {risk.get('medium', 0)} 个、"
            f"未来修复 {best.get('has_future_fix_count', 0)} 个，"
            f"平均分 {best.get('avg_score', 0)}，在当前月份子 tag 累计区间中综合风险最低。"
        ),
        "range_stats": ranked,
    }


def resolve_monthly_recommendation_for_task(
    task: Dict[str, Any],
    prog: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Restore monthly sub-tag recommendation from progress or persisted DB results."""
    # Same-month sub-tag ranges already cover the delta; never surface monthly UI.
    if is_same_month_subtag_range(
        str(task.get("from_tag") or ""),
        str(task.get("to_tag") or ""),
    ):
        return None

    prog = prog or {}
    monthly = prog.get("monthly_recommendation")
    if isinstance(monthly, dict) and (
        monthly.get("has_recommendation")
        or (monthly.get("range_stats") or [])
    ):
        return monthly

    raw = task.get("monthly_subtag_results") or ""
    if raw:
        try:
            doc = json.loads(raw) if isinstance(raw, str) else dict(raw)
            if doc.get("embedded") and doc.get("intervals"):
                from web_app.monthly_subtag_service import (
                    build_monthly_tag_recommendation_from_results,
                )
                rec = build_monthly_tag_recommendation_from_results(
                    doc.get("intervals") or [],
                )
                if rec.get("has_recommendation") or (rec.get("range_stats") or []):
                    return rec
        except (json.JSONDecodeError, TypeError):
            pass

    task_id = str(task.get("id") or "")
    if not task_id:
        return None

    try:
        rec = build_monthly_tag_recommendation([task_id])
    except Exception:
        return None

    if rec.get("has_recommendation") or (rec.get("range_stats") or []):
        return rec
    return None


def find_existing_range_task(
    from_tag: str,
    to_tag: str,
    repo_url: str = "",
) -> Optional[str]:
    """Find an existing completed task for a given tag range.
    Returns task_id if found, None otherwise.
    """
    count = _count_commits_between(from_tag, to_tag)
    if count == 0:
        return None

    if repo_url:
        to_parsed = _parse_month_subtag(to_tag)
        from_parsed = _parse_month_subtag(from_tag)
        if to_parsed:
            r_map, tag_commits = _build_month_subtag_map(to_parsed[0], repo_url)
            r_map = _dedupe_subtags_by_commit(r_map, tag_commits)
            if from_parsed and from_parsed[0] == to_parsed[0]:
                if from_parsed[1] not in r_map or to_parsed[1] not in r_map:
                    return None
            elif to_parsed[1] not in r_map:
                return None

    from web_app.database import list_tasks
    tasks = list_tasks(limit=200)
    for t in tasks:
        if (t.get("from_tag") == from_tag and t.get("to_tag") == to_tag
                and t.get("status") == "completed"):
            if int(t.get("total") or 0) <= 0:
                continue
            return t["id"]
    return None


# (compare functions removed - auto-extend integrated into range analysis)


def _flush_timing_records(task_id: str) -> None:
    """Flush buffered perf log lines for a task."""
    lines = _TIMING_BUFFERS.pop(task_id, [])
    if not lines:
        return
    _TIMING_DIR.mkdir(parents=True, exist_ok=True)
    start_time_str = _task_start_times.get(task_id, datetime.now().strftime("%Y%m%d_%H%M%S"))
    file_path = _TIMING_DIR / f"{start_time_str}.jsonl"
    try:
        with open(file_path, "a", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception:
        pass


def _log_timing_record(
    task_id: str,
    sha: str,
    phase: str,
    elapsed_ms: float,
    status: str = "success",
    **extra,
) -> None:
    """Append a structured timing record to the per-task JSONL file (buffered)."""
    record = {
        "ts": datetime.now().isoformat(),
        "task": task_id,
        "sha": sha,
        "phase": phase,
        "elapsed_ms": round(elapsed_ms, 1),
        "status": status,
    }
    if extra:
        for k, v in extra.items():
            if v is not None:
                record[k] = v
    buf = _TIMING_BUFFERS.setdefault(task_id, [])
    buf.append(json.dumps(record, ensure_ascii=False) + "\n")
    if len(buf) >= _TIMING_FLUSH_SIZE:
        _flush_timing_records(task_id)


def is_llm_running(task_id: str) -> bool:
    return _llm_in_progress.get(task_id, False)


def start_llm_analysis(task_id: str, force_reanalyze: bool = False) -> Tuple[bool, str]:
    """Start LLM deep analysis for all patches in a completed task.
    Returns (ok, error_message).
    """
    task = get_task(task_id)
    if not task:
        return False, "\u4efb\u52a1\u4e0d\u5b58\u5728"
    if task["status"] != "completed":
        return False, "\u4efb\u52a1\u5c1a\u672a\u5b8c\u6210\u811a\u672c\u5206\u6790"
    if _llm_in_progress.get(task_id):
        return False, "LLM \u5206\u6790\u5df2\u5728\u8fd0\u884c\u4e2d"

    _llm_in_progress[task_id] = True

    _set_progress(task_id, {
        "status": "llm_analyzing",
        "message": "LLM \u5206\u6790\u51c6\u5907\u4e2d...",
        "total": 0,
        "current": 0,
    })

    thread = threading.Thread(
        target=_run_llm_analysis,
        args=(task_id,),
        kwargs={"force_reanalyze": force_reanalyze},
        daemon=True,
    )
    thread.start()
    return True, ""


def _run_llm_analysis_on_patches(
    task_id: str,
    patch_rows: List[Dict[str, Any]],
    *,
    scoring_config: Optional[Dict[str, Any]] = None,
    force_reanalyze: bool = False,
    link_to_task: bool = True,
    link_shas: Optional[Set[str]] = None,
    llm_mode: str = "lightweight",
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run LLM analysis on an in-memory patch list. Optionally skip task_patches links."""
    import traceback
    from web_app.llm_service import (
        analyze_patch_via_llm,
        classify_low_risk_patch,
        get_llm_config,
        is_llm_configured,
        is_llm_analysis_result_effective,
        merge_llm_result,
        resolve_llm_concurrency,
        resolve_defect_scan_concurrency,
        resolve_patch_llm_analysis_mode,
    )

    if scoring_config is None:
        try:
            scoring_config = load_config(Path(DEFAULT_CONFIG))
        except Exception:
            scoring_config = {}
    _scfg = scoring_config

    if not is_llm_configured():
        raise RuntimeError("LLM 未配置：请设置 API Key")

    config = get_llm_config()
    _db_writer = PatchBatchWriter(batch_size=_DB_BATCH_SIZE)
    total = len(patch_rows)
    MAX_WORKERS = resolve_llm_concurrency(total)
    print(
        f"[LLM] 并发 {MAX_WORKERS} 路 / 共 {total} 笔 patch "
        f"(每 {os.environ.get('GKI_PATCHES_PER_WORKER', '10')} 笔 1 路)",
        flush=True,
    )
    _planned_minimal = sum(
        1 for row in patch_rows
        if classify_low_risk_patch(dict(row), _scfg)[0]
    )
    if _planned_minimal:
        print(
            f"[LLM] 分析深度：rule_minimal/免 LLM {_planned_minimal} 笔（低风险规则），"
            f"full {total - _planned_minimal} 笔",
            flush=True,
        )

    success = 0
    failed = 0
    last_error = ""
    failed_details: List[Dict[str, str]] = []
    pending: List[Tuple[str, Dict[str, Any]]] = []
    analyzed: List[Dict[str, Any]] = []
    skipped = 0
    minimal_count = 0
    full_depth_count = 0

    for row in patch_rows:
        sha = row.get("commit") or row.get("sha") or ""
        patch_data = dict(row)
        if (
            not force_reanalyze
            and patch_data.get("llm_analyzed")
            and float(patch_data.get("score", 0) or 0) > 0
        ):
            skipped += 1
            _llm_mod = patch_data.get("dev_module", "")
            patch_data["dev_module"] = _classify_dev_module(patch_data, llm_suggestion=_llm_mod)
            if not patch_data.get("score_details") or not patch_data.get("test_suggestions"):
                _enrich_llm_patch(patch_data, _scfg)
                patch_data["platform_tags"] = build_platform_tags(patch_data.get("files", []))
            _db_writer.upsert(patch_data)
            if link_to_task and sha and (link_shas is None or sha in link_shas):
                _db_writer.link(task_id, sha)
            analyzed.append(patch_data)
            success += 1
            continue
        pending.append((sha, patch_data))

    processed = success

    def _analyze_patch_with_retry(sha: str, pd: Dict[str, Any]) -> Tuple[Any, float, int, str]:
        """Call LLM for one patch; retry on API errors or empty score/interpretation."""
        last_exc: Optional[Exception] = None
        last_empty_result: Optional[Dict[str, Any]] = None
        patch_mode = resolve_patch_llm_analysis_mode(pd, llm_mode, _scfg)
        _, low_risk_reason = classify_low_risk_patch(pd, _scfg)
        exc_attempt = 0
        empty_attempt = 0

        while exc_attempt < _LLM_PATCH_MAX_ATTEMPTS:
            t0 = time.monotonic()
            try:
                result = analyze_patch_via_llm(
                    pd,
                    config,
                    mode=patch_mode,
                    scoring_config=_scfg,
                    low_risk_reason=low_risk_reason,
                )
                elapsed_ms = (time.monotonic() - t0) * 1000
                if is_llm_analysis_result_effective(result, patch_mode):
                    _log_timing_record(
                        task_id,
                        sha,
                        "llm_analyze",
                        elapsed_ms,
                        "success",
                        attempt=exc_attempt + empty_attempt + 1,
                        recovered=exc_attempt + empty_attempt > 0,
                        llm_mode=patch_mode,
                    )
                    return result, elapsed_ms / 1000.0, threading.get_ident(), patch_mode

                empty_attempt += 1
                last_empty_result = result if isinstance(result, dict) else {}
                will_retry_empty = empty_attempt <= _LLM_EMPTY_RESULT_MAX_RETRIES
                _log_timing_record(
                    task_id,
                    sha,
                    "llm_analyze",
                    elapsed_ms,
                    "empty",
                    attempt=empty_attempt,
                    max_attempts=_LLM_EMPTY_RESULT_MAX_RETRIES + 1,
                    will_retry=will_retry_empty,
                    llm_mode=patch_mode,
                )
                print(
                    f"[LLM RETRY] {sha[:12]} 无有效评分/解读 "
                    f"({empty_attempt}/{_LLM_EMPTY_RESULT_MAX_RETRIES + 1})",
                    flush=True,
                )
                if will_retry_empty:
                    time.sleep(min(2 ** (empty_attempt - 1), 8))
                    continue

                _log_timing_record(
                    task_id,
                    sha,
                    "llm_analyze",
                    elapsed_ms,
                    "success",
                    attempt=exc_attempt + empty_attempt,
                    recovered=True,
                    llm_mode=patch_mode,
                    empty_result=True,
                )
                return last_empty_result, elapsed_ms / 1000.0, threading.get_ident(), patch_mode
            except Exception as exc:
                last_exc = exc
                exc_attempt += 1
                elapsed_ms = (time.monotonic() - t0) * 1000
                will_retry = exc_attempt < _LLM_PATCH_MAX_ATTEMPTS
                _log_timing_record(
                    task_id,
                    sha,
                    "llm_analyze",
                    elapsed_ms,
                    "failed",
                    error=str(exc)[:500],
                    attempt=exc_attempt,
                    max_attempts=_LLM_PATCH_MAX_ATTEMPTS,
                    will_retry=will_retry,
                )
                print(
                    f"[LLM ERROR] {sha[:12]} attempt {exc_attempt}/{_LLM_PATCH_MAX_ATTEMPTS}: {exc}",
                    flush=True,
                )
                if will_retry:
                    time.sleep(min(2 ** (exc_attempt - 1), 8))
                else:
                    traceback.print_exc()
        assert last_exc is not None
        raise last_exc

    def _call_llm(sha: str, pd: Dict[str, Any]) -> Tuple[str, Any, float, int, str]:
        result, elapsed, tid, patch_mode = _analyze_patch_with_retry(sha, pd)
        return sha, result, elapsed, tid, patch_mode

    if pending:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_map = {
                executor.submit(_call_llm, sha, pd): (sha, pd)
                for sha, pd in pending
            }
            while future_map:
                if is_task_cancelled(task_id):
                    for f in future_map:
                        f.cancel()
                    break
                done, _ = wait(list(future_map.keys()), timeout=5, return_when=FIRST_COMPLETED)
                if not done:
                    if progress_cb:
                        progress_cb(processed, total, f"LLM 分析中… ({processed}/{total})")
                    continue
                for future in done:
                    sha, pd = future_map.pop(future, (None, None))
                    if not sha:
                        continue
                    processed += 1
                    try:
                        _, result, _api_elapsed, _tid, patch_mode = future.result(timeout=5)
                        merge_llm_result(pd, result)
                        if patch_mode in ("minimal", "rule_minimal"):
                            minimal_count += 1
                        else:
                            full_depth_count += 1
                        _llm_mod = pd.get("dev_module", "")
                        pd["dev_module"] = _classify_dev_module(pd, llm_suggestion=_llm_mod)
                        pd["platform_tags"] = build_platform_tags(pd.get("files", []))
                        _enrich_llm_patch(pd, _scfg)
                        _db_writer.upsert(pd)
                        if link_to_task and (link_shas is None or sha in link_shas):
                            _db_writer.link(task_id, sha)
                        analyzed.append(pd)
                        success += 1
                    except Exception as exc:
                        failed += 1
                        err_text = str(exc)
                        last_error = err_text
                        failed_details.append({
                            "sha": sha,
                            "error": err_text[:500],
                        })
                        print(
                            f"[LLM ERROR] {sha[:12]} exhausted after {_LLM_PATCH_MAX_ATTEMPTS} attempts: {exc}",
                            flush=True,
                        )
                    if progress_cb:
                        progress_cb(processed, total, f"LLM 分析中… ({processed}/{total}) {sha[:12]}")

    _db_writer.flush()
    if failed_details:
        _log_timing_record(
            task_id,
            "",
            "llm_failures",
            0,
            "failed",
            count=len(failed_details),
            failures=failed_details[:50],
        )
    info = {
        "success": success,
        "failed": failed,
        "new_analyzed": success - skipped,
        "reused_count": skipped,
        "failed_details": failed_details,
        "minimal_count": minimal_count,
        "full_depth_count": full_depth_count,
        "err_msg": (
            f"LLM: {success}成功/{failed}失败"
            + (f" | 最后错误: {last_error[:200]}" if last_error else "")
        ),
    }
    return analyzed, info


def _run_llm_analysis(task_id: str,
                       scoring_config: Optional[Dict[str, Any]] = None,
                       tracker: Optional['_ProgressTracker'] = None,
                       force_reanalyze: bool = False) -> Optional[Dict[str, Any]]:
    """Run LLM analysis on all patches of a task. Returns result info dict on success."""
    import traceback
    from web_app.llm_service import is_llm_configured

    _t0 = time.monotonic()

    def _llm_progress(status, total, current, message, **extra):
        data = {"status": status, "total": total, "current": current, "message": message, **extra}
        if tracker:
            ov_t, ov_c = tracker.update('llm_analyzing', total, current)
            data["overall_total"] = ov_t
            data["overall_current"] = ov_c
            data["phases"] = tracker.snapshot()
        _set_progress(task_id, data)

    try:
        if not is_llm_configured():
            raise RuntimeError("LLM 未配置：请设置 API Key")

        _task_meta = get_task(task_id) or {}
        _llm_mode = "full" if _task_meta.get("type") == "single" else "lightweight"
        if _llm_mode == "lightweight":
            print(f"[LLM] 区间任务使用轻量单笔分析（解读/闭环/引入/评分）", flush=True)

        rows = get_patches_by_task(task_id)
        patch_list: List[Dict[str, Any]] = []
        for row in rows:
            data_raw = row.get("data", "{}")
            try:
                patch_list.append(
                    json.loads(data_raw) if isinstance(data_raw, str) else dict(data_raw)
                )
            except (json.JSONDecodeError, TypeError):
                continue

        total = len(patch_list)
        _llm_progress(
            "llm_analyzing", total, 0,
            f"LLM 开始分析 {total} 笔 patch..."
            + ("（强制重新分析）" if force_reanalyze else ""),
        )

        def _progress_cb(current: int, t: int, msg: str) -> None:
            _llm_progress("llm_analyzing", t, current, msg)

        _llm_in_progress[task_id] = True
        _, info = _run_llm_analysis_on_patches(
            task_id,
            patch_list,
            scoring_config=scoring_config,
            force_reanalyze=force_reanalyze,
            link_to_task=True,
            llm_mode=_llm_mode,
            progress_cb=_progress_cb,
        )
        elapsed = time.monotonic() - _t0
        info["elapsed"] = elapsed
        _log_timing_record(
            task_id, "", "llm_summary",
            elapsed * 1000,
            success=info.get("success", 0),
            failed=info.get("failed", 0),
            skipped=info.get("reused_count", 0),
            failures=info.get("failed_details", [])[:50],
        )
        return info

    except Exception as exc:
        print(f"[LLM FATAL] {task_id}: {exc}", flush=True)
        traceback.print_exc()
        update_task(task_id, status="failed", error_msg=str(exc))
        _set_progress(task_id, {
            "status": "failed",
            "message": f"LLM 分析失败: {exc}",
        })
    finally:
        _flush_timing_records(task_id)
        _llm_in_progress[task_id] = False


def _load_task_patches_for_summary(task_id: str) -> List[Dict[str, Any]]:
    patches: List[Dict[str, Any]] = []
    for r in get_patches_by_task(task_id):
        data_raw = r.get("data", "{}")
        try:
            full = json.loads(data_raw) if isinstance(data_raw, str) else dict(data_raw)
        except (json.JSONDecodeError, TypeError):
            full = {}
        patches.append(full)
    return patches


def _resolve_squash_path_for_task(task: Dict[str, Any]) -> Path:
    from_tag = task.get("from_tag", "")
    to_tag = task.get("to_tag", "")
    if not from_tag or not to_tag:
        return Path()
    tag_from = from_tag.replace("/", "_").replace("\\", "_")
    tag_to = to_tag.replace("/", "_").replace("\\", "_")
    return Path(__file__).parent.parent / "outputs" / "merged_diffs" / f"{tag_from}_to_{tag_to}_squash.patch"


def _try_generate_unified_report(
    task_id: str,
    module_summaries_doc: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Generate unified analysis summary + test recommendations from module reports and patch results."""
    try:
        task = get_task(task_id)
        if not task:
            return {}
        patches = _load_task_patches_for_summary(task_id)
        if not patches:
            return {}

        if module_summaries_doc is None:
            raw = task.get("module_summaries") or ""
            if raw:
                try:
                    module_summaries_doc = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    module_summaries_doc = None

        from web_app.llm_service import generate_unified_task_report, is_llm_configured
        if not is_llm_configured():
            return {}

        squash_path = _resolve_squash_path_for_task(task)
        repo_dir = get_local_repo_dir()
        result = generate_unified_task_report(
            task,
            patches,
            squash_diff_path=str(squash_path) if squash_path.is_file() else "",
            repo_dir=str(repo_dir) if repo_dir else "",
            module_summaries_doc=module_summaries_doc,
        )
        return result or {}
    except Exception as exc:
        print(f"[UNIFIED REPORT] 生成综合报告异常: {exc}", flush=True)
        return {}


def _try_generate_summary_text(task_id: str) -> str:
    """Try to generate an LLM-based summary for a completed task.
    Returns the summary text, or empty string if not available.
    """
    try:
        task = get_task(task_id)
        if not task:
            return ""
        patches = _load_task_patches_for_summary(task_id)
        from web_app.llm_service import generate_task_summary
        result = generate_task_summary(task, patches)
        return result or ""
    except Exception as exc:
        print(f"[SUMMARY] 生成总结异常: {exc}", flush=True)
        return ""


def _try_generate_test_summary(task_id: str) -> str:
    """Try to generate an LLM-based test summary for a completed task.
    Returns the test summary text, or empty string if not available.
    """
    try:
        task = get_task(task_id)
        if not task:
            return ""
        patches = _load_task_patches_for_summary(task_id)
        from web_app.llm_service import generate_test_summary
        result = generate_test_summary(task, patches)
        return result or ""
    except Exception as exc:
        print(f"[TEST SUMMARY] 生成测试总结异常: {exc}", flush=True)
        return ""


def _apply_fallback_llm_summaries(task_id: str) -> Tuple[str, str]:
    """Fallback when unified report generation fails."""
    summary = _try_generate_summary_text(task_id)
    test_summary = _try_generate_test_summary(task_id)
    return summary, test_summary


def _run_summary_phase(
    task_id: str,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    *,
    phase_total: Optional[int] = None,
) -> None:
    """Generate unified analysis summary + test recommendations after patch analysis."""
    _summary_start = time.monotonic()
    _phase_total = phase_total or _estimate_summary_phase_total(task_id)

    def _heartbeat(current: int, message: str) -> None:
        if progress_cb:
            progress_cb(current, _phase_total, message)

    try:
        _task_meta = get_task(task_id) or {}
        _is_range_task = _task_meta.get("type") != "single"
        _report_box: Dict[str, str] = {"summary": "", "test_summary": ""}
        _module_box: Dict[str, Any] = {"data": {}}
        _module_done = 0

        if _is_range_task:
            try:
                from web_app.module_analysis_service import run_module_analysis_for_task

                def _module_progress(done: int, mod_total: int, msg: str) -> None:
                    nonlocal _module_done
                    _module_done = done
                    _heartbeat(done, msg)

                _heartbeat(0, "分模块分析中…")
                _module_box["data"] = run_module_analysis_for_task(
                    task_id, progress_cb=_module_progress,
                )
            except Exception as exc:
                print(f"[MODULE] 模块分析异常: {exc}", flush=True)

        _t_report = time.monotonic()
        _report_step = max(_module_done, _phase_total - 1)
        _heartbeat(_report_step, "结合模块报告与 Patch 分析，生成综合分析报告…")
        report = _try_generate_unified_report(
            task_id,
            module_summaries_doc=_module_box.get("data") or None,
        )
        if report:
            _report_box["summary"] = report.get("summary", "") or ""
            _report_box["test_summary"] = report.get("test_summary", "") or ""
        else:
            _heartbeat(_report_step, "综合报告生成失败，回退为 Patch 级总结…")
            summary, test_summary = _apply_fallback_llm_summaries(task_id)
            _report_box["summary"] = summary
            _report_box["test_summary"] = test_summary
        _heartbeat(_phase_total, "综合分析完成")
        _parallel_elapsed = time.monotonic() - _t_report
        print(f"[TIMING] 模块分析+综合报告: {_parallel_elapsed:.1f}s", flush=True)

        summary = _report_box["summary"]
        test_summary = _report_box["test_summary"]
        _log_timing_record(task_id, "", "unified_report", _parallel_elapsed * 1000)
        update_task(task_id, summary=summary, test_summary_llm=test_summary, squash_summary="")

        if _module_box.get("data"):
            _log_timing_record(
                task_id, "", "module_analysis",
                _parallel_elapsed * 500,
                module_count=_module_box["data"].get("module_count", 0),
            )
    finally:
        _actual = int(time.monotonic() - _summary_start)
        print(f"[TIMING] 总结阶段: {_actual}s", flush=True)
        _log_timing_record(task_id, "", "summary_phase_total", (time.monotonic() - _summary_start) * 1000)


def _run_diff_phase(task_id: str, repo: str, commits: List, from_tag: str, to_tag: str, repo_dir: Optional[Path] = None) -> None:
    """Generate merged diff."""
    _gen_start = time.monotonic()
    _generate_merged_diff(task_id, repo, commits, from_tag, to_tag, repo_dir=repo_dir)
    _actual = int(time.monotonic() - _gen_start)
    print(f"[TIMING] 合并diff生成: {_actual}s", flush=True)


def _generate_merged_diff(task_id: str, repo: str, commits: List, from_tag: str, to_tag: str, repo_dir: Optional[Path] = None) -> None:
    """Generate a merged .patch file. Prefer local git repo if available, else clone+format-patch, else HTTP."""
    from tools.patch_analyzer import run_git, normalize_repo_url

    diff_dir = Path(__file__).parent.parent / "outputs" / "merged_diffs"
    diff_dir.mkdir(parents=True, exist_ok=True)

    tag_from = from_tag.replace("/", "_").replace("\\", "_")
    tag_to = to_tag.replace("/", "_").replace("\\", "_")
    output_path = diff_dir / f"{tag_from}_to_{tag_to}.patch"
    total = len(commits)

    cached = load_interval_diff_cache(repo, from_tag, to_tag)
    if cached:
        update_task(task_id, diff_file=str(cached.diff_file))
        print(
            f"[DIFF] 复用已缓存区间 patch ({cached.source}): "
            f"{cached.diff_file.name}, {cached.commit_count} commits",
            flush=True,
        )
        return

    # ── 路径 1：本地仓库直接生成（最快） ──
    if repo_dir is not None:
        print(f"[DIFF] 使用本地仓库: {repo_dir}", flush=True)
        try:
            repo_path = Path(repo_dir)

            # 1a) 逐笔 patch（保留完整提交历史）
            patch_output = run_git(repo_path, [
                "format-patch", "--stdout", f"{from_tag}..{to_tag}",
            ])
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(patch_output)
            file_kb = output_path.stat().st_size / 1024
            commit_count = patch_output.count("From ")  # rough count
            print(f"[DIFF] 逐笔 format-patch: {commit_count} 笔, {file_kb:.0f}KB -> {output_path}", flush=True)

            # 1b) squash diff（合并为一个 diff，带函数上下文+重命名检测）
            squash_path = diff_dir / f"{tag_from}_to_{tag_to}_squash.patch"
            squash_output = run_git(repo_path, [
                "diff", "-W", "-M", f"{from_tag}..{to_tag}",
            ])
            # 加上 patch 头使其格式与 format-patch 一致
            with open(squash_path, "w", encoding="utf-8") as f:
                f.write(f"From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001\n")
                f.write(f"Subject: squash diff {from_tag}..{to_tag} ({commit_count} commits)\n\n")
                f.write(squash_output)
                f.write("\n")
            squash_kb = squash_path.stat().st_size / 1024
            print(f"[DIFF] squash diff: {squash_kb:.0f}KB -> {squash_path}", flush=True)

            _validate_squash_patch_report(
                task_id,
                repo_path,
                from_tag,
                to_tag,
                squash_path,
                expected_commit_count=commit_count,
            )

            save_interval_diff_cache(
                repo, from_tag, to_tag, output_path, squash_path, commit_count,
            )
            update_task(task_id, diff_file=str(output_path))
            return
        except Exception as exc:
            print(f"[DIFF] 本地 format-patch 失败 ({exc})，回退 HTTP…", flush=True)
            _generate_merged_diff_http(task_id, repo, commits, from_tag, to_tag, output_path, repo_dir=repo_dir)
            return

    # ── 路径 2：克隆 + format-patch ──
    repo_url = normalize_repo_url(repo)
    cache_dir = Path(__file__).parent.parent / "outputs" / "repo_cache"

    if not (cache_dir / ".git").exists():
        print(f"[DIFF] 首次浅克隆仓库 (depth={total*2})…", flush=True)
        import shutil
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        cache_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            run_git(cache_dir.parent, [
                "clone", f"--depth={total*2}",
                "--single-branch", "--no-tags",
                repo_url, str(cache_dir.name),
            ])
            # 显式拉取两个标签（使 format-patch 可用）
            run_git(cache_dir, ["fetch", "--depth", str(total*2), "origin",
                                 f"+refs/tags/{from_tag}:refs/tags/{from_tag}"])
            run_git(cache_dir, ["fetch", "--depth", str(total*2), "origin",
                                 f"+refs/tags/{to_tag}:refs/tags/{to_tag}"])
            print(f"[DIFF] 克隆完成", flush=True)
        except Exception as exc:
            print(f"[DIFF] 克隆失败 ({exc})，回退 HTTP…", flush=True)
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
            _generate_merged_diff_http(task_id, repo, commits, from_tag, to_tag, output_path)
            return

    # git format-patch
    try:
        patch_output = run_git(cache_dir, [
            "format-patch", "--stdout", f"{from_tag}..{to_tag}",
        ])
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(patch_output)
        file_kb = output_path.stat().st_size / 1024
        commit_count = patch_output.count("From ")  # rough count
        print(f"[DIFF] git format-patch 完成: {commit_count} 笔, {file_kb:.0f}KB -> {output_path}", flush=True)
        update_task(task_id, diff_file=str(output_path))
        return
    except Exception as exc:
        print(f"[DIFF] format-patch 失败 ({exc})，回退 HTTP…", flush=True)
        _generate_merged_diff_http(task_id, repo, commits, from_tag, to_tag, output_path)


def _generate_merged_diff_http(
    task_id: str, repo: str, commits: List, from_tag: str, to_tag: str,
    output_path: Path, repo_dir: Optional[Path] = None,
) -> None:
    """Fallback: generate merged diff via per-commit HTTP fetch."""
    from tools.patch_analyzer import fetch_diff_text

    total = len(commits)
    print(f"[DIFF][HTTP] 生成合并diff: {total} 笔patch", flush=True)

    # Phase 1: get diff from DB for already-fetched patches
    diffs: Dict[str, str] = {}
    remaining: List = []
    for c in commits:
        row = get_patch(c.sha)
        if row:
            data_raw = row.get("data", "{}")
            try:
                data = json.loads(data_raw) if isinstance(data_raw, str) else dict(data_raw or {})
                dt = data.get("diff_text", "")
                if dt:
                    diffs[c.sha] = dt
                    continue
            except json.JSONDecodeError:
                pass
        remaining.append(c)

    # Phase 2: parallel-fetch remaining from remote, with 429 retry
    if remaining:
        n_rem = len(remaining)
        print(f"[DIFF][HTTP] 需远程获取 {n_rem} 笔…", flush=True)
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import urllib.request

        def _fetch_with_retry(sha: str, max_retries: int = 5) -> str:
            """Wrapper with exponential backoff for 429."""
            import time as _time
            for attempt in range(max_retries):
                try:
                    return fetch_diff_text(repo, sha, repo_dir=repo_dir)
                except urllib.error.HTTPError as exc:
                    if exc.code == 429 and attempt + 1 < max_retries:
                        wait = 2 ** (attempt + 1)  # 2, 4, 8, 16, 32s
                        print(f"[DIFF][HTTP] 429限流 {sha[:12]}, 等待{wait}s重试 ({attempt+1}/{max_retries})", flush=True)
                        _time.sleep(wait)
                        continue
                    raise
                except Exception:
                    raise

        with ThreadPoolExecutor(max_workers=10) as executor:  # 降为10路减少限流
            fmap = {executor.submit(_fetch_with_retry, c.sha): c for c in remaining}
            for future in as_completed(fmap):
                c = fmap[future]
                try:
                    diffs[c.sha] = future.result(timeout=300)
                except Exception as exc:
                    print(f"[DIFF][HTTP] 获取 {c.sha[:12]} 失败: {exc}", flush=True)

    # Write combined file
    with open(output_path, "w", encoding="utf-8") as f:
        for c in commits:
            diff = diffs.get(c.sha, "")
            if not diff:
                continue
            subject = (c.message or "no subject").splitlines()[0]
            f.write(f"From {c.sha} Mon Sep 17 00:00:00 2001\n")
            f.write(f"Subject: {subject}\n\n")
            f.write(diff.strip())
            f.write("\n\n")

    actual = len(diffs)
    kb = output_path.stat().st_size / 1024
    print(f"[DIFF][HTTP] 合并diff已生成: {actual}/{total} 笔, {kb:.0f}KB -> {output_path}", flush=True)
    update_task(task_id, diff_file=str(output_path))


# ── Config path ────────────────────────────────────────
DEFAULT_CONFIG = str(Path(__file__).parent.parent / "config" / "scoring-config.yaml")

# ── In-memory progress state ──────────────────────────
_progress: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()
_ANALYSIS_LOG_LIMIT = 200


def get_progress(task_id: str) -> Dict[str, Any]:
    with _lock:
        return dict(_progress.get(task_id, {"status": "unknown", "message": ""}))


def _set_progress(task_id: str, data: Dict[str, Any]) -> None:
    with _lock:
        prev = _progress.get(task_id, {})
        log: List[Dict[str, str]] = list(prev.get("log") or data.get("log") or [])
        message = str(data.get("message") or "").strip()
        phase = str(data.get("status") or "")
        if message:
            if not (log and log[-1].get("msg") == message and log[-1].get("phase") == phase):
                log.append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "phase": phase,
                    "msg": message,
                })
                if len(log) > _ANALYSIS_LOG_LIMIT:
                    log = log[-_ANALYSIS_LOG_LIMIT:]
        data = {**data, "log": log}
        _progress[task_id] = data


def _clear_progress(task_id: str) -> None:
    with _lock:
        _progress.pop(task_id, None)


class _ProgressTracker:
    """完成数量驱动的进度追踪器，跟踪各阶段完成数并计算整体进度。"""
    def __init__(self):
        self._phases = []       # 注册顺序
        self._totals = {}       # phase -> total
        self._currents = {}     # phase -> current

    def register(self, phase: str, total: int):
        if phase not in self._totals:
            self._phases.append(phase)
        self._totals[phase] = total
        self._currents.setdefault(phase, 0)

    def set_phase_total(self, phase: str, total: int) -> None:
        """调整阶段总量（采集失败导致实际 patch 数少于采样数时使用）。"""
        total = max(0, total)
        if phase not in self._totals:
            self.register(phase, total)
            return
        self._totals[phase] = total
        cur = self._currents.get(phase, 0)
        if cur > total:
            self._currents[phase] = total

    def update(self, phase: str, total: int, current: int):
        self.register(phase, total)
        self._currents[phase] = current
        return self._compute()

    def finish(self, phase: str):
        if phase in self._totals:
            self._currents[phase] = self._totals[phase]

    def snapshot(self) -> List[Dict[str, Any]]:
        """返回各阶段 total/current，供前端精确恢复进度。"""
        out: List[Dict[str, Any]] = []
        for p in self._phases:
            t = self._totals.get(p, 0)
            c = self._currents.get(p, 0)
            out.append({"key": p, "total": t, "current": c, "done": t > 0 and c >= t})
        return out

    def _compute(self):
        total = sum(self._totals.values())
        current = sum(self._currents.get(p, 0) for p in self._phases)
        return total, min(current, total)


def _estimate_patch_phase_total(sample_size: int) -> int:
    """Placeholder per-patch phase total until commit list is fetched."""
    return sample_size if sample_size > 0 else 1


def _register_planned_phases(
    tracker: _ProgressTracker,
    *,
    is_single: bool,
    sample_size: int,
    repo_dir: Optional[Path],
    llm_configured: bool,
    auto_extend: int,
    include_monthly: bool = True,
) -> None:
    """Register all expected phases upfront so the UI can show the full pipeline immediately."""
    estimated = _estimate_patch_phase_total(sample_size)
    if not is_single:
        tracker.register("fetching", 1)
        tracker.register("format_patch", 3)
    tracker.register("collecting", estimated)
    if llm_configured:
        tracker.register("llm_analyzing", estimated)
    else:
        tracker.register("analyzing", estimated)
    if not is_single:
        tracker.register("summarizing", 2)
        if auto_extend > 0 and include_monthly:
            tracker.register("monthly_recommendation", 1)
    if repo_dir:
        tracker.register("defect_scan", estimated)


def _apply_sampled_phase_totals(
    tracker: _ProgressTracker,
    patch_count: int,
    *,
    llm_configured: bool,
) -> None:
    """Replace estimated per-patch totals once sampling is known."""
    tracker.set_phase_total("collecting", patch_count)
    if llm_configured:
        tracker.set_phase_total("llm_analyzing", patch_count)
    else:
        tracker.set_phase_total("analyzing", patch_count)
    if "defect_scan" in tracker._totals:
        tracker.set_phase_total("defect_scan", patch_count)


def _estimate_summary_phase_total(task_id: str) -> int:
    """分模块数 + 综合报告一步，供 summarizing 阶段进度条总量。"""
    task = get_task(task_id) or {}
    if task.get("type") == "single":
        return 1
    rows = get_task_patches(task_id)
    if not rows:
        return 1
    from web_app.module_analysis_service import group_patches_by_module

    patches = []
    for row in rows:
        data_raw = row.get("data", "{}")
        try:
            patches.append(json.loads(data_raw) if isinstance(data_raw, str) else dict(data_raw))
        except (json.JSONDecodeError, TypeError):
            continue
    module_count = len(group_patches_by_module(patches))
    return max(1, module_count + 1)


def _patch_reusable(row: Dict[str, Any], *, llm_configured: bool) -> bool:
    """Whether an existing DB row matches the current analysis mode and can be reused."""
    data_raw = row.get("data", "{}")
    try:
        data = json.loads(data_raw) if isinstance(data_raw, str) else (data_raw or {})
    except (json.JSONDecodeError, TypeError):
        data = {}
    score = float(row.get("score", 0) or data.get("score", 0) or 0)
    if llm_configured:
        return bool(data.get("llm_analyzed")) and score > 0
    return score > 0


def _validate_squash_patch_report(
    task_id: str,
    repo_dir: Optional[Path],
    from_tag: str,
    to_tag: str,
    squash_path: Path,
    *,
    expected_commit_count: Optional[int] = None,
    report_fn: Optional[Callable[..., None]] = None,
) -> Optional[SquashValidationResult]:
    """校验 squash patch 与 git diff 基准一致，并写入日志/进度。"""
    if not repo_dir or not squash_path.is_file():
        return None
    try:
        result = validate_squash_patch(
            Path(repo_dir),
            from_tag,
            to_tag,
            squash_path,
            expected_commit_count=expected_commit_count,
        )
    except Exception as exc:
        print(f"[SQUASH CHECK] 校验异常: {exc}", flush=True)
        return None

    status = "ok" if result.ok else "failed"
    icon = "✓" if result.ok else "✗"
    print(f"[SQUASH CHECK] {icon} {result.summary}", flush=True)
    for check in result.checks:
        mark = "OK" if check.passed else "FAIL"
        print(f"[SQUASH CHECK]   [{mark}] {check.name}: {check.detail}", flush=True)

    _log_timing_record(
        task_id,
        "",
        "squash_validate",
        0,
        status=status,
        ok=result.ok,
        summary=result.summary,
        checks=result.to_dict().get("checks"),
    )

    if report_fn:
        msg = f"squash 校验{('通过' if result.ok else '未通过')}: {result.summary}"
        report_fn("format_patch", 3, 3, msg)

    prog = get_progress(task_id)
    if prog.get("status") not in ("unknown", ""):
        _set_progress(task_id, {**prog, "squash_validation": result.to_dict()})

    return result


def _collect_one_commit_worker(
    commit: Any,
    *,
    repo: str,
    repo_dir: Optional[Path],
    parsed_patches: Dict[str, Dict[str, Any]],
    existing_row: Optional[Dict[str, Any]],
    llm_configured: bool,
) -> Dict[str, Any]:
    """Fetch or reuse one commit's raw patch data (worker thread; no DB writes)."""
    sha = commit.sha
    try:
        if existing_row and _patch_reusable(existing_row, llm_configured=llm_configured):
            data_raw = existing_row.get("data", "{}")
            if isinstance(data_raw, str):
                parsed = json.loads(data_raw)
            else:
                parsed = dict(data_raw) if data_raw else {}
            _llm_mod = parsed.get("dev_module", "")
            parsed["dev_module"] = _classify_dev_module(parsed, llm_suggestion=_llm_mod)
            return {
                "sha": sha,
                "patch": parsed,
                "reused": True,
                "fetch_elapsed_ms": 0.0,
                "error": None,
            }

        t0 = time.monotonic()
        if sha in parsed_patches:
            raw = dict(parsed_patches[sha])
        else:
            raw = fetch_patch_data(repo, commit, repo_dir=repo_dir)
        fetch_elapsed_ms = (time.monotonic() - t0) * 1000
        raw["llm_analyzed"] = False
        return {
            "sha": sha,
            "patch": raw,
            "reused": False,
            "fetch_elapsed_ms": fetch_elapsed_ms,
            "error": None,
        }
    except Exception as exc:
        return {
            "sha": sha,
            "patch": None,
            "reused": False,
            "fetch_elapsed_ms": 0.0,
            "error": str(exc),
        }


def _run_collecting_phase(
    task_id: str,
    collect_commits: List[Any],
    *,
    repo: str,
    repo_dir: Optional[Path],
    parsed_patches: Dict[str, Dict[str, Any]],
    main_task_shas: Set[str],
    llm_configured: bool,
    report_fn: Callable[..., None],
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], List[Dict[str, Any]], int, int, float]:
    """Concurrent patch collection with batched DB writes.

    Progress uses a monotonic completed counter (never commit index) so the UI
    bar advances smoothly without jumping backward when futures finish out of order.
    """
    from web_app.llm_service import resolve_collect_concurrency

    total = len(collect_commits)
    report_fn("collecting", total, 0, f"采集数据中… 0/{total}")

    if total == 0:
        return [], {}, [], 0, 0, 0.0

    existing_by_sha: Dict[str, Dict[str, Any]] = {}
    for row in get_patches_by_shas([c.sha for c in collect_commits]):
        sha = str(row.get("sha") or "").strip()
        if sha:
            existing_by_sha[sha] = row

    workers = resolve_collect_concurrency(total)
    print(
        f"[COLLECT] 并发 {workers} 路 / 共 {total} 笔 patch "
        f"(每 {os.environ.get('GKI_PATCHES_PER_WORKER', '10')} 笔 1 路)",
        flush=True,
    )

    collected: List[Dict[str, Any]] = []
    patch_by_sha: Dict[str, Dict[str, Any]] = {}
    failures: List[Dict[str, Any]] = []
    reuse_count = 0
    new_count = 0
    fetch_total_s = 0.0
    done_count = 0
    db_writer = PatchBatchWriter(batch_size=_DB_BATCH_SIZE)
    t_start = time.monotonic()

    def _apply_result(result: Dict[str, Any]) -> None:
        nonlocal done_count, reuse_count, new_count, fetch_total_s
        sha = result["sha"]
        err = result.get("error")
        if err:
            failures.append({"sha": sha, "error": err})
            _log_timing_record(task_id, sha, "fetch", 0, "failed", error=str(err)[:200])
        else:
            patch = result["patch"]
            if not patch:
                failures.append({"sha": sha, "error": "empty patch"})
                _log_timing_record(task_id, sha, "fetch", 0, "failed", error="empty patch")
            else:
                reused = bool(result.get("reused"))
                elapsed_ms = float(result.get("fetch_elapsed_ms") or 0)
                if reused:
                    reuse_count += 1
                    _log_timing_record(task_id, sha, "fetch", 0, "reused")
                else:
                    new_count += 1
                    fetch_total_s += elapsed_ms / 1000.0
                    if elapsed_ms > 5000:
                        print(
                            f"[TIMING] 采集耗时>5s: {sha[:12]} {elapsed_ms / 1000:.0f}s",
                            flush=True,
                        )
                    _log_timing_record(task_id, sha, "fetch", elapsed_ms)
                patch_by_sha[sha] = patch
                collected.append(patch)
                db_writer.upsert(patch)
                if sha in main_task_shas:
                    db_writer.link(task_id, sha)

        done_count += 1
        suffix = ""
        if err:
            suffix = f" 失败 {sha[:12]}"
        elif result.get("reused"):
            suffix = f" 复用 {sha[:12]}"
        else:
            suffix = f" {sha[:12]}"
        report_fn(
            "collecting",
            total,
            done_count,
            f"采集数据中… {done_count}/{total}{suffix}",
        )

    if workers <= 1:
        for commit in collect_commits:
            if is_task_cancelled(task_id):
                print("[CANCEL] 任务已取消，停止采集", flush=True)
                break
            _apply_result(
                _collect_one_commit_worker(
                    commit,
                    repo=repo,
                    repo_dir=repo_dir,
                    parsed_patches=parsed_patches,
                    existing_row=existing_by_sha.get(commit.sha),
                    llm_configured=llm_configured,
                )
            )
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map: Dict[Future, str] = {}
            for commit in collect_commits:
                if is_task_cancelled(task_id):
                    break
                fut = pool.submit(
                    _collect_one_commit_worker,
                    commit,
                    repo=repo,
                    repo_dir=repo_dir,
                    parsed_patches=parsed_patches,
                    existing_row=existing_by_sha.get(commit.sha),
                    llm_configured=llm_configured,
                )
                future_map[fut] = commit.sha

            while future_map:
                if is_task_cancelled(task_id):
                    for fut in future_map:
                        fut.cancel()
                    print("[CANCEL] 任务已取消，停止采集", flush=True)
                    break
                done, _ = wait(list(future_map.keys()), timeout=2, return_when=FIRST_COMPLETED)
                if not done:
                    report_fn(
                        "collecting",
                        total,
                        done_count,
                        f"采集数据中… {done_count}/{total}",
                    )
                    continue
                for fut in done:
                    sha = future_map.pop(fut, "")
                    try:
                        result = fut.result(timeout=5)
                    except Exception as exc:
                        result = {
                            "sha": sha or "?",
                            "patch": None,
                            "reused": False,
                            "fetch_elapsed_ms": 0.0,
                            "error": str(exc),
                        }
                    _apply_result(result)

    db_writer.flush()
    elapsed_s = time.monotonic() - t_start
    print(
        f"[TIMING] 采集阶段: {elapsed_s:.0f}s | 新采集{new_count}笔 | "
        f"复用{reuse_count}笔 | 失败{len(failures)}笔 | 采集耗时{fetch_total_s:.0f}s",
        flush=True,
    )
    _log_timing_record(
        task_id,
        "",
        "collecting_total",
        elapsed_s * 1000,
        new_count=new_count,
        reused=reuse_count,
        failed=len(failures),
        net_io_ms=round(fetch_total_s * 1000),
        workers=workers,
    )
    return collected, patch_by_sha, failures, reuse_count, new_count, fetch_total_s


# ── 为LLM分析结果补充评分明细和测试建议 ──────────────
DIM_LABELS = [
    ("correctness_completeness", "正确性与完整性"),
    ("risk_safety", "风险与安全性"),
    ("diff_maintainability", "Diff 可维护性"),
    ("commit_metadata_quality", "Commit/元信息质量"),
]


def _build_score_details(patch_data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Build score_details with per-dimension descriptive reasons from patch metadata."""
    overall = patch_data.get("score", 0)
    dims = config.get("dimensions", [])
    details: Dict[str, Any] = {}
    if overall == 0:
        default_reason = "LLM 未返回有效评分，展示默认 0 分"
        for dim in dims:
            dim_id = dim.get("id", "")
            weight = dim.get("weight", 0)
            if weight == 0:
                continue
            details[dim_id] = {
                "score": 0,
                "weight": weight,
                "weighted_score": 0,
                "reason": default_reason,
            }
        return details

    # 从 patch 元数据生成有意义的维度总结
    message = patch_data.get("title", "")
    files = patch_data.get("files", []) or []
    file_count = len(files)
    churn = patch_data.get("churn") or 0
    diff = patch_data.get("diff", "") or ""
    high_risk = detect_high_risk_paths(files)
    has_test = detect_test_signal(diff, files)
    dim_reasons = build_dimension_reasons(message, file_count, churn, has_test, high_risk)

    for dim in dims:
        dim_id = dim.get("id", "")
        weight = dim.get("weight", 0)
        if weight == 0:
            continue
        weighted_score = round(overall * weight, 2)
        reason = dim_reasons.get(dim_id, "LLM 综合评定")
        details[dim_id] = {
            "score": overall,
            "weight": weight,
            "weighted_score": weighted_score,
            "reason": reason,
        }
    return details


def _build_test_suggestions_from_config(patch_data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, str]:
    """Build test_suggestions dict using config defaults and patch data."""
    files = patch_data.get("files", [])
    high_risk_paths = patch_data.get("high_risk_paths", False)
    test_signal = patch_data.get("test_signal", False)
    churn = patch_data.get("churn", 0)
    patch_tags = patch_data.get("patch_tags", [])
    platform_tags = patch_data.get("platform_tags", [])
    _, profile = choose_profile(config, files)
    result = build_test_suggestions(
        files=files,
        high_risk_paths=high_risk_paths,
        test_signal=test_signal,
        churn=churn,
        config=config,
        profile=profile,
        patch_tags=patch_tags,
        platform_tags=platform_tags,
    )
    return _dict_list_to_str(result)


def _dict_list_to_str(d: Dict[str, Any]) -> Dict[str, str]:
    """Convert dict-of-lists to dict-of-strings (join lists)."""
    return {k: "\n".join(v) if isinstance(v, list) else str(v) for k, v in d.items()}


def _enrich_llm_patch(patch_data: Dict[str, Any], config: Dict[str, Any]) -> None:
    """After LLM merge, fill score_details and test_suggestions for consistent display."""
    if not patch_data.get("score_details"):
        patch_data["score_details"] = _build_score_details(patch_data, config)
    if not patch_data.get("test_suggestions"):
        patch_data["test_suggestions"] = _build_test_suggestions_from_config(patch_data, config)


def _backfill_script_score(
    patch_data: Dict[str, Any],
    config: Dict[str, Any],
    repo: str,
) -> bool:
    """Fill script score for patches that have LLM text but score=0 (lightweight mode)."""
    if float(patch_data.get("score", 0) or 0) > 0:
        return False
    try:
        scripted = analyze_patch_data(patch_data, config, repo, repo_dir=None)
    except Exception as exc:
        print(f"[SCRIPT] 补算评分失败 {str(patch_data.get('sha', ''))[:12]}: {exc}", flush=True)
        return False
    for key in (
        "score", "recommendation", "key_risk", "blocked", "block_rules_hit",
        "score_details", "test_suggestions", "patch_tags", "platform_tags",
        "problem_solved", "change_summary", "commit_interpretation",
        "code_change_analysis", "diff_preview",
    ):
        if key in scripted:
            patch_data[key] = scripted[key]
    return True


def _run_script_analysis_phase(
    task_id: str,
    collected: List[Dict[str, Any]],
    config: Dict[str, Any],
    repo: str,
    report_fn,
    failures: List[Dict[str, Any]],
    *,
    preserve_llm_fields: bool = False,
) -> List[Dict[str, Any]]:
    """Run patch_analyzer scoring. Patches with score > 0 are kept as-is."""
    patches: List[Dict[str, Any]] = []
    total = len(collected)
    _t2_start = time.monotonic()

    for i, raw in enumerate(collected):
        if is_task_cancelled(task_id):
            print(f"[CANCEL] 任务已取消，停止脚本分析", flush=True)
            break
        sha = raw.get("sha") or raw.get("commit", "") or "?"
        if float(raw.get("score", 0) or 0) > 0:
            if preserve_llm_fields:
                _enrich_llm_patch(raw, config)
            elif not raw.get("test_suggestions"):
                raw["test_suggestions"] = _build_test_suggestions_from_config(raw, config)
            patches.append(raw)
            report_fn(
                'analyzing', total, i + 1,
                f'脚本分析中… {i + 1}/{total} (已有评分: {str(sha)[:12]})',
            )
            continue
        try:
            _t_script = time.monotonic()
            result = analyze_patch_data(raw, config, repo, repo_dir=None)
            _s_elapsed = (time.monotonic() - _t_script) * 1000
            if preserve_llm_fields:
                result["llm_analyzed"] = raw.get("llm_analyzed", False)
                for key in (
                    "commit_interpretation_rich", "code_change_analysis_rich",
                    "problem_closure_rich", "problem_introducer_rich",
                    "llm_test_suggestions", "introduced_risk", "crash_risk",
                    "crash_risk_reason", "llm_usage", "dev_module",
                ):
                    if raw.get(key) not in (None, "", [], {}):
                        result[key] = raw[key]
            else:
                result["llm_analyzed"] = False
            result["dev_module"] = _classify_dev_module(
                result, llm_suggestion=raw.get("dev_module", ""),
            )
            patches.append(result)
            upsert_patch(result)
            link_task_patch(task_id, sha)
            _log_timing_record(task_id, sha, "script_analyze", _s_elapsed)
        except Exception as exc:
            failures.append({"sha": sha, "error": str(exc)})
            _log_timing_record(task_id, sha, "script_analyze", 0, "failed", error=str(exc)[:200])

        report_fn(
            'analyzing', total, i + 1,
            f'脚本分析中… {i + 1}/{total}  {str(sha)[:12]}',
        )

    _t2_elapsed = time.monotonic() - _t2_start
    print(
        f"[TIMING] 脚本阶段: {_t2_elapsed:.0f}s | {len(patches)}笔成功 | {len(failures)}笔失败",
        flush=True,
    )
    _log_timing_record(
        task_id, "", "script_summary",
        _t2_elapsed * 1000,
        success=len(patches),
        failed=len(failures),
    )
    return patches


def _run_script_analysis_on_patches(
    collected: List[Dict[str, Any]],
    config: Dict[str, Any],
    repo: str,
    failures: List[Dict[str, Any]],
    *,
    link_to_task: bool = True,
    link_shas: Optional[Set[str]] = None,
    task_id: str = "",
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
) -> List[Dict[str, Any]]:
    """脚本评分（与 LLM 互斥）；可选不写 task_patches 关联。"""
    patches: List[Dict[str, Any]] = []
    total = len(collected)
    processed = 0
    for raw in collected:
        sha = raw.get("sha") or raw.get("commit", "") or "?"
        if float(raw.get("score", 0) or 0) > 0:
            if not raw.get("test_suggestions"):
                raw["test_suggestions"] = _build_test_suggestions_from_config(raw, config)
            patches.append(raw)
            processed += 1
            if progress_cb:
                progress_cb(
                    processed, total,
                    f"脚本分析中… {processed}/{total}  {str(sha)[:12]} (复用)",
                )
            continue
        try:
            result = analyze_patch_data(raw, config, repo, repo_dir=None)
            result["llm_analyzed"] = False
            result["dev_module"] = _classify_dev_module(
                result, llm_suggestion=raw.get("dev_module", ""),
            )
            patches.append(result)
            upsert_patch(result)
            if link_to_task and task_id and (link_shas is None or sha in link_shas):
                link_task_patch(task_id, sha)
        except Exception as exc:
            failures.append({"sha": sha, "error": str(exc)})
        processed += 1
        if progress_cb:
            progress_cb(
                processed, total,
                f"脚本分析中… {processed}/{total}  {str(sha)[:12]}",
            )
    return patches


def _launch_monthly_subtag_tasks(
    parent_task_id: str,
    intervals: List[Tuple[str, str]],
    *,
    main_from_tag: str,
    main_to_tag: str,
    repo: str,
    config_path: str,
    force_reanalyze: bool,
) -> Tuple[List[str], List[Dict[str, str]]]:
    """Start or reuse child range tasks for monthly sub-tag intervals."""
    extend_ids: List[str] = []
    interval_tasks: List[Dict[str, str]] = []
    for sub_from, sub_to in intervals:
        if sub_from == main_from_tag and sub_to == main_to_tag:
            sub_id = parent_task_id
        else:
            existing = find_existing_range_task(sub_from, sub_to, repo_url=repo)
            if existing:
                sub_id = existing
            else:
                sub_id, _ = start_analysis(
                    "range",
                    repo,
                    config_path,
                    from_tag=sub_from,
                    to_tag=sub_to,
                    sample_size=0,
                    force_reanalyze=force_reanalyze,
                    auto_extend=0,
                )
        extend_ids.append(sub_id)
        interval_tasks.append({"from_tag": sub_from, "to_tag": sub_to, "task_id": sub_id})
    return extend_ids, interval_tasks


def _count_monthly_subtask_progress(
    extend_ids: List[str],
    parent_task_id: str,
    *,
    count_parent_complete: bool = False,
) -> Tuple[int, int]:
    """Return (completed, failed) counts for monthly sub-tag child tasks."""
    completed = 0
    failed = 0
    for sub_id in extend_ids:
        if sub_id == parent_task_id:
            if count_parent_complete:
                completed += 1
            continue
        sub_task = get_task(sub_id) or {}
        st = sub_task.get("status") or get_progress(sub_id).get("status")
        if st == "completed":
            completed += 1
        elif st == "failed":
            failed += 1
    return completed, failed


# ── Background runner ──────────────────────────────────

def start_analysis(
    task_type: str,
    repo: str,
    config_path: str = DEFAULT_CONFIG,
    from_tag: str = "",
    to_tag: str = "",
    sample_size: int = 100,
    sha: str = "",
    force_reanalyze: bool = False,
    auto_extend: int = 0,
) -> Tuple[str, Optional[str]]:
    """Create a task record and launch analysis in a background thread.
    Returns (task_id, error_message_if_immediately_failed).
    """
    task_id = uuid.uuid4().hex[:12]
    create_task(task_id, task_type, repo, from_tag, to_tag, sample_size)

    _set_progress(task_id, {
        "status": "pending",
        "message": "任务已创建，等待启动...",
        "total": 0,
        "current": 0,
    })

    thread = threading.Thread(
        target=_run_analysis,
        args=(task_id, repo, config_path, from_tag, to_tag, sample_size, sha),
        kwargs={"force_reanalyze": force_reanalyze,
                "auto_extend": auto_extend,
                "task_type": task_type},
        daemon=True,
    )
    thread.start()
    return task_id, None


import re

_UPSTREAM_SHA_RE = re.compile(
    r'(?:'
    r'\[\s*Upstream commit\s+([0-9a-f]{12,40})\s*\]'          # [ Upstream commit SHA ]
    r'|\(cherry picked from commit\s+([0-9a-f]{12,40})'          # (cherry picked from commit SHA
    r'|Upstream-Commit:\s*([0-9a-f]{12,40})'                   # Upstream-Commit: SHA
    r'|\bcommit\s+([0-9a-f]{12,40})\s+upstream\b'              # commit SHA upstream
    r')',
    re.IGNORECASE
)


def _extract_upstream_sha(patch_data: Dict[str, Any]) -> str:
    """Extract upstream (community) SHA from commit message, if present."""
    msg = patch_data.get("commit_message_full", "")
    if not msg:
        return ""
    m = _UPSTREAM_SHA_RE.search(msg)
    if m:
        # Return first non-None group
        for g in m.groups():
            if g:
                return g[:12]
    return ""


def _scan_future_fixes(repo_dir, patches: List[Dict[str, Any]], to_tag: str = "") -> Dict[str, List[Dict[str, str]]]:
    """Search for Fixes: commits referencing patches in our set.

    Matches both Google (cherry-pick) SHA and upstream community SHA.
    If to_tag is provided, searches only after that tag. Otherwise searches all branches.
    Returns dict mapping google_sha12 -> list of fix commit info dicts.
    """
    from tools.patch_analyzer import run_git
    _t_scan_start = time.monotonic()
    results: Dict[str, List[Dict[str, str]]] = {}

    # Build lookup: sha12 -> patch, plus upstream_sha -> google_sha mapping
    google_sha_set = set()
    upstream_to_google: Dict[str, str] = {}  # upstream_sha12 -> google_sha12
    for p in patches:
        sha = p.get("sha", p.get("commit", ""))[:12]
        if sha:
            google_sha_set.add(sha)
        # Extract upstream SHA from commit message
        upstream = _extract_upstream_sha(p)
        if upstream:
            upstream_to_google[upstream] = sha
            # Also store upstream SHA in patch_data for display
            p["upstream_sha"] = upstream

    # All SHAs to search for (both Google and upstream)
    # alias_to_google maps any known alias (upstream / sibling-cherry-pick) back to original google sha
    alias_to_google: Dict[str, str] = dict(upstream_to_google)
    alias_to_google.update({s: s for s in google_sha_set})

    # ── Subject-based sibling discovery (hybrid mode) ──
    # Small batches (<=10): per-patch git grep (~30s each, total ~5min)
    # Large batches (>10): single git log dump all subjects (~4min, regardless of count)
    _sibling_count = 0
    _subjects = set()
    for p in patches:
        _subj = p.get("title", "").strip()
        if _subj and len(_subj) >= 10:
            _subjects.add(_subj)
    _BATCH_THRESHOLD = 10
    if _subjects:
        try:
            _t_sib = time.monotonic()
            if len(_subjects) <= _BATCH_THRESHOLD:
                # Per-patch grep mode
                for _subj in _subjects:
                    try:
                        _sib_out = run_git(repo_dir, ["log", "--tags", "--format=%H|%s",
                                                      f"--grep={_subj}", "-F", "--fixed-strings"])
                    except Exception:
                        continue
                    for _sib_line in _sib_out.strip().split("\n"):
                        if "|" not in _sib_line:
                            continue
                        _sha, _sj = _sib_line.split("|", 1)
                        _sha12 = _sha.strip()[:12]
                        if _sj.strip() == _subj and _sha12 not in alias_to_google:
                            # Find original google sha for this subject
                            _orig = next((p.get("sha", p.get("commit", ""))[:12] for p in patches
                                         if p.get("title", "").strip() == _subj), "")
                            if _orig and _sha12 != _orig:
                                alias_to_google[_sha12] = _orig
                                _sibling_count += 1
            else:
                # Batch mode: single git log dump (use --tags to limit scope)
                _repo_key = str(repo_dir)
                _all_log = _TAG_SUBJECT_LOG_CACHE.get(_repo_key)
                if _all_log is None:
                    _all_log = run_git(repo_dir, ["log", "--tags", "--format=%H|%s"], timeout=300)
                    _TAG_SUBJECT_LOG_CACHE[_repo_key] = _all_log
                else:
                    print(f"[DEFECT SCAN] 兄弟发现 git log 命中缓存", flush=True)
                _subject_index: Dict[str, set] = {}
                for _line in _all_log.split("\n"):
                    if "|" in _line:
                        _sha, _sj = _line.split("|", 1)
                        _sj = _sj.strip()
                        if _sj in _subjects:
                            _subject_index.setdefault(_sj, set()).add(_sha.strip()[:12])
                for p in patches:
                    _subj = p.get("title", "").strip()
                    _google_sha = p.get("sha", p.get("commit", ""))[:12]
                    for _sib_sha12 in _subject_index.get(_subj, set()):
                        if _sib_sha12 != _google_sha and _sib_sha12 not in alias_to_google:
                            alias_to_google[_sib_sha12] = _google_sha
                            _sibling_count += 1
            print(f"[DEFECT SCAN] 兄弟发现({'per-patch' if len(_subjects) <= _BATCH_THRESHOLD else 'batch'}): "
                  f"新增 {_sibling_count} 个别名SHA | {time.monotonic()-_t_sib:.1f}s", flush=True)
        except Exception as _exc:
            print(f"[DEFECT SCAN] 兄弟发现失败: {_exc}", flush=True)
    if _sibling_count:
        print(f"[DEFECT SCAN] 同subject兄弟发现: 新增 {_sibling_count} 个别名SHA", flush=True)

    all_search_shas = set(alias_to_google.keys())
    if not all_search_shas:
        return results
    print(f"[DEFECT SCAN] 准备阶段完成: {len(all_search_shas)} 个搜索SHA | "
          f"{time.monotonic()-_t_scan_start:.1f}s", flush=True)

    # Use full commit message (%B) because Fixes: tag is in the body, not the subject
    # Include subject (%s) for cherry-pick deduplication
    try:
        _fixes_cache_key = (str(repo_dir), to_tag or "")
        output = _FIXES_LOG_CACHE.get(_fixes_cache_key)
        if output is None:
            git_args = ["log", "--tags", "--format=###COMMIT###%H%n%s%n%B", "--grep=Fixes:"]
            if to_tag:
                git_args.insert(2, f"{to_tag}..")
            output = run_git(repo_dir, git_args, timeout=300)
            _FIXES_LOG_CACHE[_fixes_cache_key] = output
        else:
            print(f"[DEFECT SCAN] Fixes: git log 命中缓存", flush=True)
    except Exception as exc:
        print(f"[DEFECT SCAN] git log 失败: {exc}", flush=True)
        return results

    if not output or not output.strip():
        return results

    # Parse inline - match Fixes: lines as we go, without storing all bodies
    fix_count = 0
    cur_sha = ""
    cur_subject = ""
    _line_idx_after_commit = 0
    for line in output.split("\n"):
        if line.startswith("###COMMIT###"):
            cur_sha = line[12:].strip()
            cur_subject = ""
            _line_idx_after_commit = 0
        else:
            _line_idx_after_commit += 1
            if _line_idx_after_commit == 1:
                cur_subject = line.strip()
        if "Fixes:" in line and cur_sha:
            # Check if any of our SHAs appear in this Fixes: line
            for matched_sha in all_search_shas:
                if matched_sha in line:
                    fix_sha12 = cur_sha[:12]
                    google_sha = alias_to_google.get(matched_sha, matched_sha)
                    is_alias = matched_sha != google_sha
                    if google_sha not in results:
                        results[google_sha] = []
                    results[google_sha].append({
                        "sha": fix_sha12,
                        "subject": cur_subject,
                        "title": line.strip(),
                        "matched_via": "sibling" if is_alias else "direct",
                        "upstream_sha": matched_sha if is_alias else "",
                    })
                    fix_count += 1

    print(f"[DEFECT SCAN] Fixes: 扫描完成 | 匹配到 {fix_count} 条引用 | "
          f"{time.monotonic()-_t_scan_start:.1f}s", flush=True)

    # ── Resolve which subsequent tag each fix commit belongs to ──
    # Only search same-series tags (fast); skip cross-series to avoid long hangs
    if results and to_tag:
        try:
            _fix_shas = set()
            for fix_list in results.values():
                for f in fix_list:
                    _fix_shas.add(f["sha"])
            if _fix_shas:
                _fix_to_tag: Dict[str, str] = {}  # fix_sha12 -> first tag
                _checked_up_to = to_tag
                _total_subseq = []
                _batch = 10
                while len(_fix_to_tag) < len(_fix_shas):
                    _subseq = find_subsequent_tags(_checked_up_to, count=_batch)
                    if not _subseq:
                        break
                    _total_subseq.extend(_subseq)
                    for _stag in _subseq:
                        try:
                            _log_out = run_git(repo_dir, ["log", "--format=%H", f"{_checked_up_to}..{_stag}"])
                            for _lsha in _log_out.strip().split("\n"):
                                _ls12 = _lsha.strip()[:12]
                                if _ls12 in _fix_shas and _ls12 not in _fix_to_tag:
                                    _fix_to_tag[_ls12] = _stag
                        except Exception:
                            pass
                        _checked_up_to = _stag
                        if len(_fix_to_tag) >= len(_fix_shas):
                            break
                    if len(_subseq) < _batch:
                        break

                # Assign tag to results (found → tag name, not found → empty)
                _found_count = 0
                for fix_list in results.values():
                    for f in fix_list:
                        f["fix_tag"] = _fix_to_tag.get(f["sha"], "")
                        if f["fix_tag"]:
                            _found_count += 1
                print(f"[DEFECT SCAN] 修复 Tag 解析: {_found_count}/{len(_fix_shas)} 笔找到tag "
                      f"(同系列检查 {_total_subseq if _total_subseq else 0} 个tag)", flush=True)
        except Exception as _tag_exc:
            print(f"[DEFECT SCAN] 修复 Tag 解析失败: {_tag_exc}", flush=True)

    # ── Deduplicate fixes: subject + file-set ──
    # Level 1: Same subject = cherry-pick (same commit title)
    # Level 2: Same file-set = same code change (rewritten/独立修复)
    # Prioritize tags from the same series as to_tag
    import re as _re
    _to_prefix = ""  # full series prefix: android14-6.1-
    _to_android = ""  # android version prefix: android14-
    if to_tag:
        _m = _re.match(r'(android\d+-\d+\.\d+[-.])', to_tag)
        if _m:
            _to_prefix = _m.group(1)
        _m2 = _re.match(r'(android\d+-)', to_tag)
        if _m2:
            _to_android = _m2.group(1)

    def _tag_sort_key(t):
        if _to_prefix and t.lstrip('>').startswith(_to_prefix):
            return (0, t)
        elif _to_android and t.lstrip('>').startswith(_to_android):
            return (1, t)
        else:
            return (2, t)

    def _dedup_tags(tags: list) -> list:
        """Remove redundant '>tag' when exact 'tag' also exists."""
        exact = {t for t in tags if not t.startswith('>')}
        result = []
        for t in tags:
            if t.startswith('>'):
                # Skip if exact version already present
                if t[1:] in exact:
                    continue
            result.append(t)
        return result

    if results:
        # Collect all unique fix SHAs for file-set lookup
        _all_fix_shas = set()
        for fix_list in results.values():
            for f in fix_list:
                _all_fix_shas.add(f["sha"])

        # Batch get file-set for each fix commit
        _fix_files: Dict[str, frozenset] = {}  # sha12 -> frozenset of files
        if _all_fix_shas and repo_dir:
            try:
                _sha_list = list(_all_fix_shas)
                # Use git diff-tree in batch: one call per commit
                for _fsha in _sha_list:
                    try:
                        _dt_out = run_git(repo_dir, ["diff-tree", "--no-commit-id",
                                                     "--name-only", "-r", _fsha])
                        _files = set(l.strip() for l in _dt_out.strip().split("\n") if l.strip())
                        _fix_files[_fsha] = frozenset(_files)
                    except Exception:
                        pass
            except Exception as _exc:
                print(f"[DEFECT SCAN] 修复文件集解析失败: {_exc}", flush=True)

        for google_sha, fix_list in results.items():
            # Level 1: Group by subject
            by_subject: Dict[str, List[Dict]] = {}
            for f in fix_list:
                subj = f.get("subject", "")
                if subj:
                    by_subject.setdefault(subj, []).append(f)
                else:
                    by_subject.setdefault(f"__sha_{f['sha']}", []).append(f)

            # Merge subject groups into intermediate entries
            subject_groups = []
            for subj, group in by_subject.items():
                base = dict(group[0])
                all_tags = []
                all_shas = set()
                for f in group:
                    all_shas.add(f["sha"])
                    tag = f.get("fix_tag", "")
                    if tag and tag not in all_tags:
                        all_tags.append(tag)
                all_tags.sort(key=_tag_sort_key)
                all_tags = _dedup_tags(all_tags)
                base["fix_tag"] = all_tags[0] if all_tags else ""
                base["fix_tags"] = all_tags
                base["cherry_pick_count"] = len(all_shas)
                base["cherry_pick_shas"] = list(all_shas)
                base["_file_set"] = _fix_files.get(base["sha"], frozenset())
                subject_groups.append(base)

            # Level 2: Compare actual diff between groups with overlapping files
            # If git diff fix1 fix2 is nearly empty → same code change
            if _fix_files and len(subject_groups) > 1:
                # Pre-filter: find pairs with overlapping file-sets
                _n = len(subject_groups)
                # Union-Find to merge transitively
                _parent = list(range(_n))
                def _find(x):
                    while _parent[x] != x:
                        _parent[x] = _parent[_parent[x]]
                        x = _parent[x]
                    return x
                def _union(a, b):
                    a, b = _find(a), _find(b)
                    if a != b:
                        _parent[b] = a

                for i in range(_n):
                    fi = subject_groups[i].get("_file_set", frozenset())
                    if not fi:
                        continue
                    for j in range(i + 1, _n):
                        fj = subject_groups[j].get("_file_set", frozenset())
                        if not fj:
                            continue
                        # Only compare if file-sets overlap
                        if not fi & fj:
                            continue
                        # Compare actual diff between representative SHAs
                        sha_i = subject_groups[i]["sha"]
                        sha_j = subject_groups[j]["sha"]
                        try:
                            _stat = run_git(repo_dir, ["diff", "--shortstat",
                                                       sha_i, sha_j])
                            # Parse: " X files changed, Y insertions(+), Z deletions(-)"
                            _changed = 0
                            import re as _re2
                            _ins = _re2.search(r'(\d+) insertion', _stat)
                            _del = _re2.search(r'(\d+) deletion', _stat)
                            if _ins:
                                _changed += int(_ins.group(1))
                            if _del:
                                _changed += int(_del.group(1))
                            if not _stat.strip() or _changed <= 5:
                                _union(i, j)
                        except Exception:
                            pass

                # Group by union-find clusters
                _clusters: Dict[int, List[int]] = {}
                for i in range(_n):
                    _clusters.setdefault(_find(i), []).append(i)

                final = []
                for cluster_indices in _clusters.values():
                    if len(cluster_indices) == 1:
                        final.append(subject_groups[cluster_indices[0]])
                    else:
                        # Merge all entries in this cluster
                        base = dict(subject_groups[cluster_indices[0]])
                        all_tags = list(base.get("fix_tags", []))
                        all_shas = set(base.get("cherry_pick_shas", []))
                        subjects = [base.get("subject", "")]
                        for idx in cluster_indices[1:]:
                            extra = subject_groups[idx]
                            for t in extra.get("fix_tags", []):
                                if t not in all_tags:
                                    all_tags.append(t)
                            all_shas.update(extra.get("cherry_pick_shas", []))
                            s = extra.get("subject", "")
                            if s and s not in subjects:
                                subjects.append(s)
                        all_tags.sort(key=_tag_sort_key)
                        all_tags = _dedup_tags(all_tags)
                        base["fix_tag"] = all_tags[0] if all_tags else ""
                        base["fix_tags"] = all_tags
                        base["cherry_pick_count"] = len(all_shas)
                        base["cherry_pick_shas"] = list(all_shas)
                        base["merged_subjects"] = subjects
                        final.append(base)
                results[google_sha] = final
            else:
                results[google_sha] = subject_groups

        # Clean up internal fields
        for fix_list in results.values():
            for f in fix_list:
                f.pop("_file_set", None)

    if results:
        alias_count = sum(1 for v in results.values()
                          for f in v if f.get("matched_via") != "direct")
        print(f"[DEFECT SCAN] 找到 {len(results)} 笔 patch 在后续版本有修复提交"
              f"（其中 {alias_count} 笔通过上游/兄弟 SHA 匹配）", flush=True)

    print(f"[DEFECT SCAN] _scan_future_fixes 总耗时: {time.monotonic()-_t_scan_start:.1f}s", flush=True)
    return results


def _run_defect_scan_on_patches(
    task_id: str,
    patches: List[Dict[str, Any]],
    repo_dir: Path,
    scan_tag: str,
    *,
    apply: bool = True,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, str]]]]:
    """扫描后续修复与 crash 模式。apply=False 时只返回 sha→字段更新，不写 DB。"""
    _t_defect = time.monotonic()
    total = len(patches) or 1
    if progress_cb:
        progress_cb(0, total, "扫描后续修复提交…")
    future_fixes = _scan_future_fixes(repo_dir, patches, scan_tag)
    from web_app.crash_pattern_detector import detect_crash_patterns
    from web_app.llm_service import resolve_defect_scan_concurrency

    updates: Dict[str, Dict[str, Any]] = {}

    def _scan_patterns(p: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        sha = (p.get("sha") or p.get("commit") or "").strip()
        sha12 = sha[:12]
        upd: Dict[str, Any] = {}
        if sha12 in future_fixes:
            upd["fix_in_future"] = future_fixes[sha12]
        patterns = detect_crash_patterns(p.get("diff_preview", {}))
        if patterns:
            upd["crash_patterns"] = patterns
        return sha, upd

    _scan_workers = resolve_defect_scan_concurrency(len(patches) or 1)
    print(
        f"[DEFECT SCAN] 规则匹配并发 {_scan_workers} 路 / 共 {len(patches)} 笔 patch",
        flush=True,
    )
    if progress_cb:
        progress_cb(0, total, f"死机风险扫描 0/{total}…")
    _fix_hits = 0
    _pattern_hits = 0
    done = 0
    with ThreadPoolExecutor(max_workers=_scan_workers) as pool:
        futures = [pool.submit(_scan_patterns, p) for p in patches]
        for fut in as_completed(futures):
            sha, upd = fut.result()
            done += 1
            if upd:
                updates[sha] = upd
                if upd.get("fix_in_future"):
                    _fix_hits += 1
                if upd.get("crash_patterns"):
                    _pattern_hits += 1
            if progress_cb:
                progress_cb(
                    done, total,
                    f"死机风险扫描 {done}/{total}…",
                )

    # Ensure every scan hit is represented in updates (pattern pass can miss edge cases).
    for sha12, fixes in future_fixes.items():
        for p in patches:
            ps = (p.get("sha") or p.get("commit") or "").strip()
            if len(ps) >= 12 and ps[:12] == sha12:
                bucket = updates.setdefault(ps, {})
                bucket["fix_in_future"] = fixes
                break

    if apply:
        _defect_writer = PatchBatchWriter(batch_size=_DB_BATCH_SIZE)
        for p in patches:
            sha = (p.get("sha") or p.get("commit") or "").strip()
            upd = updates.get(sha)
            if not upd:
                continue
            p.update(upd)
            _defect_writer.upsert(p)
        _defect_writer.flush()

    _defect_elapsed = time.monotonic() - _t_defect
    _defect_count = _fix_hits + _pattern_hits
    print(
        f"[DEFECT SCAN] 耗时: {_defect_elapsed:.1f}s | "
        f"后续修复: {len(future_fixes)}笔 | "
        f"模式匹配: {_defect_count}笔",
        flush=True,
    )
    _log_timing_record(
        task_id, "", "defect_scan",
        _defect_elapsed * 1000,
        future_fixes=len(future_fixes),
        pattern_matches=_defect_count,
    )
    return updates, future_fixes


def _resolve_patch_in_pool(
    patch_by_sha: Dict[str, Dict[str, Any]],
    sha: str,
) -> Optional[Dict[str, Any]]:
    """按 full/short sha 在 patch 池 dict 中定位条目（兼容 commit/sha 字段差异）。"""
    key = (sha or "").strip()
    if not key:
        return None
    if key in patch_by_sha:
        return patch_by_sha[key]
    key12 = key[:12]
    for pool_key, patch in patch_by_sha.items():
        if not isinstance(patch, dict):
            continue
        candidates = {
            str(pool_key or "").strip(),
            str(patch.get("sha") or "").strip(),
            str(patch.get("commit") or "").strip(),
        }
        for cand in candidates:
            if not cand:
                continue
            if cand == key or cand[:12] == key12:
                return patch
    return None


def _apply_defect_updates(
    patch_by_sha: Dict[str, Dict[str, Any]],
    updates: Dict[str, Dict[str, Any]],
    future_fixes: Optional[Dict[str, List[Dict[str, str]]]] = None,
) -> int:
    """将并行 defect 扫描结果合并进内存 patch 并写回 DB。返回成功写入笔数。"""
    if future_fixes:
        for sha12, fixes in future_fixes.items():
            patch = _resolve_patch_in_pool(patch_by_sha, sha12)
            if patch:
                canon = (patch.get("commit") or patch.get("sha") or sha12).strip()
                bucket = updates.setdefault(canon, {})
            else:
                bucket = updates.setdefault(sha12, {})
            bucket["fix_in_future"] = fixes

    if not updates:
        print("[DEFECT SCAN] 无 defect 字段需要写入 DB", flush=True)
        return 0

    from web_app.database import get_patch

    writer = PatchBatchWriter(batch_size=_DB_BATCH_SIZE)
    applied = 0
    skipped = 0
    for upd_sha, upd in updates.items():
        patch = _resolve_patch_in_pool(patch_by_sha, upd_sha)
        if not patch:
            skipped += 1
            continue
        canon_sha = (patch.get("commit") or patch.get("sha") or upd_sha).strip()
        row = get_patch(canon_sha) if canon_sha else None
        merged = patch
        if row:
            raw = row.get("data") or {}
            try:
                base = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
            except (json.JSONDecodeError, TypeError):
                base = {}
            merged = {**base, **patch, **upd}
        else:
            merged = {**patch, **upd}
        canon_sha = (merged.get("commit") or merged.get("sha") or upd_sha).strip()
        if not canon_sha:
            skipped += 1
            continue
        merged["sha"] = canon_sha
        merged["commit"] = canon_sha
        patch.clear()
        patch.update(merged)
        patch_by_sha[canon_sha] = patch
        patch_by_sha[canon_sha[:12]] = patch
        writer.upsert(patch)
        applied += 1
    writer.flush()
    print(
        f"[DEFECT SCAN] 已写入 fix/crash 字段: {applied} 笔"
        + (f"，跳过 {skipped} 笔（池内未匹配）" if skipped else ""),
        flush=True,
    )
    return applied


def _run_llm_and_defect_parallel(
    task_id: str,
    patch_by_sha: Dict[str, Dict[str, Any]],
    *,
    scoring_config: Dict[str, Any],
    repo_dir: Optional[Path],
    scan_tag: str,
    main_task_shas: Set[str],
    force_reanalyze: bool,
    llm_configured: bool,
    llm_mode: str,
    config: Dict[str, Any],
    repo: str,
    failures: List[Dict[str, Any]],
    tracker: Optional["_ProgressTracker"],
    report_fn: Callable[..., None],
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """LLM/脚本分析与 defect 扫描并行；返回 (llm_info, main_patches)。"""
    patch_list = list(patch_by_sha.values())
    total = len(patch_list)
    llm_box: Dict[str, Any] = {}
    defect_box: Dict[str, Any] = {}
    exc_box: Dict[str, Exception] = {}

    def _llm_progress_cb(current: int, t: int, msg: str) -> None:
        report_fn("llm_analyzing", t, current, msg)

    def llm_worker() -> None:
        try:
            if llm_configured:
                analyzed, info = _run_llm_analysis_on_patches(
                    task_id,
                    patch_list,
                    scoring_config=scoring_config,
                    force_reanalyze=force_reanalyze,
                    link_to_task=True,
                    link_shas=main_task_shas,
                    llm_mode=llm_mode,
                    progress_cb=_llm_progress_cb,
                )
                llm_box["info"] = info
                llm_box["analyzed"] = analyzed
                for patch in analyzed:
                    sid = (patch.get("commit") or patch.get("sha") or "").strip()
                    if sid:
                        patch_by_sha[sid] = patch
            else:
                if len(patch_list) != total:
                    tracker.set_phase_total("analyzing", total) if tracker else None
                report_fn("analyzing", total, 0, f"脚本分析中… 共 {total} 笔")

                def _script_progress(current: int, t: int, msg: str) -> None:
                    report_fn("analyzing", t, current, msg)

                analyzed = _run_script_analysis_on_patches(
                    patch_list,
                    config,
                    repo,
                    failures,
                    link_to_task=True,
                    link_shas=main_task_shas,
                    task_id=task_id,
                    progress_cb=_script_progress,
                )
                llm_box["analyzed"] = analyzed
                for patch in analyzed:
                    sid = (patch.get("commit") or patch.get("sha") or "").strip()
                    if sid:
                        patch_by_sha[sid] = patch
        except Exception as exc:
            exc_box["llm"] = exc

    def defect_worker() -> None:
        if not repo_dir:
            return

        def _defect_progress(current: int, t: int, msg: str) -> None:
            report_fn("defect_scan", t, current, msg)

        try:
            updates, future_fixes = _run_defect_scan_on_patches(
                task_id,
                patch_list,
                Path(repo_dir),
                scan_tag,
                apply=False,
                progress_cb=_defect_progress,
            )
            defect_box["updates"] = updates
            defect_box["future_fixes"] = future_fixes
        except Exception as exc:
            exc_box["defect"] = exc

    t_llm = threading.Thread(target=llm_worker, daemon=True)
    t_defect = threading.Thread(target=defect_worker, daemon=True)
    _t_parallel = time.monotonic()
    t_llm.start()
    if repo_dir:
        defect_total = len(patch_list) or 1
        if tracker:
            tracker.set_phase_total("defect_scan", defect_total)
        report_fn(
            "defect_scan", defect_total, 0,
            f"扫描死机风险（与 LLM 并行）0/{defect_total}…",
        )
    t_defect.start()
    t_llm.join()
    t_defect.join()
    _parallel_elapsed = time.monotonic() - _t_parallel

    if "llm" in exc_box:
        raise exc_box["llm"]
    if "defect" in exc_box:
        print(f"[DEFECT SCAN] 失败: {exc_box['defect']}", flush=True)

    future_fixes = defect_box.get("future_fixes") or {}
    _defect_applied = _apply_defect_updates(
        patch_by_sha,
        defect_box.get("updates") or {},
        future_fixes,
    )
    _pool_unique = _unique_pool_patches(patch_by_sha)
    _pool_fix_count = sum(1 for p in _pool_unique if p.get("fix_in_future"))
    _task_fix_count = sum(
        1 for s in main_task_shas
        if isinstance(_resolve_patch_in_pool(patch_by_sha, s), dict)
        and _resolve_patch_in_pool(patch_by_sha, s).get("fix_in_future")
    )
    if future_fixes or _pool_fix_count:
        _persist_task_future_fix_snapshot(
            task_id,
            patch_by_sha,
            main_task_shas,
            future_fixes=future_fixes or None,
        )
        _display_pool = max(_pool_fix_count, len(future_fixes))
        _display_task = max(_task_fix_count, sum(
            1 for s in main_task_shas if str(s)[:12] in future_fixes
        ))
        report_fn(
            "defect_scan",
            len(patch_list),
            len(patch_list),
            (
                f"后续 Fixes：扫描池 {_display_pool} 笔"
                + (f"，本任务采样 {_display_task} 笔" if _display_task != _display_pool else "")
                + f"（写入 DB {_defect_applied} 笔）"
            ),
        )

    info = llm_box.get("info")
    if info is not None:
        info["elapsed"] = _parallel_elapsed

    main_patches = [
        patch_by_sha[s] for s in sorted(main_task_shas) if s in patch_by_sha
    ]
    return llm_box.get("info"), main_patches


def _run_subtag_and_summary_parallel(
    task_id: str,
    *,
    monthly_enabled: bool,
    monthly_intervals: List[Tuple[str, str]],
    patch_by_sha: Dict[str, Dict[str, Any]],
    failures: List[Dict[str, Any]],
    repo: str,
    repo_dir: Optional[Path],
    llm_result_info: Optional[Dict[str, Any]],
    is_single: bool,
    tracker: _ProgressTracker,
    report_fn: Callable[..., None],
) -> Optional[Dict[str, Any]]:
    """子 tag 切片统计与综合分析（模块 LLM + 综合报告）可并行，互不依赖。"""
    run_monthly = monthly_enabled and bool(monthly_intervals)
    run_summary = not is_single
    if not run_monthly and not run_summary:
        return None

    progress_lock = threading.Lock()
    subtag_doc_box: Dict[str, Any] = {}
    exc_box: Dict[str, Exception] = {}

    def safe_report(status, total, current, message):
        with progress_lock:
            report_fn(status, total, current, message)

    def monthly_worker() -> None:
        try:
            from web_app.monthly_subtag_service import (
                build_monthly_interval_sha_map,
                finalize_monthly_subtag_from_pool,
            )

            def _monthly_progress(done: int, total: int, msg: str) -> None:
                with progress_lock:
                    tracker._currents["monthly_recommendation"] = done
                    tracker._totals["monthly_recommendation"] = total
                safe_report("monthly_recommendation", total, done, msg)

            safe_report(
                "monthly_recommendation",
                len(monthly_intervals), 0,
                f"子 tag 统计 0/{len(monthly_intervals)}…",
            )
            interval_shas, baseline_tag, rmax_tag = build_monthly_interval_sha_map(
                repo,
                monthly_intervals,
                repo_dir,
                rmax_shas=set(patch_by_sha.keys()),
            )
            subtag_doc_box["doc"] = finalize_monthly_subtag_from_pool(
                task_id,
                monthly_intervals,
                patch_by_sha,
                interval_shas,
                failures,
                baseline_tag,
                rmax_tag,
                progress_cb=_monthly_progress,
                llm_info=llm_result_info,
            )
        except Exception as exc:
            exc_box["monthly"] = exc

    def summary_worker() -> None:
        try:
            summary_total = _estimate_summary_phase_total(task_id)
            with progress_lock:
                tracker.set_phase_total("summarizing", summary_total)
            safe_report(
                "summarizing", summary_total, 0,
                "生成综合分析与测试建议中…",
            )

            def _summary_progress(current: int, total: int, msg: str) -> None:
                safe_report("summarizing", total, current, msg)

            _run_summary_phase(
                task_id,
                progress_cb=_summary_progress,
                phase_total=summary_total,
            )
        except Exception as exc:
            exc_box["summary"] = exc

    _t_parallel = time.monotonic()
    if run_monthly and run_summary:
        print("[TIMING] 子 tag 统计 ∥ 综合分析…", flush=True)
        t_monthly = threading.Thread(target=monthly_worker, daemon=True)
        t_summary = threading.Thread(target=summary_worker, daemon=True)
        t_monthly.start()
        t_summary.start()
        t_monthly.join()
        t_summary.join()
    elif run_monthly:
        monthly_worker()
    else:
        summary_worker()

    _parallel_elapsed = time.monotonic() - _t_parallel
    print(
        f"[TIMING] 子 tag/综合阶段: {_parallel_elapsed:.1f}s "
        f"(monthly={'Y' if run_monthly else 'N'}, summary={'Y' if run_summary else 'N'})",
        flush=True,
    )

    if "monthly" in exc_box:
        print(f"[MONTHLY] {task_id}: 子 tag 统计失败: {exc_box['monthly']}", flush=True)
    if "summary" in exc_box:
        print(f"[SUMMARY] {task_id}: 综合分析失败: {exc_box['summary']}", flush=True)

    if run_monthly:
        tracker.finish("monthly_recommendation")
    if run_summary:
        tracker.finish("summarizing")

    return subtag_doc_box.get("doc")


def _run_analysis(
    task_id: str,
    repo: str,
    config_path: str,
    from_tag: str,
    to_tag: str,
    sample_size: int,
    sha: str,
    force_reanalyze: bool = False,
    auto_extend: int = 0,
    task_type: str = "range",
) -> None:
    """Execute analysis in a background thread."""
    try:
        _t0 = time.monotonic()
        _task_start_times[task_id] = datetime.now().strftime("%Y%m%d_%H%M%S")
        config = load_config(Path(config_path))
        repo = normalize_repo_url(repo)

        update_task(task_id, status="running")

        repo_dir = get_local_repo_dir()
        if repo_dir:
            print(f"[DATA] 使用本地仓库拉取数据: {repo_dir}", flush=True)

        # ── 完成数量驱动的进度追踪 ─────────
        _tracker = _ProgressTracker()

        _is_single = bool(sha)
        from web_app.llm_service import is_llm_configured as _check_llm
        _llm_configured = _check_llm()
        _same_month_subtag = (
            not _is_single
            and task_type == "range"
            and is_same_month_subtag_range(from_tag or "", to_tag or "")
        )
        _register_planned_phases(
            _tracker,
            is_single=_is_single,
            sample_size=sample_size,
            repo_dir=repo_dir,
            llm_configured=_llm_configured,
            auto_extend=auto_extend,
            include_monthly=not _same_month_subtag,
        )

        # ── 子 tag 区间列表（内嵌分析，不创建独立任务） ──
        _monthly_intervals: List[Tuple[str, str]] = []
        _monthly_enabled = False
        if (
            not _is_single
            and auto_extend > 0
            and task_type == "range"
            and to_tag
            and not _same_month_subtag
        ):
            _monthly_intervals = find_monthly_subtag_intervals(
                to_tag, from_tag=from_tag, repo_url=repo,
            )
            _monthly_enabled = bool(_monthly_intervals)
            if _monthly_enabled:
                _tracker.set_phase_total("monthly_recommendation", len(_monthly_intervals))
                print(
                    f"[MONTHLY] {task_id}: 内嵌子 tag 分析 {len(_monthly_intervals)} 个区间: "
                    f"{_monthly_intervals}",
                    flush=True,
                )

        # ── 进度报告辅助函数 ─────────
        def _report(status, total, current, message):
            ov_total, ov_cur = _tracker.update(status, total, current)
            data = {
                "status": status,
                "total": total,
                "current": current,
                "message": message,
                "overall_total": ov_total,
                "overall_current": ov_cur,
                "elapsed_seconds": int(time.monotonic() - _t0),
                "phases": _tracker.snapshot(),
            }
            if _monthly_enabled and status not in ("monthly_recommendation", "completed", "failed"):
                monthly_cur = _tracker._currents.get("monthly_recommendation", 0)
                monthly_total = _tracker._totals.get("monthly_recommendation", 0)
                if monthly_total > 0:
                    data["message"] = (
                        f"{message} | 子 tag: {monthly_cur}/{monthly_total}"
                    )
            _set_progress(task_id, data)

        def _finish_phase(status):
            _tracker.finish(status)
            # 发送完成状态的进度更新到前端
            cur = _tracker._currents.get(status, 0)
            total = _tracker._totals.get(status, cur)
            _report(status, total, cur, f'{status} 完成')

        # ── Phase: 获取提交列表（区间分析才显示进度条） ─────────
        if not _is_single:
            _report('fetching', 1, 0, '获取提交列表…')
        else:
            _report('collecting', _estimate_patch_phase_total(sample_size), 0, '准备分析…')

        if sha:
            # ── Single SHA ──────────────────────────
            commit = fetch_single_commit(repo, sha)
            sampled = [commit]
            total = 1
            all_commits = [commit]
        else:
            # ── Tag range ───────────────────────────
            _t_fetch_commits = time.monotonic()
            all_commits = fetch_commits_between_tags(repo, from_tag, to_tag, repo_dir=repo_dir)
            _log_timing_record(task_id, "", "fetch_commits",
                               (time.monotonic() - _t_fetch_commits) * 1000,
                               commit_count=len(all_commits))
            total = len(all_commits)
            # sample_size = 0 表示全量分析
            if sample_size <= 0 or sample_size >= total:
                actual = total
                sampled = list(all_commits)
            else:
                actual = sample_size
                sampled = random.sample(all_commits, actual)
            sampled.sort(key=lambda c: c.sha)
            mode_desc = f"全量 {actual} 笔" if actual == total else f"采样 {actual}/{total} 笔"

        _fetch_elapsed = time.monotonic() - _t0
        if _is_single:
            print(f"[TIMING] 获取提交列表: {_fetch_elapsed:.1f}s, 单笔分析", flush=True)
        else:
            print(f"[TIMING] 获取提交列表: {_fetch_elapsed:.1f}s, {total} 笔 commit, {mode_desc}", flush=True)
        update_task(task_id, total=total)

        if not _is_single:
            _finish_phase('fetching')

        _n = len(sampled)
        _main_task_shas: Set[str] = {
            c.sha for c in sampled if getattr(c, "sha", None)
        }
        _collect_commits = sampled
        if _monthly_enabled and _monthly_intervals:
            from web_app.monthly_subtag_service import build_monthly_collect_commit_union

            _collect_commits, _main_task_shas = build_monthly_collect_commit_union(
                sampled, _monthly_intervals, repo, repo_dir,
            )
            print(
                f"[MONTHLY] {task_id}: 统一采集 {len(_collect_commits)} 笔 "
                f"(主任务 {len(_main_task_shas)} + 子 tag 并集)",
                flush=True,
            )
        _collect_n = len(_collect_commits)
        _apply_sampled_phase_totals(_tracker, _collect_n, llm_configured=_llm_configured)
        _has_format_patch = bool(repo_dir) and not _is_single

        print(f"[TIMING] 采样: {_n} 笔, format_patch: {_has_format_patch}", flush=True)

        # ── 本地仓库：一次性 format-patch 获取全部 patch 数据 + 生成 diff 文件 ──
        _parsed_patches: Dict[str, Dict[str, Any]] = {}
        if _has_format_patch:
            _report('format_patch', 3, 0, '生成 patch / diff 中…')
            _t_fp = time.monotonic()
            from tools.patch_analyzer import run_git
            try:
                diff_dir = Path(__file__).parent.parent / "outputs" / "merged_diffs"
                diff_dir.mkdir(parents=True, exist_ok=True)
                tag_from = from_tag.replace("/", "_").replace("\\", "_")
                tag_to = to_tag.replace("/", "_").replace("\\", "_")
                output_path = diff_dir / f"{tag_from}_to_{tag_to}.patch"
                squash_path = diff_dir / f"{tag_from}_to_{tag_to}_squash.patch"

                cached = load_interval_diff_cache(repo, from_tag, to_tag)
                if cached:
                    _report('format_patch', 3, 1, '复用已缓存 patch…')
                    _t_fp_read = time.monotonic()
                    fp_output = cached.diff_file.read_text(encoding="utf-8")
                    _log_timing_record(
                        task_id, "", "format_patch_cache",
                        (time.monotonic() - _t_fp_read) * 1000,
                        source=cached.source,
                    )
                    _report('format_patch', 3, 2, '解析 patch 数据…')
                    _parsed_patches = parse_format_patch_output(fp_output, repo)
                    print(
                        f"[DATA] 复用缓存 patch: {len(_parsed_patches)} 笔 "
                        f"({cached.source}), {(time.monotonic()-_t_fp):.1f}s",
                        flush=True,
                    )
                    update_task(task_id, diff_file=str(cached.diff_file))
                    val_result = _validate_squash_patch_report(
                        task_id,
                        repo_dir,
                        from_tag,
                        to_tag,
                        cached.squash_file,
                        expected_commit_count=len(_parsed_patches) or cached.commit_count,
                        report_fn=_report,
                    )
                    if val_result and not val_result.ok:
                        _report('format_patch', 3, 2, '缓存 squash 校验未通过，重新生成…')
                        try:
                            repo_path = Path(repo_dir)
                            squash_output = run_git(
                                repo_path, ["diff", "-W", "-M", f"{from_tag}..{to_tag}"],
                            )
                            with open(cached.squash_file, "w", encoding="utf-8") as f:
                                f.write(
                                    "From 0000000000000000000000000000000000000000 "
                                    "Mon Sep 17 00:00:00 2001\n"
                                )
                                f.write(
                                    f"Subject: squash diff {from_tag}..{to_tag} "
                                    f"({len(_parsed_patches)} commits)\n\n"
                                )
                                f.write(squash_output)
                                f.write("\n")
                            print(
                                f"[SQUASH CHECK] 已重新生成 squash: {cached.squash_file}",
                                flush=True,
                            )
                            _validate_squash_patch_report(
                                task_id,
                                repo_dir,
                                from_tag,
                                to_tag,
                                cached.squash_file,
                                expected_commit_count=len(_parsed_patches) or cached.commit_count,
                                report_fn=_report,
                            )
                            save_interval_diff_cache(
                                repo, from_tag, to_tag,
                                cached.diff_file, cached.squash_file,
                                len(_parsed_patches) or cached.commit_count,
                            )
                        except Exception as exc:
                            print(f"[SQUASH CHECK] 重新生成 squash 失败: {exc}", flush=True)
                else:
                    repo_path = Path(repo_dir)
                    _fp_box: Dict[str, Any] = {"output": None, "error": None}
                    _squash_box: Dict[str, Any] = {"output": None, "error": None}

                    def _fp_worker():
                        try:
                            _fp_box["output"] = run_git(
                                repo_path, ["format-patch", "--stdout", f"{from_tag}..{to_tag}"]
                            )
                        except Exception as exc:
                            _fp_box["error"] = exc

                    def _squash_worker():
                        try:
                            _squash_box["output"] = run_git(
                                repo_path, ["diff", "-W", "-M", f"{from_tag}..{to_tag}"]
                            )
                        except Exception as exc:
                            _squash_box["error"] = exc

                    _t_fp_git = time.monotonic()
                    t_fp = threading.Thread(target=_fp_worker, daemon=True)
                    t_sq = threading.Thread(target=_squash_worker, daemon=True)
                    t_fp.start()
                    t_sq.start()
                    while t_fp.is_alive() or t_sq.is_alive():
                        t_fp.join(timeout=3)
                        t_sq.join(timeout=3)
                        if t_fp.is_alive() or t_sq.is_alive():
                            _report(
                                'format_patch', 3, 0,
                                f'并行生成 patch/squash… ({(time.monotonic()-_t_fp):.0f}s)',
                            )

                    if _fp_box["error"]:
                        raise _fp_box["error"]
                    fp_output = _fp_box["output"] or ""
                    _log_timing_record(task_id, "", "format_patch_git",
                                       (time.monotonic() - _t_fp_git) * 1000)
                    _report('format_patch', 3, 1, f'解析 patch 数据… ({(time.monotonic()-_t_fp):.0f}s)')
                    _t_fp_parse = time.monotonic()
                    _parsed_patches = parse_format_patch_output(fp_output, repo)
                    _log_timing_record(task_id, "", "format_patch_parse",
                                       (time.monotonic() - _t_fp_parse) * 1000,
                                       patch_count=len(_parsed_patches))
                    print(f"[DATA] format-patch 解析完成: {len(_parsed_patches)} 笔, {(time.monotonic()-_t_fp):.1f}s", flush=True)

                    output_path.write_text(fp_output, encoding="utf-8")
                    file_kb = output_path.stat().st_size / 1024
                    print(f"[DIFF] 逐笔 patch: {len(_parsed_patches)} 笔, {file_kb:.0f}KB -> {output_path}", flush=True)
                    update_task(task_id, diff_file=str(output_path))

                    _report('format_patch', 3, 2, '写入 squash diff…')
                    try:
                        if _squash_box["error"]:
                            raise _squash_box["error"]
                        squash_output = _squash_box.get("output") or ""
                        _log_timing_record(task_id, "", "format_patch_squash",
                                           (time.monotonic() - _t_fp_git) * 1000)
                        with open(squash_path, "w", encoding="utf-8") as f:
                            f.write("From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001\n")
                            f.write(f"Subject: squash diff {from_tag}..{to_tag} ({len(_parsed_patches)} commits)\n\n")
                            f.write(squash_output)
                            f.write("\n")
                        squash_kb = squash_path.stat().st_size / 1024
                        print(f"[DIFF] squash diff: {squash_kb:.0f}KB -> {squash_path}", flush=True)

                        _validate_squash_patch_report(
                            task_id,
                            repo_dir,
                            from_tag,
                            to_tag,
                            squash_path,
                            expected_commit_count=len(_parsed_patches),
                            report_fn=_report,
                        )

                        save_interval_diff_cache(
                            repo, from_tag, to_tag, output_path, squash_path,
                            len(_parsed_patches),
                        )
                    except Exception as exc:
                        print(f"[DIFF] squash diff 生成失败: {exc}", flush=True)

            except Exception as exc:
                print(f"[DATA] format-patch 失败 ({exc})，回退逐笔 git show", flush=True)
                _parsed_patches = {}
            finally:
                _fp_total = time.monotonic() - _t_fp
                print(f"[TIMING] format-patch 阶段: {_fp_total:.1f}s, {len(_parsed_patches)} 笔", flush=True)
                _log_timing_record(task_id, "", "format_patch_total", _fp_total * 1000,
                                   patch_count=len(_parsed_patches))
                if _parsed_patches:
                    _finish_phase('format_patch')

        # ── Phase 1: 数据采集（并发 fetch + 批量写库） ─────
        collected, patch_by_sha, failures, _reuse_count, _new_count, _fetch_total = (
            _run_collecting_phase(
                task_id,
                _collect_commits,
                repo=repo,
                repo_dir=repo_dir,
                parsed_patches=_parsed_patches,
                main_task_shas=_main_task_shas,
                llm_configured=_llm_configured,
                report_fn=_report,
            )
        )
        _finish_phase("collecting")

        # ── 检查任务是否已取消 ──
        if is_task_cancelled(task_id):
            print(f"[CANCEL] 任务已取消，跳过分析", flush=True)
            _cancelled_tasks.discard(task_id)
            return

        # ── 检查 LLM 配置 ────────────────────────────
        llm_configured = _llm_configured

        _llm_result_info = None
        _subtag_doc: Optional[Dict[str, Any]] = None
        _scan_tag = "" if _is_single else to_tag

        if llm_configured:
            _llm_in_progress[task_id] = True
            update_task(task_id, status="llm_analyzing")
            if len(collected) != _collect_n:
                _tracker.set_phase_total("llm_analyzing", len(collected))
            _report(
                "llm_analyzing", len(collected), 0,
                f"LLM 深度分析中… 共 {len(collected)} 笔",
            )
        elif len(collected) != _collect_n:
            _tracker.set_phase_total("analyzing", len(collected))

        try:
            _llm_result_info, patches = _run_llm_and_defect_parallel(
                task_id,
                patch_by_sha,
                scoring_config=config,
                repo_dir=repo_dir,
                scan_tag=_scan_tag,
                main_task_shas=_main_task_shas,
                force_reanalyze=force_reanalyze,
                llm_configured=llm_configured,
                llm_mode="lightweight",
                config=config,
                repo=repo,
                failures=failures,
                tracker=_tracker,
                report_fn=_report,
            )
        finally:
            if llm_configured:
                _llm_in_progress[task_id] = False

        _pool_unique = _unique_pool_patches(patch_by_sha)
        _pool_fix_count = sum(1 for p in _pool_unique if p.get("fix_in_future"))
        _task_fix_count = sum(
            1 for s in _main_task_shas
            if isinstance(_resolve_patch_in_pool(patch_by_sha, s), dict)
            and _resolve_patch_in_pool(patch_by_sha, s).get("fix_in_future")
        )
        _stored_task = get_task(task_id) or {}
        _snap_pool = int(_stored_task.get("future_fix_pool_count") or 0)
        _snap_task = int(_stored_task.get("future_fix_task_count") or 0)
        if _pool_fix_count or _snap_pool:
            _prog = get_progress(task_id)
            _set_progress(task_id, {
                **_prog,
                "defect_future_fix_pool": max(_pool_fix_count, _snap_pool),
                "defect_future_fix_task": max(_task_fix_count, _snap_task),
            })

        if llm_configured:
            _finish_phase("llm_analyzing")
            if _llm_result_info:
                _log_timing_record(
                    task_id, "", "llm_summary",
                    (_llm_result_info.get("elapsed") or 0) * 1000,
                    success=_llm_result_info.get("success", 0),
                    failed=_llm_result_info.get("failed", 0),
                    skipped=_llm_result_info.get("reused_count", 0),
                    failures=(_llm_result_info.get("failed_details") or [])[:50],
                )
            _t_reload = time.monotonic()
            _reload_rows = get_patches_by_task(task_id)
            _reload_patches = []
            for _row in _reload_rows:
                _data_raw = _row.get("data", "{}")
                try:
                    _pd = json.loads(_data_raw) if isinstance(_data_raw, str) else dict(_data_raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                _reload_patches.append(_pd)
            _log_timing_record(
                task_id, "", "llm_reload",
                (time.monotonic() - _t_reload) * 1000,
                count=len(_reload_patches),
            )
            if _reload_patches:
                patches = _reload_patches
                print(
                    f"[LLM] 重载 {len(patches)} 笔主任务 patch "
                    f"(llm_analyzed={sum(1 for p in patches if p.get('llm_analyzed'))})",
                    flush=True,
                )
        else:
            _finish_phase("analyzing")

        if repo_dir:
            _finish_phase("defect_scan")

        update_task(task_id, analyzed=len(patches), failed=len(failures))

        # ── 检查任务是否已取消 ──
        if is_task_cancelled(task_id):
            print(f"[CANCEL] 任务已取消，终止后续阶段", flush=True)
            _cancelled_tasks.discard(task_id)
            return

        # ── 子 tag 统计 ∥ 综合分析（互不依赖，可并行） ──
        _subtag_doc = _run_subtag_and_summary_parallel(
            task_id,
            monthly_enabled=_monthly_enabled,
            monthly_intervals=_monthly_intervals,
            patch_by_sha=patch_by_sha,
            failures=failures,
            repo=repo,
            repo_dir=repo_dir,
            llm_result_info=_llm_result_info,
            is_single=_is_single,
            tracker=_tracker,
            report_fn=_report,
        )

        # ── 总耗时 ────────────────────────────────────
        _total = time.monotonic() - _t0
        print(f"[TIMING] {'='*40}", flush=True)
        print(f"[TIMING] 总耗时: {_total:.0f}s (约{_total/60:.1f}分钟) | 采样{len(sampled)}笔", flush=True)
        # 存入数据库
        update_task(task_id, elapsed_seconds=round(_total, 1))

        # ── 整体汇总 perf log（含 token 统计） ─────────
        _task_info = get_task(task_id) or {}
        _log_timing_record(task_id, "", "overall_summary",
                           _total * 1000,
                           sampled=len(sampled),
                           patches_total=len(patches),
                           failures=len(failures),
                           prompt_tokens=_task_info.get("llm_prompt_tokens", 0) or 0,
                           completion_tokens=_task_info.get("llm_completion_tokens", 0) or 0)
        _flush_timing_records(task_id)

        # ── 生成 patch/diff 文件（早期未成功时在此兜底） ──
        if not _is_single and "format_patch" in _tracker._totals:
            fp_total = _tracker._totals.get("format_patch", 0)
            fp_current = _tracker._currents.get("format_patch", 0)
            fp_done = fp_total > 0 and fp_current >= fp_total
            if not fp_done:
                try:
                    _report('format_patch', 3, 0, '生成 patch / diff 中…')
                    _run_diff_phase(task_id, repo, all_commits, from_tag, to_tag, repo_dir=repo_dir)
                except Exception as exc:
                    print(f"[DIFF] patch/diff 生成失败: {exc}", flush=True)
                _finish_phase('format_patch')

        # ── 标记任务最终完成（统一路径） ──────────────
        # ── 完成所有阶段 ──
        _finish_phase('summarizing')
        ov_total, ov_cur = _tracker._compute()

        def _mark_task_completed() -> None:
            if llm_configured:
                _llm_info = _llm_result_info or {}
                err_msg = f"LLM: {_llm_info.get('success',0)}成功/{_llm_info.get('failed',0)}失败"
                update_task(
                    task_id,
                    status="completed",
                    error_msg=err_msg,
                    completed_at=datetime.now().isoformat(),
                    new_analyzed=_llm_info.get("new_analyzed", 0),
                    reused_count=_llm_info.get("reused_count", 0),
                )
            else:
                update_task(
                    task_id,
                    status="completed",
                    completed_at=datetime.now().isoformat(),
                )

        if _monthly_enabled and _monthly_intervals and _subtag_doc:
            from web_app.monthly_subtag_service import build_monthly_tag_recommendation_from_results

            interval_tasks = [
                {
                    "from_tag": item.get("from_tag", ""),
                    "to_tag": item.get("to_tag", ""),
                    "task_id": task_id,
                    "status": item.get("status", ""),
                }
                for item in (_subtag_doc.get("intervals") or [])
            ]
            recommendation = build_monthly_tag_recommendation_from_results(
                _subtag_doc.get("intervals") or [],
            )
            _set_progress(task_id, {
                "status": "completed",
                "message": (
                    f"分析完成 | 子 tag {_subtag_doc.get('completed', 0)}/"
                    f"{_subtag_doc.get('interval_count', 0)} | "
                    f"优选: {recommendation.get('recommended_tag') or '暂无'}"
                ),
                "total": ov_total,
                "current": ov_cur,
                "overall_total": ov_total,
                "overall_current": ov_cur,
                "elapsed_seconds": int(time.monotonic() - _t0),
                "phases": _tracker.snapshot(),
                "monthly_intervals": interval_tasks,
                "monthly_recommendation": recommendation,
            })
            _mark_task_completed()
        elif _monthly_enabled and _monthly_intervals and not _subtag_doc:
            _set_progress(task_id, {
                "status": "completed",
                "message": "分析完成 | 子 tag 统计未完成",
                "total": ov_total,
                "current": ov_cur,
                "overall_total": ov_total,
                "overall_current": ov_cur,
                "elapsed_seconds": int(time.monotonic() - _t0),
                "phases": _tracker.snapshot(),
                "monthly_recommendation": {
                    "has_recommendation": False,
                    "reason": "子 tag 统计阶段失败或未执行",
                },
            })
            _mark_task_completed()
        else:
            if not _monthly_enabled and "monthly_recommendation" in _tracker._totals:
                _finish_phase("monthly_recommendation")
            _monthly_skip_payload: Dict[str, Any] = {}
            if auto_extend > 0 and not _is_single and to_tag and not _monthly_enabled:
                if _same_month_subtag:
                    # Do not attach recommendation payload — UI/report omit the section.
                    pass
                else:
                    _monthly_skip_payload = {
                        "monthly_recommendation": {
                            "has_recommendation": False,
                            "reason": f"未找到 {to_tag} 对应月份的相邻子 tag 区间",
                        },
                    }
            _set_progress(task_id, {
                "status": "completed",
                "message": f"分析完成 | 耗时 {int(_total)}s",
                "total": ov_total,
                "current": ov_cur,
                "overall_total": ov_total,
                "overall_current": ov_cur,
                "elapsed_seconds": int(_total),
                "phases": _tracker.snapshot(),
                **_monthly_skip_payload,
            })
            _mark_task_completed()

    except Exception as exc:
        update_task(task_id, status="failed", error_msg=str(exc))
        _set_progress(task_id, {"status": "failed", "message": str(exc)})
        _flush_timing_records(task_id)


# ── Task / Patch helpers ───────────────────────────────

def get_task_with_patches(task_id: str, dev_module: str = "") -> Optional[Dict[str, Any]]:
    task = get_task(task_id)
    if not task:
        return None

    prog = get_progress(task_id)
    if prog.get("status") not in ("unknown", ""):
        task["progress"] = prog

    monthly_rec = resolve_monthly_recommendation_for_task(task, prog)
    if monthly_rec:
        task["monthly_recommendation"] = monthly_rec
        task.setdefault("progress", {})
        task["progress"]["monthly_recommendation"] = monthly_rec

    llm_running = _llm_in_progress.get(task_id, False)
    task["llm_running"] = llm_running

    prog_status = str(prog.get("status") or "").lower() if prog.get("status") not in ("unknown", "") else ""
    task_status = str(task.get("status") or "").lower()
    # 全部阶段结束后再返回 patch / 总结（含并行中的子 tag、综合分析）
    show_results = task_status in ("completed", "failed") or prog_status == "completed"

    if not show_results:
        task["patches"] = []
        task["patch_count"] = task.get("total", 0) or 0
        task["llm_analyzed_count"] = 0
        task["summary"] = None
        return task

    patches = get_patches_by_task(task_id, dev_module=dev_module)
    patch_list = [_merge_patch_row(p) for p in patches]
    _enrich_patches_with_future_fix_snapshot(patch_list, task)

    task["patches"] = patch_list
    task["patch_count"] = len(patch_list)
    task["llm_analyzed_count"] = sum(1 for p in patch_list if p.get("llm_analyzed"))

    if patch_list:
        task["summary"] = _build_task_result_summary(
            task, patch_list, raw_patches=patches,
        )
    else:
        task["summary"] = None
    return task


def _merge_patch_row(db_row: Dict[str, Any]) -> Dict[str, Any]:
    """Merge DB row + JSON data into a single patch dict for UI/summary."""
    row: Dict[str, Any] = {
        "sha": db_row.get("sha", ""),
        "title": db_row.get("title", ""),
        "score": db_row.get("score"),
        "recommendation": db_row.get("recommendation", ""),
        "key_risk": db_row.get("key_risk", ""),
        "dev_module": db_row.get("dev_module", ""),
    }
    data_raw = db_row.get("data")
    if not data_raw:
        return row
    try:
        full = json.loads(data_raw) if isinstance(data_raw, str) else dict(data_raw)
    except (json.JSONDecodeError, TypeError):
        return row

    for key in (
        "commit_url", "diff_url", "llm_analyzed", "patch_tags", "platform_tags",
        "blocked", "block_rules_hit", "score_details", "test_suggestions",
        "fix_in_future", "crash_risk", "crash_risk_reason", "crash_patterns",
        "upstream_sha", "high_risk_paths", "introduced_risk", "introducer_analysis",
        "modification_interpretation", "commit_interpretation_rich",
    ):
        if key in full:
            row[key] = full[key]

    if full.get("recommendation"):
        row["recommendation"] = full["recommendation"]
    if full.get("key_risk"):
        row["key_risk"] = full["key_risk"]
    row["dev_module"] = row.get("dev_module") or full.get("dev_module", "")
    row["dev_module"] = _classify_dev_module(full, llm_suggestion=row["dev_module"])
    return row
