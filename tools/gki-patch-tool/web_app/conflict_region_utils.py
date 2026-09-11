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
    """True when source at old_start matches the entire .rej hunk old side.

    First-line-only match is not alignment: vendor may share a function signature
    while the implementation differs from GKI.
    """
    if not hunk_old:
        return False
    i0 = max(0, old_start)
    if i0 >= len(orig_lines):
        return False
    chunk = orig_lines[i0:i0 + len(hunk_old)]
    return _chunk_matches_hunk(chunk, hunk_old)


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
        if _chunk_matches_hunk(chunk, hunk_old):
            lines[i0:i0 + n_old] = hunk_new
        # else: vendor body differs — do not paste hunk_new at the .rej line number
    result = "\n".join(lines)
    if source.endswith("\n"):
        result += "\n"
    result, _n = apply_all_rej_micro_patches(result, rej_content)
    return result


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


def _regions_from_file_diff(
    orig_lines: List[str],
    prop_lines: List[str],
) -> List[Dict[str, Any]]:
    """Gerrit regions from actual repo file before vs after (not GKI .rej sides)."""
    if orig_lines == prop_lines:
        return []
    if not orig_lines and not prop_lines:
        return []
    spans: List[Tuple[int, int, int, int]] = []
    sm = difflib.SequenceMatcher(None, orig_lines, prop_lines, autojunk=False)
    gap = _CONTEXT_LINES * 2
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if spans and i1 <= spans[-1][1] + gap:
            p0, p1, q0, _q1 = spans[-1]
            spans[-1] = (p0, i2, q0, j2)
        else:
            spans.append((i1, i2, j1, j2))

    regions: List[Dict[str, Any]] = []
    for i, (i1, i2, j1, j2) in enumerate(spans[:20], 1):
        o0 = max(0, i1 - _CONTEXT_LINES)
        o1 = min(len(orig_lines), i2 + _CONTEXT_LINES)
        p0 = max(0, j1 - _CONTEXT_LINES)
        p1 = min(len(prop_lines), j2 + _CONTEXT_LINES)
        regions.append(_region_entry(
            i,
            o0 + 1,
            o1,
            "\n".join(orig_lines[o0:o1]),
            "\n".join(prop_lines[p0:p1]),
            has_merged=True,
            new_start_line=p0 + 1,
        ))
    return regions


def _vendor_pending_regions(
    orig_lines: List[str],
    rej_content: str,
) -> List[Dict[str, Any]]:
    """Before AI merge: show the vendor-repo window, not the GKI hunk old/new sides."""
    src = "\n".join(orig_lines)
    regions: List[Dict[str, Any]] = []
    for i, (old_start, _oc, _ns, _nc, body) in enumerate(_parse_rej_hunks(rej_content), 1):
        hunk_old, _hunk_new = _parse_hunk_sides(body)
        start = _locate_hunk_in_source(orig_lines, old_start, hunk_old)
        end: Optional[int] = (start + len(hunk_old)) if start is not None else None
        if start is None:
            located = None
            for name in extract_function_names_from_hunk_body(body):
                located = extract_named_c_function(src, name)
                if located:
                    break
            if located is None:
                continue
            start, end, _text = located
        o0 = max(0, start - _CONTEXT_LINES)
        o1 = min(len(orig_lines), (end or start) + _CONTEXT_LINES)
        regions.append(_region_entry(
            i,
            o0 + 1,
            o1,
            "\n".join(orig_lines[o0:o1]),
            "",
            has_merged=False,
            from_rej=True,
        ))
    return regions


