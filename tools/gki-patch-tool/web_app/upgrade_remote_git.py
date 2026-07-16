"""Remote git operations via BastionSSHSession (thread-local backend)."""
from __future__ import annotations

import re
import shlex
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

from web_app.ssh_bastion import BastionSSHSession
from web_app.target_repo_config import normalize_linux_path
from web_app.upgrade_git import GitResult
from web_app.upgrade_progress import append_job_log


_tls = threading.local()


def activate_remote_session(
    session: BastionSSHSession,
    repo_dir: str,
    job_id: str = "",
    *,
    remote_temp_dir: str = "",
) -> None:
    from web_app.remote_workdir_config import resolve_remote_temp_dir

    _tls.remote_session = session
    _tls.remote_repo = normalize_linux_path(repo_dir)
    _tls.job_id = job_id or ""
    session.set_remote_temp_dir(resolve_remote_temp_dir(remote_temp_dir))
    if job_id:
        session.set_progress_log(lambda msg: append_job_log(job_id, msg))


def deactivate_remote_session() -> None:
    _tls.remote_session = None
    _tls.remote_repo = ""
    _tls.job_id = ""


def is_remote_active() -> bool:
    return getattr(_tls, "remote_session", None) is not None


def _job_id() -> str:
    return getattr(_tls, "job_id", "") or ""


def _remote_log(msg: str, phase: str = "apply") -> None:
    append_job_log(_job_id(), msg, phase)


_APPLY_POLL_INTERVAL = 15


def _remote_sanitize_git_repo(label: str = "") -> None:
    """Remove index.lock and terminate stale git apply processes in this repo."""
    session = _session()
    qrepo = shlex.quote(_repo())
    repo = _repo()
    tag = f" ({label})" if label else ""
    _remote_log(f"▶ 清理残留 git 锁/apply 进程{tag}")
    cmd = (
        f"cd {qrepo}; "
        f"rm -f .git/index.lock .git/HEAD.lock 2>/dev/null; "
        f"ps -eo pid,cmd 2>/dev/null | grep '[g]it apply' | grep -F {shlex.quote(repo)} | "
        f"awk '{{print $1}}' | xargs -r kill -TERM 2>/dev/null; "
        f"sleep 1; "
        f"ps -eo pid,cmd 2>/dev/null | grep '[g]it apply' | grep -F {shlex.quote(repo)} | "
        f"awk '{{print $1}}' | xargs -r kill -KILL 2>/dev/null; "
        f"true"
    )
    session.run(cmd, timeout=60, check=False, capture_output=False)
    _remote_log(f"✓ 清理完成{tag}")


def _remote_verify_worktree_clean_or_fixup() -> None:
    """After reset, ensure porcelain is empty; force checkout-index if NFS left dirt."""
    session = _session()
    qrepo = shlex.quote(_repo())
    r = session.run(
        f"cd {qrepo} && git status --porcelain | wc -l",
        check=False,
        timeout=120,
    )
    try:
        n = int((r.stdout or "0").strip())
    except ValueError:
        n = -1
    if n <= 0:
        return
    _remote_log(f"reset 后仍有 {n} 项未清理，执行 checkout-index -f -a + clean -fd …")
    session.run(
        f"cd {qrepo} && git checkout-index -f -a && git clean -fd",
        timeout=7200,
        check=False,
        capture_output=False,
    )
    r2 = session.run(
        f"cd {qrepo} && git status --porcelain | wc -l",
        check=False,
        timeout=120,
    )
    try:
        n2 = int((r2.stdout or "0").strip())
    except ValueError:
        n2 = -1
    if n2 > 0:
        raise RuntimeError(
            f"reset 后工作区仍脏 ({n2} 项)，可能仍有 git apply 在写 NFS；"
            f"请 SSH 到 158 执行 pkill -f 'git apply' && git reset --hard HEAD"
        )


