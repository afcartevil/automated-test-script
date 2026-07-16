"""Deterministic conflict resolution: 3-way merge, hunk classify, LLM diff fallback."""
from __future__ import annotations

import difflib
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from web_app.conflict_policies import read_gki_file_at_tag
from web_app.conflict_region_utils import (
    _locate_hunk_in_source,
    _parse_hunk_sides,
    _rej_plus_lines_present,
    _sanitize_duplicate_wrrd_msgs_advance,
    _split_lines,
    apply_all_rej_micro_patches,
    apply_hunk_merge_to_source,
    apply_rej_hunk_micro_patches,
    collect_conflict_merge_tasks,
    extract_merged_hunk_body,
    validate_merged_hunk_middle,
    validate_rej_merge_complete,
    _vendor_body_lines,
)

HunkKind = Literal["A", "B", "C"]

_MATCH_BASE = 0.92


def _log(job_id: str, msg: str) -> None:
    from web_app.upgrade_progress import append_job_log
    append_job_log(job_id, msg, "conflicts")


def load_gki_file_versions(
    job: Dict[str, Any],
    source_path: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Return (base@from_tag, theirs@to_tag) from local GKI common, or (None, None)."""
    from_tag = (job.get("from_tag") or "").strip()
    to_tag = (job.get("to_tag") or "").strip()
    if not from_tag or not to_tag:
        return None, None
    rel = source_path.replace("\\", "/").lstrip("/")
    base = theirs = None
    try:
        base = read_gki_file_at_tag(from_tag, rel)
    except Exception:
        pass
    try:
        theirs = read_gki_file_at_tag(to_tag, rel)
    except Exception:
        pass
    return base, theirs


def git_merge_file_contents(ours: str, base: str, theirs: str) -> Tuple[str, bool]:
    """Run git merge-file; return (merged_text, has_conflict_markers)."""
    with tempfile.TemporaryDirectory(prefix="gki_merge_") as td:
        root = Path(td)
        paths = {
            "ours": root / "ours",
            "base": root / "base",
            "theirs": root / "theirs",
        }
        for key, text in (("ours", ours), ("base", base), ("theirs", theirs)):
            paths[key].write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        proc = subprocess.run(
            [
                "git", "merge-file", "-p",
                str(paths["ours"]), str(paths["base"]), str(paths["theirs"]),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        merged = proc.stdout or ""
        has_markers = "<<<<<<<" in merged or ">>>>>>>" in merged
        if proc.returncode not in (0, 1) and not merged.strip():
            raise RuntimeError(
                f"git merge-file 失败 (exit {proc.returncode}): "
                f"{(proc.stderr or '').strip()[:200]}"
            )
        return merged, has_markers or proc.returncode == 1


def _lines_match(a: List[str], b: List[str], *, ratio: float = _MATCH_BASE) -> bool:
    if not a and not b:
        return True
    if len(a) != len(b):
        return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() >= ratio
    return all(x.strip() == y.strip() for x, y in zip(a, b))


def _slice_at(lines: List[str], start: int, count: int) -> List[str]:
    s = max(0, start)
    e = min(len(lines), s + max(count, 1))
    return lines[s:e]


def classify_hunk(
    *,
    vendor_lines: List[str],
    base_lines: Optional[List[str]],
    hunk_start: int,
    hunk_end: int,
    hunk_old: List[str],
    hunk_new: List[str],
) -> HunkKind:
    """A=GKI-only change; B=keep vendor; C=both sides changed."""
    vendor_chunk = vendor_lines[hunk_start:hunk_end]
    if _lines_match(vendor_chunk, hunk_new):
        return "B"
    if hunk_old and _lines_match(hunk_old, hunk_new):
        return "B"
    if base_lines is not None:
        base_start = _locate_hunk_in_source(base_lines, hunk_start, hunk_old) or hunk_start
        base_chunk = base_lines[base_start: base_start + len(hunk_old or vendor_chunk)]
        if hunk_old and _lines_match(vendor_chunk, base_chunk) and not _lines_match(hunk_old, hunk_new):
            return "A"
        if _lines_match(vendor_chunk, base_chunk) and hunk_new:
            return "A"
    if not hunk_new or _lines_match(hunk_old, hunk_new):
        return "B"
    return "C"


def _try_region_merge_file(
    vendor_body: List[str],
    base_body: List[str],
    theirs_body: List[str],
) -> Optional[List[str]]:
    try:
        merged, has_markers = git_merge_file_contents(
            "\n".join(vendor_body) + "\n",
            "\n".join(base_body) + "\n",
            "\n".join(theirs_body) + "\n",
        )
        if has_markers:
            return None
        return _split_lines(merged)
    except (RuntimeError, OSError):
        return None


def resolve_conflict_file(
    job: Dict[str, Any],
    *,
    job_id: str = "",
    source_path: str,
    original_content: str,
    rej_content: str = "",
    has_conflict_markers: bool = False,
) -> Tuple[str, str, str]:
    """Resolve one conflicted file. Returns (proposed, summary, strategy)."""
    base_text, theirs_text = load_gki_file_versions(job, source_path)
    notes: List[str] = []

    if base_text is not None and theirs_text is not None and not has_conflict_markers:
        try:
            merged, has_markers = git_merge_file_contents(
                original_content, base_text, theirs_text,
            )
            if not has_markers:
                _log(job_id, f"三路 merge-file 成功: {source_path}")
                return (
                    merged,
                    f"git merge-file 三路合并（{job.get('from_tag')} → {job.get('to_tag')}）",
                    "merge_file",
                )
            notes.append("全文件 merge-file 含冲突标记，转 hunk 级处理")
        except RuntimeError as exc:
            notes.append(f"全文件 merge-file 失败: {exc}")

    if not rej_content.strip() and not has_conflict_markers:
        raise RuntimeError("无 .rej 且全文件三路合并未成功，需人工处理")

    tasks = collect_conflict_merge_tasks(
        original_content=original_content,
        rej_content=rej_content,
        has_conflict_markers=has_conflict_markers,
    )
    if not tasks:
        raise RuntimeError("无法解析冲突区域")

    base_lines = _split_lines(base_text) if base_text else None
    theirs_lines = _split_lines(theirs_text) if theirs_text else None
    vendor_lines = _split_lines(original_content)

    merged = original_content
    llm_tasks: List[Dict[str, Any]] = []
    n_a = n_b = n_mf = 0

    for task in sorted(tasks, key=lambda t: t["replace_start"], reverse=True):
        hs = task["replace_start"]
        he = task["replace_end"]
        pre = int(task.get("pre_len") or 0)
        post = int(task.get("post_len") or 0)
        body = _vendor_body_lines(task["vendor_snippet"], pre, post)
        hunk_body = task.get("hunk_body") or ""
        hunk_old, hunk_new = _parse_hunk_sides(hunk_body) if hunk_body else (body, body)

        kind = classify_hunk(
            vendor_lines=_split_lines(merged),
            base_lines=base_lines,
            hunk_start=hs,
            hunk_end=he,
            hunk_old=hunk_old,
            hunk_new=hunk_new,
        )

        if kind == "B":
            n_b += 1
            continue

        if kind == "A" and hunk_new:
            try:
                validate_merged_hunk_middle(hunk_new, body)
                merged = apply_hunk_merge_to_source(merged, hs, he, hunk_new)
                n_a += 1
                continue
            except ValueError:
                kind = "C"

        if kind == "C" and hunk_body:
            patched, n_ops = apply_rej_hunk_micro_patches(merged, hunk_body)
            if n_ops > 0:
                patched = _sanitize_duplicate_wrrd_msgs_advance(patched)
                merged = patched
                n_a += n_ops
                if _rej_plus_lines_present(merged, hunk_body):
                    continue
                # 微补丁已推进但未完成整 hunk：留给末尾全量 .rej 微补丁，避免 LLM 部分合入
                continue

        if kind == "C" and base_lines is not None and theirs_lines is not None:
            b0 = _locate_hunk_in_source(base_lines, hs, hunk_old) or hs
            t0 = _locate_hunk_in_source(theirs_lines, hs, hunk_new) if hunk_new else hs
            base_body = _slice_at(base_lines, b0, len(hunk_old or body))
            theirs_body = hunk_new or _slice_at(theirs_lines, t0, len(body))
            region_merged = _try_region_merge_file(body, base_body, theirs_body)
            if region_merged is not None:
                try:
                    validate_merged_hunk_middle(region_merged, body)
                    merged = apply_hunk_merge_to_source(merged, hs, he, region_merged)
                    n_mf += 1
                    continue
                except ValueError:
                    pass

        llm_tasks.append(task)

    if llm_tasks:
        from web_app.llm_service import is_llm_configured, resolve_merge_conflict_tasks_via_llm

        if not is_llm_configured():
            raise RuntimeError(
                f"{len(llm_tasks)} 个区域需 LLM 合入，但未配置 API Key"
            )
        merged, llm_summary = resolve_merge_conflict_tasks_via_llm(
            source_path=source_path,
            original_content=merged,
            tasks=llm_tasks,
        )
        notes.append(llm_summary)

    if rej_content.strip():
        patched, n_micro = apply_all_rej_micro_patches(merged, rej_content)
        patched = _sanitize_duplicate_wrrd_msgs_advance(patched)
        if _rej_plus_lines_present(patched, rej_content):
            merged = patched
            if n_micro > 0:
                notes.append(f"rej微补丁补全 {n_micro} 处")
        validate_rej_merge_complete(merged, rej_content)

    if "<<<<<<<" in merged or ">>>>>>>" in merged:
        raise RuntimeError("合并后仍含 git 冲突标记")

    orig_n = len(vendor_lines)
    merg_n = len(_split_lines(merged))
    if orig_n >= 80 and merg_n < int(orig_n * 0.95):
        raise RuntimeError(f"合并后行数异常减少：{merg_n} vs {orig_n}")

    parts = [
        f"A={n_a} 机械",
        f"B={n_b} 保留",
        f"merge_file区域={n_mf}",
        f"C→LLM={len(llm_tasks)}",
    ]
    strategy = "hybrid" if llm_tasks else "deterministic"
    if n_a + n_b + n_mf == 0 and llm_tasks:
        strategy = "llm_diff"
    summary = "；".join(notes + ["，".join(parts)]) if notes else "，".join(parts)
    _log(job_id, f"冲突合入 {source_path}: {summary}")
    return merged, summary, strategy