def extract_conflict_regions(
    *,
    kind: str,
    original: str,
    rej_content: str = "",
    proposed: str = "",
) -> List[Dict[str, Any]]:
    """Build Gerrit-style before/after diff regions for the UI.

    Left/right are the code-warehouse file (合入前 / 拟写回), not GKI common
    old/new from the .rej hunk.
    """
    orig_lines = _split_lines(original)
    prop_lines = _split_lines(proposed)
    has_proposed = bool((proposed or "").strip())
    regions: List[Dict[str, Any]] = []

    if kind == "markers" or _MARKER_BLOCK.search(original or ""):
        for i, (start, end, vendor_part, incoming) in enumerate(_parse_marker_blocks(original), 1):
            start0 = start - 1
            span = end - start + 1
            ns = start
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
            regions.append(_region_entry(
                i, s, e, before, merged, has_merged=has_proposed, new_start_line=ns,
            ))
        if regions:
            return regions

    if has_proposed and original != proposed:
        file_regions = _regions_from_file_diff(orig_lines, prop_lines)
        if file_regions:
            return file_regions

    if rej_content.strip() or kind == "rej":
        return _vendor_pending_regions(orig_lines, rej_content)

    return regions


def _lines_equal(a: str, b: str) -> bool:
    return a == b or a.strip() == b.strip()


def _chunk_matches_hunk(chunk: List[str], hunk_old: List[str]) -> bool:
    if len(chunk) != len(hunk_old):
        return False
    return all(_lines_equal(c, h) for c, h in zip(chunk, hunk_old))


_C_FUNC_DEF_HEAD = re.compile(
    r"^(?:static(?:\s+inline)?\s+)?(?:[\w*]+\s+)+\b([A-Za-z_][A-Za-z0-9_]*)\s*\("
)


def extract_function_names_from_hunk_body(hunk_body: str) -> List[str]:
    """Function names appearing as definitions in a unified-diff hunk body."""
    names: List[str] = []
    seen = set()
    for raw in hunk_body.splitlines():
        if not raw or raw[0] not in " +-":
            continue
        m = _C_FUNC_DEF_HEAD.match(raw[1:])
        if not m:
            continue
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def count_c_function_defs(source: str, name: str) -> int:
    """Count C function definitions named `name` (not calls or prototypes)."""
    if not name or not source:
        return 0
    head = re.compile(
        rf"^(?:static(?:\s+inline)?\s+)?(?:[\w*]+\s+)+\b{re.escape(name)}\s*\(",
        re.MULTILINE,
    )
    n = 0
    for m in head.finditer(source):
        rest = source[m.end(): m.end() + 500]
        if re.match(r"[^;{}]{0,400}\)\s*\{", rest, re.DOTALL):
            n += 1
    return n


def extra_function_defs_introduced(
    original: str,
    merged: str,
    hunk_or_rej: str,
) -> List[str]:
    """Names whose definition count increased after merge (second copy pasted)."""
    names: List[str] = []
    for _os, _oc, _ns, _nc, body in _parse_rej_hunks(hunk_or_rej):
        names.extend(extract_function_names_from_hunk_body(body))
    if not names:
        names = extract_function_names_from_hunk_body(hunk_or_rej)
    duped: List[str] = []
    seen = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        if count_c_function_defs(merged, name) > count_c_function_defs(original, name):
            duped.append(name)
    return duped


def _hunk_old_exactly_in_source(orig_lines: List[str], hunk_old: List[str]) -> bool:
    n = len(hunk_old)
    if n == 0:
        return True
    limit = len(orig_lines) - n + 1
    for i in range(max(0, limit)):
        if _chunk_matches_hunk(orig_lines[i:i + n], hunk_old):
            return True
    return False


def function_impl_diverged_from_gki(
    orig_lines: List[str],
    hunk_old: List[str],
    hunk_body: str,
) -> bool:
    """True when vendor already has this function but its body is not GKI-old."""
    src = "\n".join(orig_lines)
    names = extract_function_names_from_hunk_body(hunk_body)
    if not names:
        return False
    if _hunk_old_exactly_in_source(orig_lines, hunk_old):
        return False
    for name in names:
        if count_c_function_defs(src, name) >= 1:
            return True
    return False


