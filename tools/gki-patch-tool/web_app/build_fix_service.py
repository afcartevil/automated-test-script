"""AI-assisted build error resolution for GKI upgrade jobs."""
from __future__ import annotations

import os
import posixpath
import re
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from web_app.build_fix_diagnostics import (
    chains_matching_file,
    collision_call_site_lines,
    is_kernel_readonly_path,
    multi_anchor_snippet,
    parse_build_log_diagnostics,
    try_rename_kernel_macro_collision,
)
from web_app.conflict_policies import read_gki_file_at_tag
from web_app.conflict_resolution_service import make_unified_diff
from web_app.database import get_upgrade_job, update_upgrade_job
from web_app.diff_processor import (
    ApplyResult,
    apply_unified_diff as _apply_unified_diff,
    detect_comment_structure_damage,
    looks_like_unified_diff as _looks_like_unified_diff,
    normalize_llm_diff,
    parse_diff_hunks as _parse_diff_hunks,
    process_llm_fix_content,
    sanitize_empty_delete_lines as _sanitize_unified_diff,
    try_apply_to_sibling_files,
)
from web_app.llm_service import (
    BUILD_FIX_LLM_TIMEOUT,
    is_llm_configured,
    resolve_build_errors_via_llm,
    _is_llm_timeout_message,
)
from web_app.job_path_mapping import remote_path_variants, remote_abs_to_local
from web_app.target_repo_config import normalize_linux_path, resolve_build_workdir
from web_app.upgrade_progress import append_job_log

_MAX_STORE_CHARS = 120_000
_MAX_LOG_TAIL = 80_000
_MAX_ERRORS = 20
BUILD_FIX_MAX_ATTEMPTS_DEFAULT = 20
BUILD_FIX_MAX_ATTEMPTS_CAP = 100


