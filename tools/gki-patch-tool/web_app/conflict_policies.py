"""Path-based conflict resolution policies (before LLM)."""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from web_app.repo_config import get_local_repo_dir

# GKI 元数据目录：合入冲突时以目标 tag 版本为准，不做 vendor/LLM 混合合并
ANDROID_GKI_PREFIX = "android/"


def source_path_from_conflict(conflict_path: str) -> str:
    if conflict_path.endswith(".rej"):
        return conflict_path[:-4]
    return conflict_path


def is_android_gki_metadata_path(rel_path: str) -> bool:
    p = rel_path.replace("\\", "/").lstrip("/")
    return p == "android" or p.startswith(ANDROID_GKI_PREFIX)


def _local_git_show(repo_dir: Path, tag: str, rel_path: str) -> str:
    spec = f"{tag}:{rel_path}"
    proc = subprocess.run(
        ["git", "show", spec],
        cwd=str(repo_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode == 0:
        return proc.stdout

    # tag 可能未 fetch，尝试从 origin 拉取后再读
    subprocess.run(
        ["git", "fetch", "origin", f"refs/tags/{tag}:refs/tags/{tag}"],
        cwd=str(repo_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    proc = subprocess.run(
        ["git", "show", spec],
        cwd=str(repo_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise FileNotFoundError(f"GKI common 中不存在 {spec}: {detail}")
    return proc.stdout


def read_gki_file_at_tag(to_tag: str, rel_path: str) -> str:
    """Read file content from local GKI common clone at tag."""
    if not to_tag:
        raise RuntimeError("升级任务缺少 to_tag，无法读取 GKI 目标版本")
    repo = get_local_repo_dir()
    if repo is None:
        raise RuntimeError(
            "未配置本地 GKI common 仓库（页面「仓库配置」或 gki-patch-tool.yaml repo.dir）"
        )
    rel = rel_path.replace("\\", "/").lstrip("/")
    return _local_git_show(repo, to_tag, rel)


def resolve_android_with_to_tag(
    job: dict,
    source_path: str,
    *,
    original_content: str = "",
) -> Optional[Tuple[str, str, str]]:
    """Return (proposed_content, summary, strategy) or None if policy does not apply."""
    if not is_android_gki_metadata_path(source_path):
        return None
    to_tag = (job.get("to_tag") or "").strip()
    try:
        proposed = read_gki_file_at_tag(to_tag, source_path)
    except Exception as exc:
        raise RuntimeError(f"android/ 取 to_tag 失败 ({source_path}): {exc}") from exc
    summary = (
        f"android/ 元数据以 GKI to_tag ({to_tag}) 为准，"
        f"直接采用目标 tag 文件（{len(proposed.splitlines())} 行）"
    )
    return proposed, summary, "to_tag"


def _write_target_text(job: dict, target: Path, rel_path: str, content: str) -> None:
    from web_app.job_file_io import write_repo_rel
    write_repo_rel(job, rel_path, content)


def _remove_target_file(job: dict, target: Path, rel_path: str) -> None:
    from web_app.job_file_io import remove_repo_rel
    remove_repo_rel(job, rel_path)


def collect_android_gki_sources(*path_lists: Optional[List[str]]) -> List[str]:
    """Unique android/ source paths from .rej paths or plain file paths."""
    seen: Dict[str, None] = {}
    for paths in path_lists:
        if not paths:
            continue
        for p in paths:
            src = source_path_from_conflict(p)
            if is_android_gki_metadata_path(src):
                seen[src] = None
    return sorted(seen.keys())


def apply_android_gki_during_apply(
    job: dict,
    target: Path,
    *,
    rej_files: Optional[List[str]] = None,
    extra_paths: Optional[List[str]] = None,
) -> Tuple[List[str], List[str]]:
    """During apply: write android/ files from GKI to_tag, remove .rej, git add.

    Returns (applied_source_paths, failure_messages).
    """
    from web_app.upgrade_git import run_git

    to_tag = (job.get("to_tag") or "").strip()
    if not to_tag:
        return [], ["缺少 to_tag，跳过 android/ 自动写回"]

    sources = collect_android_gki_sources(rej_files, extra_paths)
    if not sources:
        return [], []

    applied: List[str] = []
    failed: List[str] = []
    rej_by_source = {
        source_path_from_conflict(p): p
        for p in (rej_files or [])
        if p.endswith(".rej")
    }

    for source in sources:
        try:
            content = read_gki_file_at_tag(to_tag, source)
            _write_target_text(job, target, source, content)
            rej_path = rej_by_source.get(source)
            if rej_path:
                _remove_target_file(job, target, rej_path)
            run_git(target, ["add", source], check=False)
            applied.append(source)
        except Exception as exc:
            failed.append(f"{source}: {exc}")

    return applied, failed
