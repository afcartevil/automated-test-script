"""Persist full upgrade execution logs to local files (not truncated)."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from web_app.app_paths import outputs_dir

_LOG_DIR = outputs_dir("upgrade_logs")
_LOG_TIME_FMT = "%Y%m%d_%H%M%S"
_LINE_RE = re.compile(
    r"^\[(?P<ts>[^\]]+)\](?:\[(?P<phase>[^\]]*)\])? (?P<msg>.*)$"
)
_job_log_paths: Dict[str, Path] = {}

UI_LOG_LIMIT = 200

# Build log API: avoid loading multi‑MB files into browser / blocking the server.
BUILD_LOG_TAIL_BYTES = 256 * 1024
BUILD_LOG_CHUNK_BYTES = 512 * 1024


def read_text_file_tail_bytes(path: Path, max_bytes: int) -> str:
    """Read up to max_bytes from the end of a (possibly huge) text file."""
    if max_bytes <= 0:
        return ""
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size <= 0:
                return ""
            start = max(0, size - max_bytes)
            f.seek(start)
            raw = f.read()
    except OSError:
        return ""
    text = raw.decode("utf-8", errors="replace")
    if start > 0:
        nl = text.find("\n")
        if nl >= 0:
            text = text[nl + 1 :]
    return text


def read_text_file_from_offset(path: Path, offset: int, max_bytes: int) -> tuple[str, int]:
    """Read a chunk starting at byte offset; returns (text, new_offset)."""
    if max_bytes <= 0:
        return "", offset
    try:
        size = path.stat().st_size
    except OSError:
        return "", offset
    if offset >= size:
        return "", size
    try:
        with path.open("rb") as f:
            f.seek(offset)
            raw = f.read(max_bytes)
    except OSError:
        return "", offset
    new_offset = offset + len(raw)
    text = raw.decode("utf-8", errors="replace")
    if offset > 0 and text:
        nl = text.find("\n")
        if nl >= 0:
            text = text[nl + 1 :]
        else:
            text = ""
    return text, new_offset


def read_text_file_last_line(path: Path, *, max_scan_bytes: int = 8192) -> str:
    """Read the last non-empty line without loading the whole file."""
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size <= 0:
                return ""
            scan = min(size, max_scan_bytes)
            f.seek(size - scan)
            chunk = f.read(scan).decode("utf-8", errors="replace")
    except OSError:
        return ""
    lines = [ln for ln in chunk.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def execution_log_dir() -> Path:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    return _LOG_DIR


def new_log_stem(when: Optional[datetime] = None) -> str:
    """Same timestamp stem as analysis perf logs (e.g. 20260625_110625)."""
    return (when or datetime.now()).strftime(_LOG_TIME_FMT)


def execution_log_path_for_stem(stem: str) -> Path:
    return execution_log_dir() / f"{stem}.log"


def build_log_path_for_stem(stem: str) -> Path:
    return execution_log_dir() / f"{stem}_build.log"


def legacy_execution_log_path(job_id: str) -> Path:
    return execution_log_dir() / f"{job_id}_execution.log"


def legacy_build_log_path(job_id: str) -> Path:
    return execution_log_dir() / f"{job_id}_build.log"


def register_execution_log_path(job_id: str, path: Path) -> None:
    if job_id:
        _job_log_paths[job_id] = path


def resolve_log_stem(job: Optional[Dict[str, Any]] = None) -> str:
    opts = (job or {}).get("options") or {}
    stem = str(opts.get("log_stem") or "").strip()
    if stem:
        return stem
    alt = str(opts.get("execution_log_file") or "").strip()
    if alt:
        name = Path(alt).name
        if name.endswith(".log"):
            return name[:-4]
        if name.endswith("_execution.log"):
            return name[: -len("_execution.log")]
    return ""


def resolve_execution_log_path(
    job_id: str,
    job: Optional[Dict[str, Any]] = None,
) -> Path:
    cached = _job_log_paths.get(job_id)
    if cached is not None:
        return cached
    if job is None:
        from web_app.database import get_upgrade_job

        job = get_upgrade_job(job_id) or {}
    opts = job.get("options") or {}
    alt = str(opts.get("execution_log_file") or "").strip()
    if alt:
        path = Path(alt)
        _job_log_paths[job_id] = path
        return path
    stem = resolve_log_stem(job)
    if stem:
        path = execution_log_path_for_stem(stem)
        _job_log_paths[job_id] = path
        return path
    legacy = legacy_execution_log_path(job_id)
    _job_log_paths[job_id] = legacy
    return legacy


def resolve_build_log_path(
    job_id: str,
    job: Optional[Dict[str, Any]] = None,
) -> Path:
    if job is None:
        from web_app.database import get_upgrade_job

        job = get_upgrade_job(job_id) or {}
    stored = str(job.get("build_log_file") or "").strip()
    if stored:
        return Path(stored)
    stem = resolve_log_stem(job)
    if stem:
        return build_log_path_for_stem(stem)
    return legacy_build_log_path(job_id)


def execution_log_path(job_id: str) -> Path:
    """Resolve on-disk execution log path (time-based or legacy)."""
    return resolve_execution_log_path(job_id)


def init_execution_log(
    job_id: str,
    *,
    stem: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Path:
    log_stem = stem or new_log_stem()
    path = execution_log_path_for_stem(log_stem)
    register_execution_log_path(job_id, path)
    with path.open("w", encoding="utf-8") as f:
        f.write(f"# GKI upgrade execution log: {job_id}\n")
        f.write(f"# log_stem: {log_stem}\n")
        f.write(f"# created_at: {datetime.now().isoformat()}\n")
        for key, val in (meta or {}).items():
            if val is None or val == "":
                continue
            f.write(f"# {key}: {val}\n")
        f.write("\n")
    return path


def append_execution_log_line(
    job_id: str,
    msg: str,
    *,
    phase: str = "",
    time_str: str = "",
) -> None:
    if not job_id or not msg:
        return
    ts = time_str or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path = resolve_execution_log_path(job_id)
    phase_part = f"[{phase}]" if phase else ""
    line = f"[{ts}]{phase_part} {msg}\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


def read_execution_log_text(job_id: str) -> str:
    path = resolve_execution_log_path(job_id)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def read_execution_log_tail(job_id: str, limit: int = UI_LOG_LIMIT) -> List[Dict[str, str]]:
    """Return last N parsed log entries for UI display."""
    path = resolve_execution_log_path(job_id)
    if not path.is_file() or limit <= 0:
        return []
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            chunk = min(size, 512 * 1024)
            f.seek(max(0, size - chunk))
            text = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = text.splitlines()
    entries: List[Dict[str, str]] = []
    for raw in lines:
        if not raw or raw.startswith("#"):
            continue
        m = _LINE_RE.match(raw)
        if not m:
            entries.append({"time": "", "phase": "", "msg": raw})
            continue
        ts = m.group("ts") or ""
        display_time = ts[-8:] if len(ts) >= 8 else ts
        entries.append({
            "time": display_time,
            "phase": m.group("phase") or "",
            "msg": m.group("msg") or "",
        })
    return entries[-limit:]


def progress_log_to_text(progress_log: List[Dict[str, str]]) -> str:
    lines: List[str] = []
    for entry in progress_log or []:
        ts = entry.get("time") or ""
        phase = entry.get("phase") or ""
        msg = entry.get("msg") or ""
        phase_part = f"[{phase}]" if phase else ""
        lines.append(f"[{ts}]{phase_part} {msg}")
    return "\n".join(lines)


def ensure_execution_log_file(job_id: str, *, meta: Optional[Dict[str, Any]] = None) -> Path:
    """Create log file if missing; return path."""
    from web_app.database import get_upgrade_job

    job = get_upgrade_job(job_id) or {}
    path = resolve_execution_log_path(job_id, job)
    if not path.is_file():
        stem = resolve_log_stem(job) or new_log_stem()
        path = init_execution_log(job_id, stem=stem, meta=meta)
    return path


def get_execution_log_for_job(job_id: str, job: Optional[Dict[str, Any]] = None) -> tuple[str, Path, str]:
    """Return (text, path, source) where source is file|alt|db|empty."""
    from web_app.database import get_upgrade_job

    job = job or get_upgrade_job(job_id) or {}
    opts = job.get("options") or {}

    path = resolve_execution_log_path(job_id, job)
    if path.is_file() and path.stat().st_size > 0:
        return path.read_text(encoding="utf-8", errors="replace"), path, "file"

    alt = (opts.get("execution_log_file") or "").strip()
    if alt:
        alt_path = Path(alt)
        if alt_path.is_file() and alt_path.stat().st_size > 0:
            return alt_path.read_text(encoding="utf-8", errors="replace"), alt_path, "alt"

    progress_log = opts.get("progress_log") or []
    if progress_log:
        text = progress_log_to_text(progress_log)
        return text, path, "db"

    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace"), path, "file"

    return "", path, "empty"
