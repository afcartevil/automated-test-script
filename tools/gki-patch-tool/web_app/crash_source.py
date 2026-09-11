"""Fetch GKI crash-site source from the local kernel repo at a tag."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_FILE_LINE_RE = re.compile(
    r"(?<![A-Za-z0-9_])((?:[A-Za-z0-9_.-]+/){0,12}[A-Za-z0-9_.-]+\.(?:c|h|S)):(\d+)"
)
_PC_FUNC_RE = re.compile(
    r"(?:PC is at|LR is at|pc\s*:|lr\s*:|RIP:)\s*(?:\[[0-9a-fxA-FX]+\]\s*)?([A-Za-z_][\w.]*)\+0x[0-9a-fA-F]+",
    re.IGNORECASE,
)
_TRACE_FUNC_RE = re.compile(r"\b([A-Za-z_][\w.]*)\+0x[0-9a-fA-F]+/0x[0-9a-fA-F]+")
_GENERIC_FUNCS = {
    "panic", "die", "oops_end", "bug", "kasan_report", "dump_stack", "dump_stack_lvl",
    "dump_backtrace", "show_stack", "arm64_serror", "el1_abort", "el1h_64_sync",
    "el1h_64_sync_handler", "do_mem_abort", "do_sp_pc_abort", "do_page_fault",
    "do_translation_fault", "__do_kernel_fault", "notifier_call_chain", "notify_die",
    "mrdump_common_die", "ipanic_die", "console_unlock", "printk",
    "queued_spin_lock_slowpath",
}
_KERNEL_TOPDIRS = (
    "fs", "mm", "kernel", "drivers", "net", "arch", "include", "block",
    "crypto", "security", "sound", "virt", "io_uring", "ipc", "lib", "init",
)
_PREFERRED_PREFIXES = (
    "kernel/", "mm/", "fs/", "drivers/", "net/", "arch/arm64/", "arch/", "include/",
)
_CONTEXT = 18
_MAX_SNIPPETS = 4
_MAX_FUNC_LINES = 80
_PLACEHOLDER_PATHS = {
    "-", "n/a", "na", "none", "null", "nil", "unknown", "unk",
    "未知", "不详", "未提供", "无",
}


def _run_git(repo_dir: str, args: Sequence[str], timeout: int = 30) -> str:
    from tools.patch_analyzer import run_git

    return run_git(Path(repo_dir), list(args), timeout=timeout) or ""


def _normalize_kernel_path(path: str) -> str:
    """Strip dump prefixes like /proc/self/cwd/common/ so GKI paths resolve."""
    text = (path or "").strip().replace("\\", "/")
    if text.startswith("/"):
        text = text.lstrip("/")
    for prefix in ("proc/self/cwd/", "proc/self/cwd"):
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip("/")
            break
    if text.startswith("common/"):
        rest = text[len("common/"):]
        top = rest.split("/", 1)[0]
        if top in _KERNEL_TOPDIRS:
            text = rest
    return text


def _is_usable_source_path(path: str) -> bool:
    text = _normalize_kernel_path(path)
    if not text or text.lower() in _PLACEHOLDER_PATHS or text in _PLACEHOLDER_PATHS:
        return False
    if " " in text or text.startswith("/"):
        return False
    return bool(re.search(r"\.(?:c|h|S)$", text))


def parse_crash_sites(crash_log: str) -> Dict[str, Any]:
    """Extract file:line hits and likely crash function from a kernel log."""
    text = crash_log or ""
    files: List[Dict[str, Any]] = []
    seen = set()
    for match in _FILE_LINE_RE.finditer(text):
        path = _normalize_kernel_path(match.group(1))
        line = int(match.group(2))
        if not path or path.startswith("/") or " " in path:
            continue
        key = (path, line)
        if key in seen:
            continue
        seen.add(key)
        files.append({"path": path, "line": line})

    func = ""
    pc = _PC_FUNC_RE.search(text)
    if pc and pc.group(1) not in _GENERIC_FUNCS:
        func = pc.group(1)
    if not func:
        for match in _TRACE_FUNC_RE.finditer(text):
            name = match.group(1)
            if name not in _GENERIC_FUNCS and len(name) > 3:
                func = name
                break
    return {"files": files[:12], "function": func}


def _list_tree(repo_dir: str, tag: str) -> List[str]:
    try:
        out = _run_git(repo_dir, ["ls-tree", "-r", "--name-only", tag], timeout=90)
    except Exception:
        return []
    return [line.strip().replace("\\", "/") for line in (out or "").splitlines() if line.strip()]


def resolve_source_path(tree: Sequence[str], raw_path: str) -> str:
    path = (raw_path or "").strip().replace("\\", "/")
    if not path:
        return ""
    if path in tree:
        return path
    basename = path.rsplit("/", 1)[-1]
    matches = [item for item in tree if item == basename or item.endswith("/" + basename)]
    if not matches:
        return ""
    if path in matches:
        return path
    for prefix in _PREFERRED_PREFIXES:
        preferred = [item for item in matches if item.startswith(prefix)]
        if preferred:
            return preferred[0]
    if "/" in path:
        suffix = "/" + path
        for item in matches:
            if item.endswith(suffix):
                return item
    return matches[0]


def _show_file(repo_dir: str, tag: str, path: str) -> str:
    try:
        return _run_git(repo_dir, ["show", f"{tag}:{path}"], timeout=30)
    except Exception:
        return ""


def _find_function_span(lines: Sequence[str], function: str) -> Optional[Tuple[int, int]]:
    if not function:
        return None
    pattern = re.compile(rf"\b{re.escape(function)}\s*\(")
    start = None
    fallback = None
    for index, line in enumerate(lines):
        if not pattern.search(line) or line.lstrip().startswith(("*", "//", "#")):
            continue
        if line[:1] in " \t":
            if fallback is None:
                fallback = index
            continue
        start = index
        break
    if start is None:
        start = fallback
    if start is None:
        return None
    end = min(len(lines), start + _MAX_FUNC_LINES)
    depth = 0
    seen_brace = False
    for index in range(start, end):
        depth += lines[index].count("{") - lines[index].count("}")
        if "{" in lines[index]:
            seen_brace = True
        if seen_brace and depth <= 0:
            return start, index + 1
    return start, end


def format_snippet(
    content: str,
    *,
    highlight_line: int = 0,
    function: str = "",
    context: int = _CONTEXT,
    prefer_function: bool = False,
) -> Dict[str, Any]:
    lines = (content or "").splitlines()
    if not lines:
        return {"start_line": 1, "text": "", "highlight_line": highlight_line, "function": function}

    start = 0
    end = len(lines)
    span = _find_function_span(lines, function) if function else None
    highlight_ok = 0 < highlight_line <= len(lines)
    if prefer_function and span:
        start, end = span
    elif highlight_ok:
        idx = max(0, highlight_line - 1)
        start = max(0, idx - context)
        end = min(len(lines), idx + context + 1)
    elif span:
        start, end = span
    elif prefer_function:
        end = min(len(lines), _MAX_FUNC_LINES)
    elif highlight_line > 0 and span is None:
        # Grep line may exceed short fixtures; keep a usable head slice.
        end = min(len(lines), _MAX_FUNC_LINES)

    numbered: List[str] = []
    for offset, line in enumerate(lines[start:end]):
        lineno = start + offset + 1
        mark = ">" if highlight_line and lineno == highlight_line else " "
        numbered.append(f"{mark}{lineno:6d}| {line}")
    return {
        "start_line": start + 1,
        "text": "\n".join(numbered),
        "highlight_line": highlight_line,
        "function": function,
    }


def _parse_path_hit(raw: Any, default_line: int = 0) -> Dict[str, Any]:
    text = str(raw or "").strip().replace("\\", "/")
    if not text:
        return {}
    match = _FILE_LINE_RE.search(text)
    if match:
        return {"path": _normalize_kernel_path(match.group(1)), "line": int(match.group(2))}
    path, sep, tail = text.rpartition(":")
    if sep and path and tail.isdigit():
        return {"path": _normalize_kernel_path(path), "line": int(tail)}
    return {"path": _normalize_kernel_path(text), "line": int(default_line or 0)}


def _path_show_candidates(path: str) -> List[str]:
    normalized = _normalize_kernel_path(path)
    out: List[str] = []
    for item in (normalized, path.replace("\\", "/")):
        if item and item not in out:
            out.append(item)
        if item.startswith(tuple(f"{top}/" for top in _KERNEL_TOPDIRS)):
            alt = "common/" + item
            if alt not in out:
                out.append(alt)
    return out


def _show_file_any(repo_dir: str, tag: str, path: str) -> Tuple[str, str]:
    for candidate in _path_show_candidates(path):
        content = _show_file(repo_dir, tag, candidate)
        if content:
            return candidate, content
    return _normalize_kernel_path(path) or path, ""


def _function_grep_paths(function: str) -> List[str]:
    name = (function or "").lower()
    if name.startswith("fuse_"):
        return ["fs/fuse", "fs"]
    if name.startswith(("shmem_", "vmscan", "kmem_", "slab_")):
        return ["mm"]
    if name.startswith(("binder_", "ext4_", "f2fs_", "overlay_")):
        return ["fs", "drivers"]
    return ["fs", "mm", "kernel", "drivers", "net", "arch", "include"]


def _parse_git_grep_line(raw: str, tag: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    rest = text
    if tag and rest.startswith(tag + ":"):
        rest = rest[len(tag) + 1:]
    path, sep, tail = rest.partition(":")
    if not sep:
        return {}
    line_s, sep2, code = tail.partition(":")
    if not sep2 or not line_s.isdigit():
        return {}
    path = _normalize_kernel_path(path)
    if not path.endswith((".c", ".h", ".S")):
        return {}
    return {"path": path, "line": int(line_s), "code": code}


def _looks_like_function_hit(function: str, code: str) -> bool:
    stripped = (code or "").lstrip()
    if stripped.startswith(("*", "//", "#", "/*")):
        return False
    return bool(re.search(rf"\b{re.escape(function)}\b", code or ""))


def _function_hit_score(function: str, path: str, code: str) -> int:
    """Prefer C definitions over call sites / header declarations."""
    text = code or ""
    stripped = text.lstrip()
    score = 0
    if path.endswith(".c"):
        score += 5
    elif path.endswith(".h"):
        score -= 3
    # Call / assign mid-statement: inode = fuse_iget_backing(
    if re.search(rf"[=,]\s*{re.escape(function)}\s*\(", text):
        score -= 20
    if stripped.startswith(("if ", "while ", "for ", "return ", "else ", "switch ")):
        score -= 15
    # Definition / prototype typically starts at column 0
    if text and text[:1] not in " \t":
        score += 12
    if re.match(
        rf"^(?:static\s+|inline\s+|extern\s+|__\w+\s+)*"
        rf"[\w\s\*]+\b{re.escape(function)}\s*\(",
        stripped,
    ):
        score += 25
    elif re.search(rf"\b{re.escape(function)}\s*\(", text):
        score += 2
    return score


def _grep_function_hits(repo_dir: str, tag: str, function: str) -> List[Dict[str, Any]]:
    if not re.fullmatch(r"[A-Za-z_][\w.]*", function or ""):
        return []
    attempts = [
        ["grep", "-n", "-I", "-F", function, tag, "--", *_function_grep_paths(function)],
        ["grep", "-n", "-I", "-F", function, tag],
    ]
    parsed: List[Dict[str, Any]] = []
    seen = set()
    for args in attempts:
        try:
            grep_out = _run_git(repo_dir, args, timeout=40)
        except Exception:
            grep_out = ""
        for raw in (grep_out or "").splitlines():
            hit = _parse_git_grep_line(raw, tag)
            path = str(hit.get("path") or "")
            if not path or not _looks_like_function_hit(function, str(hit.get("code") or "")):
                continue
            key = (path, int(hit.get("line") or 0))
            if key in seen:
                continue
            seen.add(key)
            parsed.append(hit)
        if parsed:
            break
    if not parsed:
        return []
    ranked = sorted(
        parsed,
        key=lambda item: _function_hit_score(
            function, str(item.get("path") or ""), str(item.get("code") or "")
        ),
        reverse=True,
    )
    return ranked[:3]


def collect_crash_source(
    repo_dir: str,
    tag: str,
    crash_log: str,
    extra_files: Optional[Sequence[str]] = None,
    function: str = "",
    source_line: int = 0,
) -> Dict[str, Any]:
    """Read crash-site files from local kernel at tag. Never raises."""
    tag = (tag or "").strip()
    parsed = parse_crash_sites(crash_log)
    function = (function or parsed.get("function") or "").strip()
    hits: List[Dict[str, Any]] = list(parsed.get("files") or [])
    default_line = int(source_line or 0)
    for raw in extra_files or []:
        hit = _parse_path_hit(raw, default_line)
        path = str(hit.get("path") or "")
        if not path:
            continue
        existing = next((item for item in hits if item.get("path") == path), None)
        if existing:
            if not existing.get("line") and hit.get("line"):
                existing["line"] = hit["line"]
            continue
        hits.append(hit)
    if default_line:
        for item in hits:
            if not item.get("line"):
                item["line"] = default_line
                break

    if not tag or not repo_dir:
        return {
            "tag": tag,
            "function": function,
            "snippets": [],
            "prompt_block": "",
            "missing_reason": "未配置仓库或 Tag",
        }

    snippets: List[Dict[str, Any]] = []
    seen_paths = set()
    tree: List[str] = _list_tree(repo_dir, tag) if hits else []
    for hit in hits:
        raw_path = str(hit.get("path") or "")
        resolved = resolve_source_path(tree, raw_path) if tree else ""
        if not resolved:
            resolved, content = _show_file_any(repo_dir, tag, raw_path)
        else:
            content = _show_file(repo_dir, tag, resolved)
            if not content:
                resolved, content = _show_file_any(repo_dir, tag, raw_path)
        if not resolved or resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        line = int(hit.get("line") or 0)
        formatted = format_snippet(content, highlight_line=line, function=function)
        snippets.append({
            "path": resolved,
            "requested_path": raw_path,
            "line": line,
            "function": function,
            "start_line": formatted["start_line"],
            "text": formatted["text"],
            "missing": not bool(content),
        })
        if len(snippets) >= _MAX_SNIPPETS:
            break

    if not snippets and function:
        for hit in _grep_function_hits(repo_dir, tag, function):
            raw_path = str(hit.get("path") or "")
            resolved, content = _show_file_any(repo_dir, tag, raw_path)
            if not resolved or resolved in seen_paths:
                continue
            line = int(hit.get("line") or 0)
            formatted = format_snippet(content, highlight_line=line, function=function)
            snippets.append({
                "path": resolved,
                "requested_path": raw_path,
                "line": line,
                "function": function,
                "start_line": formatted["start_line"],
                "text": formatted["text"],
                "missing": not bool(content),
            })
            seen_paths.add(resolved)
            if len(snippets) >= _MAX_SNIPPETS:
                break

    hint = function or ", ".join(str(item.get("path") or "") for item in hits[:3] if item.get("path"))
    if snippets:
        missing_reason = ""
    elif hits and not tree and not function:
        missing_reason = f"无法列出 {tag} 的文件树，请确认本地仓库已 fetch 该 Tag"
    elif hint:
        missing_reason = f"仓库中未找到崩溃点源码（{hint}）"
    else:
        missing_reason = "分析结果未给出可打开的崩溃文件或函数"
    return {
        "tag": tag,
        "function": function,
        "snippets": snippets,
        "prompt_block": build_source_prompt_block(tag, snippets, function),
        "missing_reason": missing_reason,
    }


def build_source_prompt_block(
    tag: str,
    snippets: Sequence[Dict[str, Any]],
    function: str = "",
) -> str:
    if not snippets:
        return ""
    parts = [f"以下源码取自本地仓库 Tag `{tag}`" + (f"，崩溃函数候选 `{function}`" if function else "") + "。"]
    for item in snippets:
        loc = item.get("path") or ""
        line = item.get("line") or 0
        header = f"### {loc}" + (f":{line}" if line else "")
        if item.get("missing"):
            parts.append(f"{header}\n（仓库中未能取出该文件）")
            continue
        parts.append(f"{header}\n```c\n{item.get('text') or ''}\n```")
    return "\n\n".join(parts)


def pick_latest_compare_tip(resolved: Optional[Dict[str, Any]], tag: str = "") -> Dict[str, Any]:
    """Prefer same GKI series HEAD; otherwise the newest fetched community tip."""
    data = resolved or {}
    tips = list(data.get("tips") or [])
    series = str(data.get("series") or "")
    same = next((item for item in tips if str(item.get("branch") or "") == series), None)
    if same:
        return same
    return dict(tips[0]) if tips else {}


def collect_source_at_rev(
    repo_dir: str,
    rev: str,
    crash_snippets: Sequence[Dict[str, Any]],
    function: str = "",
) -> Dict[str, Any]:
    """Read the same crash-site files at a later community revision."""
    rev = (rev or "").strip()
    snippets: List[Dict[str, Any]] = []
    if not repo_dir or not rev:
        return {"rev": rev, "snippets": [], "prompt_block": "", "missing_reason": "无社区最新 revision"}

    tree: List[str] = []
    for item in crash_snippets or []:
        raw_path = str(item.get("path") or item.get("requested_path") or "")
        if not raw_path:
            continue
        content = _show_file(repo_dir, rev, raw_path)
        resolved = raw_path
        if not content:
            if not tree:
                tree = _list_tree(repo_dir, rev)
            resolved = resolve_source_path(tree, raw_path)
            if resolved:
                content = _show_file(repo_dir, rev, resolved)
        formatted = format_snippet(
            content,
            highlight_line=0,
            function=function or str(item.get("function") or ""),
            prefer_function=True,
        )
        snippets.append({
            "path": resolved or raw_path,
            "requested_path": raw_path,
            "line": 0,
            "function": function or str(item.get("function") or ""),
            "start_line": formatted["start_line"],
            "text": formatted["text"],
            "missing": not bool(content),
        })
        if len(snippets) >= _MAX_SNIPPETS:
            break

    missing = "" if snippets else "社区最新 revision 上未能取出崩溃文件"
    if snippets and all(item.get("missing") for item in snippets):
        missing = "社区最新 revision 上这些文件不存在或无法读取"
    return {
        "rev": rev,
        "function": function,
        "snippets": snippets,
        "prompt_block": build_source_prompt_block(rev, snippets, function),
        "missing_reason": missing,
    }


def file_diff_between(repo_dir: str, start: str, end: str, path: str, limit: int = 8000) -> str:
    start = (start or "").strip()
    end = (end or "").strip()
    path = (path or "").strip()
    if not start or not end or not path:
        return ""
    try:
        out = _run_git(repo_dir, ["diff", "-U12", f"{start}..{end}", "--", path], timeout=40)
    except Exception:
        return ""
    text = (out or "").strip()
    if len(text) > limit:
        return text[:limit] + f"\n... [truncated, {len(text)} chars]"
    return text


def list_path_commits(
    repo_dir: str,
    start: str,
    end: str,
    paths: Sequence[str],
    function: str = "",
    limit: int = 16,
) -> List[Dict[str, Any]]:
    """Commits that touched the crash file/function between start and end, with file diffs."""
    start = (start or "").strip()
    end = (end or "").strip()
    ordered: List[Dict[str, Any]] = []
    seen = set()

    def add_from_log(output: str, path: str, via: str) -> None:
        for line in (output or "").splitlines():
            line = line.strip()
            if not line or "\x01" not in line:
                continue
            sha, _, title = line.partition("\x01")
            sha = sha.strip()
            if not sha or sha in seen:
                continue
            seen.add(sha)
            ordered.append({"sha": sha, "title": title.strip(), "path": path, "via": via})

    for path in paths:
        path = str(path or "").strip()
        if not path:
            continue
        if function:
            try:
                out = _run_git(
                    repo_dir,
                    [
                        "log",
                        f"{start}..{end}",
                        f"-L:{function}:{path}",
                        "--format=%H%x01%s",
                        "--no-patch",
                        "--no-merges",
                    ],
                    timeout=60,
                )
                add_from_log(out, path, "function")
            except Exception:
                pass
        if not any(row.get("path") == path for row in ordered):
            try:
                out = _run_git(
                    repo_dir,
                    [
                        "log",
                        "--format=%H%x01%s",
                        "--no-merges",
                        "-n",
                        str(max(limit, 8)),
                        f"{start}..{end}",
                        "--",
                        path,
                    ],
                    timeout=60,
                )
                add_from_log(out, path, "file")
            except Exception:
                pass

    result: List[Dict[str, Any]] = []
    for row in ordered[:limit]:
        try:
            diff = _run_git(
                repo_dir,
                ["show", "--format=", "--no-color", "-U8", row["sha"], "--", row["path"]],
                timeout=30,
            )
        except Exception:
            diff = ""
        text = (diff or "").strip()
        if len(text) > 5000:
            text = text[:5000] + f"\n... [truncated, {len(diff)} chars]"
        result.append({**row, "diff": text, "files": [row["path"]]})
    return result
