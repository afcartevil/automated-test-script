#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows-safe harness remote-runner helpers for gerrit-submit.

Goals:
  - Avoid PowerShell mangling of --args-json
  - Avoid ephemeral *.sh / prepare_*.py on the mapped drive
  - Work on any host: paths come from CLI args / discover (never hardcode Z: or user)

Subcommands:
  exec    Run a registered action; print CLI JSON and the job log body
  submit  Commit + push via temporary actions.local.json with inline bash -lc
          (commit message passed as base64; no .sh file written)

Examples:
  python harness_remote.py exec --mapped-root "Z:\\" --action workspace.project_status \\
    --args-json "{\"project_path\":\"project/km9/.../MdmConfig\"}"

  python harness_remote.py submit --mapped-root "Z:\\" \\
    --linux-root /work/code/qing.li3 \\
    --project-path project/km9/.../MdmConfig \\
    --remote origin --branch tOS_mtk_A16_trunk \\
    --add Android.mk --message-file msg.txt
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any


ACTION_ID = "git.gerrit_submit_once"
GERRIT_URL_RE = re.compile(r"https?://gerrit[^\s]+/\+/[0-9]+")
CHANGE_ID_RE = re.compile(r"Change-Id:\s*(I[0-9a-fA-F]+)")


def _find_harness_js() -> Path:
    env = os.environ.get("HARNESS_JS")
    if env and Path(env).is_file():
        return Path(env)
    appdata = os.environ.get("APPDATA", "")
    cand = Path(appdata) / "npm" / "node_modules" / "@transsion" / "harness-cli" / "bin" / "harness.js"
    if cand.is_file():
        return cand
    # npm global prefix fallback
    try:
        prefix = subprocess.check_output(["npm", "root", "-g"], text=True, stderr=subprocess.DEVNULL).strip()
        cand2 = Path(prefix) / "@transsion" / "harness-cli" / "bin" / "harness.js"
        if cand2.is_file():
            return cand2
    except Exception:
        pass
    raise SystemExit(
        "Cannot find harness.js. Install @transsion/harness-cli or set HARNESS_JS to harness.js path."
    )


def _norm_mapped_root(mapped_root: str) -> Path:
    p = Path(mapped_root)
    # Allow Z:\ or \\server\share\user
    return p


def _runner_paths(mapped_root: Path) -> tuple[Path, Path, Path, Path]:
    runner = mapped_root / "tran_harness" / "remote-runner"
    return (
        runner,
        runner / "config" / "actions.local.json",
        runner / "tmp",
        runner / "logs",
    )


def _run_harness(argv: list[str]) -> subprocess.CompletedProcess[str]:
    harness_js = _find_harness_js()
    cmd = ["node", str(harness_js), *argv]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def _latest_log(log_dir: Path, after_mtime: float | None = None) -> Path | None:
    if not log_dir.is_dir():
        return None
    files = [p for p in log_dir.glob("*.log") if p.is_file()]
    if after_mtime is not None:
        files = [p for p in files if p.stat().st_mtime >= after_mtime - 1]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _print_log(path: Path | None) -> str:
    if not path or not path.is_file():
        print("WARN: job log not found", file=sys.stderr)
        return ""
    body = path.read_text(encoding="utf-8", errors="replace")
    print(f"=== job log: {path} ===")
    print(body)
    return body


def cmd_exec(args: argparse.Namespace) -> int:
    mapped = _norm_mapped_root(args.mapped_root)
    _, _, _, log_dir = _runner_paths(mapped)
    before = time.time()
    argv = [
        "--json",
        "remote-runner",
        "exec",
        "--mapped-root",
        str(mapped),
        "--action",
        args.action,
        "--args-json",
        args.args_json,
        "--timeout",
        str(args.timeout),
    ]
    proc = _run_harness(argv)
    print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="" if proc.stderr.endswith("\n") else "\n")
    if args.read_log:
        # small wait for log flush
        time.sleep(0.3)
        _print_log(_latest_log(log_dir, after_mtime=before))
    return proc.returncode


def _read_message(args: argparse.Namespace) -> str:
    if args.message_file:
        raw = Path(args.message_file).read_bytes()
        # normalize newlines to LF
        text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        if not text.endswith("\n"):
            text += "\n"
        return text
    if args.message is not None:
        text = args.message.replace("\r\n", "\n").replace("\r", "\n")
        if not text.endswith("\n"):
            text += "\n"
        return text
    if not sys.stdin.isatty():
        text = sys.stdin.read().replace("\r\n", "\n").replace("\r", "\n")
        if not text.endswith("\n"):
            text += "\n"
        return text
    raise SystemExit("Provide --message-file, --message, or pipe message on stdin")