def _remote_run_apply_background(
    session: BastionSSHSession,
    qrepo: str,
    remote_patch: str,
    job_id: str,
    *,
    timeout: int = 7200,
) -> GitResult:
    """Run git apply in background and poll progress (avoids blocking SSH for hours)."""
    apply_log = session._remote_temp_join(f"gki_apply_{job_id}.log")
    exit_file = session._remote_temp_join(f"gki_apply_{job_id}.exit")
    qlog = shlex.quote(apply_log)
    qexit = shlex.quote(exit_file)
    qpatch = shlex.quote(remote_patch)
    tmp_patch = session._remote_temp_join(f"gki_patch_{job_id}.patch")
    qtmp = shlex.quote(tmp_patch)
    repo_marker = shlex.quote(_repo())

    _remote_sanitize_git_repo("apply 前")

    _remote_log("▶ 复制 patch 到远程 /tmp（减轻 NFS 读取延迟）")
    cp_r = session.run(
        f"cp -f {qpatch} {qtmp} && wc -c < {qtmp}",
        check=False,
        timeout=300,
        capture_output=True,
    )
    if cp_r.ok and (cp_r.stdout or "").strip():
        size = (cp_r.stdout or "").strip().splitlines()[-1]
        _remote_log(f"✓ patch 已复制到 {tmp_patch} ({size} bytes)")
        qpatch_use = qtmp
    else:
        _remote_log("⚠ patch 复制到 /tmp 失败，沿用原路径")
        qpatch_use = qpatch

    _remote_log("▶ 启动后台 git apply --reject …")
    session.run(f"rm -f {qexit}", check=False, timeout=30, capture_output=False)
    # SSH run() wraps as `{ cmd; }` — trailing `&;` is invalid bash; use `& sleep 1` instead.
    apply_inner = (
        f"cd {qrepo} && "
        f"git apply --reject --whitespace=nowarn {qpatch_use} "
        f"> /dev/null 2> {qlog}; echo $? > {qexit}"
    )
    start_cmd = (
        f"nohup bash -c {shlex.quote(apply_inner)} </dev/null >/dev/null 2>&1 & sleep 1"
    )
    session.run(start_cmd, check=False, timeout=60, capture_output=False)

    t0 = time.time()
    last_n = -1
    no_progress_hb = 0

    while time.time() - t0 < timeout:
        pr = session.run(
            f"test -f {qexit} && cat {qexit} || echo __RUNNING__",
            check=False,
            timeout=60,
            capture_output=True,
        )
        out = (pr.stdout or "").strip()
        if out and out != "__RUNNING__" and out.isdigit():
            exit_code = int(out)
            elapsed = time.time() - t0
            log_r = session.run(
                f"tail -c 80000 {qlog} 2>/dev/null || true",
                check=False,
                timeout=60,
                capture_output=True,
            )
            stdout = (log_r.stdout or "").strip()
            mark = "✓" if exit_code == 0 else "✗"
            tail = stdout[:200] if stdout and exit_code != 0 else ""
            _remote_log(
                f"{mark} 结束: git apply --reject (exit={exit_code}, {elapsed:.1f}s) {tail}"
            )
            if stdout and exit_code != 0:
                _remote_log(f"git apply 失败详情: {stdout[:2000]}")
            session.run(f"rm -f {qexit}", check=False, timeout=30, capture_output=False)
            return GitResult(exit_code, stdout, "")

        stat = session.run(
            f"cd {qrepo} && git diff --name-only HEAD 2>/dev/null | wc -l",
            check=False,
            timeout=120,
            capture_output=True,
        )
        try:
            n = int((stat.stdout or "0").strip())
        except ValueError:
            n = -1
        elapsed = time.time() - t0

        proc = session.run(
            f"ps -eo cmd 2>/dev/null | grep '[g]it apply' | grep -F {repo_marker} | wc -l",
            check=False,
            timeout=30,
            capture_output=True,
        )
        try:
            proc_n = int((proc.stdout or "0").strip())
        except ValueError:
            proc_n = -1

        if proc_n == 0 and n > 50:
            rej_r = session.run(
                f"cd {qrepo} && find . -name '*.rej' -type f 2>/dev/null | wc -l",
                check=False,
                timeout=60,
                capture_output=True,
            )
            try:
                rej_n = int((rej_r.stdout or "0").strip())
            except ValueError:
                rej_n = 0
            exit_code = 1 if rej_n > 0 else 0
            log_r = session.run(
                f"tail -c 80000 {qlog} 2>/dev/null || true",
                check=False,
                timeout=60,
                capture_output=True,
            )
            stdout = (log_r.stdout or "").strip()
            _remote_log(
                f"检测到 apply 已结束（无 git apply 进程，{n} 文件变更，"
                f"{rej_n} .rej），推断 exit={exit_code} · {elapsed:.0f}s"
            )
            return GitResult(exit_code, stdout, "")

        if n != last_n:
            _remote_log(
                f"git apply 进度: 已变更 {n} 个文件 · {elapsed:.0f}s"
                + (f"（进程数 {proc_n}）" if proc_n >= 0 else "")
            )
            last_n = n
            no_progress_hb = 0
        else:
            no_progress_hb += 1
            if no_progress_hb >= 2:
                _remote_log(
                    f"git apply 进行中: {n} 个文件 · {elapsed:.0f}s"
                    + (f" · 进程数 {proc_n}" if proc_n >= 0 else "")
                )
                no_progress_hb = 0

        time.sleep(_APPLY_POLL_INTERVAL)

    raise RuntimeError(f"git apply 超时 ({timeout}s)")


