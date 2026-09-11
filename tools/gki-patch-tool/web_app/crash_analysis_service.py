"""GKI 升级死机分析服务 - 分析死机日志并定位问题 patch。"""
import json
import threading
import time
import uuid
from datetime import datetime
from html import escape as html_escape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from web_app.app_paths import outputs_dir, setup_sys_path

setup_sys_path()

from web_app.database import (
    create_crash_analysis,
    get_crash_analysis,
    get_patch_by_sha,
    update_crash_analysis,
)


# ── Progress tracking ─────────────────────────────────
_crash_progress: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()

# ── Performance logging ──────────────────────────────
_TIMING_DIR = outputs_dir("perf_logs")


def _log_crash_timing(
    crash_id: str,
    phase: str,
    elapsed_ms: float,
    status: str = "success",
    **extra,
) -> None:
    """Append a structured timing record for crash analysis to JSONL."""
    record = {
        "ts": datetime.now().isoformat(),
        "crash_id": crash_id,
        "phase": phase,
        "elapsed_ms": round(elapsed_ms, 1),
        "status": status,
    }
    for k, v in extra.items():
        if v is not None:
            record[k] = v
    _TIMING_DIR.mkdir(parents=True, exist_ok=True)
    # Use current date_time as filename
    file_path = _TIMING_DIR / f"crash_{crash_id[:12]}.jsonl"
    try:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 日志写入失败不影响主流程


def get_crash_progress(crash_id: str) -> Dict[str, Any]:
    with _lock:
        return dict(_crash_progress.get(crash_id, {"status": "unknown", "message": ""}))


def _set_crash_progress(crash_id: str, data: Dict[str, Any]) -> None:
    with _lock:
        _crash_progress[crash_id] = data


from web_app.repo_config import get_local_repo_dir

def start_crash_analysis(
    from_tag: str,
    to_tag: str,
    crash_log: str,
    mode: str = "interval",
) -> Tuple[str, Optional[str]]:
    """Create a crash analysis task and launch it in background.

    mode=interval: from_tag..to_tag 归因 + 从 to_tag 搜社区修复
    mode=current_tag: 只分析日志，并从当前 tag 搜到 HEAD 是否已有修复
    """
    mode = (mode or "interval").strip().lower()
    if mode not in ("interval", "current_tag"):
        return "", f"不支持的分析类型: {mode}"
    if mode == "interval":
        if not (from_tag or "").strip() or not (to_tag or "").strip():
            return "", "区间模式需要提供 from_tag 和 to_tag"
    else:
        current = (to_tag or from_tag or "").strip()
        if not current:
            return "", "当前 Tag 模式需要提供当前 GKI tag"
        from_tag = ""
        to_tag = current

    crash_id = uuid.uuid4().hex[:12]
    create_crash_analysis(crash_id, from_tag, to_tag, crash_log)

    _set_crash_progress(crash_id, {
        "status": "pending",
        "message": "死机分析任务已创建...",
        "mode": mode,
    })

    thread = threading.Thread(
        target=_run_crash_analysis,
        args=(crash_id, from_tag, to_tag, crash_log, mode),
        daemon=True,
    )
    thread.start()
    return crash_id, None


