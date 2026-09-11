"""Map remote Linux paths to locally mounted workspace paths (hybrid SSH mode)."""
from __future__ import annotations

import os
import posixpath
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from web_app.target_repo_config import normalize_linux_path, resolve_build_workdir

# Compile logs may use /work/code/{user}/... while job config uses /work/{user}/code/...
_WORK_CODE_RE = re.compile(r"^(/work)/code/([^/]+)(/.*)?$")
_WORK_USER_CODE_RE = re.compile(r"^(/work)/([^/]+)/code(/.*)?$")


def is_hybrid_job(job: Optional[Dict[str, Any]]) -> bool:
    if not job:
        return False
    opts = job.get("options") or {}
    if not opts.get("remote"):
        return False
    mount = (job.get("local_repo_mount") or "").strip()
    return bool(mount) or bool(opts.get("hybrid"))


def use_local_file_io(job: Optional[Dict[str, Any]]) -> bool:
    """Remote git/build via SSH, but read/write files on local mount."""
    if not is_hybrid_job(job):
        return False
    return bool((job.get("local_repo_mount") or "").strip())


def _is_windows_local_path(path_str: str) -> bool:
    s = (path_str or "").strip()
    return s.startswith("\\\\") or (len(s) >= 2 and s[1] == ":")


def _norm_local(path_str: str) -> Path:
    p = Path(path_str).expanduser()
    if _is_windows_local_path(str(p)):
        return p
    return p.resolve()


def persist_local_mount_path(path_str: str) -> str:
    """Persist the path the user typed.

    ``Path.resolve()`` on Windows turns mapped drives (``Z:\\...``) into UNC
    (``\\\\server\\share\\...``). Copy-last and the form should keep the drive letter.
    """
    raw = (path_str or "").strip()
    if not raw:
        return ""
    return str(_norm_local(raw))


def job_local_repo_root(job: Dict[str, Any]) -> Optional[Path]:
    raw = (job.get("local_repo_mount") or "").strip()
    if not raw:
        return None
    p = _norm_local(raw)
    return p if p.is_dir() else None


def swap_work_path_layout(path: str) -> str:
    """Swap /work/code/{user}/… ↔ /work/{user}/code/… (same NFS tree, different bind paths)."""
    p = normalize_linux_path(path)
    m = _WORK_CODE_RE.match(p)
    if m:
        return normalize_linux_path(f"{m.group(1)}/{m.group(2)}/code{m.group(3) or ''}")
    m = _WORK_USER_CODE_RE.match(p)
    if m:
        return normalize_linux_path(f"{m.group(1)}/code/{m.group(2)}{m.group(3) or ''}")
    return p


def remote_path_variants(path: str) -> List[str]:
    """Normalized remote path candidates (collapse .., path layout aliases)."""
    raw = normalize_linux_path((path or "").replace("\\", "/"))
    out: List[str] = []
    seen: set[str] = set()

    def add(p: str) -> None:
        if not p or p in seen:
            return
        seen.add(p)
        out.append(p)

    add(raw)
    if raw.startswith("/"):
        add(posixpath.normpath(raw))
    add(swap_work_path_layout(raw))
    if raw.startswith("/"):
        add(swap_work_path_layout(posixpath.normpath(raw)))
    return out


def _remote_prefix_aliases(prefix: str) -> List[str]:
    base = normalize_linux_path(prefix).rstrip("/")
    out: List[str] = []
    seen: set[str] = set()
    for p in (base, swap_work_path_layout(base)):
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def resolve_local_project_mount(job: Dict[str, Any]) -> Optional[Path]:
    """Parent of vnd/build mount — vendor/ may live here instead of under vnd/."""
    local_build = resolve_local_build_mount(job)
    if local_build is None:
        local_repo = job_local_repo_root(job)
        if local_repo is not None and local_repo.parent.is_dir():
            return local_repo.parent
        return None
    parent = local_build.parent
    return parent if parent.is_dir() else None


def resolve_local_build_mount(job: Dict[str, Any]) -> Optional[Path]:
    explicit = (job.get("local_build_mount") or "").strip()
    if explicit:
        p = _norm_local(explicit)
        return p if p.is_dir() else None
    local_repo = job_local_repo_root(job)
    if local_repo is None:
        return None
    remote_repo = normalize_linux_path(job.get("target_repo_dir") or "")
    remote_build = normalize_linux_path(job.get("build_workdir") or "")
    if not remote_build or remote_build == remote_repo:
        return local_repo.parent if local_repo.parent.is_dir() else None
    rb = remote_build.rstrip("/")
    rr = remote_repo.rstrip("/")
    if rr == rb:
        return local_repo
    if rr.startswith(rb + "/"):
        extra = rr[len(rb):].lstrip("/")
        p = local_repo
        for _ in (extra.split("/") if extra else []):
            p = p.parent
        return p if p.is_dir() else None
    return None