def _remote_run_am_background(
    session: BastionSSHSession,
    qrepo: str,
    remote_patch: str,
    job_id: str,
    *,
    timeout: int = 10800,
) -> GitResult:
    """Run git am in background and poll progress (avoids SSH command_timeout on long am)."""
    am_log = session._remote_temp_join(f"gki_am_{job_id}.log")
    exit_file = session._remote_temp_join(f"gki_am_{job_id}.exit")
    qlog = shlex.quote(am_log)
    qexit = shlex.quote(exit_file)
    qpatch = shlex.quote(remote_patch)
    tmp_patch = session._remote_temp_join(f"gki_am_patch_{job_id}.patch")
    qtmp = shlex.quote(tmp_patch)
    repo_marker = shlex.quote(_repo())

    _remote_sanitize_git_repo("git am 前")

    _remote_log("▶ 复制 patch 到远程 /tmp（减轻 NFS 读取延迟）")
    cp_r = session.run(
        f"cp -f {qpatch} {qtmp} && wc -c < {qtmp}",
        check=False,
        timeout=300,
        capture_output=True,
    )
    if cp_r.ok and (cp_r.stdout or "").strip():
        size = (cp_r.stdout or "").strip().splitlines()[-1]
        _remote_log(f"✓ patch 已复制到 {tmp_patch} ({size} bytes)")
        qpatch_use = qtmp
    else:
        _remote_log("⚠ patch 复制到 /tmp 失败，沿用原路径")
        qpatch_use = qpatch

    _remote_log("▶ 启动后台 git am --3way --keep-cr …")
    session.run(f"rm -f {qexit}", check=False, timeout=30, capture_output=False)
    am_inner = (
        f"cd {qrepo} && "
        f"git am --3way --keep-cr < {qpatch_use} "
        f"> {qlog} 2>&1; echo $? > {qexit}"
    )
    start_cmd = (
        f"nohup bash -c {shlex.quote(am_inner)} </dev/null >/dev/null 2>&1 & sleep 1"
    )
    session.run(start_cmd, check=False, timeout=60, capture_output=False)

    t0 = time.time()
    last_progress = ""
    no_progress_hb = 0

    while time.time() - t0 < timeout:
        pr = session.run(
            f"test -f {qexit} && cat {qexit} || echo __RUNNING__",
            check=False,
            timeout=60,
            capture_output=True,
        )
        out = (pr.stdout or "").strip()
        if out and out != "__RUNNING__" and out.isdigit():
            exit_code = int(out)
            elapsed = time.time() - t0
            log_r = session.run(
                f"tail -c 80000 {qlog} 2>/dev/null || true",
                check=False,
                timeout=60,
                capture_output=True,
            )
            stdout = (log_r.stdout or "").strip()
            mark = "✓" if exit_code == 0 else "✗"
            tail = stdout[:200] if stdout and exit_code != 0 else ""
            _remote_log(
                f"{mark} 结束: git am --3way --keep-cr (exit={exit_code}, {elapsed:.1f}s) {tail}"
            )
            if stdout and exit_code != 0:
                _remote_log(f"git am 失败详情: {stdout[:2000]}")
            session.run(f"rm -f {qexit}", check=False, timeout=30, capture_output=False)
            return GitResult(exit_code, stdout, "")

        prog_r = session.run(
            f"cd {qrepo} && "
            "if test -d .git/rebase-apply; then "
            "printf '%s/%s' \"$(cat .git/rebase-apply/next 2>/dev/null || echo 0)\" "
            "\"$(cat .git/rebase-apply/end 2>/dev/null || echo ?)\"; "
            "else echo __NO_AM__; fi",
            check=False,
            timeout=60,
            capture_output=True,
        )
        progress = (prog_r.stdout or "").strip()
        elapsed = time.time() - t0

        proc = session.run(
            f"ps -eo cmd 2>/dev/null | grep '[g]it am' | grep -F {repo_marker} | wc -l",
            check=False,
            timeout=30,
            capture_output=True,
        )
        try:
            proc_n = int((proc.stdout or "0").strip())
        except ValueError:
            proc_n = -1

        if progress != last_progress and progress and progress != "__NO_AM__":
            _remote_log(
                f"git am 进度: commit {progress} · {elapsed:.0f}s"
                + (f" · 进程数 {proc_n}" if proc_n >= 0 else "")
            )
            last_progress = progress
            no_progress_hb = 0
        elif proc_n == 0 and progress == "__NO_AM__":
            log_r = session.run(
                f"test -f {qexit} && cat {qexit} || echo __MISSING__",
                check=False,
                timeout=30,
                capture_output=True,
            )
            if (log_r.stdout or "").strip() == "__MISSING__":
                log_tail = session.run(
                    f"tail -c 80000 {qlog} 2>/dev/null || true",
                    check=False,
                    timeout=60,
                    capture_output=True,
                )
                stdout = (log_tail.stdout or "").strip()
                _remote_log(
                    f"检测到 git am 已结束（无 rebase-apply、无 git am 进程）· {elapsed:.0f}s"
                )
                return GitResult(1, stdout, "git am 异常退出（未写入 exit 文件）")
        else:
            no_progress_hb += 1
            if no_progress_hb >= 2:
                hint = (
                    f": commit {progress}"
                    if progress and progress != "__NO_AM__"
                    else ""
                )
                _remote_log(
                    f"git am 进行中{hint} · {elapsed:.0f}s"
                    + (f" · 进程数 {proc_n}" if proc_n >= 0 else "")
                )
                no_progress_hb = 0

        time.sleep(_APPLY_POLL_INTERVAL)

    raise RuntimeError(f"git am 超时 ({timeout}s)")


