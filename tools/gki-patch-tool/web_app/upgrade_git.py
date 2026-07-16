"""Git operations for GKI upgrade workflow (apply / conflict / commit)."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class GitResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_git(
    repo_dir: Path,
    args: List[str],
    *,
    timeout: Optional[int] = None,
    check: bool = True,
    capture_output: bool = True,
) -> GitResult:
    from web_app.upgrade_remote_git import is_remote_active, remote_run_git

    if is_remote_active():
        return remote_run_git(
            repo_dir, args, timeout=timeout, check=check, capture_output=capture_output,
        )
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"git {' '.join(args)} timed out after {timeout}s") from exc
    result = GitResult(proc.returncode, proc.stdout, proc.stderr)
    if check and not result.ok:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result


def repo_is_git(repo_dir: Path) -> bool:
    from web_app.upgrade_remote_git import is_remote_active, remote_repo_is_git

    if is_remote_active():
        return remote_repo_is_git(repo_dir)
    return (repo_dir / ".git").exists()


def current_branch(repo_dir: Path) -> str:
    r = run_git(repo_dir, ["rev-parse", "--abbrev-ref", "HEAD"])
    return r.stdout.strip()


def working_tree_status(repo_dir: Path) -> str:
    from web_app.upgrade_remote_git import is_remote_active, remote_working_tree_status

    if is_remote_active():
        return remote_working_tree_status(repo_dir)
    r = run_git(repo_dir, ["status", "--porcelain"])
    return r.stdout.strip()


def is_clean_worktree(repo_dir: Path) -> bool:
    return not working_tree_status(repo_dir)


_UNMERGED_XY = frozenset({"UU", "AA", "DD", "AU", "UA", "DU", "UD"})


_APPLY_CONFLICT_RE = re.compile(r"Applied patch to '([^']+)' with conflicts\.")

# squash 合入：--reject 保留能合入的 hunk，失败的生成 .rej（vendor 合入比 --3way 更稳）
# 不用 --quiet：158 等旧版 git 不支持；远程 apply 通过 stdout 重定向到 /dev/null 抑制输出
SQUASH_APPLY_GIT_ARGS = ["apply", "--reject", "--whitespace=nowarn"]


def parse_apply_conflict_files(apply_output: str) -> List[str]:
    return sorted(set(_APPLY_CONFLICT_RE.findall(apply_output or "")))


def parse_reject_files_from_porcelain(status_text: str) -> List[str]:
    """Extract ``.rej`` paths from ``git status --porcelain`` (untracked ``??`` lines)."""
    found: List[str] = []
    for line in (status_text or "").splitlines():
        if len(line) < 4 or line[0:2] != "??":
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path.endswith(".rej"):
            found.append(path)
    return sorted(found)


def _tracked_changed_vs_head(repo_dir: Path) -> set[str]:
    files: set[str] = set()
    head = run_git(repo_dir, ["diff", "--name-only", "HEAD"], check=False)
    for line in head.stdout.splitlines():
        s = line.strip()
        if s:
            files.add(s)
    return files


def changed_files_from_status(
    repo_dir: Path,
    *,
    squash_apply: bool = False,
    rej_files: Optional[List[str]] = None,
) -> List[str]:
    """Paths with any worktree change (staged, unstaged, or untracked).

    When *squash_apply* is True (squash + --reject after apply), only collect
    tracked diffs vs HEAD and ``.rej`` files — avoids a full-tree
    ``git ls-files --others`` / ``find`` scan on large remote kernel trees.
    Pass *rej_files* when already known to skip another remote scan.
    """
    files = _tracked_changed_vs_head(repo_dir)
    if squash_apply:
        if rej_files is None:
            rej_files = list_reject_files(repo_dir)
        files.update(rej_files)
        return sorted(files)
    for args in (
        ["ls-files", "--others", "--exclude-standard"],
    ):
        r = run_git(repo_dir, args, check=False)
        for line in r.stdout.splitlines():
            s = line.strip()
            if s:
                files.add(s)
    if files:
        return sorted(files)
    status = working_tree_status(repo_dir)
    for line in status.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path:
            files.add(path)
    return sorted(files)


def list_reject_files(repo_dir: Path) -> List[str]:
    """Return paths of .rej files left by git apply --reject."""
    from web_app.upgrade_remote_git import is_remote_active, remote_list_reject_files

    if is_remote_active():
        return remote_list_reject_files(repo_dir)
    found = parse_reject_files_from_porcelain(working_tree_status(repo_dir))
    if found:
        return found
    paths: List[str] = []
    for p in repo_dir.rglob("*.rej"):
        if p.is_file():
            paths.append(p.relative_to(repo_dir).as_posix())
    return sorted(paths)


def list_unmerged_files(repo_dir: Path) -> List[str]:
    r = run_git(repo_dir, ["diff", "--name-only", "--diff-filter=U"])
    files = [line.strip() for line in r.stdout.splitlines() if line.strip()]
    if files:
        return files
    status = working_tree_status(repo_dir)
    unmerged: List[str] = []
    for line in status.splitlines():
        if len(line) >= 3 and line[0:2] in _UNMERGED_XY:
            path = line[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            if path:
                unmerged.append(path)
    return sorted(set(unmerged))


def has_conflict_markers(repo_dir: Path, files: Optional[List[str]] = None) -> List[str]:
    """Return files that still contain conflict markers (only in changed files when given)."""
    from web_app.upgrade_remote_git import is_remote_active, remote_has_conflict_markers

    if is_remote_active():
        return remote_has_conflict_markers(repo_dir, files)
    targets = files or []
    if not targets:
        return []
    if len(targets) > 32:
        try:
            proc = subprocess.run(
                ["grep", "-l", "-r", "^<<<<<<< ", "--include=*", *targets],
                cwd=str(repo_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            return sorted(
                line.strip().lstrip("./")
                for line in proc.stdout.splitlines()
                if line.strip()
            )
        except OSError:
            pass
    conflicted: List[str] = []
    for rel in targets:
        path = repo_dir / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if re.search(r"^<<<<<<< ", text, re.MULTILINE):
            conflicted.append(rel)
    return conflicted


def prepare_patch_for_apply(patch_file: Path, job_id: str = "") -> Tuple[Path, Optional[Path]]:
    """Return (path_to_apply, temp_path_to_delete). Converts CRLF patch to LF for Linux git apply."""
    data = patch_file.read_bytes()
    if b"\r" not in data:
        return patch_file, None
    tag = job_id or patch_file.stem
    tmp = patch_file.parent / f".apply_lf_{tag}.patch"
    text = data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    return tmp, tmp


def git_am_in_progress(repo_dir: Path) -> bool:
    from web_app.upgrade_remote_git import is_remote_active, remote_git_am_in_progress

    if is_remote_active():
        return remote_git_am_in_progress(repo_dir)
    return (repo_dir / ".git" / "rebase-apply").exists()


def create_backup_branch(repo_dir: Path, suffix: str) -> str:
    branch = f"gki-upgrade-backup-{suffix}"
    run_git(repo_dir, ["branch", "-f", branch, "HEAD"])
    return branch


def git_head_info(repo_dir: Path) -> Tuple[str, str]:
    """Return (branch_or_HEAD, short_sha)."""
    branch = current_branch(repo_dir)
    sha = run_git(repo_dir, ["rev-parse", "--short", "HEAD"]).stdout.strip()
    return branch, sha


def branch_exists(repo_dir: Path, branch: str) -> bool:
    r = run_git(repo_dir, ["rev-parse", "--verify", f"refs/heads/{branch}"], check=False)
    return r.ok


# 超过此数量时，远程分步 reset/clean（避免单次长命令无进度、且不做重复 checkout）
_FAST_RESET_THRESHOLD = 150


def count_dirty_entries(repo_dir: Path) -> int:
    status = working_tree_status(repo_dir).strip()
    if not status:
        return 0
    return len([ln for ln in status.splitlines() if ln.strip()])


def classify_dirty_entries(status: str) -> tuple[int, int, int]:
    """Return (total, tracked, untracked) from porcelain status."""
    tracked = untracked = 0
    for ln in status.splitlines():
        if not ln.strip():
            continue
        if ln.startswith("??"):
            untracked += 1
        else:
            tracked += 1
    return tracked + untracked, tracked, untracked


def reset_worktree(repo_dir: Path) -> None:
    from web_app.upgrade_remote_git import is_remote_active, remote_reset_worktree_fast

    status = working_tree_status(repo_dir).strip()
    n, tracked, untracked = classify_dirty_entries(status)
    if is_remote_active() and n >= _FAST_RESET_THRESHOLD:
        remote_reset_worktree_fast(
            repo_dir,
            dirty_count=n,
            tracked_count=tracked,
            untracked_count=untracked,
        )
        return
    reset_timeout = 7200 if n >= _FAST_RESET_THRESHOLD else None
    if tracked > 0:
        run_git(
            repo_dir,
            ["reset", "--hard", "HEAD"],
            check=False,
            timeout=reset_timeout,
            capture_output=False,
        )
    if untracked > 0 or tracked == 0:
        run_git(
            repo_dir,
            ["clean", "-fd"],
            check=False,
            capture_output=False,
        )


def ensure_clean_worktree(repo_dir: Path) -> Tuple[bool, str]:
    """Discard uncommitted changes so apply starts from a clean tree.

    Returns (was_dirty, log_message). Raises if still dirty after reset.
    """
    status = working_tree_status(repo_dir).strip()
    if not status:
        return False, ""
    lines = [ln for ln in status.splitlines() if ln.strip()]
    preview = "\n".join(lines[:20])
    if len(lines) > 20:
        preview += f"\n... 等 {len(lines)} 条"
    n = len(lines)
    from web_app.upgrade_remote_git import is_remote_active

    _, tracked, untracked = classify_dirty_entries(status)
    if n >= _FAST_RESET_THRESHOLD:
        if is_remote_active():
            parts = []
            if tracked:
                parts.append(f"reset --hard ({tracked} tracked)")
            if untracked:
                parts.append(f"clean -fd ({untracked} untracked)")
            mode = "远程分步清理: " + " + ".join(parts) if parts else "git reset --hard && git clean -fd"
        else:
            mode = "git reset --hard（文件较多，可能较慢）"
    else:
        mode = "git reset --hard HEAD && git clean -fd"
    reset_worktree(repo_dir)
    if not is_clean_worktree(repo_dir):
        remain = working_tree_status(repo_dir).strip()
        raise RuntimeError(
            "自动清理后工作区仍不干净，请手动处理后再试"
            + (f"\n{remain[:800]}" if remain else "")
        )
    return True, (
        f"工作区不干净（{n} 项），已自动清理：{mode}\n{preview}"
    )


def prepare_upgrade_branches(
    repo_dir: Path,
    suffix: str,
    *,
    upgrade_branch: str = "",
) -> Tuple[str, str]:
    """Create backup branch and checkout a named branch for applying the patch.

    Returns (backup_branch, work_branch).
    - backup_branch: rollback point (pre-apply commit)
    - work_branch: branch to apply patch on (never detached HEAD)

    If upgrade_branch is set, checkout that existing branch first and apply there.
    Otherwise always create/checkout gki-upgrade-work-{suffix} from current HEAD.
    """
    target = (upgrade_branch or "").strip()
    if target:
        if not branch_exists(repo_dir, target):
            raise RuntimeError(
                f"指定的合入分支不存在: {target}。"
                "请留空以自动创建工作分支，或先在仓库中创建该分支。"
            )
        run_git(repo_dir, ["checkout", target])

    backup = f"gki-upgrade-backup-{suffix}"
    run_git(repo_dir, ["branch", "-f", backup, "HEAD"])

    if target:
        return backup, target

    work = f"gki-upgrade-work-{suffix}"
    run_git(repo_dir, ["checkout", "-B", work, "HEAD"])
    return backup, work


def checkout_branch(repo_dir: Path, branch: str, *, create: bool = False) -> None:
    args = ["checkout"]
    if create:
        args.append("-b")
    args.append(branch)
    run_git(repo_dir, args)


def apply_format_patch(repo_dir: Path, patch_file: Path, job_id: str = "") -> GitResult:
    from web_app.upgrade_remote_git import is_remote_active, remote_apply_format_patch

    if is_remote_active():
        if not job_id:
            raise RuntimeError("远程合入需要 job_id")
        return remote_apply_format_patch(repo_dir, patch_file, job_id)
    with patch_file.open("r", encoding="utf-8", errors="replace") as f:
        proc = subprocess.run(
            ["git", "am", "--3way", "--keep-cr"],
            cwd=str(repo_dir),
            stdin=f,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    return GitResult(proc.returncode, proc.stdout, proc.stderr)


def apply_squash_patch(repo_dir: Path, patch_file: Path, job_id: str = "") -> GitResult:
    from web_app.upgrade_remote_git import is_remote_active, remote_apply_squash_patch

    apply_path, tmp = prepare_patch_for_apply(patch_file, job_id)
    try:
        if is_remote_active():
            if not job_id:
                raise RuntimeError("远程合入需要 job_id")
            return remote_apply_squash_patch(repo_dir, apply_path, job_id)
        return run_git(
            repo_dir,
            [*SQUASH_APPLY_GIT_ARGS, str(apply_path)],
            check=False,
        )
    finally:
        if tmp and tmp.is_file():
            tmp.unlink(missing_ok=True)


def stage_all(repo_dir: Path) -> None:
    run_git(repo_dir, ["add", "-A"])


def stage_paths(repo_dir: Path, paths: List[str]) -> None:
    """Stage only the given paths (repo-relative)."""
    cleaned = [(raw or "").strip() for raw in paths if (raw or "").strip()]
    if not cleaned:
        return
    chunk_size = 80
    for i in range(0, len(cleaned), chunk_size):
        run_git(repo_dir, ["add", "--", *cleaned[i : i + chunk_size]], check=False)


def has_staged_changes(repo_dir: Path) -> bool:
    """True if the index has staged changes."""
    r = run_git(repo_dir, ["diff", "--cached", "--quiet"], check=False)
    return r.returncode == 1


def am_continue(repo_dir: Path) -> GitResult:
    return run_git(repo_dir, ["am", "--continue", "--no-edit"], check=False)


def am_abort(repo_dir: Path) -> None:
    if git_am_in_progress(repo_dir):
        run_git(repo_dir, ["am", "--abort"], check=False)


def commit(repo_dir: Path, message: str = "", *, message_file: str = "") -> str:
    if message_file:
        run_git(repo_dir, ["commit", "-F", message_file])
    else:
        run_git(repo_dir, ["commit", "-m", message])
    r = run_git(repo_dir, ["rev-parse", "HEAD"])
    return r.stdout.strip()


def head_sha(repo_dir: Path) -> str:
    r = run_git(repo_dir, ["rev-parse", "HEAD"])
    return r.stdout.strip()


_STATUS_UPSTREAM_RE = re.compile(
    r"(?:up to date with|ahead of|behind)\s+'([^/'\s]+)/([^']+)'",
    re.IGNORECASE,
)


def parse_upstream_from_status_text(status_text: str) -> Tuple[str, str]:
    """Parse ``(remote, branch)`` from ``git status`` or ``git status -sb`` output."""
    text = status_text or ""
    for line in text.splitlines():
        m = _STATUS_UPSTREAM_RE.search(line)
        if m:
            return m.group(1), m.group(2)
    first = (text.splitlines() or [""])[0].strip()
    m = re.match(r"^## \S+\.\.\.([^/ \t]+)/(\S+)", first)
    if m:
        return m.group(1), m.group(2)
    return "", ""


def run_repo_start_local(repo_dir: Path) -> GitResult:
    """Run ``repo start local .`` in the target project directory."""
    from web_app.upgrade_remote_git import is_remote_active, remote_run_in_dir

    if is_remote_active():
        return remote_run_in_dir(
            str(repo_dir).replace("\\", "/"),
            "repo start local . 2>&1",
            timeout=120,
        )
    try:
        proc = subprocess.run(
            ["repo", "start", "local", "."],
            cwd=str(repo_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("repo start local . timed out after 120s") from exc
    return GitResult(proc.returncode, proc.stdout or "", "")


def capture_gerrit_review_branch(repo_dir: Path) -> Dict[str, str]:
    """Before modifying the tree: ``repo start local .`` then ``git status``, save push target."""
    repo_r = run_repo_start_local(repo_dir)
    repo_note = ((repo_r.stdout or "") + (repo_r.stderr or "")).strip()

    status_r = run_git(repo_dir, ["status"], check=False)
    status_text = (status_r.stdout or "").strip()

    rem, branch = parse_upstream_from_status_text(status_text)
    if not branch:
        rem, branch = resolve_gerrit_review_branch(repo_dir, check=False)

    return {
        "gerrit_remote": rem,
        "gerrit_review_branch": branch,
        "gerrit_capture_status": status_text[:800],
        "repo_start_ok": str(repo_r.ok).lower(),
        "repo_start_note": repo_note[:300],
    }


def resolve_gerrit_review_branch(
    repo_dir: Path,
    remote: str = "origin",
    *,
    saved_remote: str = "",
    saved_branch: str = "",
    check: bool = True,
) -> Tuple[str, str]:
    """Resolve Gerrit review branch from upstream tracking (same as ``git status`` shows).

    Typical vendor workflow::

        repo start local .
        git status  →  Your branch is up to date with 'origin/tOS15.1.2_mtk_A12_vnd_release'

    Programmatic equivalent::

        git rev-parse --abbrev-ref --symbolic-full-name @{u}
        → origin/tOS15.1.2_mtk_A12_vnd_release

    Returns ``(remote, review_branch)`` for ``git push REMOTE HEAD:refs/for/BRANCH``.
    """
    saved_rem = (saved_remote or "").strip()
    saved_br = (saved_branch or "").strip()
    if saved_br:
        return saved_rem or remote, saved_br

    # 1) Upstream of current branch (@{u}) — preferred, matches git status line
    r = run_git(
        repo_dir,
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        check=False,
    )
    upstream = (r.stdout or "").strip()
    if upstream and upstream != "@{u}" and "/" in upstream:
        rem, branch = upstream.split("/", 1)
        if branch:
            return rem or remote, branch

    # 2) ``git status -sb`` → ``## local...origin/tOS15.1.2_...``
    r = run_git(repo_dir, ["status", "-sb"], check=False)
    first = ((r.stdout or "").splitlines() or [""])[0].strip()
    m = re.match(r"^## \S+\.\.\.([^/ \t]+)/(\S+)", first)
    if m:
        return m.group(1) or remote, m.group(2)

    # 3) branch.<name>.merge → refs/heads/<review-branch>
    head = current_branch(repo_dir)
    r = run_git(repo_dir, ["config", "--get", f"branch.{head}.merge"], check=False)
    merge_ref = (r.stdout or "").strip()
    if merge_ref.startswith("refs/heads/"):
        branch = merge_ref[len("refs/heads/") :]
        r_remote = run_git(repo_dir, ["config", "--get", f"branch.{head}.remote"], check=False)
        rem = (r_remote.stdout or "").strip() or remote
        if branch:
            return rem, branch

    if check:
        raise RuntimeError(
            "无法解析 Gerrit 目标分支（当前分支未配置 upstream）。"
            f"请在仓库 {repo_dir} 执行类似 "
            f"「repo start local .」后再 push，"
            "或确认 git status 显示 "
            "「Your branch is up to date with 'origin/<release-branch>'」。"
            + (
                "（prepare 阶段应已保存 gerrit_review_branch，"
                "若仍出现本错误请检查 push 是否传入保存的分支）"
                if not saved_br
                else ""
            )
        )
    return "", ""


@dataclass
class PushResult:
    cmd: str
    remote: str
    review_branch: str
    stdout: str
    stderr: str
    gerrit_urls: List[str]
    ok: bool
    error: str = ""


_GERRIT_URL_RE = re.compile(
    r"https?://[^\s\]\)\"'<>]+(?:/\+/\d+|/c/[^/\s]+/\+/\d+)",
    re.I,
)


def parse_gerrit_urls_from_push_output(text: str) -> List[str]:
    """Extract Gerrit change URLs from ``git push`` hook output."""
    urls: List[str] = []
    for line in (text or "").splitlines():
        low = line.lower()
        if "remote:" not in low and "new change" not in low:
            continue
        for m in _GERRIT_URL_RE.finditer(line):
            u = m.group(0).rstrip(".,;)")
            if u not in urls:
                urls.append(u)
    return urls


def remote_get_url(repo_dir: Path, remote: str = "origin") -> str:
    r = run_git(repo_dir, ["remote", "get-url", remote], check=False)
    return (r.stdout or "").strip()


def gerrit_browse_url_for_sha(remote_url: str, sha: str) -> str:
    """Best-effort Gerrit/Googlesource browse URL for a commit sha."""
    if not remote_url or not sha:
        return ""
    raw = remote_url.strip()
    url = raw
    if "://" not in raw:
        host = ""
        path = ""
        if raw.startswith("git@"):
            rest = raw[4:]
            if ":" in rest:
                host, path = rest.split(":", 1)
            else:
                host = rest
        elif "@" in raw and ":" in raw:
            rest = raw.split("@", 1)[1]
            if ":" in rest:
                host, path = rest.split(":", 1)
            else:
                host = rest
        elif ":" in raw:
            host, path = raw.split(":", 1)
        else:
            host = raw
        if host:
            url = f"https://{host}/{path}" if path else f"https://{host}"
    url = url.rstrip("/")
    if "/a/" in url:
        url = url.replace("/a/", "/", 1)
    if url.endswith(".git"):
        url = url[:-4]
    return f"{url}/+/{sha}"


def push(
    repo_dir: Path,
    remote: str = "",
    branch: str = "",
    *,
    gerrit: bool = True,
    gerrit_remote: str = "",
    gerrit_review_branch: str = "",
) -> PushResult:
    """Push commits. Default: Gerrit ``git push origin HEAD:refs/for/<upstream-branch>``."""
    if gerrit:
        rem, review_branch = resolve_gerrit_review_branch(
            repo_dir,
            remote or "origin",
            saved_remote=gerrit_remote,
            saved_branch=gerrit_review_branch,
        )
        refspec = f"HEAD:refs/for/{review_branch}"
        r = run_git(repo_dir, ["push", rem, refspec], check=False)
        combined = "\n".join(x for x in (r.stdout, r.stderr) if x)
        urls = parse_gerrit_urls_from_push_output(combined)
        cmd = f"{rem} {refspec}"
        if not r.ok:
            err = (r.stderr or r.stdout or "").strip() or f"git push {rem} {refspec} failed"
            raise RuntimeError(err)
        return PushResult(
            cmd=cmd,
            remote=rem,
            review_branch=review_branch,
            stdout=r.stdout or "",
            stderr=r.stderr or "",
            gerrit_urls=urls,
            ok=True,
        )

    rem = remote or "origin"
    target = branch or current_branch(repo_dir)
    r = run_git(repo_dir, ["push", rem, target], check=False)
    combined = "\n".join(x for x in (r.stdout, r.stderr) if x)
    urls = parse_gerrit_urls_from_push_output(combined)
    cmd = f"{rem} {target}"
    if not r.ok:
        err = (r.stderr or r.stdout or "").strip() or f"git push {rem} {target} failed"
        raise RuntimeError(err)
    return PushResult(
        cmd=cmd,
        remote=rem,
        review_branch=target,
        stdout=r.stdout or "",
        stderr=r.stderr or "",
        gerrit_urls=urls,
        ok=True,
    )