def rej_has_diverged_function_impl(original_content: str, rej_content: str) -> bool:
    if not (rej_content or "").strip():
        return False
    orig_lines = _split_lines(original_content)
    for _os, _oc, _ns, _nc, body in _parse_rej_hunks(rej_content):
        hunk_old, _ = _parse_hunk_sides(body)
        if function_impl_diverged_from_gki(orig_lines, hunk_old, body):
            return True
    return False


def _find_function_def_line(orig_lines: List[str], name: str) -> Optional[int]:
    head = re.compile(
        rf"^(?:static(?:\s+inline)?\s+)?(?:[\w*]+\s+)+\b{re.escape(name)}\s*\("
    )
    for i, ln in enumerate(orig_lines):
        if head.match(ln):
            return i
    return None


def _find_c_function_end(lines: List[str], start: int) -> int:
    depth = 0
    seen_brace = False
    for i in range(start, len(lines)):
        for ch in lines[i]:
            if ch == "{":
                depth += 1
                seen_brace = True
            elif ch == "}":
                depth -= 1
                if seen_brace and depth == 0:
                    return i + 1
    return min(len(lines), start + 200)


def extract_named_c_function(
    source: str, name: str,
) -> Optional[Tuple[int, int, str]]:
    """Return (start, end, text) for a C function definition; skip prototypes."""
    if not source or not name:
        return None
    lines = _split_lines(source)
    head = re.compile(
        rf"^(?:static(?:\s+inline)?\s+)?(?:[\w*]+\s+)+\b{re.escape(name)}\s*\("
    )
    for i, ln in enumerate(lines):
        if not head.match(ln):
            continue
        rest = "\n".join(lines[i: min(len(lines), i + 30)])
        brace = re.search(r"\)\s*\{", rest, re.DOTALL)
        semi = re.search(r"\)\s*;", rest, re.DOTALL)
        if not brace or (semi and semi.start() < brace.start()):
            continue
        end = _find_c_function_end(lines, i)
        if end <= i + 1:
            continue
        text = "\n".join(lines[i:end])
        if "{" not in text:
            continue
        return i, end, text
    return None


def function_names_from_rej(rej_content: str) -> List[str]:
    names: List[str] = []
    seen = set()
    for _os, _oc, _ns, _nc, body in _parse_rej_hunks(rej_content):
        for name in extract_function_names_from_hunk_body(body):
            if name in seen:
                continue
            seen.add(name)
            names.append(name)
    return names


def collect_incremental_function_tasks(
    original_content: str,
    rej_content: str,
) -> List[Dict[str, Any]]:
    """LLM tasks that edit the vendor function in place (no GKI function paste)."""
    orig_lines = _split_lines(original_content)
    hunks = _parse_rej_hunks(rej_content)
    tasks: List[Dict[str, Any]] = []
    total = len(hunks)
    for i, (_os, _oc, _ns, _nc, hunk_body) in enumerate(hunks, 1):
        hunk_old, _hunk_new = _parse_hunk_sides(hunk_body)
        if not function_impl_diverged_from_gki(orig_lines, hunk_old, hunk_body):
            continue
        names = extract_function_names_from_hunk_body(hunk_body)
        located: Optional[Tuple[int, int, str]] = None
        for name in names:
            located = extract_named_c_function(original_content, name)
            if located is not None:
                break
        if located is None:
            continue
        start, end, body_text = located
        tasks.append({
            "index": i,
            "total": total,
            "start_line": start + 1,
            "end_line": end,
            "replace_start": start,
            "replace_end": end,
            "pre_len": 0,
            "post_len": 0,
            "aligned": True,
            "vendor_snippet": body_text,
            "body_snippet": body_text,
            "incoming_snippet": "",
            "incoming_body_snippet": "",
            "hunk_body": hunk_body,
            "kind": "incremental_rej",
            "incremental_only": True,
        })
    return tasks