def _run_crash_analysis(
    crash_id: str,
    from_tag: str,
    to_tag: str,
    crash_log: str,
    mode: str = "interval",
) -> None:
    """Execute crash analysis in background thread."""
    import traceback
    from tools.patch_analyzer import fetch_commits_between_tags, run_git
    from web_app.llm_service import (
        _try_parse_crash_analysis,
        analyze_crash_cause,
        compare_crash_source_with_latest,
        find_suspected_patches,
        findFixCommits,
        identify_fix_from_source_diffs,
        is_llm_configured,
    )

    _t0 = time.monotonic()

    def _report(phase: str, message: str, **extra):
        elapsed = int(time.monotonic() - _t0)
        data = {
            "status": phase,
            "message": message,
            "elapsed_seconds": elapsed,
            "mode": mode,
            **extra,
        }
        with _lock:
            prev = dict(_crash_progress.get(crash_id) or {})
            steps = list(prev.get("steps") or [])
            last = steps[-1] if steps else None
            if not last or last.get("message") != message or last.get("phase") != phase:
                steps.append({
                    "phase": phase,
                    "message": message,
                    "elapsed_seconds": elapsed,
                })
                if len(steps) > 80:
                    steps = steps[-80:]
            data["steps"] = steps
            _crash_progress[crash_id] = data

    try:
        update_crash_analysis(crash_id, status="analyzing")

        # ── Check LLM ──
        if not is_llm_configured():
            raise RuntimeError("LLM 未配置：请在设置中配置 API Key")

        repo_dir = get_local_repo_dir()
        if not repo_dir:
            raise RuntimeError(
                "未配置本地仓库路径，请在主页「代码路径」中配置，"
                "或设置 GKI_REPO_DIR 环境变量，或将仓库放到 code/common"
            )

        from web_app.crash_fix_search import (
            attach_commit_files,
            collect_fix_candidates,
            resolve_community_search_tips,
        )
        from web_app.crash_source import (
            collect_crash_source,
            collect_source_at_rev,
            file_diff_between,
            list_path_commits,
            pick_latest_compare_tip,
        )

        interval_mode = mode != "current_tag"
        commits: List[Any] = []
        patch_list: List[Dict[str, Any]] = []
        squash_output = ""
        squash_stat = ""
        crash_analysis: Dict[str, Any] = {}
        source_pack: Dict[str, Any] = {}
        suspected: List[Dict[str, Any]] = []
        is_caused = False
        explanation = ""
        confidence = "低"
        causation_type = "无"
        recommendations: Dict[str, Any] = {}

        if interval_mode:
            # ── 获取提交列表（含文件信息） ──
            _report("fetching", f"获取 {from_tag}..{to_tag} 区间的提交列表...")
            _t_fetch = time.monotonic()
            commits = fetch_commits_between_tags("", from_tag, to_tag, repo_dir=repo_dir)
            for c in commits:
                title = c.message.split("\n")[0] if c.message else ""
                try:
                    files_out = run_git(repo_dir, [
                        "diff-tree", "--no-commit-id", "--name-only", "-r", c.sha
                    ])
                    files = [f.strip() for f in files_out.strip().split("\n") if f.strip()]
                except Exception:
                    files = []
                patch_list.append({"sha": c.sha, "title": title, "files": files})
            _fetch_ms = (time.monotonic() - _t_fetch) * 1000
            _log_crash_timing(crash_id, "fetch", _fetch_ms, commit_count=len(commits))
            _report("fetching", f"获取到 {len(commits)} 笔提交")
            print(f"[CRASH] 获取到 {len(commits)} 笔提交, 耗时 {_fetch_ms/1000:.1f}s", flush=True)

        # ── 检测已有分析结果 / 并行 squash + LLM 死机分析 ──
        import concurrent.futures

        pre_analysis = _try_parse_crash_analysis(crash_log)
        skip_phase1 = pre_analysis is not None

        def _gen_squash():
            """Generate squash diff + stat. Reuse cached interval patch if available."""
            from web_app.interval_diff_service import load_interval_diff_cache
            _report("squash_diff", "获取变更统计...")
            _t_sq = time.monotonic()

            sq = ""
            reused = False
            cached = load_interval_diff_cache("", from_tag, to_tag)
            if cached:
                try:
                    sq = cached.squash_file.read_text(encoding="utf-8")
                    reused = True
                    print(
                        f"[CRASH] squash diff 复用缓存: {cached.squash_file.name} "
                        f"({len(sq)} chars, {cached.source})",
                        flush=True,
                    )
                    _report("squash_diff", f"复用已缓存 squash diff ({len(sq)} 字符)")
                except Exception as e:
                    print(f"[CRASH] 读取缓存 squash diff 失败: {e}", flush=True)
                    sq = ""

            if not sq:
                _report("squash_diff", "生成 squash diff...")
                try:
                    sq = run_git(repo_dir, ["diff", "-M", f"{from_tag}..{to_tag}"])
                except Exception as exc:
                    sq = f"(squash diff 生成失败: {exc})"

            try:
                st = run_git(repo_dir, ["diff", "--stat", f"{from_tag}..{to_tag}"])
            except Exception:
                st = ""

            sq_ms = (time.monotonic() - _t_sq) * 1000
            _log_crash_timing(crash_id, "squash_diff", sq_ms,
                              reused="reused" if reused else "generated",
                              size_chars=len(sq))
            return sq, st

        def _analyze_crash():
            _report("crash_analysis", "LLM 分析死机原因...")
            _t_p1 = time.monotonic()
            result = analyze_crash_cause(crash_log=crash_log)
            p1_ms = (time.monotonic() - _t_p1) * 1000
            usage = result.get("usage", {})
            _log_crash_timing(crash_id, "crash_cause_llm", p1_ms,
                              input_tokens=usage.get("prompt_tokens"),
                              output_tokens=usage.get("completion_tokens"))
            return result

        def _source_files_from_analysis(analysis: Dict[str, Any]) -> List[str]:
            files: List[str] = []
            for raw in analysis.get("crash_files") or []:
                text = str(raw or "").strip()
                if text and text not in files:
                    files.append(text)
            path = str(analysis.get("crash_source_path") or "").strip()
            line = int(analysis.get("crash_source_line") or 0)
            if path:
                files.append(f"{path}:{line}" if line else path)
            return files

        def _collect_source_for_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
            func = str(analysis.get("crash_function") or analysis.get("crash_site_function") or "")
            files = _source_files_from_analysis(analysis)
            _report(
                "crash_analysis",
                f"根据分析结果读取崩溃点源码（{func or '未知函数'} @ {to_tag}）...",
            )
            pack = collect_crash_source(
                repo_dir,
                to_tag,
                crash_log,
                extra_files=files,
                function=func,
                source_line=int(analysis.get("crash_source_line") or 0),
            )
            snippets = pack.get("snippets") or []
            if snippets:
                _report("crash_analysis", f"已取出 {len(snippets)} 处源码（{to_tag}）")
            elif pack.get("missing_reason"):
                _report("crash_analysis", str(pack.get("missing_reason")))
            return pack

        def _refine_with_source(analysis: Dict[str, Any], pack: Dict[str, Any]) -> Dict[str, Any]:
            block = str(pack.get("prompt_block") or "")
            if not block or not (pack.get("snippets") or []):
                return analysis
            _report("crash_analysis", "结合源码说明崩溃点...")
            _t_src = time.monotonic()
            refined = analyze_crash_cause(crash_log=crash_log, source_block=block)
            src_ms = (time.monotonic() - _t_src) * 1000
            usage = refined.get("usage", {})
            _log_crash_timing(crash_id, "crash_source_refine_llm", src_ms,
                              input_tokens=usage.get("prompt_tokens"),
                              output_tokens=usage.get("completion_tokens"))
            extra = refined.get("crash_analysis") or {}
            if refined.get("error") or not extra:
                return analysis
            merged = dict(analysis)
            for key in (
                "crash_mechanism",
                "crash_description",
                "crash_source_path",
                "crash_source_statement",
            ):
                if extra.get(key):
                    merged[key] = extra[key]
            if extra.get("crash_source_line"):
                merged["crash_source_line"] = extra["crash_source_line"]
            if extra.get("crash_files"):
                seen = list(merged.get("crash_files") or [])
                for path in extra.get("crash_files") or []:
                    if path and path not in seen:
                        seen.append(path)
                merged["crash_files"] = seen
            return merged

        if skip_phase1:
            _report("crash_analysis",
                    f"识别到已有分析结果，跳过死机原因分析 | "
                    f"类型: {pre_analysis.get('crash_type', '未知')} | "
                    f"函数: {pre_analysis.get('crash_function', '未知')}")
            _log_crash_timing(crash_id, "crash_cause_llm", 0, "skipped_pre_analyzed")
            crash_analysis = pre_analysis
            phase1 = {"crash_analysis": pre_analysis}
            if interval_mode:
                squash_output, squash_stat = _gen_squash()
        elif interval_mode:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                squash_future = pool.submit(_gen_squash)
                crash_future = pool.submit(_analyze_crash)
                squash_output, squash_stat = squash_future.result()
                phase1 = crash_future.result()
            crash_analysis = phase1.get("crash_analysis", {})
            if phase1.get("error"):
                raise RuntimeError(f"死机原因分析失败: {phase1['error']}")
        else:
            phase1 = _analyze_crash()
            crash_analysis = phase1.get("crash_analysis", {})
            if phase1.get("error"):
                raise RuntimeError(f"死机原因分析失败: {phase1['error']}")

        source_pack = _collect_source_for_analysis(crash_analysis)
        crash_analysis = _refine_with_source(crash_analysis, source_pack)

        if interval_mode:
            _report("squash_diff", f"squash diff 完成 ({len(squash_output)} 字符)")
            print(f"[CRASH] squash diff: {len(squash_output)} 字符, stat: {len(squash_stat)} 字符", flush=True)

        _report("crash_analysis",
                f"死机原因: {crash_analysis.get('crash_type', '未知')} | "
                f"崩溃函数: {crash_analysis.get('crash_function', '未知')} | "
                f"模块: {crash_analysis.get('crash_module', '未知')}")

        if interval_mode:
            _report("crash_analysis", "LLM 归因分析: 寻找引入提交...")
            _t_p2 = time.monotonic()
            phase2 = find_suspected_patches(
                crash_analysis=crash_analysis,
                crash_log=crash_log,
                patch_list=patch_list,
                squash_diff=squash_output,
                squash_stat=squash_stat,
                repo_dir=repo_dir,
                from_tag=from_tag,
                to_tag=to_tag,
            )
            if phase2.get("error"):
                raise RuntimeError(f"归因分析失败: {phase2['error']}")
            _p2_ms = (time.monotonic() - _t_p2) * 1000
            _usage2 = phase2.get("usage", {})
            _log_crash_timing(crash_id, "attribution_llm", _p2_ms,
                              input_tokens=_usage2.get("prompt_tokens"),
                              output_tokens=_usage2.get("completion_tokens"),
                              suspected_count=len(phase2.get("suspected_patches", [])))
            is_caused = phase2.get("is_caused_by_merge", False)
            suspected = phase2.get("suspected_patches", [])
            explanation = phase2.get("explanation", "")
            confidence = phase2.get("confidence", "低")
            causation_type = phase2.get("causation_type", "无")
            recommendations = phase2.get("recommendations", {}) or {}
            _report("crash_analysis",
                    f"归因完成: {'合入代码引起' if is_caused else '非合入代码引起'} | "
                    f"置信度: {confidence} | 因果: {causation_type}")

            _report("enrich", f"获取 {len(suspected)} 笔疑似 patch 的详情...")
            _t_enrich = time.monotonic()
            db_hits = 0
            llm_hits = 0
            for sp in suspected:
                sha = sp.get("sha", "")
                if not sha or len(sha) < 7:
                    continue
                db_patch = get_patch_by_sha(sha)
                if db_patch and db_patch.get("data"):
                    data = db_patch["data"]
                    sp["commit_message"] = data.get("commit_message", "") or data.get("commit_message_full", "")
                    diff_text = data.get("diff_text", "")
                    MAX_PATCH_DIFF = 8000
                    if len(diff_text) > MAX_PATCH_DIFF:
                        diff_text = diff_text[:MAX_PATCH_DIFF] + f"\n\n... [truncated, {len(diff_text)} chars total]"
                    sp["diff"] = diff_text
                    db_hits += 1
                    if data.get("llm_analyzed"):
                        sp["llm_analysis"] = {
                            "score": data.get("score", 0),
                            "recommendation": data.get("recommendation", ""),
                            "key_risk": data.get("key_risk", ""),
                            "summary": (data.get("commit_interpretation_rich") or {}).get("summary", ""),
                            "code_changes": (data.get("code_change_analysis_rich") or {}).get("logic_changes", []),
                            "problem_solved": (data.get("problem_closure_rich") or {}).get("conclusion", ""),
                            "introducer": (data.get("problem_introducer_rich") or {}).get("summary", ""),
                            "test_suggestions": data.get("llm_test_suggestions", ""),
                            "score_details": data.get("score_details", {}),
                        }
                        llm_hits += 1
                    print(f"[CRASH] patch {sha[:12]} 从数据库复用 (LLM: {'有' if data.get('llm_analyzed') else '无'})", flush=True)
                    continue
                try:
                    msg_out = run_git(repo_dir, ["log", "-1", "--format=%B", sha])
                    sp["commit_message"] = msg_out.strip()
                    diff_out = run_git(repo_dir, ["show", "--format=", "--no-color", sha])
                    MAX_PATCH_DIFF = 8000
                    if len(diff_out) > MAX_PATCH_DIFF:
                        diff_out = diff_out[:MAX_PATCH_DIFF] + f"\n\n... [truncated, {len(diff_out)} chars total]"
                    sp["diff"] = diff_out.strip()
                except Exception as e:
                    print(f"[CRASH] 获取 patch {sha[:12]} 详情失败: {e}", flush=True)
                    sp["commit_message"] = ""
                    sp["diff"] = ""
            if db_hits > 0:
                _report("enrich", f"{len(suspected)} 笔疑似 patch 中有 {db_hits} 笔复用数据库数据，{llm_hits} 笔有 LLM 分析")
            _enrich_ms = (time.monotonic() - _t_enrich) * 1000
            _log_crash_timing(crash_id, "enrich", _enrich_ms, db_hits=db_hits, llm_hits=llm_hits)
        else:
            explanation = "当前 Tag 模式：不分析区间引入，仅判断社区/谷歌后续提交是否已有修复。"
            confidence = "中"
            causation_type = "无"
            recommendations = {
                "immediate_actions": "对照崩溃函数与社区修复提交，确认本机 kernel 是否已包含对应 SHA。",
                "test_suggestions": "若找到修复，合入或升到包含该提交的 GKI tag 后复现验证。",
                "next_steps": "无社区修复时，继续用崩溃文件/符号在本地仓库排查。",
            }

        crash_summary = {
            "crash_type": crash_analysis.get("crash_type", ""),
            "bug_class": crash_analysis.get("bug_class", ""),
            "crash_function": crash_analysis.get("crash_function", ""),
            "crash_site_function": crash_analysis.get("crash_site_function", ""),
            "crash_module": crash_analysis.get("crash_module", ""),
            "pc_symbol": crash_analysis.get("pc_symbol", ""),
            "fault_addr": crash_analysis.get("fault_addr", ""),
            "call_stack_summary": crash_analysis.get("call_stack_summary", ""),
            "crash_description": crash_analysis.get("crash_description", ""),
            "crash_mechanism": crash_analysis.get("crash_mechanism", ""),
            "crash_files": crash_analysis.get("crash_files", []),
            "crash_symbols": crash_analysis.get("crash_symbols", []),
            "evidence": crash_analysis.get("evidence", []),
            "analysis_mode": mode,
            "source_tag": to_tag,
            "crash_source_path": crash_analysis.get("crash_source_path", "") or "",
            "crash_source_line": crash_analysis.get("crash_source_line", 0) or 0,
            "crash_source_statement": crash_analysis.get("crash_source_statement", "") or "",
            "crash_source_snippets": source_pack.get("snippets") or [],
            "source_missing_reason": source_pack.get("missing_reason") or "",
        }

        crash_summary_with_meta = dict(crash_summary)
        crash_summary_with_meta["explanation"] = explanation
        crash_summary_with_meta["confidence"] = confidence
        crash_summary_with_meta["causation_type"] = causation_type
        update_crash_analysis(
            crash_id,
            crash_summary=json.dumps(crash_summary_with_meta, ensure_ascii=False),
            suspected_patches=json.dumps(suspected, ensure_ascii=False),
            is_caused_by_merge=1 if is_caused else 0,
            recommendations=json.dumps(recommendations, ensure_ascii=False),
        )

        # ── 对照社区最新源码，必要时再按文件 diff 定位修复 ──
        search_tag = to_tag
        fix_commits: List[Dict[str, Any]] = []
        _t_fix = time.monotonic()
        _report("find_fix", f"拉取社区最新源码，对照 {search_tag} 崩溃点...")
        try:
            resolved = resolve_community_search_tips(
                repo_dir, search_tag, on_progress=lambda message: _report("find_fix", message),
            ) if search_tag else {}
            tip = pick_latest_compare_tip(resolved, search_tag)
            latest_rev = str(tip.get("sha") or "")
            latest_ref = str(tip.get("ref") or latest_rev or "HEAD")
            crash_snips = list(source_pack.get("snippets") or [])
            latest_pack = collect_source_at_rev(
                repo_dir,
                latest_rev,
                crash_snips,
                function=str(crash_analysis.get("crash_function") or source_pack.get("function") or ""),
            ) if crash_snips and latest_rev else {
                "snippets": [],
                "prompt_block": "",
                "missing_reason": "没有崩溃点源码或社区最新 revision",
            }
            file_diffs: List[Dict[str, str]] = []
            for item in crash_snips:
                path = str(item.get("path") or "")
                if not path:
                    continue
                diff_text = file_diff_between(repo_dir, search_tag, latest_rev, path)
                if diff_text:
                    file_diffs.append({"path": path, "diff": diff_text})

            compare: Dict[str, Any] = {
                "still_present": True,
                "latest_status": "cannot_compare",
                "confidence": "低",
                "summary": latest_pack.get("missing_reason") or "未能对照最新源码",
                "code_change": "",
                "fix_evidence": "",
            }
            if crash_snips and latest_pack.get("prompt_block") and not all(
                item.get("missing") for item in (latest_pack.get("snippets") or [])
            ):
                _report("find_fix", f"LLM 对照崩溃点与 {latest_ref} 源码...")
                compare = compare_crash_source_with_latest(
                    crash_analysis=crash_analysis,
                    crash_tag=search_tag,
                    latest_ref=latest_ref,
                    crash_source_block=str(source_pack.get("prompt_block") or ""),
                    latest_source_block=str(latest_pack.get("prompt_block") or ""),
                    file_diffs=file_diffs,
                )
                _report(
                    "find_fix",
                    f"最新源码结论: {compare.get('latest_status')} | {compare.get('summary') or ''}",
                )

            crash_summary_with_meta["latest_compare"] = {
                **compare,
                "latest_ref": latest_ref,
                "latest_rev": latest_rev,
                "latest_branch": tip.get("branch") or "",
            }
            crash_summary_with_meta["latest_source_snippets"] = latest_pack.get("snippets") or []
            crash_summary_with_meta["latest_source_missing"] = latest_pack.get("missing_reason") or ""

            used_source_diff = False
            if compare.get("latest_status") == "likely_fixed":
                paths = [str(item.get("path") or "") for item in crash_snips if item.get("path")]
                _report("find_fix", "最新代码已避开该路径，正在分析后续提交 diff...")
                history_commits = list_path_commits(
                    repo_dir,
                    search_tag,
                    latest_rev,
                    paths,
                    function=str(crash_analysis.get("crash_function") or source_pack.get("function") or ""),
                )
                _report("find_fix", f"崩溃文件后续 {len(history_commits)} 笔提交，送模型读 diff")
                if history_commits:
                    fix_commits = identify_fix_from_source_diffs(
                        crash_analysis=crash_analysis,
                        compare=compare,
                        commits=history_commits,
                        crash_tag=search_tag,
                        latest_ref=latest_ref,
                    )
                    used_source_diff = bool(fix_commits)
                    if fix_commits:
                        _report("find_fix", f"从源码 diff 定位到 {len(fix_commits)} 笔修复", fix_count=len(fix_commits))

            if not fix_commits and compare.get("latest_status") == "still_buggy":
                _report("find_fix", "最新源码仍可能存在该问题，不再把后续提交判成修复")
                crash_summary_with_meta["fix_search"] = {
                    "search_from_tag": search_tag,
                    "search_to_ref": latest_ref,
                    "search_to_rev": latest_rev,
                    "commits_after_tag": int(resolved.get("count") or 0),
                    "candidates": 0,
                    "crash_files": [str(item.get("path") or "") for item in crash_snips],
                    "strategy": "source_compare_still_buggy",
                    "fetched": bool(resolved.get("fetched")),
                    "fetch_source": str(resolved.get("fetch_source") or ""),
                    "fetched_branches": list(resolved.get("fetched_branches") or []),
                }
            elif not fix_commits:
                _report("find_fix", "改用崩溃文件/标题检索社区后续提交...")
                candidates, search_meta = collect_fix_candidates(
                    repo_dir,
                    search_tag,
                    crash_analysis=crash_analysis,
                    suspected=suspected,
                    crash_log=crash_log,
                    on_progress=lambda message: _report("find_fix", message),
                    resolved=resolved,
                )
                search_meta["strategy"] = (
                    "source_compare_then_titles" if compare.get("latest_status") else search_meta.get("strategy")
                )
                crash_summary_with_meta["fix_search"] = search_meta
                total_after = int(search_meta.get("commits_after_tag") or 0)
                end_ref = str(search_meta.get("search_to_ref") or latest_ref or "HEAD")
                if candidates:
                    if any(not (c.get("files") or []) for c in candidates):
                        candidates = attach_commit_files(repo_dir, candidates)
                    crash_info_for_fix = dict(crash_summary)
                    crash_info_for_fix["suspected_patches"] = suspected
                    title_hits = findFixCommits(
                        crash_info=crash_info_for_fix,
                        commits_after_b=candidates,
                        from_tag=from_tag,
                        to_tag=to_tag,
                        search_from_tag=search_tag,
                        search_to_rev=str(search_meta.get("search_to_rev") or latest_rev),
                        total_after_tag=total_after,
                        on_progress=lambda message: _report("find_fix", message),
                    )
                    for row in title_hits:
                        row["via"] = row.get("via") or "title"
                    fix_commits = title_hits
                    _report("find_fix", f"标题检索找到 {len(fix_commits)} 个疑似修复提交", fix_count=len(fix_commits))
                elif total_after == 0:
                    _report("find_fix", search_meta.get("empty_reason") or f"{search_tag} 之后没有更新提交")
                else:
                    _report("find_fix", f"崩溃相关文件在 {search_tag}..{end_ref} 没有后续改动")
            else:
                crash_summary_with_meta["fix_search"] = {
                    "search_from_tag": search_tag,
                    "search_to_ref": latest_ref,
                    "search_to_rev": latest_rev,
                    "commits_after_tag": int(resolved.get("count") or 0),
                    "candidates": len(fix_commits),
                    "crash_files": [str(item.get("path") or "") for item in crash_snips],
                    "strategy": "source_compare_and_diff",
                    "fetched": bool(resolved.get("fetched")),
                    "fetch_source": str(resolved.get("fetch_source") or ""),
                    "fetched_branches": list(resolved.get("fetched_branches") or []),
                }

            if used_source_diff:
                crash_summary_with_meta.setdefault("fix_search", {})["strategy"] = "source_compare_and_diff"
        except Exception as exc:
            print(f"[CRASH] 查找修复提交失败: {exc}", flush=True)
            _report("find_fix", f"查找修复提交失败: {exc}")

        _fix_ms = (time.monotonic() - _t_fix) * 1000
        _log_crash_timing(crash_id, "find_fix", _fix_ms, fix_count=len(fix_commits))

        update_crash_analysis(
            crash_id,
            crash_summary=json.dumps(crash_summary_with_meta, ensure_ascii=False),
        )

        # ── Phase 5: 生成完整报告 ──
        _report("report", "生成分析报告...")
        _t_report = time.monotonic()
        full_report = _build_crash_report(
            crash_id=crash_id,
            from_tag=from_tag,
            to_tag=to_tag,
            crash_log=crash_log,
            crash_summary=crash_summary_with_meta,
            is_caused=is_caused,
            confidence=confidence,
            explanation=explanation,
            suspected=suspected,
            fix_commits=fix_commits,
            recommendations=recommendations,
            total_patches=len(commits),
        )

        _report_ms = (time.monotonic() - _t_report) * 1000
        _log_crash_timing(crash_id, "report", _report_ms)

        # ── Finalize ──
        _elapsed = time.monotonic() - _t0
        _log_crash_timing(crash_id, "overall", _elapsed * 1000,
                          from_tag=from_tag, to_tag=to_tag,
                          is_caused=is_caused, confidence=confidence)
        update_crash_analysis(
            crash_id,
            status="completed",
            fix_commits=json.dumps(fix_commits, ensure_ascii=False),
            full_report=full_report,
            elapsed_seconds=round(_elapsed, 1),
            completed_at=datetime.now().isoformat(),
        )

        _set_crash_progress(crash_id, {
            "status": "completed",
            "message": f"分析完成 | 耗时 {int(_elapsed)}s",
            "elapsed_seconds": int(_elapsed),
        })
        print(f"[CRASH] 分析完成: {crash_id}, 耗时 {_elapsed:.0f}s", flush=True)
        from web_app.feishu_service import try_notify_crash_finished
        try_notify_crash_finished(crash_id, status="completed")

    except Exception as exc:
        print(f"[CRASH FATAL] {crash_id}: {exc}", flush=True)
        traceback.print_exc()
        update_crash_analysis(crash_id, status="failed", error_msg=str(exc))
        _set_crash_progress(crash_id, {"status": "failed", "message": str(exc)})
        from web_app.feishu_service import try_notify_crash_finished
        try_notify_crash_finished(crash_id, status="failed")


