"""GKI upgrade workflow: apply patch → resolve conflicts → commit → build."""
from __future__ import annotations

import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from web_app.database import (
    create_upgrade_job,
    get_task,
    get_upgrade_job,
    update_upgrade_job,
)
from web_app.interval_diff_service import load_interval_diff_cache
from web_app.remote_workdir_config import job_remote_temp_join
from web_app.target_repo_config import (
    get_apply_mode,
    get_build_timeout,
    normalize_linux_path,
    resolve_build_workdir,
    resolve_target_repo_path,
)
from web_app.ssh_bastion import load_bastion_config
from web_app.ssh_credentials_config import get_saved_ssh_credentials
from web_app.upgrade_progress import register_job_progress, unregister_job_progress
from web_app.upgrade_ssh_manager import (
    clear_ssh_otp,
    connect_cqris_bastion,
    connect_job_ssh,
    get_stashed_ssh_credentials,
    has_cqris_partial_session,
    is_remote_job,
    is_ssh_terminal_status,
    release_job_ssh,
    remote_job_context,
    stash_ssh_credentials,
)
from web_app.upgrade_remote_git import deactivate_remote_session, is_remote_active
from web_app.upgrade_git import (
    am_abort,
    am_continue,
    apply_format_patch,
    apply_squash_patch,
    changed_files_from_status,
    commit,
    parse_apply_conflict_files,
    prepare_upgrade_branches,
    git_head_info,
    git_am_in_progress,
    has_conflict_markers,
    head_sha,
    is_clean_worktree,
    ensure_clean_worktree,
    list_reject_files,
    list_unmerged_files,
    repo_is_git,
    run_git,
    stage_all,
    working_tree_status,
)

from web_app.upgrade_execution_log import (
    UI_LOG_LIMIT,
    append_execution_log_line,
    ensure_execution_log_file,
    execution_log_dir,
    get_execution_log_for_job,
    init_execution_log,
    new_log_stem,
    read_execution_log_tail,
    resolve_build_log_path,
    resolve_execution_log_path,
)

PROJECT_ROOT = Path(__file__).parent.parent
BUILD_LOG_DIR = PROJECT_ROOT / "outputs" / "upgrade_logs"

_progress: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()
_cancelled: Dict[str, bool] = {}
_build_running: set[str] = set()


_UPGRADE_PHASE_ORDER = ["prepare", "apply", "build", "commit", "done"]
_TIMING_PHASES = ("prepare", "apply", "build", "commit")
_PHASE_LABELS = {
    "prepare": "准备环境",
    "apply": "合入 Patch",
    "commit": "提交代码",
    "build": "编译验证",
}


def _now_ts() -> float:
    return datetime.now().timestamp()


