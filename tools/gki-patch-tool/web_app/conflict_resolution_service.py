"""AI-assisted merge conflict resolution for GKI upgrade jobs."""
from __future__ import annotations

import difflib
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from web_app.conflict_region_utils import extract_conflict_regions
from web_app.conflict_policies import resolve_android_with_to_tag
from web_app.database import get_upgrade_job, update_upgrade_job
from web_app.llm_service import is_llm_configured
from web_app.upgrade_progress import append_job_log
from web_app.upgrade_ssh_manager import has_pooled_ssh_session, is_remote_job, remote_job_context

_lock = threading.Lock()
_ai_running: set[str] = set()

_MAX_STORE_CHARS = 400_000


def _log(job_id: str, msg: str) -> None:
    append_job_log(job_id, msg, "conflicts")


def source_path_from_conflict(conflict_path: str) -> str:
    if conflict_path.endswith(".rej"):
        return conflict_path[:-4]
    return conflict_path


def _read_repo_text(job: Dict[str, Any], rel_path: str) -> str:
    from web_app.job_file_io import read_repo_rel
    return read_repo_rel(job, rel_path)


def _write_repo_text(job: Dict[str, Any], rel_path: str, content: str) -> None:
    from web_app.job_file_io import write_repo_rel
    write_repo_rel(job, rel_path, content)


def _remove_remote_file(job: Dict[str, Any], rel_path: str) -> None:
    from web_app.job_file_io import remove_repo_rel
    remove_repo_rel(job, rel_path)


def make_unified_diff(path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )


def _get_resolutions(job: Dict[str, Any]) -> Dict[str, Any]:
    opts = job.get("options") or {}
    cr = opts.get("conflict_resolutions")
    if not isinstance(cr, dict):
        cr = {"ai_status": "idle", "files": {}}
    if "files" not in cr:
        cr["files"] = {}
    return cr


def _save_resolutions(job_id: str, job: Dict[str, Any], cr: Dict[str, Any]) -> None:
    opts = dict(job.get("options") or {})
    opts["conflict_resolutions"] = cr
    update_upgrade_job(job_id, options=opts)


def _trim_store(text: str) -> str:
    if len(text) <= _MAX_STORE_CHARS:
        return text
    half = _MAX_STORE_CHARS // 2
    return text[:half] + f"\n... [truncated {len(text) - _MAX_STORE_CHARS} chars for storage] ...\n" + text[-half:]


def _build_file_resolution(
    job: Dict[str, Any],
    conflict_path: str,
) -> Dict[str, Any]:
    source = source_path_from_conflict(conflict_path)
    kind = "rej" if conflict_path.endswith(".rej") else "markers"
    original = _read_repo_text(job, source)
    rej_content = ""
    if kind == "rej":
        try:
            rej_content = _read_repo_text(job, conflict_path)
        except FileNotFoundError:
            rej_content = ""
    return {
        "conflict_path": conflict_path,
        "source_path": source,
        "kind": kind,
        "status": "pending",
        "original": _trim_store(original),
        "rej_content": _trim_store(rej_content),
        "proposed": "",
        "diff": "",
        "summary": "",
        "strategy": "",
        "error": "",
        "confirmed": False,
        "applied": False,
        "updated_at": datetime.now().isoformat(),
    }