def _build_crash_report(
    crash_id: str,
    from_tag: str,
    to_tag: str,
    crash_log: str,
    crash_summary: Dict[str, Any],
    is_caused: bool,
    confidence: str,
    explanation: str,
    suspected: List[Dict[str, Any]],
    fix_commits: List[Dict[str, Any]],
    recommendations: Dict[str, Any],
    total_patches: int,
) -> str:
    """Build a full HTML report for the crash analysis."""

    current_tag_mode = (crash_summary.get("analysis_mode") == "current_tag") or not from_tag
    search_meta = crash_summary.get("fix_search") or {}
    search_note = ""
    if search_meta.get("search_from_tag"):
        end_label = search_meta.get("search_to_ref") or "HEAD"
        search_note = (
            f"{search_meta.get('search_from_tag')}..{end_label}"
            f"（共 {search_meta.get('commits_after_tag', 0)} 笔，"
            f"筛出 {search_meta.get('candidates', 0)} 笔候选）"
        )

    source_html = ""
    snippets = crash_summary.get("crash_source_snippets") or []
    source_tag = crash_summary.get("source_tag") or to_tag
    statement = crash_summary.get("crash_source_statement") or ""
    if snippets:
        blocks = []
        for item in snippets:
            loc = html_escape(str(item.get("path") or ""))
            line = item.get("line") or 0
            loc_label = f"{loc}:{line}" if line else loc
            body = html_escape(str(item.get("text") or ""))
            if item.get("missing"):
                blocks.append(f"<p class='muted'>{loc_label}：仓库中未能取出该文件</p>")
            else:
                blocks.append(
                    f"<h3>{loc_label}</h3><pre class='crash-log'>{body}</pre>"
                )
        statement_html = (
            f"<div class='info-box blue'><strong>死在：</strong>{html_escape(str(statement))}</div>"
            if statement else ""
        )
        source_html = f"""
    <h3>崩溃点源码（{html_escape(str(source_tag))}）</h3>
    {statement_html}
    {''.join(blocks)}
"""
    elif crash_summary.get("source_missing_reason"):
        source_html = f"<p class='muted'>{html_escape(str(crash_summary.get('source_missing_reason')))}</p>"

    compare = crash_summary.get("latest_compare") or {}
    latest_html = ""
    if compare.get("latest_status") or compare.get("summary"):
        status = str(compare.get("latest_status") or "")
        status_label = {
            "likely_fixed": "最新源码已避开该崩溃路径",
            "still_buggy": "最新源码仍可能存在该问题",
            "cannot_compare": "未能对照最新源码",
        }.get(status, status or "未知")
        box_cls = "green" if status == "likely_fixed" else ("red" if status == "still_buggy" else "blue")
        latest_blocks = []
        for item in crash_summary.get("latest_source_snippets") or []:
            loc = html_escape(str(item.get("path") or ""))
            body = html_escape(str(item.get("text") or ""))
            if item.get("missing"):
                latest_blocks.append(f"<p class='muted'>{loc}：最新 revision 未能取出</p>")
            elif body:
                latest_blocks.append(f"<h3>{loc}（最新）</h3><pre class='crash-log'>{body}</pre>")
        latest_html = f"""
    <h3>对照社区最新源码（{html_escape(str(compare.get('latest_ref') or ''))}）</h3>
    <div class="info-box {box_cls}"><strong>{html_escape(status_label)}</strong>
    <br/>{html_escape(str(compare.get('summary') or ''))}
    {f"<br/><strong>代码变化：</strong>{html_escape(str(compare.get('code_change')))}" if compare.get('code_change') else ""}
    {f"<br/><strong>依据：</strong>{html_escape(str(compare.get('fix_evidence')))}" if compare.get('fix_evidence') else ""}
    </div>
    {''.join(latest_blocks)}
"""

    mechanism = crash_summary.get("crash_mechanism") or ""
    mechanism_html = (
        f"<h3>机制说明</h3><div class='info-box blue'>{html_escape(str(mechanism))}</div>"
        if mechanism else ""
    )

    # Suspected patches HTML
    suspected_html = ""
    if suspected:
        rows = []
        for sp in suspected:
            rows.append(
                f'<tr><td><code>{sp.get("sha", "")[:12]}</code></td>'
                f'<td>{sp.get("title", "")}</td>'
                f'<td>{sp.get("reason", "")}</td>'
                f'<td><code>{sp.get("related_files", "")}</code></td></tr>'
            )
        suspected_html = f"""
        <table class="data-table">
          <thead><tr><th>SHA</th><th>标题</th><th>可疑原因</th><th>相关文件</th></tr></thead>
          <tbody>{"".join(rows)}</tbody>
        </table>"""
    else:
        suspected_html = "<p>未识别出疑似问题 patch</p>"

    # Fix commits HTML
    fix_html = ""
    if fix_commits:
        rows = []
        for fc in fix_commits:
            rows.append(
                f'<tr><td><code>{fc.get("sha", "")[:12]}</code></td>'
                f'<td>{fc.get("title", "")}</td>'
                f'<td><span class="badge badge-{fc.get("fix_type", "")}">{fc.get("fix_type", "")}</span></td>'
                f'<td><span class="badge badge-conf-{fc.get("confidence", "")}">{fc.get("confidence", "")}</span></td>'
                f'<td>{fc.get("reason", "")}</td>'
                f'<td>{("源码 diff" if fc.get("via") == "source_diff" else "标题检索")}</td></tr>'
            )
        fix_html = f"""
        <table class="data-table">
          <thead><tr><th>SHA</th><th>标题</th><th>类型</th><th>置信度</th><th>原因</th><th>依据</th></tr></thead>
          <tbody>{"".join(rows)}</tbody>
        </table>"""
    else:
        if search_meta.get("commits_after_tag") == 0:
            reason = search_meta.get("empty_reason") or (
                "本地没有比该 Tag 更新的同系列提交。请 fetch 社区/谷歌对应分支后再查。"
            )
            fix_html = f"<p class='muted'>{reason}</p>"
        else:
            extra = f"<p class='muted'>检索范围：{search_note}</p>" if search_note else ""
            if (crash_summary.get("latest_compare") or {}).get("latest_status") == "still_buggy":
                fix_html = extra + "<p>最新源码仍可能走这次崩溃路径，未将后续提交判定为修复</p>"
            else:
                fix_html = extra + "<p>未在当前 Tag 至社区/谷歌最新提交中找到与本次崩溃相关的修复</p>"

    # Crash log truncated
    crash_log_display = crash_log[:5000]
    if len(crash_log) > 5000:
        crash_log_display += "\n\n... (日志截断)"

    if current_tag_mode:
        latest_status = str((crash_summary.get("latest_compare") or {}).get("latest_status") or "")
        if fix_commits:
            cause_text = "已找到社区/谷歌修复"
            cause_color = "#059669"
        elif latest_status == "likely_fixed":
            cause_text = "最新源码已避开，未定位到具体提交"
            cause_color = "#059669"
        elif latest_status == "still_buggy":
            cause_text = "最新源码仍可能有该问题"
            cause_color = "#d97706"
        else:
            cause_text = "未找到社区/谷歌修复"
            cause_color = "#d97706"
        interval_label = f"当前 Tag: {to_tag}"
        patch_count_label = "查社区修复"
    else:
        cause_text = "是（由本次合入代码引起）" if is_caused else "否（非合入代码引起）"
        cause_color = "#dc2626" if is_caused else "#059669"
        interval_label = f"{from_tag} → {to_tag}"
        patch_count_label = f"合入 patch: {total_patches} 笔"

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>GKI 升级死机分析报告</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #1f2937; background: #f8fafc; }}
    h1 {{ font-size: 22px; margin: 0 0 16px 0; }}
    h2 {{ font-size: 16px; margin: 20px 0 10px 0; color: #1e293b; border-bottom: 2px solid #e5e7eb; padding-bottom: 6px; }}
    h3 {{ font-size: 14px; margin: 14px 0 6px 0; color: #334155; }}
    .muted {{ color: #6b7280; font-size: 13px; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 16px 0; }}
    .card {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; background: #fff; }}
    .card-v {{ font-size: 20px; font-weight: 700; margin-bottom: 4px; }}
    .card-k {{ font-size: 12px; color: #6b7280; }}
    .section {{ margin-bottom: 16px; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; }}
    .data-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    .data-table th {{ text-align: left; padding: 8px; background: #f1f5f9; border-bottom: 2px solid #e2e8f0; font-weight: 600; }}
    .data-table td {{ padding: 8px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }}
    .data-table tr:hover {{ background: #f8fafc; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; }}
    .badge-revert {{ background: #fee2e2; color: #991b1b; }}
    .badge-fix {{ background: #dcfce7; color: #166534; }}
    .badge-其他 {{ background: #f3f4f6; color: #4b5563; }}
    .badge-conf-高 {{ background: #dcfce7; color: #166534; }}
    .badge-conf-中 {{ background: #fef3c7; color: #92400e; }}
    .badge-conf-低 {{ background: #f3f4f6; color: #4b5563; }}
    .crash-log {{ background: #1e293b; color: #e2e8f0; padding: 12px; border-radius: 6px; font-family: ui-monospace, monospace; font-size: 12px; line-height: 1.5; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }}
    .cause-yes {{ color: #dc2626; font-weight: 700; }}
    .cause-no {{ color: #059669; font-weight: 700; }}
    .info-box {{ padding: 12px; border-radius: 6px; margin: 8px 0; font-size: 13px; line-height: 1.6; }}
    .info-box.red {{ background: #fef2f2; border: 1px solid #fecaca; }}
    .info-box.green {{ background: #f0fdf4; border: 1px solid #bbf7d0; }}
    .info-box.blue {{ background: #eff6ff; border: 1px solid #bfdbfe; }}
    .kv-grid {{ display: grid; grid-template-columns: 120px 1fr; gap: 4px 12px; font-size: 13px; }}
    .kv-grid dt {{ color: #64748b; font-weight: 500; }}
    .kv-grid dd {{ color: #1e293b; margin: 0; }}
  </style>
</head>
<body>
  <h1>GKI 升级死机分析报告</h1>
  <p class="muted">任务 ID: {crash_id} | {interval_label} | {patch_count_label}</p>

  <div class="summary-grid">
    <div class="card"><div class="card-v">{crash_summary.get('crash_type', '未知')}</div><div class="card-k">死机类型</div></div>
    <div class="card"><div class="card-v">{crash_summary.get('crash_function', '未知')}</div><div class="card-k">崩溃函数</div></div>
    <div class="card"><div class="card-v">{crash_summary.get('crash_module', '未知')}</div><div class="card-k">相关模块</div></div>
    <div class="card"><div class="card-v" style="color:{cause_color}">{cause_text}</div><div class="card-k">{"社区修复" if current_tag_mode else f"是否合入代码引起 | 置信度: {confidence}"}</div></div>
  </div>

  <h2>1. 死机分析</h2>
  <div class="section">
    <dl class="kv-grid">
      <dt>死机类型</dt><dd>{crash_summary.get('crash_type', '')}</dd>
      <dt>崩溃函数</dt><dd>{crash_summary.get('crash_function', '')}</dd>
      <dt>相关模块</dt><dd>{crash_summary.get('crash_module', '')}</dd>
      <dt>调用栈摘要</dt><dd><code>{crash_summary.get('call_stack_summary', '')}</code></dd>
    </dl>
    <h3>死机现象描述</h3>
    <div class="info-box {'blue' if current_tag_mode else ('red' if is_caused else 'green')}">{crash_summary.get('crash_description', '')}</div>
    {mechanism_html}
    {source_html}
    {latest_html}
    <h3>{"检索说明" if current_tag_mode else "归因分析"}</h3>
    <div class="info-box blue">
      {"" if current_tag_mode else f"<strong>是否由合入代码引起：</strong>{cause_text}<br/><strong>置信度：</strong>{confidence}<br/>"}
      <strong>原因：</strong>{explanation}
      {f"<br/><strong>检索范围：</strong>{search_note}" if search_note else ""}
    </div>
  </div>

  {"" if current_tag_mode else f'''
  <h2>2. 疑似问题 Patch</h2>
  <div class="section">
    {suspected_html}
  </div>
  '''}

  <h2>{"2" if current_tag_mode else "3"}. 后续修复提交</h2>
  <div class="section">
    {f'<p class="muted">检索范围：{search_note}</p>' if search_note and fix_commits else ""}
    {fix_html}
  </div>

  <h2>{"3" if current_tag_mode else "4"}. 建议</h2>
  <div class="section">
    <h3>紧急措施</h3>
    <div class="info-box red">{recommendations.get('immediate_actions', '') or '无'}</div>
    <h3>测试验证建议</h3>
    <div class="info-box blue">{recommendations.get('test_suggestions', '') or '无'}</div>
    <h3>后续排查步骤</h3>
    <div class="info-box green">{recommendations.get('next_steps', '') or '无'}</div>
  </div>

  <h2>{"4" if current_tag_mode else "5"}. 死机日志</h2>
  <div class="section">
    <div class="crash-log">{crash_log_display}</div>
  </div>
</body>
</html>"""
    return html
