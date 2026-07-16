"""SSH session lifecycle for remote GKI upgrade jobs (credentials not persisted)."""
from __future__ import annotations

import threading
from typing import Any, Dict, FrozenSet, Optional

from web_app.database import get_upgrade_job
from web_app.ssh_bastion import BastionSSHSession, load_bastion_config
from web_app.ssh_credentials_config import get_saved_ssh_credentials
from web_app.target_repo_config import normalize_linux_path
from web_app.upgrade_remote_git import activate_remote_session, deactivate_remote_session, is_remote_active

_lock = threading.Lock()
_pending_creds: Dict[str, Dict[str, Any]] = {}
_active_sessions: Dict[str, BastionSSHSession] = {}
_cqris_partial: Dict[str, BastionSSHSession] = {}

# Release SSH only when the upgrade job reaches a terminal state or is deleted.
SSH_TERMINAL_STATUSES: FrozenSet[str] = frozenset({
    "completed",
    "failed",
    "cancelled",
    "aborted",
    "build_failed",
})


def is_ssh_terminal_status(status: str) -> bool:
    return status in SSH_TERMINAL_STATUSES


def stash_ssh_credentials(job_id: str, creds: Dict[str, Any]) -> None:
    with _lock:
        prev = dict(_pending_creds.get(job_id) or {})
        prev.update({k: v for k, v in creds.items() if v is not None})
        if "otp" in creds and not str(creds.get("otp") or "").strip():
            prev.pop("otp", None)
        _pending_creds[job_id] = prev