def _resolve_one_with_ai(job_id: str, job: Dict[str, Any], entry: Dict[str, Any]) -> Dict[str, Any]:
    source = entry["source_path"]
    original = _read_repo_text(job, source)
    rej = entry.get("rej_content") or ""
    if entry["kind"] == "rej" and not rej:
        try:
            rej = _read_repo_text(job, entry["conflict_path"])
        except FileNotFoundError:
            pass
    elif entry["kind"] == "rej" and rej and "truncated" in rej[:2000].lower():
        try:
            rej = _read_repo_text(job, entry["conflict_path"])
        except FileNotFoundError:
            pass

    # android/ 元数据：优先 to_tag 直取，不走 LLM
    try:
        tag_result = resolve_android_with_to_tag(job, source, original_content=original)
        if tag_result:
            proposed, summary, strategy = tag_result
            entry["proposed"] = _trim_store(proposed)
            entry["original"] = _trim_store(original)
            entry["diff"] = make_unified_diff(source, original, proposed)
            entry["summary"] = summary
            entry["strategy"] = strategy
            entry["status"] = "ai_done"
            entry["error"] = ""
            _log(job_id, f"to_tag 直取已生成: {source} ({strategy})")
            entry["updated_at"] = datetime.now().isoformat()
            return entry
    except Exception as exc:
        _log(job_id, f"android/ to_tag 策略失败 {source}，回退 LLM: {exc}")

    try:
        from web_app.conflict_merge_service import resolve_conflict_file

        proposed, summary, strategy = resolve_conflict_file(
            job,
            job_id=job_id,
            source_path=source,
            original_content=original,
            rej_content=rej,
            has_conflict_markers=entry["kind"] == "markers",
        )
        entry["proposed"] = _trim_store(proposed)
        entry["original"] = _trim_store(original)
        entry["diff"] = make_unified_diff(source, original, proposed)
        entry["summary"] = summary
        entry["strategy"] = strategy
        entry["status"] = "ai_done"
        entry["error"] = ""
        _log(job_id, f"合入建议已生成: {source} ({strategy})")
    except RuntimeError as exc:
        if not is_llm_configured():
            entry["status"] = "failed"
            entry["error"] = str(exc)
            _log(job_id, f"合入失败 {source}: {exc}")
        else:
            try:
                from web_app.llm_service import _resolve_merge_conflict_llm_only
                proposed, summary = _resolve_merge_conflict_llm_only(
                    source_path=source,
                    original_content=original,
                    rej_content=rej,
                    has_conflict_markers=entry["kind"] == "markers",
                )
                entry["proposed"] = _trim_store(proposed)
                entry["original"] = _trim_store(original)
                entry["diff"] = make_unified_diff(source, original, proposed)
                entry["summary"] = summary
                entry["strategy"] = "llm_regions"
                entry["status"] = "ai_done"
                entry["error"] = ""
                _log(job_id, f"混合合入失败，LLM 回退成功: {source}")
            except Exception as llm_exc:
                entry["status"] = "failed"
                entry["error"] = f"{exc}; LLM 回退: {llm_exc}"
                _log(job_id, f"合入失败 {source}: {entry['error']}")
    entry["updated_at"] = datetime.now().isoformat()
    return entry


