"""FastAPI 服务端 - REST API + WebSocket 实时进度推送。"""
import asyncio
import json
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# Ensure web_app package is importable
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from web_app.analyzer_service import (
    DEFAULT_CONFIG,
    get_progress,
    get_task_with_patches,
    is_llm_running,
    start_analysis,
    start_llm_analysis,
)
from web_app.crash_analysis_service import (
    get_crash_progress,
    start_crash_analysis,
)
from web_app.database import (
    delete_task as db_delete_task,
    get_patch,
    get_patches_by_task,
    get_task,
    get_all_module_stats,
    get_crash_analysis,
    list_crash_analyses,
    delete_crash_analysis,
    init_db,
    list_all_patches,
    list_tasks,
    get_upgrade_job,
    list_upgrade_jobs,
    delete_upgrade_job,
)
from web_app.llm_service import is_llm_configured, save_llm_config
from render_report_llm import render_patch
from web_app.task_report import build_task_report_html, render_monthly_analysis_html

# ── App ────────────────────────────────────────────────
app = FastAPI(title="GKI Patch 分析平台", version="1.0.0")

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
_FRONTEND_DIST = _PROJECT_ROOT / "frontend" / "dist"
_FRONTEND_ASSETS = _FRONTEND_DIST / "assets"

if _FRONTEND_ASSETS.is_dir():
    app.mount("/app/assets", StaticFiles(directory=_FRONTEND_ASSETS), name="vue-assets")


# ── Startup ────────────────────────────────────────────
@app.on_event("startup")
def _startup():
    init_db()


# ── API: Start analysis ────────────────────────────────
@app.post("/api/analyze")
async def api_analyze(body: Dict[str, Any]):
    sha = str(body.get("sha", "") or "").strip()
    from_tag = str(body.get("from_tag", "") or "").strip()
    to_tag = str(body.get("to_tag", "") or "").strip()
    repo = str(body.get("repo", "https://android.googlesource.com/kernel/common") or "").strip()
    config = body.get("config", DEFAULT_CONFIG)
    task_type = body.get("type", "range")
    sample_raw = body.get("sample_size", 0)
    try:
        # 空值 / 未传 = 0，表示全量分析；仅显式传入正整数时采样
        sample_size = int(sample_raw) if sample_raw not in (None, "") else 0
    except (TypeError, ValueError):
        raise HTTPException(400, "sample_size 必须是整数")
    if sample_size < 0:
        raise HTTPException(400, "sample_size 不能为负数")
    force_reanalyze = bool(body.get("force_reanalyze", False))
    # 跨月升级到目标月时做子 tag 推荐；同月两个 _rN 区间由主任务覆盖，不再单独拉子 tag
    auto_extend = 1

    if task_type == "single":
        if not sha:
            raise HTTPException(400, "单 SHA 分析需要提供 sha 参数")
        task_id, err = start_analysis("single", repo, config, sha=sha,
                                       force_reanalyze=force_reanalyze)
    else:
        if not from_tag or not to_tag:
            raise HTTPException(400, "区间分析需要提供 from_tag 和 to_tag 参数")
        task_id, err = start_analysis("range", repo, config,
                                       from_tag=from_tag, to_tag=to_tag,
                                       sample_size=sample_size,
                                       force_reanalyze=force_reanalyze,
                                       auto_extend=auto_extend)
    if err:
        raise HTTPException(500, err)
    return {"task_id": task_id}


# ── API: List tasks ────────────────────────────────────
@app.get("/api/tasks")
async def api_list_tasks(limit: int = Query(50, ge=1, le=200)):
    return {"tasks": list_tasks(limit)}


# ── API: Get task detail ───────────────────────────────
@app.get("/api/tasks/{task_id}")
async def api_get_task(task_id: str, dev_module: str = Query("", description="按开发模块筛选")):
    task = get_task_with_patches(task_id, dev_module=dev_module)
    if not task:
        raise HTTPException(404, "任务不存在")
    return task


# ── API: Get task module stats ──────────────────────────
@app.get("/api/tasks/{task_id}/module-stats")
async def api_task_module_stats(task_id: str):
    from web_app.database import get_task_module_stats, get_task
    if not get_task(task_id):
        raise HTTPException(404, "任务不存在")
    return {"stats": get_task_module_stats(task_id)}


# ── API: Get task module analysis ─────────────────────
@app.get("/api/tasks/{task_id}/modules")
async def api_task_module_analysis(task_id: str):
    import json
    from web_app.database import get_task
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    raw = task.get("module_summaries", "") or ""
    if not raw:
        return {"module_count": 0, "modules": {}}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        data = {"module_count": 0, "modules": {}}
    return data