def _session() -> BastionSSHSession:
    s = getattr(_tls, "remote_session", None)
    if not s:
        raise RuntimeError("远程 SSH 未连接")
    return s


def _repo() -> str:
    r = getattr(_tls, "remote_repo", "")
    if not r:
        raise RuntimeError("未设置远程仓库路径")
    return r


def _resolve_remote_cwd(repo_dir: Path) -> str:
    """Map Path(``.``) placeholder to the SSH session's configured remote repo."""
    cwd = normalize_linux_path(str(repo_dir).replace("\\", "/")).rstrip("/")
    if not cwd or cwd in (".", "./"):
        return normalize_linux_path(_repo()).rstrip("/")
    return cwd


def _git_cmd(args: List[str]) -> str:
    parts = " ".join(shlex.quote(a) for a in args)
    return f"cd {shlex.quote(_repo())} && git {parts}"


def _git_cmd_for_repo(repo_dir: Path, args: List[str]) -> str:
    """Run git in ``repo_dir`` when it differs from the session default repo."""
    parts = " ".join(shlex.quote(a) for a in args)
    cwd = _resolve_remote_cwd(repo_dir)
    default = normalize_linux_path(_repo()).rstrip("/")
    if cwd != default:
        return f"cd {shlex.quote(cwd)} && git {parts}"
    return _git_cmd(args)


def remote_run_git(
    repo_dir: Path,
    args: List[str],
    *,
    timeout: Optional[int] = None,
    check: bool = True,
    log_label: str = "",
    capture_output: bool = True,
) -> GitResult:
    label = log_label or f"git {' '.join(args)}"
    _remote_log(f"▶ 开始: {label}")
    t0 = time.time()
    r = _session().run(
        _git_cmd_for_repo(repo_dir, args),
        timeout=timeout,
        check=False,
        capture_output=capture_output,
    )
    elapsed = time.time() - t0
    result = GitResult(r.returncode, r.stdout, r.stderr)
    tail = ""
    if not result.ok:
        tail = (result.stderr.strip() or result.stdout.strip())[:200]
        _remote_log(f"✗ 结束: {label} (exit={result.returncode}, {elapsed:.1f}s) {tail}")
    else:
        _remote_log(f"✓ 结束: {label} (exit=0, {elapsed:.1f}s)")
    if check and not result.ok:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result


def remote_repo_diagnose() -> str:
    if not is_remote_active():
        return "远程 SSH 未连接"
    ok, detail = _session().diagnose_repo(_repo())
    return "" if ok else detail


