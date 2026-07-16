"""LLM unified-diff normalization, multi-stage apply, verification, sibling propagation."""
from __future__ import annotations

import difflib
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_HUNK_HEADER_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@",
    re.MULTILINE,
)
_DIFF_HEADER_GLUE_RE = re.compile(
    r"(---\s+\S+)\s*(\+\+\+\s+\S+)\s*(@@ -?\d+(?:,\d+)? \+\d+(?:,\d+)? @@)",
)
_FENCE_RE = re.compile(r"^```(?:diff|patch)?\s*$", re.MULTILINE | re.IGNORECASE)
_HUNK_FUZZ = 15

# Protected includes: reject diff that deletes them unless file no longer needs them.
_PROTECTED_INCLUDE_PREFIXES = (
    "#include <linux/version.h>",
    "#include <linux/types.h>",
    "#include <linux/kernel.h>",
)
_DEVICE_ATTR_RE = re.compile(r"\bDEVICE_ATTR\s*\(\s*(\w+)\s*,")
_IFNDEF_GUARD_RE = re.compile(r"#\s*ifndef\s+(\S+)")
_AMBIGUOUS_COMMENT_DELETE_RE = re.compile(
    r"^\s*(?:\*/|\*(?:\s*$)|/\*(?!\*))\s*$"
)
_ORPHAN_KERNEL_DOC_RE = re.compile(r"^\s+\*(?:\s+[^/*]|$)")
_ORPHAN_COMMENT_CLOSE_RE = re.compile(r"^\s*\*/\s*$")


@dataclass
class ApplyResult:
    """Outcome of processing one LLM fix against on-disk content."""

    content: Optional[str]
    error: Optional[str] = None
    strategy: str = "failed"
    processed_diff: str = ""
    warnings: Tuple[str, ...] = ()


def looks_like_unified_diff(text: str) -> bool:
    return bool(_HUNK_HEADER_RE.search(text or ""))


def _diff_line_equal(file_line: str, patch_line: str) -> bool:
    if file_line == patch_line:
        return True
    if file_line.strip() == patch_line.strip():
        return True
    return re.sub(r"\s+", " ", file_line.strip()) == re.sub(
        r"\s+", " ", patch_line.strip()
    )


def strip_diff_fences(text: str) -> str:
    if not text:
        return text
    lines = text.splitlines()
    if lines and _FENCE_RE.match(lines[0].strip()):
        lines = lines[1:]
    while lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines)


def repair_malformed_diff_headers(text: str) -> str:
    """Fix glued ``--- a/x+++ b/x@@ -1,1 +1,0 @@`` lines from LLM output."""
    if not text:
        return text
    out = _DIFF_HEADER_GLUE_RE.sub(r"\1\n\2\n\3", text)
    # Separate @@ glued to prior line without newline
    out = re.sub(
        r"(\+\+\+ [^\n]+)(@@ -?\d)",
        r"\1\n\2",
        out,
    )
    out = re.sub(
        r"(--- [^\n]+)(\+\+\+ )",
        r"\1\n\2",
        out,
    )
    return out


def sanitize_empty_delete_lines(diff_text: str) -> str:
    """Drop bogus empty ``-`` lines that break relaxed matching."""
    if not diff_text or not looks_like_unified_diff(diff_text):
        return diff_text
    kept: List[str] = []
    for line in diff_text.splitlines():
        if line.startswith("-") and len(line) == 1:
            continue
        if line.startswith("-") and not line[1:].strip():
            continue
        kept.append(line)
    out = "\n".join(kept)
    if diff_text.endswith("\n"):
        out += "\n"
    return out


def normalize_llm_diff(raw: str) -> str:
    """Full diff cleanup pipeline before apply."""
    text = (raw or "").strip()
    text = strip_diff_fences(text)
    text = repair_malformed_diff_headers(text)
    text = sanitize_empty_delete_lines(text)
    return text