@app.get("/api/tasks/{task_id}/monthly-subtag-patches")
async def api_monthly_subtag_patches(
    task_id: str,
    from_tag: str = Query(..., description="子 tag 区间起点"),
    to_tag: str = Query(..., description="子 tag 区间终点"),
):
    """获取某累计子 tag 区间内全部 patch 的分析详情。"""
    from web_app.database import get_task
    from web_app.monthly_subtag_service import get_monthly_subtag_interval_patches

    if not get_task(task_id):
        raise HTTPException(404, "任务不存在")
    try:
        return get_monthly_subtag_interval_patches(task_id, from_tag, to_tag)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


# ── API: Extend comparison stats ──────────────────────────
@app.get("/api/tasks/{task_id}/extend-stats")
async def api_extend_stats(task_id: str):
    """Get auto-extend comparison statistics for a range task."""
    import json as _json

    from web_app.analyzer_service import build_monthly_tag_recommendation, get_progress
    from web_app.database import get_cross_range_overlap, get_range_comparison_stats, get_task

    prog = get_progress(task_id)
    if not prog:
        raise HTTPException(404, "任务不存在")

    task = get_task(task_id) or {}
    raw = task.get("monthly_subtag_results") or ""
    if raw:
        try:
            doc = _json.loads(raw) if isinstance(raw, str) else dict(raw)
            if doc.get("embedded") and doc.get("intervals"):
                from web_app.monthly_subtag_service import (
                    build_monthly_tag_recommendation_from_results,
                )
                stats = [
                    item["stats"]
                    for item in doc.get("intervals") or []
                    if item.get("status") == "completed" and item.get("stats")
                ]
                recommendation = build_monthly_tag_recommendation_from_results(
                    doc.get("intervals") or [],
                )
                intervals = [
                    {
                        "from_tag": item.get("from_tag", ""),
                        "to_tag": item.get("to_tag", ""),
                        "task_id": task_id,
                        "status": item.get("status", ""),
                    }
                    for item in (doc.get("intervals") or [])
                ]
                return {
                    "has_extend": True,
                    "embedded": True,
                    "range_stats": stats,
                    "overlap": {},
                    "monthly_intervals": intervals,
                    "monthly_recommendation": recommendation,
                    "running": 0,
                    "completed": doc.get("completed", 0),
                    "failed": doc.get("failed", 0),
                    "total": doc.get("interval_count", len(intervals)),
                }
        except (_json.JSONDecodeError, TypeError, KeyError):
            pass

    extend_ids = prog.get("extend_task_ids", [])
    if not extend_ids:
        monthly = prog.get("monthly_recommendation")
        if not monthly:
            try:
                monthly = build_monthly_tag_recommendation([task_id])
            except Exception:
                monthly = None
        if monthly and monthly.get("has_recommendation"):
            return {
                "has_extend": True,
                "embedded": True,
                "range_stats": monthly.get("range_stats") or [],
                "overlap": {},
                "monthly_intervals": prog.get("monthly_intervals", []),
                "monthly_recommendation": monthly,
                "running": 0,
                "completed": len(monthly.get("range_stats") or []),
                "failed": 0,
                "total": len(monthly.get("range_stats") or []),
            }
        return {"has_extend": False}

    all_ids = [task_id] + [eid for eid in extend_ids if eid]
    stats = get_range_comparison_stats(all_ids)
    overlap = get_cross_range_overlap(all_ids)
    running = 0
    completed = 0
    for eid in extend_ids:
        if eid:
            ep = get_progress(eid)
            if ep and ep.get("status") in ("completed",):
                completed += 1
            else:
                running += 1
    return {
        "has_extend": True,
        "embedded": False,
        "range_stats": stats,
        "overlap": overlap,
        "monthly_intervals": prog.get("monthly_intervals", []),
        "monthly_recommendation": prog.get("monthly_recommendation"),
        "extend_task_ids": extend_ids,
        "running": running,
        "completed": completed,
        "total": len(extend_ids),
    }


# ── API: LLM config check ────────────────────────────
@app.get("/api/llm/config")
async def api_llm_config():
    from web_app.llm_service import get_llm_config
    cfg = get_llm_config()
    return {
        "configured": bool(cfg["api_key"]),
        "api_key": cfg["api_key"],
        "api_base": cfg["api_base"],
        "model": cfg["model"],
    }


# ── API: Save LLM config to DB ─────────────────────────
@app.put("/api/llm/config")
async def api_llm_config_save(body: Dict[str, Any]):
    from web_app.llm_service import save_llm_config
    api_key = body.get("api_key", "")
    api_base = body.get("api_base", "https://api.openai.com/v1")
    model = body.get("model", "gpt-4o")
    save_llm_config(api_key, api_base, model)
    return {"saved": True}