def _shell_quote_single(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def cmd_submit(args: argparse.Namespace) -> int:
    mapped = _norm_mapped_root(args.mapped_root)
    runner, actions_local, tmp_dir, log_dir = _runner_paths(mapped)
    if not runner.is_dir():
        raise SystemExit(f"runner not found under mapped root: {runner}")

    linux_root = args.linux_root.rstrip("/")
    project_path = args.project_path.replace("\\", "/").lstrip("/")
    linux_repo = f"{linux_root}/{project_path}"

    message = _read_message(args)
    msg_b64 = base64.b64encode(message.encode("utf-8")).decode("ascii")

    if args.add:
        add_cmd = "git add -- " + " ".join(_shell_quote_single(f) for f in args.add)
    else:
        add_cmd = "git add -u"
    nonce = uuid.uuid4().hex[:10]
    log_linux = f"{linux_root}/tran_harness/remote-runner/tmp/gerrit_submit_{nonce}.log"
    log_win = tmp_dir / f"gerrit_submit_{nonce}.log"

    # Entire remote script base64-encoded to avoid quoting / CRLF / Chinese issues.
    remote_script = f"""set -euo pipefail
LOG={_shell_quote_single(log_linux)}
exec >"$LOG" 2>&1
echo "START $(date -Is)"
cd {_shell_quote_single(linux_repo)}
echo "CWD=$(pwd)"
git status -sb
{add_cmd}
echo {msg_b64} | base64 -d | git commit -F -
echo "--- log -1 ---"
git log -1 --pretty=fuller
echo "--- push ---"
git push {_shell_quote_single(args.remote)} HEAD:refs/for/{args.branch}
echo "END $(date -Is)"
"""
    script_b64 = base64.b64encode(remote_script.encode("utf-8")).decode("ascii")
    bash_lc = f"echo {script_b64} | base64 -d | bash"

    actions: dict[str, Any] = {
        "schema_version": 1,
        "actions": [
            {
                "action_id": ACTION_ID,
                "enabled": True,
                "cwd": ".",
                "command": ["bash", "-lc", bash_lc],
                "timeout_sec": int(args.timeout),
                "allow_args": False,
                "arg_schema": {},
                "env_allowlist": [],
            }
        ],
    }

    tmp_dir.mkdir(parents=True, exist_ok=True)
    actions_local.parent.mkdir(parents=True, exist_ok=True)
    # LF-only JSON
    payload = (json.dumps(actions, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if b"\r" in payload:
        raise SystemExit("internal error: CRLF in actions.local.json payload")
    actions_local.write_bytes(payload)
    print(f"Wrote temporary action {ACTION_ID} -> {actions_local}")

    # Allow runner to reload config
    time.sleep(max(args.reload_wait, 0))

    before = time.time()
    proc = _run_harness(
        [
            "--json",
            "remote-runner",
            "exec",
            "--mapped-root",
            str(mapped),
            "--action",
            ACTION_ID,
            "--timeout",
            str(args.timeout),
        ]
    )
    print(proc.stdout, end="" if (proc.stdout or "").endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="" if proc.stderr.endswith("\n") else "\n")

    # Prefer dedicated submit log; fall back to job log
    time.sleep(0.3)
    body = ""
    if log_win.is_file():
        body = log_win.read_text(encoding="utf-8", errors="replace")
        print(f"=== submit log: {log_win} ===")
        print(body)
    else:
        body = _print_log(_latest_log(log_dir, after_mtime=before))

    # Always cleanup actions.local.json (even on failure)
    try:
        if actions_local.is_file():
            actions_local.unlink()
            print(f"Removed {actions_local}")
    except OSError as exc:
        print(f"WARN: failed to remove {actions_local}: {exc}", file=sys.stderr)

    urls = GERRIT_URL_RE.findall(body)
    change_ids = CHANGE_ID_RE.findall(body)
    result = {
        "ok": proc.returncode == 0 and bool(urls),
        "returncode": proc.returncode,
        "gerrit_url": urls[-1] if urls else None,
        "change_id": change_ids[-1] if change_ids else None,
        "submit_log": str(log_win) if log_win.is_file() else None,
        "remote": args.remote,
        "branch": args.branch,
        "linux_repo": linux_repo,
    }
    print("=== submit result ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else (proc.returncode or 1)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="gerrit-submit harness remote helpers")
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("exec", help="remote-runner exec with safe argv + optional log dump")
    e.add_argument("--mapped-root", required=True, help="From discover mapped_root (e.g. Z:\\)")
    e.add_argument("--action", required=True)
    e.add_argument("--args-json", default="{}")
    e.add_argument("--timeout", type=int, default=120)
    e.add_argument("--read-log", action="store_true", help="Print newest job log after exec")
    e.set_defaults(func=cmd_exec)

    s = sub.add_parser("submit", help="commit+push without writing .sh on mapped drive")
    s.add_argument("--mapped-root", required=True)
    s.add_argument("--linux-root", required=True, help="From discover inferred_remote_workspace")
    s.add_argument("--project-path", required=True, help="Path relative to linux/mapped root")
    s.add_argument("--remote", required=True, help="git remote name (e.g. origin)")
    s.add_argument("--branch", required=True, help="Gerrit target branch (refs/for/<branch>)")
    s.add_argument("--add", action="append", default=[], help="File to git add (repeatable). Default: git add -u")
    s.add_argument("--message-file", help="Local commit message file (any host path)")
    s.add_argument("--message", help="Commit message text")
    s.add_argument("--timeout", type=int, default=300)
    s.add_argument("--reload-wait", type=float, default=2.0, help="Seconds to wait for action reload")
    s.set_defaults(func=cmd_submit)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
