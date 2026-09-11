"""Deterministic conflict resolution: 3-way merge, hunk classify, LLM diff fallback."""
from __future__ import annotations

import difflib
import re
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
    build_function_logic_hints,
    collect_conflict_merge_tasks,
    collect_incremental_function_tasks,
    extra_function_defs_introduced,
    extract_function_names_from_hunk_body,
    extract_merged_hunk_body,
    extract_named_c_function,
    function_impl_diverged_from_gki,
    function_names_from_rej,
    rej_has_diverged_function_impl,
    validate_merged_hunk_middle,
    validate_rej_merge_complete,
    assert_micro_inserts_follow_context,
    _micro_inserts_follow_context,
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


def git_merge_file_contents(
    ours: str, base: str, theirs: str, *, diff3: bool = False,
) -> Tuple[str, bool]:
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
        cmd = ["git", "merge-file", "-p"]
        if diff3:
            cmd.append("--diff3")
        cmd.extend([
            str(paths["ours"]), str(paths["base"]), str(paths["theirs"]),
        ])
        proc = subprocess.run(
            cmd,
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


_DIFF3_BLOCK = re.compile(
    r"^<<<<<<<[^\n]*\n"
    r"(?P<ours>.*?)"
    r"^\|{7}[^\n]*\n"
    r"(?P<base>.*?)"
    r"^=======\n"
    r"(?P<theirs>.*?)"
    r"^>>>>>>>[^\n]*\n",
    re.MULTILINE | re.DOTALL,
)


def _resolve_empty_base_conflicts(text: str) -> Optional[str]:
    """Insert-insert (empty diff3 base): keep GKI (theirs) then vendor (ours)."""
    if "<<<<<<<" not in (text or ""):
        return text
    if not _DIFF3_BLOCK.search(text):
        return None
    out: List[str] = []
    pos = 0
    for m in _DIFF3_BLOCK.finditer(text):
        out.append(text[pos:m.start()])
        if (m.group("base") or "").strip():
            return None
        theirs = m.group("theirs") or ""
        ours = m.group("ours") or ""
        chunk = theirs
        if theirs and ours and not theirs.endswith("\n"):
            chunk += "\n"
        chunk += ours
        out.append(chunk)
        pos = m.end()
    out.append(text[pos:])
    resolved = "".join(out)
    if "<<<<<<<" in resolved or ">>>>>>>" in resolved:
        return None
    return resolved


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


def _try_unaligned_rej_micro_patches(
    original_content: str,
    rej_content: str,
    *,
    job_id: str = "",
    source_path: str = "",
) -> Optional[Tuple[str, str, str]]:
    """When hunk windows cannot be aligned, still try context-anchored .rej micro-patches."""
    if not (rej_content or "").strip():
        return None
    patched, n_micro = apply_all_rej_micro_patches(original_content, rej_content)
    patched = _sanitize_duplicate_wrrd_msgs_advance(patched)
    if n_micro <= 0 or not _rej_plus_lines_present(patched, rej_content):
        return None
    if not _micro_inserts_follow_context(patched, rej_content):
        return None
    try:
        validate_rej_merge_complete(patched, rej_content)
    except RuntimeError:
        return None
    dups = extra_function_defs_introduced(original_content, patched, rej_content)
    if dups:
        return None
    orig_n = len(_split_lines(original_content))
    merg_n = len(_split_lines(patched))
    if orig_n >= 80 and merg_n < int(orig_n * 0.95):
        return None
    summary = f"未对齐 hunk，rej微补丁补全 {n_micro} 处"
    _log(job_id, f"冲突合入 {source_path}: {summary}")
    return patched, summary, "deterministic"


_FN_HINT_CHARS = 16000


def _clip_fn_hint(text: str) -> str:
    raw = text or ""
    if len(raw) <= _FN_HINT_CHARS:
        return raw
    return raw[:_FN_HINT_CHARS] + "\n... (truncated)"


def _try_function_level_three_way(
    original_content: str,
    rej_content: str,
    base_text: Optional[str],
    theirs_text: Optional[str],
    *,
    job_id: str = "",
    source_path: str = "",
) -> Optional[Tuple[str, str, str]]:
    """3-way merge each named function (vendor vs GKI-old vs GKI-new)."""
    if not base_text or not theirs_text or not (rej_content or "").strip():
        return None
    names = function_names_from_rej(rej_content)
    if not names:
        return None
    merged = original_content
    applied = 0
    for name in names:
        vendor_fn = extract_named_c_function(merged, name)
        base_fn = extract_named_c_function(base_text, name)
        theirs_fn = extract_named_c_function(theirs_text, name)
        if not vendor_fn or not base_fn or not theirs_fn:
            continue
        start, end, vendor_text = vendor_fn
        try:
            fn_merged, has_markers = git_merge_file_contents(
                vendor_text, base_fn[2], theirs_fn[2], diff3=True,
            )
        except RuntimeError:
            continue
        if has_markers:
            fn_merged = _resolve_empty_base_conflicts(fn_merged) or ""
            has_markers = "<<<<<<<" in fn_merged or ">>>>>>>" in fn_merged
        if has_markers or not fn_merged.strip():
            continue
        candidate = apply_hunk_merge_to_source(
            merged, start, end, _split_lines(fn_merged),
        )
        if extra_function_defs_introduced(original_content, candidate, rej_content):
            continue
        merged = candidate
        applied += 1
    if applied <= 0:
        return None
    if not _rej_plus_lines_present(merged, rej_content):
        return None
    try:
        validate_rej_merge_complete(merged, rej_content)
        assert_micro_inserts_follow_context(merged, rej_content)
    except RuntimeError:
        return None
    orig_n = len(_split_lines(original_content))
    merg_n = len(_split_lines(merged))
    if orig_n >= 80 and merg_n < int(orig_n * 0.95):
        return None
    summary = f"函数级三路合并 {applied} 个函数（对照 GKI 旧/新实现）"
    _log(job_id, f"冲突合入 {source_path}: {summary}")
    return merged, summary, "function_merge"


def _attach_function_impl_hints(
    task: Dict[str, Any],
    source: str,
    base_text: Optional[str],
    theirs_text: Optional[str],
) -> None:
    """Attach GKI-old/new bodies and control-flow notes to assist (not replace) merge."""
    hunk_body = task.get("hunk_body") or ""
    vendor_src = (
        task.get("vendor_function")
        or task.get("body_snippet")
        or task.get("vendor_snippet")
        or source
    )
    names = extract_function_names_from_hunk_body(hunk_body)
    if not names:
        names = function_names_from_rej(hunk_body)
    if names:
        name = names[0]
        vendor_fn = extract_named_c_function(source, name)
        base_fn = extract_named_c_function(base_text, name) if base_text else None
        theirs_fn = extract_named_c_function(theirs_text, name) if theirs_text else None
        if vendor_fn:
            task["vendor_function"] = _clip_fn_hint(vendor_fn[2])
            vendor_src = vendor_fn[2]
        if base_fn:
            task["gki_old_function"] = _clip_fn_hint(base_fn[2])
        if theirs_fn:
            task["gki_new_function"] = _clip_fn_hint(theirs_fn[2])
        if vendor_fn and base_fn and theirs_fn:
            try:
                preview, markers = git_merge_file_contents(
                    vendor_fn[2], base_fn[2], theirs_fn[2], diff3=True,
                )
                if markers:
                    resolved = _resolve_empty_base_conflicts(preview)
                    if resolved is None:
                        task["function_merge_preview"] = _clip_fn_hint(preview)
            except RuntimeError:
                pass
    if hunk_body:
        hint = build_function_logic_hints(hunk_body, vendor_src)
        if hint:
            task["logic_hints"] = hint


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
                dups = extra_function_defs_introduced(
                    original_content, merged, rej_content,
                )
                if dups:
                    notes.append(
                        f"全文件 merge-file 引入重复函数 {', '.join(dups)}，转增量合入"
                    )
                else:
                    _log(job_id, f"三路 merge-file 成功: {source_path}")
                    return (
                        merged,
                        f"git merge-file 三路合并（{job.get('from_tag')} → {job.get('to_tag')}）",
                        "merge_file",
                    )
            else:
                notes.append("全文件 merge-file 含冲突标记，转 hunk 级处理")
        except RuntimeError as exc:
            notes.append(f"全文件 merge-file 失败: {exc}")

    if not rej_content.strip() and not has_conflict_markers:
        raise RuntimeError("无 .rej 且全文件三路合并未成功，需人工处理")

    vendor_lines = _split_lines(original_content)
    diverged = rej_has_diverged_function_impl(original_content, rej_content)
    if diverged:
        # Same-name function, different body: never paste GKI function; apply +/- first.
        micro = _try_unaligned_rej_micro_patches(
            original_content, rej_content, job_id=job_id, source_path=source_path,
        )
        if micro:
            return micro

    tasks = collect_conflict_merge_tasks(
        original_content=original_content,
        rej_content=rej_content,
        has_conflict_markers=has_conflict_markers,
    )
    if not tasks:
        # 厂商仓行号漂移时 .rej hunk 对不齐当前文件，整段定位会失败；
        # 微补丁按 context/-/+ 小组定位，不依赖 @@ 行号。
        micro = _try_unaligned_rej_micro_patches(
            original_content, rej_content, job_id=job_id, source_path=source_path,
        )
        if micro:
            return micro
        tasks = collect_incremental_function_tasks(original_content, rej_content)
        if not tasks:
            fn = _try_function_level_three_way(
                original_content, rej_content, base_text, theirs_text,
                job_id=job_id, source_path=source_path,
            )
            if fn:
                return fn
            raise RuntimeError(
                "无法在当前源文件中定位 .rej hunk（行号漂移或厂商改动过大），请手动合入"
            )
        notes.append("函数实现与 GKI 旧代码不同，按 vendor 函数增量合入")

    if base_text and theirs_text and rej_content.strip():
        fn = _try_function_level_three_way(
            original_content, rej_content, base_text, theirs_text,
            job_id=job_id, source_path=source_path,
        )
        if fn:
            merged_fn, summary, strategy = fn
            text = "；".join(notes + [summary]) if notes else summary
            return merged_fn, text, strategy

    base_lines = _split_lines(base_text) if base_text else None
    theirs_lines = _split_lines(theirs_text) if theirs_text else None

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
        incremental = bool(task.get("incremental_only")) or (
            bool(hunk_body)
            and function_impl_diverged_from_gki(vendor_lines, hunk_old, hunk_body)
        )
        if incremental:
            task["incremental_only"] = True
            task["incoming_snippet"] = ""
            task["incoming_body_snippet"] = ""

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

        # Diverged impl: do not replace vendor function with GKI hunk_new.
        if kind == "A" and hunk_new and not incremental:
            try:
                validate_merged_hunk_middle(hunk_new, body)
                candidate = apply_hunk_merge_to_source(merged, hs, he, hunk_new)
                dups = extra_function_defs_introduced(
                    original_content, candidate, hunk_body or rej_content,
                )
                if dups:
                    kind = "C"
                else:
                    merged = candidate
                    n_a += 1
                    continue
            except ValueError:
                kind = "C"

        if (kind == "C" or incremental) and hunk_body:
            patched, n_ops = apply_rej_hunk_micro_patches(merged, hunk_body)
            if n_ops > 0:
                patched = _sanitize_duplicate_wrrd_msgs_advance(patched)
                merged = patched
                n_a += n_ops
                if _rej_plus_lines_present(merged, hunk_body):
                    continue
                if not incremental:
                    # 微补丁已推进但未完成整 hunk：留给末尾全量 .rej 微补丁，避免 LLM 部分合入
                    continue

        if (
            kind == "C"
            and not incremental
            and base_lines is not None
            and theirs_lines is not None
        ):
            b0 = _locate_hunk_in_source(base_lines, hs, hunk_old) or hs
            t0 = _locate_hunk_in_source(theirs_lines, hs, hunk_new) if hunk_new else hs
            base_body = _slice_at(base_lines, b0, len(hunk_old or body))
            theirs_body = hunk_new or _slice_at(theirs_lines, t0, len(body))
            region_merged = _try_region_merge_file(body, base_body, theirs_body)
            if region_merged is not None:
                try:
                    validate_merged_hunk_middle(region_merged, body)
                    candidate = apply_hunk_merge_to_source(merged, hs, he, region_merged)
                    dups = extra_function_defs_introduced(
                        original_content, candidate, hunk_body or rej_content,
                    )
                    if not dups:
                        merged = candidate
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
        for task in llm_tasks:
            if task.get("incremental_only"):
                task["incoming_snippet"] = ""
                task["incoming_body_snippet"] = ""
            _attach_function_impl_hints(task, merged, base_text, theirs_text)
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
        assert_micro_inserts_follow_context(merged, rej_content)
        dups = extra_function_defs_introduced(original_content, merged, rej_content)
        if dups:
            raise RuntimeError(
                "合入结果出现重复函数定义（"
                + ", ".join(dups)
                + "）：已拒绝把 GKI 整函数贴入 vendor 实现"
            )

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
