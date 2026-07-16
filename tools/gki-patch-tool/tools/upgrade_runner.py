#!/usr/bin/env python3
"""GKI upgrade CLI: apply patch → resolve conflicts → commit → build."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from cli_config import (  # noqa: E402
    add_settings_argument,
    get_upgrade_options,
    load_settings,
    strip_settings_from_argv,
)
from web_app.upgrade_service import (  # noqa: E402
    abort_upgrade,
    build_upgrade,
    commit_upgrade,
    continue_after_conflicts,
    get_upgrade_job,
    get_upgrade_progress,
    start_upgrade,
)


def _wait_job(job_id: str) -> dict:
    import time

    for _ in range(600):
        prog = get_upgrade_progress(job_id)
        status = prog.get("status", "")
        print(f"[{status}] {prog.get('message', '')}", flush=True)
        if status in ("completed", "failed", "conflicts", "aborted", "build_failed"):
            job = get_upgrade_job(job_id)
            return job or prog
        time.sleep(1)
    raise RuntimeError(f"任务 {job_id} 等待超时")


def cmd_start(args: argparse.Namespace) -> int:
    settings, _ = load_settings(args.settings)
    upgrade_opts = get_upgrade_options(settings)
    target = args.target_repo.strip()
    if not target:
        print("ERROR: --target-repo 必填", file=sys.stderr)
        return 1
    job_id, err = start_upgrade(
        from_tag=args.from_tag,
        to_tag=args.to_tag,
        repo=args.repo,
        analysis_task_id=args.task_id or "",
        patch_file=args.patch_file or "",
        target_repo_dir=target,
        apply_mode=args.apply_mode or upgrade_opts["apply_mode"],
        auto_commit=args.auto_commit,
        auto_build=args.auto_build,
        force_dirty=args.force_dirty,
        create_backup=not args.no_backup,
        commit_message=args.commit_message or "",
        commit_message_file=getattr(args, "commit_message_file", "") or "",
        build_command=args.build_command or "",
        build_workdir=args.build_workdir or "",
    )
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1
    print(f"升级任务已启动: {job_id}")
    if args.wait:
        job = _wait_job(job_id)
        print(json.dumps(job, ensure_ascii=False, indent=2, default=str))
        if job.get("status") == "conflicts":
            print("\n存在冲突，请手动解决后运行:")
            print(f"  python tools/upgrade_runner.py continue --job-id {job_id}")
            return 2
        return 0 if job.get("status") == "completed" else 1
    return 0


def cmd_continue(args: argparse.Namespace) -> int:
    ok, msg = continue_after_conflicts(args.job_id)
    print(msg)
    if ok and args.commit:
        ok2, msg2 = commit_upgrade(args.job_id, args.commit_message or "")
        print(msg2)
        ok = ok2
    if ok and args.build:
        ok3, msg3 = build_upgrade(
            args.job_id,
            args.build_command or "",
            args.build_workdir or "",
        )
        print(msg3)
        ok = ok3
    return 0 if ok else 1


def cmd_commit(args: argparse.Namespace) -> int:
    ok, msg = commit_upgrade(args.job_id, args.message or "")
    print(msg)
    return 0 if ok else 1


def cmd_build(args: argparse.Namespace) -> int:
    ok, msg = build_upgrade(args.job_id, args.command or "", args.workdir or "")
    print(msg)
    return 0 if ok else 1


def cmd_status(args: argparse.Namespace) -> int:
    job = get_upgrade_job(args.job_id)
    if not job:
        print(f"任务不存在: {args.job_id}", file=sys.stderr)
        return 1
    print(json.dumps(job, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_abort(args: argparse.Namespace) -> int:
    ok, msg = abort_upgrade(args.job_id)
    print(msg)
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GKI 升级合入工具")
    add_settings_argument(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="启动升级任务（合入 patch）")
    p_start.add_argument("--from-tag", required=True)
    p_start.add_argument("--to-tag", required=True)
    p_start.add_argument("--repo", default="https://android.googlesource.com/kernel/common")
    p_start.add_argument("--task-id", default="", help="关联的分析任务 ID（复用其 patch）")
    p_start.add_argument("--patch-file", default="", help="直接指定 patch 文件路径")
    p_start.add_argument("--target-repo", required=True, help="本次合入的 vendor 内核代码路径（必填）")
    p_start.add_argument("--apply-mode", choices=["format-patch", "squash"], default="")
    p_start.add_argument("--auto-commit", action="store_true")
    p_start.add_argument("--auto-build", action="store_true")
    p_start.add_argument("--force-dirty", action="store_true", help="允许在非干净工作区合入")
    p_start.add_argument("--no-backup", action="store_true")
    p_start.add_argument("--commit-message", default="")
    p_start.add_argument("--commit-message-file", default="", help="commit message 文件路径（git commit -F）")
    p_start.add_argument("--build-command", default="", help="编译命令（自动编译时必填）")
    p_start.add_argument("--build-workdir", default="", help="编译工作目录（自动编译时必填）")
    p_start.add_argument("--wait", action="store_true", help="等待任务完成")
    p_start.set_defaults(func=cmd_start)

    p_cont = sub.add_parser("continue", help="冲突解决后继续")
    p_cont.add_argument("--job-id", required=True)
    p_cont.add_argument("--commit", action="store_true", help="合入完成后自动提交")
    p_cont.add_argument("--build", action="store_true", help="提交后自动编译")
    p_cont.add_argument("--commit-message", default="")
    p_cont.add_argument("--build-command", default="")
    p_cont.add_argument("--build-workdir", default="")
    p_cont.set_defaults(func=cmd_continue)

    p_commit = sub.add_parser("commit", help="提交已合入的变更")
    p_commit.add_argument("--job-id", required=True)
    p_commit.add_argument("--message", default="")
    p_commit.set_defaults(func=cmd_commit)

    p_build = sub.add_parser("build", help="编译验证")
    p_build.add_argument("--job-id", required=True)
    p_build.add_argument("--command", default="", help="编译命令")
    p_build.add_argument("--workdir", default="", help="编译工作目录")
    p_build.set_defaults(func=cmd_build)

    p_status = sub.add_parser("status", help="查看任务状态")
    p_status.add_argument("--job-id", required=True)
    p_status.set_defaults(func=cmd_status)

    p_abort = sub.add_parser("abort", help="中止 git am")
    p_abort.add_argument("--job-id", required=True)
    p_abort.set_defaults(func=cmd_abort)

    return parser


def main() -> int:
    settings_path, rest = strip_settings_from_argv(sys.argv[1:])
    sys.argv = [sys.argv[0], *rest]
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "settings"):
        args.settings = settings_path
    else:
        args.settings = settings_path
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
