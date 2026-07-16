"""Extract conflict hunks for Gerrit-style side-by-side diff UI."""
from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Optional, Tuple

_CONTEXT_LINES = 5
_MAX_REGION_LINES = 600

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)
_MARKER_BLOCK = re.compile(
    r"^<<<<<<<[^\n]*\n(.*?)\n=======\n(.*?)\n>>>>>>>[^\n]*",
    re.MULTILINE | re.DOTALL,
)

RejHunk = Tuple[int, int, int, int, str]  # old_start0, old_count, new_start0, new_count, body


def _split_lines(text: str) -> List[str]:
    if not text:
        return []
    return text.splitlines()


def _parse_hunk_sides(hunk_body: str) -> Tuple[List[str], List[str]]:
    """Split unified-diff hunk body into old-file and new-file line lists."""
    old_lines: List[str] = []
    new_lines: List[str] = []
    for hline in hunk_body.splitlines():
        if not hline:
            continue
        tag = hline[0]
        content = hline[1:] if len(hline) > 1 else ""
        if tag == " ":
            old_lines.append(content)
            new_lines.append(content)
        elif tag == "-":
            old_lines.append(content)
        elif tag == "+":
            new_lines.append(content)
    return old_lines, new_lines


def _paired_slices(
    orig_lines: List[str],
    prop_lines: List[str],
    start_0: int,
    count: int,
) -> Tuple[int, int, str, str]:
    i0 = max(0, start_0 - _CONTEXT_LINES)
    i1 = min(len(orig_lines), start_0 + max(count, 1) + _CONTEXT_LINES)
    vendor = "\n".join(orig_lines[i0:i1])
    if len(prop_lines) == len(orig_lines):
        merged = "\n".join(prop_lines[i0:i1])
    else:
        j0 = max(0, start_0 - _CONTEXT_LINES)
        j1 = min(len(prop_lines), start_0 + max(count, 1) + _CONTEXT_LINES)
        merged = "\n".join(prop_lines[j0:j1])
    return i0 + 1, i1, vendor, merged


def _trim_diff_rows(rows: List[Dict[str, Any]], max_lines: int = _MAX_REGION_LINES) -> List[Dict[str, Any]]:
    if len(rows) <= max_lines:
        return rows
    head = max_lines * 2 // 3
    tail = max_lines - head - 1
    omitted = len(rows) - head - tail
    marker = {
        "left": {"num": None, "text": f"... （省略 {omitted} 行） ...", "cls": "ctx"},
        "right": {"num": None, "text": "", "cls": "empty"},
    }
    return rows[:head] + [marker] + rows[-tail:]


def _side(num: Optional[int], text: str, cls: str) -> Dict[str, Any]:
    return {"num": num, "text": text, "cls": cls}