def _add_lines_duplicate_existing_function(add_lines: List[str], current_lines: List[str]) -> bool:
    src = "\n".join(current_lines)
    for ln in add_lines[:4]:
        m = _C_FUNC_DEF_HEAD.match(ln)
        if m and count_c_function_defs(src, m.group(1)) >= 1:
            return True
    return False


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

    # Do not treat a similar-but-different function body as aligned. Vendor may
    # share the signature while the implementation differs; those hunks must be
    # applied as incremental +/- onto the existing function, not as a window replace.
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


_WEAK_CTX_LINE = re.compile(
    r"^[\s{}]*$"
    r"|^\s*(else|break;?|continue;?|return;?)\s*$"
)


def _ctx_line_strong(line: str) -> bool:
    s = (line or "").strip()
    return bool(s) and _WEAK_CTX_LINE.match(line) is None


def _suffix_strong_enough(suffix: List[str]) -> bool:
    nonempty = [s for s in suffix if s.strip()]
    if not nonempty:
        return False
    if _ctx_line_strong(nonempty[-1]):
        return True
    return len(nonempty) >= 3


def _match_ctx_suffix(lines: List[str], ctx: List[str]) -> Tuple[List[int], int]:
    """Longest ctx suffix that appears in lines. Returns (starts, matched_len).

    Vendor files often insert extra statements in the middle of a GKI hunk, so the
    full context subsequence misses. Using the unmatched full len(ctx) as an offset
    after a 1-line fallback lands inserts on the wrong later block.
    """
    if not ctx:
        return [0], 0
    for k in range(len(ctx), 0, -1):
        suffix = ctx[-k:]
        if k < len(ctx) and not _suffix_strong_enough(suffix):
            continue
        positions = _find_all_subsequence(lines, suffix)
        if positions:
            return positions, k
    return [], 0


def _is_block_closer(line: str) -> bool:
    return (line or "").strip() in ("}", "};", "else", "else {")


def _last_nonempty(seq: List[str]) -> Optional[str]:
    for item in reversed(seq or []):
        if item.strip():
            return item
    return None


def _first_nonempty(seq: List[str]) -> Optional[str]:
    for item in seq or []:
        if item.strip():
            return item
    return None


_CONTROL_HEAD = re.compile(r"^\s*(if|else\s+if|while|for|switch)\b")


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _read_control_header(lines: List[str], start: int) -> str:
    """Collapse a possibly multiline if/while/for header, without the opening brace."""
    if start < 0 or start >= len(lines):
        return ""
    parts = [lines[start].rstrip()]
    joined = lines[start]
    i = start
    while i + 1 < len(lines) and "{" not in joined and not joined.rstrip().endswith(";"):
        i += 1
        parts.append(lines[i].rstrip())
        joined = "\n".join(parts)
        if _CONTROL_HEAD.match(lines[i]) and i > start:
            parts.pop()
            break
    header = _norm_ws(" ".join(p.strip() for p in parts))
    return header.split("{")[0].strip()


