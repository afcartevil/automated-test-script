"""内嵌式子 tag 分析：不创建独立任务，逐区间 LLM/脚本分析 + 统计聚合。"""
from __future__ import annotations

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from patch_analyzer import fetch_commits_between_tags, fetch_patch_data, load_config

from web_app.analyzer_service import (
    DEFAULT_CONFIG,
    _classify_dev_module,
    _parse_month_subtag,
    _patch_reusable,
    _run_llm_analysis_on_patches,
    _run_script_analysis_on_patches,
    is_task_cancelled,
)
from web_app.database import get_patch, update_task, upsert_patch

# 兼容旧参数名；实际并发见 resolve_interval_worker_concurrency / GKI_MONTHLY_INTERVAL_WORKERS
MONTHLY_INTERVAL_WORKERS = 3


def _build_interval_result(
    from_tag: str,
    to_tag: str,
    *,
    task_id: str,
    interval_shas: Dict[Tuple[str, str], set],
    patch_by_sha: Dict[str, Dict[str, Any]],
    collect_failures: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """单个累计子 tag 区间：切片 + 统计（只读 patch 池，可并行）。"""
    if is_task_cancelled(task_id):
        return {
            "from_tag": from_tag,
            "to_tag": to_tag,
            "status": "cancelled",
            "error": "任务已取消",
            "stats": compute_interval_stats([], from_tag, to_tag),
        }

    interval_patches = _patches_for_interval(
        interval_shas, patch_by_sha, from_tag, to_tag,
    )
    stats = compute_interval_stats(interval_patches, from_tag, to_tag)
    patch_shas = sorted(
        _patch_identity(p) for p in interval_patches if _patch_identity(p)
    )
    return {
        "from_tag": from_tag,
        "to_tag": to_tag,
        "status": "completed",
        "commit_count": len(interval_patches),
        "failed_count": len(collect_failures),
        "patch_shas": patch_shas,
        "stats": stats,
    }


def _cumulative_subtag_sort_key(stats: Dict[str, Any]) -> Tuple[Any, ...]:
    """Sort cumulative r1->rN intervals: lower risk first, then prefer higher rN."""
    risk = stats.get("risk_distribution") or {}
    r_num = 0
    parsed = _parse_month_subtag(str(stats.get("to_tag") or ""))
    if parsed:
        r_num = parsed[1]
    return (
        int(risk.get("high", 0) or 0),
        int(risk.get("medium", 0) or 0),
        int(stats.get("has_future_fix_count", 0) or 0),
        int(stats.get("blocked_count", 0) or 0),
        -float(stats.get("min_score", 0) or 0),
        -float(stats.get("avg_score", 0) or 0),
        -r_num,
    )


def compute_interval_stats(
    patches: List[Dict[str, Any]],
    from_tag: str,
    to_tag: str,
) -> Dict[str, Any]:
    """从 patch 列表计算区间统计（与 get_range_comparison_stats 字段兼容）。"""
    scores: List[float] = []
    risk_counts = {"high": 0, "medium": 0, "low": 0, "none": 0}
    llm_count = 0
    fix_count = 0
    blocked_count = 0
    mod_dist: Dict[str, int] = {}

    for p in patches:
        score = float(p.get("score", 0) or 0)
        if score > 0:
            scores.append(score)
        rec = (p.get("recommendation") or "").lower()
        if "high" in rec or "高" in rec:
            risk_counts["high"] += 1
        elif "medium" in rec or "中" in rec:
            risk_counts["medium"] += 1
        elif "low" in rec or "低" in rec:
            risk_counts["low"] += 1
        else:
            risk_counts["none"] += 1
        if p.get("llm_analyzed"):
            llm_count += 1
        if p.get("fix_in_future"):
            fix_count += 1
        if p.get("blocked"):
            blocked_count += 1
        mod = (p.get("dev_module") or "").strip()
        if mod:
            mod_dist[mod] = mod_dist.get(mod, 0) + 1

    sorted_by_score = sorted(patches, key=lambda x: float(x.get("score", 0) or 0))
    top_risk = [
        {
            "sha": (p.get("commit") or p.get("sha", ""))[:12],
            "title": (p.get("title") or "")[:60],
            "score": float(p.get("score", 0) or 0),
        }
        for p in sorted_by_score[:10]
        if float(p.get("score", 0) or 0) > 0
    ]

    return {
        "from_tag": from_tag,
        "to_tag": to_tag,
        "total_patches": len(patches),
        "avg_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "min_score": round(min(scores), 2) if scores else 0,
        "max_score": round(max(scores), 2) if scores else 0,
        "blocked_count": blocked_count,
        "risk_distribution": risk_counts,
        "module_distribution": mod_dist,
        "llm_analyzed_count": llm_count,
        "has_future_fix_count": fix_count,
        "top_risk_patches": top_risk,
    }


def build_monthly_tag_recommendation_from_results(
    interval_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """从 embedded 子 tag 区间结果生成推荐。"""
    stats = [
        item["stats"]
        for item in interval_results
        if item.get("status") == "completed"
        and int((item.get("stats") or {}).get("total_patches") or 0) > 0
    ]
    if not stats:
        return {"has_recommendation": False, "reason": "暂无可用于子 tag 分析的区间结果"}

    ranked = sorted(stats, key=_cumulative_subtag_sort_key)
    best = ranked[0]
    risk = best.get("risk_distribution") or {}
    target_tag = best.get("to_tag") or ""
    return {
        "has_recommendation": True,
        "recommended_tag": target_tag,
        "recommended_interval": {
            "from_tag": best.get("from_tag"),
            "to_tag": target_tag,
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


def _patch_identity(p: Dict[str, Any]) -> str:
    return (p.get("commit") or p.get("sha") or "").strip()


def _collect_single_patch(
    repo: str,
    sha: str,
    commit: Any,
    repo_dir: Optional[Path],
    *,
    llm_configured: bool,
    failures: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    try:
        existing_row = get_patch(sha)
        if existing_row and _patch_reusable(existing_row, llm_configured=llm_configured):
            data_raw = existing_row.get("data", "{}")
            parsed = json.loads(data_raw) if isinstance(data_raw, str) else dict(data_raw or {})
            _llm_mod = parsed.get("dev_module", "")
            parsed["dev_module"] = _classify_dev_module(parsed, llm_suggestion=_llm_mod)
            upsert_patch(parsed)
            return parsed
        raw = fetch_patch_data(repo, commit, repo_dir=repo_dir)
        raw["llm_analyzed"] = False
        upsert_patch(raw)
        return raw
    except Exception as exc:
        failures.append({"sha": sha, "error": str(exc)})
        return None


def _resolve_baseline_and_rmax(intervals: List[Tuple[str, str]]) -> Tuple[str, str]:
    """累计区间共享 baseline（r1），rMax 为 to_tag 中 r 序号最大者。"""
    if not intervals:
        raise ValueError("empty intervals")
    baseline = intervals[0][0]
    rmax_tag = intervals[0][1]
    best_r = -1
    for _from_tag, to_tag in intervals:
        parsed = _parse_month_subtag(to_tag)
        r_num = parsed[1] if parsed else -1
        if r_num > best_r:
            best_r = r_num
            rmax_tag = to_tag
    return baseline, rmax_tag


def _commit_sha_set(
    repo: str,
    from_tag: str,
    to_tag: str,
    repo_dir: Optional[Path],
) -> set:
    commits = fetch_commits_between_tags(repo, from_tag, to_tag, repo_dir=repo_dir)
    return {c.sha for c in commits if getattr(c, "sha", None)}


def build_monthly_collect_commit_union(
    sampled: List[Any],
    intervals: List[Tuple[str, str]],
    repo: str,
    repo_dir: Optional[Path],
) -> Tuple[List[Any], set]:
    """主任务采样 commit ∪ 子 tag r1→rMax 全量 commit（去重，按 sha 排序）。"""
    main_shas = {c.sha for c in sampled if getattr(c, "sha", None)}
    sha_to_commit = {c.sha: c for c in sampled if getattr(c, "sha", None)}
    if intervals:
        baseline, rmax_tag = _resolve_baseline_and_rmax(intervals)
        for commit in fetch_commits_between_tags(
            repo, baseline, rmax_tag, repo_dir=repo_dir,
        ):
            sha = getattr(commit, "sha", None)
            if sha and sha not in sha_to_commit:
                sha_to_commit[sha] = commit
    commits = sorted(sha_to_commit.values(), key=lambda c: c.sha)
    return commits, main_shas


def build_monthly_interval_sha_map(
    repo: str,
    intervals: List[Tuple[str, str]],
    repo_dir: Optional[Path],
    *,
    rmax_shas: Optional[set] = None,
) -> Tuple[Dict[Tuple[str, str], set], str, str]:
    """构建各累计区间的 commit sha 集合（不采集 patch）。

    ``rmax_shas`` 表示已采集 patch 池（可大于 r1→rMax 的 git 区间），
    仅在与 git 区间 commit 求交后写入 rMax 累计区间，避免把主采样 patch 误归入子 tag。
    """
    baseline, rmax_tag = _resolve_baseline_and_rmax(intervals)
    interval_shas: Dict[Tuple[str, str], set] = {}
    for from_tag, to_tag in intervals:
        key = (from_tag, to_tag)
        git_shas = _commit_sha_set(repo, from_tag, to_tag, repo_dir)
        if to_tag == rmax_tag and rmax_shas is not None:
            interval_shas[key] = git_shas & rmax_shas
        else:
            interval_shas[key] = git_shas
    return interval_shas, baseline, rmax_tag


def finalize_monthly_subtag_from_pool(
    task_id: str,
    intervals: List[Tuple[str, str]],
    patch_by_sha: Dict[str, Dict[str, Any]],
    interval_shas: Dict[Tuple[str, str], set],
    collect_failures: List[Dict[str, Any]],
    baseline_tag: str,
    rmax_tag: str,
    *,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    llm_info: Optional[Dict[str, Any]] = None,
    analysis_mode: str = "cumulative_rmax_pooled",
    max_workers: Optional[int] = None,
) -> Dict[str, Any]:
    """对已采集+分析的全集 patch 池按区间切片统计（不再采集/LLM）。"""
    from web_app.llm_service import resolve_interval_worker_concurrency

    total = len(intervals)
    unique_patch_count = len(patch_by_sha)
    worker_count = (
        max_workers
        if max_workers is not None
        else resolve_interval_worker_concurrency(total)
    )
    print(
        f"[MONTHLY] {task_id}: 子 tag 区间统计并发 {worker_count} 路 / 共 {total} 个区间",
        flush=True,
    )

    progress_lock = threading.Lock()
    done = 0
    ordered_results: List[Optional[Dict[str, Any]]] = [None] * total

    def _emit_progress(from_tag: str, to_tag: str, patch_count: int) -> None:
        nonlocal done
        with progress_lock:
            done += 1
            cur = done
        if progress_cb:
            with progress_lock:
                progress_cb(
                    cur, total,
                    f"子 tag 结论 {cur}/{total}：{from_tag} → {to_tag}（{patch_count} 笔）",
                )

    if total == 0:
        results: List[Dict[str, Any]] = []
    elif worker_count <= 1 or total == 1:
        results = []
        for from_tag, to_tag in intervals:
            item = _build_interval_result(
                from_tag, to_tag,
                task_id=task_id,
                interval_shas=interval_shas,
                patch_by_sha=patch_by_sha,
                collect_failures=collect_failures,
            )
            results.append(item)
            _emit_progress(from_tag, to_tag, item.get("commit_count", 0))
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            future_map = {
                pool.submit(
                    _build_interval_result,
                    from_tag,
                    to_tag,
                    task_id=task_id,
                    interval_shas=interval_shas,
                    patch_by_sha=patch_by_sha,
                    collect_failures=collect_failures,
                ): (idx, from_tag, to_tag)
                for idx, (from_tag, to_tag) in enumerate(intervals)
            }
            for future in as_completed(future_map):
                idx, from_tag, to_tag = future_map[future]
                item = future.result()
                ordered_results[idx] = item
                _emit_progress(from_tag, to_tag, item.get("commit_count", 0))
        results = [item for item in ordered_results if item is not None]

    completed = sum(1 for r in results if r.get("status") == "completed")
    failed = sum(1 for r in results if r.get("status") == "failed")
    llm_info = llm_info or {}

    doc = {
        "interval_count": total,
        "completed": completed,
        "failed": failed,
        "intervals": results,
        "embedded": True,
        "baseline_tag": baseline_tag,
        "rmax_tag": rmax_tag,
        "unique_patch_count": unique_patch_count,
        "analysis_mode": analysis_mode,
        "llm_info": llm_info,
    }
    update_task(
        task_id,
        monthly_subtag_results=json.dumps(doc, ensure_ascii=False),
    )
    print(
        f"[MONTHLY] {task_id}: 子 tag 统计完成 {completed}/{total} "
        f"(r1→rMax {unique_patch_count} 笔，模式 {analysis_mode})",
        flush=True,
    )
    return doc


def _prepare_cumulative_from_rmax(
    repo: str,
    intervals: List[Tuple[str, str]],
    repo_dir: Optional[Path],
    *,
    llm_configured: bool,
) -> Tuple[
    Dict[Tuple[str, str], set],
    Dict[str, Dict[str, Any]],
    List[Dict[str, Any]],
    str,
    str,
]:
    """仅采集并分析 r1->rMax 的 patch；各 r1->rN 区间只做 commit 切片。"""
    baseline, rmax_tag = _resolve_baseline_and_rmax(intervals)
    failures: List[Dict[str, Any]] = []

    commits_rmax = fetch_commits_between_tags(
        repo, baseline, rmax_tag, repo_dir=repo_dir,
    )
    patch_by_sha: Dict[str, Dict[str, Any]] = {}
    for commit in commits_rmax:
        sha = commit.sha
        if not sha:
            continue
        patch = _collect_single_patch(
            repo, sha, commit, repo_dir,
            llm_configured=llm_configured,
            failures=failures,
        )
        if patch:
            patch_by_sha[sha] = patch

    rmax_shas = set(patch_by_sha.keys())
    interval_shas: Dict[Tuple[str, str], set] = {}
    for from_tag, to_tag in intervals:
        key = (from_tag, to_tag)
        git_shas = _commit_sha_set(repo, from_tag, to_tag, repo_dir)
        if to_tag == rmax_tag:
            interval_shas[key] = git_shas & rmax_shas
        else:
            interval_shas[key] = git_shas

    return interval_shas, patch_by_sha, failures, baseline, rmax_tag


def _prepare_cumulative_patch_pool(
    repo: str,
    intervals: List[Tuple[str, str]],
    repo_dir: Optional[Path],
    *,
    llm_configured: bool,
) -> Tuple[Dict[Tuple[str, str], set], Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    """兼容别名：委托给 r1->rMax 单次采集。"""
    interval_shas, patch_by_sha, failures, _baseline, _rmax = _prepare_cumulative_from_rmax(
        repo, intervals, repo_dir, llm_configured=llm_configured,
    )
    return interval_shas, patch_by_sha, failures


def _patches_for_interval(
    interval_shas: Dict[Tuple[str, str], set],
    patch_by_sha: Dict[str, Dict[str, Any]],
    from_tag: str,
    to_tag: str,
) -> List[Dict[str, Any]]:
    shas = interval_shas.get((from_tag, to_tag), set())
    return [patch_by_sha[s] for s in shas if s in patch_by_sha]


def _collect_interval_patches(
    repo: str,
    from_tag: str,
    to_tag: str,
    repo_dir: Optional[Path],
    *,
    llm_configured: bool,
    failures: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    commits = fetch_commits_between_tags(repo, from_tag, to_tag, repo_dir=repo_dir)
    patches: List[Dict[str, Any]] = []
    for commit in commits:
        sha = commit.sha
        patch = _collect_single_patch(
            repo, sha, commit, repo_dir,
            llm_configured=llm_configured,
            failures=failures,
        )
        if patch:
            patches.append(patch)
    return patches


def analyze_monthly_interval(
    task_id: str,
    from_tag: str,
    to_tag: str,
    *,
    repo: str,
    config: Dict[str, Any],
    repo_dir: Optional[Path],
    llm_configured: bool,
    force_reanalyze: bool = False,
) -> Dict[str, Any]:
    """单个子 tag 区间：采集 + LLM 或脚本分析 + 区间统计（不跑模块分析）。"""
    failures: List[Dict[str, Any]] = []
    try:
        patches = _collect_interval_patches(
            repo, from_tag, to_tag, repo_dir,
            llm_configured=llm_configured,
            failures=failures,
        )
        if is_task_cancelled(task_id):
            return {
                "from_tag": from_tag,
                "to_tag": to_tag,
                "status": "cancelled",
                "error": "任务已取消",
                "stats": compute_interval_stats([], from_tag, to_tag),
            }

        if llm_configured:
            patches, _info = _run_llm_analysis_on_patches(
                task_id,
                patches,
                scoring_config=config,
                force_reanalyze=force_reanalyze,
                link_to_task=False,
                llm_mode="lightweight",
            )
        else:
            patches = _run_script_analysis_on_patches(
                patches, config, repo, failures, link_to_task=False,
            )

        stats = compute_interval_stats(patches, from_tag, to_tag)
        return {
            "from_tag": from_tag,
            "to_tag": to_tag,
            "status": "completed",
            "commit_count": len(patches),
            "failed_count": len(failures),
            "stats": stats,
        }
    except Exception as exc:
        return {
            "from_tag": from_tag,
            "to_tag": to_tag,
            "status": "failed",
            "error": str(exc),
            "stats": compute_interval_stats([], from_tag, to_tag),
        }


def run_monthly_subtag_analysis_for_task(
    task_id: str,
    intervals: List[Tuple[str, str]],
    *,
    repo: str,
    config_path: str = DEFAULT_CONFIG,
    repo_dir: Optional[Path] = None,
    llm_configured: bool,
    force_reanalyze: bool = False,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    max_workers: Optional[int] = None,
) -> Dict[str, Any]:
    """对累计子 tag 做内嵌分析：仅 r1->rMax 采集+分析一次，再输出各 r1->rN 结论。"""
    if not intervals:
        return {"interval_count": 0, "intervals": [], "completed": 0, "failed": 0}

    try:
        config = load_config(Path(config_path))
    except Exception:
        config = {}

    total = len(intervals)
    if progress_cb:
        progress_cb(0, total, "子 tag 采集 r1→rMax patch…")

    (
        interval_shas,
        patch_by_sha,
        collect_failures,
        baseline_tag,
        rmax_tag,
    ) = _prepare_cumulative_from_rmax(
        repo, intervals, repo_dir, llm_configured=llm_configured,
    )
    unique_patch_count = len(patch_by_sha)
    print(
        f"[MONTHLY] {task_id}: r1→rMax ({baseline_tag} → {rmax_tag}) "
        f"共 {unique_patch_count} 笔 patch，{total} 个累计区间待统计",
        flush=True,
    )

    if is_task_cancelled(task_id):
        cancelled = [{
            "from_tag": ft,
            "to_tag": tt,
            "status": "cancelled",
            "error": "任务已取消",
            "stats": compute_interval_stats([], ft, tt),
        } for ft, tt in intervals]
        doc = {
            "interval_count": total,
            "completed": 0,
            "failed": 0,
            "intervals": cancelled,
            "embedded": True,
            "baseline_tag": baseline_tag,
            "rmax_tag": rmax_tag,
            "unique_patch_count": unique_patch_count,
            "analysis_mode": "cumulative_rmax",
        }
        update_task(task_id, monthly_subtag_results=json.dumps(doc, ensure_ascii=False))
        return doc

    all_patches = list(patch_by_sha.values())
    llm_info: Dict[str, Any] = {}
    if llm_configured:
        if progress_cb:
            progress_cb(
                0, total,
                f"子 tag LLM 分析 r1→rMax {unique_patch_count} 笔…",
            )
        all_patches, llm_info = _run_llm_analysis_on_patches(
            task_id,
            all_patches,
            scoring_config=config,
            force_reanalyze=force_reanalyze,
            link_to_task=False,
            llm_mode="lightweight",
        )
    else:
        all_patches = _run_script_analysis_on_patches(
            all_patches, config, repo, collect_failures, link_to_task=False,
        )

    patch_by_sha = {_patch_identity(p): p for p in all_patches if _patch_identity(p)}

    return finalize_monthly_subtag_from_pool(
        task_id,
        intervals,
        patch_by_sha,
        interval_shas,
        collect_failures,
        baseline_tag,
        rmax_tag,
        progress_cb=progress_cb,
        llm_info=llm_info,
        analysis_mode="cumulative_rmax",
        max_workers=max_workers,
    )


def get_monthly_subtag_interval_patches(
    task_id: str,
    from_tag: str,
    to_tag: str,
) -> Dict[str, Any]:
    """返回某累计子 tag 区间内的 patch 分析详情（优先读持久化 sha 列表）。"""
    from web_app.analyzer_service import _merge_patch_row
    from web_app.database import get_patches_by_shas, get_task
    from web_app.repo_config import get_local_repo_dir

    task = get_task(task_id)
    if not task:
        raise ValueError("任务不存在")

    raw = task.get("monthly_subtag_results") or ""
    if not raw:
        raise ValueError("该任务无子 tag 分析结果")
    try:
        doc = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("子 tag 结果解析失败") from exc

    match: Optional[Dict[str, Any]] = None
    for item in doc.get("intervals") or []:
        if item.get("from_tag") == from_tag and item.get("to_tag") == to_tag:
            match = item
            break
    if not match:
        raise ValueError(f"未找到区间 {from_tag} -> {to_tag}")
    if match.get("status") != "completed":
        raise ValueError(f"区间 {from_tag} -> {to_tag} 未完成分析")

    shas: List[str] = list(match.get("patch_shas") or [])
    if not shas:
        repo = task.get("repo") or ""
        repo_dir = get_local_repo_dir()
        shas = sorted(_commit_sha_set(repo, from_tag, to_tag, repo_dir))

    rows = get_patches_by_shas(shas)
    row_by_sha = {r.get("sha"): r for r in rows if r.get("sha")}
    patches = [_merge_patch_row(row_by_sha[s]) for s in shas if s in row_by_sha]
    patches.sort(key=lambda p: float(p.get("score") or 0))

    missing = [s for s in shas if s not in row_by_sha]
    return {
        "task_id": task_id,
        "from_tag": from_tag,
        "to_tag": to_tag,
        "total_patches": len(shas),
        "loaded_patches": len(patches),
        "missing_shas": missing,
        "stats": match.get("stats") or {},
        "patches": patches,
    }
