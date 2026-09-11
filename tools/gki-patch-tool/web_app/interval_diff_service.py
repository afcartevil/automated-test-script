"""区间 patch 缓存：以数据库为索引，patch 正文保存在磁盘文件中。

同一 repo + from_tag + to_tag 首次生成后写入 interval_diffs 表；
后续分析任务直接复用，跳过 git format-patch / diff。
直接合入也可按 tag 查找已有 squash，或从本地 kernel 仓库现场生成。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from web_app.database import (
    delete_interval_diff,
    find_interval_diff_by_tags,
    get_interval_diff,
    upsert_interval_diff,
)

from web_app.app_paths import outputs_dir

MERGED_DIFFS_DIR = outputs_dir("merged_diffs")
LogFn = Callable[[str], None]


def interval_diff_paths(from_tag: str, to_tag: str) -> Tuple[Path, Path]:
    """标准区间 patch 文件路径（format-patch 与 squash）。"""
    tag_from = from_tag.replace("/", "_").replace("\\", "_")
    tag_to = to_tag.replace("/", "_").replace("\\", "_")
    diff_path = MERGED_DIFFS_DIR / f"{tag_from}_to_{tag_to}.patch"
    squash_path = MERGED_DIFFS_DIR / f"{tag_from}_to_{tag_to}_squash.patch"
    return diff_path, squash_path


def _normalize_repo_key(repo: str) -> str:
    if not repo:
        return ""
    from tools.patch_analyzer import normalize_repo_url
    return normalize_repo_url(repo)


def _file_ok(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _files_valid(diff_file: Path, squash_file: Path) -> bool:
    return _file_ok(diff_file) and _file_ok(squash_file)


def is_squash_patch_path(path: Path) -> bool:
    return path.name.endswith("_squash.patch")


def _estimate_commit_count(diff_file: Path) -> int:
    """从 format-patch 文件估算 commit 数（仅用于回填旧文件）。"""
    try:
        count = 0
        with open(diff_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("From ") and " Mon Sep 17 " in line:
                    count += 1
        return count
    except OSError:
        return 0


@dataclass
class IntervalDiffCache:
    diff_file: Path
    squash_file: Path
    commit_count: int
    source: str  # "db" | "disk_backfill"


def load_interval_diff_cache(
    repo: str, from_tag: str, to_tag: str,
) -> Optional[IntervalDiffCache]:
    """查找已缓存的区间 patch；DB 记录失效时尝试默认磁盘路径并回填。"""
    repo_key = _normalize_repo_key(repo)

    row = get_interval_diff(repo_key, from_tag, to_tag)
    if row:
        diff_p = Path(row["diff_file"])
        squash_p = Path(row["squash_file"])
        if _files_valid(diff_p, squash_p):
            return IntervalDiffCache(
                diff_p, squash_p,
                int(row.get("commit_count") or 0),
                "db",
            )
        if not _file_ok(diff_p) and not _file_ok(squash_p):
            delete_interval_diff(repo_key, from_tag, to_tag)
            print(
                f"[INTERVAL DIFF] DB 记录已失效，将重新生成: {from_tag}..{to_tag}",
                flush=True,
            )

    diff_p, squash_p = interval_diff_paths(from_tag, to_tag)
    if _files_valid(diff_p, squash_p):
        commit_count = _estimate_commit_count(diff_p)
        upsert_interval_diff(
            repo_key, from_tag, to_tag,
            str(diff_p), str(squash_p), commit_count,
        )
        print(
            f"[INTERVAL DIFF] 从磁盘回填缓存: {diff_p.name} ({commit_count} commits)",
            flush=True,
        )
        return IntervalDiffCache(diff_p, squash_p, commit_count, "disk_backfill")
    return None


def save_interval_diff_cache(
    repo: str,
    from_tag: str,
    to_tag: str,
    diff_file: Path,
    squash_file: Path,
    commit_count: int,
) -> None:
    """将新生成的区间 patch 登记到数据库。"""
    repo_key = _normalize_repo_key(repo)
    upsert_interval_diff(
        repo_key, from_tag, to_tag,
        str(diff_file), str(squash_file), commit_count,
    )
    print(
        f"[INTERVAL DIFF] 已缓存区间 patch: {from_tag}..{to_tag} "
        f"({commit_count} commits)",
        flush=True,
    )


def prefer_squash_sibling(path: Path) -> Path:
    """If a squash sibling of a format-patch file exists, prefer it."""
    if is_squash_patch_path(path):
        return path
    sibling = path.parent / f"{path.stem}_squash{path.suffix}"
    if _file_ok(sibling):
        return sibling
    return path


def find_interval_patch_file(
    repo: str,
    from_tag: str,
    to_tag: str,
    *,
    prefer_squash: bool = True,
) -> Optional[Path]:
    """Find an existing interval patch. Squash-only files are enough for 合入."""
    candidates: List[Path] = []
    repo_key = _normalize_repo_key(repo)
    row = get_interval_diff(repo_key, from_tag, to_tag)
    if not row:
        row = find_interval_diff_by_tags(from_tag, to_tag)
    if row:
        squash_p = Path(row.get("squash_file") or "")
        diff_p = Path(row.get("diff_file") or "")
        if prefer_squash:
            candidates.extend([squash_p, diff_p])
        else:
            candidates.extend([diff_p, squash_p])

    disk_diff, disk_squash = interval_diff_paths(from_tag, to_tag)
    if prefer_squash:
        candidates.extend([disk_squash, disk_diff])
    else:
        candidates.extend([disk_diff, disk_squash])

    seen = set()
    for path in candidates:
        key = str(path)
        if not key or key in seen:
            continue
        seen.add(key)
        if _file_ok(path):
            return prefer_squash_sibling(path) if prefer_squash else path
    return None


def generate_interval_squash(
    from_tag: str,
    to_tag: str,
    repo_dir: Path,
    *,
    log_fn: Optional[LogFn] = None,
) -> Path:
    """Generate squash patch from a local kernel/common checkout."""
    from tools.patch_analyzer import run_git

    def log(msg: str) -> None:
        print(f"[INTERVAL DIFF] {msg}", flush=True)
        if log_fn:
            log_fn(msg)

    for tag in (from_tag, to_tag):
        try:
            run_git(repo_dir, ["rev-parse", "--verify", f"{tag}^{{commit}}"])
        except RuntimeError as exc:
            raise FileNotFoundError(
                f"本地 kernel 仓库未找到 tag {tag}，无法生成区间 patch。"
                "请先 fetch 该 tag，或完成区间分析后再合入。"
            ) from exc

    commit_count = 0
    try:
        out = run_git(repo_dir, ["rev-list", "--count", f"{from_tag}..{to_tag}"]).strip()
        commit_count = int(out or 0)
    except Exception:
        pass

    log(f"正在从本地仓库生成 squash: {from_tag}..{to_tag} ({commit_count} commits)")
    squash_output = run_git(
        repo_dir,
        ["diff", "-W", "-M", f"{from_tag}..{to_tag}"],
        timeout=900,
    )
    if not (squash_output or "").strip():
        raise FileNotFoundError(
            f"区间 {from_tag}..{to_tag} 的 git diff 为空，请确认 tag 顺序与仓库正确"
        )

    _, squash_path = interval_diff_paths(from_tag, to_tag)
    squash_path.parent.mkdir(parents=True, exist_ok=True)
    with open(squash_path, "w", encoding="utf-8") as f:
        f.write(
            "From 0000000000000000000000000000000000000000 "
            "Mon Sep 17 00:00:00 2001\n"
        )
        f.write(f"Subject: squash diff {from_tag}..{to_tag} ({commit_count} commits)\n\n")
        f.write(squash_output)
        if not squash_output.endswith("\n"):
            f.write("\n")
    size_kb = squash_path.stat().st_size / 1024
    log(f"已生成 squash: {squash_path.name} ({size_kb:.0f} KB)")
    return squash_path


def ensure_interval_patch_file(
    repo: str,
    from_tag: str,
    to_tag: str,
    *,
    prefer_squash: bool = True,
    log_fn: Optional[LogFn] = None,
) -> Path:
    """Return an existing interval patch, or generate squash from the local repo."""
    found = find_interval_patch_file(
        repo, from_tag, to_tag, prefer_squash=prefer_squash,
    )
    if found and (not prefer_squash or is_squash_patch_path(found)):
        return found

    from web_app.repo_config import get_local_repo_dir

    repo_dir = get_local_repo_dir()
    if not repo_dir:
        raise FileNotFoundError(
            f"未找到区间 patch 文件: {from_tag}..{to_tag}。"
            "直接合入请先在「系统设置」配置本地 kernel/common 路径，"
            "或先完成区间分析"
        )
    return generate_interval_squash(from_tag, to_tag, repo_dir, log_fn=log_fn)


def local_repo_can_generate_patch() -> bool:
    from web_app.repo_config import get_local_repo_dir

    return get_local_repo_dir() is not None