def _run_ai_resolution(
    job_id: str,
    ssh_creds: Optional[Dict[str, Any]] = None,
    *,
    paths: Optional[List[str]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    job = get_upgrade_job(job_id)
    if not job:
        return {}
    conflict_files = job.get("conflict_files") or []
    if paths:
        path_set = set(paths)
        conflict_files = [cp for cp in conflict_files if cp in path_set]
    if not conflict_files:
        return _get_resolutions(job).get("files") or {}

    cr = _get_resolutions(job)
    cr["ai_status"] = "running"
    cr["ai_message"] = f"正在处理 {len(conflict_files)} 个冲突…"
    files: Dict[str, Any] = dict(cr.get("files") or {})
    cr["files"] = files
    _save_resolutions(job_id, job, cr)

    try:
        with remote_job_context(job_id, ssh_creds):
            job = get_upgrade_job(job_id) or job
            done = 0
            for cp in conflict_files:
                ent = files.get(cp) or {}
                status = ent.get("status", "pending")
                should_run = force or status in ("pending", "failed") or not ent.get("proposed")
                if not should_run:
                    done += 1
                    continue
                try:
                    entry = files.get(cp) or _build_file_resolution(job, cp)
                    files[cp] = _resolve_one_with_ai(job_id, job, entry)
                except Exception as exc:
                    files[cp] = {
                        "conflict_path": cp,
                        "source_path": source_path_from_conflict(cp),
                        "status": "failed",
                        "error": str(exc),
                    }
                    _log(job_id, f"读取冲突文件失败 {cp}: {exc}")
                done += 1
                job = get_upgrade_job(job_id) or job
                cr = _get_resolutions(job)
                cr["ai_status"] = "running"
                cr["ai_message"] = f"AI 处理中 ({done}/{len(conflict_files)})…"
                cr["files"] = files
                _save_resolutions(job_id, job, cr)

            job = get_upgrade_job(job_id) or job
            cr = _get_resolutions(job)
            cr["files"] = files
            processed = [cp for cp in conflict_files if cp in files]
            failed = sum(1 for cp in processed if files[cp].get("status") == "failed")
            ok = len(processed) - failed
            cr["ai_status"] = "failed" if processed and failed == len(processed) else "done"
            cr["ai_message"] = (
                f"AI 处理完成：{ok}/{len(processed)} 成功"
                + (f"，{failed} 个需人工编辑" if failed else "")
            )
            _save_resolutions(job_id, job, cr)
            _log(job_id, cr["ai_message"])
            return files
    except Exception as exc:
        job = get_upgrade_job(job_id) or job
        cr = _get_resolutions(job)
        cr["ai_status"] = "failed"
        cr["ai_message"] = str(exc)
        cr["files"] = files
        _save_resolutions(job_id, job, cr)
        _log(job_id, f"AI 冲突处理失败: {exc}")
        return files


def _conflict_paths_for_job(job: Dict[str, Any], cr: Dict[str, Any]) -> List[str]:
    active = job.get("conflict_files") or []
    history = (job.get("options") or {}).get("conflict_history_files") or []
    stored = list((cr.get("files") or {}).keys())
    seen: set[str] = set()
    out: List[str] = []
    for path in active + history + stored:
        if path and path not in seen:
            seen.add(path)
            out.append(path)
    return out


def _maybe_auto_continue_after_apply(
    job_id: str,
    ssh_creds: Optional[Dict[str, Any]] = None,
) -> None:
    job = get_upgrade_job(job_id)
    if not job or not (job.get("options") or {}).get("auto_resolve_conflicts"):
        return
    cr = _get_resolutions(job)
    files = cr.get("files") or {}
    conflict_paths = _conflict_paths_for_job(job, cr)
    unapplied = [cp for cp in conflict_paths if not (files.get(cp) or {}).get("applied")]
    if unapplied:
        failed = sum(1 for cp in unapplied if (files.get(cp) or {}).get("status") == "failed")
        msg = f"{len(unapplied)} 个文件未写回，需人工处理"
        if failed:
            msg += f"（{failed} 个 AI 失败）"
        cr["ai_message"] = (cr.get("ai_message") or "") + f"；自动继续跳过：{msg}"
        _save_resolutions(job_id, job, cr)
        _log(job_id, f"自动继续跳过：{msg}")
        return

    from web_app.upgrade_service import continue_after_conflicts

    for _ in range(10):
        ok, msg = continue_after_conflicts(job_id, ssh_creds=ssh_creds)
        job = get_upgrade_job(job_id) or job
        cr = _get_resolutions(job)
        if ok:
            cr["ai_message"] = (cr.get("ai_message") or "") + "；已自动继续合入"
            _save_resolutions(job_id, job, cr)
            _log(job_id, f"自动继续合入成功: {msg}")
            return
        if job.get("status") != "conflicts":
            cr["ai_message"] = (cr.get("ai_message") or "") + f"；{msg}"
            _save_resolutions(job_id, job, cr)
            _log(job_id, f"自动继续: {msg}")
            return
        if "再次点击继续" in msg or "仍有后续 commit" in msg:
            continue
        cr["ai_message"] = (cr.get("ai_message") or "") + f"；自动继续失败: {msg}"
        _save_resolutions(job_id, job, cr)
        _log(job_id, f"自动继续合入失败: {msg}")
        return
    job = get_upgrade_job(job_id) or job
    cr = _get_resolutions(job)
    cr["ai_message"] = (cr.get("ai_message") or "") + "；自动继续未完成（git am 多轮）"
    _save_resolutions(job_id, job, cr)
    _log(job_id, "自动继续：git am 多轮后仍未完成，请手动点击继续")


def schedule_ai_conflict_resolution(
    job_id: str,
    ssh_creds: Optional[Dict[str, Any]] = None,
    *,
    paths: Optional[List[str]] = None,
    force: bool = False,
    auto_apply: bool = False,
    auto_continue: bool = False,
) -> None:
    with _lock:
        if job_id in _ai_running:
            return
        _ai_running.add(job_id)

    def _worker() -> None:
        try:
            files = _run_ai_resolution(
                job_id, ssh_creds, paths=paths, force=force,
            )
            if auto_apply and files:
                apply_paths = [
                    cp for cp, ent in files.items()
                    if ent.get("proposed") and not ent.get("applied")
                ]
                if paths:
                    path_set = set(paths)
                    apply_paths = [cp for cp in apply_paths if cp in path_set]
                if apply_paths:
                    job = get_upgrade_job(job_id) or {}
                    _set_ai_phase(
                        job_id, job, "applying",
                        f"正在写回 {len(apply_paths)} 个文件…",
                    )
                    count, _ = apply_confirmed_conflicts(
                        job_id, apply_paths, ssh_creds=ssh_creds,
                    )
                    job = get_upgrade_job(job_id) or {}
                    cr = _get_resolutions(job)
                    cr["ai_status"] = "done"
                    cr["ai_message"] = (
                        (cr.get("ai_message") or "")
                        + f"；已写回 {count} 个文件"
                    )
                    _save_resolutions(job_id, job, cr)
                    _log(job_id, f"批量写回完成：{count} 个文件")
            if auto_continue:
                _maybe_auto_continue_after_apply(job_id, ssh_creds=ssh_creds)
        finally:
            with _lock:
                _ai_running.discard(job_id)

    threading.Thread(target=_worker, daemon=True, name=f"conflict-ai-{job_id}").start()


def get_conflict_resolution_state(job_id: str) -> Dict[str, Any]:
    job = get_upgrade_job(job_id)
    if not job:
        return {"error": "任务不存在"}
    cr = _get_resolutions(job)
    files = cr.get("files") or {}
    items = []
    for path in _conflict_paths_for_job(job, cr):
        ent = files.get(path)
        if not ent:
            ent = {
                "conflict_path": path,
                "source_path": source_path_from_conflict(path),
                "status": "pending",
            }
        items.append(_public_entry(ent, job=job))
    return {
        "job_id": job_id,
        "ai_status": cr.get("ai_status", "idle"),
        "ai_message": cr.get("ai_message", ""),
        "conflict_files": _conflict_paths_for_job(job, cr),
        "auto_resolve_conflicts": bool((job.get("options") or {}).get("auto_resolve_conflicts")),
        "items": items,
        "ssh_connected": is_remote_job(job) and has_pooled_ssh_session(job_id),
    }


def _rej_path_for_ent(ent: Dict[str, Any]) -> str:
    cp = (ent.get("conflict_path") or "").replace("\\", "/")
    if cp.endswith(".rej"):
        return cp
    src = ent.get("source_path") or source_path_from_conflict(cp)
    return f"{src}.rej"


def _fresh_display_texts(job: Dict[str, Any], ent: Dict[str, Any]) -> Tuple[str, str]:
    """Re-read source + .rej from repo when possible (avoid stale/truncated DB copies)."""
    src = ent.get("source_path") or source_path_from_conflict(ent.get("conflict_path", ""))
    rej_path = _rej_path_for_ent(ent)
    original = ent.get("original") or ""
    rej = ent.get("rej_content") or ""
    job_id = job.get("id") or ""

    def _load() -> None:
        nonlocal original, rej
        try:
            fresh = _read_repo_text(job, src)
            if fresh.strip():
                original = fresh
        except Exception:
            pass
        try:
            fresh_rej = _read_repo_text(job, rej_path)
            if fresh_rej.strip():
                rej = fresh_rej
        except Exception:
            pass

    try:
        if is_remote_job(job):
            with remote_job_context(job_id):
                _load()
        else:
            _load()
    except Exception:
        _load()
    return original, rej


def _set_ai_phase(
    job_id: str,
    job: Dict[str, Any],
    status: str,
    message: str = "",
) -> None:
    cr = _get_resolutions(job)
    cr["ai_status"] = status
    if message:
        cr["ai_message"] = message
    _save_resolutions(job_id, job, cr)


def _public_entry(ent: Dict[str, Any], job: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    src = ent.get("source_path") or source_path_from_conflict(ent.get("conflict_path", ""))
    original = ent.get("original") or ""
    proposed = ent.get("proposed") or ""
    rej_content = ent.get("rej_content") or ""
    # 列表/轮询 API 只用 DB 缓存，避免每 3s 远程 cat 全部冲突文件拖死 SSH
    diff = ent.get("diff") or ""
    if proposed and original and not diff:
        diff = make_unified_diff(src, original, proposed)
    kind = ent.get("kind", "")
    cp = ent.get("conflict_path", "")
    if not kind and cp.endswith(".rej"):
        kind = "rej"
    if not kind and rej_content.strip():
        kind = "rej"
    regions = extract_conflict_regions(
        kind=kind,
        original=original,
        rej_content=rej_content,
        proposed=proposed,
    )
    return {
        "conflict_path": ent.get("conflict_path", ""),
        "source_path": src,
        "kind": kind,
        "status": ent.get("status", "pending"),
        "summary": ent.get("summary", ""),
        "strategy": ent.get("strategy", ""),
        "error": ent.get("error", ""),
        "confirmed": bool(ent.get("confirmed")),
        "applied": bool(ent.get("applied")),
        "original": original,
        "proposed": proposed,
        "diff": diff,
        "rej_content": rej_content,
        "conflict_regions": regions,
        "updated_at": ent.get("updated_at", ""),
    }


def update_proposed_content(job_id: str, conflict_path: str, content: str) -> Dict[str, Any]:
    job = get_upgrade_job(job_id)
    if not job:
        raise RuntimeError("任务不存在")
    cr = _get_resolutions(job)
    files = dict(cr.get("files") or {})
    ent = dict(files.get(conflict_path) or {})
    src = ent.get("source_path") or source_path_from_conflict(conflict_path)
    original = ent.get("original") or ""
    if not original:
        with remote_job_context(job_id):
            job = get_upgrade_job(job_id) or job
            original = _read_repo_text(job, src)
    ent["proposed"] = content
    ent["original"] = original
    ent["diff"] = make_unified_diff(src, original, content)
    ent["status"] = "edited"
    ent["confirmed"] = False
    ent["updated_at"] = datetime.now().isoformat()
    files[conflict_path] = ent
    cr["files"] = files
    _save_resolutions(job_id, job, cr)
    return _public_entry(ent, job=job)


def update_rej_content(job_id: str, conflict_path: str, rej_content: str) -> Dict[str, Any]:
    from web_app.conflict_region_utils import merge_rej_into_source

    job = get_upgrade_job(job_id)
    if not job:
        raise RuntimeError("任务不存在")
    cr = _get_resolutions(job)
    files = dict(cr.get("files") or {})
    ent = dict(files.get(conflict_path) or {})
    src = ent.get("source_path") or source_path_from_conflict(conflict_path)
    original = ent.get("original") or ""
    if not original:
        with remote_job_context(job_id):
            job = get_upgrade_job(job_id) or job
            original = _read_repo_text(job, src)
    proposed = merge_rej_into_source(original, rej_content)
    ent["rej_content"] = rej_content
    ent["proposed"] = proposed
    ent["original"] = original
    ent["diff"] = make_unified_diff(src, original, proposed)
    ent["kind"] = ent.get("kind") or "rej"
    ent["status"] = "edited"
    ent["confirmed"] = False
    ent["updated_at"] = datetime.now().isoformat()
    files[conflict_path] = ent
    cr["files"] = files
    _save_resolutions(job_id, job, cr)
    return _public_entry(ent, job=job)


def apply_confirmed_conflicts(
    job_id: str,
    paths: Optional[List[str]] = None,
    *,
    ssh_creds: Optional[Dict[str, Any]] = None,
) -> Tuple[int, List[str]]:
    job = get_upgrade_job(job_id)
    if not job:
        raise RuntimeError("任务不存在")
    cr = _get_resolutions(job)
    files = dict(cr.get("files") or {})
    targets = paths or list(files.keys())
    applied: List[str] = []

    with remote_job_context(job_id, ssh_creds):
        job = get_upgrade_job(job_id) or job
        from web_app.target_repo_config import normalize_linux_path
        from web_app.upgrade_staging import stage_path_for_job

        target_dir = normalize_linux_path(job.get("target_repo_dir") or "").rstrip("/")
        build_wd = (job.get("build_workdir") or "").strip()
        for cp in targets:
            ent = files.get(cp)
            if not ent or not ent.get("proposed"):
                continue
            src = ent.get("source_path") or source_path_from_conflict(cp)
            try:
                from web_app.llm_service import sanitize_merged_conflict_content
                original_ref = ent.get("original") or ""
                try:
                    original_live = _read_repo_text(job, src)
                    if original_live:
                        original_ref = original_live
                except FileNotFoundError:
                    pass
                proposed_text = sanitize_merged_conflict_content(
                    ent["proposed"],
                    original_content=original_ref,
                    source_path=src,
                )
            except (ValueError, RuntimeError) as exc:
                raise RuntimeError(f"{src}: {exc}") from exc
            rej_check = ent.get("rej_content") or ""
            if rej_check.strip():
                from web_app.conflict_region_utils import validate_rej_merge_complete
                try:
                    validate_rej_merge_complete(proposed_text, rej_check)
                except RuntimeError as exc:
                    raise RuntimeError(
                        f"{src}: {exc}。请在页面重新「AI 合入」后再应用。"
                    ) from exc
            _write_repo_text(job, src, proposed_text)
            if cp.endswith(".rej") or ent.get("kind") == "rej":
                _remove_remote_file(job, cp)
            ent["applied"] = True
            ent["confirmed"] = True
            ent["status"] = "applied"
            ent["updated_at"] = datetime.now().isoformat()
            files[cp] = ent
            applied.append(src)
            abs_path = f"{target_dir}/{src.lstrip('/')}" if target_dir else src
            try:
                stage_path_for_job(
                    job_id,
                    job,
                    abs_path,
                    build_workdir=build_wd,
                )
            except Exception as exc:
                from web_app.upgrade_git import run_git
                from web_app.upgrade_service import _job_target_path

                run_git(_job_target_path(job), ["add", "--", src], check=False)
                _log(job_id, f"git add 回退 ({src}): {exc}")
            _log(job_id, f"已写回并 git add: {src}")

    cr["files"] = files
    _save_resolutions(job_id, job, cr)
    return len(applied), applied