def _headers_match(a: str, b: str) -> bool:
    na, nb = _norm_ws(a), _norm_ws(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return na.startswith(nb) or nb.startswith(na)


def _block_end(lines: List[str], start: int) -> Optional[int]:
    """Line after the block that starts at `start` (header). None if no braces."""
    depth = 0
    seen = False
    for i in range(start, len(lines)):
        for ch in lines[i]:
            if ch == "{":
                depth += 1
                seen = True
            elif ch == "}":
                depth -= 1
                if seen and depth == 0:
                    return i + 1
    return None if not seen else len(lines)


def _control_span(lines: List[str], header: str) -> Optional[Tuple[int, int]]:
    """[start, end) of the vendor block whose if/while header matches `header`."""
    if not header:
        return None
    for i, ln in enumerate(lines):
        if not _CONTROL_HEAD.match(ln):
            continue
        got = _read_control_header(lines, i)
        if not _headers_match(got, header):
            continue
        end = _block_end(lines, i)
        if end is None:
            continue
        return i, end
    return None


def _line_is_comment(s: str) -> bool:
    t = (s or "").strip()
    return t.startswith("/*") or t.startswith("*") or t.startswith("//")


def _comment_before(lines: List[str], idx: int) -> Optional[str]:
    parts: List[str] = []
    i = idx - 1
    while i >= 0 and not lines[i].strip():
        i -= 1
    while i >= 0 and _line_is_comment(lines[i]):
        parts.append(lines[i].strip())
        i -= 1
        if parts[-1].startswith("/*") or parts[-1].startswith("//"):
            break
    if not parts:
        return None
    parts.reverse()
    return _norm_ws(" ".join(parts))


def _enclosing_controls(
    lines: List[str], at: int,
) -> Tuple[List[str], Optional[str]]:
    """Innermost-first if/while/for headers enclosing lines[at], plus nearest comment."""
    if at < 0 or at >= len(lines):
        return [], None
    stack: List[Tuple[str, int, Optional[str]]] = []
    pending: Optional[str] = None
    pending_at = 0
    depth = 0
    for i in range(0, at + 1):
        if _CONTROL_HEAD.match(lines[i]):
            pending = _read_control_header(lines, i)
            pending_at = i
        for ch in lines[i]:
            if ch == "{":
                depth += 1
                if pending:
                    stack.append((pending, depth, _comment_before(lines, pending_at)))
                    pending = None
            elif ch == "}":
                while stack and stack[-1][1] == depth:
                    stack.pop()
                depth -= 1
    headers = [h for h, _d, _c in reversed(stack)]
    comment = None
    for _h, _d, c in reversed(stack):
        if c:
            comment = c
            break
    return headers, comment


def _iter_groups_with_logic(hunk_body: str):
    """Yield (ctx, dels, adds, trail, headers, comment) using GKI-old control flow."""
    old_lines, _new = _parse_hunk_sides(hunk_body)
    cursor = 0
    for ctx, dels, adds, trail in _iter_hunk_micro_groups(hunk_body):
        at: Optional[int] = None
        if ctx:
            at = cursor + len(ctx) - 1
            cursor += len(ctx)
        elif cursor:
            at = cursor - 1
        headers: List[str] = []
        comment: Optional[str] = None
        if at is not None and 0 <= at < len(old_lines):
            headers, comment = _enclosing_controls(old_lines, at)
        cursor += len(dels)
        yield ctx, dels, adds, trail, headers, comment


def _anchor_in_logic_windows(
    lines: List[str],
    ctx: List[str],
    dels: List[str],
    trail: Optional[List[str]],
    headers: List[str],
) -> Tuple[Optional[int], Optional[int]]:
    """Prefer the vendor branch with the same if/while as GKI, then fall back to the whole file."""
    windows: List[Tuple[int, int]] = []
    for header in headers:
        span = _control_span(lines, header)
        if span and span not in windows:
            windows.append(span)
    full = (0, len(lines))
    if full not in windows:
        windows.append(full)
    for lo, hi in windows:
        sub = lines[lo:hi]
        anchor, rep_pos = _pick_context_anchor(sub, ctx, dels, trail)
        if anchor is None:
            continue
        return lo + anchor, (lo + rep_pos) if rep_pos is not None else None
    return None, None


def build_function_logic_hints(hunk_body: str, vendor_source: str = "") -> str:
    """Describe which control-flow branch each GKI +/- belongs to."""
    if not (hunk_body or "").strip():
        return ""
    names = extract_function_names_from_hunk_body(hunk_body)
    vendor_lines = _split_lines(vendor_source)
    for name in names:
        located = extract_named_c_function(vendor_source, name)
        if located:
            vendor_lines = _split_lines(located[2])
            break
    old_lines, _ = _parse_hunk_sides(hunk_body)
    old_headers = []
    for i, ln in enumerate(old_lines):
        if _CONTROL_HEAD.match(ln):
            old_headers.append(_read_control_header(old_lines, i))
    foreign: List[str] = []
    for i, ln in enumerate(vendor_lines):
        if not _CONTROL_HEAD.match(ln):
            continue
        header = _read_control_header(vendor_lines, i)
        if any(_headers_match(header, h) for h in old_headers):
            continue
        extra = ""
        end = _block_end(vendor_lines, i)
        body = "\n".join(vendor_lines[i:end] if end else vendor_lines[i:i + 8])
        if "CONTINUOUS_WR" in body:
            extra = "（厂商独有 CONTINUOUS_WR 路径）"
        elif "qos" in body.lower() or "pm_qos" in body:
            extra = "（厂商独有 qos 路径）"
        foreign.append(f"{header}{extra}")
        if len(foreign) >= 6:
            break

    items: List[str] = []
    for ctx, dels, adds, _trail, headers, comment in _iter_groups_with_logic(hunk_body):
        if not adds:
            continue
        preview = " / ".join(a.strip() for a in adds[:3] if a.strip())[:120]
        kind = "替换" if dels else "插入"
        chain = " → ".join(headers[:3]) if headers else "函数体顶层（声明/序言）"
        located = "vendor 中未扫到字面相同的 if/while（仍按 .rej 上下文合入）"
        for header in headers:
            if _control_span(vendor_lines, header):
                located = f"vendor 中可参考的对应分支: {header}"
                break
        piece = f"• {kind} `{preview}`\n  所属控制流: {chain}"
        if comment:
            piece += f"\n  注释: {comment[:160]}"
        piece += f"\n  {located}"
        items.append(piece)
        if len(items) >= 8:
            break
    if not items and not foreign:
        return ""
    lines_out = [
        "【实现逻辑参考，辅助合入】下面从 GKI 旧实现还原控制流与注释，用来帮助判断"
        "每条 +/- 在函数里的意图、更适合落在 vendor 的哪条路径。"
        "这是参考信息，不是唯一规则：仍要结合 .rej 上下文和 vendor 定制一起合入。",
    ]
    lines_out.extend(items)
    if foreign:
        lines_out.append("vendor 中多出来的分支（合入时注意不要把 GKI 改动误写入这些路径）:")
        for h in foreign:
            lines_out.append(f"• {h}")
    return "\n".join(lines_out)


def _iter_hunk_micro_groups(
    hunk_body: str,
) -> List[Tuple[List[str], List[str], List[str], List[str]]]:
    """Split a unified-diff hunk into (ctx, dels, adds, trailing-ctx) groups."""
    hunk_lines = [ln for ln in (hunk_body or "").splitlines() if ln]
    groups: List[Tuple[List[str], List[str], List[str], List[str]]] = []
    i = 0
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
        trail: List[str] = []
        j = i
        while j < len(hunk_lines) and hunk_lines[j][:1] == " ":
            trail.append(hunk_lines[j][1:])
            j += 1
        groups.append((ctx, dels, adds, trail))
    return groups


def _insert_site_ok(
    lines: List[str],
    anchor: int,
    ctx: List[str],
    trail: Optional[List[str]] = None,
) -> bool:
    """Insert must sit immediately after last context; block closers must still follow."""
    if anchor < 0 or anchor > len(lines):
        return False
    last_ctx = _last_nonempty(ctx)
    if last_ctx is None:
        return False
    if anchor == 0 or lines[anchor - 1].strip() != last_ctx.strip():
        return False
    first_trail = _first_nonempty(trail or [])
    if first_trail and _is_block_closer(first_trail):
        if anchor >= len(lines) or lines[anchor].strip() != first_trail.strip():
            return False
    return True


def _micro_inserts_follow_hunk_body(source: str, hunk_body: str) -> bool:
    """True if each insert-only group sits immediately after its .rej context."""
    if not (hunk_body or "").strip():
        return True
    lines = _split_lines(source)
    for ctx, dels, adds, trail in _iter_hunk_micro_groups(hunk_body):
        if dels or not adds:
            continue
        last_ctx = _last_nonempty(ctx)
        if last_ctx is None:
            return False
        needle = [last_ctx] + adds
        first_trail = _first_nonempty(trail)
        if first_trail and _is_block_closer(first_trail):
            needle = needle + [first_trail]
        if _find_subsequence(lines, needle) is None:
            return False
    return True


def _micro_inserts_follow_context(source: str, rej_content: str) -> bool:
    """Reject merges where a + insert is not immediately after its .rej context."""
    hunks = _parse_rej_hunks(rej_content)
    bodies = [h[4] for h in hunks] if hunks else (
        [rej_content] if (rej_content or "").strip() else []
    )
    return all(_micro_inserts_follow_hunk_body(source, body) for body in bodies)


_MICRO_INSERT_PLACEMENT_ERR = (
    "合入结果未把 .rej 的 + 行紧挨其 context 落地"
    "（可能插到厂商其它代码块），已拒绝写回，请手动合入"
)


def assert_micro_inserts_follow_context(source: str, rej_or_hunk: str) -> None:
    """Raise if insert-only .rej + lines are not adjacent to their context."""
    if (rej_or_hunk or "").strip() and not _micro_inserts_follow_context(
        source, rej_or_hunk,
    ):
        raise RuntimeError(_MICRO_INSERT_PLACEMENT_ERR)


def _pick_context_anchor(
    lines: List[str],
    ctx: List[str],
    dels: List[str],
    trail: Optional[List[str]] = None,
) -> Tuple[Optional[int], Optional[int]]:
    """Pick context match; prefer last site where dels follow context (vendor prefix code)."""
    if not ctx:
        return (0, None) if dels else (None, None)
    positions, matched_len = _match_ctx_suffix(lines, ctx)
    if not positions:
        return None, None

    for pos in reversed(positions):
        anchor = pos + matched_len
        if dels:
            rep_pos = _find_subsequence(lines, dels, anchor)
            if rep_pos is not None and rep_pos <= anchor + 20:
                return anchor, rep_pos
            continue
        if _insert_site_ok(lines, anchor, ctx, trail):
            return anchor, None

    if dels:
        for pos in reversed(positions):
            anchor = pos + matched_len
            rep_pos = _find_subsequence(lines, dels, max(0, pos))
            if rep_pos is not None and rep_pos <= anchor + 30:
                return anchor, rep_pos
        return None, None
    return None, None


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

    Walks unified-diff hunk body: for each context + (-lines / +lines) group, prefer
    the vendor if/while whose condition matches GKI-old (implementation logic as a
    hint), then fall back to full-file context match. Does not replace the whole
    function. Insert-only groups must sit immediately after the matched context;
    if the next hunk line is a block closer (`}`), that closer must still be the
    next source line.
    """
    if not hunk_body.strip():
        return source, 0
    lines = _split_lines(source)
    applied = 0

    for ctx, dels, adds, trail, headers, _comment in _iter_groups_with_logic(hunk_body):
        anchor, rep_pos = _anchor_in_logic_windows(lines, ctx, dels, trail, headers)
        if anchor is None:
            continue

        if dels:
            if rep_pos is None:
                last_ctx = _last_nonempty(ctx)
                start = 0
                if last_ctx:
                    ctx_pos = _find_subsequence(lines, [last_ctx])
                    if ctx_pos is not None:
                        start = ctx_pos
                rep_pos = _find_subsequence(lines, dels, start)
                if rep_pos is not None and last_ctx and rep_pos > start + 40:
                    rep_pos = None
            if rep_pos is not None:
                lines[rep_pos:rep_pos + len(dels)] = adds
                applied += 1
                continue

        if adds and not dels:
            chunk = "\n".join(lines)
            if all(a.strip() in chunk for a in adds if a.strip()):
                continue
            if _add_lines_duplicate_existing_function(adds, lines):
                continue
            if not _insert_site_ok(lines, anchor, ctx, trail):
                continue
            lines[anchor:anchor] = adds
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