def path_mappings_for_job(job: Dict[str, Any]) -> List[Tuple[str, Path]]:
    """Remote prefix -> local root, longest remote prefix first."""
    pairs: List[Tuple[str, Path]] = []
    seen: set[tuple[str, str]] = set()

    def add(remote_prefix: str, local_root: Path) -> None:
        if not remote_prefix or local_root is None:
            return
        local_key = str(local_root).lower()
        for rp in _remote_prefix_aliases(remote_prefix):
            key = (rp, local_key)
            if key in seen:
                continue
            seen.add(key)
            pairs.append((rp, local_root))

    local_repo = job_local_repo_root(job)
    remote_repo = normalize_linux_path(job.get("target_repo_dir") or "")
    if local_repo and remote_repo:
        add(remote_repo, local_repo)

    local_build = resolve_local_build_mount(job)
    remote_build = normalize_linux_path(job.get("build_workdir") or "")
    if local_build and remote_build:
        add(remote_build, local_build)

    local_project = resolve_local_project_mount(job)
    if local_project and remote_build:
        rb = remote_build.rstrip("/")
        parent = rb.rsplit("/", 1)[0] if "/" in rb else ""
        if parent:
            add(parent, local_project)

    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    return pairs


def remote_abs_to_local(job: Dict[str, Any], remote_abs: str) -> Optional[Path]:
    if not (remote_abs or "").strip():
        return None
    mappings = path_mappings_for_job(job)
    for remote in remote_path_variants(remote_abs):
        if not remote.startswith("/"):
            continue
        for prefix, local_root in mappings:
            if remote == prefix:
                return local_root
            if remote.startswith(prefix + "/"):
                suffix = remote[len(prefix):].lstrip("/")
                return local_root / suffix.replace("/", os.sep)
    return None


def local_abs_to_remote(job: Dict[str, Any], local_abs: str) -> Optional[str]:
    """Map a locally mounted path back to the configured remote Linux path."""
    if not (local_abs or "").strip():
        return None
    try:
        local = Path(local_abs).expanduser().resolve()
    except OSError:
        return None
    for remote_prefix, local_root in path_mappings_for_job(job):
        try:
            root = local_root.resolve()
        except OSError:
            continue
        try:
            if local == root:
                return remote_prefix.rstrip("/")
            rel = local.relative_to(root).as_posix()
            return f"{remote_prefix.rstrip('/')}/{rel}"
        except ValueError:
            continue
    return None


def repo_rel_to_local(job: Dict[str, Any], rel_path: str) -> Path:
    root = job_local_repo_root(job)
    if root is None:
        raise FileNotFoundError("未配置 local_repo_mount")
    rel = rel_path.replace("\\", "/").lstrip("/")
    return root / rel.replace("/", os.sep)


def validate_hybrid_mounts(
    *,
    remote_target: str,
    local_repo_mount: str,
    remote_build_workdir: str = "",
    local_build_mount: str = "",
) -> Optional[str]:
    if not local_repo_mount.strip():
        return "混合模式请填写服务器映射到本地的路径（local_repo_mount）"
    local_repo = Path(local_repo_mount).expanduser()
    if not local_repo.is_dir():
        return f"本地映射路径不存在或不是目录: {local_repo_mount}"
    if not remote_target.startswith("/"):
        return "远程合入目标仍须为 Linux 绝对路径"
    if local_build_mount.strip():
        lb = Path(local_build_mount).expanduser()
        if not lb.is_dir():
            return f"本地编译目录映射不存在: {local_build_mount}"
    elif remote_build_workdir.strip():
        fake_job = {
            "target_repo_dir": normalize_linux_path(remote_target),
            "build_workdir": normalize_linux_path(remote_build_workdir),
            "local_repo_mount": str(local_repo.resolve()),
        }
        if resolve_local_build_mount(fake_job) is None:
            return (
                "无法从合入目标映射推导编译目录映射，请填写「编译目录本地映射」"
            )
    if not (local_repo / ".git").exists() and not local_repo.is_dir():
        return f"映射路径下未找到 git 仓库: {local_repo}"
    return None


def resolve_local_target_repo_path(path_str: str) -> Optional[Path]:
    """Validate local mount path for hybrid jobs."""
    raw = (path_str or "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    if not p.is_absolute():
        return None
    p = p.resolve()
    return p if p.is_dir() else None