def _format_duration(sec: float) -> str:
    if sec is None or sec < 0:
        return "0s"
    if sec < 60:
        return f"{sec:.1f}s"
    minutes, seconds = divmod(int(sec), 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s" if seconds else f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m" if minutes else f"{hours}h"


def _enrich_phase_timings(timings: Dict[str, Any]) -> Dict[str, Any]:
    if not timings:
        return {}
    out = dict(timings)
    phases = dict(out.get("phases") or {})
    enriched_phases: Dict[str, Any] = {}
    now = _now_ts()
    for key, entry in phases.items():
        row = {k: v for k, v in entry.items() if not str(k).startswith("_")}
        base = float(row.get("duration_sec") or 0)
        active = entry.get("_active_start")
        if active:
            row["elapsed_sec"] = round(base + max(0, now - active), 2)
            row["running"] = True
        else:
            row["elapsed_sec"] = round(base, 2)
            row["running"] = False
        enriched_phases[key] = row
    out["phases"] = enriched_phases
    started = out.get("job_started_at")
    if started and not out.get("job_ended_at"):
        try:
            t0 = datetime.fromisoformat(started).timestamp()
            out["total_elapsed_sec"] = round(max(0, now - t0), 2)
        except ValueError:
            pass
    elif out.get("total_wall_sec") is not None:
        out["total_elapsed_sec"] = out["total_wall_sec"]
    return out


_PROGRESS_LOG_SKIP_PHASES = frozenset({"cancelled", "resume", "failed", "done", ""})
_RESUME_PHASE_RANK = {
    "prepare": 0,
    "apply": 1,
    "conflicts": 2,
    "applied": 3,
    "build": 4,
    "build_failed": 4,
    "build_fix": 5,
    "commit": 6,
    "committed": 6,
}


def _phase_rank(phase: str) -> int:
    return _RESUME_PHASE_RANK.get((phase or "").strip(), -1)


def _latest_progress_log_phase(opts: Dict[str, Any]) -> str:
    for row in reversed(opts.get("progress_log") or []):
        ph = (row.get("phase") or "").strip()
        if ph and ph not in _PROGRESS_LOG_SKIP_PHASES:
            return ph
    return ""


def _capture_resume_point(
    job: Dict[str, Any],
    prog: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Best-effort checkpoint when cancelling; survives server restart via progress_log."""
    prog = prog or {}
    opts = dict(job.get("options") or {})
    job_id = job.get("id") or ""

    job_status = (job.get("status") or "").strip()
    job_phase = (job.get("phase") or "").strip()
    prog_status = (prog.get("status") or "").strip()
    prog_phase = (prog.get("phase") or "").strip()
    log_phase = _latest_progress_log_phase(opts)
    last_active = (opts.get("last_active_phase") or "").strip()

    bf = opts.get("build_fix") or {}
    bf_running = bf.get("status") == "running"

    in_build = False
    if job_id:
        with _lock:
            in_build = job_id in _build_running

    candidates: List[str] = []
    for ph in (prog_phase, log_phase, last_active, job_phase):
        if ph and ph not in _PROGRESS_LOG_SKIP_PHASES:
            candidates.append(ph)

    if bf_running or prog_phase == "build_fix" or log_phase == "build_fix":
        candidates.append("build_fix")
    if in_build or job.get("build_log_file") or job_status in ("build_failed", "commit_failed"):
        candidates.append("build_fix" if bf_running else "build")

    phase = max(candidates, key=_phase_rank) if candidates else ""

    if job_status == "commit_failed":
        phase = "commit"

    if phase in ("committed", "commit") and (
        in_build or job.get("build_log_file") or bf_running or log_phase in ("build", "build_fix")
    ):
        phase = "build_fix" if bf_running else "build"

    if job_status == "build_failed" and _phase_rank(phase) < _phase_rank("build"):
        phase = "build"

    status = prog_status or job_status
    if job_status == "commit_failed":
        status = "commit_failed"
    elif phase in ("build", "build_fix"):
        status = "build_failed" if job_status == "build_failed" else "running"
    elif phase == "conflicts":
        status = "conflicts"
    elif status in ("cancelled", ""):
        status = prog_status or job_status

    return {
        "status": status,
        "phase": phase,
        "message": (prog.get("message") or job.get("error_msg") or "").strip(),
        "percent": prog.get("percent"),
        "cancelled_at": datetime.now().isoformat(),
    }


def _normalize_resume_point(
    job: Dict[str, Any],
    rp: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Fill gaps in saved resume_point using DB fields and progress_log."""
    rp = dict(rp or {})
    opts = job.get("options") or {}
    phase = (rp.get("phase") or "").strip()

    if not phase:
        captured = _capture_resume_point(job, {})
        for key, val in captured.items():
            if key == "cancelled_at":
                continue
            if val is not None and val != "":
                rp.setdefault(key, val)
        phase = (rp.get("phase") or "").strip()

    bf = opts.get("build_fix") or {}
    build_evidence = bool(
        job.get("build_log_file") or job.get("build_command") or bf
    )
    if build_evidence and _phase_rank(phase) < _phase_rank("build"):
        rp["phase"] = "build_fix" if bf.get("status") == "running" else "build"
        if job.get("status") == "build_failed":
            rp["status"] = "build_failed"
        elif (rp.get("status") or "") in ("", "cancelled", "applied", "committed"):
            rp["status"] = "running"
        phase = rp["phase"]

    if bf.get("status") == "running" and _phase_rank(phase) < _phase_rank("build_fix"):
        rp["phase"] = "build_fix"
        rp["status"] = "running"

    if phase in ("committed", "commit") and build_evidence:
        if job.get("status") == "commit_failed":
            rp["phase"] = "commit"
            rp["status"] = "commit_failed"
        elif bf.get("status") == "running":
            rp["phase"] = "build_fix"
            rp["status"] = "running"
        elif (rp.get("status") or "") in ("", "committed", "cancelled"):
            rp["phase"] = "build"
            rp["status"] = "build_failed" if job.get("status") == "build_failed" else "running"

    return rp


def _save_progress_options(job_id: str, prog: Dict[str, Any]) -> None:
    log_to_save = prog.get("log")
    timings_to_save = prog.get("phase_timings")
    phase_to_save = (prog.get("phase") or "").strip()
    if not log_to_save and not timings_to_save and not phase_to_save:
        return
    try:
        job = get_upgrade_job(job_id)
        if not job:
            return
        opts = dict(job.get("options") or {})
        if log_to_save:
            opts["progress_log"] = log_to_save
        if timings_to_save:
            clean = dict(timings_to_save)
            phases = {}
            for key, entry in (clean.get("phases") or {}).items():
                phases[key] = {k: v for k, v in entry.items() if not str(k).startswith("_")}
            clean["phases"] = phases
            opts["phase_timings"] = clean
        if phase_to_save and phase_to_save not in _PROGRESS_LOG_SKIP_PHASES:
            opts["last_active_phase"] = phase_to_save
        if not opts.get("execution_log_file"):
            opts["execution_log_file"] = str(resolve_execution_log_path(job_id, job))
        update_upgrade_job(job_id, options=opts)
    except Exception:
        pass


def _begin_phase_timing(job_id: str, phase: str) -> None:
    if phase not in _TIMING_PHASES:
        return
    with _lock:
        prev = dict(_progress.get(job_id, {}))
        timings = dict(prev.get("phase_timings") or {})
        if not timings.get("job_started_at"):
            timings["job_started_at"] = datetime.now().isoformat()
        phases = dict(timings.get("phases") or {})
        entry = dict(phases.get(phase) or {"duration_sec": 0.0, "runs": 0})
        if not entry.get("_active_start"):
            entry["_active_start"] = _now_ts()
            entry.setdefault("started_at", datetime.now().isoformat())
        phases[phase] = entry
        timings["phases"] = phases
        prev["phase_timings"] = timings
        _progress[job_id] = prev
    _save_progress_options(job_id, prev)


def _end_phase_timing(job_id: str, phase: str, status: str = "done") -> None:
    if phase not in _TIMING_PHASES:
        return
    with _lock:
        prev = dict(_progress.get(job_id, {}))
        timings = dict(prev.get("phase_timings") or {})
        phases = dict(timings.get("phases") or {})
        entry = dict(phases.get(phase) or {})
        active = entry.pop("_active_start", None)
        if active is not None:
            delta = max(0, _now_ts() - active)
            entry["duration_sec"] = round(float(entry.get("duration_sec") or 0) + delta, 2)
            entry["runs"] = int(entry.get("runs") or 0) + 1
        entry["ended_at"] = datetime.now().isoformat()
        entry["status"] = status
        phases[phase] = entry
        timings["phases"] = phases
        prev["phase_timings"] = timings
        duration = float(entry.get("duration_sec") or 0)
        if duration > 0:
            log = list(prev.get("log", []))
            label = _PHASE_LABELS.get(phase, phase)
            runs = int(entry.get("runs") or 0)
            run_note = f"（第{runs}次）" if runs > 1 else ""
            timing_msg = f"{label} 耗时 {_format_duration(duration)}{run_note}"
            now = datetime.now()
            log.append({
                "time": now.strftime("%H:%M:%S"),
                "phase": phase,
                "msg": timing_msg,
            })
            prev["log"] = log[-UI_LOG_LIMIT:]
            _write_log_line(job_id, now.strftime("%Y-%m-%d %H:%M:%S"), phase, timing_msg)
        _progress[job_id] = prev
    _save_progress_options(job_id, prev)


def _end_active_phase_timings(job_id: str, status: str) -> None:
    with _lock:
        prev = dict(_progress.get(job_id, {}))
        timings = dict(prev.get("phase_timings") or {})
        phases = dict(timings.get("phases") or {})
    for phase in _TIMING_PHASES:
        entry = phases.get(phase) or {}
        if entry.get("_active_start"):
            _end_phase_timing(job_id, phase, status)


def _finalize_job_timing(job_id: str) -> None:
    _end_active_phase_timings(job_id, "done")
    with _lock:
        prev = dict(_progress.get(job_id, {}))
        timings = dict(prev.get("phase_timings") or {})
        started = timings.get("job_started_at")
        if started and not timings.get("job_ended_at"):
            try:
                t0 = datetime.fromisoformat(started).timestamp()
                timings["total_wall_sec"] = round(max(0, _now_ts() - t0), 2)
                timings["job_ended_at"] = datetime.now().isoformat()
            except ValueError:
                pass
        prev["phase_timings"] = timings
        _progress[job_id] = prev
    _save_progress_options(job_id, prev)


def get_upgrade_progress(job_id: str) -> Dict[str, Any]:
    with _lock:
        prog = dict(_progress.get(job_id, {"status": "unknown", "message": ""}))
    job = get_upgrade_job(job_id)
    if job:
        job = reconcile_upgrade_job_record(job)
        js = str(job.get("status") or "")
        if js:
            prog["status"] = js
            raw_phase = job.get("phase") or prog.get("phase") or ""
            # build_fix is a sub-phase of compile verification in the UI step list
            prog["phase"] = "build" if raw_phase == "build_fix" else raw_phase
        else:
            prog.setdefault("status", "unknown")
            prog.setdefault("phase", job.get("phase", ""))
        opts = job.get("options") or {}
        if not prog.get("log") and opts.get("progress_log"):
            prog["log"] = opts["progress_log"]
        if len(prog.get("log") or []) < UI_LOG_LIMIT:
            file_tail = read_execution_log_tail(job_id, UI_LOG_LIMIT)
            if file_tail and len(file_tail) >= len(prog.get("log") or []):
                prog["log"] = file_tail
        prog["execution_log_file"] = opts.get("execution_log_file") or str(resolve_execution_log_path(job_id, job))
        if job.get("build_log_file"):
            prog["build_log_file"] = job.get("build_log_file")
        if job.get("build_exit_code") is not None:
            prog["build_exit_code"] = job.get("build_exit_code")
        bf = opts.get("build_fix")
        if bf:
            prog["build_fix"] = bf
        if not prog.get("phase_timings") and opts.get("phase_timings"):
            prog["phase_timings"] = opts["phase_timings"]
        subs = opts.get("gerrit_submissions")
        if subs:
            from web_app.upgrade_staging import _normalize_gerrit_submission_row

            subs = [
                _normalize_gerrit_submission_row(dict(r))
                for r in subs
                if isinstance(r, dict)
            ]
            if not prog.get("gerrit_submissions"):
                prog["gerrit_submissions"] = subs
            else:
                prog["gerrit_submissions"] = [
                    _normalize_gerrit_submission_row(dict(r))
                    for r in prog["gerrit_submissions"]
                    if isinstance(r, dict)
                ]
        prog["job"] = job
    if prog.get("phase_timings"):
        prog["phase_timings"] = _enrich_phase_timings(prog["phase_timings"])
    return prog


def _write_log_line(job_id: str, time_str: str, phase: str, msg: str) -> None:
    try:
        job = get_upgrade_job(job_id)
        opts = (job or {}).get("options") or {}
        if job and not opts.get("execution_log_file"):
            path = ensure_execution_log_file(job_id)
            opts = dict(opts)
            opts["execution_log_file"] = str(path)
            update_upgrade_job(job_id, options=opts)
        elif not resolve_execution_log_path(job_id, job).is_file():
            ensure_execution_log_file(job_id)
    except Exception:
        ensure_execution_log_file(job_id)
    append_execution_log_line(job_id, msg, phase=phase, time_str=time_str)


def _append_progress_log(job_id: str, msg: str, phase: str = "") -> None:
    """Append one execution log line without changing the current progress message."""
    now = datetime.now()
    time_str = now.strftime("%H:%M:%S")
    file_ts = now.strftime("%Y-%m-%d %H:%M:%S")
    with _lock:
        prev = dict(_progress.get(job_id, {}))
        phase_val = phase or prev.get("phase", "")
        log = list(prev.get("log", []))
        log.append({
            "time": time_str,
            "phase": phase_val,
            "msg": msg,
        })
        prev["log"] = log[-UI_LOG_LIMIT:]
        _progress[job_id] = prev
    _write_log_line(job_id, file_ts, phase_val, msg)
    _save_progress_options(job_id, prev)


def _set_progress_message(job_id: str, message: str, phase: Optional[str] = None) -> None:
    """Update the visible status line without duplicating the execution log."""
    with _lock:
        prev = dict(_progress.get(job_id, {}))
        prev["message"] = message or ""
        if phase:
            prev["phase"] = phase
        _progress[job_id] = prev
    _save_progress_options(job_id, prev)


def _set_progress(job_id: str, data: Dict[str, Any]) -> None:
    skip_log = bool(data.pop("skip_log", False))
    with _lock:
        prev = dict(_progress.get(job_id, {}))
        msg = (data.get("message") or "").strip()
        if msg and not skip_log and msg != (prev.get("message") or "").strip():
            now = datetime.now()
            time_str = now.strftime("%H:%M:%S")
            file_ts = now.strftime("%Y-%m-%d %H:%M:%S")
            phase = data.get("phase", prev.get("phase", ""))
            log = list(prev.get("log", []))
            log.append({
                "time": time_str,
                "phase": phase,
                "msg": msg,
            })
            data["log"] = log[-UI_LOG_LIMIT:]
            _write_log_line(job_id, file_ts, phase, msg)
        elif "log" not in data and prev.get("log"):
            data["log"] = prev["log"]
        prev.update(data)
        _progress[job_id] = prev

    _save_progress_options(job_id, prev)


def _job_target_path(job: Dict[str, Any]) -> Path:
    """Local git cwd. Remote jobs use the SSH session repo path (_repo()), not this Path."""
    if is_remote_job(job):
        return Path(".")
    return Path(job["target_repo_dir"])


def _commit_finished_evidence(job: Dict[str, Any]) -> bool:
    """True only when auto-commit actually finished (not merely build success)."""
    if (job.get("phase") or "") == "done":
        return True
    opts = job.get("options") or {}
    for entry in reversed(opts.get("progress_log") or []):
        if "提交完成" in (entry.get("msg") or ""):
            return True
    return False


def reconcile_upgrade_job_record(job: Dict[str, Any]) -> Dict[str, Any]:
    """Fix legacy / inconsistent job records (conflicts, stale completed, etc.)."""
    if not job:
        return job
    job = dict(job)
    conflicts = job.get("conflict_files") or []
    if job.get("status") == "conflicts" and not conflicts:
        update_upgrade_job(job["id"], status="failed", phase="apply", conflict_files=[])
        job["status"] = "failed"
        job["phase"] = "apply"
        job["conflict_files"] = []

    if job.get("status") == "completed":
        opts = job.get("options") or {}
        if opts.get("auto_commit") and not _commit_finished_evidence(job):
            err = (job.get("error_msg") or "").strip() or "提交未完成（任务被中断或服务重启）"
            update_upgrade_job(
                job["id"],
                status="commit_failed",
                phase="commit",
                error_msg=err,
                completed_at="",
            )
            job["status"] = "commit_failed"
            job["phase"] = "commit"
            job["error_msg"] = err
    return job


def _job_target_repo(job: Dict[str, Any]) -> str:
    if is_remote_job(job):
        return normalize_linux_path(job["target_repo_dir"])
    return str(Path(job["target_repo_dir"]))


def cancel_upgrade(job_id: str) -> None:
    with _lock:
        _cancelled[job_id] = True


def _clear_cancelled(job_id: str) -> None:
    with _lock:
        _cancelled.pop(job_id, None)


def _is_cancelled(job_id: str) -> bool:
    with _lock:
        return _cancelled.get(job_id, False)


def _estimate_commit_count(patch_file: Path) -> int:
    try:
        count = 0
        with patch_file.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("From ") and " Mon Sep 17 " in line:
                    count += 1
        return count
    except OSError:
        return 0


def _resolve_patch_file(
    repo: str,
    from_tag: str,
    to_tag: str,
    analysis_task_id: str = "",
    patch_file: str = "",
) -> Tuple[Path, str]:
    if patch_file:
        p = Path(patch_file)
        if p.is_file():
            return p, "explicit"
    if analysis_task_id:
        task = get_task(analysis_task_id)
        if task:
            diff_file = (task.get("diff_file") or "").strip()
            if diff_file and Path(diff_file).is_file():
                return Path(diff_file), "task"
    cache = load_interval_diff_cache(repo, from_tag, to_tag)
    if cache:
        return cache.diff_file, "cache"
    raise FileNotFoundError(
        f"未找到区间 patch 文件: {from_tag}..{to_tag}，请先完成区间分析或指定 patch 路径"
    )


def _default_commit_message(from_tag: str, to_tag: str) -> str:
    return f"GKI upgrade: {from_tag} -> {to_tag}"


def commit_message_file_path(job: Dict[str, Any]) -> str:
    return ((job.get("options") or {}).get("commit_message_file") or "").strip()


def resolve_commit_message_file_abs(job: Dict[str, Any]) -> str:
    """Absolute path to commit message file on the machine where git runs."""
    rel_or_abs = commit_message_file_path(job)
    if not rel_or_abs:
        return ""
    norm = rel_or_abs.replace("\\", "/")
    remote = bool((job.get("options") or {}).get("remote"))
    root = (job.get("target_repo_dir") or "").rstrip("/\\")
    if norm.startswith("/"):
        return normalize_linux_path(norm) if remote else str(Path(norm).resolve())
    if remote:
        return f"{normalize_linux_path(root)}/{norm.lstrip('/')}"
    return str((Path(root) / norm).resolve())


def _is_remote_git_job(job: Dict[str, Any]) -> bool:
    """Remote or hybrid: git commands and commit-message checks run on SSH target."""
    return bool((job.get("options") or {}).get("remote"))


def _verify_commit_message_file(job: Dict[str, Any], abs_path: str) -> None:
    from web_app.upgrade_remote_git import is_remote_active, remote_file_exists

    if not abs_path:
        raise ValueError("commit message 文件路径为空")
    if _is_remote_git_job(job):
        if not is_remote_active():
            raise RuntimeError("远程 SSH 未连接，无法校验 commit message 文件")
        if not remote_file_exists(abs_path):
            raise FileNotFoundError(f"commit message 文件不存在: {abs_path}")
        return
    fp = Path(abs_path)
    if not fp.is_file():
        raise FileNotFoundError(f"commit message 文件不存在: {abs_path}")


def _read_commit_message_file_text(job: Dict[str, Any], abs_path: str) -> str:
    from web_app.upgrade_remote_git import is_remote_active, remote_read_absolute, remote_read_text

    rel = commit_message_file_path(job)
    if _is_remote_git_job(job):
        if not is_remote_active():
            raise RuntimeError("远程 SSH 未连接，无法读取 commit message 文件")
        if rel.replace("\\", "/").startswith("/"):
            text = remote_read_absolute(abs_path)
        else:
            text = remote_read_text(rel.lstrip("/"))
    else:
        text = Path(abs_path).read_text(encoding="utf-8", errors="replace")
    text = text.lstrip("\ufeff").strip()
    if not text:
        raise ValueError(f"commit message 文件为空: {abs_path}")
    return text


def _commit_message_preview(text: str, max_len: int = 120) -> str:
    line = text.splitlines()[0] if text else ""
    if len(line) <= max_len:
        return line
    return line[: max_len - 1] + "…"


def resolve_git_commit_message(
    job: Dict[str, Any],
    override: str = "",
) -> Tuple[str, str, str]:
    """Return (message_for_m, message_file_for_F, preview_for_ui)."""
    if override and override.strip():
        msg = override.strip()
        return msg, "", _commit_message_preview(msg)
    file_path = commit_message_file_path(job)
    if file_path:
        abs_path = resolve_commit_message_file_abs(job)
        _verify_commit_message_file(job, abs_path)
        preview = _commit_message_preview(_read_commit_message_file_text(job, abs_path))
        return "", abs_path, preview
    options = job.get("options") or {}
    msg = options.get("commit_message") or _default_commit_message(
        job.get("from_tag", ""), job.get("to_tag", ""),
    )
    return msg, "", _commit_message_preview(msg)


def start_upgrade(
    *,
    from_tag: str,
    to_tag: str,
    repo: str = "https://android.googlesource.com/kernel/common",
    analysis_task_id: str = "",
    patch_file: str = "",
    target_repo_dir: str = "",
    apply_mode: str = "",
    auto_commit: bool = False,
    auto_build: bool = False,
    auto_fix_build_errors: bool = False,
    build_fix_max_attempts: int = 0,
    auto_resolve_conflicts: bool = False,
    force_dirty: bool = False,
    create_backup: bool = True,
    upgrade_branch: str = "",
    commit_message: str = "",
    commit_message_file: str = "",
    build_command: str = "",
    build_workdir: str = "",
    remote_temp_dir: str = "",
    local_repo_mount: str = "",
    local_build_mount: str = "",
    remote: bool = False,
    remote_ssh: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Optional[str]]:
    if not from_tag or not to_tag:
        return "", "需要提供 from_tag 和 to_tag"

    raw_target = (target_repo_dir or "").strip()
    if not raw_target:
        return "", "每次合入必须指定目标代码路径 target_repo_dir"

    if remote:
        if not raw_target.startswith("/"):
            return "", "远程合入请填写 Linux 绝对路径，如 /data/.../vnd/kernel-5.10"
        target = normalize_linux_path(raw_target)
    else:
        target_path = resolve_target_repo_path(raw_target)
        if target_path is None or not repo_is_git(target_path):
            return "", f"目标代码路径无效或不是 git 仓库: {raw_target}"
        target = str(target_path)

    if remote and not remote_ssh:
        remote_ssh = get_saved_ssh_credentials()
    if remote and not remote_ssh:
        return "", (
            "远程合入需要 SSH 账号信息。"
            "请先在「系统设置 → 远程 SSH」保存 cqris 与目标机账号"
        )

    if remote and remote_ssh:
        for key, label in (
            ("bastion_user", "cqris 用户名"),
            ("bastion_password", "cqris 密码"),
            ("target_user", "目标机用户名"),
            ("target_password", "目标机密码"),
        ):
            if not str(remote_ssh.get(key) or "").strip():
                return "", f"远程合入需要填写{label}"

    build_cmd = (build_command or "").strip()
    build_wd = (build_workdir or "").strip()
    remote_temp = (remote_temp_dir or "").strip()

    local_mount = (local_repo_mount or "").strip()
    local_build_mount_val = (local_build_mount or "").strip()
    hybrid = bool(remote and local_mount)
    if hybrid:
        from web_app.job_path_mapping import validate_hybrid_mounts
        err = validate_hybrid_mounts(
            remote_target=target,
            local_repo_mount=local_mount,
            remote_build_workdir=build_wd,
            local_build_mount=local_build_mount_val,
        )
        if err:
            return "", err

    mode = apply_mode or get_apply_mode()
    if mode not in ("format-patch", "squash"):
        return "", f"不支持的 apply_mode: {mode}"

    if remote and not build_wd:
        return "", "远程合入需要填写编译工作目录（patch 将上传到该目录并保留供手动调试）"
    if remote and build_wd and not build_wd.startswith("/"):
        return "", "远程合入的编译工作目录请填写 Linux 绝对路径"
    if remote and remote_temp and not remote_temp.startswith("/"):
        return "", "远程临时工作目录请填写 Linux 绝对路径，留空则使用 /tmp"
    if auto_build:
        if not build_cmd:
            return "", "勾选自动编译时必须填写编译命令"
        if not build_wd:
            return "", "勾选自动编译时必须填写编译工作目录"
        if remote:
            if not build_wd.startswith("/"):
                return "", "远程编译请填写 Linux 绝对路径作为编译工作目录"
        elif resolve_build_workdir(build_wd) is None:
            return "", f"编译工作目录无效或不存在: {build_wd}"

    try:
        patch_path, _ = _resolve_patch_file(
            repo, from_tag, to_tag, analysis_task_id, patch_file,
        )
    except FileNotFoundError as exc:
        return "", str(exc)

    if mode == "squash":
        cache = load_interval_diff_cache(repo, from_tag, to_tag)
        if cache and cache.squash_file.is_file():
            patch_path = cache.squash_file
        else:
            squash_candidate = patch_path.parent / (
                patch_path.stem + "_squash" + patch_path.suffix
            )
            if squash_candidate.is_file():
                patch_path = squash_candidate

    job_id = uuid.uuid4().hex[:12]
    now = datetime.now().isoformat()
    log_stem = new_log_stem()
    log_path = init_execution_log(
        job_id,
        stem=log_stem,
        meta={
            "from_tag": from_tag,
            "to_tag": to_tag,
            "target_repo": target,
            "apply_mode": mode,
            "remote": remote,
            "patch_file": str(patch_path),
        },
    )
    from web_app.build_fix_service import (
        BUILD_FIX_MAX_ATTEMPTS_DEFAULT,
        normalize_build_fix_max_attempts,
    )

    options = {
        "auto_commit": auto_commit,
        "auto_build": auto_build,
        "auto_fix_build_errors": auto_fix_build_errors,
        "auto_resolve_conflicts": auto_resolve_conflicts,
        "build_fix_max_attempts": normalize_build_fix_max_attempts(
            build_fix_max_attempts or BUILD_FIX_MAX_ATTEMPTS_DEFAULT
        ),
        "force_dirty": force_dirty,
        "create_backup": create_backup,
        "upgrade_branch": (upgrade_branch or "").strip(),
        "commit_message": commit_message or _default_commit_message(from_tag, to_tag),
        "commit_message_file": (commit_message_file or "").strip(),
        "remote": remote,
        "hybrid": hybrid,
        "log_stem": log_stem,
        "execution_log_file": str(log_path),
    }
    create_upgrade_job({
        "id": job_id,
        "analysis_task_id": analysis_task_id,
        "repo": repo,
        "target_repo_dir": target,
        "from_tag": from_tag,
        "to_tag": to_tag,
        "apply_mode": mode,
        "patch_file": str(patch_path),
        "status": "pending",
        "phase": "prepare",
        "options": options,
        "created_at": now,
    })
    update_upgrade_job(
        job_id,
        total_commits=_estimate_commit_count(patch_path) if mode == "format-patch" else 1,
        build_command=build_cmd,
        build_workdir=build_wd,
        remote_temp_dir=normalize_linux_path(remote_temp) if remote_temp else "",
        local_repo_mount=str(Path(local_mount).resolve()) if hybrid else "",
        local_build_mount=str(Path(local_build_mount_val).resolve()) if local_build_mount_val else "",
    )
    mode_label = "（远程 SSH + 本地映射）" if hybrid else ("（远程 SSH）" if remote else "")
    _set_progress(job_id, {
        "status": "pending",
        "phase": "prepare",
        "message": f"升级任务已创建：{from_tag} → {to_tag}{mode_label}",
        "percent": 0,
        "detail": f"目标仓库: {target}" + (f"\n本地映射: {local_mount}" if hybrid else ""),
    })

    otp = str((remote_ssh or {}).get("otp") or "").strip()
    defer_ssh = remote and remote_ssh and len(otp) < 4

    if remote and remote_ssh:
        base = {k: v for k, v in remote_ssh.items() if k != "otp"}
        stash_ssh_credentials(job_id, base)

    if defer_ssh:
        update_upgrade_job(job_id, status="awaiting_ssh", phase="awaiting_otp")
        _set_progress(job_id, {
            "status": "awaiting_ssh",
            "phase": "awaiting_cqris",
            "message": "任务已创建：请先点击「连接 cqris」",
            "percent": 1,
            "detail": "等同 ssh -p 22 用户名@cqris.transsion.com，输入密码后再手动输入 OTP",
        })
        return job_id, None

    if remote and remote_ssh:
        stash_ssh_credentials(job_id, remote_ssh)

    thread = threading.Thread(
        target=_run_upgrade,
        args=(job_id,),
        daemon=True,
    )
    thread.start()
    return job_id, None


def connect_cqris_for_job(job_id: str) -> Tuple[bool, str]:
    """Phase 1: ssh to cqris with password; wait for manual OTP."""
    job = get_upgrade_job(job_id)
    if not job:
        return False, "任务不存在"
    if not is_remote_job(job):
        return False, "该任务不是远程 SSH 模式"
    if job.get("status") != "awaiting_ssh":
        return False, f"当前状态不可连接 cqris: {job.get('status')}"

    try:
        connect_cqris_bastion(job_id)
    except Exception as exc:
        update_upgrade_job(job_id, error_msg=str(exc))
        _set_progress(job_id, {
            "status": "awaiting_ssh",
            "phase": "awaiting_cqris",
            "message": f"连接 cqris 失败: {exc}",
        })
        return False, str(exc)

    from web_app.ssh_bastion import load_bastion_config
    cfg = load_bastion_config()
    base = get_stashed_ssh_credentials(job_id) or {}
    user = base.get("bastion_user", "")
    update_upgrade_job(job_id, status="awaiting_otp", phase="awaiting_otp", error_msg="")
    _set_progress(job_id, {
        "status": "awaiting_otp",
        "phase": "awaiting_otp",
        "message": f"已连接 cqris（ssh -p {cfg.bastion_port} {user}@{cfg.bastion_host}），请输入 OTP",
        "percent": 3,
        "detail": "请在手机打开验证器，输入 6 位动态码后点击「输入 OTP 并进入目标机」",
    })
    return True, "cqris 已连接，请输入 OTP"


def connect_upgrade_ssh(job_id: str, otp: str) -> Tuple[bool, str]:
    """Phase 2: OTP → target host, then start upgrade."""
    job = get_upgrade_job(job_id)
    if not job:
        return False, "任务不存在"
    if not is_remote_job(job):
        return False, "该任务不是远程 SSH 模式"
    if job.get("status") not in ("awaiting_otp", "awaiting_ssh"):
        return False, f"当前状态不可提交 OTP: {job.get('status')}"
    if job.get("status") == "awaiting_ssh" and not has_cqris_partial_session(job_id):
        return False, "请先点击「连接 cqris」，再输入 OTP"

    otp = (otp or "").strip()
    if len(otp) < 4:
        return False, "请输入 6 位动态验证码 (OTP)"

    stash_ssh_credentials(job_id, {"otp": otp})
    update_upgrade_job(job_id, status="running", phase="prepare", error_msg="")
    _append_progress_log(job_id, f"已收到 OTP: {otp}（共 {len(otp)} 位）", "awaiting_otp")
    _set_progress(job_id, {
        "status": "running",
        "phase": "prepare",
        "message": "正在使用 OTP 登录目标机…",
        "percent": 5,
        "skip_log": True,
    })
    threading.Thread(target=_run_upgrade, args=(job_id,), daemon=True).start()
    return True, "正在进入目标机并开始合入…"


def _run_upgrade(job_id: str) -> None:
    job = get_upgrade_job(job_id)
    if not job:
        return
    options = job.get("options") or {}
    remote = is_remote_job(job)
    target_repo = _job_target_repo(job) if remote else job["target_repo_dir"]
    target = Path(target_repo) if not remote else Path(".")
    progress_registered = False

    def _remote_progress_log(msg: str, phase: str = "") -> None:
        with _lock:
            p = phase or (_progress.get(job_id) or {}).get("phase") or "prepare"
        _append_progress_log(job_id, msg, p)

    try:
        if remote:
            register_job_progress(job_id, _remote_progress_log)
            progress_registered = True
        if remote and not is_remote_active():
            _phase_connect_ssh(job_id, target_repo, options)
            update_upgrade_job(job_id, status="running", phase="prepare")
        elif remote:
            _set_progress(job_id, {
                "status": "running",
                "phase": "prepare",
                "message": "SSH 已连接，开始检查远程仓库…",
                "percent": 8,
            })
        _phase_prepare(job_id, target, options)
        if _is_cancelled(job_id):
            raise RuntimeError("任务已取消")

        _phase_apply(job_id, target, job)
        if _is_cancelled(job_id):
            raise RuntimeError("任务已取消")

        job = get_upgrade_job(job_id) or job
        if job.get("status") == "conflicts":
            _set_progress(job_id, {
                "status": "conflicts",
                "phase": "conflicts",
                "message": "等待手动解决冲突后继续",
                "percent": 55,
                "conflict_files": job.get("conflict_files") or [],
                "skip_log": True,
            })
            return
        if job.get("status") == "failed":
            return

        if options.get("auto_build"):
            _set_progress(job_id, {
                "status": "running",
                "phase": "build",
                "message": "自动编译：准备启动编译…",
                "percent": 88,
            })
            _phase_build(job_id, target, job)
        else:
            job = get_upgrade_job(job_id) or job
            if job.get("status") == "applied":
                _set_progress(job_id, {
                    "status": "applied",
                    "phase": "applied",
                    "message": "Patch 已合入，可进行编译验证或手动提交",
                    "percent": 60,
                })
    except Exception as exc:
        if _is_cancelled(job_id) or str(exc) == "任务已取消":
            _end_active_phase_timings(job_id, "cancelled")
            _finalize_job_timing(job_id)
            update_upgrade_job(
                job_id,
                status="cancelled",
                phase="cancelled",
                error_msg="任务已取消",
                completed_at=datetime.now().isoformat(),
            )
            _set_progress(job_id, {
                "status": "cancelled",
                "phase": "cancelled",
                "message": "任务已取消",
            })
        elif remote and (
            has_cqris_partial_session(job_id) or not is_remote_active()
        ) and any(
            k in str(exc) for k in ("OTP", "SSH", "连接", "cqris", "验证码", "2nd Password", "堡垒")
        ):
            _end_active_phase_timings(job_id, "failed")
            revert = "awaiting_otp" if has_cqris_partial_session(job_id) else "awaiting_ssh"
            update_upgrade_job(job_id, status=revert, phase="awaiting_otp" if revert == "awaiting_otp" else "awaiting_cqris", error_msg=str(exc))
            _set_progress(job_id, {
                "status": revert,
                "phase": "awaiting_otp" if revert == "awaiting_otp" else "awaiting_cqris",
                "message": f"SSH 连接失败，请重试：{exc}",
            })
        else:
            _end_active_phase_timings(job_id, "failed")
            _finalize_job_timing(job_id)
            err_text = str(exc)
            update_upgrade_job(
                job_id,
                status="failed",
                error_msg=err_text,
                completed_at=datetime.now().isoformat(),
            )
            _append_progress_log(job_id, f"任务失败：{err_text}", "failed")
            _set_progress(job_id, {
                "status": "failed",
                "message": "任务失败",
                "skip_log": True,
            })
    finally:
        if progress_registered:
            unregister_job_progress(job_id)
        if remote:
            deactivate_remote_session()
            job = get_upgrade_job(job_id) or {}
            if is_ssh_terminal_status(job.get("status", "")):
                release_job_ssh(job_id)
            else:
                clear_ssh_otp(job_id)


def _phase_connect_ssh(job_id: str, target_repo: str, options: Dict[str, Any]) -> None:
    stashed = get_stashed_ssh_credentials(job_id) or {}
    otp = str(stashed.get("otp") or "").strip()
    if otp:
        _append_progress_log(job_id, f"向 cqris 发送 OTP: {otp}（共 {len(otp)} 位）", "prepare")
    target_ip = str(stashed.get("target_ip") or load_bastion_config().target_ip).strip()
    if target_ip:
        _append_progress_log(job_id, f"OTP 后将输入 IP 选择资产: {target_ip}（等同手动在「请选择目标资产：」后回车）", "prepare")
    repo = normalize_linux_path(target_repo)
    _set_progress(job_id, {
        "status": "running",
        "phase": "prepare",
        "message": "正在通过 cqris 连接远程服务器…",
        "percent": 2,
        "detail": repo,
    })
    connect_job_ssh(job_id, repo)
    _set_progress(job_id, {
        "status": "running",
        "phase": "prepare",
        "message": "SSH 连接成功，开始检查远程仓库…",
        "percent": 4,
    })


def _phase_prepare(job_id: str, target: Path, options: Dict[str, Any]) -> None:
    job = get_upgrade_job(job_id) or {}
    repo_label = _job_target_repo(job) if is_remote_job(job) else str(target)
    _begin_phase_timing(job_id, "prepare")
    if is_remote_job(job):
        _append_progress_log(job_id, f"准备阶段: 检查远程仓库 {repo_label}", "prepare")
    _set_progress(job_id, {
        "status": "running",
        "phase": "prepare",
        "message": "检查目标仓库是否为有效 git 仓库…",
        "percent": 5,
        "detail": repo_label,
    })
    update_upgrade_job(job_id, status="running", phase="prepare")

    if not repo_is_git(target):
        detail = ""
        if is_remote_job(job) and is_remote_active():
            from web_app.upgrade_remote_git import remote_repo_diagnose
            detail = remote_repo_diagnose()
        msg = f"目标路径不是 git 仓库: {repo_label}"
        if detail:
            msg += f"\n远程诊断:\n{detail}"
        raise RuntimeError(msg)

    _set_progress(job_id, {
        "status": "running",
        "phase": "prepare",
        "message": "检查并清理工作区…",
        "percent": 7,
    })

    if not is_clean_worktree(target) and not options.get("force_dirty"):
        was_dirty, clean_msg = ensure_clean_worktree(target)
        if was_dirty:
            _append_progress_log(job_id, clean_msg, "prepare")
            _set_progress(job_id, {
                "status": "running",
                "phase": "prepare",
                "message": "已自动清理工作区，可以合入",
                "percent": 8,
            })
        else:
            _append_progress_log(job_id, "工作区干净，可以合入", "prepare")
    elif not is_clean_worktree(target):
        status = working_tree_status(target).strip()
        _set_progress(job_id, {
            "status": "running",
            "phase": "prepare",
            "message": "工作区有未提交变更（已启用 force_dirty，跳过清理）",
            "percent": 8,
        })
        _append_progress_log(
            job_id,
            "force_dirty：保留当前工作区修改，直接合入\n" + (status[:500] if status else ""),
            "prepare",
        )
    else:
        _set_progress(job_id, {
            "status": "running",
            "phase": "prepare",
            "message": "工作区干净，可以合入",
            "percent": 8,
        })
        _append_progress_log(job_id, "工作区干净，可以合入", "prepare")

    _set_progress(job_id, {
        "status": "running",
        "phase": "prepare",
        "message": "解析 Gerrit 目标分支（repo start local .）…",
        "percent": 8,
    })
    try:
        from web_app.upgrade_git import capture_gerrit_review_branch

        gerrit_info = capture_gerrit_review_branch(target)
        opts = dict(job.get("options") or {})
        opts.update({k: v for k, v in gerrit_info.items() if v})
        update_upgrade_job(job_id, options=opts)
        job = get_upgrade_job(job_id) or job
        gerrit_branch = gerrit_info.get("gerrit_review_branch") or ""
        gerrit_remote = gerrit_info.get("gerrit_remote") or "origin"
        if gerrit_branch:
            _append_progress_log(
                job_id,
                f"已保存 Gerrit 推送分支: {gerrit_remote}/{gerrit_branch}",
                "prepare",
            )
        else:
            _append_progress_log(
                job_id,
                "未能从 git status 解析 Gerrit 分支，push 时将尝试 @{u} 或报错",
                "prepare",
            )
    except Exception as exc:
        _append_progress_log(
            job_id,
            f"repo start / git status 解析 Gerrit 分支失败（将 push 时重试）: {exc}",
            "prepare",
        )

    _set_progress(job_id, {
        "status": "running",
        "phase": "prepare",
        "message": "在合入目标目录执行 repo list . 解析仓名…",
        "percent": 9,
    })
    try:
        from web_app.build_fix_service import capture_repo_project_registry, repo_capture_dirs_for_job

        capture_dirs = repo_capture_dirs_for_job(job, options)
        registry = capture_repo_project_registry(job, capture_dirs)
        if registry:
            opts = dict(job.get("options") or {})
            opts["repo_project_registry"] = registry
            update_upgrade_job(job_id, options=opts)
            job = get_upgrade_job(job_id) or job
            names = sorted({
                v.get("repo_project")
                for v in registry.values()
                if isinstance(v, dict) and v.get("repo_project")
            })
            if names:
                preview = ", ".join(names[:8])
                extra = f" 等 {len(names)} 个" if len(names) > 8 else ""
                dirs_hint = ", ".join(capture_dirs[:3]) if capture_dirs else ""
                _append_progress_log(
                    job_id,
                    f"已在合入目标目录执行 repo list .（{dirs_hint}），已保存仓名: {preview}{extra}",
                    "prepare",
                )
            else:
                _append_progress_log(
                    job_id,
                    f"已保存 repo 路径索引（{len(registry)} 条）",
                    "prepare",
                )
    except Exception as exc:
        _append_progress_log(
            job_id,
            f"在合入目标目录执行 repo list . 失败（将在修改文件时于对应目录重试）: {exc}",
            "prepare",
        )

    if options.get("create_backup"):
        _set_progress(job_id, {
            "status": "running",
            "phase": "prepare",
            "message": "正在自动创建备份并切换合入分支（无需手动 SSH 操作）…",
            "percent": 9,
        })
        suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
        branch_before, sha_before = git_head_info(target)
        upgrade_branch = (options.get("upgrade_branch") or "").strip()
        backup, work = prepare_upgrade_branches(
            target, suffix, upgrade_branch=upgrade_branch,
        )
        opts = dict(job.get("options") or {})
        opts["work_branch"] = work
        opts["pre_upgrade_branch"] = branch_before
        opts["pre_upgrade_sha"] = sha_before
        update_upgrade_job(job_id, backup_branch=backup, options=opts)
        branch_after, sha_after = git_head_info(target)
        auto_note = (
            f"已从 {branch_before} @ {sha_before} 自动切换"
            if branch_before != work
            else f"已在 {work} @ {sha_after}"
        )
        detail = (
            f"合入前: {branch_before} @ {sha_before}\n"
            f"备份: {backup}\n"
            f"合入分支: {work} @ {sha_after}（{auto_note}）\n"
            f"回滚: git checkout {backup}"
        )
        _append_progress_log(job_id, detail.replace("\n", "；"), "prepare")
        _set_progress(job_id, {
            "status": "running",
            "phase": "prepare",
            "message": f"已就绪：在分支 {work} 上合入",
            "percent": 12,
            "backup_branch": backup,
            "detail": detail,
        })
    else:
        _set_progress(job_id, {
            "status": "running",
            "phase": "prepare",
            "message": "准备完成（未创建备份分支）",
            "percent": 12,
        })
    _end_phase_timing(job_id, "prepare", "done")


def _phase_apply(job_id: str, target: Path, job: Dict[str, Any]) -> None:
    patch_file = Path(job["patch_file"])
    if not patch_file.is_file():
        raise FileNotFoundError(f"patch 文件不存在: {patch_file}")

    mode = job.get("apply_mode", "format-patch")
    patch_name = patch_file.name
    commit_hint = job.get("total_commits") or 0
    _begin_phase_timing(job_id, "apply")
    _set_progress(job_id, {
        "status": "running",
        "phase": "apply",
        "message": f"开始合入 patch（{mode}）",
        "percent": 18,
        "detail": f"文件: {patch_name}" + (f"，约 {commit_hint} 个 commit" if commit_hint else ""),
    })
    update_upgrade_job(job_id, phase="apply")

    opts = job.get("options") or {}
    work = (opts.get("work_branch") or "").strip()
    branch_pre, sha_pre = git_head_info(target)
    if branch_pre == "HEAD":
        if not work:
            suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
            work = f"gki-upgrade-work-{suffix}"
            run_git(target, ["checkout", "-B", work, "HEAD"])
        else:
            run_git(target, ["checkout", work])
        branch_pre, sha_pre = git_head_info(target)
        _append_progress_log(
            job_id,
            f"检测到 detached HEAD，已自动切换到 {work} @ {sha_pre} 再合入",
            "apply",
        )
    else:
        _append_progress_log(
            job_id,
            f"合入前: 分支={branch_pre} @ {sha_pre}",
            "apply",
        )

    cmd_desc = "git am --3way" if mode == "format-patch" else "git apply --reject"
    _append_progress_log(job_id, f"合入模式: {mode}，patch: {patch_name} ({patch_file.stat().st_size / 1024 / 1024:.1f} MB)", "apply")
    _set_progress(job_id, {
        "status": "running",
        "phase": "apply",
        "message": f"准备合入（{mode}）…",
        "percent": 20,
        "detail": str(patch_file),
    })

    if is_remote_job(job):
        _append_progress_log(
            job_id,
            "远程合入流程: ① 上传 patch 到编译工作目录 → ② ls 校验 → ③ git apply/am（patch 保留不删）",
            "apply",
        )
    _set_progress(job_id, {
        "status": "running",
        "phase": "apply",
        "message": f"正在执行 {cmd_desc}…",
        "percent": 22,
        "detail": str(patch_file),
    })

    if mode == "format-patch":
        result = apply_format_patch(target, patch_file, job_id)
    else:
        result = apply_squash_patch(target, patch_file, job_id)

    apply_detail = (result.stderr.strip() or result.stdout.strip())
    apply_conflict_paths = parse_apply_conflict_files(apply_detail)
    _append_progress_log(
        job_id,
        f"git 合入命令结束: exit={result.returncode}"
        + (f"；{apply_detail[:500]}" if apply_detail else ""),
        "apply",
    )

    branch_now, sha_now = git_head_info(target)
    squash_apply = mode == "squash"
    rej_files = list_reject_files(target)
    changed_files = changed_files_from_status(
        target, squash_apply=squash_apply, rej_files=rej_files,
    )
    diff_stat = run_git(target, ["diff", "--stat", "HEAD"], check=False)
    stat_summary = diff_stat.stdout.strip().splitlines()[-1] if diff_stat.stdout.strip() else "无 diff"
    _append_progress_log(
        job_id,
        f"合入后: 分支={branch_now} @ {sha_now}；"
        f"工作区变更 {len(changed_files)} 个文件；"
        f".rej {len(rej_files)} 个；{stat_summary}",
        "apply",
    )
    if rej_files:
        _append_progress_log(
            job_id,
            f".rej 文件（需手动处理）: {', '.join(rej_files[:20])}"
            + (f" …等 {len(rej_files)} 个" if len(rej_files) > 20 else ""),
            "apply",
        )
    scan_targets = sorted(set(changed_files + apply_conflict_paths))
    conflicts = list_unmerged_files(target)
    # squash + --reject：冲突体现为 .rej，不会产生 <<<<<<< 标记，无需逐文件 grep
    if mode == "squash":
        marker_files: List[str] = []
    elif scan_targets:
        marker_files = has_conflict_markers(target, scan_targets)
    else:
        marker_files = []
    apply_conflict_on_disk = [f for f in apply_conflict_paths if f in changed_files]
    if apply_conflict_paths and not apply_conflict_on_disk and not changed_files:
        _append_progress_log(
            job_id,
            f"apply 日志提到冲突文件 {apply_conflict_paths}，"
            "但工作区无变更（请检查是否应使用 --reject）",
            "apply",
        )

    from web_app.conflict_policies import apply_android_gki_during_apply

    android_applied, android_failed = apply_android_gki_during_apply(
        job,
        target,
        rej_files=rej_files,
        extra_paths=conflicts + marker_files + apply_conflict_on_disk + apply_conflict_paths,
    )
    if android_applied:
        _append_progress_log(
            job_id,
            f"android/ 已在 apply 阶段 to_tag 自动写回 {len(android_applied)} 个: "
            f"{', '.join(android_applied)}",
            "apply",
        )
        android_applied_set = set(android_applied)
        rej_files = sorted(
            p for p in rej_files
            if (p[:-4] if p.endswith(".rej") else p) not in android_applied_set
        )
        changed_files = changed_files_from_status(
            target, squash_apply=squash_apply, rej_files=rej_files,
        )
        if mode != "squash" and scan_targets:
            marker_files = has_conflict_markers(target, scan_targets)
        else:
            marker_files = []
        conflicts = list_unmerged_files(target)
    if android_failed:
        _append_progress_log(
            job_id,
            f"android/ to_tag 自动写回失败（仍待人工处理）: {'; '.join(android_failed)}",
            "apply",
        )

    android_applied_set = set(android_applied)
    # 待手动处理：unmerged / .rej / 冲突标记；不要把全部已合入文件算作冲突
    raw_conflicts = sorted(set(conflicts + marker_files + apply_conflict_on_disk + rej_files))

    def _still_pending(path: str) -> bool:
        src = path[:-4] if path.endswith(".rej") else path
        return src not in android_applied_set

    all_conflicts = sorted(p for p in raw_conflicts if _still_pending(p))

    if not all_conflicts:
        if not result.ok:
            if rej_files:
                all_conflicts = sorted(p for p in rej_files if _still_pending(p))
            elif changed_files and mode == "squash":
                # 部分合入成功、无 .rej：视为已合入，无需逐文件排查
                _append_progress_log(
                    job_id,
                    f"git apply exit={result.returncode}，"
                    f"已合入 {len(changed_files)} 个文件，无 .rej，请按需检查日志",
                    "apply",
                )
            elif changed_files:
                all_conflicts = sorted(
                    p for p in set(marker_files + apply_conflict_on_disk) if _still_pending(p)
                )
            else:
                err_tail = (
                    f"git apply 未产生任何工作区变更（patch 未真正合入到 {branch_now} @ {sha_now}）。"
                    f" exit={result.returncode}。"
                    f" {(apply_detail or 'git 合入失败')[:1500]}"
                )
                update_upgrade_job(
                    job_id,
                    status="failed",
                    phase="apply",
                    conflict_files=[],
                    error_msg=err_tail,
                )
                _append_progress_log(job_id, f"合入失败：{err_tail}", "apply")
                _set_progress(job_id, {
                    "status": "failed",
                    "phase": "apply",
                    "message": "合入失败",
                    "percent": 55,
                    "conflict_files": [],
                    "skip_log": True,
                })
                _end_phase_timing(job_id, "apply", "failed")
                return

        if not changed_files:
            err_tail = (
                f"git apply 退出码为 0，但工作区无任何变更（{branch_now} @ {sha_now}）。"
                " 请检查 patch 是否为空或与当前基线一致。"
            )
            update_upgrade_job(
                job_id,
                status="failed",
                phase="apply",
                conflict_files=[],
                error_msg=err_tail,
            )
            _append_progress_log(job_id, f"合入异常：{err_tail}", "apply")
            _set_progress(job_id, {
                "status": "failed",
                "phase": "apply",
                "message": "合入失败",
                "percent": 55,
                "conflict_files": [],
                "skip_log": True,
            })
            _end_phase_timing(job_id, "apply", "failed")
            return

    if all_conflicts:
        err_tail = (apply_detail or "合入时产生冲突或未完全合入")[:1500]
        if rej_files:
            err_tail = (
                f"已合入 {len(changed_files)} 个文件，"
                f"待处理 .rej {len(rej_files)} 个：{', '.join(rej_files[:8])}"
                + (f" …等 {len(rej_files)} 个" if len(rej_files) > 8 else "")
            )
        elif not result.ok and changed_files and not marker_files and not apply_conflict_paths:
            err_tail = (
                f"git apply 部分合入（exit={result.returncode}），"
                f"{len(changed_files)} 个文件有变更，请检查后手动处理。"
                f" {err_tail[:800]}"
            )
        update_upgrade_job(
            job_id,
            status="conflicts",
            phase="conflicts",
            conflict_files=all_conflicts,
            error_msg=err_tail,
        )
        job = get_upgrade_job(job_id) or {}
        opts = dict(job.get("options") or {})
        opts["conflict_history_files"] = all_conflicts
        update_upgrade_job(job_id, options=opts)
        _append_progress_log(
            job_id,
            f"合入产生冲突（{len(all_conflicts)} 个文件）：{err_tail}",
            "conflicts",
        )
        _set_progress(job_id, {
            "status": "conflicts",
            "phase": "conflicts",
            "message": (
                f"合入产生冲突（{len(all_conflicts)} 个待处理文件，已合入 {len(changed_files)} 个）"
                if changed_files and rej_files
                else f"合入产生冲突（{len(all_conflicts)} 个文件）"
            ),
            "percent": 55,
            "conflict_files": all_conflicts,
            "skip_log": True,
        })
        _end_phase_timing(job_id, "apply", "conflicts")
        from web_app.conflict_resolution_service import schedule_ai_conflict_resolution
        auto_resolve = bool(opts.get("auto_resolve_conflicts"))
        if auto_resolve:
            _append_progress_log(job_id, "已启用自动冲突合入：AI 处理 → 写回 → 继续", "conflicts")
        schedule_ai_conflict_resolution(
            job_id,
            auto_apply=auto_resolve,
            auto_continue=auto_resolve,
        )
        return

    _set_progress(job_id, {
        "status": "running",
        "phase": "apply",
        "message": "Patch 合入成功",
        "percent": 50,
        "detail": "无冲突",
    })
    update_upgrade_job(job_id, status="applied", phase="applied", conflict_files=[])
    _end_phase_timing(job_id, "apply", "done")
    job = get_upgrade_job(job_id) or job
    from web_app.upgrade_staging import stage_apply_changes_for_job

    staged = stage_apply_changes_for_job(job_id, job)
    if staged:
        _append_progress_log(job_id, f"合入变更已 git add（{staged} 个路径，待编译成功后仅提交已暂存文件）", "apply")


def continue_after_conflicts(job_id: str, ssh_creds: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    job = get_upgrade_job(job_id)
    if not job:
        return False, "任务不存在"
    if job.get("status") != "conflicts":
        return False, f"当前状态不是 conflicts: {job.get('status')}"

    with remote_job_context(job_id, ssh_creds):
        return _continue_after_conflicts_impl(job_id, job)


def _continue_after_conflicts_impl(job_id: str, job: Dict[str, Any]) -> Tuple[bool, str]:
    target = _job_target_path(job)
    conflicts = list_unmerged_files(target)
    squash_apply = job.get("apply_mode") == "squash"
    changed = changed_files_from_status(target, squash_apply=squash_apply)
    rej = list_reject_files(target)
    markers: List[str] = []
    if job.get("apply_mode") != "squash":
        markers = (
            has_conflict_markers(target, changed)
            if changed
            else has_conflict_markers(target, conflicts or None)
        )
    if conflicts or markers or rej:
        pending = sorted(set(conflicts + markers + rej))
        update_upgrade_job(job_id, conflict_files=pending)
        hint = rej and f"仍有 .rej 文件: {', '.join(rej[:5])}" or f"仍有未解决冲突: {', '.join(pending[:10])}"
        return False, hint

    _begin_phase_timing(job_id, "apply")
    _set_progress(job_id, {
        "status": "running",
        "phase": "apply",
        "message": "冲突已解决，正在继续合入…",
        "percent": 48,
    })

    mode = job.get("apply_mode", "format-patch")
    if mode == "format-patch" and git_am_in_progress(target):
        _set_progress(job_id, {
            "status": "running",
            "phase": "apply",
            "message": "执行 git am --continue…",
            "percent": 50,
        })
        result = am_continue(target)
        if not result.ok:
            new_conflicts = list_unmerged_files(target)
            if new_conflicts:
                update_upgrade_job(
                    job_id,
                    status="conflicts",
                    phase="conflicts",
                    conflict_files=new_conflicts,
                    error_msg=result.stderr.strip(),
                )
                _end_phase_timing(job_id, "apply", "conflicts")
                return False, "git am --continue 后仍有冲突"
            return False, result.stderr.strip() or "git am --continue 失败"

        if git_am_in_progress(target):
            update_upgrade_job(job_id, status="conflicts", phase="conflicts")
            return False, "仍有后续 commit 待合入，请再次点击继续"

    update_upgrade_job(job_id, status="applied", phase="applied", conflict_files=[], error_msg="")
    _set_progress(job_id, {
        "status": "applied",
        "phase": "applied",
        "message": "冲突已全部解决，合入完成",
        "percent": 60,
    })
    _end_phase_timing(job_id, "apply", "done")
    job = get_upgrade_job(job_id) or job
    from web_app.upgrade_staging import stage_apply_changes_for_job

    staged = stage_apply_changes_for_job(job_id, job)
    if staged:
        _append_progress_log(
            job_id,
            f"冲突解决后已 git add（{staged} 个路径，待编译成功后仅提交已暂存文件）",
            "apply",
        )
    options = job.get("options") or {}
    if options.get("auto_build"):
        schedule_build_upgrade(job_id)
    return True, "冲突已解决，patch 合入完成"


def commit_upgrade(job_id: str, message: str = "", ssh_creds: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    job = get_upgrade_job(job_id)
    if not job:
        return False, "任务不存在"
    if job.get("status") not in ("applied", "committed"):
        return False, f"当前状态不可提交: {job.get('status')}"

    target = _job_target_path(job)
    if ssh_creds:
        stash_ssh_credentials(job_id, ssh_creds)
    try:
        with remote_job_context(job_id, ssh_creds):
            msg, msg_file, preview = resolve_git_commit_message(job, message)
            sha = _phase_commit(
                job_id, target, job,
                msg if msg else None, msg_file, preview,
            )
        job = get_upgrade_job(job_id) or job
        options = job.get("options") or {}
        if options.get("auto_build"):
            ok, build_msg = schedule_build_upgrade(job_id)
            if ok:
                return True, f"{sha}（已自动启动编译）"
            return True, f"{sha}（提交成功；自动编译未启动: {build_msg}）"
        return True, sha
    except Exception as exc:
        return False, str(exc)


def _is_commit_failed_job(job: Dict[str, Any]) -> bool:
    if (job.get("status") or "") == "commit_failed":
        return True
    return (
        job.get("status") == "build_failed"
        and (job.get("phase") or "") == "commit"
        and job.get("build_exit_code") == 0
    )


def retry_commit_upgrade(
    job_id: str,
    ssh_creds: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """Retry git commit/push after a successful build (compile ok, submit failed)."""
    job = get_upgrade_job(job_id)
    if not job:
        return False, "任务不存在"
    if not _is_commit_failed_job(job):
        return False, f"当前状态不可重试提交: {job.get('status')}"

    if ssh_creds:
        stash_ssh_credentials(job_id, ssh_creds)

    try:
        with remote_job_context(job_id, ssh_creds):
            _set_progress(job_id, {
                "status": "running",
                "phase": "commit",
                "message": "正在重新提交并推送…",
                "percent": 98,
            })
            from web_app.upgrade_staging import finalize_deferred_commits

            result = finalize_deferred_commits(job_id, job, push_remote=True)
            summaries = result.summary_lines()
            if not summaries:
                raise RuntimeError("提交/推送未产生任何结果")
            summary = "；".join(str(s) for s in summaries[:4])
            _append_progress_log(job_id, f"提交完成: {summary}", "commit")
            _end_phase_timing(job_id, "commit", "done")
            update_upgrade_job(job_id, status="completed", phase="done", error_msg="")
            job = get_upgrade_job(job_id) or job
            gerrit_submissions = (job.get("options") or {}).get("gerrit_submissions") or []
            _set_progress(job_id, {
                "status": "completed",
                "phase": "done",
                "message": f"升级流程全部完成（{summary}）",
                "percent": 100,
                "build_exit_code": 0,
                "gerrit_submissions": gerrit_submissions,
                "skip_log": True,
            })
            _finalize_job_timing(job_id)
        return True, summary
    except Exception as exc:
        err = str(exc).strip() or "提交失败"
        _append_progress_log(job_id, f"重新提交失败: {err}", "commit")
        update_upgrade_job(job_id, status="commit_failed", phase="commit", error_msg=err, build_exit_code=0)
        _set_progress(job_id, {
            "status": "commit_failed",
            "phase": "commit",
            "message": f"编译成功但提交失败: {err}",
            "percent": 98,
            "build_exit_code": 0,
            "gerrit_submissions": (get_upgrade_job(job_id) or {}).get("options", {}).get("gerrit_submissions") or [],
            "skip_log": True,
        })
        return False, err


def _phase_commit(
    job_id: str,
    target: Path,
    job: Dict[str, Any],
    message: Optional[str] = None,
    message_file: str = "",
    preview: str = "",
) -> str:
    update_upgrade_job(job_id, phase="commit")

    if message is None and not message_file:
        message, message_file, preview = resolve_git_commit_message(job)
    elif not preview:
        preview = _commit_message_preview(message or message_file)
    _begin_phase_timing(job_id, "commit")
    _append_progress_log(job_id, "正在提交代码…", "commit")
    _set_progress(job_id, {
        "status": "running",
        "phase": "commit",
        "message": "正在提交代码…",
        "percent": 72,
        "detail": (preview or message or message_file)[:120],
    })

    mode = job.get("apply_mode", "format-patch")
    if mode == "squash" or not git_am_in_progress(target):
        if not is_clean_worktree(target):
            stage_all(target)
            sha = commit(target, message or "", message_file=message_file)
        else:
            sha = head_sha(target)
    else:
        stage_all(target)
        result = am_continue(target)
        if not result.ok:
            raise RuntimeError(result.stderr.strip() or "git am --continue 失败")
        sha = head_sha(target)

    update_upgrade_job(job_id, status="committed", phase="committed", commit_sha=sha)
    _set_progress(job_id, {
        "status": "committed",
        "phase": "committed",
        "message": f"提交完成: {sha[:12]}",
        "percent": 85,
        "commit_sha": sha,
        "detail": (preview or message or message_file)[:200],
    })
    _end_phase_timing(job_id, "commit", "done")
    return sha


def is_build_running(job_id: str) -> bool:
    with _lock:
        return job_id in _build_running


def schedule_build_upgrade(
    job_id: str,
    build_command: str = "",
    build_workdir: str = "",
    ssh_creds: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """Start build in a background thread (HTTP returns immediately)."""
    job = get_upgrade_job(job_id)
    if not job:
        return False, "任务不存在"
    if job.get("status") not in ("committed", "applied", "completed", "build_failed"):
        return False, f"当前状态不可编译: {job.get('status')}"
    with _lock:
        if job_id in _build_running:
            return False, "编译已在进行中，请稍候"
        _build_running.add(job_id)

    if ssh_creds:
        stash_ssh_credentials(job_id, ssh_creds)

    def _worker() -> None:
        try:
            _run_build(job_id, build_command, build_workdir)
        finally:
            with _lock:
                _build_running.discard(job_id)
            job = get_upgrade_job(job_id) or {}
            if is_remote_job(job) and is_ssh_terminal_status(job.get("status", "")):
                release_job_ssh(job_id)

    threading.Thread(
        target=_worker,
        daemon=True,
        name=f"upgrade-build-{job_id}",
    ).start()
    return True, "编译已在后台启动，请查看下方日志"


def _run_build(
    job_id: str,
    build_command: str = "",
    build_workdir: str = "",
) -> None:
    job = get_upgrade_job(job_id)
    if not job:
        return
    target = _job_target_path(job)
    try:
        with remote_job_context(job_id):
            _phase_build(job_id, target, job, build_command, build_workdir)
    except Exception as exc:
        _append_progress_log(job_id, f"编译失败: {exc}", "build")
        job = get_upgrade_job(job_id) or job
        if job.get("status") not in ("completed", "build_failed"):
            update_upgrade_job(job_id, status="build_failed", phase="build", error_msg=str(exc))
            _set_progress(job_id, {
                "status": "build_failed",
                "phase": "build",
                "message": f"编译失败: {exc}",
                "percent": 95,
                "skip_log": True,
            })


def build_upgrade(
    job_id: str,
    build_command: str = "",
    build_workdir: str = "",
    ssh_creds: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    return schedule_build_upgrade(job_id, build_command, build_workdir, ssh_creds)


def _complete_build_result(
    job_id: str,
    code: int,
    log_path: Path,
) -> None:
    job = get_upgrade_job(job_id) or {}
    options = job.get("options") or {}
    auto_commit = bool(options.get("auto_commit"))
    build_status = "done" if code == 0 else "failed"
    _end_phase_timing(job_id, "build", build_status)
    if code != 0:
        update_upgrade_job(
            job_id,
            status="build_failed",
            build_exit_code=code,
            build_log_file=str(log_path),
        )
        _append_progress_log(job_id, f"编译失败 (exit {code})，详见下方编译日志", "build")
        _set_progress(job_id, {
            "status": "build_failed",
            "phase": "build",
            "message": "编译失败",
            "percent": 95,
            "build_log_file": str(log_path),
            "build_exit_code": code,
            "skip_log": code != 0,
        })
        return

    post_build_status = "running" if auto_commit else "completed"
    post_build_phase = "build" if auto_commit else "done"
    update_upgrade_job(
        job_id,
        status=post_build_status,
        phase=post_build_phase,
        build_exit_code=code,
        build_log_file=str(log_path),
        completed_at=datetime.now().isoformat() if not auto_commit else "",
    )

    _append_progress_log(job_id, "编译成功", "build")
    job = get_upgrade_job(job_id) or {}
    options = job.get("options") or {}
    commit_summary = ""
    if options.get("auto_commit"):
        try:
            update_upgrade_job(job_id, status="running", phase="commit")
            _set_progress(job_id, {
                "status": "running",
                "phase": "commit",
                "message": "编译成功，正在统一提交并推送…",
                "percent": 98,
            })
            from web_app.upgrade_staging import finalize_deferred_commits

            with remote_job_context(job_id):
                result = finalize_deferred_commits(job_id, job, push_remote=True)
            summaries = result.summary_lines()
            if summaries:
                commit_summary = "；".join(str(s) for s in summaries[:4])
                _append_progress_log(job_id, f"提交完成: {commit_summary}", "commit")
                job = get_upgrade_job(job_id) or job
                if not job.get("commit_sha") and result.submissions:
                    update_upgrade_job(job_id, commit_sha=str(result.submissions[0].get("commit_sha") or "")[:40])
            _end_phase_timing(job_id, "commit", "done")
        except Exception as exc:
            err = str(exc).strip() or "自动提交失败"
            _append_progress_log(job_id, f"自动提交失败: {err}", "commit")
            _end_phase_timing(job_id, "commit", "failed")
            update_upgrade_job(
                job_id,
                status="commit_failed",
                phase="commit",
                error_msg=err,
                build_exit_code=0,
            )
            job = get_upgrade_job(job_id) or {}
            _set_progress(job_id, {
                "status": "commit_failed",
                "phase": "commit",
                "message": f"编译成功但提交失败: {err}",
                "percent": 98,
                "build_log_file": str(log_path),
                "build_exit_code": 0,
                "gerrit_submissions": (job.get("options") or {}).get("gerrit_submissions") or [],
                "skip_log": True,
            })
            return

    done_msg = "升级流程全部完成"
    if commit_summary:
        done_msg += f"（{commit_summary}）"
    job = get_upgrade_job(job_id) or {}
    gerrit_submissions = (job.get("options") or {}).get("gerrit_submissions") or []
    _set_progress(job_id, {
        "status": "completed",
        "phase": "done",
        "message": done_msg,
        "percent": 100,
        "build_log_file": str(log_path),
        "build_exit_code": code,
        "gerrit_submissions": gerrit_submissions,
        "skip_log": True,
    })
    update_upgrade_job(
        job_id,
        status="completed",
        phase="done",
        completed_at=datetime.now().isoformat(),
    )
    _finalize_job_timing(job_id)


def _run_single_build(
    job_id: str,
    target: Path,
    job: Dict[str, Any],
    build_command: str = "",
    build_workdir: str = "",
    *,
    build_attempt: int = 1,
) -> Tuple[int, Path]:
    cmd = (build_command or job.get("build_command") or "").strip()
    wd_raw = (build_workdir or job.get("build_workdir") or "").strip()
    if not cmd:
        raise RuntimeError("需要提供编译命令 build_command")
    if not wd_raw:
        raise RuntimeError("需要提供编译工作目录 build_workdir")

    if is_remote_job(job):
        cwd = normalize_linux_path(wd_raw)
        if not cwd.startswith("/"):
            raise RuntimeError(f"远程编译工作目录应为 Linux 绝对路径: {wd_raw}")
    else:
        cwd = resolve_build_workdir(wd_raw)
        if cwd is None:
            raise RuntimeError(f"编译工作目录无效或不存在: {wd_raw}")
        cwd = str(cwd)

    BUILD_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = resolve_build_log_path(job_id, job)
    remote_log = job_remote_temp_join(job, f"gki_build_{job_id}.log")

    header = (
        f"# build command: {cmd}\n"
        f"# cwd: {cwd}\n"
        f"# attempt: {build_attempt}\n"
        f"# started: {datetime.now().isoformat()}\n\n"
    )
    # 每次编译开始时清空旧日志，保证 build_fix 只解析本轮输出（不累积多轮 attempt）
    log_path.write_text(header, encoding="utf-8")
    if is_remote_job(job):
        from web_app.upgrade_remote_git import reset_build_log_remote_sync
        reset_build_log_remote_sync(log_path)

    _build_hb = {"last_ts": 0.0}
    _BUILD_PROGRESS_INTERVAL = 30.0

    def _on_build_log_update(last_line: str = "") -> None:
        now = _now_ts()
        if _build_hb["last_ts"] and now - _build_hb["last_ts"] < _BUILD_PROGRESS_INTERVAL:
            return
        _build_hb["last_ts"] = now
        tail = (last_line or "").strip()[-200:]
        size_hint = ""
        try:
            if log_path.is_file():
                mb = log_path.stat().st_size / (1024 * 1024)
                if mb >= 0.01:
                    size_hint = f" · 已写 {mb:.1f} MB"
        except OSError:
            pass
        progress_msg = "编译中"
        if size_hint:
            progress_msg += size_hint
        if tail:
            progress_msg += f" · {tail}"
        _append_progress_log(job_id, progress_msg, "build")
        detail = f"目录: {cwd}\n命令: {cmd}"
        if tail:
            detail += f"\n最新: {tail}"
        if size_hint:
            detail += f"\n{size_hint.lstrip(' · ')}"
        _set_progress(job_id, {
            "status": "running",
            "phase": "build",
            "message": "编译进行中…",
            "percent": 92,
            "detail": detail[:500],
            "build_log_file": str(log_path),
            "skip_log": True,
        })

    if build_attempt == 1:
        _begin_phase_timing(job_id, "build")
    label = "重新编译" if build_attempt > 1 else "编译"
    if build_attempt > 1:
        _append_progress_log(job_id, "已清空上次编译日志，开始新一轮编译", "build")
    _append_progress_log(job_id, f"{label}已启动 (第 {build_attempt} 次): {cmd}", "build")
    _append_progress_log(job_id, f"编译目录: {cwd}", "build")
    _set_progress(job_id, {
        "status": "running",
        "phase": "build",
        "message": "正在启动编译…",
        "percent": 90,
        "detail": f"目录: {cwd}\n命令: {cmd}",
        "build_log_file": str(log_path),
    })
    update_upgrade_job(
        job_id, phase="build", status="running",
        build_command=cmd, build_workdir=cwd,
        build_log_file=str(log_path),
    )

    timeout = get_build_timeout()
    if is_remote_job(job):
        from web_app.upgrade_remote_git import remote_fetch_build_log, remote_run_build

        code = remote_run_build(
            cwd, cmd, remote_log, timeout,
            local_log=log_path,
            on_log_update=_on_build_log_update,
        )
        remote_fetch_build_log(remote_log, log_path)
    else:
        with log_path.open("a", encoding="utf-8") as log_f:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                log_f.write(line)
                log_f.flush()
                if line.strip():
                    _on_build_log_update(line.rstrip("\n"))
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                raise RuntimeError(f"编译超时 ({timeout}s)") from None
            log_f.write(f"\n\n# exit code: {code}\n")

    return code, log_path


def _phase_build(
    job_id: str,
    target: Path,
    job: Dict[str, Any],
    build_command: str = "",
    build_workdir: str = "",
) -> Path:
    options = job.get("options") or {}
    auto_fix = bool(options.get("auto_fix_build_errors"))
    from web_app.build_fix_service import (
        normalize_build_fix_max_attempts,
        persisted_build_fix_round_count,
    )
    max_attempts = normalize_build_fix_max_attempts(options.get("build_fix_max_attempts"))
    job = get_upgrade_job(job_id) or job
    fix_round = persisted_build_fix_round_count(job)
    build_attempt = fix_round
    if fix_round > 0:
        _append_progress_log(
            job_id,
            f"继续编译/修复流程（已完成 {fix_round} 轮 AI 编译修复，本次编译为第 {fix_round + 1} 次）",
            "build",
        )

    while True:
        build_attempt += 1
        job = get_upgrade_job(job_id) or job
        code, log_path = _run_single_build(
            job_id, target, job, build_command, build_workdir,
            build_attempt=build_attempt,
        )
        if code == 0:
            _complete_build_result(job_id, code, log_path)
            opts = dict((get_upgrade_job(job_id) or {}).get("options") or {})
            bf = dict(opts.get("build_fix") or {})
            if bf.get("status") == "running":
                bf["status"] = "success"
                opts["build_fix"] = bf
                update_upgrade_job(job_id, options=opts)
            return log_path

        if not auto_fix or fix_round >= max_attempts:
            _complete_build_result(job_id, code, log_path)
            if auto_fix and fix_round >= max_attempts:
                _append_progress_log(
                    job_id,
                    f"已达 AI 修复上限（已累计 {fix_round} 轮，上限 {max_attempts} 轮），自动修复已停止。可点击「AI 修复并重试」继续。",
                    "build_fix",
                )
                raise RuntimeError(
                    f"编译失败，已达 AI 修复上限（已累计 {fix_round}/{max_attempts} 轮）。请点击「AI 修复并重试」继续处理。"
                )
            raise RuntimeError(f"编译失败，exit code={code}")

        fix_round += 1
        _append_progress_log(
            job_id,
            f"编译失败 (exit {code})，AI 修复第 {fix_round}/{max_attempts} 轮…",
            "build_fix",
        )
        _set_progress(job_id, {
            "status": "running",
            "phase": "build_fix",
            "message": f"编译失败，AI 修复中（第 {fix_round}/{max_attempts} 轮，LLM 分析约 1～10 分钟）…",
            "percent": 93,
            "build_log_file": str(log_path),
            "build_exit_code": code,
            "build_fix_attempt": fix_round,
            "skip_log": True,
        })
        update_upgrade_job(job_id, phase="build_fix", status="running")

        from web_app.build_fix_service import run_build_fix_attempt

        result = run_build_fix_attempt(job_id, str(log_path), fix_round)
        if not result.get("applied"):
            _complete_build_result(job_id, code, log_path)
            detail = result.get("error") or "AI 未能修复编译错误"
            raise RuntimeError(f"编译失败且 AI 修复未成功: {detail}")

        summary = result.get("summary") or ""
        _append_progress_log(
            job_id,
            f"AI 修复已写回，准备重新编译: {summary}",
            "build_fix",
        )
        _set_progress(job_id, {
            "status": "running",
            "phase": "build",
            "message": f"AI 修复完成，重新编译中… ({summary})",
            "percent": 91,
            "build_log_file": str(log_path),
            "skip_log": True,
        })
        update_upgrade_job(job_id, phase="build", status="running")


def cancel_upgrade_job(job_id: str) -> Tuple[bool, str]:
    """Cancel an upgrade job; abort git am if in progress."""
    job = get_upgrade_job(job_id)
    if not job:
        return False, "任务不存在"

    status = job.get("status", "")
    if status in ("completed", "cancelled", "aborted"):
        return False, f"当前状态不可取消: {status}"

    with _lock:
        prog = dict(_progress.get(job_id, {}))

    resume_point = _capture_resume_point(job, prog)
    opts = dict(job.get("options") or {})
    opts["resume_point"] = resume_point

    cancel_upgrade(job_id)
    _end_active_phase_timings(job_id, "cancelled")
    _finalize_job_timing(job_id)
    release_job_ssh(job_id)
    target = _job_target_path(job)
    if not is_remote_job(job) and target.exists() and repo_is_git(target):
        try:
            am_abort(target)
        except Exception:
            pass

    phase_label = resume_point.get("phase") or resume_point.get("status") or "未知"
    update_upgrade_job(
        job_id,
        status="cancelled",
        phase="cancelled",
        error_msg="任务已取消",
        completed_at=datetime.now().isoformat(),
        options=opts,
    )
    _append_progress_log(job_id, f"任务已取消（断点: {phase_label}）", "cancelled")
    _set_progress(job_id, {
        "status": "cancelled",
        "phase": "cancelled",
        "message": f"任务已取消（可从「{phase_label}」继续）",
        "percent": prog.get("percent") or 0,
        "resume_point": resume_point,
    })
    return True, "任务已取消"


_RESUME_PHASE_LABELS = {
    "conflicts": "冲突合入",
    "build": "编译验证",
    "build_fix": "AI 编译修复",
    "build_failed": "编译验证",
    "commit": "提交代码",
    "committed": "编译验证",
    "applied": "合入完成",
    "apply": "合入 Patch",
    "prepare": "准备环境",
}


def _resolve_resume_action(
    job: Dict[str, Any],
    target: Path,
    rp: Dict[str, Any],
) -> str:
    """Decide how to resume from saved cancel checkpoint + current git state."""
    rp = _normalize_resume_point(job, rp)
    status = (rp.get("status") or "").strip()
    phase = (rp.get("phase") or "").strip()
    options = job.get("options") or {}
    bf = options.get("build_fix") or {}

    conflicts = list_unmerged_files(target)
    rej = list_reject_files(target)
    if conflicts or rej or git_am_in_progress(target):
        return "conflicts_continue"

    if status == "conflicts" or phase == "conflicts":
        return "conflicts_continue"

    if phase == "build_fix" or bf.get("status") == "running":
        return "build_fix"

    if status == "build_failed" or phase in ("build", "build_failed"):
        return "build"

    if status == "commit_failed":
        return "commit_only"

    build_evidence = bool(
        job.get("build_log_file") or job.get("build_command") or bf
    )
    if build_evidence and job.get("commit_sha"):
        return "build"

    if status == "committed" or phase in ("commit", "committed"):
        if options.get("auto_build"):
            return "build"
        return "restore_applied"

    if phase == "commit" or (status == "running" and phase == "commit"):
        if options.get("auto_build"):
            return "build"
        return "restore_applied"

    if status == "applied" or phase == "applied":
        if options.get("auto_build"):
            return "build"
        return "restore_applied"

    if status == "running" and phase in ("apply", "prepare"):
        return "restore_conflicts" if (conflicts or git_am_in_progress(target)) else "restore_applied"

    return "restore_applied"


def _resume_upgrade_worker(job_id: str) -> None:
    job = get_upgrade_job(job_id)
    if not job:
        return
    rp = _normalize_resume_point(
        job, (job.get("options") or {}).get("resume_point") or {}
    )
    options = job.get("options") or {}
    try:
        with remote_job_context(job_id):
            target = _job_target_path(job)
            action = _resolve_resume_action(job, target, rp)

            if action == "conflicts_continue":
                conflicts = list_unmerged_files(target)
                if conflicts:
                    update_upgrade_job(
                        job_id,
                        status="conflicts",
                        phase="conflicts",
                        conflict_files=conflicts,
                        error_msg="",
                    )
                else:
                    update_upgrade_job(job_id, status="conflicts", phase="conflicts", error_msg="")
                ok, msg = _continue_after_conflicts_impl(job_id, get_upgrade_job(job_id) or job)
                if not ok:
                    cur = get_upgrade_job(job_id) or job
                    if cur.get("status") == "conflicts":
                        _set_progress(job_id, {
                            "status": "conflicts",
                            "phase": "conflicts",
                            "message": msg,
                            "percent": 55,
                        })
                    else:
                        update_upgrade_job(job_id, error_msg=msg)
                return

            if action == "build_fix":
                opts = dict(options)
                opts["auto_fix_build_errors"] = True
                update_upgrade_job(job_id, status="build_failed", phase="build", options=opts, error_msg="")
                _run_build(job_id)
                return

            if action == "build":
                st = "committed" if job.get("commit_sha") else "applied"
                update_upgrade_job(job_id, status=st, phase="build", error_msg="")
                _run_build(job_id)
                return

            if action == "commit_then_build":
                if (job.get("options") or {}).get("auto_build"):
                    _run_build(job_id)
                return

            if action == "commit_only":
                from web_app.upgrade_staging import finalize_deferred_commits

                finalize_deferred_commits(job_id, job, push_remote=True)
                return

            if action == "restore_conflicts":
                conflicts = list_unmerged_files(target) or job.get("conflict_files") or []
                update_upgrade_job(
                    job_id,
                    status="conflicts",
                    phase="conflicts",
                    conflict_files=conflicts,
                    error_msg="",
                )
                _set_progress(job_id, {
                    "status": "conflicts",
                    "phase": "conflicts",
                    "message": "已恢复至冲突待处理，请解决后继续",
                    "percent": 55,
                    "conflict_files": conflicts,
                })
                return

            update_upgrade_job(job_id, status="applied", phase="applied", error_msg="")
            _set_progress(job_id, {
                "status": "applied",
                "phase": "applied",
                "message": "任务已恢复，可手动提交或编译",
                "percent": 60,
            })
    except Exception as exc:
        if _is_cancelled(job_id) or str(exc) == "任务已取消":
            return
        update_upgrade_job(job_id, status="failed", phase="failed", error_msg=str(exc))
        _set_progress(job_id, {"status": "failed", "phase": "failed", "message": str(exc)})


def resume_upgrade_job(
    job_id: str,
    ssh_creds: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """Resume a cancelled job from the saved checkpoint."""
    job = get_upgrade_job(job_id)
    if not job:
        return False, "任务不存在"
    if job.get("status") != "cancelled":
        return False, f"当前状态不可继续: {job.get('status')}"

    rp = _normalize_resume_point(
        job, (job.get("options") or {}).get("resume_point") or {}
    )
    phase = (rp.get("phase") or rp.get("status") or "").strip()
    label = _RESUME_PHASE_LABELS.get(phase, phase or "上次进度")
    # build_fix resume immediately runs compile; UI step map only knows prepare/apply/build/commit
    ui_phase = "build" if phase in ("build_fix", "build_failed") else (phase or "resume")

    _clear_cancelled(job_id)
    if ssh_creds:
        stash_ssh_credentials(job_id, ssh_creds)

    opts = dict(job.get("options") or {})
    opts["resume_point"] = {**(opts.get("resume_point") or {}), **rp}
    update_upgrade_job(
        job_id,
        status="running",
        phase=ui_phase,
        error_msg="",
        completed_at="",
        options=opts,
    )
    _append_progress_log(job_id, f"继续执行（取消前: {label}）", "resume")
    _set_progress(job_id, {
        "status": "running",
        "phase": ui_phase,
        "message": f"正在从「{label}」继续…",
        "percent": rp.get("percent") if rp.get("percent") is not None else 50,
        "skip_log": True,
    })

    threading.Thread(
        target=_resume_upgrade_worker,
        args=(job_id,),
        daemon=True,
        name=f"upgrade-resume-{job_id}",
    ).start()
    return True, f"已从「{label}」继续执行"


def abort_upgrade(job_id: str) -> Tuple[bool, str]:
    """Backward-compatible alias for cancel."""
    return cancel_upgrade_job(job_id)