@app.post("/api/llm/models")
async def api_llm_models(body: Dict[str, Any] = None):
    from web_app.llm_service import fetch_llm_models

    body = body or {}
    result = fetch_llm_models(
        api_key=(body.get("api_key") or "").strip(),
        api_base=(body.get("api_base") or "").strip(),
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── API: Repo path config ──────────────────────────────
@app.get("/api/repo/config")
async def api_repo_config():
    from web_app.repo_config import get_repo_config
    return get_repo_config()


@app.put("/api/repo/config")
async def api_repo_config_save(body: Dict[str, Any]):
    from web_app.repo_config import get_repo_config, save_repo_config
    save_repo_config(body.get("repo_dir", ""))
    return {"saved": True, **get_repo_config()}


# ── API: GKI Upgrade workflow ──────────────────────────
@app.get("/api/upgrade/config")
async def api_upgrade_config():
    from web_app.target_repo_config import get_upgrade_defaults_config
    return get_upgrade_defaults_config()


@app.put("/api/upgrade/config")
async def api_upgrade_config_save(body: Dict[str, Any]):
    from web_app.target_repo_config import get_upgrade_defaults_config, save_upgrade_defaults_config
    save_upgrade_defaults_config(
        apply_mode=body.get("apply_mode", ""),
    )
    return {"saved": True, **get_upgrade_defaults_config()}


@app.get("/api/upgrade/ssh-config")
async def api_upgrade_ssh_config():
    from web_app.ssh_bastion import load_bastion_config
    from web_app.ssh_credentials_config import get_ssh_credentials_api_payload

    cfg = load_bastion_config()
    return {
        "bastion_host": cfg.bastion_host,
        "bastion_port": cfg.bastion_port,
        "target_ip": cfg.target_ip,
        **get_ssh_credentials_api_payload(),
    }


@app.put("/api/upgrade/ssh-credentials")
async def api_upgrade_ssh_credentials_save(body: Dict[str, Any]):
    from web_app.ssh_credentials_config import get_ssh_credentials_api_payload, save_ssh_credentials

    save_ssh_credentials(body or {})
    return {"saved": True, **get_ssh_credentials_api_payload()}


@app.delete("/api/upgrade/ssh-credentials")
async def api_upgrade_ssh_credentials_clear():
    from web_app.ssh_credentials_config import clear_ssh_credentials, get_ssh_credentials_api_payload

    clear_ssh_credentials()
    return {"cleared": True, **get_ssh_credentials_api_payload()}


@app.post("/api/upgrade")
async def api_start_upgrade(body: Dict[str, Any]):
    from web_app.upgrade_service import start_upgrade
    target_repo_dir = (body.get("target_repo_dir") or "").strip()
    if not target_repo_dir:
        raise HTTPException(400, "每次合入必须指定 target_repo_dir（目标 vendor 代码路径）")
    job_id, err = start_upgrade(
        from_tag=body.get("from_tag", ""),
        to_tag=body.get("to_tag", ""),
        repo=body.get("repo", "https://android.googlesource.com/kernel/common"),
        analysis_task_id=body.get("analysis_task_id", ""),
        patch_file=body.get("patch_file", ""),
        target_repo_dir=body.get("target_repo_dir", ""),
        apply_mode=body.get("apply_mode", ""),
        auto_commit=bool(body.get("auto_commit", False)),
        auto_build=bool(body.get("auto_build", False)),
        auto_fix_build_errors=bool(body.get("auto_fix_build_errors", False)),
        build_fix_max_attempts=int(body.get("build_fix_max_attempts") or 0),
        auto_resolve_conflicts=bool(body.get("auto_resolve_conflicts", False)),
        force_dirty=bool(body.get("force_dirty", False)),
        create_backup=not bool(body.get("no_backup", False)),
        upgrade_branch=body.get("upgrade_branch", ""),
        commit_message=body.get("commit_message", ""),
        commit_message_file=(body.get("commit_message_file") or "").strip(),
        build_command=body.get("build_command", ""),
        build_workdir=body.get("build_workdir", ""),
        remote_temp_dir=body.get("remote_temp_dir", ""),
        local_repo_mount=(body.get("local_repo_mount") or "").strip(),
        local_build_mount=(body.get("local_build_mount") or "").strip(),
        remote=bool(body.get("remote", False)),
        remote_ssh=body.get("remote_ssh"),
    )
    if err:
        raise HTTPException(400, err)
    awaiting = False
    from web_app.database import get_upgrade_job
    job = get_upgrade_job(job_id)
    if job and job.get("status") == "awaiting_ssh":
        awaiting = True
    return {"job_id": job_id, "awaiting_ssh": awaiting}


@app.post("/api/upgrade/jobs/{job_id}/ssh-bastion")
async def api_upgrade_ssh_bastion(job_id: str):
    from web_app.upgrade_service import connect_cqris_for_job
    ok, msg = connect_cqris_for_job(job_id)
    if not ok:
        raise HTTPException(400, msg)
    from web_app.database import get_upgrade_job
    return {"ok": True, "message": msg, "job": get_upgrade_job(job_id)}


@app.post("/api/upgrade/jobs/{job_id}/ssh-connect")
async def api_upgrade_ssh_connect(job_id: str, body: Dict[str, Any] = None):
    from web_app.upgrade_service import connect_upgrade_ssh
    body = body or {}
    ok, msg = connect_upgrade_ssh(job_id, body.get("otp", ""))
    if not ok:
        raise HTTPException(400, msg)
    from web_app.database import get_upgrade_job
    return {"ok": True, "message": msg, "job": get_upgrade_job(job_id)}


@app.get("/api/upgrade/jobs")
async def api_list_upgrade_jobs(limit: int = Query(50, ge=1, le=200)):
    return {"jobs": list_upgrade_jobs(limit)}


@app.get("/api/upgrade/jobs/{job_id}")
async def api_get_upgrade_job(job_id: str):
    from web_app.upgrade_service import get_upgrade_progress, reconcile_upgrade_job_record
    from web_app.upgrade_ssh_manager import has_pooled_ssh_session, is_remote_job
    job = get_upgrade_job(job_id)
    if not job:
        raise HTTPException(404, "升级任务不存在")
    job = reconcile_upgrade_job_record(job)
    job = dict(job)
    job["ssh_connected"] = bool(is_remote_job(job) and has_pooled_ssh_session(job_id))
    return {"job": job, "progress": get_upgrade_progress(job_id)}


@app.get("/api/upgrade/jobs/{job_id}/conflicts")
async def api_upgrade_conflicts(job_id: str):
    from web_app.conflict_resolution_service import get_conflict_resolution_state
    job = get_upgrade_job(job_id)
    if not job:
        raise HTTPException(404, "升级任务不存在")
    return get_conflict_resolution_state(job_id)


@app.post("/api/upgrade/jobs/{job_id}/conflicts/resolve")
async def api_upgrade_conflicts_resolve(job_id: str, body: Optional[Dict[str, Any]] = None):
    from web_app.conflict_resolution_service import schedule_ai_conflict_resolution
    job = get_upgrade_job(job_id)
    if not job:
        raise HTTPException(404, "升级任务不存在")
    if job.get("status") != "conflicts":
        raise HTTPException(400, "当前任务不在 conflicts 状态")
    body = body or {}
    ssh_creds = body.get("remote_ssh") if isinstance(body, dict) else None
    paths = body.get("paths") or body.get("conflict_paths")
    force = bool(body.get("force"))
    auto_apply = bool(body.get("auto_apply"))
    schedule_ai_conflict_resolution(
        job_id,
        ssh_creds=ssh_creds,
        paths=paths,
        force=force,
        auto_apply=auto_apply,
    )
    n = len(paths) if paths else len(job.get("conflict_files") or [])
    action = "AI 处理并写回" if auto_apply else "AI 冲突处理"
    return {"ok": True, "message": f"{action}已启动（{n} 个文件）"}


@app.put("/api/upgrade/jobs/{job_id}/conflicts/content")
async def api_upgrade_conflicts_content(job_id: str, body: Dict[str, Any]):
    from web_app.conflict_resolution_service import update_proposed_content, update_rej_content
    path = (body.get("conflict_path") or body.get("path") or "").strip()
    rej_content = body.get("rej_content")
    content = body.get("content")
    if not path:
        raise HTTPException(400, "需要 conflict_path")
    if rej_content is not None:
        try:
            item = update_rej_content(job_id, path, rej_content)
        except RuntimeError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True, "item": item}
    if content is None:
        raise HTTPException(400, "需要 content 或 rej_content")
    try:
        item = update_proposed_content(job_id, path, content)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "item": item}


