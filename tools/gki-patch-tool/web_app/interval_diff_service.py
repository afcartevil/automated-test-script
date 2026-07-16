"""区间 patch 缓存：以数据库为索引，patch 正文保存在磁盘文件中。

同一 repo + from_tag + to_tag 首次生成后写入 interval_diffs 表；
后续分析任务直接复用，跳过 git format-patch / diff。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from web_app.database import delete_interval_diff, get_interval_diff, upsert_interval_diff

MERGED_DIFFS_DIR = Path(__file__).parent.parent / "outputs" / "merged_diffs"


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


def _files_valid(diff_file: Path, squash_file: Path) -> bool:
    try:
        return (
            diff_file.is_file()
            and squash_file.is_file()
            and diff_file.stat().st_size > 0
            and squash_file.stat().st_size > 0
        )
    except OSError:
        return False


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
