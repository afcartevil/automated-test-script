"""模块 chunk 分组、diff 提取与覆盖率元数据。"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from web_app.analyzer_service import patch_high_risk_reason
from web_app.app_paths import data_dir

CHUNK_MAX_PATCHES = 60
CHUNK_MAX_DIFF_CHARS = 60000
MODULE_DIFF_MAX_CHARS = 45000
# 超过该 patch 数才强制切 chunk；提高以减少模块 LLM 次数（质量换成本）
SMALL_MODULE_THRESHOLD = 80
HIGH_RISK_EVIDENCE_MAX_PATCHES = 8
HIGH_RISK_EVIDENCE_PER_PATCH_CHARS = 6000
HIGH_RISK_EVIDENCE_TOTAL_CHARS = 32000
PATCH_DIGEST_MAX_CHARS = 24000

_GLOBAL_CHUNK_CACHE_LOCK = None  # lazy threading.Lock
_GLOBAL_CHUNK_CACHE_PATH = data_dir() / "module_chunk_global_cache.json"


def patch_sha(p: Dict[str, Any]) -> str:
    return (p.get("commit") or p.get("sha") or "").strip()


def is_priority_patch(p: Dict[str, Any]) -> bool:
    """高风险 patch 必须在 chunk digest 中完整保留。"""
    if p.get("blocked"):
        return True
    crash = (p.get("crash_risk") or "").strip()
    if crash in ("高", "中"):
        return True
    if (p.get("key_risk") or "").strip():
        return True
    score = float(p.get("score", 0) or 0)
    if score and score < 6:
        return True
    if patch_high_risk_reason(p):
        return True
    return False


def patch_priority_key(p: Dict[str, Any]) -> tuple:
    score = float(p.get("score", 0) or 0)
    blocked = 1 if p.get("blocked") else 0
    crash = (p.get("crash_risk") or "").strip()
    crash_rank = 2 if crash == "高" else 1 if crash == "中" else 0
    low_score = 1 if score and score < 6 else 0
    return (-blocked, -crash_rank, -low_score, score)


def _patch_dir_key(p: Dict[str, Any]) -> str:
    """按变更文件目录聚合，优先保留同目录 patch 在同一 chunk。"""
    files = [f.strip().lstrip("./") for f in (p.get("files") or []) if f and str(f).strip()]
    if not files:
        return "__no_files__"
    parts = files[0].split("/")
    if len(parts) >= 3:
        return "/".join(parts[:2])
    if len(parts) >= 2:
        return parts[0]
    return parts[0]


def build_module_chunks(
    patches: List[Dict[str, Any]],
    *,
    max_patches: int = CHUNK_MAX_PATCHES,
) -> List[Dict[str, Any]]:
    """将模块 patch 拆分为若干 chunk，保证每笔 patch 恰好落入一个 chunk。"""
    if not patches:
        return []

    if len(patches) <= max_patches:
        return [{
            "chunk_id": "chunk_0",
            "chunk_index": 0,
            "patches": list(patches),
            "dir_hint": "all",
        }]

    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in patches:
        groups[_patch_dir_key(p)].append(p)

    sorted_groups = sorted(
        groups.items(),
        key=lambda item: (-len(item[1]), item[0]),
    )

    chunks: List[Dict[str, Any]] = []
    current: List[Dict[str, Any]] = []
    current_dirs: List[str] = []

    def _flush() -> None:
        nonlocal current, current_dirs
        if not current:
            return
        idx = len(chunks)
        chunks.append({
            "chunk_id": f"chunk_{idx}",
            "chunk_index": idx,
            "patches": list(current),
            "dir_hint": ",".join(current_dirs[:4]) or "mixed",
        })
        current = []
        current_dirs = []

    for dir_key, group_patches in sorted_groups:
        if len(group_patches) > max_patches:
            if current:
                _flush()
            for i in range(0, len(group_patches), max_patches):
                sub = group_patches[i:i + max_patches]
                idx = len(chunks)
                chunks.append({
                    "chunk_id": f"chunk_{idx}",
                    "chunk_index": idx,
                    "patches": sub,
                    "dir_hint": dir_key,
                })
            continue

        if len(current) + len(group_patches) > max_patches:
            _flush()
        current.extend(group_patches)
        if dir_key not in current_dirs:
            current_dirs.append(dir_key)

    _flush()
    return chunks


def chunk_cache_key(module_name: str, chunk: Dict[str, Any]) -> str:
    """Content-addressed key: module + sorted SHA digest（不含 chunk_index，便于跨任务复用）。"""
    shas = sorted(patch_sha(p)[:12] for p in chunk.get("patches") or [] if patch_sha(p))
    digest = hashlib.sha256("|".join(shas).encode("utf-8")).hexdigest()[:16]
    return f"{module_name}__{digest}"


def module_rollup_cache_key(module_name: str, patches: List[Dict[str, Any]]) -> str:
    shas = sorted(patch_sha(p)[:12] for p in patches if patch_sha(p))
    digest = hashlib.sha256("|".join(shas).encode("utf-8")).hexdigest()[:16]
    return f"{module_name}__rollup__{digest}"


def _global_cache_lock():
    global _GLOBAL_CHUNK_CACHE_LOCK
    if _GLOBAL_CHUNK_CACHE_LOCK is None:
        import threading
        _GLOBAL_CHUNK_CACHE_LOCK = threading.Lock()
    return _GLOBAL_CHUNK_CACHE_LOCK


def load_global_chunk_cache() -> Dict[str, Any]:
    path = _GLOBAL_CHUNK_CACHE_PATH
    if not path.exists():
        return {"modules": {}, "rollups": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"modules": {}, "rollups": {}}
        data.setdefault("modules", {})
        data.setdefault("rollups", {})
        return data
    except (json.JSONDecodeError, OSError, TypeError):
        return {"modules": {}, "rollups": {}}


def save_global_chunk_cache(cache: Dict[str, Any]) -> None:
    path = _GLOBAL_CHUNK_CACHE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    payload = {
        "modules": cache.get("modules") if isinstance(cache.get("modules"), dict) else {},
        "rollups": cache.get("rollups") if isinstance(cache.get("rollups"), dict) else {},
    }
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def lookup_global_chunk_entry(module_name: str, cache_key: str) -> Optional[Dict[str, Any]]:
    with _global_cache_lock():
        cache = load_global_chunk_cache()
        mod = (cache.get("modules") or {}).get(module_name) or {}
        if not isinstance(mod, dict):
            return None
        entry = mod.get(cache_key)
        return entry if isinstance(entry, dict) else None


def lookup_global_rollup(module_name: str, rollup_key: str) -> Optional[Dict[str, Any]]:
    with _global_cache_lock():
        cache = load_global_chunk_cache()
        rollups = cache.get("rollups") or {}
        if not isinstance(rollups, dict):
            return None
        entry = rollups.get(rollup_key)
        if isinstance(entry, dict) and entry.get("analysis"):
            return entry
        # legacy flat
        return None


def store_global_chunk_entries(module_entries: Dict[str, Dict[str, Any]]) -> None:
    if not module_entries:
        return
    with _global_cache_lock():
        cache = load_global_chunk_cache()
        modules = cache.setdefault("modules", {})
        for module_name, entries in module_entries.items():
            if not isinstance(entries, dict):
                continue
            mod_cache = modules.setdefault(module_name, {})
            if isinstance(mod_cache, dict):
                mod_cache.update(entries)
            modules[module_name] = mod_cache
        save_global_chunk_cache(cache)


def store_global_rollup(rollup_key: str, analysis: Dict[str, Any], *, module_name: str = "") -> None:
    if not rollup_key or not isinstance(analysis, dict):
        return
    with _global_cache_lock():
        cache = load_global_chunk_cache()
        rollups = cache.setdefault("rollups", {})
        if isinstance(rollups, dict):
            rollups[rollup_key] = {
                "module": module_name,
                "analysis": analysis,
            }
        save_global_chunk_cache(cache)


def _chunk_dir_hint(patches: List[Dict[str, Any]]) -> str:
    dirs = sorted({_patch_dir_key(p) for p in patches})
    if not dirs:
        return "mixed"
    if len(dirs) == 1:
        return dirs[0]
    if len(dirs) <= 4:
        return ",".join(dirs)
    return "mixed"


def get_chunk_pathspecs(patches: List[Dict[str, Any]], max_specs: int = 24) -> List[str]:
    """优先使用 chunk 内 patch 的精确文件路径，避免目录 pathspec 拉入无关 diff。"""
    paths: set = set()
    for p in patches:
        for fp in p.get("files") or []:
            fp = str(fp).strip().lstrip("./")
            if fp:
                paths.add(fp)
    if not paths:
        return []
    if len(paths) <= max_specs:
        return sorted(paths)

    dir_prefixes: set = set()
    for fp in paths:
        parts = fp.split("/")
        if len(parts) >= 3:
            dir_prefixes.add("/".join(parts[:2]))
        elif len(parts) >= 2:
            dir_prefixes.add(parts[0])
        else:
            dir_prefixes.add(parts[0])
    specs = sorted(dir_prefixes)
    if len(specs) <= max_specs:
        return specs
    return specs[:max_specs]


def _fetch_chunk_diff_raw(
    from_tag: str,
    to_tag: str,
    patches: List[Dict[str, Any]],
    repo_dir: Path,
) -> str:
    pathspecs = get_chunk_pathspecs(patches)
    if not pathspecs:
        return ""
    from tools.patch_analyzer import run_git
    cmd = ["diff", "-W", "-M", f"{from_tag}..{to_tag}", "--", *pathspecs]
    return run_git(repo_dir, cmd)


def measure_chunk_diff_chars(
    from_tag: str,
    to_tag: str,
    patches: List[Dict[str, Any]],
    repo_dir: Optional[Path] = None,
    diff_size_fn=None,
) -> int:
    """估算 chunk diff 字符数；无仓库时返回 0（不做自适应拆分）。"""
    if diff_size_fn is not None:
        return int(diff_size_fn(patches))
    if not repo_dir or not from_tag or not to_tag or not patches:
        return 0
    try:
        out = _fetch_chunk_diff_raw(from_tag, to_tag, patches, Path(repo_dir))
        return len(out) if out.strip() else 0
    except Exception:
        return 0


def _split_chunk_adaptive(
    chunk: Dict[str, Any],
    from_tag: str,
    to_tag: str,
    repo_dir: Optional[Path],
    max_diff_chars: int,
    diff_size_fn=None,
) -> List[Dict[str, Any]]:
    patch_list = list(chunk.get("patches") or [])
    if not patch_list:
        return [chunk]

    size = measure_chunk_diff_chars(
        from_tag, to_tag, patch_list, repo_dir, diff_size_fn=diff_size_fn,
    )
    if size <= max_diff_chars:
        return [chunk]

    if len(patch_list) <= 1:
        return [{**chunk, "split_exhausted": True}]

    mid = len(patch_list) // 2
    left = {
        "patches": patch_list[:mid],
        "dir_hint": _chunk_dir_hint(patch_list[:mid]),
        "auto_split": True,
    }
    right = {
        "patches": patch_list[mid:],
        "dir_hint": _chunk_dir_hint(patch_list[mid:]),
        "auto_split": True,
    }
    return (
        _split_chunk_adaptive(left, from_tag, to_tag, repo_dir, max_diff_chars, diff_size_fn)
        + _split_chunk_adaptive(right, from_tag, to_tag, repo_dir, max_diff_chars, diff_size_fn)
    )


def build_adaptive_module_chunks(
    patches: List[Dict[str, Any]],
    *,
    from_tag: str = "",
    to_tag: str = "",
    repo_dir: Optional[Path] = None,
    max_patches: int = CHUNK_MAX_PATCHES,
    max_diff_chars: int = CHUNK_MAX_DIFF_CHARS,
    diff_size_fn=None,
) -> List[Dict[str, Any]]:
    """按 patch 数量初步分组，再按 diff 体积极限递归二分，避免截断后送 LLM。"""
    base = build_module_chunks(patches, max_patches=max_patches)
    if not base:
        return []

    expanded: List[Dict[str, Any]] = []
    for chunk in base:
        expanded.extend(
            _split_chunk_adaptive(
                chunk, from_tag, to_tag, repo_dir, max_diff_chars, diff_size_fn,
            )
        )

    for idx, chunk in enumerate(expanded):
        chunk["chunk_index"] = idx
        chunk["chunk_id"] = f"chunk_{idx}"
    return expanded


def get_patch_diff_text(
    patch: Dict[str, Any],
    repo_dir: Optional[Path] = None,
    *,
    max_chars: int = HIGH_RISK_EVIDENCE_PER_PATCH_CHARS,
) -> str:
    """获取单笔 patch diff，优先用已采集的 diff_text / diff_preview。"""
    diff = (patch.get("diff_text") or "").strip()
    if not diff:
        preview = patch.get("diff_preview") or {}
        if isinstance(preview, dict):
            diff = (preview.get("content") or preview.get("text") or "").strip()
        elif isinstance(preview, str):
            diff = preview.strip()
    if not diff and repo_dir:
        sha = patch_sha(patch)
        if sha:
            try:
                from tools.patch_analyzer import run_git
                diff = run_git(Path(repo_dir), ["show", "--format=", "--no-color", sha])
            except Exception:
                diff = ""
    if max_chars and len(diff) > max_chars:
        return diff[:max_chars] + f"\n... (patch diff truncated, total {len(diff)} chars) ..."
    return diff


def build_high_risk_evidence(
    patches: List[Dict[str, Any]],
    repo_dir: Optional[Path] = None,
    *,
    max_patches: int = HIGH_RISK_EVIDENCE_MAX_PATCHES,
    max_per_patch_chars: int = HIGH_RISK_EVIDENCE_PER_PATCH_CHARS,
    max_total_chars: int = HIGH_RISK_EVIDENCE_TOTAL_CHARS,
) -> str:
    """为高风险 patch 附加关键 diff 片段，供 chunk/rollup 取证。"""
    priority = sorted(
        [p for p in patches if is_priority_patch(p)],
        key=patch_priority_key,
    )
    if not priority:
        return ""

    blocks: List[str] = []
    total = 0
    for p in priority[:max_patches]:
        sha = patch_sha(p)[:12]
        title = (p.get("title") or "")[:80]
        reason = patch_high_risk_reason(p) or (p.get("key_risk") or "")[:80]
        diff = get_patch_diff_text(p, repo_dir, max_chars=max_per_patch_chars)
        header = f"### `{sha}` {title}"
        if reason:
            header += f"\n风险: {reason}"
        block = (
            f"{header}\n```diff\n{diff}\n```"
            if diff
            else f"{header}\n(无 diff，请依据 Patch 摘要)"
        )
        if total + len(block) > max_total_chars:
            remaining = len(priority) - len(blocks)
            if remaining > 0:
                blocks.append(f"... 另有 {remaining} 笔高风险 patch 未附 diff")
            break
        blocks.append(block)
        total += len(block)
    return "\n\n".join(blocks)


def get_chunk_diff_content(
    from_tag: str,
    to_tag: str,
    patches: List[Dict[str, Any]],
    repo_dir: Optional[Path] = None,
    max_chars: int = CHUNK_MAX_DIFF_CHARS,
) -> Tuple[str, bool]:
    """获取 chunk 相关路径的合并 diff。返回 (content, truncated)."""
    if not repo_dir or not from_tag or not to_tag or not patches:
        return "", False
    pathspecs = get_chunk_pathspecs(patches)
    if not pathspecs:
        return "", False
    try:
        out = _fetch_chunk_diff_raw(from_tag, to_tag, patches, Path(repo_dir))
        if not out.strip():
            return "", False
        if len(out) > max_chars:
            return out[:max_chars] + f"\n\n... (diff truncated, total {len(out)} chars) ...", True
        return out, False
    except Exception as exc:
        return f"(chunk diff 获取失败: {exc})", False


def get_chunk_diff_stat(
    from_tag: str,
    to_tag: str,
    patches: List[Dict[str, Any]],
    repo_dir: Optional[Path] = None,
    max_chars: int = 8000,
) -> str:
    if not repo_dir or not from_tag or not to_tag or not patches:
        return ""
    pathspecs = get_chunk_pathspecs(patches)
    if not pathspecs:
        return ""
    try:
        from tools.patch_analyzer import run_git
        cmd = ["diff", "--stat", f"{from_tag}..{to_tag}", "--", *pathspecs]
        out = run_git(Path(repo_dir), cmd)
        if len(out) > max_chars:
            return out[:max_chars] + "\n... (stat truncated)"
        return out
    except Exception as exc:
        return f"(chunk stat 获取失败: {exc})"


def build_coverage_metadata(
    chunks: List[Dict[str, Any]],
    chunk_summaries: List[Dict[str, Any]],
    mod_patches: List[Dict[str, Any]],
) -> Dict[str, Any]:
    covered: set = set()
    for cs in chunk_summaries:
        for sha in cs.get("covered_shas") or []:
            if sha:
                covered.add(str(sha)[:12])
        for p in cs.get("patches") or []:
            sha = patch_sha(p)
            if sha:
                covered.add(sha[:12])

    expected = {patch_sha(p)[:12] for p in mod_patches if patch_sha(p)}
    truncated = sum(1 for cs in chunk_summaries if cs.get("truncated_input"))
    split_exhausted = sum(1 for c in chunks if c.get("split_exhausted"))
    auto_split = any(c.get("auto_split") for c in chunks)
    high_risk = sum(1 for p in mod_patches if patch_high_risk_reason(p))
    patch_coverage = bool(expected) and covered >= expected

    return {
        "chunk_count": len(chunks),
        "covered_patch_count": len(covered & expected) if expected else len(covered),
        "total_patch_count": len(mod_patches),
        "truncated_chunk_count": truncated,
        "split_exhausted_count": split_exhausted,
        "auto_split": auto_split,
        "high_risk_patch_count": high_risk,
        "patch_coverage_complete": patch_coverage,
        "coverage_complete": patch_coverage and truncated == 0 and split_exhausted == 0,
    }


def load_chunk_cache(task_id: str) -> Dict[str, Any]:
    from web_app.database import get_task
    task = get_task(task_id) or {}
    raw = task.get("module_chunk_summaries") or ""
    if not raw:
        return {}
    try:
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def save_chunk_cache(task_id: str, cache: Dict[str, Any]) -> None:
    from web_app.database import update_task
    update_task(task_id, module_chunk_summaries=json.dumps(cache, ensure_ascii=False))


def merge_chunk_cache(task_id: str, module_name: str, entries: Dict[str, Any]) -> None:
    apply_chunk_cache_batch(task_id, {module_name: entries})


def apply_chunk_cache_batch(task_id: str, module_entries: Dict[str, Dict[str, Any]]) -> None:
    """Merge chunk cache entries for one or more modules in a single DB write.

    Also mirrors into the process-global content-addressed cache for cross-task reuse.
    """
    if not module_entries:
        return
    cache = load_chunk_cache(task_id)
    for module_name, entries in module_entries.items():
        if not isinstance(entries, dict):
            continue
        mod_cache = cache.setdefault(module_name, {})
        if isinstance(mod_cache, dict):
            mod_cache.update(entries)
        cache[module_name] = mod_cache
    save_chunk_cache(task_id, cache)
    store_global_chunk_entries(module_entries)


def resolve_chunk_cache_entry(
    task_id: str,
    module_name: str,
    cache_key: str,
    *,
    task_mod_cache: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Lookup task-local cache first, then global content cache."""
    mod_cache = task_mod_cache if task_mod_cache is not None else (
        (load_chunk_cache(task_id).get(module_name) or {})
    )
    if isinstance(mod_cache, dict):
        entry = mod_cache.get(cache_key)
        if isinstance(entry, dict) and entry.get("summary"):
            return entry
        digest = cache_key.split("__")[-1] if "__" in cache_key else cache_key
        for key, val in mod_cache.items():
            if not isinstance(val, dict) or not val.get("summary"):
                continue
            if key == cache_key or str(key).endswith(f"__{digest}"):
                return val
    return lookup_global_chunk_entry(module_name, cache_key)


def get_cached_chunk_summary(
    task_id: str,
    module_name: str,
    cache_key: str,
) -> Optional[Dict[str, Any]]:
    return resolve_chunk_cache_entry(task_id, module_name, cache_key)