@app.post("/api/upgrade/jobs/{job_id}/conflicts/apply")
async def api_upgrade_conflicts_apply(job_id: str, body: Dict[str, Any] = None):
    from web_app.conflict_resolution_service import apply_confirmed_conflicts
    body = body or {}
    paths = body.get("paths") or body.get("conflict_paths")
    try:
        count, applied = apply_confirmed_conflicts(
            job_id, paths, ssh_creds=body.get("remote_ssh"),
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    if count == 0:
        raise HTTPException(400, "没有可写回的文件（请先确认 AI 建议或编辑内容）")
    return {"ok": True, "applied_count": count, "applied_files": applied, "job": get_upgrade_job(job_id)}


@app.post("/api/upgrade/jobs/{job_id}/continue")
async def api_upgrade_continue(job_id: str, body: Dict[str, Any] = None):
    from web_app.upgrade_service import continue_after_conflicts
    body = body or {}
    ssh = body.get("remote_ssh")
    ok, msg = continue_after_conflicts(job_id, ssh_creds=ssh)
    if not ok:
        raise HTTPException(400, msg)
    if body.get("commit"):
        from web_app.upgrade_service import commit_upgrade
        ok2, msg2 = commit_upgrade(job_id, body.get("commit_message", ""), ssh_creds=ssh)
        if not ok2:
            raise HTTPException(400, msg2)
        msg = msg2
    if body.get("build"):
        from web_app.upgrade_service import build_upgrade
        ok3, msg3 = build_upgrade(
            job_id,
            body.get("build_command", ""),
            body.get("build_workdir", ""),
            ssh_creds=ssh,
        )
        if not ok3:
            raise HTTPException(400, msg3)
        msg = msg3
    job = get_upgrade_job(job_id)
    return {"ok": True, "message": msg, "job": job}


@app.post("/api/upgrade/jobs/{job_id}/commit")
async def api_upgrade_commit(job_id: str, body: Dict[str, Any] = None):
    from web_app.upgrade_service import commit_upgrade
    body = body or {}
    message = body.get("message", "")
    ok, msg = commit_upgrade(job_id, message, ssh_creds=body.get("remote_ssh"))
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "commit_sha": msg, "job": get_upgrade_job(job_id)}