def normalize_build_fix_max_attempts(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = BUILD_FIX_MAX_ATTEMPTS_DEFAULT
    return max(1, min(n, BUILD_FIX_MAX_ATTEMPTS_CAP))


def persisted_build_fix_round_count(job: Dict[str, Any]) -> int:
    """Max ``attempt`` already recorded in options.build_fix.attempts (survives resume/retry)."""
    attempts = _get_state(job).get("attempts") or []
    if not attempts:
        return 0
    nums = [int(a.get("attempt") or 0) for a in attempts if isinstance(a, dict)]
    return max(nums) if nums else 0

# 内核树内相对路径前缀（合入目标仓库根下）
_KERNEL_PATH_MARKERS = (
    "drivers/", "kernel/", "include/", "arch/", "fs/", "net/", "mm/",
    "sound/", "security/", "crypto/", "lib/", "scripts/", "android/",
    "Documentation/", "tools/", "virt/", "init/", "ipc/", "block/",
)

_GCC_ERROR_RE = re.compile(
    r"^(?P<file>[^\s:\'\"<>|]+?\.(?:c|h|S|cpp|cc|rs|dts|dtsi|ld|Kconfig|Makefile|mk|java|aidl))"
    r":(?P<line>\d+)(?::(?P<col>\d+))?\s*:\s*(?P<kind>error|fatal error)\s*:\s*(?P<msg>.+)$",
    re.MULTILINE | re.IGNORECASE,
)
_GCC_PREV_DEF_NOTE_RE = re.compile(
    r"^(?P<file>[^\s:\'\"<>|]+?\.(?:c|h|S|cpp|cc))"
    r":(?P<line>\d+)(?::\d+)?\s*:\s*note:\s*"
    r"(?:this is the location of the previous definition|previous definition is here)",
    re.MULTILINE | re.IGNORECASE,
)
_NINJA_FAIL_RE = re.compile(r"^FAILED:\s*(.+)$", re.MULTILINE)
_MAKE_FAIL_RE = re.compile(r"^make(?:\[\d+\])?\:\s+\*\*\*.*Error\s+(\d+)", re.MULTILINE)
_REBUILD_ATTEMPT_RE = re.compile(
    r"^# ={3,}\s*rebuild attempt\s+\d+\s*={3,}",
    re.MULTILINE | re.IGNORECASE,
)

# 搜索/写回优先级：数值越小越优先（合入目标仓库 deliberately 最低）
_ROOT_RANK = {
    "build_workdir": 0,
    "target_repo": 10,
}


@dataclass(frozen=True)
class FileLocation:
    """Resolved source file on disk (local or remote)."""

    abs_path: str
    display_path: str
    root: str  # target_repo | build_workdir | absolute


def _log(job_id: str, msg: str) -> None:
    append_job_log(job_id, msg, "build_fix")


def _trim(text: str, limit: int = _MAX_STORE_CHARS) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + f"\n... [truncated {len(text) - limit} chars] ...\n" + text[-half:]


_ROOT_LABEL_PREFIX_RE = re.compile(
    r"^\[(?:build_workdir|target_repo)\]\s*",
    re.IGNORECASE,
)


def _strip_root_label_prefix(path: str) -> str:
    """Drop UI labels like ``[build_workdir] vendor/...`` → ``vendor/...``."""
    s = (path or "").strip()
    while True:
        m = _ROOT_LABEL_PREFIX_RE.match(s)
        if not m:
            break
        s = s[m.end():].lstrip()
    return s


def sanitize_llm_fix_path(path: str) -> str:
    """Normalize a path from an LLM ``fix`` block (labels, backticks, slashes)."""
    s = _strip_root_label_prefix((path or "").strip().strip("`").strip())
    if _is_windows_local_path(s):
        return s
    s = s.replace("\\", "/")
    while "//" in s:
        s = s.replace("//", "/")
    return s.lstrip("/")


def fix_path_for_llm(path: str) -> str:
    """Repository-relative path for LLM to echo in fix blocks (preserve case)."""
    return sanitize_llm_fix_path(path)


def _norm_path(path_str: str) -> str:
    s = _strip_root_label_prefix(path_str or "")
    if not s:
        return s
    if _is_windows_local_path(s):
        return s.replace("/", "\\")
    s = s.replace("\\", "/")
    while "//" in s:
        s = s.replace("//", "/")
    if s.startswith("/"):
        s = posixpath.normpath(s)
    elif s:
        s = posixpath.normpath(s)
    if s.endswith("/") and s != "/":
        s = s.rstrip("/")
    return s


def _is_windows_local_path(path_str: str) -> bool:
    s = (path_str or "").strip()
    return s.startswith("\\\\") or (len(s) >= 2 and s[1] == ":")


def _local_abs(path_str: str) -> str:
    """Normalize local path; avoid resolve() on UNC/mapped drives (can fail on SMB)."""
    p = Path(path_str).expanduser()
    if _is_windows_local_path(str(p)):
        return str(p)
    if not p.is_absolute():
        return str(p.resolve())
    return str(p)


def _local_path_candidates(path_str: str) -> List[str]:
    """Path variants for Windows file APIs (UNC long-path prefix, etc.)."""
    raw = (path_str or "").strip()
    if not raw:
        return []
    out: List[str] = []
    seen: set[str] = set()

    def add(p: str) -> None:
        if p and p not in seen:
            seen.add(p)
            out.append(p)

    add(raw)
    p = Path(raw).expanduser()
    add(str(p))
    s = str(p)
    if s.startswith("\\\\") and not s.startswith("\\\\?\\"):
        add("\\\\?\\UNC\\" + s[2:])
    return out


def _hybrid_local_path(job: Dict[str, Any], path_str: str) -> Optional[Path]:
    """Map remote absolute path to local mount (hybrid mode); else None."""
    if not _use_local_mount(job):
        return None
    p = _norm_path(path_str)
    if p.startswith("/"):
        return remote_abs_to_local(job, p)
    if _is_windows_local_path(p):
        return Path(p)
    return None


def _local_is_file(path_str: str) -> bool:
    for cand in _local_path_candidates(path_str):
        try:
            if os.path.isfile(cand):
                return True
        except OSError:
            pass
        try:
            pp = Path(cand)
            if pp.is_file() or (pp.exists() and not pp.is_dir()):
                return True
        except OSError:
            pass
    return False


def _local_is_dir(path_str: str) -> bool:
    for cand in _local_path_candidates(path_str):
        try:
            if os.path.isdir(cand):
                return True
        except OSError:
            pass
        try:
            if Path(cand).is_dir():
                return True
        except OSError:
            pass
    return False


def _local_read_text(path_str: str) -> str:
    last_err: Optional[Exception] = None
    for cand in _local_path_candidates(path_str):
        try:
            return Path(cand).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            last_err = exc
    raise FileNotFoundError(path_str) from last_err


def _local_write_text(path_str: str, content: str) -> None:
    last_err: Optional[Exception] = None
    for cand in _local_path_candidates(path_str):
        try:
            fp = Path(cand)
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8", newline="\n")
            return
        except OSError as exc:
            last_err = exc
    raise OSError(f"无法写回本地映射: {path_str}") from last_err


def _use_local_mount(job: Dict[str, Any]) -> bool:
    from web_app.job_path_mapping import use_local_file_io
    return use_local_file_io(job)


def _build_fix_via_ssh_files(job: Dict[str, Any]) -> bool:
    """Hybrid build-fix always reads/writes via local mount, not SSH file I/O."""
    if _use_local_mount(job):
        return False
    from web_app.upgrade_remote_git import is_remote_active
    return is_remote_active()


def _root_dir_name(root: str) -> str:
    p = root.replace("\\", "/").rstrip("/")
    if not p:
        return ""
    return p.rsplit("/", 1)[-1]


def _join_root_rel(root: str, rel: str) -> str:
    """Join search root + compiler-relative path; drop duplicated tree prefix."""
    rel_norm = rel.replace("\\", "/").lstrip("/")
    root_name = _root_dir_name(root)
    if root_name and rel_norm.startswith(root_name + "/"):
        rel_norm = rel_norm[len(root_name) + 1:]
    if root_name.lower() == "vnd" and rel_norm.startswith("vnd/"):
        rel_norm = rel_norm[4:]
    return str(Path(root) / rel_norm)


def _use_linux_paths(job: Dict[str, Any]) -> bool:
    """Compiler / remote logs use Linux absolute paths."""
    from web_app.upgrade_remote_git import is_remote_active
    return is_remote_active()


def _build_root_anchor(job: Dict[str, Any], build_workdir: str = "") -> str:
    """编译目录最后一级目录名，如 …/gkiPatchTest/vnd → vnd。"""
    wd = normalize_linux_path(build_workdir or job.get("build_workdir") or "")
    if not wd:
        return ""
    return wd.rstrip("/").rsplit("/", 1)[-1]


def _rel_from_build_anchor(raw: str, anchor: str) -> Optional[str]:
    """从日志绝对路径中截取 anchor/ 之后的相对路径（忽略 /work/... 前缀差异）。"""
    if not anchor:
        return None
    raw = _norm_path(raw)
    needle = f"/{anchor}/"
    idx = raw.find(needle)
    if idx >= 0:
        return raw[idx + len(needle):]
    if raw.startswith(f"{anchor}/"):
        return raw[len(anchor) + 1:]
    return None


def _candidate_rels_under_build_root(raw: str, anchor: str) -> List[str]:
    """拼接到配置编译目录下的相对路径候选。"""
    raw = _norm_path(raw)
    out: List[str] = []
    seen: set[str] = set()

    def add(rel: str) -> None:
        rel = rel.replace("\\", "/").lstrip("/")
        if rel and rel not in seen:
            seen.add(rel)
            out.append(rel)

    under = _rel_from_build_anchor(raw, anchor)
    if under:
        add(under)
    is_abs = raw.startswith("/") or (len(raw) > 2 and raw[1] == ":")
    if not is_abs:
        add(raw)
    return out


def _kernel_repo_rels(rel: str) -> List[str]:
    """合入目标 kernel 仓库根下的相对路径（drivers/… 等）。"""
    rel = rel.lstrip("/")
    if not rel:
        return []
    if rel.startswith("kernel-"):
        slash = rel.find("/")
        if slash >= 0:
            return [rel[slash + 1:]]
        return []
    if any(rel.startswith(m) for m in _KERNEL_PATH_MARKERS):
        return [rel]
    return []


def _strip_kernel_tree_prefix(rel: str) -> str:
    rel = rel.lstrip("/")
    if rel.startswith("kernel-"):
        slash = rel.find("/")
        if slash >= 0:
            return rel[slash + 1:]
    return rel


def _vendor_touchscreen_fallback_rels(rel: str) -> List[str]:
    """touchscreen 驱动报错常指向 kernel 树内路径，真实源文件在 vendor/transsion/touchscreen/…。"""
    rel = _strip_kernel_tree_prefix(rel).lstrip("/")
    out: List[str] = []
    seen: set[str] = set()

    def add(r: str) -> None:
        r = r.lstrip("/")
        if r and r not in seen:
            seen.add(r)
            out.append(r)

    if rel.startswith("vendor/transsion/touchscreen/"):
        add(rel)
        return out

    marker = "drivers/input/touchscreen/"
    idx = rel.find(marker)
    if idx < 0:
        return out
    rest = rel[idx + len(marker):]
    parts = [p for p in rest.split("/") if p and p != ".."]
    if len(parts) < 2:
        return out
    basename = parts[-1]
    chip = parts[0]

    for ic in ("goodix", "omnivision", "focaltech", "synaptics"):
        add(f"vendor/transsion/touchscreen/vendor/{ic}/{chip}/{basename}")
    if len(parts) > 2:
        add(f"vendor/transsion/touchscreen/{'/'.join(parts)}")
    return out


def _find_under_build_root(build_root: str, basename: str, *, limit: int = 5) -> List[Tuple[str, str]]:
    """在 vendor/、kernel-5.10/ 下按文件名搜索（跳过网络盘 rglob，太慢）。"""
    if not basename or basename in (".", ".."):
        return []
    if _is_windows_local_path(build_root):
        return []
    root = Path(build_root)
    hits: List[Tuple[str, str]] = []
    for sub in ("vendor", "kernel-5.10"):
        base = root / sub
        if not base.is_dir():
            continue
        try:
            for p in base.rglob(basename):
                if not p.is_file():
                    continue
                try:
                    rel = p.relative_to(root).as_posix()
                except ValueError:
                    continue
                hits.append((str(p), rel))
                if len(hits) >= limit:
                    return hits
        except OSError:
            pass
    return hits


def _io_abs_path(job: Dict[str, Any], path_str: str, root: str = "") -> str:
    """Resolve path for existence checks and read/write."""
    p = _norm_path(path_str)
    if root:
        return _join_root_rel(root, p)
    if _build_fix_via_ssh_files(job):
        return normalize_linux_path(p)
    return _local_abs(p)


def _file_exists(abs_path: str, job: Dict[str, Any]) -> bool:
    local = _hybrid_local_path(job, abs_path)
    if local is not None:
        try:
            return local.is_file()
        except OSError:
            pass
    if _use_local_mount(job):
        return _local_is_file(abs_path)
    p = _norm_path(abs_path)
    if _build_fix_via_ssh_files(job):
        from web_app.upgrade_remote_git import remote_file_exists
        return remote_file_exists(p if p.startswith("/") else p)
    try:
        return Path(p).is_file()
    except OSError:
        return False


def _read_at_location(job: Dict[str, Any], loc: FileLocation) -> str:
    if _build_fix_via_ssh_files(job):
        from web_app.upgrade_remote_git import remote_read_absolute
        return remote_read_absolute(loc.abs_path)
    if _use_local_mount(job):
        return _local_read_text(loc.abs_path)
    return Path(loc.abs_path).read_text(encoding="utf-8", errors="replace")


_CONTEXT_FULL_FILE_MAX_BYTES = 48_000
_CONTEXT_FULL_FILE_MAX_LINES = 120


def _file_stat_key(abs_path: str) -> Optional[str]:
    """Same inode on SMB/symlink aliases → one key (Windows st_dev+st_ino)."""
    for cand in _local_path_candidates(abs_path):
        try:
            st = os.stat(cand)
            return f"stat:{st.st_dev}:{st.st_ino}"
        except OSError:
            continue
    return None


def _file_identity_key(job: Dict[str, Any], abs_path: str) -> str:
    """Canonical path for dedup: symlink/hardlink aliases resolve to one key."""
    if not abs_path:
        return ""
    try:
        if _build_fix_via_ssh_files(job):
            import shlex
            from web_app.upgrade_remote_git import _session, normalize_linux_path
            path = normalize_linux_path(abs_path.replace("\\", "/"))
            r = _session().run(
                f"stat -c '%d:%i' {shlex.quote(path)} 2>/dev/null",
                check=False,
                timeout=30,
            )
            body = (r.stdout or "").strip()
            if r.returncode == 0 and body and ":" in body:
                return f"stat:{body}"
            r2 = _session().run(
                f"readlink -f {shlex.quote(path)} 2>/dev/null || echo {shlex.quote(path)}",
                check=False,
                timeout=30,
            )
            real = ((r2.stdout or "").strip().splitlines() or [path])[0]
            return _norm_path(real).lower()
        stat_key = _file_stat_key(abs_path)
        if stat_key:
            return stat_key
        for cand in _local_path_candidates(abs_path):
            try:
                return _norm_path(os.path.realpath(cand)).lower()
            except OSError:
                continue
        return _norm_path(abs_path).lower()
    except OSError:
        return _norm_path(abs_path).lower()


def _dedupe_paths_by_file_identity(
    job: Dict[str, Any],
    paths: List[str],
    build_workdir: str,
) -> List[str]:
    """Keep one representative path per on-disk file (symlink aliases)."""
    seen: set[str] = set()
    out: List[str] = []
    for path in paths:
        loc = resolve_file_location(job, path, build_workdir)
        key = _file_identity_key(job, loc.abs_path) if loc else _normalize_source_path(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _file_byte_size(job: Dict[str, Any], abs_path: str) -> Optional[int]:
    try:
        if _use_local_mount(job):
            return os.path.getsize(abs_path)
        if _build_fix_via_ssh_files(job):
            import shlex
            from web_app.upgrade_remote_git import _session, normalize_linux_path
            path = normalize_linux_path(abs_path.replace("\\", "/"))
            r = _session().run(
                f"stat -c%s {shlex.quote(path)} 2>/dev/null || echo -1",
                check=False,
                timeout=30,
            )
            try:
                n = int((r.stdout or "").strip())
                return n if n >= 0 else None
            except ValueError:
                return None
        return Path(abs_path).stat().st_size
    except OSError:
        return None


def _read_line_window_local(abs_path: str, line_no: int, radius: int) -> str:
    """Read only a line window — avoid loading multi-MB sources over UNC."""
    start = max(1, line_no - radius)
    end = line_no + radius
    out: List[str] = []
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh, 1):
                if lineno < start:
                    continue
                if lineno > end:
                    break
                prefix = ">>>" if lineno == line_no else "   "
                out.append(f"{prefix} {lineno:5d}| {line.rstrip(chr(10) + chr(13))}")
    except OSError:
        return ""
    return "\n".join(out)


def _read_line_window_at_location(
    job: Dict[str, Any],
    loc: FileLocation,
    line_no: int,
    radius: int,
) -> str:
    if _build_fix_via_ssh_files(job):
        import shlex
        from web_app.upgrade_remote_git import _session, normalize_linux_path
        start = max(1, line_no - radius)
        end = line_no + radius
        path = normalize_linux_path(loc.abs_path.replace("\\", "/"))
        r = _session().run(
            f"sed -n '{start},{end}p' {shlex.quote(path)}",
            check=False,
            timeout=60,
        )
        if r.returncode != 0 or not (r.stdout or "").strip():
            return _file_context_snippet(_read_at_location(job, loc), line_no, radius)
        buf: List[str] = []
        for i, line in enumerate((r.stdout or "").splitlines(), start):
            prefix = ">>>" if i == line_no else "   "
            buf.append(f"{prefix} {i:5d}| {line}")
        return "\n".join(buf)
    if _use_local_mount(job):
        return _read_line_window_local(loc.abs_path, line_no, radius)
    return _read_line_window_local(loc.abs_path, line_no, radius)


def _read_context_from_location(
    job: Dict[str, Any],
    loc: FileLocation,
    line_no: int,
    radius: int,
) -> Tuple[str, Optional[str]]:
    """Return (snippet, full_content_or_none). Large files use line-window only."""
    size = _file_byte_size(job, loc.abs_path)
    if size is not None and size > _CONTEXT_FULL_FILE_MAX_BYTES:
        return _read_line_window_at_location(job, loc, line_no, radius), None
    content = _read_at_location(job, loc)
    line_count = len(content.splitlines())
    if line_count > _CONTEXT_FULL_FILE_MAX_LINES or len(content) > _CONTEXT_FULL_FILE_MAX_BYTES:
        return _read_line_window_at_location(job, loc, line_no, radius), None
    return _file_context_snippet(content, line_no, radius), content


def _write_at_location(job: Dict[str, Any], loc: FileLocation, content: str) -> None:
    if _build_fix_via_ssh_files(job):
        from web_app.upgrade_remote_git import remote_write_absolute
        remote_write_absolute(loc.abs_path, content)
        return
    if _use_local_mount(job):
        _local_write_text(loc.abs_path, content)
        return
    fp = Path(loc.abs_path)
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8", newline="\n")


def _target_repo_abs(job: Dict[str, Any], build_workdir: str = "") -> Optional[str]:
    if _use_local_mount(job):
        from web_app.job_path_mapping import job_local_repo_root
        root = job_local_repo_root(job)
        return str(root) if root else None
    target = (job.get("target_repo_dir") or "").strip()
    if not target:
        return None
    if _use_linux_paths(job):
        return normalize_linux_path(target)
    from web_app.target_repo_config import resolve_target_repo_path
    resolved = resolve_target_repo_path(target)
    return _local_abs(str(resolved) if resolved else target)


def _is_under_target_repo(
    abs_path: str,
    job: Dict[str, Any],
    build_workdir: str = "",
) -> bool:
    target = _target_repo_abs(job, build_workdir)
    if not target:
        return False
    return _under_root(abs_path, target, job) is not None


# Google GKI readonly: compare on-disk content with GKI common @ job.to_tag.
_gki_to_tag_cache: Dict[str, Dict[str, Optional[str]]] = {}


def _normalize_file_text(text: str) -> str:
    t = text.replace("\r\n", "\n")
    if t and not t.endswith("\n"):
        t += "\n"
    return t


def _google_to_tag_text(job: Dict[str, Any], kernel_rel: str) -> Optional[str]:
    """GKI common file at to_tag, or None if not in upstream / unavailable."""
    to_tag = (job.get("to_tag") or "").strip()
    if not to_tag:
        return None
    rel = kernel_rel.replace("\\", "/").lstrip("/")
    job_id = str(job.get("id") or job.get("job_id") or "")
    bucket_key = f"{job_id}:{to_tag}"
    bucket = _gki_to_tag_cache.setdefault(bucket_key, {})
    if rel in bucket:
        return bucket[rel]
    try:
        text = read_gki_file_at_tag(to_tag, rel)
    except FileNotFoundError:
        bucket[rel] = None
        return None
    except Exception:
        return None
    bucket[rel] = text
    return text


def _kernel_tree_rel(
    raw_path: str,
    loc: FileLocation,
    job: Dict[str, Any],
    build_workdir: str = "",
) -> str:
    """Path relative to kernel tree root (strip kernel-5.10/ prefix from build_workdir paths)."""
    raw = _norm_path(raw_path or "").lstrip("/")
    if raw.startswith("kernel-"):
        slash = raw.find("/")
        if slash >= 0:
            return raw[slash + 1 :]
    target = _target_repo_abs(job, build_workdir)
    if target:
        rel = _under_root(loc.abs_path, target, job)
        if rel is not None:
            return rel
    build_abs = _abs_build_root(job, build_workdir)
    if build_abs:
        rel = _under_root(loc.abs_path, build_abs, job)
        if rel:
            if rel.startswith("kernel-5.10/"):
                return rel[len("kernel-5.10/") :]
            if rel.startswith("kernel/"):
                parts = rel.split("/", 2)
                if len(parts) >= 3 and parts[1].startswith("kernel-"):
                    return parts[2]
            return rel
    disp = loc.display_path
    if "]" in disp:
        disp = disp.split("]", 1)[1].strip()
    return _strip_kernel_tree_prefix(disp).lstrip("/")


def _is_google_kernel_readonly(
    rel: str,
    *,
    job: Optional[Dict[str, Any]] = None,
    content: Optional[str] = None,
) -> bool:
    """True when file content matches GKI to_tag (pure Google upstream, no vendor delta)."""
    rel = rel.lstrip("/")
    if rel.startswith(("vendor/", "device/", "hardware/", "frameworks/", "system/")):
        return False
    if not job or content is None:
        return False
    google = _google_to_tag_text(job, rel)
    if google is None:
        return False
    return _normalize_file_text(content) == _normalize_file_text(google)


def _is_upstream_kernel_readonly(
    rel: str,
    *,
    job: Optional[Dict[str, Any]] = None,
    content: Optional[str] = None,
) -> bool:
    return _is_google_kernel_readonly(rel, job=job, content=content)


def _upstream_readonly_reason(rel: str, job: Optional[Dict[str, Any]] = None) -> str:
    tag = (job.get("to_tag") if job else "") or ""
    tag_note = f"GKI to_tag={tag} " if tag else ""
    return (
        f"与 {tag_note}内容一致 ({rel})，判定为 Google 上游代码，禁止修改；"
        "若编译器指向该文件（如 minmax.h），应在 vendor/驱动侧修复先定义的宏"
    )


def _rank_location(loc: FileLocation, job: Dict[str, Any], build_workdir: str) -> int:
    """Rank by declared root only — do not bump build_workdir paths under kernel tree."""
    return _ROOT_RANK.get(loc.root, 5)


def _abs_build_root(job: Dict[str, Any], build_workdir: str) -> Optional[str]:
    """配置的编译目录在本机/远程上的绝对路径。"""
    bw = (build_workdir or job.get("build_workdir") or "").strip()
    if not bw:
        return None
    if _use_local_mount(job):
        from web_app.job_path_mapping import resolve_local_build_mount
        local = resolve_local_build_mount(job)
        return str(local) if local else None
    if _use_linux_paths(job):
        return normalize_linux_path(bw)
    resolved = resolve_build_workdir(bw)
    return _local_abs(str(resolved) if resolved else bw)


def _search_roots(job: Dict[str, Any], build_workdir: str = "") -> List[Tuple[str, str]]:
    """Return [(root_name, abs_root), …] — 仅编译目录 + 合入目标。"""
    roots: List[Tuple[str, str]] = []
    build_abs = _abs_build_root(job, build_workdir)
    if build_abs:
        roots.append(("build_workdir", build_abs))
    target_abs = _target_repo_abs(job, build_workdir)
    if target_abs:
        roots.append(("target_repo", target_abs))
    return roots


def _under_root(abs_path: str, root: str, job: Dict[str, Any]) -> Optional[str]:
    """Return relative path if abs_path is under root."""
    if _build_fix_via_ssh_files(job):
        p, r = _norm_path(abs_path), _norm_path(root)
        if p == r:
            return ""
        if p.startswith(r + "/"):
            return p[len(r) + 1:]
        return None
    try:
        p = Path(abs_path).resolve()
        r = Path(root).resolve()
        if p == r:
            return ""
        return p.relative_to(r).as_posix()
    except (ValueError, OSError):
        return None


def resolve_all_file_locations(
    job: Dict[str, Any],
    raw_path: str,
    build_workdir: str = "",
    *,
    vendor_fallback: bool = False,
) -> List[FileLocation]:
    """Return all resolved locations sorted by priority (build_workdir before target_repo).

    不解析 build log 里的 /work/... 绝对路径前缀；从配置的编译目录名（如 vnd）截取
    相对段，再与 build_workdir / target_repo 拼接。
    """
    raw = _norm_path(raw_path)
    if not raw:
        return []

    bw = build_workdir or job.get("build_workdir") or ""
    anchor = _build_root_anchor(job, bw)
    rels = _candidate_rels_under_build_root(raw, anchor)
    if not rels:
        return []

    roots = {name: path for name, path in _search_roots(job, build_workdir)}
    found: Dict[str, FileLocation] = {}
    tried: List[str] = []

    def add_loc(loc: FileLocation) -> None:
        key = loc.abs_path.lower()
        prev = found.get(key)
        if prev is None or _rank_location(loc, job, build_workdir) < _rank_location(prev, job, build_workdir):
            found[key] = loc

    def try_abs(abs_p: str, *, root_name: str, display_rel: str) -> None:
        tried.append(abs_p)
        if _file_exists(abs_p, job):
            add_loc(FileLocation(
                abs_path=abs_p,
                display_path=f"[{root_name}] {display_rel}",
                root=root_name,
            ))

    if _use_local_mount(job) and raw.startswith("/"):
        from web_app.job_path_mapping import remote_abs_to_local
        local_p = remote_abs_to_local(job, raw)
        if local_p is not None:
            abs_p = str(local_p)
            rel_under = _under_root(abs_p, roots.get("target_repo") or "", job)
            if rel_under is None and roots.get("build_workdir"):
                rel_under = _under_root(abs_p, roots["build_workdir"], job)
            disp = rel_under or abs_p
            root_name = "target_repo" if rel_under and roots.get("target_repo") and _under_root(abs_p, roots["target_repo"], job) is not None else "build_workdir"
            try_abs(abs_p, root_name=root_name, display_rel=disp)

    def try_join(root_name: str, rel: str) -> None:
        root = roots.get(root_name)
        if not root or not rel:
            return
        if _build_fix_via_ssh_files(job):
            abs_p = normalize_linux_path(f"{root.rstrip('/')}/{rel.lstrip('/')}")
        else:
            abs_p = _join_root_rel(root, rel)
        try_abs(abs_p, root_name=root_name, display_rel=rel)

    queued: List[str] = []
    seen_rels: set[str] = set()

    def queue_rel(r: str) -> None:
        r = r.lstrip("/")
        if r and r not in seen_rels:
            seen_rels.add(r)
            queued.append(r)

    primary_rel = rels[0].lstrip("/") if rels else ""

    for rel in rels:
        queue_rel(rel)
        if vendor_fallback:
            for fb in _vendor_touchscreen_fallback_rels(rel):
                queue_rel(fb)

    for rel in queued:
        try_join("build_workdir", rel)
        for krel in _kernel_repo_rels(rel):
            try_join("target_repo", krel)

    if not found:
        build_root = roots.get("build_workdir")
        basename = posixpath.basename(raw)
        if build_root and basename:
            for abs_p, rel in _find_under_build_root(build_root, basename):
                tried.append(abs_p)
                if _file_exists(abs_p, job):
                    add_loc(FileLocation(
                        abs_path=abs_p,
                        display_path=f"[build_workdir] {rel}",
                        root="build_workdir",
                    ))

    locs = list(found.values())

    def _sort_key(loc: FileLocation) -> Tuple[int, int, str]:
        rank = _rank_location(loc, job, build_workdir)
        disp = loc.display_path.lower()
        primary = primary_rel.lower()
        # Prefer the path segment derived from the compiler error over aliases.
        primary_match = 0 if primary and disp.endswith(primary) else 1
        return (rank, primary_match, loc.display_path)

    locs.sort(key=_sort_key)
    if not locs and tried and _use_local_mount(job):
        job_id = job.get("id") or job.get("job_id") or ""
        if job_id:
            sample = "; ".join(tried[:4])
            if len(tried) > 4:
                sample += f" …共 {len(tried)} 个候选"
            _log(str(job_id), f"路径未命中: {raw_path!r}（anchor={anchor!r}，已尝试 {sample}）")
    return locs


def resolve_file_location(
    job: Dict[str, Any],
    raw_path: str,
    build_workdir: str = "",
    *,
    avoid_target_repo: bool = False,
) -> Optional[FileLocation]:
    """Locate a source file; prefer paths outside merge target when avoid_target_repo=True."""
    locs = resolve_all_file_locations(job, raw_path, build_workdir)
    if not locs:
        return None
    if avoid_target_repo:
        for loc in locs:
            if not _is_under_target_repo(loc.abs_path, job, build_workdir):
                return loc
        return None
    return locs[0]


def validate_hybrid_build_fix_mounts(
    job: Dict[str, Any],
    build_workdir: str = "",
) -> Optional[str]:
    """混合模式 build_fix 预检：本地映射必须可读，否则提前失败并给出可操作提示。"""
    if not _use_local_mount(job):
        return None

    mount = (job.get("local_repo_mount") or "").strip()
    roots = _search_roots(job, build_workdir)
    if not roots:
        return "未推导出本地 build_workdir / target_repo 根目录，请检查编译目录与服务器映射路径配置"

    bad: List[str] = []
    for name, path in roots:
        if not _local_is_dir(path):
            bad.append(f"{name}={path}")
    if bad:
        hint = (
            "请在已映射网络盘的同一终端启动 Web 服务（python web_app/app.py），"
            "「服务器映射路径」建议填 Z: 盘路径，例如 Z:\\gkiPatchTest\\vnd\\kernel-5.10"
        )
        return f"本地映射目录不可访问: {'; '.join(bad)}。{hint}"

    anchor = _build_root_anchor(job, build_workdir)
    root_summary = ", ".join(f"{n}={p}" for n, p in roots)
    job_id = job.get("id") or job.get("job_id") or ""
    if job_id:
        _log(
            str(job_id),
            f"本地映射预检通过（anchor={anchor!r}）: {root_summary}",
        )
    return None


def probe_error_file_resolution(
    job: Dict[str, Any],
    errors: List[Dict[str, Any]],
    build_workdir: str = "",
) -> Tuple[int, int, List[str]]:
    """Try resolving compile errors locally; return (resolved, total, unresolved samples)."""
    samples: List[str] = []
    resolved = 0
    total = 0
    seen: set[str] = set()
    for err in errors:
        fp = (err.get("file") or "").strip()
        if not fp or fp in seen:
            continue
        seen.add(fp)
        total += 1
        if resolve_file_location(job, fp, build_workdir):
            resolved += 1
        elif len(samples) < 3:
            samples.append(fp)
    return resolved, total, samples


def _get_state(job: Dict[str, Any]) -> Dict[str, Any]:
    opts = job.get("options") or {}
    st = opts.get("build_fix")
    if not isinstance(st, dict):
        st = {"status": "idle", "attempts": []}
    if "attempts" not in st:
        st["attempts"] = []
    return st


def _save_state(job_id: str, job: Dict[str, Any], state: Dict[str, Any]) -> None:
    opts = dict(job.get("options") or {})
    opts["build_fix"] = state
    update_upgrade_job(job_id, options=opts)


def read_log_tail(log_path: str, max_chars: int = _MAX_LOG_TAIL) -> str:
    p = Path(log_path)
    if not p.is_file():
        return ""
    try:
        size = p.stat().st_size
        with p.open("rb") as f:
            if size > max_chars:
                f.seek(size - max_chars)
            data = f.read()
        text = data.decode("utf-8", errors="replace")
        if size > max_chars and "\n" in text:
            text = text.split("\n", 1)[-1]
        return text
    except OSError:
        return ""


def extract_latest_build_log_segment(log_text: str) -> str:
    """Keep only the latest rebuild attempt block (multi-round builds append to one file)."""
    if not log_text:
        return log_text
    matches = list(_REBUILD_ATTEMPT_RE.finditer(log_text))
    if not matches:
        return log_text
    return log_text[matches[-1].start():]


def read_log_for_build_fix(log_path: str, max_chars: int = _MAX_LOG_TAIL) -> str:
    """Tail of build log for build_fix (see _effective_build_log_segment)."""
    read_size = max(max_chars, 400_000)
    return read_log_tail(log_path, max_chars=read_size)


def _effective_build_log_segment(log_text: str) -> str:
    segment = extract_latest_build_log_segment(log_text)
    if len(segment) < 8000 and len(log_text) > len(segment) + 1000:
        return log_text
    return segment


def parse_build_errors(
    log_text: str,
    *,
    max_errors: int = _MAX_ERRORS,
) -> Tuple[List[Dict[str, Any]], str, List[Dict[str, Any]]]:
    """Return structured errors, log excerpt, and diagnostic chains for LLM context."""
    segment = _effective_build_log_segment(log_text)
    errors, chains = parse_build_log_diagnostics(segment, max_errors=max_errors)

    excerpt_lines: List[str] = []
    if errors:
        for err in errors[:12]:
            priority = err.get("error_priority") or ""
            tag = f"[{priority}] " if priority else ""
            excerpt_lines.append(
                f"{tag}{err['file']}:{err['line']}: {err['kind']}: {err['message']}"
            )
    else:
        for m in _NINJA_FAIL_RE.finditer(log_text):
            excerpt_lines.append(f"FAILED: {m.group(1).strip()}")
        for m in _MAKE_FAIL_RE.finditer(log_text):
            excerpt_lines.append(f"make Error {m.group(1)}")

    tail = segment[-min(len(segment), 12_000):]
    excerpt = "\n".join(excerpt_lines)
    if excerpt:
        excerpt += "\n\n--- log tail (latest attempt) ---\n"
    excerpt += tail
    return errors, excerpt, chains


def _parse_previous_definition_sites(
    log_text: str,
    *,
    max_sites: int = 20,
) -> List[Dict[str, Any]]:
    """GCC notes pointing at the original MAX/MIN (etc.) definition before minmax.h."""
    segment = _effective_build_log_segment(log_text)
    sites: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for m in _GCC_PREV_DEF_NOTE_RE.finditer(segment):
        path = m.group("file").replace("\\", "/")
        key = path.lower()
        if key in seen:
            continue
        seen.add(key)
        sites.append({
            "file": path,
            "line": int(m.group("line")),
            "kind": "note",
            "message": "previous definition",
        })
        if len(sites) >= max_sites:
            break
    return sites


def _normalize_source_path(path: str) -> str:
    p = _norm_path(path or "").lower().strip()
    if p.startswith("[build_workdir]"):
        p = p.split("]", 1)[-1].strip()
    return p.lstrip("/").replace("\\", "/")


def _source_path_variants(path: str) -> List[str]:
    norm = _normalize_source_path(path)
    if not norm:
        return []
    variants = {norm}
    for marker in ("kernel-5.10/", "kernel/"):
        if marker in norm:
            variants.add(norm.split(marker, 1)[-1])
    return list(variants)


def _error_matches_fix_path(err_file: str, raw_path: str, loc: FileLocation) -> bool:
    """True if compile error file and LLM fix path refer to the same source."""
    err_variants = set(_source_path_variants(err_file))
    if not err_variants:
        return False
    fix_variants: set[str] = set()
    for candidate in (raw_path, loc.display_path, loc.abs_path):
        fix_variants.update(_source_path_variants(candidate))
    if not fix_variants:
        return False
    for ef in err_variants:
        for fp in fix_variants:
            if ef == fp:
                return True
            if ef.endswith("/" + fp) or fp.endswith("/" + ef):
                return True
    return False


def _file_context_snippet(content: str, line_no: int, radius: int = 40) -> str:
    lines = content.splitlines()
    if not lines:
        return content[:8000]
    idx = max(0, min(len(lines) - 1, line_no - 1))
    start = max(0, idx - radius)
    end = min(len(lines), idx + radius + 1)
    out: List[str] = []
    for i in range(start, end):
        prefix = ">>>" if i == idx else "   "
        out.append(f"{prefix} {i + 1:5d}| {lines[i]}")
    return "\n".join(out)


def _resolve_fix_content(before: str, content: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (new_content, error) via diff processor pipeline."""
    result = process_llm_fix_content(before, content or "")
    return result.content, result.error


def _format_apply_error(display_path: str, detail: str, before: str) -> str:
    """Include on-disk snippet so LLM retry can align diff context."""
    hint_m = re.search(r"(?:hint 第|约第) (\d+) 行", detail)
    if hint_m and before:
        line_no = int(hint_m.group(1))
        snippet = _file_context_snippet(before, line_no, radius=15)
        return (
            f"{display_path}: {detail}\n"
            f"--- 该路径磁盘文件片段（diff 上下文须与此一致）---\n{snippet}"
        )
    return f"{display_path}: {detail}"


def _error_context_role(err: Dict[str, Any]) -> str:
    """Label for LLM: where to fix vs read-only error site."""
    path = _normalize_source_path(err.get("file") or "")
    kernel = is_kernel_readonly_path(path)
    if (err.get("kind") or "").lower() == "note":
        if kernel:
            return "readonly_macro_definition"
        return "previous_definition"
    if kernel:
        return "readonly_error_site"
    priority = err.get("error_priority") or ""
    if priority == "primary":
        return "primary_error"
    if priority == "cascade":
        return "cascade_error"
    if priority == "related":
        return "related_error"
    return "error_site"


def _sort_errors_for_context(errors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    role_order = {
        "primary_error": 0,
        "previous_definition": 1,
        "related_error": 2,
        "error_site": 3,
        "cascade_error": 4,
        "readonly_macro_definition": 5,
        "readonly_error_site": 6,
    }
    enriched = []
    for err in errors:
        row = dict(err)
        row["context_role"] = _error_context_role(row)
        enriched.append(row)
    return sorted(
        enriched,
        key=lambda e: (
            role_order.get(e.get("context_role", ""), 9),
            _normalize_source_path(e.get("file") or ""),
            int(e.get("line") or 0),
        ),
    )


_ROLE_LABELS = {
    "primary_error": "厂商侧 error — 在此文件修复（勿改内核）",
    "previous_definition": "厂商先前定义 — 在此文件修复（勿改内核）",
    "related_error": "同文件关联 error",
    "cascade_error": "可能由前面错误引起的连带 error",
    "readonly_macro_definition": "GKI/内核先前定义 — 只读勿改",
    "readonly_error_site": "GKI/内核 error 落点 — 只读勿改，改厂商文件",
    "error_site": "error 落点",
}


def _context_entry_from_location(
    job: Dict[str, Any],
    loc: FileLocation,
    line_no: int,
    role: str,
    build_workdir: str,
    *,
    anchors: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    radius = 55 if role in ("previous_definition", "primary_error") else 40
    snippet, content = _read_context_from_location(job, loc, line_no, radius)
    if content and anchors and len(anchors) > 1:
        snippet = multi_anchor_snippet(content, anchors, radius=radius)
    damage = detect_comment_structure_damage(content or "")
    if damage:
        snippet = (
            "=== ⚠ 磁盘文件注释结构已损坏（本轮 diff 须优先修复，再处理宏/其它报错）===\n"
            f"{damage.replace('，已拒绝写回', '')}\n"
            "常见原因：此前误删 `/**` 仅留下 ` * …` / ` */`。"
            "修复方式：补回缺失 `/**`，或整段删除孤立 ` * … */` 块（连续 hunk）。\n\n"
            f"{snippet}"
        )
    return {
        "path": loc.display_path,
        "fix_path": fix_path_for_llm(loc.display_path),
        "file_identity": _file_identity_key(job, loc.abs_path),
        "abs_path": loc.abs_path,
        "root": loc.root,
        "in_target_repo": _is_under_target_repo(loc.abs_path, job, build_workdir),
        "line": line_no,
        "role": role,
        "role_label": _ROLE_LABELS.get(role, role),
        "anchors": anchors or [{"line": line_no, "role": role}],
        "snippet": snippet,
        "content": content,
    }


def _refresh_file_contexts(
    job: Dict[str, Any],
    contexts: List[Dict[str, Any]],
    build_workdir: str,
) -> List[Dict[str, Any]]:
    """Re-read snippets from disk (after partial apply or failed retry)."""
    refreshed: List[Dict[str, Any]] = []
    for ctx in contexts:
        path = ctx.get("path") or ctx.get("abs_path") or ""
        loc = resolve_file_location(job, path, build_workdir)
        if not loc:
            refreshed.append(ctx)
            continue
        try:
            line_no = int(ctx.get("line") or 1)
            role = ctx.get("role") or _error_context_role({})
            refreshed.append(_context_entry_from_location(job, loc, line_no, role, build_workdir))
        except FileNotFoundError:
            refreshed.append(ctx)
    return refreshed


def _is_readonly_kernel_fix_path(path: str) -> bool:
    """Paths under include/linux/ are GKI upstream — never LLM-fix targets."""
    p = _normalize_source_path(path).lstrip("/")
    return bool(p) and (p.startswith("include/linux/") or "/include/linux/" in f"/{p}/")


def _vendor_note_fix_paths(errors: List[Dict[str, Any]]) -> List[str]:
    """Extract vendor paths from previous_definition notes (macro redef root cause)."""
    out: List[str] = []
    seen: set[str] = set()
    for err in errors:
        role = err.get("context_role") or _error_context_role(err)
        if role != "previous_definition":
            continue
        raw = err.get("file") or ""
        norm = _normalize_source_path(raw)
        if "vendor/" not in norm and not norm.startswith("vendor/"):
            continue
        fp = sanitize_llm_fix_path(raw)
        key = _normalize_source_path(fp)
        if key and key not in seen:
            seen.add(key)
            out.append(fp)
    return out


def _expand_failed_paths_for_retry(
    job: Dict[str, Any],
    paths: List[str],
    errors: List[Dict[str, Any]],
    build_workdir: str,
) -> List[str]:
    """Redirect readonly kernel-head failures to vendor note sites."""
    out: List[str] = []
    seen: set[str] = set()
    vendor_alts = _vendor_note_fix_paths(errors)
    for raw in paths:
        if _is_readonly_kernel_fix_path(raw):
            for alt in vendor_alts:
                key = _normalize_source_path(alt)
                if key and key not in seen:
                    seen.add(key)
                    out.append(alt)
            continue
        loc = resolve_file_location(job, raw, build_workdir)
        if loc:
            krel = _kernel_tree_rel(raw, loc, job, build_workdir)
            try:
                before = _read_at_location(job, loc)
            except FileNotFoundError:
                before = ""
            if _is_upstream_kernel_readonly(krel, job=job, content=before):
                for alt in vendor_alts:
                    key = _normalize_source_path(alt)
                    if key and key not in seen:
                        seen.add(key)
                        out.append(alt)
                continue
        key = _normalize_source_path(raw)
        if key and key not in seen:
            seen.add(key)
            out.append(sanitize_llm_fix_path(raw))
    return out


def _filter_llm_fix_targets(
    job: Dict[str, Any],
    fixes: List[Dict[str, str]],
    build_workdir: str,
    *,
    job_id: str = "",
) -> List[Dict[str, str]]:
    """Drop fixes targeting Google upstream / include/linux (readonly)."""
    kept: List[Dict[str, str]] = []
    for fix in fixes:
        path = fix.get("path") or ""
        if _is_readonly_kernel_fix_path(path):
            if job_id:
                _log(job_id, f"忽略 LLM 对只读内核头的修改建议: {path}")
            continue
        loc = resolve_file_location(job, path, build_workdir)
        if loc:
            krel = _kernel_tree_rel(path, loc, job, build_workdir)
            try:
                before = _read_at_location(job, loc)
            except FileNotFoundError:
                before = ""
            if _is_upstream_kernel_readonly(krel, job=job, content=before):
                if job_id:
                    _log(
                        job_id,
                        f"忽略 LLM 对 Google 上游文件的修改建议: {path}（应在 vendor note 处修复）",
                    )
                continue
        kept.append(fix)
    return kept


def _extract_failed_paths(apply_errors: List[str]) -> List[str]:
    paths: List[str] = []
    seen: set[str] = set()
    for msg in apply_errors:
        m = re.match(r"^\[[^\]]+\]\s+([^:\n]+):", msg)
        if not m:
            continue
        p = m.group(1).strip()
        key = _normalize_source_path(p)
        if key in seen:
            continue
        seen.add(key)
        paths.append(sanitize_llm_fix_path(p))
    return paths


def _apply_error_matches_path(err_msg: str, path: str) -> bool:
    m = re.match(r"^\[[^\]]+\]\s+([^:\n]+):", err_msg)
    if not m:
        return _normalize_source_path(path) in _normalize_source_path(err_msg)
    return _normalize_source_path(m.group(1)) == _normalize_source_path(path)


def _collect_context_for_path(
    job: Dict[str, Any],
    display_path: str,
    errors: List[Dict[str, Any]],
    build_workdir: str,
) -> Optional[Dict[str, Any]]:
    loc = resolve_file_location(job, display_path, build_workdir)
    if not loc:
        return None
    line_no = 40
    role = "previous_definition"
    norm = _normalize_source_path(display_path)
    for err in errors:
        if _normalize_source_path(err.get("file") or "") == norm:
            line_no = int(err.get("line") or line_no)
            role = err.get("context_role") or _error_context_role(err)
            break
    try:
        return _context_entry_from_location(job, loc, line_no, role, build_workdir)
    except FileNotFoundError:
        return None


def _collect_file_contexts(
    job: Dict[str, Any],
    errors: List[Dict[str, Any]],
    build_workdir: str,
    *,
    max_contexts: int = 16,
    job_id: str = "",
    diagnostic_chains: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Tuple[Dict[str, Any], FileLocation]]] = {}
    order: List[str] = []
    for err in _sort_errors_for_context(errors):
        if (err.get("kind") or "").lower() == "note":
            path = err.get("file") or ""
            if "/include/linux/" in _normalize_source_path(path):
                continue
        loc = resolve_file_location(job, err.get("file", ""), build_workdir)
        if not loc:
            continue
        identity = _file_identity_key(job, loc.abs_path)
        if identity not in grouped:
            grouped[identity] = []
            order.append(identity)
        grouped[identity].append((err, loc))

    contexts: List[Dict[str, Any]] = []
    for identity in order:
        if len(contexts) >= max_contexts:
            break
        items = grouped[identity]
        primary_err = items[0][0]
        loc = items[0][1]
        primary_role = primary_err.get("context_role") or _error_context_role(primary_err)
        fix_path = _kernel_tree_rel(
            primary_err.get("file") or "",
            loc,
            job,
            build_workdir,
        ) or sanitize_llm_fix_path(loc.display_path)
        if primary_role in ("readonly_error_site", "readonly_macro_definition"):
            continue
        if _is_readonly_kernel_fix_path(fix_path):
            continue
        for err, _ in items:
            if err.get("error_priority") == "primary" or err.get("context_role") == "primary_error":
                primary_err = err
                break
        if len(items) > 1 and job_id:
            names = ", ".join(l.display_path for _, l in items[1:3])
            extra = f" 等 {len(items)} 个" if len(items) > 3 else ""
            _log(
                job_id,
                f"软链接合并: {len(items)} 条报错路径指向同一文件，仅加载一份上下文"
                f"（代表: {loc.display_path}; 别名: {names}{extra}）",
            )
        try:
            file_content = _read_at_location(job, loc)
            anchors: List[Dict[str, Any]] = []
            seen_lines: set[int] = set()
            for err, _ in items:
                if (err.get("kind") or "").lower() != "error":
                    continue
                ln = int(err.get("line") or 0)
                if not ln or ln in seen_lines:
                    continue
                seen_lines.add(ln)
                anchors.append({
                    "line": ln,
                    "role": err.get("context_role") or _error_context_role(err),
                    "priority": err.get("error_priority") or "",
                    "message": (err.get("message") or "")[:100],
                })
            fix_path = fix_path_for_llm(loc.display_path)
            for chain in chains_matching_file(diagnostic_chains or [], fix_path):
                if chain.get("chain_type") != "kernel_macro_collision":
                    continue
                symbol = chain.get("symbol") or ""
                for ln in collision_call_site_lines(file_content, symbol):
                    if ln in seen_lines:
                        continue
                    seen_lines.add(ln)
                    anchors.append({
                        "line": ln,
                        "role": "collision_use",
                        "priority": "related",
                        "message": f"{symbol} 引用/定义（rename 须同步）",
                    })
            anchors.sort(key=lambda a: int(a.get("line") or 0))
            line_no = int(primary_err.get("line") or anchors[0]["line"] if anchors else 1)
            role = primary_err.get("context_role") or _error_context_role(primary_err)
            ctx = _context_entry_from_location(
                job, loc, line_no, role, build_workdir, anchors=anchors or None,
            )
            if len(items) > 1:
                ctx["symlink_aliases"] = [l.display_path for _, l in items[1:]]
            contexts.append(ctx)
        except FileNotFoundError:
            continue
    return contexts


def _collect_readonly_note_contexts(
    job: Dict[str, Any],
    errors: List[Dict[str, Any]],
    build_workdir: str,
    *,
    max_notes: int = 6,
) -> List[Dict[str, Any]]:
    """Load short read-only snippets for kernel header notes (macro definition sites)."""
    contexts: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for err in errors:
        if (err.get("kind") or "").lower() != "note":
            continue
        role = err.get("context_role") or _error_context_role(err)
        if role != "readonly_macro_definition":
            continue
        path = err.get("file") or ""
        line_no = int(err.get("line") or 1)
        key = f"{_normalize_source_path(path)}:{line_no}"
        if key in seen:
            continue
        seen.add(key)
        loc = resolve_file_location(job, path, build_workdir)
        if not loc:
            continue
        try:
            snippet = _read_line_window_at_location(job, loc, line_no, radius=5)
            contexts.append({
                "path": loc.display_path,
                "fix_path": fix_path_for_llm(loc.display_path),
                "line": line_no,
                "macro": err.get("macro") or "",
                "message": err.get("message") or "",
                "readonly": True,
                "snippet": snippet,
            })
        except (FileNotFoundError, OSError):
            continue
        if len(contexts) >= max_notes:
            break
    return contexts


def _llm_skip_summary(summary: str) -> bool:
    return bool(re.search(
        r"无需|跳过|已无|无需修改|不必修改|已删除|已修复|无需再改",
        summary or "",
        re.I,
    ))


def _filter_errors_exclude_fixed_identities(
    job: Dict[str, Any],
    apply_errors: List[str],
    applied: List[Dict[str, Any]],
    build_workdir: str,
) -> List[str]:
    """Drop errors for symlink aliases once the canonical file was patched."""
    fixed = {
        _file_identity_key(job, row["abs_path"])
        for row in applied
        if row.get("abs_path")
    }
    if not fixed:
        return apply_errors
    kept: List[str] = []
    for err in apply_errors:
        m = re.match(r"^\[[^\]]+\]\s+([^:\n]+):", err)
        path = m.group(1).strip() if m else err
        loc = resolve_file_location(job, path, build_workdir)
        ik = _file_identity_key(job, loc.abs_path) if loc else ""
        if ik and ik in fixed:
            continue
        kept.append(err)
    return kept


def _basename_fix_cache(applied: List[Dict[str, Any]]) -> Dict[str, str]:
    """Map basename → last successful fix content (prefer parseable unified diff)."""
    cache: Dict[str, str] = {}
    for row in applied:
        base = posixpath.basename(_normalize_source_path(row.get("path") or ""))
        if not base:
            continue
        llm = (row.get("llm_fix_content") or "").strip()
        processed = (row.get("processed_diff") or "").strip()
        stored_diff = (row.get("diff") or "").strip()
        picked: Optional[str] = None
        for candidate in (processed, llm, stored_diff):
            if not candidate:
                continue
            sanitized = _sanitize_unified_diff(candidate)
            if _looks_like_unified_diff(sanitized):
                try:
                    _parse_diff_hunks(sanitized)
                    picked = candidate
                    break
                except ValueError:
                    continue
        if picked:
            cache[base] = picked
        elif llm:
            cache[base] = llm
    return cache


def _try_reuse_basename_fixes(
    job: Dict[str, Any],
    paths: List[str],
    cache: Dict[str, str],
    build_workdir: str,
    *,
    job_id: str = "",
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """Apply a diff that worked on one file to siblings with the same basename."""
    if not cache or not paths:
        return [], paths, []
    reuse_fixes: List[Dict[str, str]] = []
    reuse_paths: List[str] = []
    remaining: List[str] = []
    for path in paths:
        base = posixpath.basename(_normalize_source_path(path))
        if base and base in cache:
            reuse_fixes.append({"path": path, "content": cache[base]})
            reuse_paths.append(path)
        else:
            remaining.append(path)
    if not reuse_fixes:
        return [], paths, []
    if job_id:
        _log(
            job_id,
            f"复用同 basename 已成功 diff → {len(reuse_paths)} 个文件 "
            f"({posixpath.basename(reuse_paths[0])} 等)",
        )
    applied, errors, _ = apply_build_fixes(
        job, reuse_fixes, build_workdir, job_id=job_id,
    )
    still_failed = list(remaining)
    for p in reuse_paths:
        if any(_apply_error_matches_path(e, p) for e in errors):
            still_failed.append(p)
    return applied, still_failed, errors


def get_build_fix_state(job_id: str) -> Dict[str, Any]:
    job = get_upgrade_job(job_id)
    if not job:
        return {"status": "unknown", "attempts": []}
    st = _get_state(job)
    build_workdir = (job.get("build_workdir") or "").strip()
    attempts = []
    for attempt in st.get("attempts") or []:
        item = dict(attempt)
        item["files_changed"] = enrich_build_fix_files(
            job, build_workdir, list(item.get("files_changed") or []),
        )
        attempts.append(item)
    return {
        "status": st.get("status", "idle"),
        "attempts": attempts,
        "completed_rounds": persisted_build_fix_round_count(job),
        "next_round": persisted_build_fix_round_count(job) + 1,
        "max_attempts": normalize_build_fix_max_attempts(
            (job.get("options") or {}).get("build_fix_max_attempts")
        ),
        "auto_fix_enabled": bool((job.get("options") or {}).get("auto_fix_build_errors")),
        "failure_triage": st.get("failure_triage") or None,
    }


_REPO_LIST_LINE_RE = re.compile(r"^([^:]+?)\s*:\s*(.+?)\s*$")
_repo_project_cache: Dict[str, Dict[str, str]] = {}
_repo_project_cache_lock = threading.Lock()
_repo_list_dot_cache: Dict[str, Dict[str, str]] = {}
_manifest_root_cache: Dict[str, str] = {}


def _parse_repo_list_dot_output(text: str) -> Tuple[str, str]:
    """Parse ``repo list .`` line → ``(project_name, checkout_path)``.

    Example::

        kernel-5.10 : MTK_CODE/quark/kernel-5.10
        → project ``MTK_CODE/quark/kernel-5.10``, checkout ``kernel-5.10``
    """
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.lower().startswith("in directory"):
            continue
        m = _REPO_LIST_LINE_RE.match(s)
        if m:
            checkout = m.group(1).strip().rstrip("/")
            project = m.group(2).strip().rstrip("/")
            return project, checkout
    return "", ""


def _io_path_is_dir(path: str, job: Dict[str, Any]) -> bool:
    p = _norm_path(path)
    if not p:
        return False
    local = _hybrid_local_path(job, p)
    if local is not None:
        try:
            return local.is_dir()
        except OSError:
            pass
    if _use_local_mount(job) and not p.startswith("/"):
        return _local_is_dir(p)
    if _build_fix_via_ssh_files(job):
        from web_app.upgrade_remote_git import is_remote_active

        if not is_remote_active():
            return False
        from web_app.upgrade_remote_git import remote_run_in_dir

        r = remote_run_in_dir("/", f"test -d {shlex.quote(normalize_linux_path(p))} && echo yes", timeout=20)
        return (r.stdout or "").strip() == "yes"
    from web_app.upgrade_remote_git import is_remote_active

    if is_remote_active() and p.startswith("/"):
        from web_app.upgrade_remote_git import remote_run_in_dir

        r = remote_run_in_dir("/", f"test -d {shlex.quote(normalize_linux_path(p))} && echo yes", timeout=20)
        if (r.stdout or "").strip() == "yes":
            return True
    if _use_local_mount(job) and p.startswith("/"):
        local = remote_abs_to_local(job, p)
        if local is not None:
            return local.is_dir()
    try:
        return Path(p).is_dir()
    except OSError:
        return False


def _run_repo_list_dot(job: Dict[str, Any], cwd: str) -> str:
    """Run ``repo list .`` in ``cwd`` (file's project directory). Prefer local mount over SSH."""
    raw = (cwd or "").strip()
    if not raw:
        return ""
    candidates = remote_path_variants(raw) if raw.replace("\\", "/").startswith("/") else [raw]
    seen: set[str] = set()
    for cand in candidates:
        norm = normalize_linux_path(_norm_path(cand)).rstrip("/")
        if not norm or norm in seen:
            continue
        seen.add(norm)
        local = _hybrid_local_path(job, norm)
        if local is not None and local.is_dir():
            try:
                cp = subprocess.run(
                    ["repo", "list", "."],
                    cwd=str(local),
                    capture_output=True,
                    text=True,
                    timeout=45,
                    check=False,
                )
                if cp.returncode == 0 and (cp.stdout or "").strip():
                    return cp.stdout
            except (OSError, subprocess.TimeoutExpired):
                pass
        if _build_fix_via_ssh_files(job):
            from web_app.upgrade_remote_git import is_remote_active, remote_run_in_dir

            if is_remote_active():
                r = remote_run_in_dir(norm, "repo list . 2>/dev/null", timeout=45)
                if r.ok and (r.stdout or "").strip():
                    return r.stdout
            continue
        from web_app.upgrade_remote_git import is_remote_active, remote_run_in_dir

        if is_remote_active() and norm.startswith("/"):
            r = remote_run_in_dir(norm, "repo list . 2>/dev/null", timeout=45)
            if r.ok and (r.stdout or "").strip():
                return r.stdout
    return ""


def _find_manifest_root(start_dir: str, job: Dict[str, Any]) -> str:
    opts = job.get("options") or {}
    job_cached = (opts.get("repo_manifest_root") or "").strip().rstrip("/")
    if job_cached:
        return job_cached
    cur = normalize_linux_path(_norm_path(start_dir)).rstrip("/")
    if not cur:
        return ""
    if cur in _manifest_root_cache:
        return _manifest_root_cache[cur]
    walk = cur
    for _ in range(16):
        if _io_path_is_dir(posixpath.join(walk, ".repo"), job):
            _manifest_root_cache[cur] = walk
            if isinstance(opts, dict):
                opts["repo_manifest_root"] = walk
            return walk
        parent = posixpath.dirname(walk)
        if not parent or parent == walk:
            break
        walk = parent
    _manifest_root_cache[cur] = ""
    return ""


def _merge_registry_entry(
    registry: Dict[str, Dict[str, str]],
    info: Dict[str, str],
) -> None:
    if not (info.get("repo_project") or info.get("repo_checkout")):
        return
    cwd = normalize_linux_path(
        (info.get("capture_cwd") or info.get("repo_root") or "").strip(),
    ).rstrip("/")
    if cwd:
        registry[cwd] = dict(info)
    repo_root = (info.get("repo_root") or "").strip()
    if repo_root:
        registry[normalize_linux_path(repo_root).rstrip("/")] = dict(info)


def capture_repo_project_for_file_path(
    job: Dict[str, Any],
    abs_path: str,
    build_workdir: str = "",
) -> Dict[str, str]:
    """Run ``repo list .`` in the error file's parent directory (after path normalize)."""
    del build_workdir
    path = _norm_path(abs_path)
    if not path:
        return {}
    parent = posixpath.dirname(path.rstrip("/"))
    if not parent:
        return {}
    info = capture_repo_project_at_cwd(job, parent)
    if info.get("repo_project") or info.get("repo_checkout"):
        return dict(info)
    return {}


def persist_repo_project_registry(
    job_id: str,
    registry: Dict[str, Dict[str, str]],
) -> None:
    job = get_upgrade_job(job_id) or {}
    opts = dict(job.get("options") or {})
    opts["repo_project_registry"] = registry
    update_upgrade_job(job_id, options=opts)


def ensure_repo_project_captured_for_path(
    job_id: str,
    job: Dict[str, Any],
    abs_path: str,
    build_workdir: str = "",
) -> Dict[str, str]:
    """Before modifying a file: ``repo list .`` in its project dir, save to registry."""
    from web_app.upgrade_staging import resolve_remote_abs_for_job

    ap = resolve_remote_abs_for_job(job, abs_path, build_workdir=build_workdir) or _norm_path(abs_path)
    saved = lookup_saved_repo_project(job, ap)
    if saved.get("repo_project") or saved.get("repo_checkout"):
        return saved
    info = capture_repo_project_for_file_path(job, ap, build_workdir)
    if not (info.get("repo_project") or info.get("repo_checkout")):
        return {}
    registry = dict((job.get("options") or {}).get("repo_project_registry") or {})
    _merge_registry_entry(registry, info)
    if job_id:
        persist_repo_project_registry(job_id, registry)
        fresh = get_upgrade_job(job_id) or job
        if isinstance(fresh.get("options"), dict):
            job["options"] = dict(fresh["options"])
        project = (info.get("repo_project") or info.get("repo_checkout") or "").strip()
        if project:
            _log(job_id, f"repo list . 已解析仓名: {project}（目录 {info.get('capture_cwd') or ''}）")
    return info


def ensure_repo_project_captured_for_paths(
    job_id: str,
    job: Dict[str, Any],
    paths: List[str],
    build_workdir: str = "",
) -> None:
    """One ``repo list .`` per unique parent directory of error files."""
    t0 = time.monotonic()
    pending_dirs: set[str] = set()
    for raw in paths:
        p = _norm_path((raw or "").strip())
        if not p or lookup_saved_repo_project(job, p).get("repo_project"):
            continue
        parent = posixpath.dirname(p.rstrip("/"))
        if not parent:
            continue
        dkey = normalize_linux_path(parent).rstrip("/").lower()
        if dkey:
            pending_dirs.add(dkey)
    if job_id and pending_dirs:
        _log(
            job_id,
            f"repo 解析: {len(pending_dirs)} 个唯一父目录待执行 repo list ."
            f"（来自 {len(paths)} 条报错路径）",
        )
    seen_dirs: set[str] = set()
    for raw in paths:
        p = _norm_path((raw or "").strip())
        if not p:
            continue
        if lookup_saved_repo_project(job, p).get("repo_project"):
            continue
        parent = posixpath.dirname(p.rstrip("/"))
        if not parent:
            continue
        dkey = normalize_linux_path(parent).rstrip("/").lower()
        if not dkey or dkey in seen_dirs:
            continue
        seen_dirs.add(dkey)
        ensure_repo_project_captured_for_path(job_id, job, p, build_workdir)
    if job_id:
        elapsed = time.monotonic() - t0
        _log(job_id, f"repo 工程解析完成（{elapsed:.1f}s）")


def repo_capture_dirs_for_job(
    job: Dict[str, Any],
    options: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Directories where code will be modified first — run ``repo list .`` in each."""
    options = options or job.get("options") or {}
    dirs: List[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        p = normalize_linux_path(_norm_path((raw or "").strip())).rstrip("/")
        if not p or p == "." or p in seen:
            return
        seen.add(p)
        dirs.append(p)

    add(job.get("target_repo_dir") or "")
    return dirs


def lookup_saved_repo_project(job: Dict[str, Any], abs_path: str) -> Dict[str, str]:
    """Find pre-captured ``repo list`` info whose ``repo_root`` contains ``abs_path``."""
    registry = (job.get("options") or {}).get("repo_project_registry") or {}
    if not isinstance(registry, dict) or not registry:
        return {}
    path = _strip_root_label_prefix(_norm_path(abs_path)).replace("\\", "/").rstrip("/")
    if not path:
        return {}
    best: Dict[str, str] = {}
    best_len = -1
    for _key, info in registry.items():
        if not isinstance(info, dict):
            continue
        root = _norm_path(info.get("repo_root") or "").replace("\\", "/").rstrip("/")
        checkout = (info.get("repo_checkout") or "").strip().rstrip("/").replace("\\", "/")
        matched = False
        match_len = 0
        if root and (path == root or path.startswith(root + "/")):
            matched = True
            match_len = len(root)
        elif checkout:
            co = checkout.lstrip("/")
            if path == co or path.startswith(co + "/") or path.endswith("/" + co) or f"/{co}/" in f"/{path}/":
                matched = True
                match_len = len(co)
        if matched and match_len > best_len:
            best_len = match_len
            best = dict(info)
    return best


def repo_display_name(job: Dict[str, Any], repo_root_or_path: str) -> str:
    """Human-readable repo name for UI / commit summary."""
    info = lookup_saved_repo_project(job, repo_root_or_path)
    project = (info.get("repo_project") or "").strip()
    if project:
        return project
    checkout = (info.get("repo_checkout") or "").strip().rstrip("/")
    if checkout:
        return checkout.rsplit("/", 1)[-1]
    return ""


def capture_repo_project_at_cwd(job: Dict[str, Any], cwd: str) -> Dict[str, str]:
    """Run ``repo list .`` at ``cwd`` (typically the error file's parent directory)."""
    norm = normalize_linux_path(_norm_path(cwd)).rstrip("/")
    if not norm:
        return {}
    cache_key = norm.lower()
    if cache_key in _repo_list_dot_cache:
        return dict(_repo_list_dot_cache[cache_key])
    out = _run_repo_list_dot(job, norm)
    project, checkout = _parse_repo_list_dot_output(out)
    if not project and not checkout:
        _repo_list_dot_cache[cache_key] = {}
        return {}
    manifest_root = _find_manifest_root(norm, job)
    repo_root = ""
    if manifest_root and checkout:
        repo_root = normalize_linux_path(f"{manifest_root.rstrip('/')}/{checkout.lstrip('/')}")
    elif manifest_root and project:
        repo_root = manifest_root
    result = {
        "repo_project": project,
        "repo_checkout": checkout,
        "repo_root": repo_root,
        "repo_manifest_root": manifest_root,
        "capture_cwd": norm,
    }
    _repo_list_dot_cache[cache_key] = result
    return dict(result)


def capture_repo_project_registry(
    job: Dict[str, Any],
    dirs: List[str],
) -> Dict[str, Dict[str, str]]:
    """Capture ``repo list .`` in each target directory (must be inside a repo project)."""
    registry: Dict[str, Dict[str, str]] = {}
    existing = (job.get("options") or {}).get("repo_project_registry") or {}
    if isinstance(existing, dict):
        for k, v in existing.items():
            if isinstance(v, dict):
                registry[k] = dict(v)
    seen_cwd: set[str] = set()
    for raw in dirs:
        cwd = normalize_linux_path(_norm_path(raw)).rstrip("/")
        if not cwd or cwd in seen_cwd:
            continue
        seen_cwd.add(cwd)
        info = capture_repo_project_at_cwd(job, cwd)
        if not any(info.get(k) for k in ("repo_project", "repo_checkout", "repo_root")):
            continue
        info = dict(info)
        info["capture_cwd"] = cwd
        _merge_registry_entry(registry, info)
    return registry


def _rel_path_for_display(
    abs_path: str,
    repo_root: str,
    repo_checkout: str,
    raw_path: str,
) -> str:
    """Short repo-relative path for UI (avoid truncating long absolute paths)."""
    ap = _norm_path(abs_path).rstrip("/")
    rr = _norm_path(repo_root).rstrip("/")
    if ap and rr and (ap == rr or ap.startswith(rr + "/")):
        return ap[len(rr) + 1 :] if ap.startswith(rr + "/") else "."
    rp = _strip_root_label_prefix(raw_path)
    co = (repo_checkout or "").strip().rstrip("/")
    if co and rp:
        if rp == co:
            return posixpath.basename(rp) or rp
        if rp.startswith(co + "/"):
            return rp[len(co) + 1 :]
        return rp
    if rp and not rp.startswith("/") and len(rp) < 260:
        return rp
    if ap:
        return ap.rsplit("/", 1)[-1]
    return rp


def resolve_repo_project_for_path(
    job: Dict[str, Any],
    abs_path: str,
    build_workdir: str = "",
) -> Dict[str, str]:
    """Resolve Android repo project via ``repo list .`` under the file directory."""
    path = _norm_path(abs_path)
    if not path:
        return {}
    cache_key = path.lower()
    with _repo_project_cache_lock:
        cached = _repo_project_cache.get(cache_key)
        if cached is not None:
            return dict(cached)

    saved = lookup_saved_repo_project(job, path)
    if saved.get("repo_project") or saved.get("repo_checkout"):
        result = {
            "repo_project": saved.get("repo_project") or "",
            "repo_checkout": saved.get("repo_checkout") or "",
            "repo_root": saved.get("repo_root") or "",
            "repo_manifest_root": saved.get("repo_manifest_root") or "",
        }
        with _repo_project_cache_lock:
            _repo_project_cache[cache_key] = result
        return result

    info = capture_repo_project_for_file_path(job, path, build_workdir)
    result = {
        "repo_project": info.get("repo_project") or "",
        "repo_checkout": info.get("repo_checkout") or "",
        "repo_root": info.get("repo_root") or "",
        "repo_manifest_root": info.get("repo_manifest_root") or "",
    }
    with _repo_project_cache_lock:
        _repo_project_cache[cache_key] = result
    return result


def enrich_build_fix_files(
    job: Dict[str, Any],
    build_workdir: str,
    files: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in files:
        row = dict(item)
        if not row.get("repo_project"):
            abs_path = row.get("abs_path") or row.get("path") or ""
            row.update(resolve_repo_project_for_path(job, abs_path, build_workdir))
        abs_path = row.get("abs_path") or row.get("path") or ""
        rel = _rel_path_for_display(
            abs_path,
            row.get("repo_root") or "",
            row.get("repo_checkout") or "",
            row.get("path") or "",
        )
        row["rel_path"] = rel
        row["path_full"] = _norm_path(abs_path) or _strip_root_label_prefix(row.get("path") or "")
        out.append(row)
    return out


def _fix_equivalence_key(raw_path: str) -> str:
    """Group kernel vs vendor paths that fix the same logical source (e.g. touchscreen)."""
    p = _norm_path(raw_path).lstrip("/")
    base = posixpath.basename(p)
    marker = "drivers/input/touchscreen/"
    if marker in p:
        rest = p.split(marker, 1)[1]
        parts = [x for x in rest.split("/") if x and x != ".."]
        if len(parts) >= 2:
            return f"touchscreen:{parts[0]}/{base}"
    if "vendor/transsion/touchscreen/" in p:
        rest = p.split("vendor/transsion/touchscreen/", 1)[1]
        parts = [x for x in rest.split("/") if x]
        if len(parts) >= 3:
            return f"touchscreen:{parts[2]}/{base}"
    return p


def _read_text_at_abs(job: Dict[str, Any], abs_path: str) -> str:
    if _build_fix_via_ssh_files(job):
        from web_app.upgrade_remote_git import remote_read_absolute
        return remote_read_absolute(abs_path)
    if _use_local_mount(job):
        return _local_read_text(abs_path)
    return Path(abs_path).read_text(encoding="utf-8", errors="replace")


def _file_location_for_abs(
    job: Dict[str, Any], abs_path: str, rel_path: str, build_workdir: str,
) -> FileLocation:
    loc = resolve_file_location(job, rel_path, build_workdir)
    if loc:
        return loc
    root = build_workdir if build_workdir else ""
    display = rel_path if not root else f"[build_workdir] {rel_path}"
    return FileLocation(abs_path=abs_path, display_path=display, root="build_workdir")


def _record_applied_fix(
    *,
    loc: FileLocation,
    job: Dict[str, Any],
    build_workdir: str,
    before: str,
    after: str,
    raw_content: str,
    strategy: str,
    processed_diff: str = "",
    external: List[Any],
    job_id: str = "",
) -> Dict[str, Any]:
    if job_id:
        ensure_repo_project_captured_for_path(job_id, job, loc.abs_path, build_workdir)
    diff = make_unified_diff(loc.display_path, before, after) if before else ""
    in_target = _is_under_target_repo(loc.abs_path, job, build_workdir or "")
    row = {
        "path": loc.display_path,
        "abs_path": loc.abs_path,
        "root": loc.root,
        "in_target_repo": in_target,
        "must_modify_target": in_target and not external,
        "strategy": strategy,
        "llm_fix_content": raw_content,
        "processed_diff": processed_diff or normalize_llm_diff(raw_content),
        "diff": _trim(diff, 80_000),
        "bytes_before": len(before),
        "bytes_after": len(after),
    }
    row.update(resolve_repo_project_for_path(job, loc.abs_path, build_workdir))
    return row


def _propagate_fix_to_siblings(
    job: Dict[str, Any],
    *,
    loc: FileLocation,
    raw_path: str,
    processed_diff: str,
    build_workdir: str,
    external: List[Any],
    fixed_identities: set[str],
    job_id: str = "",
) -> List[Dict[str, Any]]:
    if not processed_diff or not build_workdir:
        return []
    sibling_rows = try_apply_to_sibling_files(
        source_rel=raw_path,
        source_abs=loc.abs_path,
        processed_diff=processed_diff,
        build_workdir=build_workdir,
        read_file=lambda p: _read_text_at_abs(job, p),
        file_identity_key=lambda p: _file_identity_key(job, p),
        already_fixed_identities=fixed_identities,
    )
    out: List[Dict[str, Any]] = []
    for row in sibling_rows:
        sib_loc = _file_location_for_abs(
            job, row["abs_path"], row["rel_path"], build_workdir,
        )
        krel = _kernel_tree_rel(row["rel_path"], sib_loc, job, build_workdir)
        try:
            before_sib = _read_at_location(job, sib_loc)
        except FileNotFoundError:
            before_sib = ""
        if _is_upstream_kernel_readonly(krel, job=job, content=before_sib):
            continue
        _write_at_location(job, sib_loc, row["content"])
        if job_id:
            try:
                from web_app.upgrade_staging import stage_path_for_job

                stage_path_for_job(
                    job_id,
                    job,
                    sib_loc.abs_path,
                    build_workdir=build_workdir or "",
                    from_build_fix=True,
                )
            except Exception as exc:
                _log(job_id, f"git add 失败 ({sib_loc.display_path}): {exc}")
        out.append(_record_applied_fix(
            loc=sib_loc,
            job=job,
            build_workdir=build_workdir,
            before=before_sib,
            after=row["content"],
            raw_content=row.get("llm_fix_content") or processed_diff,
            strategy=row.get("strategy") or "sibling_diff",
            processed_diff=row.get("processed_diff") or processed_diff,
            external=external,
            job_id=job_id,
        ))
        fixed_identities.add(_file_identity_key(job, sib_loc.abs_path))
        if job_id:
            _log(
                job_id,
                f"同 basename 扩散写回: {row['rel_path']} ({row.get('strategy', 'sibling')})",
            )
    return out


def _try_collision_rename_auto_fix(
    job_id: str,
    job: Dict[str, Any],
    contexts: List[Dict[str, Any]],
    diagnostic_chains: List[Dict[str, Any]],
    build_workdir: str,
) -> Optional[List[Dict[str, Any]]]:
    """Deterministic rename when vendor static symbol collides with a kernel macro."""
    if len(contexts) != 1 or not diagnostic_chains:
        return None
    ctx = contexts[0]
    fix_path = fix_path_for_llm(ctx.get("fix_path") or ctx.get("path") or "")
    chains = [
        c for c in chains_matching_file(diagnostic_chains, fix_path)
        if c.get("chain_type") == "kernel_macro_collision" and c.get("symbol")
    ]
    if not chains:
        return None
    symbol = str(chains[0].get("symbol") or "")
    path = ctx.get("path") or fix_path
    loc = resolve_file_location(job, path, build_workdir)
    if not loc:
        return None
    try:
        before = _read_at_location(job, loc)
    except FileNotFoundError:
        return None
    after = try_rename_kernel_macro_collision(before, symbol)
    if not after or after == before:
        return None
    from web_app.build_fix_diagnostics import _pick_collision_rename
    new_name = _pick_collision_rename(symbol, before)
    _log(
        job_id,
        f"诊断链 kernel_macro_collision: 自动 rename `{symbol}` → `{new_name}`"
        f"（含全部引用，跳过 LLM）",
    )
    external = _search_roots(job, build_workdir)
    _write_at_location(job, loc, after)
    if job_id:
        try:
            from web_app.upgrade_staging import stage_path_for_job

            stage_path_for_job(
                job_id,
                job,
                loc.abs_path,
                build_workdir=build_workdir or "",
                from_build_fix=True,
            )
        except Exception as exc:
            _log(job_id, f"登记待提交失败 ({loc.display_path}): {exc}")
    row = _record_applied_fix(
        loc=loc,
        job=job,
        build_workdir=build_workdir,
        before=before,
        after=after,
        raw_content=f"auto-rename {symbol} -> {new_name}",
        strategy="collision_rename",
        external=external,
        job_id=job_id,
    )
    siblings = _propagate_fix_to_siblings(
        job,
        loc=loc,
        raw_path=fix_path,
        processed_diff=row.get("processed_diff") or "",
        build_workdir=build_workdir,
        external=external,
        fixed_identities={_file_identity_key(job, loc.abs_path)},
        job_id=job_id,
    )
    return [row, *siblings]


def apply_build_fixes(
    job: Dict[str, Any],
    fixes: List[Dict[str, str]],
    build_workdir: str = "",
    *,
    job_id: str = "",
) -> Tuple[List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
    """Write LLM fixes. Prefer changes outside merge target; target only if no alternative.

    Returns (applied, errors, skipped_target_fixes).
    """
    applied: List[Dict[str, Any]] = []
    errors: List[str] = []
    skipped_target: List[Dict[str, Any]] = []
    pending: List[Tuple[Dict[str, str], FileLocation, str]] = []
    pending_identity: Dict[str, Tuple[Dict[str, str], FileLocation, str]] = {}

    for fix in fixes:
        raw_path = sanitize_llm_fix_path(fix.get("path") or "")
        content = fix.get("content")
        if not raw_path or content is None:
            continue
        if raw_path == "unknown":
            errors.append("LLM 返回未知文件路径 (unknown)")
            continue
        loc = resolve_file_location(job, raw_path, build_workdir, avoid_target_repo=True)
        if not loc:
            loc = resolve_file_location(job, raw_path, build_workdir, avoid_target_repo=False)
        if not loc:
            errors.append(f"无法定位源文件: {raw_path}")
            continue
        identity = _file_identity_key(job, loc.abs_path)
        if identity in pending_identity:
            skipped_target.append({
                "path": loc.display_path,
                "abs_path": loc.abs_path,
                "reason": "软链接/硬链接指向同一文件，本批次仅应用一次修复",
            })
            if job_id:
                prev = pending_identity[identity][1].display_path
                _log(
                    job_id,
                    f"跳过重复 fix 目标: {loc.display_path}（与 {prev} 为同一文件）",
                )
            continue
        pending_identity[identity] = (fix, loc, raw_path)

    pending = list(pending_identity.values())

    external = [
        (f, loc, rp) for f, loc, rp in pending
        if not _is_under_target_repo(loc.abs_path, job, build_workdir)
    ]
    external_keys = {_fix_equivalence_key(rp) for _, _, rp in external}

    to_apply: List[Tuple[Dict[str, str], FileLocation, str]] = []
    seen_identity: set[str] = set()
    for fix, loc, raw_path in external + [
        (f, loc, rp) for f, loc, rp in pending
        if _is_under_target_repo(loc.abs_path, job, build_workdir)
    ]:
        identity = _file_identity_key(job, loc.abs_path)
        if identity in seen_identity:
            continue
        is_internal = _is_under_target_repo(loc.abs_path, job, build_workdir)
        eq_key = _fix_equivalence_key(raw_path)
        if is_internal and eq_key in external_keys:
            skipped_target.append({
                "path": loc.display_path,
                "abs_path": loc.abs_path,
                "reason": f"同一报错已有合入目标路径外替代方案（key={eq_key}），跳过 kernel 副本",
            })
            continue
        seen_identity.add(identity)
        to_apply.append((fix, loc, raw_path))

    fixed_identities: set[str] = set()

    for fix, loc, raw_path in to_apply:
        try:
            before = _read_at_location(job, loc)
        except FileNotFoundError:
            before = ""
        krel = _kernel_tree_rel(raw_path, loc, job, build_workdir)
        if _is_upstream_kernel_readonly(krel, job=job, content=before):
            errors.append(f"{loc.display_path}: {_upstream_readonly_reason(krel, job)}")
            continue
        raw_content = fix["content"]
        result: ApplyResult = process_llm_fix_content(before, raw_content)
        if result.error or result.content is None:
            detail = result.error or "无法解析修复内容"
            if job_id and result.strategy == "failed" and "误删" in detail:
                _log(job_id, f"diff 预检/校验拒绝 ({loc.display_path}): {detail[:200]}")
            errors.append(_format_apply_error(loc.display_path, detail, before))
            continue
        content = result.content
        if content == before:
            applied.append(_record_applied_fix(
                loc=loc,
                job=job,
                build_workdir=build_workdir,
                before=before,
                after=content,
                raw_content=raw_content,
                strategy="already_applied",
                processed_diff=result.processed_diff,
                external=external,
                job_id=job_id,
            ))
            fixed_identities.add(_file_identity_key(job, loc.abs_path))
            continue
        _write_at_location(job, loc, content)
        if job_id:
            try:
                from web_app.upgrade_staging import stage_path_for_job

                stage_path_for_job(
                    job_id,
                    job,
                    loc.abs_path,
                    build_workdir=build_workdir or "",
                    from_build_fix=True,
                )
            except Exception as exc:
                _log(job_id, f"git add 失败 ({loc.display_path}): {exc}")
        applied.append(_record_applied_fix(
            loc=loc,
            job=job,
            build_workdir=build_workdir,
            before=before,
            after=content,
            raw_content=raw_content,
            strategy=result.strategy,
            processed_diff=result.processed_diff,
            external=external,
            job_id=job_id,
        ))
        fixed_identities.add(_file_identity_key(job, loc.abs_path))
        if job_id and result.strategy != "already_applied":
            _log(job_id, f"diff 写回 ({result.strategy}): {loc.display_path}")
        diff_for_siblings = result.processed_diff or normalize_llm_diff(raw_content)
        applied.extend(_propagate_fix_to_siblings(
            job,
            loc=loc,
            raw_path=raw_path,
            processed_diff=diff_for_siblings,
            build_workdir=build_workdir,
            external=external,
            fixed_identities=fixed_identities,
            job_id=job_id,
        ))

    if not applied and fixes:
        if not errors:
            errors.append("未能将 LLM 输出映射到可写回的源文件")
    return applied, errors, skipped_target


def _resolve_build_errors_with_wait(
    job_id: str,
    *,
    label: str = "",
    **kwargs: Any,
) -> Tuple[List[Dict[str, str]], str]:
    """Call LLM with periodic heartbeat logs so long waits are visible."""
    done = threading.Event()
    timeout_hint = BUILD_FIX_LLM_TIMEOUT
    minutes_hint = max(1, (timeout_hint + 59) // 60)

    def _heartbeat() -> None:
        t0 = time.monotonic()
        while not done.wait(30):
            elapsed = int(time.monotonic() - t0)
            _log(
                job_id,
                f"LLM 仍在分析{label}… 已等待 {elapsed}s（单次最长约 {minutes_hint} 分钟）",
            )

    th = threading.Thread(target=_heartbeat, daemon=True)
    th.start()
    from web_app.prompt_loader import set_session_retry_hint

    job = get_upgrade_job(job_id) or {}
    set_session_retry_hint(str((job.get("options") or {}).get("build_fix_user_hint") or ""))
    try:
        return resolve_build_errors_via_llm(wait_log=lambda m: _log(job_id, m), **kwargs)
    finally:
        done.set()
        set_session_retry_hint("")


def _context_fix_path(ctx: Dict[str, Any]) -> str:
    return (ctx.get("fix_path") or ctx.get("path") or "").strip()


def _resolve_llm_per_file_contexts(
    job_id: str,
    *,
    contexts: List[Dict[str, Any]],
    context_errors: List[Dict[str, Any]],
    excerpt: str,
    job: Dict[str, Any],
    build_workdir: str,
    search_roots: List[Dict[str, str]],
    diagnostic_chains: Optional[List[Dict[str, Any]]] = None,
    readonly_note_contexts: Optional[List[Dict[str, Any]]] = None,
    apply_feedback: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, str]], str, List[str]]:
    """Call LLM once per file context (skips batch when few unique files)."""
    all_fixes: List[Dict[str, str]] = []
    summaries: List[str] = []
    errors: List[str] = []
    for ctx in contexts:
        path = _context_fix_path(ctx)
        if not path:
            continue
        if _is_readonly_kernel_fix_path(path):
            _log(job_id, f"跳过只读内核头 LLM 目标: {path}（应在 vendor note 处修复）")
            continue
        _log(job_id, f"单文件 LLM: {path}")
        try:
            fixes, summary = _resolve_build_errors_with_wait(
                job_id,
                label=f"单文件 {path}",
                errors=context_errors,
                log_excerpt=excerpt,
                file_contexts=[ctx],
                target_repo_dir=job.get("target_repo_dir") or "",
                build_workdir=build_workdir,
                search_roots=search_roots,
                diagnostic_chains=diagnostic_chains,
                readonly_note_contexts=readonly_note_contexts,
                apply_feedback=apply_feedback,
                focus_paths=[path],
            )
            fixes = _filter_llm_fix_targets(job, fixes, build_workdir, job_id=job_id)
            all_fixes.extend(fixes)
            if summary:
                summaries.append(summary)
        except Exception as exc:
            msg = f"单文件 LLM 失败 ({path}): {exc}"
            _log(job_id, msg)
            errors.append(msg)
    combined = "; ".join(summaries[:3]) if summaries else "单文件 LLM 修复"
    return all_fixes, combined, errors


def run_build_fix_attempt(
    job_id: str,
    log_path: str,
    attempt: int,
) -> Dict[str, Any]:
    """Parse build log, ask LLM, apply fixes. Caller must hold remote_job_context if remote."""
    job = get_upgrade_job(job_id)
    if not job:
        return {"applied": False, "error": "任务不存在"}

    if not is_llm_configured():
        return {"applied": False, "error": "LLM 未配置 API Key"}

    build_workdir = (job.get("build_workdir") or "").strip()
    log_text = read_log_for_build_fix(log_path)
    if not log_text:
        return {"applied": False, "error": f"无法读取编译日志: {log_path}"}

    errors, excerpt, diagnostic_chains = parse_build_errors(log_text)
    raw_error_count = len(errors)
    state = _get_state(job)
    state["status"] = "running"
    record: Dict[str, Any] = {
        "attempt": attempt,
        "started_at": datetime.now().isoformat(),
        "build_log_file": log_path,
        "errors": errors[:_MAX_ERRORS],
        "errors_parsed": raw_error_count,
        "error_excerpt": _trim(excerpt, 40_000),
        "files_changed": [],
        "llm_summary": "",
        "applied": False,
        "error": "",
    }
    state.setdefault("attempts", []).append(record)
    _save_state(job_id, job, state)

    _log(
        job_id,
        f"第 {attempt} 轮编译错误修复：日志解析 {raw_error_count} 条，待处理 {len(errors)} 条",
    )

    mount_err = validate_hybrid_build_fix_mounts(job, build_workdir)
    if mount_err:
        record["error"] = mount_err
        record["finished_at"] = datetime.now().isoformat()
        state["status"] = "failed"
        _save_state(job_id, get_upgrade_job(job_id) or job, state)
        _log(job_id, f"本地映射预检失败: {mount_err}")
        return {"applied": False, "error": mount_err, "attempt": attempt}

    if errors and _use_local_mount(job):
        resolved, total, unresolved = probe_error_file_resolution(job, errors, build_workdir)
        if total and resolved == 0:
            anchor = _build_root_anchor(job, build_workdir)
            msg = (
                f"编译报错 {total} 个文件均无法在本地映射定位（anchor={anchor!r}），"
                f"示例: {'; '.join(unresolved[:2])}。"
                "请确认「服务器映射路径」与编译目录下 vnd 树一致，且该进程能访问 Z:/UNC。"
            )
            record["error"] = msg
            record["finished_at"] = datetime.now().isoformat()
            state["status"] = "failed"
            _save_state(job_id, get_upgrade_job(job_id) or job, state)
            _log(job_id, msg)
            return {"applied": False, "error": msg, "attempt": attempt}
        if resolved < total:
            _log(job_id, f"路径预检: {resolved}/{total} 个报错文件已在本地映射命中")

    if not errors:
        msg = (
            "编译失败但过滤后无可处理 error"
            + (f"（日志解析到 {raw_error_count} 条 gcc error）" if raw_error_count else "（日志未解析到 gcc error 行）")
            + "；请查看编译日志中的 FAILED/split_build_helper 或其它未命中报错"
        )
        record["error"] = msg
        record["finished_at"] = datetime.now().isoformat()
        state["status"] = "failed"
        _save_state(job_id, get_upgrade_job(job_id) or job, state)
        _log(job_id, msg)
        return {"applied": False, "error": msg, "attempt": attempt}

    _log(job_id, f"待处理 {len(errors)} 条编译诊断（含 note），准备解析 repo 工程与文件上下文")
    error_paths = [str(e.get("file") or "").strip() for e in errors if e.get("file")]
    if error_paths:
        ensure_repo_project_captured_for_paths(job_id, job, error_paths, build_workdir)
        job = get_upgrade_job(job_id) or job

    context_errors = _sort_errors_for_context(list(errors))
    seen_ctx: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for err in context_errors:
        loc = resolve_file_location(job, err.get("file", ""), build_workdir)
        line_no = int(err.get("line") or 0)
        kind = (err.get("kind") or "").lower()
        if loc:
            key = f"{_file_identity_key(job, loc.abs_path)}:{line_no}:{kind}"
        else:
            key = f"{_normalize_source_path(err.get('file', ''))}:{line_no}:{kind}"
        if key and key in seen_ctx:
            continue
        if key:
            seen_ctx.add(key)
        deduped.append(err)
    context_errors = deduped

    if diagnostic_chains:
        _log(
            job_id,
            f"已识别 {len(diagnostic_chains)} 条诊断链"
            f"（类型: {', '.join(c.get('chain_type', '?') for c in diagnostic_chains[:3])}）",
        )

    _log(job_id, "正在读取报错文件上下文…")
    contexts = _collect_file_contexts(
        job, context_errors, build_workdir, job_id=job_id,
        diagnostic_chains=diagnostic_chains,
    )
    readonly_note_contexts = _collect_readonly_note_contexts(
        job, context_errors, build_workdir,
    )
    if contexts:
        n_alias = sum(len(c.get("symlink_aliases") or []) for c in contexts)
        ctx_paths = ", ".join(
            f"{c.get('fix_path') or c.get('path', '?')}:{c.get('line', '?')}" for c in contexts[:4]
        )
        extra = f"（含 {n_alias} 个软链接别名已合并）" if n_alias else ""
        _log(job_id, f"已加载 {len(contexts)} 个唯一文件上下文{extra}: {ctx_paths}")
    elif errors:
        _log(job_id, "警告：未能从合入仓库/编译目录定位报错文件，将仅依赖日志片段")

    auto_applied = _try_collision_rename_auto_fix(
        job_id, job, contexts, diagnostic_chains or [], build_workdir,
    )
    if auto_applied:
        record["files_changed"] = auto_applied
        record["llm_summary"] = (
            f"工具侧自动 rename 消除内核宏冲突（{auto_applied[0].get('strategy', 'collision_rename')}）"
        )
        record["applied"] = True
        record["finished_at"] = datetime.now().isoformat()
        state["status"] = "idle"
        _save_state(job_id, get_upgrade_job(job_id) or job, state)
        paths = ", ".join(x["path"] for x in auto_applied[:3])
        _log(job_id, f"AI 修复已写回 {len(auto_applied)} 个文件（自动 rename）: {paths}")
        return {
            "applied": True,
            "attempt": attempt,
            "summary": record["llm_summary"],
            "files_changed": auto_applied,
        }

    search_roots = [
        {"name": n, "path": p} for n, p in _search_roots(job, build_workdir)
    ]

    timeout_min = max(1, (BUILD_FIX_LLM_TIMEOUT + 59) // 60)
    _log(
        job_id,
        f"正在调用 LLM 分析编译报错（单次最长约 {timeout_min} 分钟，"
        f"可通过 GKI_BUILD_FIX_LLM_TIMEOUT 调整）…",
    )
    all_applied: List[Dict[str, Any]] = []
    apply_errors: List[str] = []
    skipped_target: List[Dict[str, Any]] = []
    summary = ""
    fixes: List[Dict[str, str]] = []

    llm_common = dict(
        errors=context_errors,
        log_excerpt=excerpt,
        target_repo_dir=job.get("target_repo_dir") or "",
        build_workdir=build_workdir,
        search_roots=search_roots,
        diagnostic_chains=diagnostic_chains,
        readonly_note_contexts=readonly_note_contexts,
    )

    if contexts and len(contexts) <= 2:
        _log(job_id, f"仅 {len(contexts)} 个唯一文件上下文，跳过批量 LLM，按单文件调用")
        fixes, summary, llm_errors = _resolve_llm_per_file_contexts(
            job_id,
            contexts=contexts,
            context_errors=context_errors,
            excerpt=excerpt,
            job=job,
            build_workdir=build_workdir,
            search_roots=search_roots,
            diagnostic_chains=diagnostic_chains,
            readonly_note_contexts=readonly_note_contexts,
        )
        apply_errors.extend(llm_errors)
        if not fixes and llm_errors and all(
            _is_llm_timeout_message(e) for e in llm_errors
        ):
            record["error"] = "; ".join(llm_errors[:2])
            record["finished_at"] = datetime.now().isoformat()
            state["status"] = "failed"
            _save_state(job_id, get_upgrade_job(job_id) or job, state)
            _log(job_id, f"LLM 修复失败: {record['error']}")
            return {"applied": False, "error": record["error"], "attempt": attempt}
    else:
        try:
            fixes, summary = _resolve_build_errors_with_wait(
                job_id,
                label="编译报错",
                file_contexts=contexts,
                **llm_common,
            )
        except Exception as exc:
            if _is_llm_timeout_message(str(exc)) and contexts:
                _log(job_id, f"批量 LLM 超时: {exc}，改按单文件重试")
                fixes, summary, llm_errors = _resolve_llm_per_file_contexts(
                    job_id,
                    contexts=contexts,
                    context_errors=context_errors,
                    excerpt=excerpt,
                    job=job,
                    build_workdir=build_workdir,
                    search_roots=search_roots,
                    diagnostic_chains=diagnostic_chains,
                    readonly_note_contexts=readonly_note_contexts,
                )
                apply_errors.extend(llm_errors)
                if not fixes:
                    record["error"] = str(exc)
                    record["finished_at"] = datetime.now().isoformat()
                    state["status"] = "failed"
                    _save_state(job_id, get_upgrade_job(job_id) or job, state)
                    _log(job_id, f"LLM 修复失败: {exc}")
                    return {"applied": False, "error": str(exc), "attempt": attempt}
            else:
                record["error"] = str(exc)
                record["finished_at"] = datetime.now().isoformat()
                state["status"] = "failed"
                _save_state(job_id, get_upgrade_job(job_id) or job, state)
                _log(job_id, f"LLM 修复失败: {exc}")
                return {"applied": False, "error": str(exc), "attempt": attempt}

    if summary:
        _log(
            job_id,
            f"LLM 返回修复方案: {summary[:120]}{'…' if len(summary) > 120 else ''}",
        )
        record["llm_summary"] = summary

    fixes = _filter_llm_fix_targets(job, fixes, build_workdir, job_id=job_id)

    applied, apply_errors, skipped_target = apply_build_fixes(
        job, fixes, build_workdir, job_id=job_id,
    )
    all_applied.extend(applied)
    apply_errors = _filter_errors_exclude_fixed_identities(
        job, apply_errors, all_applied, build_workdir,
    )
    if applied:
        paths = ", ".join(x["path"] for x in applied[:3])
        _log(job_id, f"已写回 {len(applied)} 个文件: {paths}")
    if apply_errors:
        preview = "; ".join(e.split("\n")[0][:160] for e in apply_errors[:2])
        _log(job_id, f"写回问题 ({len(apply_errors)}): {preview}")
        _log(job_id, "将尝试 diff 复用与单文件 LLM 重试（不再发起第二轮大批量 LLM）")
    apply_feedback: Optional[List[str]] = apply_errors or None

    failed_paths = _dedupe_paths_by_file_identity(
        job, _extract_failed_paths(apply_errors), build_workdir,
    )
    failed_paths = _expand_failed_paths_for_retry(
        job, failed_paths, context_errors, build_workdir,
    )
    basename_cache = _basename_fix_cache(all_applied)
    if failed_paths and basename_cache:
        reused, failed_paths, reuse_errors = _try_reuse_basename_fixes(
            job, failed_paths, basename_cache, build_workdir, job_id=job_id,
        )
        if reused:
            all_applied.extend(reused)
            apply_errors = _filter_errors_exclude_fixed_identities(
                job, apply_errors, all_applied, build_workdir,
            )
            paths = ", ".join(x["path"] for x in reused[:3])
            _log(job_id, f"basename 复用写回 {len(reused)} 个文件: {paths}")
            for row in reused:
                apply_errors = [
                    e for e in apply_errors
                    if not _apply_error_matches_path(e, fix_path_for_llm(row.get("path") or ""))
                ]
        apply_errors.extend(reuse_errors)

    if apply_errors and failed_paths:
        _log(job_id, f"仍有 {len(failed_paths)} 个文件 diff 未应用，启动单文件 LLM 重试…")

    def _fixed_identity_keys() -> set[str]:
        keys: set[str] = set()
        for row in all_applied:
            ap = row.get("abs_path") or ""
            if ap:
                keys.add(_file_identity_key(job, ap))
        return keys

    def _reuse_basename_for_remaining(trigger: str) -> None:
        nonlocal apply_errors, failed_paths
        fixed_keys = _fixed_identity_keys()
        pending: List[str] = []
        for p in failed_paths:
            ploc = resolve_file_location(job, p, build_workdir)
            if not ploc:
                pending.append(p)
                continue
            if _file_identity_key(job, ploc.abs_path) not in fixed_keys:
                pending.append(p)
        cache = _basename_fix_cache(all_applied)
        if not pending or not cache:
            return
        reused, still_failed, reuse_errors = _try_reuse_basename_fixes(
            job, pending, cache, build_workdir, job_id=job_id,
        )
        if reused:
            all_applied.extend(reused)
            apply_errors = _filter_errors_exclude_fixed_identities(
                job, apply_errors, all_applied, build_workdir,
            )
            paths = ", ".join(x["path"] for x in reused[:3])
            _log(job_id, f"basename 复用写回 {len(reused)} 个文件（触发: {trigger}）: {paths}")
            for row in reused:
                apply_errors = [
                    e for e in apply_errors
                    if not _apply_error_matches_path(e, fix_path_for_llm(row.get("path") or ""))
                ]
        if reuse_errors:
            apply_errors.extend(reuse_errors)
        failed_paths = still_failed

    for path in failed_paths[:10]:
        loc = resolve_file_location(job, path, build_workdir)
        if loc and _file_identity_key(job, loc.abs_path) in _fixed_identity_keys():
            continue
        ctx = _collect_context_for_path(job, path, context_errors, build_workdir)
        if not ctx:
            continue
        file_feedback = [e for e in apply_errors if _apply_error_matches_path(e, path)]
        _log(job_id, f"单文件 LLM 重试: {path}")
        try:
            fixes, file_summary = _resolve_build_errors_with_wait(
                job_id,
                label=f"单文件 {path}",
                errors=context_errors,
                log_excerpt=excerpt,
                file_contexts=[ctx],
                target_repo_dir=job.get("target_repo_dir") or "",
                build_workdir=build_workdir,
                search_roots=search_roots,
                diagnostic_chains=diagnostic_chains,
                readonly_note_contexts=readonly_note_contexts,
                apply_feedback=file_feedback or apply_feedback,
                focus_paths=[path],
            )
        except Exception as exc:
            _log(job_id, f"单文件 LLM 重试失败 ({path}): {exc}")
            continue
        if not fixes and _llm_skip_summary(file_summary):
            apply_errors = [e for e in apply_errors if not _apply_error_matches_path(e, path)]
            _log(job_id, f"单文件跳过（LLM 判断无需修改）: {path}")
            continue
        fixes = _filter_llm_fix_targets(job, fixes, build_workdir, job_id=job_id)
        record["llm_summary"] = file_summary
        applied, new_errors, skipped = apply_build_fixes(
            job, fixes, build_workdir, job_id=job_id,
        )
        if applied:
            all_applied.extend(applied)
            apply_errors = _filter_errors_exclude_fixed_identities(
                job, apply_errors, all_applied, build_workdir,
            )
            _log(job_id, f"单文件写回成功: {path}")
            _reuse_basename_for_remaining(path)
        apply_errors = [e for e in apply_errors if not _apply_error_matches_path(e, path)]
        if new_errors:
            apply_errors.extend(new_errors)

    applied = all_applied
    record["files_changed"] = enrich_build_fix_files(
        get_upgrade_job(job_id) or job,
        build_workdir,
        applied,
    )
    record["skipped_target_fixes"] = skipped_target
    record["must_modify_target"] = bool(
        applied and all(x.get("in_target_repo") for x in applied)
    )
    record["finished_at"] = datetime.now().isoformat()

    if skipped_target:
        skipped_paths = ", ".join(x["path"] for x in skipped_target[:3])
        _log(job_id, f"已跳过合入目标路径修改（同文件已有 vendor 外替代方案）: {skipped_paths}")

    if apply_errors or not applied:
        err = "; ".join(apply_errors[:3]) if apply_errors else "LLM 未返回可写回的文件"
        record["error"] = err
        state["status"] = "failed"
        _save_state(job_id, get_upgrade_job(job_id) or job, state)
        _log(job_id, f"写回失败: {err}")
        return {"applied": False, "error": err, "attempt": attempt, "summary": summary}

    record["applied"] = True
    state["status"] = "idle"
    _save_state(job_id, get_upgrade_job(job_id) or job, state)
    if applied and record.get("must_modify_target"):
        _log(job_id, "本次修复必须修改合入目标路径下的代码")
    paths = ", ".join(x["path"] for x in applied[:5])
    _log(job_id, f"AI 修复已写回 {len(applied)} 个文件: {paths}")
    return {
        "applied": True,
        "attempt": attempt,
        "summary": summary,
        "files_changed": applied,
    }


def triage_after_unapplied_attempt(
    job_id: str,
    log_path: str,
    attempt: int,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    """Diagnose an unapplied build-fix attempt; auto-retry once if verdict is retry."""
    from web_app.failure_triage import analyze_upgrade_failure
    from web_app.prompt_loader import set_session_retry_hint

    job = get_upgrade_job(job_id) or {}
    state = _get_state(job)
    last = (state.get("attempts") or [None])[-1] or {}
    excerpt = str(last.get("error_excerpt") or last.get("llm_summary") or "")[:4000]
    errors = str(result.get("error") or last.get("error") or "AI 未能写回编译修复")
    state["status"] = "triaging"
    _save_state(job_id, job, state)
    _log(job_id, "AI 修复未写回，正在分析失败原因…")

    triage = analyze_upgrade_failure(kind="build_fix", errors=errors, extra=excerpt)
    job = get_upgrade_job(job_id) or job
    state = _get_state(job)
    state["failure_triage"] = triage.as_dict()
    state["status"] = "failed"
    _save_state(job_id, job, state)
    _log(job_id, f"失败诊断: {triage.verdict} — {triage.reason}")

    if triage.verdict != "retry" or not (triage.retry_hint or "").strip():
        return result

    opts = dict((get_upgrade_job(job_id) or {}).get("options") or {})
    opts["build_fix_user_hint"] = triage.retry_hint
    update_upgrade_job(job_id, options=opts)
    set_session_retry_hint(triage.retry_hint)
    _log(job_id, "诊断认为可再试，正在按新约束再修一轮…")
    retry_result = run_build_fix_attempt(job_id, log_path, attempt)
    triage.auto_retried = True
    if not retry_result.get("applied"):
        triage.verdict = "manual"
        triage.advice = (
            (triage.advice or "")
            + "\n自动重试后仍失败，请按建议在本机处理。"
        ).strip()
    job = get_upgrade_job(job_id) or {}
    state = _get_state(job)
    state["failure_triage"] = triage.as_dict()
    if retry_result.get("applied"):
        state["status"] = "idle"
    else:
        state["status"] = "failed"
    _save_state(job_id, job, state)
    return retry_result