def remote_repo_is_git(repo_dir: Path) -> bool:
    if not is_remote_active():
        return False
    cwd = _resolve_remote_cwd(repo_dir)
    default = normalize_linux_path(_repo()).rstrip("/")
    if cwd == default:
        return _session().test_repo(_repo())
    r = remote_run_in_dir(
        cwd,
        "git rev-parse --is-inside-work-tree 2>/dev/null",
        timeout=20,
    )
    return r.ok and (r.stdout or "").strip().lower() == "true"


_PORCELAIN_LINE = re.compile(r"^(?:[ MADRCU?!]{2}|\?\?) ")


def _filter_porcelain_lines(text: str) -> str:
    lines = [ln for ln in text.splitlines() if _PORCELAIN_LINE.match(ln)]
    return "\n".join(lines)


def remote_working_tree_status(repo_dir: Path) -> str:
    raw = remote_run_git(repo_dir, ["status", "--porcelain"], log_label="git status --porcelain").stdout
    return _filter_porcelain_lines(raw)


def remote_is_clean_worktree(repo_dir: Path) -> bool:
    return not remote_working_tree_status(repo_dir)


def remote_reset_worktree_fast(
    repo_dir: Path,
    *,
    dirty_count: int = 0,
    tracked_count: int = 0,
    untracked_count: int = 0,
) -> None:
    """Reset large dirty trees on remote NFS (split steps, no redundant parallel checkout)."""
    qrepo = shlex.quote(_repo())
    n_hint = dirty_count or "?"
    session = _session()
    timeout = 7200

    _remote_sanitize_git_repo("reset 前")

    if tracked_count > 0:
        _remote_log(
            f"▶ 开始: git reset --hard HEAD（约 {tracked_count} 项 tracked 变更）"
        )
        t0 = time.time()
        r = session.run(
            f"set -e; cd {qrepo}; git reset --hard HEAD",
            timeout=timeout,
            check=False,
            capture_output=False,
        )
        elapsed = time.time() - t0
        if not r.ok:
            tail = (r.stdout or "")[-1500:]
            _remote_log(f"✗ git reset --hard 失败 (exit={r.returncode}, {elapsed:.1f}s)")
            raise RuntimeError(
                f"git reset --hard 失败 (exit {r.returncode}): {tail[-800:]}"
            )
        _remote_log(f"✓ 结束: git reset --hard HEAD ({elapsed:.1f}s)")

    if untracked_count > 0 or tracked_count == 0:
        label = untracked_count or n_hint
        _remote_log(f"▶ 开始: git clean -fd（约 {label} 项 untracked）")
        t0 = time.time()
        if untracked_count >= 200:
            clean_cmd = (
                f"set -e; cd {qrepo}; "
                "jobs=$(nproc 2>/dev/null || echo 4); "
                "git ls-files --others --exclude-standard -z | "
                "xargs -0 -r -P \"$jobs\" -n 80 rm -f; "
                "git clean -fd"
            )
        else:
            clean_cmd = f"set -e; cd {qrepo}; git clean -fd"
        r = session.run(clean_cmd, timeout=timeout, check=False, capture_output=False)
        elapsed = time.time() - t0
        if not r.ok:
            tail = (r.stdout or "")[-1500:]
            _remote_log(f"✗ git clean 失败 (exit={r.returncode}, {elapsed:.1f}s)")
            raise RuntimeError(f"git clean -fd 失败 (exit {r.returncode}): {tail[-800:]}")
        _remote_log(f"✓ 结束: git clean -fd ({elapsed:.1f}s)")

    _remote_verify_worktree_clean_or_fixup()


def remote_git_am_in_progress(repo_dir: Path) -> bool:
    q = shlex.quote(_repo() + "/.git/rebase-apply")
    r = _session().run(f"test -d {q} && echo yes || echo no", check=False)
    return "yes" in r.stdout


def _remote_patch_dest(job_id: str, patch_file: Path) -> str:
    """Upload patch to the task's build workdir (Linux path on target host)."""
    from web_app.database import get_upgrade_job

    job = get_upgrade_job(job_id) or {}
    build_wd = normalize_linux_path(job.get("build_workdir") or "")
    if not build_wd:
        raise RuntimeError(
            "远程合入需要填写「编译工作目录」，patch 将上传到该目录（合入后保留供手动调试）"
        )
    if not build_wd.startswith("/"):
        raise RuntimeError(f"编译工作目录须为 Linux 绝对路径: {build_wd}")
    name = patch_file.name or f"gki_upgrade_{job_id}.patch"
    return f"{build_wd}/{name}"


