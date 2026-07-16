"""GKI 升级死机分析服务 - 分析死机日志并定位问题 patch。"""
import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

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
_TIMING_DIR = Path(__file__).parent.parent / "outputs" / "perf_logs"


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
) -> Tuple[str, Optional[str]]:
    """Create a crash analysis task and launch it in background.
    Returns (crash_id, error_message_if_failed).
    """
    crash_id = uuid.uuid4().hex[:12]
    create_crash_analysis(crash_id, from_tag, to_tag, crash_log)

    _set_crash_progress(crash_id, {
        "status": "pending",
        "message": "死机分析任务已创建...",
    })

    thread = threading.Thread(
        target=_run_crash_analysis,
        args=(crash_id, from_tag, to_tag, crash_log),
        daemon=True,
    )
    thread.start()
    return crash_id, None


def _run_crash_analysis(
    crash_id: str,
    from_tag: str,
    to_tag: str,
    crash_log: str,
) -> None:
    """Execute crash analysis in background thread."""
    import traceback
    from tools.patch_analyzer import fetch_commits_between_tags, run_git
    from web_app.llm_service import (
        _try_parse_crash_analysis,
        analyze_crash_cause,
        find_suspected_patches,
        findFixCommits,
        is_llm_configured,
    )

    _t0 = time.monotonic()

    def _report(phase: str, message: str, **extra):
        data = {
            "status": phase,
            "message": message,
            "elapsed_seconds": int(time.monotonic() - _t0),
            **extra,
        }
        _set_crash_progress(crash_id, data)

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

        # ── Phase 1: 获取提交列表（含文件信息） ──
        _report("fetching", f"获取 {from_tag}..{to_tag} 区间的提交列表...")
        _t_fetch = time.monotonic()
        commits = fetch_commits_between_tags("", from_tag, to_tag, repo_dir=repo_dir)
        patch_list = []
        for c in commits:
            title = c.message.split("\n")[0] if c.message else ""
            # Get files for each commit
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

        # ── Phase 2 & 3: 检测已有分析结果 / 并行执行 squash diff + LLM 死机分析 ──
        import concurrent.futures

        # Try to parse existing analysis result first
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

        if skip_phase1:
            # Already have analysis result — skip Phase 1, only generate squash diff
            _report("crash_analysis",
                    f"识别到已有分析结果，跳过死机原因分析 | "
                    f"类型: {pre_analysis.get('crash_type', '未知')} | "
                    f"函数: {pre_analysis.get('crash_function', '未知')}")
            _log_crash_timing(crash_id, "crash_cause_llm", 0, "skipped_pre_analyzed")

            squash_output, squash_stat = _gen_squash()
            crash_analysis = pre_analysis
            phase1 = {"crash_analysis": pre_analysis}
        else:
            # Normal flow: run squash diff + LLM crash analysis in parallel
            def _analyze_crash():
                """LLM crash analysis (only needs crash log)."""
                _report("crash_analysis", "LLM 分析死机原因...")
                _t_p1 = time.monotonic()
                result = analyze_crash_cause(crash_log=crash_log)
                p1_ms = (time.monotonic() - _t_p1) * 1000
                usage = result.get("usage", {})
                _log_crash_timing(crash_id, "crash_cause_llm", p1_ms,
                                  input_tokens=usage.get("prompt_tokens"),
                                  output_tokens=usage.get("completion_tokens"))
                return result

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                squash_future = pool.submit(_gen_squash)
                crash_future = pool.submit(_analyze_crash)

                squash_output, squash_stat = squash_future.result()
                phase1 = crash_future.result()

            crash_analysis = phase1.get("crash_analysis", {})
            if phase1.get("error"):
                raise RuntimeError(f"死机原因分析失败: {phase1['error']}")

        _report("squash_diff", f"squash diff 完成 ({len(squash_output)} 字符)")
        print(f"[CRASH] squash diff: {len(squash_output)} 字符, stat: {len(squash_stat)} 字符", flush=True)

        _report("crash_analysis",
                f"死机原因: {crash_analysis.get('crash_type', '未知')} | "
                f"崩溃函数: {crash_analysis.get('crash_function', '未知')} | "
                f"模块: {crash_analysis.get('crash_module', '未知')}")

        # ── Phase 4: LLM 归因分析（基于死机原因 + patch 信息） ──
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

        # Combine results
        crash_summary = {
            "crash_type": crash_analysis.get("crash_type", ""),
            "crash_function": crash_analysis.get("crash_function", ""),
            "crash_module": crash_analysis.get("crash_module", ""),
            "call_stack_summary": crash_analysis.get("call_stack_summary", ""),
            "crash_description": crash_analysis.get("crash_description", ""),
            "crash_mechanism": crash_analysis.get("crash_mechanism", ""),
            "crash_files": crash_analysis.get("crash_files", []),
            "crash_symbols": crash_analysis.get("crash_symbols", []),
        }
        is_caused = phase2.get("is_caused_by_merge", False)
        suspected = phase2.get("suspected_patches", [])
        explanation = phase2.get("explanation", "")
        confidence = phase2.get("confidence", "低")
        causation_type = phase2.get("causation_type", "无")
        recommendations = phase2.get("recommendations", {})

        _report("crash_analysis",
                f"归因完成: {'合入代码引起' if is_caused else '非合入代码引起'} | "
                f"置信度: {confidence} | 因果: {causation_type}")

        # Enrich suspected patches with commit info and diff
        _report("enrich", f"获取 {len(suspected)} 笔疑似 patch 的详情...")
        _t_enrich = time.monotonic()
        db_hits = 0
        llm_hits = 0
        for sp in suspected:
            sha = sp.get("sha", "")
            if not sha or len(sha) < 7:
                continue
            # Try to get from database first
            db_patch = get_patch_by_sha(sha)
            if db_patch and db_patch.get("data"):
                data = db_patch["data"]
                sp["commit_message"] = data.get("commit_message", "") or data.get("commit_message_full", "")
                diff_text = data.get("diff_text", "")
                # Truncate if too long
                MAX_PATCH_DIFF = 8000
                if len(diff_text) > MAX_PATCH_DIFF:
                    diff_text = diff_text[:MAX_PATCH_DIFF] + f"\n\n... [truncated, {len(diff_text)} chars total]"
                sp["diff"] = diff_text
                db_hits += 1
                # Check if LLM analysis is available
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
            # Fallback to git
            try:
                # Get full commit message
                msg_out = run_git(repo_dir, [
                    "log", "-1", "--format=%B", sha
                ])
                sp["commit_message"] = msg_out.strip()
                # Get diff (limited to avoid token overflow)
                diff_out = run_git(repo_dir, [
                    "show", "--format=", "--no-color", sha
                ])
                # Truncate diff if too long
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
        _log_crash_timing(crash_id, "enrich", _enrich_ms,
                          db_hits=db_hits, llm_hits=llm_hits)

        # Save intermediate results
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

        # ── Phase 4: 查找修复提交（仅当确认是合入代码引起时） ──
        fix_commits: List[Dict[str, Any]] = []
        _t_fix = time.monotonic()
        if is_caused:
            _report("find_fix", "查找 B tag 之后的修复提交...")
            try:
                # Get commits after B tag (up to ~50 recent commits)
                after_out = run_git(repo_dir, [
                    "log", "--format=%H%x01%s", f"{to_tag}..HEAD", "--max-count=50"
                ])
                commits_after = []
                for line in after_out.strip().split("\n"):
                    if not line.strip():
                        continue
                    parts = line.split("\x01", 1)
                    if len(parts) == 2:
                        commits_after.append({
                            "sha": parts[0],
                            "title": parts[1],
                        })

                if commits_after:
                    _report("find_fix", f"分析 {len(commits_after)} 笔后续提交...")
                    fix_commits = findFixCommits(
                        crash_info=crash_summary,
                        commits_after_b=commits_after,
                        from_tag=from_tag,
                        to_tag=to_tag,
                    )
                    _report("find_fix",
                            f"找到 {len(fix_commits)} 个疑似修复提交",
                            fix_count=len(fix_commits))
                else:
                    _report("find_fix", "B tag 之后无更多提交")
            except Exception as exc:
                print(f"[CRASH] 查找修复提交失败: {exc}", flush=True)
                _report("find_fix", f"查找修复提交失败: {exc}")

        if is_caused:
            _fix_ms = (time.monotonic() - _t_fix) * 1000
            _log_crash_timing(crash_id, "find_fix", _fix_ms,
                              fix_count=len(fix_commits))

        # ── Phase 5: 生成完整报告 ──
        _report("report", "生成分析报告...")
        _t_report = time.monotonic()
        full_report = _build_crash_report(
            crash_id=crash_id,
            from_tag=from_tag,
            to_tag=to_tag,
            crash_log=crash_log,
            crash_summary=crash_summary,
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

    except Exception as exc:
        print(f"[CRASH FATAL] {crash_id}: {exc}", flush=True)
        traceback.print_exc()
        update_crash_analysis(crash_id, status="failed", error_msg=str(exc))
        _set_crash_progress(crash_id, {"status": "failed", "message": str(exc)})


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
                f'<td>{fc.get("reason", "")}</td></tr>'
            )
        fix_html = f"""
        <table class="data-table">
          <thead><tr><th>SHA</th><th>标题</th><th>类型</th><th>置信度</th><th>原因</th></tr></thead>
          <tbody>{"".join(rows)}</tbody>
        </table>"""
    else:
        if is_caused:
            fix_html = "<p>未在 B tag 之后的提交中找到修复</p>"
        else:
            fix_html = "<p class='muted'>（非合入代码引起，未进行修复检查）</p>"

    # Crash log truncated
    crash_log_display = crash_log[:5000]
    if len(crash_log) > 5000:
        crash_log_display += "\n\n... (日志截断)"

    cause_text = "是（由本次合入代码引起）" if is_caused else "否（非合入代码引起）"
    cause_color = "#dc2626" if is_caused else "#059669"

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
  <p class="muted">任务 ID: {crash_id} | 升级区间: {from_tag} → {to_tag} | 合入 patch: {total_patches} 笔</p>

  <div class="summary-grid">
    <div class="card"><div class="card-v">{crash_summary.get('crash_type', '未知')}</div><div class="card-k">死机类型</div></div>
    <div class="card"><div class="card-v">{crash_summary.get('crash_function', '未知')}</div><div class="card-k">崩溃函数</div></div>
    <div class="card"><div class="card-v">{crash_summary.get('crash_module', '未知')}</div><div class="card-k">相关模块</div></div>
    <div class="card"><div class="card-v" style="color:{cause_color}">{cause_text}</div><div class="card-k">是否合入代码引起 | 置信度: {confidence}</div></div>
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
    <div class="info-box {'red' if is_caused else 'green'}">{crash_summary.get('crash_description', '')}</div>
    <h3>归因分析</h3>
    <div class="info-box blue">
      <strong>是否由合入代码引起：</strong>{cause_text}<br/>
      <strong>置信度：</strong>{confidence}<br/>
      <strong>原因：</strong>{explanation}
    </div>
  </div>

  <h2>2. 疑似问题 Patch</h2>
  <div class="section">
    {suspected_html}
  </div>

  <h2>3. 后续修复提交</h2>
  <div class="section">
    {fix_html}
  </div>

  <h2>4. 建议</h2>
  <div class="section">
    <h3>紧急措施</h3>
    <div class="info-box red">{recommendations.get('immediate_actions', '') or '无'}</div>
    <h3>测试验证建议</h3>
    <div class="info-box blue">{recommendations.get('test_suggestions', '') or '无'}</div>
    <h3>后续排查步骤</h3>
    <div class="info-box green">{recommendations.get('next_steps', '') or '无'}</div>
  </div>

  <h2>5. 死机日志</h2>
  <div class="section">
    <div class="crash-log">{crash_log_display}</div>
  </div>
</body>
</html>"""
    return html
