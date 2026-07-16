"""Unified repo file I/O: local mount (hybrid) vs SSH vs pure local."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from web_app.job_path_mapping import (
    is_hybrid_job,
    remote_abs_to_local,
    repo_rel_to_local,
    resolve_local_build_mount,
    use_local_file_io,
)


def _current_job() -> Optional[Dict[str, Any]]:
    try:
        from web_app.upgrade_remote_git import _tls
        from web_app.database import get_upgrade_job

        jid = getattr(_tls, "job_id", None)
        if jid:
            return get_upgrade_job(jid)
    except Exception:
        pass
    return None


def should_use_ssh_file_io(job: Optional[Dict[str, Any]] = None) -> bool:
    from web_app.upgrade_remote_git import is_remote_active

    job = job or _current_job()
    if not is_remote_active():
        return False
    return not use_local_file_io(job)


def read_repo_rel(job: Dict[str, Any], rel_path: str) -> str:
    rel = rel_path.replace("\\", "/").lstrip("/")
    if use_local_file_io(job):
        fp = repo_rel_to_local(job, rel)
        if not fp.is_file():
            raise FileNotFoundError(rel_path)
        return fp.read_text(encoding="utf-8", errors="replace")
    if should_use_ssh_file_io(job):
        from web_app.upgrade_remote_git import remote_read_text
        return remote_read_text(rel)
    root = Path(job.get("target_repo_dir") or "")
    fp = root / rel
    if not fp.is_file():
        raise FileNotFoundError(rel_path)
    return fp.read_text(encoding="utf-8", errors="replace")


def write_repo_rel(job: Dict[str, Any], rel_path: str, content: str) -> None:
    rel = rel_path.replace("\\", "/").lstrip("/")
    if use_local_file_io(job):
        fp = repo_rel_to_local(job, rel)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8", newline="\n")
        return
    if should_use_ssh_file_io(job):
        from web_app.upgrade_remote_git import remote_write_text
        remote_write_text(rel, content)
        return
    root = Path(job.get("target_repo_dir") or "")
    fp = root / rel
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8", newline="\n")


def read_absolute(job: Dict[str, Any], abs_path: str) -> str:
    path = abs_path.replace("\\", "/")
    if use_local_file_io(job):
        if path.startswith("/"):
            local = remote_abs_to_local(job, path)
            if local is not None:
                if not local.is_file():
                    raise FileNotFoundError(abs_path)
                return local.read_text(encoding="utf-8", errors="replace")
            from web_app.upgrade_remote_git import remote_read_absolute
            return remote_read_absolute(path)
        return read_repo_rel(job, path.lstrip("/"))
    if should_use_ssh_file_io(job):
        from web_app.upgrade_remote_git import remote_read_absolute, remote_read_text
        if path.startswith("/"):
            return remote_read_absolute(path)
        return remote_read_text(path.lstrip("/"))
    fp = Path(path)
    if not fp.is_file():
        raise FileNotFoundError(abs_path)
    return fp.read_text(encoding="utf-8", errors="replace")


def write_absolute(job: Dict[str, Any], abs_path: str, content: str) -> None:
    path = abs_path.replace("\\", "/")
    if use_local_file_io(job):
        if path.startswith("/"):
            local = remote_abs_to_local(job, path)
            if local is None:
                raise FileNotFoundError(f"无法映射远程路径到本地: {abs_path}")
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_text(content, encoding="utf-8", newline="\n")
            return
        write_repo_rel(job, path, content)
        return
    if should_use_ssh_file_io(job):
        from web_app.upgrade_remote_git import remote_write_absolute, remote_write_text
        if path.startswith("/"):
            remote_write_absolute(path, content)
        else:
            remote_write_text(path.lstrip("/"), content)
        return
    fp = Path(path)
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8", newline="\n")


def file_exists(job: Dict[str, Any], abs_path: str) -> bool:
    path = abs_path.replace("\\", "/")
    if use_local_file_io(job):
        if path.startswith("/"):
            local = remote_abs_to_local(job, path)
            if local is not None:
                return local.is_file()
            from web_app.upgrade_remote_git import remote_file_exists
            return remote_file_exists(path)
        try:
            return repo_rel_to_local(job, path.lstrip("/")).is_file()
        except FileNotFoundError:
            return False
    if should_use_ssh_file_io(job):
        from web_app.upgrade_remote_git import remote_file_exists
        return remote_file_exists(path if path.startswith("/") else path)
    return Path(path).is_file()


def remove_repo_rel(job: Dict[str, Any], rel_path: str) -> None:
    rel = rel_path.replace("\\", "/").lstrip("/")
    if use_local_file_io(job):
        fp = repo_rel_to_local(job, rel)
        fp.unlink(missing_ok=True)
        return
    if should_use_ssh_file_io(job):
        import shlex
        from web_app.upgrade_remote_git import remote_run_shell
        remote_run_shell(f"rm -f {shlex.quote(rel)}")
        return
    (Path(job.get("target_repo_dir") or "") / rel).unlink(missing_ok=True)


def copy_local_file_to_remote_path(
    job: Dict[str, Any],
    local_src: str | Path,
    remote_dest: str,
) -> Path:
    """Hybrid: copy patch/file to mapped local path instead of SSH upload."""
    if not use_local_file_io(job):
        raise RuntimeError("copy_local_file_to_remote_path 仅用于混合模式")
    local_dest = remote_abs_to_local(job, remote_dest)
    if local_dest is None:
        raise FileNotFoundError(f"无法映射远程路径: {remote_dest}")
    local_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(local_src), local_dest)
    return local_dest