def _log_manual_apply_hints(remote_patch: str) -> None:
    qpatch = shlex.quote(remote_patch)
    qrepo = shlex.quote(_repo())
    _remote_log(f"远程 patch 已保留: {remote_patch}")
    _remote_log("手动调试示例（SSH 到 158 后执行）:")
    _remote_log(f"  ls -lh {remote_patch}")
    _remote_log(f"  cd {qrepo} && git status")
    _remote_log(f"  cd {qrepo} && git apply --stat {qpatch}")
    _remote_log(f"  cd {qrepo} && git apply --reject --whitespace=nowarn {qpatch}")
    _remote_log(f"  cd {qrepo} && find . -name '*.rej' | head")


def _deploy_patch_file(job_id: str, patch_file: Path, remote_patch: str) -> None:
    """Copy patch to remote path: hybrid uses local mount; otherwise SSH upload."""
    from web_app.database import get_upgrade_job
    from web_app.job_file_io import copy_local_file_to_remote_path, use_local_file_io

    job = get_upgrade_job(job_id) or {}
    if use_local_file_io(job):
        local_dest = copy_local_file_to_remote_path(job, patch_file, remote_patch)
        _remote_log(f"步骤 1/3: 混合模式 — 经本地映射写入 patch -> {local_dest}")
        return
    _remote_log(f"步骤 1/3: 上传 patch -> {remote_patch}")
    _session().upload_local_file(str(patch_file), remote_patch)


def remote_apply_format_patch(repo_dir: Path, patch_file: Path, job_id: str) -> GitResult:
    local = Path(patch_file)
    remote_patch = _remote_patch_dest(job_id, local)
    build_wd = normalize_linux_path(remote_patch.rsplit("/", 1)[0])
    _remote_log(f"合入(format-patch): 本地 {local.name} ({local.stat().st_size / 1024 / 1024:.1f} MB)")
    dir_chk = _session().run(
        f"test -d {shlex.quote(build_wd)} && echo OK || echo MISSING",
        check=False,
    )
    if "OK" not in dir_chk.stdout:
        raise RuntimeError(f"编译工作目录不存在: {build_wd}")
    _deploy_patch_file(job_id, local, remote_patch)
    _remote_log("步骤 2/3: 校验远程 patch 文件")
    chk = _session().run(
        f"test -f {shlex.quote(remote_patch)} && ls -lh {shlex.quote(remote_patch)} || echo MISSING",
        check=False,
    )
    if "MISSING" in chk.stdout:
        raise RuntimeError(f"上传后远程 patch 不存在: {remote_patch}")
    if chk.stdout.strip():
        _remote_log(f"远程文件: {chk.stdout.strip().splitlines()[-1]}")
    _remote_log("步骤 3/3: git am --3way --keep-cr")
    session = _session()
    qrepo = shlex.quote(_repo())
    _remote_log(
        "▶ 开始: git am --3way --keep-cr（后台执行 + 轮询进度，"
        "避免 SSH 长连接 3600s 超时；冲突/错误见远程日志）"
    )
    result = _remote_run_am_background(
        session, qrepo, remote_patch, job_id, timeout=10800,
    )
    _log_manual_apply_hints(remote_patch)
    return result


def remote_apply_squash_patch(repo_dir: Path, patch_file: Path, job_id: str) -> GitResult:
    local = Path(patch_file)
    remote_patch = _remote_patch_dest(job_id, local)
    build_wd = normalize_linux_path(remote_patch.rsplit("/", 1)[0])
    _remote_log(f"合入(squash): 本地 {local.name} ({local.stat().st_size / 1024 / 1024:.1f} MB)")
    dir_chk = _session().run(
        f"test -d {shlex.quote(build_wd)} && echo OK || echo MISSING",
        check=False,
    )
    if "OK" not in dir_chk.stdout:
        raise RuntimeError(f"编译工作目录不存在: {build_wd}")
    _deploy_patch_file(job_id, local, remote_patch)
    _remote_log("步骤 2/3: 校验远程 patch 文件")
    chk = _session().run(
        f"test -f {shlex.quote(remote_patch)} && ls -lh {shlex.quote(remote_patch)} || echo MISSING",
        check=False,
    )
    if "MISSING" in chk.stdout:
        raise RuntimeError(f"上传后远程 patch 不存在: {remote_patch}")
    if chk.stdout.strip():
        _remote_log(f"远程文件: {chk.stdout.strip().splitlines()[-1]}")
    _remote_log(f"步骤 3/3: git apply --reject --whitespace=nowarn {remote_patch}")
    session = _session()
    qrepo = shlex.quote(_repo())
    _remote_log(
        "▶ 开始: git apply --reject（后台执行 + 轮询进度，"
        "避免 SSH 长连接阻塞；冲突/错误见远程日志）"
    )
    result = _remote_run_apply_background(
        session, qrepo, remote_patch, job_id, timeout=7200,
    )
    _log_manual_apply_hints(remote_patch)
    return result