@app.post("/api/upgrade/jobs/{job_id}/commit-retry")
async def api_upgrade_commit_retry(job_id: str, body: Dict[str, Any] = None):
    from web_app.upgrade_service import retry_commit_upgrade

    body = body or {}
    ok, msg = retry_commit_upgrade(job_id, ssh_creds=body.get("remote_ssh"))
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg, "job": get_upgrade_job(job_id)}


@app.post("/api/upgrade/jobs/{job_id}/build")
async def api_upgrade_build(job_id: str, body: Dict[str, Any] = None):
    from web_app.upgrade_service import build_upgrade
    from web_app.database import get_upgrade_job, update_upgrade_job
    body = body or {}
    command = body.get("command", "") or body.get("build_command", "")
    workdir = body.get("workdir", "") or body.get("build_workdir", "")
    if body.get("auto_fix_build_errors") is not None:
        job = get_upgrade_job(job_id)
        if job:
            opts = dict(job.get("options") or {})
            opts["auto_fix_build_errors"] = bool(body.get("auto_fix_build_errors"))
            update_upgrade_job(job_id, options=opts)
    ok, msg = build_upgrade(job_id, command, workdir, ssh_creds=body.get("remote_ssh"))
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "build_log": msg, "job": get_upgrade_job(job_id)}


@app.get("/api/upgrade/jobs/{job_id}/build-fixes")
async def api_upgrade_build_fixes(job_id: str):
    from web_app.build_fix_service import get_build_fix_state
    from web_app.database import get_upgrade_job
    job = get_upgrade_job(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return get_build_fix_state(job_id)


@app.post("/api/upgrade/jobs/{job_id}/build/fix-retry")
async def api_upgrade_build_fix_retry(job_id: str, body: Optional[Dict[str, Any]] = None):
    from web_app.database import get_upgrade_job, update_upgrade_job
    from web_app.upgrade_service import build_upgrade, get_upgrade_job as _get_job
    body = body or {}
    job = get_upgrade_job(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    if job.get("status") not in ("build_failed", "committed", "completed"):
        raise HTTPException(400, f"当前状态不可修复重试: {job.get('status')}")
    opts = dict(job.get("options") or {})
    opts["auto_fix_build_errors"] = True
    if body.get("max_attempts"):
        from web_app.build_fix_service import normalize_build_fix_max_attempts
        opts["build_fix_max_attempts"] = normalize_build_fix_max_attempts(body["max_attempts"])
    update_upgrade_job(job_id, options=opts)
    command = body.get("build_command") or job.get("build_command") or ""
    workdir = body.get("build_workdir") or job.get("build_workdir") or ""
    ok, msg = build_upgrade(job_id, command, workdir, ssh_creds=body.get("remote_ssh"))
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg, "job": _get_job(job_id)}


@app.post("/api/upgrade/jobs/{job_id}/resume")
async def api_upgrade_resume(job_id: str, body: Dict[str, Any] = None):
    from web_app.upgrade_service import resume_upgrade_job
    body = body or {}
    ok, msg = resume_upgrade_job(job_id, ssh_creds=body.get("remote_ssh"))
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg, "job": get_upgrade_job(job_id)}