def get_stashed_ssh_credentials(job_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        raw = _pending_creds.get(job_id)
        return dict(raw) if raw else None


def clear_ssh_otp(job_id: str) -> None:
    with _lock:
        if job_id in _pending_creds:
            _pending_creds[job_id].pop("otp", None)


def _require_base_credentials(job_id: str) -> Dict[str, Any]:
    base = get_stashed_ssh_credentials(job_id)
    if not base or not str(base.get("bastion_user") or "").strip():
        saved = get_saved_ssh_credentials()
        if saved:
            stash_ssh_credentials(job_id, saved)
            base = get_stashed_ssh_credentials(job_id)
    if not base:
        raise RuntimeError(
            "SSH 账号信息已失效，请重新创建任务或在「系统设置 → 远程 SSH」中配置"
        )
    for key, label in (
        ("bastion_user", "cqris 用户名"),
        ("bastion_password", "cqris 密码"),
        ("target_user", "目标机用户名"),
        ("target_password", "目标机密码"),
    ):
        if not str(base.get(key) or "").strip():
            raise RuntimeError(f"缺少 {label}")
    return base


def connect_cqris_bastion(job_id: str) -> None:
    """Phase 1: ssh -p 22 user@cqris with password; stop at OTP prompt."""
    base = _require_base_credentials(job_id)
    cfg = load_bastion_config()
    session = BastionSSHSession(cfg)
    session.connect_cqris_phase1(
        str(base["bastion_user"]).strip(),
        str(base["bastion_password"]),
    )
    with _lock:
        old = _cqris_partial.pop(job_id, None)
        if old:
            try:
                old.close()
            except Exception:
                pass
        _cqris_partial[job_id] = session


def has_cqris_partial_session(job_id: str) -> bool:
    with _lock:
        return job_id in _cqris_partial


def complete_ssh_to_target(job_id: str, remote_repo: str, otp: str) -> None:
    """Phase 2: OTP → target IP → login; activate remote git session."""
    stashed = get_stashed_ssh_credentials(job_id) or {}
    otp = (otp or stashed.get("otp") or "").strip()
    if len(otp) < 4:
        raise RuntimeError("请输入 6 位动态验证码 (OTP)")

    base = _require_base_credentials(job_id)
    cfg = load_bastion_config()
    with _lock:
        session = _cqris_partial.pop(job_id, None)
    if not session:
        raise RuntimeError("请先点击「连接 cqris」，再输入 OTP")

    target_ip = str(base.get("target_ip") or cfg.target_ip).strip()
    try:
        session.complete_to_target(
            otp,
            target_ip,
            str(base["target_user"]).strip(),
            str(base["target_password"]),
        )
    except Exception:
        with _lock:
            _cqris_partial[job_id] = session
        raise

    clear_ssh_otp(job_id)
    job = get_upgrade_job(job_id) or {}
    activate_remote_session(
        session, remote_repo, job_id,
        remote_temp_dir=str(job.get("remote_temp_dir") or ""),
    )
    with _lock:
        old = _active_sessions.pop(job_id, None)
        if old and old is not session:
            try:
                old.close()
            except Exception:
                pass
        _active_sessions[job_id] = session


def resolve_ssh_credentials(
    job_id: str,
    creds: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base = _require_base_credentials(job_id)
    extra = dict(creds or {})
    merged = {**base, **extra}
    otp = str(merged.get("otp") or "").strip()
    if len(otp) < 4:
        raise RuntimeError("请先输入 6 位动态验证码 (OTP)，再点击连接")
    merged["otp"] = otp
    return merged


def pop_ssh_credentials(job_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        return _pending_creds.pop(job_id, None)


def _session_alive(session: Optional[BastionSSHSession]) -> bool:
    return bool(session and getattr(session, "_shell", None))


def attach_job_ssh(job_id: str, remote_repo: str) -> bool:
    """Bind an existing job session to the current thread (cross-thread reuse)."""
    with _lock:
        session = _active_sessions.get(job_id)
    if not _session_alive(session):
        return False
    job = get_upgrade_job(job_id) or {}
    temp_dir = str(job.get("remote_temp_dir") or "")
    activate_remote_session(
        session, remote_repo, job_id, remote_temp_dir=temp_dir,
    )
    return True


def has_pooled_ssh_session(job_id: str) -> bool:
    with _lock:
        return _session_alive(_active_sessions.get(job_id))


def ensure_job_ssh(
    job_id: str,
    remote_repo: str,
    creds: Optional[Dict[str, Any]] = None,
) -> None:
    """Ensure SSH is ready on the current thread; reuse pooled session when possible."""
    remote_repo = normalize_linux_path(remote_repo)
    if attach_job_ssh(job_id, remote_repo):
        return
    if is_remote_active():
        return
    if has_cqris_partial_session(job_id):
        stashed = get_stashed_ssh_credentials(job_id) or {}
        merged = {**stashed, **(creds or {})}
        otp = str(merged.get("otp") or "").strip()
        complete_ssh_to_target(job_id, remote_repo, otp)
        return

    cfg = load_bastion_config()
    raw = resolve_ssh_credentials(job_id, creds)
    from web_app.ssh_bastion import BastionSSHCredentials

    cred_obj = BastionSSHCredentials(
        bastion_user=str(raw.get("bastion_user") or "").strip(),
        bastion_password=str(raw.get("bastion_password") or ""),
        otp=str(raw.get("otp") or "").strip(),
        target_ip=str(raw.get("target_ip") or cfg.target_ip).strip(),
        target_user=str(raw.get("target_user") or "").strip(),
        target_password=str(raw.get("target_password") or ""),
    )
    session = BastionSSHSession(cfg)
    try:
        session.connect(cred_obj)
    finally:
        clear_ssh_otp(job_id)
    job = get_upgrade_job(job_id) or {}
    temp_dir = str(job.get("remote_temp_dir") or "")
    activate_remote_session(session, remote_repo, job_id, remote_temp_dir=temp_dir)
    with _lock:
        old = _active_sessions.pop(job_id, None)
        if old and old is not session:
            try:
                old.close()
            except Exception:
                pass
        _active_sessions[job_id] = session


def connect_job_ssh(job_id: str, remote_repo: str, creds: Optional[Dict[str, Any]] = None) -> None:
    ensure_job_ssh(job_id, remote_repo, creds)


def disconnect_active_ssh(job_id: str) -> None:
    """Close fully connected remote session only (keep cqris partial for OTP retry)."""
    deactivate_remote_session()
    with _lock:
        session = _active_sessions.pop(job_id, None)
    if session:
        try:
            session.close()
        except Exception:
            pass


def disconnect_job_ssh(job_id: str) -> None:
    disconnect_active_ssh(job_id)
    with _lock:
        partial = _cqris_partial.pop(job_id, None)
    if partial:
        try:
            partial.close()
        except Exception:
            pass


def release_job_ssh(job_id: str) -> None:
    """Close SSH and drop stashed credentials (task ended / deleted)."""
    disconnect_job_ssh(job_id)
    pop_ssh_credentials(job_id)


def is_remote_job(job: Dict[str, Any]) -> bool:
    return bool((job.get("options") or {}).get("remote"))


def remote_job_context(job_id: str, creds: Optional[Dict[str, Any]] = None):
    from web_app.database import get_upgrade_job

    class _Ctx:
        def __init__(self):
            self._remote = False

        def __enter__(self):
            job = get_upgrade_job(job_id)
            self._remote = bool(job and is_remote_job(job))
            if not self._remote:
                return True
            ensure_job_ssh(job_id, job["target_repo_dir"], creds)
            return True

        def __exit__(self, exc_type, exc, tb):
            # Keep pooled SSH alive until task ends; only detach thread-local handle.
            if self._remote:
                deactivate_remote_session()
            return False

    return _Ctx()
