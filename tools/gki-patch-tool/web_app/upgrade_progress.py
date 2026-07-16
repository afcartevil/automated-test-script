"""Per-job upgrade progress log callbacks (avoid circular imports)."""
from __future__ import annotations

import threading
from typing import Callable, Dict, Optional

_lock = threading.Lock()
_callbacks: Dict[str, Callable[[str, str], None]] = {}


def register_job_progress(job_id: str, callback: Callable[[str, str], None]) -> None:
    with _lock:
        _callbacks[job_id] = callback


def unregister_job_progress(job_id: str) -> None:
    with _lock:
        _callbacks.pop(job_id, None)


def append_job_log(job_id: str, msg: str, phase: str = "apply") -> None:
    if not job_id or not msg:
        return
    with _lock:
        cb = _callbacks.get(job_id)
    if cb:
        cb(msg, phase)
        return
    try:
        from web_app.upgrade_service import _append_progress_log

        _append_progress_log(job_id, msg, phase)
    except Exception:
        pass