def split_unified_diff_by_file(diff_text: str) -> List[Tuple[str, str]]:
    """Split a multi-file unified diff into (path, single_file_diff) pairs."""
    if not diff_text.strip():
        return []
    lines = diff_text.splitlines()
    chunks: List[List[str]] = []
    current: List[str] = []
    current_path = ""

    def flush() -> None:
        nonlocal current, current_path
        if current and looks_like_unified_diff("\n".join(current)):
            chunks.append((current_path, "\n".join(current) + "\n"))
        current = []
        current_path = ""

    for line in lines:
        if line.startswith("--- "):
            flush()
            current = [line]
            m = re.match(r"--- (?:a/)?(.+?)(?:\t|$)", line[4:].strip())
            current_path = (m.group(1) if m else line[4:].strip()).strip()
            continue
        if current:
            current.append(line)
    flush()
    if chunks:
        return chunks
    if looks_like_unified_diff(diff_text):
        return [("", diff_text if diff_text.endswith("\n") else diff_text + "\n")]
    return []


def _clean_hunk_ops(ops: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    return [(tag, data) for tag, data in ops if not (tag == "-" and not data.strip())]


def parse_diff_hunks(diff_text: str) -> List[Tuple[int, List[Tuple[str, str]]]]:
    patch_lines = diff_text.splitlines()
    hunks: List[Tuple[int, List[Tuple[str, str]]]] = []
    i = 0
    while i < len(patch_lines):
        line = patch_lines[i]
        if not line.startswith("@@"):
            i += 1
            continue
        m = _HUNK_HEADER_RE.match(line)
        if not m:
            raise ValueError(f"无效的 diff hunk: {line[:120]}")
        old_start = max(0, int(m.group(1)) - 1)
        ops: List[Tuple[str, str]] = []
        i += 1
        while i < len(patch_lines) and not patch_lines[i].startswith("@@"):
            pl = patch_lines[i]
            if pl.startswith(("---", "+++")) or not pl:
                i += 1
                continue
            if pl[0] == "\\":
                i += 1
                continue
            tag = pl[0]
            if tag not in (" ", "-", "+"):
                raise ValueError(f"未知 diff 行前缀: {pl[:40]!r}")
            ops.append((tag, pl[1:]))
            i += 1
        ops = _clean_hunk_ops(ops)
        if ops:
            hunks.append((old_start, ops))
    if not hunks:
        raise ValueError("未找到有效的 @@ hunk 头")
    return hunks


def _find_hunk_position(
    orig_lines: List[str],
    ops: List[Tuple[str, str]],
    hint_start: int,
    *,
    fuzz: int = _HUNK_FUZZ,
) -> Optional[int]:
    needle = [(tag, data) for tag, data in ops if tag in (" ", "-")]
    if not needle:
        return min(hint_start, len(orig_lines))

    def matches_at(pos: int) -> bool:
        for k, (_, data) in enumerate(needle):
            idx = pos + k
            if idx >= len(orig_lines):
                return False
            if not _diff_line_equal(orig_lines[idx], data):
                return False
        return True

    lo = max(0, hint_start - fuzz)
    hi = min(len(orig_lines), hint_start + fuzz + 1)
    for pos in range(lo, hi):
        if matches_at(pos):
            return pos
    limit = len(orig_lines) - len(needle) + 1
    for pos in range(0, max(0, limit)):
        if matches_at(pos):
            return pos
    return None


def _find_hunk_by_deletes(
    orig_lines: List[str],
    ops: List[Tuple[str, str]],
) -> Optional[int]:
    deletes = [data for tag, data in ops if tag == "-" and data.strip()]
    if not deletes:
        return None
    n = len(deletes)
    for pos in range(len(orig_lines) - n + 1):
        if all(_diff_line_equal(orig_lines[pos + i], deletes[i]) for i in range(n)):
            return pos
    return None


def _find_hunk_by_deletes_fuzzy(
    orig_lines: List[str],
    ops: List[Tuple[str, str]],
) -> Optional[int]:
    """Match delete lines individually when consecutive block match fails."""
    deletes = [data for tag, data in ops if tag == "-" and data.strip()]
    if not deletes:
        return None
    first = deletes[0]
    for pos in range(len(orig_lines)):
        if not _diff_line_equal(orig_lines[pos], first):
            continue
        ok = True
        for i, data in enumerate(deletes):
            idx = pos + i
            if idx >= len(orig_lines) or not _diff_line_equal(orig_lines[idx], data):
                ok = False
                break
        if ok:
            return pos
    return None


def _ops_from_first_delete(ops: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    idx = next((i for i, (t, _) in enumerate(ops) if t == "-"), len(ops))
    return ops[idx:]


def _splice_hunk(
    orig_lines: List[str], start: int, ops: List[Tuple[str, str]]
) -> List[str]:
    out = list(orig_lines[:start])
    idx = start
    for tag, data in ops:
        if tag == " ":
            if idx < len(orig_lines):
                out.append(orig_lines[idx])
                idx += 1
        elif tag == "-":
            if idx < len(orig_lines):
                idx += 1
        elif tag == "+":
            out.append(data)
    out.extend(orig_lines[idx:])
    return out


def apply_unified_diff_strict(original: str, diff_text: str) -> str:
    orig_lines = original.splitlines()
    hunks = parse_diff_hunks(diff_text)
    out: List[str] = []
    orig_idx = 0

    for hint_start, ops in hunks:
        pos = _find_hunk_position(orig_lines, ops, hint_start)
        if pos is None:
            sample = next((data for tag, data in ops if tag in (" ", "-")), "")
            raise ValueError(
                f"diff 上下文无法在文件中定位（hint 第 {hint_start + 1} 行）: {sample[:80]!r}"
            )
        while orig_idx < pos:
            out.append(orig_lines[orig_idx])
            orig_idx += 1
        for tag, data in ops:
            if tag == " ":
                if orig_idx >= len(orig_lines) or not _diff_line_equal(
                    orig_lines[orig_idx], data
                ):
                    raise ValueError(
                        f"diff 上下文不匹配 (约第 {orig_idx + 1} 行): {data[:80]!r}"
                    )
                out.append(orig_lines[orig_idx])
                orig_idx += 1
            elif tag == "-":
                if orig_idx >= len(orig_lines) or not _diff_line_equal(
                    orig_lines[orig_idx], data
                ):
                    raise ValueError(
                        f"diff 删除行不匹配 (约第 {orig_idx + 1} 行): {data[:80]!r}"
                    )
                orig_idx += 1
            elif tag == "+":
                out.append(data)

    out.extend(orig_lines[orig_idx:])
    merged = "\n".join(out)
    if original.endswith("\n"):
        merged += "\n"
    return merged


def apply_unified_diff_relaxed(original: str, diff_text: str) -> str:
    orig_lines = original.splitlines()
    hunks = parse_diff_hunks(diff_text)
    placements: List[Tuple[int, List[Tuple[str, str]]]] = []
    for hint_start, ops in hunks:
        delete_pos = _find_hunk_by_deletes(orig_lines, ops)
        if delete_pos is None:
            delete_pos = _find_hunk_by_deletes_fuzzy(orig_lines, ops)
        if delete_pos is None:
            sample = next((data for tag, data in ops if tag == "-" and data.strip()), "")
            if not sample:
                sample = next((data for tag, data in ops if tag in (" ", "-")), "")
            raise ValueError(
                f"diff 删除行无法在文件中定位: {sample[:80]!r}"
            )
        placements.append((delete_pos, _ops_from_first_delete(ops)))
    for start, ops in sorted(placements, key=lambda x: x[0], reverse=True):
        orig_lines = _splice_hunk(orig_lines, start, ops)
    merged = "\n".join(orig_lines)
    if original.endswith("\n"):
        merged += "\n"
    return merged


def apply_unified_diff_delete_only(original: str, diff_text: str) -> str:
    """Apply only delete lines from hunks; ignore stale context/add lines."""
    orig_lines = original.splitlines()
    hunks = parse_diff_hunks(diff_text)
    delete_ops: List[Tuple[int, List[str]]] = []
    for _hint, ops in hunks:
        deletes = [data for tag, data in ops if tag == "-" and data.strip()]
        if not deletes:
            continue
        pos = _find_hunk_by_deletes(orig_lines, ops)
        if pos is None:
            pos = _find_hunk_by_deletes_fuzzy(orig_lines, ops)
        if pos is None:
            raise ValueError(
                f"diff 删除行无法在文件中定位: {deletes[0][:80]!r}"
            )
        delete_ops.append((pos, deletes))

    for pos, deletes in sorted(delete_ops, key=lambda x: x[0], reverse=True):
        for i, data in enumerate(deletes):
            idx = pos + i
            if idx >= len(orig_lines):
                raise ValueError(f"diff 删除行超出文件 (约第 {idx + 1} 行): {data[:80]!r}")
            if not _diff_line_equal(orig_lines[idx], data):
                raise ValueError(
                    f"diff 删除行不匹配 (约第 {idx + 1} 行): {data[:80]!r}"
                )
        del orig_lines[pos : pos + len(deletes)]

    merged = "\n".join(orig_lines)
    if original.endswith("\n"):
        merged += "\n"
    return merged


def apply_unified_diff(original: str, diff_text: str) -> str:
    try:
        return apply_unified_diff_strict(original, diff_text)
    except ValueError:
        return apply_unified_diff_relaxed(original, diff_text)


def _scan_c_like_structure(text: str) -> Tuple[int, List[str]]:
    """Return (block_comment_depth_at_eof, #ifndef guard names visible at depth 0)."""
    depth = 0
    ifndef_names: List[str] = []
    active_line: List[str] = []
    i = 0
    n = len(text or "")

    def flush_line() -> None:
        nonlocal active_line
        if depth == 0:
            m = _IFNDEF_GUARD_RE.search("".join(active_line))
            if m:
                ifndef_names.append(m.group(1))
        active_line = []

    while i < n:
        ch = text[i]
        if ch == "\n":
            flush_line()
            i += 1
            continue
        if depth == 0 and text.startswith("//", i):
            flush_line()
            while i < n and text[i] != "\n":
                i += 1
            continue
        if depth == 0 and text.startswith("/*", i):
            flush_line()
            depth = 1
            i += 2
            continue
        if depth > 0 and text.startswith("*/", i):
            depth -= 1
            i += 2
            continue
        if depth == 0 and ch == '"':
            active_line.append(ch)
            i += 1
            while i < n and text[i] != '"':
                if text[i] == "\\":
                    active_line.append(text[i])
                    i += 1
                    if i < n:
                        active_line.append(text[i])
                        i += 1
                    continue
                active_line.append(text[i])
                i += 1
            if i < n:
                active_line.append(text[i])
                i += 1
            continue
        if depth == 0 and ch == "'":
            active_line.append(ch)
            i += 1
            while i < n and text[i] != "'":
                if text[i] == "\\":
                    active_line.append(text[i])
                    i += 1
                    if i < n:
                        active_line.append(text[i])
                        i += 1
                    continue
                active_line.append(text[i])
                i += 1
            if i < n:
                active_line.append(text[i])
                i += 1
            continue
        if depth == 0:
            active_line.append(ch)
        i += 1
    flush_line()
    return depth, ifndef_names


def detect_comment_structure_damage(text: str) -> Optional[str]:
    """Detect orphan kernel-doc / stray `` */`` at block-comment depth 0."""
    return _orphan_comment_fragment_error(text)


def _prev_line_continues_c_expr(lines: List[str], idx: int) -> bool:
    """Whether lines[idx] is likely `` * rhs`` continuing a multi-line C expression."""
    if idx <= 0:
        return False
    for j in range(idx - 1, max(idx - 6, -1), -1):
        prev = lines[j].strip()
        if not prev:
            continue
        if prev.endswith((
            "(", ",", "+", "-", "*", "/", "%", "|", "&", "^",
            "=", "?", ":", "||", "&&", "<<", ">>",
        )):
            return True
        if "sizeof(" in prev or prev.endswith("sizeof"):
            return True
        if not prev.endswith((";", "{", "}")) and prev[-1] in "(=+-*&|?:,":
            return True
        return False
    return False


def _is_c_multiply_or_deref_star_line(line: str, lines: List[str], idx: int) -> bool:
    """Distinguish `` * MAX_N`` / `` * ptr`` code from kernel-doc `` * @param`` lines."""
    m = re.match(r"^\s+\*(\s*)(.+)$", line)
    if not m:
        return False
    rest = (m.group(2) or "").strip()
    if not rest:
        return False
    if rest.startswith("@"):
        return False
    if _prev_line_continues_c_expr(lines, idx):
        return True
    if re.match(r"[A-Z][A-Z0-9_]*", rest):
        return True
    if rest[0] in "([":
        return True
    if re.match(r"[A-Za-z_]\w*", rest) and rest.endswith((";", ",", ")", "||", "&&")):
        return True
    return False


def _orphan_comment_fragment_error(text: str) -> Optional[str]:
    """Detect kernel-doc fragments or stray `` */`` at block-comment depth 0."""
    lines = (text or "").splitlines()
    in_block = False
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not in_block:
            if stripped.startswith("/*"):
                if "*/" in stripped[2:]:
                    continue
                in_block = True
                continue
            if _ORPHAN_COMMENT_CLOSE_RE.match(line):
                return (
                    f"第 {i} 行存在孤立的 ` */`（可能误删 `/**`），"
                    "头文件结构异常，已拒绝写回"
                )
            if _ORPHAN_KERNEL_DOC_RE.match(line):
                if _is_c_multiply_or_deref_star_line(line, lines, i - 1):
                    continue
                return (
                    f"第 {i} 行存在孤立的 kernel-doc 注释行（可能误删 `/**`），"
                    "头文件结构异常，已拒绝写回"
                )
            continue
        if "*/" in stripped:
            in_block = False
    return None


def structural_integrity_error(before: str, after: str) -> Optional[str]:
    """Reject patches that break block comments or comment-out include guards."""
    return _structural_integrity_error(before, after)


def _structural_integrity_error(before: str, after: str) -> Optional[str]:
    """Reject patches that break block comments or comment-out include guards."""
    before_depth, before_guards = _scan_c_like_structure(before)
    after_depth, after_guards = _scan_c_like_structure(after)

    if after_depth > 0:
        return (
            "修复后块注释未闭合（可能误删 ` */` 或 `/*`），"
            "导致后续 `#ifndef`/代码被注释掉，已拒绝写回"
        )
    if before_depth == 0 and after_depth != 0:
        return "修复引入了未闭合的块注释，已拒绝写回"

    orphan_err = _orphan_comment_fragment_error(after)
    if orphan_err:
        before_orphan = _orphan_comment_fragment_error(before)
        if before_orphan:
            return (
                f"{orphan_err} "
                "（磁盘文件此前已有注释结构损坏，可能来自更早的错误写回；"
                "须先修复孤立注释，再仅删除冲突 `#define`）"
            )
        return orphan_err

    missing = [g for g in before_guards if g not in after_guards]
    if missing:
        sample = ", ".join(missing[:3])
        return (
            f"修复后活跃代码中丢失 #ifndef 保护（{sample}），"
            "可能误删注释结束符导致头文件守卫失效，已拒绝写回"
        )
    return None


def _is_ambiguous_comment_delete_line(line: str) -> bool:
    return bool(_AMBIGUOUS_COMMENT_DELETE_RE.match(line or ""))


def _delete_line_has_define(line: str) -> bool:
    return bool(re.search(r"#\s*define\s+\w+", line or ""))


def validate_llm_diff_safety(diff_text: str) -> Optional[str]:
    """Reject diffs that would likely delete the wrong comment block (e.g. file header)."""
    if not diff_text or not looks_like_unified_diff(diff_text):
        return None
    try:
        hunks = parse_diff_hunks(diff_text)
    except ValueError:
        return None
    for hint_start, ops in hunks:
        deletes = [data for tag, data in ops if tag == "-" and data.strip()]
        if not deletes:
            continue
        has_define = any(_delete_line_has_define(d) for d in deletes)
        starts_with_comment = any(
            d.strip().startswith("/**")
            or d.strip().startswith("/*")
            or _is_ambiguous_comment_delete_line(d)
            for d in deletes[:2]
        )
        if starts_with_comment and not has_define:
            return (
                "diff hunk 以孤立注释删除行起笔且不含 #define，"
                "会误删文件头 kernel-doc；请以 note 处 #define 为锚点重写 hunk"
            )
        if hint_start < 20 and starts_with_comment and not has_define:
            return (
                f"diff hunk 锚定在文件前部（约第 {hint_start + 1} 行）且删除注释却无 #define，"
                "已拒绝模拟应用"
            )
    return None


def _find_deletes_anchored_on_define(
    orig_lines: List[str],
    deletes: List[str],
    hint_start: int,
    *,
    fuzz: int = 40,
) -> Optional[List[int]]:
    """Prefer contiguous matches where a ``#define`` line in the hunk anchors the block."""
    define_offsets = [
        i for i, data in enumerate(deletes) if _delete_line_has_define(data)
    ]
    if not define_offsets:
        return None
    def_off = define_offsets[0]
    define_line = deletes[def_off]
    lo = max(0, hint_start - fuzz)
    hi = min(len(orig_lines), hint_start + fuzz + len(deletes) + 10)
    for start in range(lo, hi):
        define_idx = start + def_off
        if define_idx >= len(orig_lines):
            continue
        if not _diff_line_equal(orig_lines[define_idx], define_line):
            continue
        block_start = start
        if block_start + len(deletes) > len(orig_lines):
            continue
        indices = list(range(block_start, block_start + len(deletes)))
        if all(
            _diff_line_equal(orig_lines[idx], deletes[j])
            for j, idx in enumerate(indices)
        ):
            return indices
    return None


def _find_delete_indices_near_hint(
    orig_lines: List[str],
    deletes: List[str],
    hint_start: int,
    *,
    fuzz: int = 40,
) -> Optional[List[int]]:
    """Match delete lines in order within a window around the hunk hint."""
    if not deletes:
        return None
    if len(deletes) == 1 and _is_ambiguous_comment_delete_line(deletes[0]):
        if (
            0 <= hint_start < len(orig_lines)
            and _diff_line_equal(orig_lines[hint_start], deletes[0])
            and hint_start >= 20
        ):
            return [hint_start]
        return None

    lo = max(0, hint_start - fuzz)
    hi = min(len(orig_lines), hint_start + fuzz + len(deletes) + 20)
    best: Optional[List[int]] = None
    for start in range(lo, hi):
        idx = start
        indices: List[int] = []
        for data in deletes:
            while idx < len(orig_lines) and not _diff_line_equal(orig_lines[idx], data):
                idx += 1
            if idx >= len(orig_lines):
                break
            indices.append(idx)
            idx += 1
        if len(indices) == len(deletes):
            if best is None or indices[0] < best[0]:
                best = indices
    return best


def _find_contiguous_deletes(
    orig_lines: List[str],
    deletes: List[str],
    hint_start: int,
    *,
    fuzz: int = 40,
) -> Optional[int]:
    if not deletes:
        return None
    n = len(deletes)
    lo = max(0, hint_start - fuzz)
    hi = min(len(orig_lines) - n + 1, hint_start + fuzz + 1)
    for pos in range(lo, hi):
        if all(
            _diff_line_equal(orig_lines[pos + i], deletes[i])
            for i in range(n)
        ):
            return pos
    return None


def apply_unified_diff_delete_individual(original: str, diff_text: str) -> str:
    """Apply per-hunk deletes near @@ hint (avoid global first-match on comment fragments)."""
    orig_lines = original.splitlines()
    hunks = parse_diff_hunks(diff_text)
    delete_indices: List[int] = []

    for hint_start, ops in hunks:
        deletes = [data for tag, data in ops if tag == "-" and data.strip()]
        if not deletes:
            continue
        pos = _find_hunk_by_deletes(orig_lines, ops)
        indices: Optional[List[int]] = None
        if pos is not None:
            indices = list(range(pos, pos + len(deletes)))
        else:
            pos = _find_hunk_by_deletes_fuzzy(orig_lines, ops)
            if pos is not None:
                indices = list(range(pos, pos + len(deletes)))
        if indices is None:
            indices = _find_deletes_anchored_on_define(orig_lines, deletes, hint_start)
        if indices is None:
            pos = _find_contiguous_deletes(orig_lines, deletes, hint_start)
            if pos is not None:
                indices = list(range(pos, pos + len(deletes)))
        if indices is None:
            indices = _find_delete_indices_near_hint(orig_lines, deletes, hint_start)
        if not indices:
            raise ValueError(
                f"diff 删除行无法在 hunk 附近匹配（hint 第 {hint_start + 1} 行）: "
                f"{deletes[0][:80]!r}"
            )
        delete_indices.extend(indices)

    for idx in sorted(set(delete_indices), reverse=True):
        del orig_lines[idx]

    merged = "\n".join(orig_lines)
    if original.endswith("\n"):
        merged += "\n"
    return merged


def apply_diff_with_fallbacks(original: str, diff_text: str) -> Tuple[str, str]:
    """Try strict → relaxed → delete-only → individual-delete apply."""
    stages: List[Tuple[str, Callable[[str, str], str]]] = [
        ("strict", apply_unified_diff_strict),
        ("relaxed", apply_unified_diff_relaxed),
        ("delete_only", apply_unified_diff_delete_only),
        ("delete_individual", apply_unified_diff_delete_individual),
    ]
    last_err: Optional[Exception] = None
    for name, fn in stages:
        try:
            return fn(original, diff_text), name
        except ValueError as exc:
            last_err = exc
            continue
    raise ValueError(str(last_err) if last_err else "diff 无法应用")


def verify_patch_result(
    before: str,
    after: str,
    *,
    diff_text: str = "",
) -> Tuple[Optional[str], Tuple[str, ...]]:
    """Post-apply safety checks. Returns (error, warnings)."""
    warnings: List[str] = []
    if before == after:
        return None, tuple(warnings)

    before_lines = before.splitlines()
    after_lines = after.splitlines()
    if not after_lines and before_lines:
        return "修复后文件为空，已拒绝写回", tuple(warnings)

    if diff_text and looks_like_unified_diff(diff_text):
        try:
            hunks = parse_diff_hunks(diff_text)
        except ValueError:
            hunks = []
        deleted_in_diff = {
            data.strip()
            for _hs, ops in hunks
            for tag, data in ops
            if tag == "-" and data.strip()
        }
        for prefix in _PROTECTED_INCLUDE_PREFIXES:
            if prefix in before and prefix not in after:
                return (
                    f"修复误删受保护 include: {prefix}",
                    tuple(warnings),
                )

    struct_err = _structural_integrity_error(before, after)
    if struct_err:
        return struct_err, tuple(warnings)

    after = _dedupe_device_attr_in_after(before, after)
    dup_err = _duplicate_device_attr_error(after)
    if dup_err:
        return dup_err, tuple(warnings)
    return None, tuple(warnings)


def _duplicate_device_attr_error(after: str) -> Optional[str]:
    """Reject patches that introduce duplicate DEVICE_ATTR(name) in one file."""
    from collections import Counter
    names = _DEVICE_ATTR_RE.findall(after or "")
    if not names:
        return None
    counts = Counter(names)
    for name, cnt in counts.items():
        if cnt > 1:
            return f"修复后重复 DEVICE_ATTR({name})，请合并为一处"
    return None


def _dedupe_device_attr_in_after(before: str, after: str) -> str:
    """Drop newly added DEVICE_ATTR(name) lines when name already exists in before."""
    from collections import Counter
    counts = Counter(_DEVICE_ATTR_RE.findall(before or ""))
    if not counts:
        return after
    before_stripped = {ln.strip() for ln in (before or "").splitlines()}
    out: List[str] = []
    for line in (after or "").splitlines(keepends=True):
        m = _DEVICE_ATTR_RE.search(line)
        if m and counts[m.group(1)] >= 1 and line.strip() not in before_stripped:
            continue
        if m:
            counts[m.group(1)] += 1
        out.append(line)
    return "".join(out)


def process_llm_fix_content(before: str, raw_content: str) -> ApplyResult:
    """Normalize LLM output and apply via multi-stage diff pipeline."""
    text = (raw_content or "").strip()
    if not text:
        return ApplyResult(None, "修复内容为空", "failed")

    normalized = normalize_llm_diff(text)
    if looks_like_unified_diff(normalized):
        safety_err = validate_llm_diff_safety(normalized)
        if safety_err:
            return ApplyResult(None, safety_err, "failed", processed_diff=normalized)
        try:
            after, strategy = apply_diff_with_fallbacks(before, normalized)
        except ValueError as exc:
            return ApplyResult(None, str(exc), "failed", processed_diff=normalized)
        if after == before:
            return ApplyResult(
                after,
                None,
                "already_applied",
                processed_diff=normalized,
            )
        after = _dedupe_device_attr_in_after(before, after)
        verr, warnings = verify_patch_result(before, after, diff_text=normalized)
        if verr:
            return ApplyResult(
                None,
                verr,
                "verify_failed",
                processed_diff=normalized,
                warnings=warnings,
            )
        return ApplyResult(
            after,
            None,
            strategy,
            processed_diff=normalized,
            warnings=warnings,
        )

    if text == before:
        return ApplyResult(text, None, "already_applied")
    verr, warnings = verify_patch_result(before, text)
    if verr:
        return ApplyResult(None, verr, "verify_failed", warnings=warnings)
    return ApplyResult(text, None, "full_replace", warnings=warnings)


def _is_windows_unc(path_str: str) -> bool:
    s = (path_str or "").strip()
    return s.startswith("\\\\") or (len(s) >= 2 and s[1] == ":")


def find_files_by_basename(
    build_workdir: str,
    basename: str,
    *,
    exclude_abs: Optional[str] = None,
    limit: int = 32,
) -> List[Tuple[str, str]]:
    """Return [(abs_path, rel_path), ...] under build_workdir vendor/ and kernel-5.10/."""
    if not build_workdir or not basename or basename in (".", ".."):
        return []
    root = Path(build_workdir)
    if not root.is_dir():
        return []
    hits: List[Tuple[str, str]] = []
    exclude_norm = (exclude_abs or "").replace("\\", "/").lower()
    for sub in ("vendor", "kernel-5.10"):
        base = root / sub
        if not base.is_dir():
            continue
        try:
            for p in base.rglob(basename):
                if not p.is_file():
                    continue
                abs_p = str(p)
                if exclude_norm and abs_p.replace("\\", "/").lower() == exclude_norm:
                    continue
                try:
                    rel = p.relative_to(root).as_posix()
                except ValueError:
                    rel = abs_p
                hits.append((abs_p, rel))
                if len(hits) >= limit:
                    return hits
        except OSError:
            continue
    return hits


def retarget_diff_path(diff_text: str, new_path: str) -> str:
    """Rewrite ---/+++ headers to target a different file path."""
    if not diff_text or not new_path:
        return diff_text
    lines = diff_text.splitlines()
    out: List[str] = []
    for line in lines:
        if line.startswith("--- "):
            out.append(f"--- a/{new_path}")
        elif line.startswith("+++ "):
            out.append(f"+++ b/{new_path}")
        else:
            out.append(line)
    result = "\n".join(out)
    if diff_text.endswith("\n"):
        result += "\n"
    return result


def try_apply_to_sibling_files(
    *,
    source_rel: str,
    source_abs: str,
    processed_diff: str,
    build_workdir: str,
    read_file: Callable[[str], str],
    file_identity_key: Callable[[str], str],
    already_fixed_identities: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    """Apply the same processed diff to other files with the same basename."""
    basename = posixpath.basename(source_rel.replace("\\", "/"))
    if not basename or not processed_diff:
        return []

    fixed = already_fixed_identities or set()
    fixed.add(file_identity_key(source_abs))
    siblings = find_files_by_basename(
        build_workdir,
        basename,
        exclude_abs=source_abs,
    )
    applied: List[Dict[str, Any]] = []
    for abs_p, rel in siblings:
        ident = file_identity_key(abs_p)
        if ident in fixed:
            continue
        try:
            before = read_file(abs_p)
        except (OSError, FileNotFoundError):
            continue
        sib_diff = retarget_diff_path(processed_diff, rel)
        result = process_llm_fix_content(before, sib_diff)
        if result.error or result.content is None:
            continue
        if result.content == before:
            fixed.add(ident)
            continue
        applied.append({
            "abs_path": abs_p,
            "rel_path": rel,
            "content": result.content,
            "strategy": f"sibling_{result.strategy}",
            "llm_fix_content": sib_diff,
            "processed_diff": result.processed_diff or sib_diff,
            "warnings": result.warnings,
        })
        fixed.add(ident)
    return applied
