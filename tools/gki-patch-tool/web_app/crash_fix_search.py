"""Find Google/community fix commits after a GKI tag.

Fetches kernel/common (same series, newer lines such as 6.18, and mainline)
and walks crash-related files / symbols only.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

_GIT_TIMEOUT = 180
_FETCH_TIMEOUT = 120
_LS_REMOTE_TIMEOUT = 60
_LLM_CANDIDATE_LIMIT = 80
_GOOGLE_COMMON = "https://android.googlesource.com/kernel/common"
_SERIES_RE = re.compile(r"^(android\d+-\d+\.\d+)")
_BRANCH_RE = re.compile(r"^(android\d+-\d+\.\d+|android-mainline)$")
_REMOTE_HEAD_RE = re.compile(r"(?:refs/heads/)?(android\d+-\d+\.\d+|android-mainline)\s*$")
_MAX_NEWER_SERIES = 2
_AOSP_TRACKING = "aosp"
_FIX_TITLE_RE = re.compile(
    r"(revert|fix(es|ed)?|panic|oops|watchdog|deadlock|"
    r"use-after-free|\buaf\b|null pointer|null-ptr|lockdep|"
    r"kasan|oob|overflow|race|spinlock|rcu\s+stall)",
    re.IGNORECASE,
)
_STACK_FILE_RE = re.compile(
    r"(?<![A-Za-z0-9_])((?:[A-Za-z0-9_.-]+/){1,8}[A-Za-z0-9_.-]+\.(?:c|h|S))(?::\d+)?"
)


def _run_git(repo_dir: str, args: Sequence[str], timeout: int = _GIT_TIMEOUT) -> str:
    from tools.patch_analyzer import run_git

    return run_git(Path(repo_dir), list(args), timeout=timeout) or ""


def gki_series_from_tag(tag: str) -> str:
    m = _SERIES_RE.match((tag or "").strip())
    return m.group(1) if m else ""


def parse_kernel_tuple(name: str) -> Optional[Tuple[int, int, int]]:
    raw = (name or "").strip()
    if raw == "android-mainline":
        return (999, 999, 999)
    m = re.match(r"^android(\d+)-(\d+)\.(\d+)$", raw)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def select_community_branches(available: Sequence[str], current_series: str) -> List[str]:
    """Same GKI line + newer kernel lines (e.g. 6.12 plus 6.18) + mainline."""
    names: List[str] = []
    for raw in available:
        item = str(raw or "").strip()
        item = item.replace("refs/heads/", "").split("/")[-1] if item.startswith("refs/heads/") else item
        if item == "android-mainline" or parse_kernel_tuple(item):
            if item not in names:
                names.append(item)
    current = parse_kernel_tuple(current_series)
    newer = sorted(
        [
            name for name in names
            if name != "android-mainline"
            and parse_kernel_tuple(name)
            and current is not None
            and parse_kernel_tuple(name) > current
        ],
        key=lambda name: parse_kernel_tuple(name) or (0, 0, 0),
        reverse=True,
    )
    picked: List[str] = []
    for name in newer[:_MAX_NEWER_SERIES]:
        picked.append(name)
    if current_series:
        picked.append(current_series)
    if "android-mainline" in names:
        picked.append("android-mainline")
    unique: List[str] = []
    for name in picked:
        if name and name not in unique:
            unique.append(name)
    return unique


def _note(on_progress: Optional[Callable[[str], None]], message: str) -> None:
    if on_progress:
        on_progress(message)
    print(f"[CRASH FIX] {message}", flush=True)


def _rev_parse(repo_dir: str, ref: str) -> str:
    ref = (ref or "").strip()
    if not ref:
        return ""
    try:
        return _run_git(repo_dir, ["rev-parse", "--verify", ref], timeout=20).strip()
    except Exception:
        return ""


def rev_parse_head(repo_dir: str) -> str:
    return _rev_parse(repo_dir, "HEAD")


def _count_range(repo_dir: str, start: str, end: str) -> int:
    start = (start or "").strip()
    end = (end or "").strip()
    if not start or not end:
        return 0
    try:
        out = _run_git(repo_dir, ["rev-list", "--count", f"{start}..{end}"], timeout=60)
        return int((out or "0").strip() or 0)
    except Exception:
        return 0


def count_commits_after_tag(repo_dir: str, tag: str, end_rev: str = "HEAD") -> int:
    return _count_range(repo_dir, tag, end_rev)


def _list_remotes(repo_dir: str) -> List[str]:
    try:
        out = _run_git(repo_dir, ["remote"], timeout=15)
    except Exception:
        return []
    return [line.strip() for line in (out or "").splitlines() if line.strip()]


def _google_fetch_url(repo_dir: str) -> str:
    """Prefer a googlesource kernel/common remote; otherwise fetch Google by URL."""
    try:
        out = _run_git(repo_dir, ["remote", "-v"], timeout=15)
    except Exception:
        out = ""
    for line in (out or "").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        name, url = parts[0], parts[1]
        normalized = url.replace("\\", "/").lower()
        if "googlesource.com/kernel/common" in normalized:
            return name
    return _GOOGLE_COMMON


def _parse_ls_remote_heads(output: str) -> List[str]:
    names: List[str] = []
    for line in (output or "").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        ref = parts[-1]
        match = _REMOTE_HEAD_RE.search(ref)
        if match:
            name = match.group(1)
            if name not in names:
                names.append(name)
    return names


def list_community_heads(repo_dir: str, fetch_url: str) -> List[str]:
    try:
        out = _run_git(
            repo_dir,
            ["ls-remote", "--heads", fetch_url],
            timeout=_LS_REMOTE_TIMEOUT,
        )
        return _parse_ls_remote_heads(out)
    except Exception:
        return []


def _tracking_ref(branch: str) -> str:
    return f"{_AOSP_TRACKING}/{branch}"


def fetch_community_branches(
    repo_dir: str,
    branches: Sequence[str],
    fetch_url: str,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Tuple[List[str], List[str]]:
    fetched: List[str] = []
    failed: List[str] = []
    for branch in branches:
        spec = f"refs/heads/{branch}:refs/remotes/{_AOSP_TRACKING}/{branch}"
        _note(on_progress, f"正在从社区拉取 {branch} ...")
        try:
            _run_git(repo_dir, ["fetch", "--no-tags", fetch_url, spec], timeout=_FETCH_TIMEOUT)
            if _rev_parse(repo_dir, _tracking_ref(branch)):
                fetched.append(branch)
                _note(on_progress, f"已拉取 {branch}")
            else:
                failed.append(branch)
        except Exception as exc:
            failed.append(branch)
            _note(on_progress, f"拉取 {branch} 失败: {exc}")
    return fetched, failed


def _merge_base(repo_dir: str, a: str, b: str) -> str:
    try:
        return _run_git(repo_dir, ["merge-base", a, b], timeout=30).strip()
    except Exception:
        return ""


def resolve_community_search_tips(
    repo_dir: str,
    tag: str,
    on_progress: Optional[Callable[[str], None]] = None,
    do_fetch: bool = True,
) -> Dict[str, Any]:
    """Fetch Google kernel/common and pick same series + newer lines (6.18) + mainline."""
    tag = (tag or "").strip()
    series = gki_series_from_tag(tag)
    fetch_url = _google_fetch_url(repo_dir)
    _note(on_progress, f"社区源: {fetch_url}")
    remote_heads = list_community_heads(repo_dir, fetch_url) if do_fetch else []
    if not remote_heads:
        _note(on_progress, "ls-remote 未拿到分支列表，改用 6.18 / 当前系列 / mainline")
        remote_heads = [series, "android16-6.18", "android-mainline"] if series else [
            "android16-6.18", "android-mainline",
        ]
    branches = select_community_branches(remote_heads, series)
    fetched_branches: List[str] = []
    fetch_failed: List[str] = []
    if do_fetch and branches:
        fetched_branches, fetch_failed = fetch_community_branches(
            repo_dir, branches, fetch_url, on_progress,
        )
    tips: List[Dict[str, str]] = []
    for branch in branches:
        ref = _tracking_ref(branch)
        sha = _rev_parse(repo_dir, ref)
        if not sha:
            sha = _rev_parse(repo_dir, branch)
            ref = branch if sha else ref
        if not sha:
            for remote in _list_remotes(repo_dir):
                alt = f"{remote}/{branch}"
                sha = _rev_parse(repo_dir, alt)
                if sha:
                    ref = alt
                    break
        if not sha:
            continue
        start = _merge_base(repo_dir, tag, sha) or tag
        tips.append({"ref": ref, "sha": sha, "branch": branch, "start": start})
    if not tips:
        head = _rev_parse(repo_dir, "HEAD")
        if head:
            tips.append({
                "ref": "HEAD",
                "sha": head,
                "branch": series or "HEAD",
                "start": tag,
            })
    primary = tips[0] if tips else {"ref": "HEAD", "sha": "", "branch": series, "start": tag}
    newest_count = _count_range(repo_dir, tag, primary.get("sha") or "") if primary.get("sha") else 0
    empty_reason = ""
    if not tips:
        empty_reason = (
            f"未能从社区解析可检索分支（已尝试 {', '.join(branches) or '无'}）。"
            f"请确认能访问 {fetch_url}"
        )
    return {
        "tips": tips,
        "end_ref": ",".join(t["ref"] for t in tips),
        "end_sha": primary.get("sha") or "",
        "count": newest_count,
        "series": series,
        "fetched": bool(fetched_branches),
        "fetched_branches": fetched_branches,
        "fetch_failed": fetch_failed,
        "fetch_source": fetch_url,
        "empty_reason": empty_reason,
        "branches": branches,
    }


def resolve_fix_search_tip(
    repo_dir: str,
    tag: str,
    fetch_if_empty: bool = True,
) -> Dict[str, Any]:
    """Back-compat wrapper: primary community tip."""
    data = resolve_community_search_tips(repo_dir, tag, do_fetch=fetch_if_empty)
    primary = (data.get("tips") or [{}])[0]
    return {
        "end_ref": primary.get("ref") or data.get("end_ref") or "HEAD",
        "end_sha": primary.get("sha") or "",
        "count": data.get("count") or 0,
        "series": data.get("series") or "",
        "fetched": data.get("fetched") or False,
        "empty_reason": data.get("empty_reason") or "",
        "tips": data.get("tips") or [],
        "fetch_source": data.get("fetch_source") or "",
        "fetched_branches": data.get("fetched_branches") or [],
        "branches": data.get("branches") or [],
    }


def list_commits_after_tag(repo_dir: str, tag: str) -> List[Dict[str, str]]:
    """Deprecated full walk. Kept for tests; production uses file-scoped search."""
    tag = (tag or "").strip()
    if not tag:
        return []
    out = _run_git(repo_dir, ["log", "--format=%H%x01%s", "--no-merges", f"{tag}..HEAD"])
    return _parse_sha_title(out)


def _parse_sha_title(out: str) -> List[Dict[str, str]]:
    commits: List[Dict[str, str]] = []
    for line in (out or "").splitlines():
        line = line.strip()
        if not line or "\x01" not in line:
            continue
        sha, _, title = line.partition("\x01")
        if sha.strip():
            commits.append({"sha": sha.strip(), "title": title.strip()})
    return commits


def _parse_sha_title_nameonly(out: str) -> List[Dict[str, Any]]:
    commits: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for raw in (out or "").splitlines():
        line = raw.strip()
        if "\x01" in line:
            if current:
                commits.append(current)
            sha, _, title = line.partition("\x01")
            current = {"sha": sha.strip(), "title": title.strip(), "files": []}
            continue
        if not line or current is None:
            continue
        files = current.setdefault("files", [])
        if line not in files:
            files.append(line)
    if current:
        commits.append(current)
    return commits


def _crash_file_paths(
    crash_analysis: Optional[Dict[str, Any]],
    crash_log: str = "",
) -> List[str]:
    files: List[str] = []
    seen = set()

    def add(raw: Any) -> None:
        path = str(raw or "").strip().replace("\\", "/")
        if not path or path in seen:
            return
        if path.startswith("/") or " " in path or "/" not in path:
            return
        if not re.search(r"\.(c|h|S)$", path):
            return
        seen.add(path)
        files.append(path)

    info = crash_analysis or {}
    for raw in info.get("crash_files") or []:
        add(raw)
        if len(files) >= 24:
            return files
    for raw in _STACK_FILE_RE.findall(str(info.get("call_stack_summary") or "")):
        add(raw)
        if len(files) >= 24:
            return files
    for raw in _STACK_FILE_RE.findall(crash_log or ""):
        add(raw)
        if len(files) >= 24:
            return files
    return files


def _grep_terms(
    crash_analysis: Optional[Dict[str, Any]],
    suspected: Sequence[Dict[str, Any]],
) -> List[str]:
    terms: List[str] = []
    seen = set()

    def add(raw: Any, min_len: int = 4) -> None:
        tok = str(raw or "").strip()
        if len(tok) < min_len or tok.lower() in seen:
            return
        if re.search(r"[\s/\\]", tok):
            return
        seen.add(tok.lower())
        terms.append(tok)

    info = crash_analysis or {}
    add(info.get("crash_function"))
    for sym in (info.get("crash_symbols") or [])[:8]:
        add(sym)
    for sp in suspected or []:
        sha = str(sp.get("sha") or "").strip()
        if len(sha) >= 8:
            add(sha[:12], min_len=8)
            add(f"Revert {sha[:12]}", min_len=8)
    return terms[:12]


def _log_nameonly(
    repo_dir: str,
    start_rev: str,
    end_rev: str,
    extra_before: Sequence[str] = (),
    extra_after: Sequence[str] = (),
) -> List[Dict[str, Any]]:
    start_rev = (start_rev or "").strip()
    end_rev = (end_rev or "").strip()
    if not start_rev or not end_rev:
        return []
    try:
        out = _run_git(
            repo_dir,
            [
                "log",
                "--format=%H%x01%s",
                "--name-only",
                "--no-merges",
                *extra_before,
                f"{start_rev}..{end_rev}",
                *extra_after,
            ],
        )
    except Exception:
        return []
    return _parse_sha_title_nameonly(out)


def _list_commits_touching_files(
    repo_dir: str,
    start_rev: str,
    end_rev: str,
    files: Sequence[str],
) -> List[Dict[str, Any]]:
    if not files:
        return []
    return _log_nameonly(
        repo_dir, start_rev, end_rev, extra_after=["--", *files],
    )


def _list_commits_by_grep(
    repo_dir: str,
    start_rev: str,
    end_rev: str,
    terms: Sequence[str],
) -> List[Dict[str, Any]]:
    if not terms:
        return []
    grep_args: List[str] = ["-i", "-F"]
    for term in terms:
        grep_args.extend(["--grep", term])
    return _log_nameonly(repo_dir, start_rev, end_rev, extra_before=grep_args)


def _title_rank(
    title: str,
    crash_analysis: Optional[Dict[str, Any]],
    suspected: Sequence[Dict[str, Any]],
) -> int:
    t = (title or "").lower()
    score = 0
    if _FIX_TITLE_RE.search(t):
        score += 20
    info = crash_analysis or {}
    func = str(info.get("crash_function") or "").strip().lower()
    if len(func) >= 4 and func in t:
        score += 50
    for token in (info.get("crash_symbols") or [])[:8]:
        tok = str(token or "").strip().lower()
        if len(tok) >= 4 and tok in t:
            score += 30
            break
    for sp in suspected or []:
        sha = str(sp.get("sha") or "").strip().lower()
        if len(sha) >= 8 and sha[:8] in t:
            score += 80
            break
    return score


def collect_fix_candidates(
    repo_dir: str,
    tag: str,
    crash_analysis: Optional[Dict[str, Any]] = None,
    suspected: Optional[Sequence[Dict[str, Any]]] = None,
    crash_log: str = "",
    on_progress: Optional[Callable[[str], None]] = None,
    resolved: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Collect crash-file commits on Google/community tips, including newer GKI lines."""
    tag = (tag or "").strip()
    suspected = list(suspected or [])
    files = _crash_file_paths(crash_analysis, crash_log)
    terms = _grep_terms(crash_analysis, suspected)
    if resolved is None:
        resolved = (
            resolve_community_search_tips(repo_dir, tag, on_progress=on_progress)
            if tag else {
                "tips": [],
                "end_ref": "HEAD",
                "end_sha": "",
                "count": 0,
                "series": "",
                "fetched": False,
                "empty_reason": "",
                "fetched_branches": [],
                "fetch_source": "",
                "branches": [],
            }
        )
    tips = list(resolved.get("tips") or [])
    series = str(resolved.get("series") or gki_series_from_tag(tag))
    current_tuple = parse_kernel_tuple(series)

    touching: List[Dict[str, Any]] = []
    grepped: List[Dict[str, Any]] = []
    for tip in tips:
        start = str(tip.get("start") or tag)
        end = str(tip.get("sha") or "")
        ref = str(tip.get("ref") or "")
        if not end:
            continue
        _note(on_progress, f"按崩溃文件检索 {ref}")
        for row in _list_commits_touching_files(repo_dir, start, end, files):
            touching.append({**row, "branch": tip.get("branch") or ref})
        for row in _list_commits_by_grep(repo_dir, start, end, terms):
            grepped.append({**row, "branch": tip.get("branch") or ref})

    ordered: List[Dict[str, Any]] = []
    seen = set()

    def add(commit: Dict[str, Any], via: str) -> None:
        sha = commit.get("sha") or ""
        if not sha or sha in seen:
            return
        seen.add(sha)
        title = commit.get("title") or ""
        branch = str(commit.get("branch") or "")
        extra = 0
        b_tuple = parse_kernel_tuple(branch)
        if current_tuple and b_tuple and b_tuple > current_tuple:
            extra += 15
        if branch == "android-mainline":
            extra += 10
        ranked = {
            "sha": sha,
            "title": title,
            "files": list(commit.get("files") or [])[:8],
            "via": via,
            "branch": branch,
            "_rank": _title_rank(title, crash_analysis, suspected) + extra + (40 if via == "file" else 10),
        }
        ordered.append(ranked)

    for commit in touching:
        add(commit, "file")
    for commit in grepped:
        add(commit, "grep")

    ordered.sort(key=lambda row: (-int(row.get("_rank") or 0),))
    for row in ordered:
        row.pop("_rank", None)
    candidates = ordered[:_LLM_CANDIDATE_LIMIT]
    end_ref = str(resolved.get("end_ref") or ",".join(t.get("ref") or "" for t in tips) or "HEAD")
    primary_sha = str((tips[0].get("sha") if tips else "") or resolved.get("end_sha") or "")

    meta = {
        "search_from_tag": tag,
        "search_to_ref": end_ref,
        "search_to_rev": primary_sha,
        "commits_after_tag": int(resolved.get("count") or 0),
        "file_touching": len(touching),
        "grep_hits": len(grepped),
        "candidates": len(candidates),
        "crash_files": files,
        "grep_terms": terms,
        "series": series,
        "fetched": bool(resolved.get("fetched")),
        "fetched_branches": list(resolved.get("fetched_branches") or []),
        "fetch_source": str(resolved.get("fetch_source") or ""),
        "empty_reason": str(resolved.get("empty_reason") or ""),
        "strategy": "community_files_and_symbols",
    }
    return candidates, meta


def attach_commit_files(
    repo_dir: str,
    commits: Iterable[Dict[str, str]],
    limit: int = 8,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for commit in commits:
        sha = commit.get("sha") or ""
        files = list(commit.get("files") or [])[:limit]
        if sha and not files:
            try:
                raw = _run_git(
                    repo_dir,
                    ["diff-tree", "--no-commit-id", "--name-only", "-r", sha],
                    timeout=30,
                )
                files = [f.strip() for f in (raw or "").splitlines() if f.strip()][:limit]
            except Exception:
                files = []
        out.append({**commit, "files": files})
    return out