def remote_has_conflict_markers(repo_dir: Path, files: Optional[List[str]] = None) -> List[str]:
    if not files:
        return []
    qrepo = shlex.quote(_repo())
    repo_prefix = _repo().rstrip("/") + "/"
    if len(files) <= 32:
        paths = " ".join(shlex.quote(rel) for rel in files)
        cmd = f"cd {qrepo} && grep -l '^<<<<<<< ' {paths} 2>/dev/null || true"
        _remote_log(f"检查冲突标记 <<<<<<< …（{len(files)} 个变更文件）")
    else:
        _remote_log(f"批量检查冲突标记 <<<<<<< …（{len(files)} 个变更文件，单次 grep）")
        cmd = (
            f"cd {qrepo} && git diff --name-only HEAD | "
            f"xargs -r grep -l '^<<<<<<< ' 2>/dev/null || true"
        )
    r = _session().run(cmd, check=False)
    conflicted: List[str] = []
    for line in r.stdout.splitlines():
        s = line.strip().lstrip("./")
        if s.startswith(repo_prefix):
            s = s[len(repo_prefix):]
        if s:
            conflicted.append(s)
    return sorted(set(conflicted))


def remote_list_reject_files(repo_dir: Path) -> List[str]:
    from web_app.upgrade_git import parse_reject_files_from_porcelain

    raw = remote_run_git(
        repo_dir,
        ["status", "--porcelain"],
        log_label="git status --porcelain (.rej)",
        check=False,
    ).stdout
    return parse_reject_files_from_porcelain(raw)


def remote_read_text(rel_path: str) -> str:
    rel = rel_path.replace("\\", "/").lstrip("/")
    q = shlex.quote(f"{_repo()}/{rel}")
    r = _session().run(
        f"test -f {q} && cat {q} || echo __GKI_FILE_MISSING__",
        check=False,
        timeout=180,
        capture_output=False,
    )
    if "__GKI_FILE_MISSING__" in r.stdout and r.stdout.strip() == "__GKI_FILE_MISSING__":
        raise FileNotFoundError(rel_path)
    return r.stdout.replace("__GKI_FILE_MISSING__", "")


def remote_read_absolute(abs_path: str) -> str:
    path = normalize_linux_path(abs_path.replace("\\", "/"))
    q = shlex.quote(path)
    r = _session().run(
        f"test -f {q} && cat {q} || echo __GKI_FILE_MISSING__",
        check=False,
        timeout=180,
        capture_output=False,
    )
    if "__GKI_FILE_MISSING__" in r.stdout and r.stdout.strip() == "__GKI_FILE_MISSING__":
        raise FileNotFoundError(path)
    return r.stdout.replace("__GKI_FILE_MISSING__", "")


def remote_file_exists(abs_path: str) -> bool:
    path = abs_path.replace("\\", "/")
    if not path.startswith("/"):
        path = f"{_repo().rstrip('/')}/{path.lstrip('/')}"
    else:
        path = normalize_linux_path(path)
    q = shlex.quote(path)
    r = _session().run(f"test -f {q} && echo yes || echo no", check=False)
    return r.stdout.strip() == "yes"


def remote_write_text(rel_path: str, content: str) -> None:
    rel = rel_path.replace("\\", "/").lstrip("/")
    remote = f"{_repo().rstrip('/')}/{rel}"
    _session().upload_text_file(content, remote)


def remote_write_absolute(abs_path: str, content: str) -> None:
    path = normalize_linux_path(abs_path.replace("\\", "/"))
    _session().upload_text_file(content, path)


def remote_run_shell(command: str) -> None:
    qrepo = shlex.quote(_repo())
    _session().run(f"cd {qrepo} && {command}", check=False)


def remote_run_in_dir(cwd: str, command: str, *, timeout: int = 45) -> GitResult:
    """Run shell command with cwd on remote build machine."""
    qcwd = shlex.quote(normalize_linux_path((cwd or "").replace("\\", "/")))
    r = _session().run(
        f"cd {qcwd} && {command}",
        timeout=timeout,
        check=False,
        capture_output=True,
    )
    return GitResult(r.returncode, r.stdout or "", r.stderr or "")


