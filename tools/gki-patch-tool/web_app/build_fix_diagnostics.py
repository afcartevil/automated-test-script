"""GCC diagnostic parsing, error-note chains, and multi-anchor snippets for build_fix."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

_MAX_ERRORS_PER_FILE = 8

_GCC_DIAG_RE = re.compile(
    r"^(?P<file>[^\s:\'\"<>|]+?\.(?:c|h|S|cpp|cc|rs|dts|dtsi|ld|Kconfig|Makefile|mk|java|aidl))"
    r":(?P<line>\d+)(?::(?P<col>\d+))?\s*:\s*"
    r"(?P<kind>error|fatal error|note|warning)\s*:\s*(?P<msg>.+)$",
    re.MULTILINE | re.IGNORECASE,
)
_MACRO_DEFINED_NOTE_RE = re.compile(
    r"macro\s+'(?P<macro>[^']+)'\s+defined here",
    re.IGNORECASE,
)
_PREV_DEF_NOTE_RE = re.compile(
    r"previous definition|this is the location of the previous definition",
    re.IGNORECASE,
)
_CASCADE_MSG_RE = re.compile(
    r"undeclared identifier|expected ';'|invalid suffix|incomplete type",
    re.IGNORECASE,
)
_MACRO_INVOKE_MSG_RE = re.compile(
    r"too many arguments.*macro|function-like macro invocation",
    re.IGNORECASE,
)
_MACRO_REDEFINED_ERR_RE = re.compile(
    r'"([^"]+)"\s+redefined',
    re.IGNORECASE,
)


def _norm_path(path: str) -> str:
    return (path or "").replace("\\", "/").strip()


def is_kernel_readonly_path(path: str) -> bool:
    """True for include/linux/* (GKI/upstream headers; never patch)."""
    p = _norm_path(path).lower()
    return "/include/linux/" in p or p.startswith("include/linux/")


_is_kernel_readonly_path = is_kernel_readonly_path


def parse_gcc_diagnostic_entries(log_segment: str) -> List[Dict[str, Any]]:
    """Parse gcc/clang diagnostic lines in log order."""
    entries: List[Dict[str, Any]] = []
    for seq, m in enumerate(_GCC_DIAG_RE.finditer(log_segment or "")):
        kind = m.group("kind").lower()
        if kind == "fatal error":
            kind = "error"
        msg = m.group("msg").strip()
        path = _norm_path(m.group("file"))
        row: Dict[str, Any] = {
            "seq": seq,
            "file": path,
            "line": int(m.group("line")),
            "column": int(m.group("col")) if m.group("col") else None,
            "kind": kind,
            "message": msg,
        }
        macro_m = _MACRO_DEFINED_NOTE_RE.search(msg)
        if macro_m:
            row["macro"] = macro_m.group("macro")
        if kind == "note" and _PREV_DEF_NOTE_RE.search(msg):
            row["note_kind"] = "previous_definition"
        elif kind == "note" and macro_m:
            row["note_kind"] = "macro_defined_here"
        entries.append(row)
    return entries


def select_errors_for_llm(
    entries: List[Dict[str, Any]],
    *,
    max_total: int = 20,
    max_per_file: int = _MAX_ERRORS_PER_FILE,
) -> List[Dict[str, Any]]:
    """Keep multiple errors per file; include paired notes."""
    errors_by_file: Dict[str, List[Dict[str, Any]]] = {}
    notes: List[Dict[str, Any]] = []
    for entry in entries:
        if entry.get("kind") == "error":
            key = _norm_path(entry.get("file") or "").lower()
            errors_by_file.setdefault(key, []).append(dict(entry))
        elif entry.get("kind") == "note":
            notes.append(dict(entry))

    selected_errors: List[Dict[str, Any]] = []
    for _key, file_errors in errors_by_file.items():
        # Preserve log order within file; cap per file.
        for err in file_errors[:max_per_file]:
            selected_errors.append(err)

    selected_errors.sort(key=lambda e: int(e.get("seq") or 0))
    if len(selected_errors) > max_total:
        selected_errors = selected_errors[-max_total:]

    selected_seq = {int(e.get("seq") or -1) for e in selected_errors}
    selected_notes: List[Dict[str, Any]] = []
    for note in notes:
        nseq = int(note.get("seq") or -1)
        for eseq in selected_seq:
            if 0 <= nseq - eseq <= 4:
                selected_notes.append(note)
                break

    merged = selected_errors + selected_notes
    merged.sort(key=lambda e: (int(e.get("seq") or 0), e.get("kind") != "error"))
    return merged[: max_total + 12]


def build_diagnostic_chains(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pair vendor errors with kernel notes into diagnostic chains."""
    chains_by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def _find_readonly_note(
        start: int,
        entry: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        start_file = _norm_path(entry.get("file") or "").lower()
        for j in range(start + 1, min(start + 8, len(entries))):
            nxt = entries[j]
            if nxt.get("kind") == "error":
                if _norm_path(nxt.get("file") or "").lower() != start_file:
                    break
                continue
            if nxt.get("kind") != "note":
                continue
            note_msg = nxt.get("message") or ""
            macro = nxt.get("macro") or (
                _MACRO_DEFINED_NOTE_RE.search(note_msg).group("macro")
                if _MACRO_DEFINED_NOTE_RE.search(note_msg)
                else None
            )
            if macro and _is_kernel_readonly_path(nxt.get("file") or ""):
                return dict(nxt), macro
            if nxt.get("note_kind") == "previous_definition" or _PREV_DEF_NOTE_RE.search(note_msg):
                return dict(nxt), None
        return None, None

    for i, entry in enumerate(entries):
        if entry.get("kind") != "error":
            continue
        msg = entry.get("message") or ""
        readonly_note, symbol = _find_readonly_note(i, entry)
        if not readonly_note:
            continue

        primary_file = _norm_path(entry.get("file") or "").lower()
        chain_type: Optional[str] = None
        if symbol and (
            _MACRO_INVOKE_MSG_RE.search(msg)
            or _CASCADE_MSG_RE.search(msg)
            or "expected ';'" in msg
        ):
            chain_type = "kernel_macro_collision"
        elif "redefin" in msg.lower():
            chain_type = "macro_redefinition"
            if not symbol:
                macro_m = _MACRO_REDEFINED_ERR_RE.search(msg)
                if macro_m:
                    symbol = macro_m.group(1)
        if not chain_type:
            continue

        key = (primary_file, symbol or chain_type)
        if key in chains_by_key:
            existing = chains_by_key[key]
            pline = int(existing["primary_error"].get("line") or 0)
            eline = int(entry.get("line") or 0)
            if eline == pline:
                existing.setdefault("related_errors", []).append(dict(entry))
            elif _CASCADE_MSG_RE.search(msg):
                existing.setdefault("cascade_errors", []).append(dict(entry))
            elif eline > pline:
                existing.setdefault("related_errors", []).append(dict(entry))
            continue

        chains_by_key[key] = {
            "chain_type": chain_type,
            "symbol": symbol,
            "primary_error": dict(entry),
            "readonly_note": readonly_note,
            "related_errors": [],
            "cascade_errors": [],
        }

    for chain in chains_by_key.values():
        primary = chain["primary_error"]
        primary_file = _norm_path(primary.get("file") or "").lower()
        primary_line = int(primary.get("line") or 0)
        primary_seq = int(primary.get("seq") or -1)
        related_seq = {
            int(r.get("seq") or -1) for r in chain.get("related_errors") or []
        }
        cascade_seq = {
            int(c.get("seq") or -1) for c in chain.get("cascade_errors") or []
        }
        for other in entries:
            if other.get("kind") != "error":
                continue
            if _norm_path(other.get("file") or "").lower() != primary_file:
                continue
            oseq = int(other.get("seq") or -1)
            if oseq == primary_seq or oseq in related_seq or oseq in cascade_seq:
                continue
            omsg = other.get("message") or ""
            oline = int(other.get("line") or 0)
            if _CASCADE_MSG_RE.search(omsg):
                chain["cascade_errors"].append(dict(other))
                cascade_seq.add(oseq)
            elif oline >= primary_line:
                chain["related_errors"].append(dict(other))
                related_seq.add(oseq)

        chain["related_errors"] = chain["related_errors"][:6]
        chain["cascade_errors"] = chain["cascade_errors"][:4]

    return list(chains_by_key.values())


def assign_error_priorities(
    errors: List[Dict[str, Any]],
    chains: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Tag each error with error_priority for sorting and snippet anchors."""
    primary_seq: set[int] = set()
    related_seq: set[int] = set()
    cascade_seq: set[int] = set()
    for chain in chains:
        pe = chain.get("primary_error") or {}
        primary_seq.add(int(pe.get("seq") or -1))
        for rel in chain.get("related_errors") or []:
            related_seq.add(int(rel.get("seq") or -1))
        for cas in chain.get("cascade_errors") or []:
            cascade_seq.add(int(cas.get("seq") or -1))

    enriched: List[Dict[str, Any]] = []
    for err in errors:
        row = dict(err)
        seq = int(row.get("seq") or -1)
        if seq in primary_seq:
            row["error_priority"] = "primary"
        elif seq in cascade_seq:
            row["error_priority"] = "cascade"
        elif seq in related_seq:
            row["error_priority"] = "related"
        elif row.get("kind") == "note":
            if row.get("note_kind") == "macro_defined_here" and _is_kernel_readonly_path(row.get("file") or ""):
                row["error_priority"] = "readonly_note"
            else:
                row["error_priority"] = "note"
        else:
            row["error_priority"] = "error"
        enriched.append(row)
    return enriched


def multi_anchor_snippet(
    content: str,
    anchors: List[Dict[str, Any]],
    *,
    radius: int = 40,
) -> str:
    """Build snippet with multiple >>> markers at error lines."""
    lines = content.splitlines()
    if not lines:
        return content[:8000]

    anchor_lines = sorted({
        max(1, min(len(lines), int(a.get("line") or 1)))
        for a in anchors
        if a.get("line")
    })
    if not anchor_lines:
        return _single_anchor_snippet(lines, 1, radius)

    start = max(0, min(anchor_lines) - 1 - radius)
    end = min(len(lines), max(anchor_lines) + radius)
    marked = {ln for ln in anchor_lines}
    out: List[str] = []
    for i in range(start, end):
        prefix = ">>>" if (i + 1) in marked else "   "
        out.append(f"{prefix} {i + 1:5d}| {lines[i]}")
    return "\n".join(out)


def _single_anchor_snippet(lines: List[str], line_no: int, radius: int) -> str:
    idx = max(0, min(len(lines) - 1, line_no - 1))
    start = max(0, idx - radius)
    end = min(len(lines), idx + radius + 1)
    out: List[str] = []
    for i in range(start, end):
        prefix = ">>>" if i == idx else "   "
        out.append(f"{prefix} {i + 1:5d}| {lines[i]}")
    return "\n".join(out)


def format_diagnostic_chains_for_llm(chains: List[Dict[str, Any]]) -> str:
    """Render diagnostic chains as structured text for LLM."""
    if not chains:
        return ""
    parts = ["=== 编译诊断链（error 与 note 配对，按因果顺序阅读） ==="]
    for idx, chain in enumerate(chains[:8], 1):
        ctype = chain.get("chain_type") or "unknown"
        symbol = chain.get("symbol") or "?"
        pe = chain.get("primary_error") or {}
        parts.append(f"链 #{idx} [{ctype}] 符号={symbol}")
        parts.append(
            f"  primary: {pe.get('file', '?')}:{pe.get('line', '?')}: {pe.get('message', '')}"
        )
        rn = chain.get("readonly_note")
        if rn:
            parts.append(
                f"  readonly note: {rn.get('file', '?')}:{rn.get('line', '?')}: {rn.get('message', '')}"
            )
        for rel in chain.get("related_errors") or []:
            parts.append(
                f"  related: {rel.get('file', '?')}:{rel.get('line', '?')}: {rel.get('message', '')}"
            )
        for cas in chain.get("cascade_errors") or []:
            parts.append(
                f"  cascade: {cas.get('file', '?')}:{cas.get('line', '?')}: {cas.get('message', '')}"
            )
    return "\n".join(parts)


def parse_build_log_diagnostics(
    log_segment: str,
    *,
    max_errors: int = 20,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (enriched errors+notes, diagnostic chains) from a log segment."""
    entries = parse_gcc_diagnostic_entries(log_segment)
    selected = select_errors_for_llm(entries, max_total=max_errors)
    chains = build_diagnostic_chains(entries)
    enriched = assign_error_priorities(selected, chains)
    return enriched, chains


def _match_path_for_focus(err_path: str, focus_path: str) -> bool:
    err = _norm_path(err_path).lower().lstrip("/")
    focus = _norm_path(focus_path).lower().lstrip("/")
    if not err or not focus:
        return False
    if err == focus or err.endswith("/" + focus) or focus.endswith("/" + err):
        return True
    import posixpath
    return posixpath.basename(err) == posixpath.basename(focus)


def filter_diagnostics_for_focus(
    errors: List[Dict[str, Any]],
    chains: List[Dict[str, Any]],
    readonly_notes: Optional[List[Dict[str, Any]]],
    focus_path: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Keep only diagnostics relevant to a single-file LLM call."""
    filtered_chains = [
        c for c in (chains or [])
        if _match_path_for_focus((c.get("primary_error") or {}).get("file", ""), focus_path)
    ]
    chain_note_keys = {
        f"{_norm_path((c.get('readonly_note') or {}).get('file', ''))}:"
        f"{(c.get('readonly_note') or {}).get('line', '')}"
        for c in filtered_chains
        if c.get("readonly_note")
    }
    filtered_errors: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for err in errors or []:
        kind = (err.get("kind") or "").lower()
        if kind == "note":
            key = f"note:{_norm_path(err.get('file', ''))}:{err.get('line')}"
            if key in seen:
                continue
            if err.get("note_kind") == "macro_defined_here":
                nkey = f"{_norm_path(err.get('file', ''))}:{err.get('line')}"
                if nkey in chain_note_keys or _is_kernel_readonly_path(err.get("file") or ""):
                    seen.add(key)
                    filtered_errors.append(err)
            continue
        if not _match_path_for_focus(err.get("file", ""), focus_path):
            continue
        key = f"err:{err.get('line')}:{(err.get('message') or '')[:40]}"
        if key in seen:
            continue
        seen.add(key)
        filtered_errors.append(err)

    filtered_notes: List[Dict[str, Any]] = []
    note_seen: set[str] = set()
    for note in readonly_notes or []:
        nkey = f"{_norm_path(note.get('path') or note.get('fix_path') or '')}:{note.get('line')}"
        if nkey in note_seen:
            continue
        note_seen.add(nkey)
        filtered_notes.append(note)
    if not filtered_notes and filtered_chains:
        for c in filtered_chains:
            rn = c.get("readonly_note") or {}
            nkey = f"{_norm_path(rn.get('file', ''))}:{rn.get('line')}"
            if nkey in note_seen:
                continue
            note_seen.add(nkey)
            filtered_notes.append({
                "path": rn.get("file", ""),
                "fix_path": rn.get("file", ""),
                "line": rn.get("line"),
                "macro": c.get("symbol") or rn.get("macro") or "",
                "message": rn.get("message") or "",
                "readonly": True,
            })
    return filtered_errors, filtered_chains, filtered_notes[:3]


def _pick_collision_rename(symbol: str, content: str) -> str:
    for suffix in ("_local", "_wa", "_vendor"):
        candidate = f"{symbol}{suffix}"
        if not re.search(rf"\b{re.escape(candidate)}\b", content):
            return candidate
    return f"{symbol}_fixed"


def _has_static_symbol_definition(content: str, symbol: str) -> bool:
    if not symbol or not content:
        return False
    pat = re.compile(
        rf"^\s*static\s+[\w\s\*]+?\b{re.escape(symbol)}\s*\(",
        re.MULTILINE,
    )
    return bool(pat.search(content))


def try_rename_kernel_macro_collision(content: str, symbol: str) -> Optional[str]:
    """Rename a vendor static symbol that collides with a kernel macro (all references)."""
    if not symbol or not _has_static_symbol_definition(content, symbol):
        return None
    if not re.search(rf"\b{re.escape(symbol)}\b", content):
        return None
    new_name = _pick_collision_rename(symbol, content)
    return re.sub(rf"\b{re.escape(symbol)}\b", new_name, content)


def collision_call_site_lines(content: str, symbol: str) -> List[int]:
    """Return 1-based line numbers where symbol is invoked or defined."""
    if not symbol or not content:
        return []
    pat = re.compile(rf"\b{re.escape(symbol)}\b")
    lines: List[int] = []
    for i, line in enumerate(content.splitlines(), 1):
        if pat.search(line):
            lines.append(i)
    return lines


def chains_matching_file(
    chains: List[Dict[str, Any]],
    file_path: str,
) -> List[Dict[str, Any]]:
    return [
        c for c in (chains or [])
        if _match_path_for_focus((c.get("primary_error") or {}).get("file", ""), file_path)
    ]