def build_gerrit_diff_rows(
    before_text: str,
    after_text: str,
    *,
    line_base: int = 1,
    new_line_base: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Build aligned side-by-side rows: left=before, right=after (Gerrit-like)."""
    old_lines = _split_lines(before_text)
    new_lines = _split_lines(after_text)
    if not old_lines and not new_lines:
        return []

    right_base = new_line_base if new_line_base is not None else line_base
    rows: List[Dict[str, Any]] = []
    sm = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                rows.append({
                    "left": _side(line_base + i1 + k, old_lines[i1 + k], "ctx"),
                    "right": _side(right_base + j1 + k, new_lines[j1 + k], "ctx"),
                })
        elif tag == "delete":
            for k in range(i2 - i1):
                rows.append({
                    "left": _side(line_base + i1 + k, old_lines[i1 + k], "del"),
                    "right": _side(None, "", "empty"),
                })
        elif tag == "insert":
            for k in range(j2 - j1):
                rows.append({
                    "left": _side(None, "", "empty"),
                    "right": _side(right_base + j1 + k, new_lines[j1 + k], "add"),
                })
        elif tag == "replace":
            old_chunk = old_lines[i1:i2]
            new_chunk = new_lines[j1:j2]
            span = max(len(old_chunk), len(new_chunk))
            for k in range(span):
                ol = old_chunk[k] if k < len(old_chunk) else None
                nl = new_chunk[k] if k < len(new_chunk) else None
                if ol is not None and nl is not None:
                    cls = "chg" if ol != nl else "ctx"
                    rows.append({
                        "left": _side(line_base + i1 + k, ol, cls),
                        "right": _side(right_base + j1 + k, nl, cls),
                    })
                elif ol is not None:
                    rows.append({
                        "left": _side(line_base + i1 + k, ol, "del"),
                        "right": _side(None, "", "empty"),
                    })
                else:
                    rows.append({
                        "left": _side(None, "", "empty"),
                        "right": _side(right_base + j1 + k, nl or "", "add"),
                    })
    return rows


def _parse_rej_hunks(rej_content: str) -> List[RejHunk]:
    if not rej_content.strip():
        return []
    hunks: List[RejHunk] = []
    matches = list(_HUNK_HEADER.finditer(rej_content))
    if not matches:
        return hunks
    for idx, m in enumerate(matches):
        old_start = int(m.group(1)) - 1
        old_count = int(m.group(2) or "1")
        new_start = int(m.group(3)) - 1
        new_count = int(m.group(4) or "1")
        # Body starts on the line after the @@ header (ignore trailing context on header line).
        nl = rej_content.find("\n", m.start())
        body_start = nl + 1 if nl >= 0 else m.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(rej_content)
        body = rej_content[body_start:body_end].strip("\n")
        hunks.append((old_start, old_count, new_start, new_count, body))
    return hunks


def _file_lines_usable(lines: List[str], need_len: int) -> bool:
    """True if line list is long enough and not a truncated DB snapshot."""
    if len(lines) < need_len:
        return False
    sample = "\n".join(lines[:8] + lines[-8:])
    return "truncated" not in sample.lower()


def _orig_span_to_prop_lines(
    orig_lines: List[str],
    prop_lines: List[str],
    start: int,
    end: int,
) -> List[str]:
    """Map original line span [start, end) to the corresponding proposed lines."""
    if start >= end:
        return []
    if (
        len(orig_lines) == len(prop_lines)
        and _file_lines_usable(prop_lines, end)
    ):
        return prop_lines[start:end]

    out: List[str] = []
    for tag, o0, o1, p0, p1 in difflib.SequenceMatcher(None, orig_lines, prop_lines).get_opcodes():
        os0, os1 = max(o0, start), min(o1, end)
        if os0 >= os1:
            continue
        if tag == "equal":
            out.extend(prop_lines[p0 + (os0 - o0): p0 + (os1 - o0)])
        elif tag == "replace":
            for o in range(os0, os1):
                rel = o - o0
                if p0 + rel < p1:
                    out.append(prop_lines[p0 + rel])
        elif tag == "insert" and o0 <= start < o1:
            out.extend(prop_lines[p0:p1])
    return out


def _file_hunk_aligned(orig_lines: List[str], old_start: int, hunk_old: List[str]) -> bool:
    """True when source file at old_start matches the .rej hunk old side."""
    if not hunk_old:
        return False
    i0 = max(0, old_start)
    if i0 >= len(orig_lines):
        return False
    chunk = orig_lines[i0:i0 + len(hunk_old)]
    if chunk == hunk_old:
        return True
    return orig_lines[i0].strip() == hunk_old[0].strip()


def _prop_window_usable(prop_win: List[str], baseline: List[str], hunk_new: List[str]) -> bool:
    """Reject proposed slices that are the wrong file span (same length, wrong offset)."""
    if not prop_win or not baseline:
        return False
    if abs(len(prop_win) - len(baseline)) > max(12, len(baseline) // 3):
        return False
    if prop_win[0].strip() != baseline[0].strip():
        h0 = hunk_new[0].strip() if hunk_new else ""
        if h0 and prop_win[0].strip() != h0:
            return False
    return True


def _region_from_rej_hunk(
    orig_lines: List[str],
    prop_lines: List[str],
    old_start: int,
    new_start: int,
    hunk_body: str,
    *,
    has_proposed: bool,
) -> Tuple[int, int, int, str, str]:
    """Build vendor (left) and patch/merged (right) snippets for one .rej hunk.

    The .rej hunk body is authoritative for the conflict body; line numbers are
    only used for optional context lines outside the hunk when the file aligns.
    """
    hunk_old, hunk_new = _parse_hunk_sides(hunk_body)
    n_old = len(hunk_old)

    pre: List[str] = []
    post: List[str] = []
    aligned = _file_hunk_aligned(orig_lines, old_start, hunk_old)
    if aligned:
        need_end = old_start + n_old + _CONTEXT_LINES
        if _file_lines_usable(orig_lines, need_end):
            pre = orig_lines[max(0, old_start - _CONTEXT_LINES):old_start]
            post = orig_lines[old_start + n_old: old_start + n_old + _CONTEXT_LINES]

    before_lines = pre + hunk_old + post
    baseline = pre + hunk_new + post
    win_start = old_start - len(pre)
    win_end = old_start + n_old + len(post)

    after_lines = baseline
    if has_proposed and prop_lines and aligned:
        prop_win = _orig_span_to_prop_lines(orig_lines, prop_lines, win_start, win_end)
        if _prop_window_usable(prop_win, baseline, hunk_new):
            after_lines = prop_win

    start_line = win_start + 1
    end_line = win_end
    new_start_line = max(1, new_start - len(pre) + 1)
    return start_line, end_line, new_start_line, "\n".join(before_lines), "\n".join(after_lines)


def _parse_marker_blocks(original: str) -> List[Tuple[int, int, str, str]]:
    text = original if original.endswith("\n") else original + "\n"
    blocks: List[Tuple[int, int, str, str]] = []
    for m in _MARKER_BLOCK.finditer(text):
        vendor = m.group(1)
        incoming = m.group(2)
        start = text[: m.start()].count("\n") + 1
        end = text[: m.end()].count("\n") + 1
        blocks.append((start, end, vendor, incoming))
    return blocks


def merge_rej_into_source(source: str, rej_content: str) -> str:
    """Apply all hunks from a .rej file onto the full source text."""
    if not rej_content.strip():
        return source
    lines = _split_lines(source)
    hunks = _parse_rej_hunks(rej_content)
    if not hunks:
        return source
    for old_start, _old_count, _new_start, _new_count, hunk_body in reversed(hunks):
        hunk_old, hunk_new = _parse_hunk_sides(hunk_body)
        n_old = len(hunk_old)
        if n_old == 0 and not hunk_new:
            continue
        i0 = max(0, old_start)
        chunk = lines[i0:i0 + n_old] if i0 < len(lines) else []
        if chunk == hunk_old:
            lines[i0:i0 + n_old] = hunk_new
        elif i0 < len(lines):
            replace_len = min(n_old, len(lines) - i0) if n_old else 0
            if replace_len > 0:
                lines[i0:i0 + replace_len] = hunk_new
            else:
                lines[i0:i0] = hunk_new
        else:
            lines.extend(hunk_new)
    return "\n".join(lines)


def _region_entry(
    index: int,
    start_line: int,
    end_line: int,
    before: str,
    after: str,
    *,
    has_merged: bool,
    from_rej: bool = False,
    new_start_line: Optional[int] = None,
) -> Dict[str, Any]:
    rows = build_gerrit_diff_rows(
        before,
        after or "",
        line_base=start_line,
        new_line_base=new_start_line if new_start_line is not None else start_line,
    )
    if not from_rej and len(rows) > _MAX_REGION_LINES:
        rows = _trim_diff_rows(rows, _MAX_REGION_LINES)
    return {
        "index": index,
        "start_line": start_line,
        "end_line": end_line,
        "vendor": before,
        "merged": after or "",
        "has_merged": has_merged,
        "diff_rows": rows,
    }


def extract_conflict_regions(
    *,
    kind: str,
    original: str,
    rej_content: str = "",
    proposed: str = "",
) -> List[Dict[str, Any]]:
    """Build Gerrit-style before/after diff regions for the UI."""
    orig_lines = _split_lines(original)
    prop_lines = _split_lines(proposed)
    has_proposed = bool(proposed.strip())
    regions: List[Dict[str, Any]] = []

    if kind == "markers" or _MARKER_BLOCK.search(original or ""):
        for i, (start, end, vendor_part, incoming) in enumerate(_parse_marker_blocks(original), 1):
            start0 = start - 1
            span = end - start + 1
            if has_proposed:
                s, e, before, merged = _paired_slices(orig_lines, prop_lines, start0, span)
            else:
                hunk_body = "\n".join(
                    [f"-{ln}" for ln in vendor_part.splitlines()]
                    + [f"+{ln}" for ln in incoming.splitlines()]
                )
                s, e, ns, before, merged = _region_from_rej_hunk(
                    orig_lines, prop_lines, start0, start0, hunk_body, has_proposed=False,
                )
            regions.append(_region_entry(i, s, e, before, merged, has_merged=has_proposed, new_start_line=ns))
        if regions:
            return regions

    hunks = _parse_rej_hunks(rej_content)
    if hunks:
        for i, (old_start, _oc, new_start, _nc, hunk_body) in enumerate(hunks, 1):
            s, e, ns, before, merged = _region_from_rej_hunk(
                orig_lines, prop_lines, old_start, new_start, hunk_body,
                has_proposed=has_proposed,
            )
            regions.append(_region_entry(
                i, s, e, before, merged, has_merged=has_proposed, from_rej=True, new_start_line=ns,
            ))
        return regions

    # .rej conflict but hunk parse failed — do not fall back to whole-file diff
    if kind == "rej" or rej_content.strip():
        return regions

    if has_proposed and original != proposed:
        idx = 0
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, orig_lines, prop_lines).get_opcodes():
            if tag == "equal":
                continue
            idx += 1
            s, e, before, merged = _paired_slices(orig_lines, prop_lines, i1, i2 - i1)
            regions.append(_region_entry(idx, s, e, before, merged, has_merged=True))
        return regions[:20]

    return regions


def _lines_equal(a: str, b: str) -> bool:
    return a == b or a.strip() == b.strip()


def _chunk_matches_hunk(chunk: List[str], hunk_old: List[str]) -> bool:
    if len(chunk) != len(hunk_old):
        return False
    return all(_lines_equal(c, h) for c, h in zip(chunk, hunk_old))


_MAX_HUNK_BODY_LINES = 90
_FUNC_BOUNDARY = re.compile(
    r"^(?:static\s+(?:inline\s+)?(?:void|int|unsigned|bool|long|ssize_t)|/\*\*|/\*)"
)


def _extract_hunk_raw_segment(hunk_body: str, old_begin: int, old_end: int) -> str:
    """Slice unified-diff hunk body for hunk_old[old_begin:old_end]."""
    lines_out: List[str] = []
    old_i = 0
    for ln in hunk_body.splitlines():
        if not ln or ln[0] == "\\":
            continue
        tag = ln[0]
        if tag not in " +-":
            continue
        if tag in " -":
            if old_begin <= old_i < old_end:
                lines_out.append(ln)
            if tag == " " or tag == "-":
                old_i += 1
        elif tag == "+":
            if old_begin <= old_i < old_end:
                lines_out.append(ln)
    return "\n".join(lines_out)


def _split_oversized_rej_hunk(
    old_start: int,
    old_count: int,
    hunk_body: str,
) -> List[Tuple[int, int, str]]:
    """Split giant .rej hunks (e.g. menu.c 268 lines) at function boundaries."""
    hunk_old, _ = _parse_hunk_sides(hunk_body)
    n = len(hunk_old)
    if n <= _MAX_HUNK_BODY_LINES:
        return [(old_start, old_count, hunk_body)]

    bounds = [0]
    for i in range(1, n):
        s = hunk_old[i].strip()
        if _FUNC_BOUNDARY.match(s) and (i - bounds[-1]) >= 15:
            bounds.append(i)
    if bounds[-1] != n:
        bounds.append(n)
    if len(bounds) <= 2:
        bounds = list(range(0, n, _MAX_HUNK_BODY_LINES))
        if bounds[-1] != n:
            bounds.append(n)

    parts: List[Tuple[int, int, str]] = []
    offset = old_start
    for bi in range(len(bounds) - 1):
        b0, b1 = bounds[bi], bounds[bi + 1]
        seg = _extract_hunk_raw_segment(hunk_body, b0, b1)
        if not seg.strip():
            offset += b1 - b0
            continue
        seg_old, _ = _parse_hunk_sides(seg)
        if not seg_old:
            offset += b1 - b0
            continue
        parts.append((offset, len(seg_old), seg))
        offset += len(seg_old)
    return parts if parts else [(old_start, old_count, hunk_body)]


def validate_merged_hunk_middle(
    middle: List[str],
    vendor_body: Optional[List[str]] = None,
) -> None:
    """Reject merged hunk bodies that would corrupt C structure."""
    if not middle:
        raise ValueError("合并结果为空")
    text = "\n".join(middle)
    if "<<<<<<<" in text or ">>>>>>>" in text:
        raise ValueError("合并结果仍含 git 冲突标记")

    depth = 0
    for ln in middle:
        stripped = ln.strip()
        if depth > 0 and re.match(
            r"^static\s+(?:inline\s+)?(?:void|int|unsigned|bool|long|ssize_t)\s+",
            stripped,
        ):
            raise ValueError(
                f"合并结果在函数体内出现 static 声明（结构错误）: {stripped[:70]!r}"
            )
        depth += ln.count("{") - ln.count("}")

    open_b = text.count("{")
    close_b = text.count("}")
    if vendor_body:
        vb = "\n".join(vendor_body)
        delta_v = vb.count("{") - vb.count("}")
        delta_m = open_b - close_b
        if abs(delta_m - delta_v) > 2:
            raise ValueError(
                f"大括号净增量异常（vendor {delta_v:+d}，合并 {delta_m:+d}）"
            )
    elif abs(open_b - close_b) > 3:
        raise ValueError(f"大括号严重不平衡: {{ {open_b} vs }} {close_b}")


def _locate_hunk_in_source(
    orig_lines: List[str],
    rej_old_start: int,
    hunk_old: List[str],
    *,
    old_count: int = 0,
    search_radius: int = 500,
) -> Optional[int]:
    """Find hunk_old in source; .rej line numbers drift when vendor differs from GKI."""
    if not hunk_old:
        return None
    n = len(hunk_old)
    if _file_hunk_aligned(orig_lines, rej_old_start, hunk_old):
        return rej_old_start

    lo = max(0, rej_old_start - search_radius)
    hi = min(len(orig_lines), rej_old_start + search_radius + n)
    for i in range(lo, hi):
        if i + n <= len(orig_lines) and _chunk_matches_hunk(orig_lines[i:i + n], hunk_old):
            return i

    first_sig = next((ln for ln in hunk_old if ln.strip()), "")
    if first_sig.strip():
        for i, line in enumerate(orig_lines):
            if line.strip() != first_sig.strip():
                continue
            if i + n <= len(orig_lines) and _chunk_matches_hunk(orig_lines[i:i + n], hunk_old):
                return i

    best_i: Optional[int] = None
    best_score = 0.0
    search_lo = max(0, rej_old_start - search_radius)
    search_hi = min(len(orig_lines), rej_old_start + search_radius + n)
    for i in range(search_lo, search_hi):
        if i + n > len(orig_lines):
            continue
        score = difflib.SequenceMatcher(
            None, hunk_old, orig_lines[i:i + n], autojunk=False,
        ).ratio()
        if score > best_score:
            best_score = score
            best_i = i
    if best_i is not None and best_score >= 0.72:
        return best_i

    # Weak anchor: only when rej line already matches hunk head (avoid vendor drift)
    if rej_old_start < len(orig_lines) and hunk_old:
        head = hunk_old[0].strip()
        if head:
            for j in range(rej_old_start, min(len(orig_lines), rej_old_start + 8)):
                if orig_lines[j].strip() == head:
                    return j
    return None


def _rej_hunk_window(
    orig_lines: List[str],
    old_start: int,
    old_count: int,
    hunk_body: str,
) -> Tuple[int, int, int, int, str, str, bool]:
    """Return hunk span, context lens, snippets, and whether hunk was located."""
    hunk_old, hunk_new = _parse_hunk_sides(hunk_body)
    n_old = len(hunk_old)
    actual_start = _locate_hunk_in_source(
        orig_lines, old_start, hunk_old, old_count=old_count,
    )
    aligned = actual_start is not None
    if not aligned:
        return old_start, old_start, 0, 0, "", "", False

    hunk_start = actual_start
    if n_old > 0:
        hunk_end = min(len(orig_lines), hunk_start + n_old)
    else:
        hunk_end = min(len(orig_lines), hunk_start + max(old_count, 1))

    pre: List[str] = []
    post: List[str] = []
    need_end = hunk_end + _CONTEXT_LINES
    if _file_lines_usable(orig_lines, need_end):
        pre = orig_lines[max(0, hunk_start - _CONTEXT_LINES):hunk_start]
        post = orig_lines[hunk_end: min(len(orig_lines), hunk_end + _CONTEXT_LINES)]
    hunk_body_lines = orig_lines[hunk_start:hunk_end]

    vendor_snippet = "\n".join(pre + hunk_body_lines + post)
    incoming_snippet = "\n".join(pre + hunk_new + post)
    return hunk_start, hunk_end, len(pre), len(post), vendor_snippet, incoming_snippet, aligned


def collect_conflict_merge_tasks(
    *,
    original_content: str,
    rej_content: str = "",
    has_conflict_markers: bool = False,
) -> List[Dict[str, Any]]:
    """Build per-region LLM merge tasks (only conflict hunks, not whole file)."""
    orig_lines = _split_lines(original_content)
    tasks: List[Dict[str, Any]] = []

    if has_conflict_markers or _MARKER_BLOCK.search(original_content or ""):
        blocks = _parse_marker_blocks(original_content)
        total = len(blocks)
        for i, (start, end, _vendor_part, incoming) in enumerate(blocks, 1):
            conflict_start = start - 1
            conflict_end = end
            ctx_start = max(0, conflict_start - _CONTEXT_LINES)
            ctx_end = min(len(orig_lines), conflict_end + _CONTEXT_LINES)
            tasks.append({
                "index": i,
                "total": total,
                "start_line": ctx_start + 1,
                "end_line": ctx_end,
                "replace_start": conflict_start,
                "replace_end": conflict_end,
                "pre_len": conflict_start - ctx_start,
                "post_len": ctx_end - conflict_end,
                "aligned": True,
                "vendor_snippet": "\n".join(orig_lines[ctx_start:ctx_end]),
                "body_snippet": "\n".join(orig_lines[conflict_start:conflict_end]),
                "incoming_snippet": incoming.strip(),
                "hunk_body": "",
                "kind": "markers",
            })
        if tasks:
            return tasks

    hunks = _parse_rej_hunks(rej_content)
    if hunks:
        sub_hunks: List[Tuple[int, int, int, int, str]] = []
        for old_start, old_count, new_start, new_count, hunk_body in hunks:
            for sub_start, sub_count, sub_body in _split_oversized_rej_hunk(
                old_start, old_count, hunk_body,
            ):
                sub_hunks.append((sub_start, sub_count, new_start, new_count, sub_body))
        total = len(sub_hunks)
        for i, (old_start, old_count, _new_start, _nc, hunk_body) in enumerate(sub_hunks, 1):
            hunk_start, hunk_end, pre_len, post_len, vendor_snippet, incoming_snippet, aligned = (
                _rej_hunk_window(orig_lines, old_start, old_count, hunk_body)
            )
            if not aligned or not vendor_snippet.strip():
                continue
            tasks.append({
                "index": i,
                "total": total,
                "start_line": max(1, hunk_start - pre_len + 1),
                "end_line": hunk_end + post_len,
                "replace_start": hunk_start,
                "replace_end": hunk_end,
                "pre_len": pre_len,
                "post_len": post_len,
                "aligned": aligned,
                "vendor_snippet": vendor_snippet,
                "body_snippet": "\n".join(_vendor_body_lines(vendor_snippet, pre_len, post_len)),
                "incoming_snippet": incoming_snippet,
                "incoming_body_snippet": "\n".join(
                    _vendor_body_lines(incoming_snippet, pre_len, post_len)
                ),
                "hunk_body": hunk_body,
                "kind": "rej",
            })
        return tasks

    return tasks


def _strip_match_lines(a: List[str], b: List[str]) -> bool:
    if len(a) != len(b):
        return False
    return all(x.strip() == y.strip() for x, y in zip(a, b))


def _find_subsequence(
    haystack: List[str],
    needle: List[str],
    start: int = 0,
) -> Optional[int]:
    if not needle:
        return start
    for i in range(max(0, start), len(haystack) - len(needle) + 1):
        if all(haystack[i + k].strip() == needle[k].strip() for k in range(len(needle))):
            return i
    return None


def _find_all_subsequence(
    haystack: List[str],
    needle: List[str],
    start: int = 0,
) -> List[int]:
    if not needle:
        return [start]
    out: List[int] = []
    i = max(0, start)
    while i <= len(haystack) - len(needle):
        pos = _find_subsequence(haystack, needle, i)
        if pos is None:
            break
        out.append(pos)
        i = pos + 1
    return out


def _pick_context_anchor(
    lines: List[str],
    ctx: List[str],
    dels: List[str],
) -> Tuple[Optional[int], Optional[int]]:
    """Pick context match; prefer last site where dels follow context (vendor prefix code)."""
    if not ctx:
        return 0, None
    positions = _find_all_subsequence(lines, ctx)
    if not positions:
        for c in reversed(ctx):
            if not c.strip():
                continue
            for j, ln in enumerate(lines):
                if ln.strip() == c.strip():
                    positions = [j]
                    break
            if positions:
                break
    if not positions:
        return None, None

    for pos in reversed(positions):
        anchor = pos + len(ctx)
        if dels:
            rep_pos = _find_subsequence(lines, dels, anchor)
            if rep_pos is not None and rep_pos <= anchor + 20:
                return anchor, rep_pos
        else:
            return anchor, None

    if dels:
        for pos in reversed(positions):
            anchor = pos + len(ctx)
            rep_pos = _find_subsequence(lines, dels, max(0, pos))
            if rep_pos is not None and rep_pos <= anchor + 30:
                return anchor, rep_pos
    return positions[-1] + len(ctx), None


def _sanitize_duplicate_wrrd_msgs_advance(source: str) -> str:
    """Collapse accidental double WRRD msgs advance from overlapping micro-patches."""
    dup = (
        "\t\tif (i2c->op == I2C_MASTER_WRRD)\n"
        "\t\t\tmsgs += 2;\n"
        "\t\telse\n"
        "\t\tif (i2c->op == I2C_MASTER_WRRD)\n"
        "\t\t\tmsgs += 2;\n"
        "\t\telse\n"
        "\t\t\tmsgs++;"
    )
    fix = (
        "\t\tif (i2c->op == I2C_MASTER_WRRD)\n"
        "\t\t\tmsgs += 2;\n"
        "\t\telse\n"
        "\t\t\tmsgs++;"
    )
    if dup in source:
        source = source.replace(dup, fix, 1)
    return source


def apply_rej_hunk_micro_patches(source: str, hunk_body: str) -> Tuple[str, int]:
    """Apply .rej hunk via context-anchored micro-patches (safe when vendor added extra code).

    Walks unified-diff hunk body: for each context + (-lines / +lines) group, locate context
    in the full source file and apply replace or insert. Does not replace the whole function.
    """
    if not hunk_body.strip():
        return source, 0
    lines = _split_lines(source)
    hunk_lines = [ln for ln in hunk_body.splitlines() if ln]
    i = 0
    applied = 0

    while i < len(hunk_lines):
        ctx: List[str] = []
        while i < len(hunk_lines) and hunk_lines[i][:1] == " ":
            ctx.append(hunk_lines[i][1:])
            i += 1
        dels: List[str] = []
        adds: List[str] = []
        while i < len(hunk_lines) and hunk_lines[i][:1] in "-+":
            if hunk_lines[i][0] == "-":
                dels.append(hunk_lines[i][1:])
                i += 1
            elif hunk_lines[i][0] == "+":
                adds.append(hunk_lines[i][1:])
                i += 1
            else:
                break
        if not dels and not adds:
            if i < len(hunk_lines):
                i += 1
            continue

        anchor, rep_pos = _pick_context_anchor(lines, ctx, dels)
        if anchor is None:
            continue

        if dels:
            if rep_pos is None:
                rep_pos = _find_subsequence(lines, dels, max(0, anchor - len(ctx) - 5))
            if rep_pos is None:
                rep_pos = _find_subsequence(lines, dels)
            if rep_pos is not None:
                lines[rep_pos:rep_pos + len(dels)] = adds
                applied += 1
                continue

        if adds and not dels:
            chunk = "\n".join(lines)
            if all(a.strip() in chunk for a in adds if a.strip()):
                continue
            ins = anchor
            if ins <= len(lines) and adds:
                lines[ins:ins] = adds
                applied += 1

    result = "\n".join(lines)
    if source.endswith("\n"):
        result += "\n"
    result = _sanitize_duplicate_wrrd_msgs_advance(result)
    return result, applied


def _rej_missing_plus_lines(source: str, rej_content: str, *, limit: int = 5) -> List[str]:
    """Return stripped + lines from .rej that are absent in source."""
    missing: List[str] = []
    for _os, _oc, _ns, _nc, body in _parse_rej_hunks(rej_content):
        for ln in body.splitlines():
            if not ln.startswith("+"):
                continue
            s = ln[1:].strip()
            if not s:
                continue
            if s not in source:
                missing.append(ln[1:])
                if len(missing) >= limit:
                    return missing
    return missing


def validate_rej_merge_complete(source: str, rej_content: str) -> None:
    """Raise if any + line from .rej is missing in merged source."""
    if not rej_content.strip():
        return
    missing = _rej_missing_plus_lines(source, rej_content, limit=8)
    if missing:
        preview = "; ".join(m.strip()[:60] for m in missing[:3])
        raise RuntimeError(
            f"合并不完整：.rej 中 {len(missing)}+ 处 GKI 改动未落地，例如: {preview}"
        )


def _rej_plus_lines_present(source: str, hunk_body: str) -> bool:
    """True if every + line from the hunk appears in source (micro-patch complete)."""
    adds = [ln[1:] for ln in hunk_body.splitlines() if ln.startswith("+")]
    if not adds:
        return True
    for a in adds:
        s = a.strip()
        if not s:
            continue
        if s not in source:
            return False
    return True


def apply_all_rej_micro_patches(source: str, rej_content: str) -> Tuple[str, int]:
    """Apply every hunk in a .rej file via micro-patches."""
    total = 0
    merged = source
    for _os, _oc, _ns, _nc, body in _parse_rej_hunks(rej_content):
        merged, n = apply_rej_hunk_micro_patches(merged, body)
        total += n
    return merged, total


def _vendor_body_lines(vendor_snippet: str, pre_len: int, post_len: int) -> List[str]:
    vendor_lines = _split_lines(vendor_snippet)
    if post_len:
        return vendor_lines[pre_len: len(vendor_lines) - post_len]
    return vendor_lines[pre_len:]


def extract_merged_hunk_body(
    vendor_snippet: str,
    merged_region: str,
    pre_len: int,
    post_len: int,
) -> List[str]:
    """Parse LLM output into the merged conflict body (middle hunk only)."""
    vendor_lines = _split_lines(vendor_snippet)
    merged_lines = _split_lines(merged_region)
    body_len = len(vendor_lines) - pre_len - post_len
    if body_len < 0:
        raise ValueError("vendor 区域上下文长度无效")
    if not merged_lines:
        raise ValueError("合并结果为空")

    # Full region with exact preserved context
    if len(merged_lines) >= pre_len + post_len:
        pre_ok = pre_len == 0 or merged_lines[:pre_len] == vendor_lines[:pre_len]
        post_ok = post_len == 0 or merged_lines[-post_len:] == vendor_lines[-post_len:]
        if pre_ok and post_ok:
            middle = merged_lines[pre_len:-post_len] if post_len else merged_lines[pre_len:]
            if middle or body_len == 0:
                return middle

    # Full region with whitespace-tolerant context
    if len(merged_lines) >= pre_len + post_len and (pre_len or post_len):
        pre_ok = pre_len == 0 or _strip_match_lines(merged_lines[:pre_len], vendor_lines[:pre_len])
        post_ok = post_len == 0 or _strip_match_lines(merged_lines[-post_len:], vendor_lines[-post_len:])
        if pre_ok and post_ok:
            return merged_lines[pre_len:-post_len] if post_len else merged_lines[pre_len:]

    # Middle-only output (preferred): LLM returns just the merged hunk body
    if "<<<<<<<" not in merged_region and ">>>>>>>" not in merged_region:
        if body_len == 0 or (
            len(merged_lines) >= max(1, int(body_len * 0.35))
            and len(merged_lines) <= int(body_len * 3) + 40
        ):
            return merged_lines

    raise ValueError(
        f"无法解析 LLM 合并结果（输出 {len(merged_lines)} 行，冲突主体约 {body_len} 行）"
    )


def apply_hunk_merge_to_source(
    source: str,
    hunk_start: int,
    hunk_end: int,
    merged_middle: List[str],
) -> str:
    """Replace only the conflict hunk lines, leaving outer context untouched."""
    lines = _split_lines(source)
    hs = max(0, hunk_start)
    he = min(len(lines), hunk_end)
    if hs > len(lines):
        raise ValueError(f"hunk 起始行 {hs + 1} 超出文件长度 {len(lines)}")
    new_lines = lines[:hs] + merged_middle + lines[he:]
    result = "\n".join(new_lines)
    if source.endswith("\n"):
        result += "\n"
    return result


def splice_region_into_source(
    source: str,
    replace_start: int,
    replace_end: int,
    merged_region: str,
) -> str:
    """Replace source lines [replace_start, replace_end) with merged_region."""
    lines = _split_lines(source)
    merged_lines = _split_lines(merged_region)
    rs = max(0, replace_start)
    re_ = min(len(lines), replace_end)
    if rs > len(lines):
        raise ValueError(f"区域起始行 {rs + 1} 超出文件长度 {len(lines)}")
    new_lines = lines[:rs] + merged_lines + lines[re_:]
    result = "\n".join(new_lines)
    if source.endswith("\n"):
        result += "\n"
    return result