@app.post("/api/upgrade/jobs/{job_id}/cancel")
async def api_upgrade_cancel(job_id: str):
    from web_app.upgrade_service import cancel_upgrade_job
    ok, msg = cancel_upgrade_job(job_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg, "job": get_upgrade_job(job_id)}


@app.post("/api/upgrade/jobs/{job_id}/abort")
async def api_upgrade_abort(job_id: str):
    from web_app.upgrade_service import cancel_upgrade_job
    ok, msg = cancel_upgrade_job(job_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


@app.delete("/api/upgrade/jobs/{job_id}")
async def api_delete_upgrade_job(job_id: str):
    if not get_upgrade_job(job_id):
        raise HTTPException(404, "升级任务不存在")
    from web_app.upgrade_ssh_manager import release_job_ssh
    release_job_ssh(job_id)
    delete_upgrade_job(job_id)
    return {"deleted": True}


@app.get("/api/upgrade/jobs/{job_id}/execution-log")
async def api_upgrade_execution_log(job_id: str):
    from web_app.database import get_upgrade_job
    from web_app.upgrade_execution_log import (
        ensure_execution_log_file,
        execution_log_dir,
        get_execution_log_for_job,
        progress_log_to_text,
    )

    job = get_upgrade_job(job_id)
    if not job:
        raise HTTPException(404, "升级任务不存在")
    text, path, source = get_execution_log_for_job(job_id, job)
    if not text.strip():
        raise HTTPException(
            404,
            f"执行日志尚未生成。日志目录: {execution_log_dir()}",
        )
    if source == "db":
        try:
            dest = ensure_execution_log_file(job_id)
            with dest.open("a", encoding="utf-8") as f:
                f.write(progress_log_to_text((job.get("options") or {}).get("progress_log") or []))
                f.write("\n")
            path = dest
        except Exception:
            pass
    from fastapi.responses import PlainTextResponse
    note = ""
    if source == "db":
        note = "# 注：此日志从数据库 progress_log 恢复（本地文件此前未生成）\n\n"
    return PlainTextResponse(
        note + text,
        headers={
            "Content-Disposition": f'attachment; filename="{path.name}"',
            "X-Log-Source": source,
            "X-Log-Path": str(path),
        },
    )


# ── API: Start LLM analysis ────────────────────────────
@app.post("/api/analyze/{task_id}/llm")
async def api_llm_analyze(task_id: str, body: Dict[str, Any] = None):
    force_reanalyze = bool((body or {}).get("force_reanalyze", False))
    ok, err = start_llm_analysis(task_id, force_reanalyze=force_reanalyze)
    if not ok:
        raise HTTPException(400, err)
    return {"task_id": task_id}


# ── API: Cancel task ─────────────────────────────────────
@app.post("/api/tasks/{task_id}/cancel")
async def api_cancel_task(task_id: str):
    from web_app.analyzer_service import cancel_analysis_task

    ok, msg = cancel_analysis_task(task_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"cancelled": True, "message": msg}


# ── API: Delete task ─────────────────────────────────────
@app.delete("/api/tasks/{task_id}")
async def api_delete_task(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    # 先标记取消，让运行中的线程自行停止
    from web_app.analyzer_service import cancel_task
    cancel_task(task_id)
    db_delete_task(task_id)
    return {"deleted": True}


# ── API: Get single patch HTML detail ──────────────────
@app.get("/api/patches/{sha}/html")
async def api_patch_html(sha: str):
    row = get_patch(sha)
    if not row:
        raise HTTPException(404, "patch 不存在")
    data_raw = row.get("data", "{}")
    try:
        patch_data = json.loads(data_raw) if isinstance(data_raw, str) else data_raw
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(500, "patch 数据格式错误")
    if not isinstance(patch_data, dict):
        patch_data = {}
    patch_data.setdefault("commit", row.get("sha") or sha)
    patch_data.setdefault("sha", row.get("sha") or sha)
    patch_data.setdefault("title", row.get("title") or "")
    patch_data.setdefault("score", row.get("score"))
    patch_data.setdefault("recommendation", row.get("recommendation") or "")
    patch_data.setdefault("key_risk", row.get("key_risk") or "")
    patch_data.setdefault("dev_module", row.get("dev_module") or "")
    html = render_patch(0, patch_data)
    return HTMLResponse(html)


@app.get("/api/patches/{sha}/file-diff")
async def api_patch_file_diff(sha: str, path: str = Query(..., description="文件路径")):
    """返回单个 patch 中指定文件的 diff 片段。"""
    from web_app.diff_utils import extract_file_diff

    row = get_patch(sha)
    if not row:
        raise HTTPException(404, "patch 不存在")
    data_raw = row.get("data", "{}")
    try:
        patch_data = json.loads(data_raw) if isinstance(data_raw, str) else data_raw
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(500, "patch 数据格式错误")

    diff_raw = patch_data.get("diff_preview", {})
    diff_text = diff_raw.get("text", "") if isinstance(diff_raw, dict) else str(diff_raw or "")
    file_diff = extract_file_diff(diff_text, path)
    truncated = bool(diff_raw.get("truncated")) if isinstance(diff_raw, dict) else False
    return {
        "sha": sha,
        "path": path,
        "text": file_diff,
        "found": bool(file_diff),
        "truncated": truncated,
    }


# ── API: Download diff file ─────────────────────────────
@app.get("/api/tasks/{task_id}/diff")
async def api_task_diff(task_id: str):
    """Download diff file for a task.

    - Interval analysis: returns the squash diff file
    - Single SHA: returns the patch diff from patch data
    """
    from fastapi.responses import Response
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    task_type = task.get("type", "")

    if task_type == "range":
        # Interval analysis: serve squash diff file
        diff_file = task.get("diff_file", "")
        squash_path = None
        if diff_file:
            from pathlib import Path
            p = Path(diff_file)
            squash_candidate = p.parent / (p.stem + "_squash.patch")
            if squash_candidate.is_file():
                squash_path = squash_candidate
            elif p.is_file():
                squash_path = p
        if not squash_path or not squash_path.is_file():
            raise HTTPException(404, "diff 文件不存在")
        content = squash_path.read_text(encoding="utf-8", errors="replace")
        filename = squash_path.name
        return Response(
            content=content,
            media_type="text/x-diff",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    else:
        # Single SHA: extract diff from patch data
        patches = get_patches_by_task(task_id)
        if not patches:
            raise HTTPException(404, "无 patch 数据")
        p = patches[0]
        data = json.loads(p["data"]) if isinstance(p["data"], str) else p["data"]
        diff_text = ""
        diff_raw = data.get("diff_preview", {})
        if isinstance(diff_raw, dict):
            diff_text = diff_raw.get("text", "")
        elif isinstance(diff_raw, str):
            diff_text = diff_raw
        if not diff_text:
            raise HTTPException(404, "无 diff 数据")
        sha = data.get("sha", p.get("sha", "unknown"))
        filename = f"{sha[:12]}.patch"
        return Response(
            content=diff_text,
            media_type="text/x-diff",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


# ── API: Get full task report HTML (downloadable) ──────

@app.get("/api/tasks/{task_id}/report")
async def api_task_report(task_id: str, inline: bool = Query(False, description="浏览器内嵌查看")):
    from fastapi.responses import Response

    detail = get_task_with_patches(task_id)
    if not detail:
        raise HTTPException(404, "任务不存在")

    # Prefer raw DB rows so render_patch keeps full analysis/diff fields.
    patches = get_patches_by_task(task_id)
    if not patches:
        patches = detail.get("patches") or []
    summary = detail.get("summary") or {}
    monthly_html = render_monthly_analysis_html(task_id)
    html = build_task_report_html(
        detail,
        patches,
        summary=summary if isinstance(summary, dict) else {},
        monthly_html=monthly_html,
    )

    from_tag = detail.get("from_tag", "")
    to_tag = detail.get("to_tag", "")
    if from_tag and to_tag:
        fn = f"patch_report_{from_tag}_to_{to_tag}.html".replace("/", "_").replace("\\", "_")
    else:
        fn = f"patch_report_{task_id[:8]}.html"
    disposition = "inline" if inline else "attachment"
    return Response(
        content=html.encode("utf-8"),
        media_type="text/html",
        headers={"Content-Disposition": f'{disposition}; filename="{fn}"'},
    )


# ── API: Crash Analysis ─────────────────────────────

@app.post("/api/crash-analysis")
async def api_crash_analysis_create(body: Dict[str, Any]):
    from_tag = body.get("from_tag", "")
    to_tag = body.get("to_tag", "")
    crash_log = body.get("crash_log", "")

    if not from_tag or not to_tag:
        raise HTTPException(400, "需要提供 from_tag 和 to_tag")
    if not crash_log:
        raise HTTPException(400, "需要提供死机日志")

    crash_id, err = start_crash_analysis(from_tag, to_tag, crash_log)
    if err:
        raise HTTPException(500, err)
    return {"crash_id": crash_id}


@app.get("/api/crash-analyses")
async def api_crash_analyses_list():
    """List all crash analysis records."""
    return {"items": list_crash_analyses(limit=100)}


@app.get("/api/crash-analysis/{crash_id}")
async def api_crash_analysis_get(crash_id: str):
    result = get_crash_analysis(crash_id)
    if not result:
        raise HTTPException(404, "死机分析不存在")
    return result


@app.delete("/api/crash-analysis/{crash_id}")
async def api_crash_analysis_delete(crash_id: str):
    delete_crash_analysis(crash_id)
    return {"deleted": True}


@app.get("/api/crash-analysis/{crash_id}/report")
async def api_crash_analysis_report(crash_id: str):
    """Download the crash analysis report as HTML."""
    result = get_crash_analysis(crash_id)
    if not result:
        raise HTTPException(404, "死机分析不存在")
    report = result.get("full_report", "")
    if not report:
        raise HTTPException(404, "报告尚未生成")
    from fastapi.responses import Response
    return Response(
        content=report.encode("utf-8"),
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="crash_report_{crash_id[:8]}.html"'},
    )


@app.websocket("/ws/crash-analysis/{crash_id}")
async def ws_crash_analysis_progress(websocket: WebSocket, crash_id: str):
    await websocket.accept()
    try:
        while True:
            prog = get_crash_progress(crash_id)
            await websocket.send_json(prog)
            if prog.get("status") in ("completed", "failed"):
                break
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass


@app.websocket("/ws/upgrade/{job_id}")
async def ws_upgrade_progress(websocket: WebSocket, job_id: str):
    from web_app.upgrade_service import get_upgrade_progress

    await websocket.accept()
    terminal = frozenset({
        "completed", "failed", "conflicts", "aborted", "build_failed", "cancelled",
    })
    try:
        while True:
            try:
                prog = get_upgrade_progress(job_id)
                await websocket.send_json(prog)
                if prog.get("status") in terminal:
                    break
            except WebSocketDisconnect:
                raise
            except Exception:
                # 客户端已断开或发送失败，结束推送
                break
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass


# ── WebSocket: Real-time progress ──────────────────────
@app.websocket("/ws/{task_id}")
async def ws_progress(websocket: WebSocket, task_id: str):
    await websocket.accept()
    try:
        while True:
            prog = get_progress(task_id)
            await websocket.send_json(prog)
            if prog.get("status") in ("completed", "failed", "cancelled"):
                break
            await asyncio.sleep(0.4)
    except WebSocketDisconnect:
        pass


# ── Serve frontend ─────────────────────────────────────

def _serve_vue_app() -> HTMLResponse:
    index_path = _FRONTEND_DIST / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<h1>Vue UI 尚未构建</h1>"
        "<p>请先在 frontend 目录执行 <code>npm install && npm run build</code>。</p>",
        status_code=503,
    )


@app.get("/", response_class=HTMLResponse)
async def index():
    return _serve_vue_app()


@app.get("/app", response_class=HTMLResponse)
@app.get("/app/", response_class=HTMLResponse)
async def vue_app_root():
    return _serve_vue_app()


@app.get("/app/{path:path}", response_class=HTMLResponse)
async def vue_app_fallback(path: str):
    return _serve_vue_app()


@app.get("/legacy")
@app.get("/crash-analysis")
async def redirect_removed_legacy_pages():
    return RedirectResponse(url="/app/", status_code=301)


@app.get("/patches")
async def redirect_legacy_patches_page():
    return RedirectResponse(url="/app/patches", status_code=301)


# ── Tool documentation page ────────────────────────
@app.get("/overview", response_class=HTMLResponse)
async def docs_page():
    doc_path = Path(__file__).parent.parent.resolve() / "gkiPatchTool_OVERVIEW.html"
    if doc_path.exists():
        return HTMLResponse(doc_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>文档文件未找到</h1>")


# ── API: List all patches (paginated) ────────────────
@app.get("/api/patches")
async def api_list_patches(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str = Query(""),
    dev_module: str = Query(""),
):
    return list_all_patches(page=page, page_size=page_size, search=search, dev_module=dev_module)


# ── API: Module stats across all patches ─────────────
@app.get("/api/patches/module-stats")
async def api_all_module_stats():
    return {"stats": get_all_module_stats()}


# ── Entrypoint ─────────────────────────────────────────
def _configure_terminal_encoding() -> None:
    """Windows 终端默认 GBK，强制 stdout/stderr 使用 UTF-8 避免中文乱码。"""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass


def main():
    _configure_terminal_encoding()
    from web_app.repo_config import get_repo_config
    repo_cfg = get_repo_config()
    print("=" * 50)
    print("  GKI Patch 分析平台")
    print(f"  默认配置: {DEFAULT_CONFIG}")
    if repo_cfg["configured"]:
        print(f"  本地仓库: {repo_cfg['effective_dir']} ({repo_cfg['source']})")
    else:
        print("  本地仓库: 未配置（将使用远程 API，建议在页面配置代码路径）")
    print("=" * 50)
    print("  启动: http://127.0.0.1:8000/app/")
    print("=" * 50)
    webbrowser.open("http://127.0.0.1:8000/app/")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