def remote_run_build(
    build_workdir: str,
    build_command: str,
    log_remote: str,
    timeout: int,
    *,
    local_log: Optional[Path] = None,
    on_log_update: Optional[Callable[[str], None]] = None,
) -> int:
    """Run build on remote in background; poll log until exit file appears."""
    wd = shlex.quote(build_workdir.strip())
    log = shlex.quote(log_remote)
    exit_file = shlex.quote(log_remote + ".exit")
    inner = (
        f"cd {wd} && ({build_command.strip()}) > {log} 2>&1; "
        f"echo $? > {log_remote + '.exit'}"
    )
    start_cmd = (
        f"rm -f {log} {exit_file}; "
        f"nohup bash -c {shlex.quote(inner)} </dev/null >/dev/null 2>&1 & sleep 1"
    )
    _session().run(start_cmd, timeout=120, check=False, capture_output=False)

    deadline = time.time() + max(timeout, 60)
    while time.time() < deadline:
        r = _session().run(
            f"test -f {exit_file} && cat {exit_file} || echo __RUNNING__",
            check=False,
        )
        out = (r.stdout or "").strip()
        if out and out != "__RUNNING__" and "__RUNNING__" not in out:
            m = re.search(r"(\d+)", out)
            code = int(m.group(1)) if m else -1
            if local_log is not None:
                remote_fetch_build_log(log_remote, local_log, keep_remote=True)
                if on_log_update:
                    from web_app.upgrade_execution_log import read_text_file_last_line
                    on_log_update(read_text_file_last_line(local_log))
            return code

        if local_log is not None:
            remote_fetch_build_log(log_remote, local_log, keep_remote=True)
            if on_log_update:
                from web_app.upgrade_execution_log import read_text_file_last_line
                on_log_update(read_text_file_last_line(local_log))
        time.sleep(15)

    raise TimeoutError(f"远程编译超时 ({timeout}s)")


def _remote_offset_path(local_log: Path) -> Path:
    return Path(f"{local_log}.remote_off")


def reset_build_log_remote_sync(local_log: Path) -> None:
    """Reset remote→local byte offset after truncating the local build log."""
    off = _remote_offset_path(local_log)
    if off.is_file():
        off.unlink()


def _read_remote_offset(local_log: Path) -> int:
    off = _remote_offset_path(local_log)
    if not off.is_file():
        return 0
    try:
        return max(0, int((off.read_text(encoding="utf-8") or "0").strip()))
    except (ValueError, OSError):
        return 0


def _write_remote_offset(local_log: Path, nbytes: int) -> None:
    _remote_offset_path(local_log).write_text(str(max(0, nbytes)), encoding="utf-8")


def remote_fetch_build_log(
    log_remote: str,
    local_log: Path,
    *,
    keep_remote: bool = False,
    reset: bool = False,
) -> str:
    """Sync remote build log to local file (incremental append after local header).

    Tracks bytes already copied from the **remote** log in ``{local_log}.remote_off``,
    not local file size (local may contain a metadata header that remote does not).
    """
    if reset:
        reset_build_log_remote_sync(local_log)
    session = _session()
    local_log.parent.mkdir(parents=True, exist_ok=True)
    remote_off = _read_remote_offset(local_log)
    r = session.run(
        f"tail -c +{remote_off + 1} {shlex.quote(log_remote)} 2>/dev/null || true",
        check=False,
    )
    chunk = r.stdout or ""
    if chunk:
        with local_log.open("a", encoding="utf-8", errors="replace") as f:
            f.write(chunk)
        _write_remote_offset(
            local_log,
            remote_off + len(chunk.encode("utf-8", errors="replace")),
        )
    elif remote_off == 0 and local_log.is_file() and local_log.stat().st_size == 0:
        r = session.run(f"cat {shlex.quote(log_remote)}", check=False)
        text = r.stdout or ""
        if text:
            local_log.write_text(text, encoding="utf-8", errors="replace")
            _write_remote_offset(
                local_log,
                len(text.encode("utf-8", errors="replace")),
            )
    if not keep_remote:
        session.run(
            f"rm -f {shlex.quote(log_remote)} {shlex.quote(log_remote + '.exit')}",
            check=False,
        )
    try:
        return local_log.read_text(encoding="utf-8", errors="replace") if local_log.stat().st_size < 512 * 1024 else ""
    except OSError:
        return ""
