#!/usr/bin/env python3
"""Host ASF / Harness remote-exec compatibility for modem-patch-tool.

Mirrors tahp-console host-tool-runtime + harness-bridge-exec:
- legacy: remote-runner bridge-exec
- new asf: bridge up / bridge cmd (+ exit-code wrap)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

BRIDGE_EXIT_MARKER = "TAHP_BRIDGE_EXIT:"
FLAVOR_LEGACY = "legacy-bridge-exec"
FLAVOR_ASF = "asf-bridge"
FLAVOR_UNAVAILABLE = "unavailable"

LogFn = Callable[[str], None]

_flavor_cache: Optional[Tuple[str, float]] = None
_asf_session: Optional[int] = None
_FLAVOR_TTL_SEC = 60.0


def _noop_log(_msg: str) -> None:
    pass


def resolve_cli_spawn(args: List[str]) -> Tuple[str, List[str]]:
    """Prefer node + harness.js (Windows-safe argv); else asf/harness on PATH."""
    appdata = os.environ.get("APPDATA") or ""
    if appdata:
        harness_js = os.path.join(
            appdata, "npm", "node_modules", "@transsion", "harness-cli", "bin", "harness.js"
        )
        node = shutil.which("node")
        if os.path.isfile(harness_js) and node:
            return node, [harness_js, *args]

    npm_dir = os.path.join(appdata, "npm") if appdata else ""
    prefix = "harness"
    if npm_dir and (
        os.path.isfile(os.path.join(npm_dir, "asf.cmd"))
        or os.path.isfile(os.path.join(npm_dir, "asf.ps1"))
    ):
        prefix = "asf"
    elif shutil.which("asf"):
        prefix = "asf"
    return prefix, args


def run_cli(
    args: List[str],
    *,
    timeout: float = 300,
    log: LogFn = _noop_log,
) -> subprocess.CompletedProcess:
    command, argv = resolve_cli_spawn(args)
    full = [command, *argv]
    log(f"Running host CLI: {' '.join(full[:8])}{' ...' if len(full) > 8 else ''}")
    try:
        return subprocess.run(
            full,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
    except FileNotFoundError:
        # Last resort: shell lookup (asf.cmd / harness.cmd)
        prefix = "asf" if shutil.which("asf") else "harness"
        return subprocess.run(
            [prefix, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=(sys.platform == "win32"),
        )


def run_cli_help_text(args: List[str], timeout: float = 8) -> str:
    try:
        result = run_cli(args, timeout=timeout)
        return f"{result.stdout or ''}\n{result.stderr or ''}"
    except Exception as exc:
        return str(exc)


def flavor_from_help_text(remote_runner_help: str, bridge_help: str) -> str:
    if re.search(r"bridge-exec", remote_runner_help or ""):
        return FLAVOR_LEGACY
    if re.search(r"\bcmd\b", bridge_help or "") and re.search(r"bridge", bridge_help or ""):
        return FLAVOR_ASF
    return FLAVOR_UNAVAILABLE


def detect_flavor(*, refresh: bool = False) -> str:
    global _flavor_cache
    now = time.time()
    if (
        not refresh
        and _flavor_cache is not None
        and (now - _flavor_cache[1]) < _FLAVOR_TTL_SEC
    ):
        return _flavor_cache[0]
    rr = run_cli_help_text(["remote-runner", "--help"])
    br = "" if "bridge-exec" in rr else run_cli_help_text(["bridge", "--help"])
    value = flavor_from_help_text(rr, br)
    _flavor_cache = (value, now)
    return value


def wrap_remote_shell_for_exit_code(command: str) -> str:
    trimmed = re.sub(r";\s*$", "", (command or "").strip())
    return f"{{ {trimmed}; }}; echo {BRIDGE_EXIT_MARKER}$?"


def parse_wrapped_remote_result(output: str) -> Tuple[str, Optional[int]]:
    lines = (output or "").splitlines()
    exit_code: Optional[int] = None
    kept: List[str] = []
    for line in lines:
        m = re.match(r"^TAHP_BRIDGE_EXIT:(\d+)$", line.strip())
        if m:
            exit_code = int(m.group(1))
            continue
        kept.append(line)
    text = "\n".join(kept).rstrip("\n")
    return text, exit_code


def parse_json_loose(text: str) -> Optional[Dict[str, Any]]:
    trimmed = (text or "").strip()
    if not trimmed:
        return None
    try:
        parsed = json.loads(trimmed)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        start = trimmed.find("{")
        end = trimmed.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(trimmed[start : end + 1])
                return parsed if isinstance(parsed, dict) else None
            except Exception:
                return None
    return None


def asf_bridge_wait_sec(timeout_sec: float) -> int:
    return min(8, max(1, int(timeout_sec or 1)))


def asf_bridge_cli_timeout_sec(wait_sec: int) -> float:
    wait = max(1, int(wait_sec or 1))
    return float(wait + 90)


def is_transient_asf_bridge_failure(text: str) -> bool:
    return bool(
        re.search(
            r"BRIDGE_CMD_FAILED|zellij timed out|list-panes|host CLI timeout|timed out",
            text or "",
            re.I,
        )
    )


def _asf_sessions(parsed: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not parsed:
        return []
    raw = parsed.get("sessions")
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            session = int(item.get("session"))
        except Exception:
            continue
        if session <= 0:
            continue
        out.append(
            {
                "session": session,
                "phase": str(item.get("phase") or ""),
                "message": str(item.get("message") or ""),
            }
        )
    return out


def pick_asf_up_session(slots: List[Dict[str, Any]], mux_names: Optional[List[str]] = None) -> Optional[int]:
    ready = next((s for s in slots if s.get("phase") == "ready"), None)
    if ready:
        return int(ready["session"])
    blocked = set()
    for name in mux_names or []:
        m = re.match(r"^agent_session(\d+)$", str(name or ""), re.I)
        if m:
            blocked.add(int(m.group(1)))
    for s in slots:
        if re.search(r"zellij timed out|list-panes", str(s.get("message") or ""), re.I):
            blocked.add(int(s["session"]))
    for n in range(1, 5):
        if n not in blocked:
            return n
    return None


def list_asf_bridge_sessions(log: LogFn = _noop_log) -> List[Dict[str, Any]]:
    result = run_cli(["--json", "bridge", "ls"], timeout=30, log=log)
    parsed = parse_json_loose(result.stdout) or parse_json_loose(result.stderr)
    return _asf_sessions(parsed)


def asf_zellij_missing_from_doctor(parsed: Optional[Dict[str, Any]]) -> bool:
    if not parsed:
        return True
    tools = parsed.get("tools")
    if not isinstance(tools, list):
        return True
    zellij = next(
        (
            t
            for t in tools
            if isinstance(t, dict) and str(t.get("name") or "").lower() == "zellij"
        ),
        None,
    )
    if not zellij:
        return True
    return zellij.get("ok") is not True


def ensure_asf_zellij_installed(log: LogFn = _noop_log) -> None:
    result = run_cli(["--json", "bridge", "doctor"], timeout=45, log=log)
    parsed = parse_json_loose(result.stdout) or parse_json_loose(result.stderr)
    if not asf_zellij_missing_from_doctor(parsed):
        return
    log("Zellij 未安装，自动执行 asf --json bridge setup…")
    run_cli(["--json", "bridge", "setup"], timeout=180, log=log)


def ensure_asf_bridge_session(log: LogFn = _noop_log) -> int:
    global _asf_session
    ensure_asf_zellij_installed(log=log)
    slots = list_asf_bridge_sessions(log=log)
    ready = next((s for s in slots if s.get("phase") == "ready"), None)
    if ready:
        _asf_session = int(ready["session"])
        log(f"ASF Bridge session ready: {_asf_session}")
        return _asf_session

    session = pick_asf_up_session(slots) or 1
    log(f"ASF Bridge no ready session; claiming session {session} via bridge up…")
    result = run_cli(
        ["--json", "bridge", "up", "--session", str(session)],
        timeout=180,
        log=log,
    )
    parsed = parse_json_loose(result.stdout) or parse_json_loose(result.stderr)
    phase = str((parsed or {}).get("phase") or "")
    up_session = (parsed or {}).get("session")
    try:
        up_n = int(up_session) if up_session is not None else session
    except Exception:
        up_n = session
    if phase == "ready" or (parsed and str(parsed.get("status", "")).lower() == "ok" and not parsed.get("error_code")):
        # Re-list to confirm ready
        slots2 = list_asf_bridge_sessions(log=log)
        ready2 = next((s for s in slots2 if s.get("phase") == "ready"), None)
        if ready2:
            _asf_session = int(ready2["session"])
            return _asf_session
        _asf_session = up_n
        return _asf_session

    # Fallback: any ready after up attempt
    slots3 = list_asf_bridge_sessions(log=log)
    ready3 = next((s for s in slots3 if s.get("phase") == "ready"), None)
    if ready3:
        _asf_session = int(ready3["session"])
        return _asf_session

    err = (parsed or {}).get("message") or (result.stderr or result.stdout or "bridge up failed")
    raise RuntimeError(f"ASF Bridge up failed: {err}")


def _asf_failure_message(parsed: Dict[str, Any], stderr: str = "") -> str:
    parts = [
        str(parsed.get("error_code") or "").strip(),
        str(parsed.get("error") or "").strip(),
        str(parsed.get("message") or "").strip(),
        (stderr or "").strip(),
    ]
    return " ".join(p for p in parts if p).strip() or "asf bridge error"


def _make_wrapper(returncode: int, stdout: str, stderr: str) -> Any:
    wrapper = type("", (), {})()
    wrapper.returncode = returncode
    wrapper.stdout = stdout or ""
    wrapper.stderr = stderr or ""
    return wrapper


def _run_legacy_bridge_exec(
    remote_cmd: str,
    *,
    timeout_sec: float,
    log: LogFn,
) -> Any:
    args = [
        "--json",
        "remote-runner",
        "bridge-exec",
        "--i-understand-this-runs-raw-shell",
        "--timeout",
        str(int(max(1, timeout_sec))),
        "--command",
        remote_cmd,
    ]
    log(
        "Running remote command: "
        f"… remote-runner bridge-exec --command {remote_cmd[:120]}{'…' if len(remote_cmd) > 120 else ''}"
    )
    result = run_cli(args, timeout=timeout_sec + 60, log=log)
    parsed = parse_json_loose(result.stdout)
    if not parsed:
        return result
    status = str(parsed.get("status") or "unknown")
    exit_code = parsed.get("exit_code")
    if exit_code is None:
        exit_code = 1 if status == "error" else 0
    wrapper = _make_wrapper(int(exit_code), str(parsed.get("output") or ""), result.stderr or "")
    # Attach harness envelope fields for callers that inspect logs via run_harness_command
    wrapper._harness_json = parsed
    wrapper._harness_raw_stderr = result.stderr or ""
    return wrapper


def _asf_bridge_cmd_once(
    session: int,
    wrapped: str,
    *,
    wait_sec: int,
    timeout_sec: float,
    log: LogFn,
) -> Any:
    local_timeout = asf_bridge_cli_timeout_sec(wait_sec)
    args = [
        "--json",
        "bridge",
        "cmd",
        "--session",
        str(session),
        "--wait",
        str(wait_sec),
        "--lines",
        "200",
        wrapped,
    ]
    log(
        f"Running remote command: … bridge cmd --session {session} --wait {wait_sec} "
        f"{wrapped[:100]}{'…' if len(wrapped) > 100 else ''}"
    )
    try:
        result = run_cli(args, timeout=local_timeout, log=log)
    except subprocess.TimeoutExpired as exc:
        return _make_wrapper(1, "", f"host CLI timeout after {int(local_timeout)}s: {exc}")

    parsed = parse_json_loose(result.stdout) or parse_json_loose(result.stderr)
    if not parsed:
        return _make_wrapper(
            1,
            result.stdout or "",
            f"invalid asf bridge json: {(result.stderr or result.stdout or '(empty)').strip()}",
        )

    if str(parsed.get("status", "")).lower() == "error" or parsed.get("error_code"):
        fail = _asf_failure_message(parsed, result.stderr or "")
        out = str(parsed.get("output") if parsed.get("output") is not None else (result.stdout or ""))
        wrapper = _make_wrapper(1, out, fail)
        wrapper._harness_json = {
            "status": "error",
            "exit_code": -1,
            "output": out,
            "error": fail,
            "error_code": parsed.get("error_code"),
        }
        return wrapper

    output = str(parsed.get("output") or "")
    complete = parsed.get("complete") is not False
    if not complete and BRIDGE_EXIT_MARKER not in output:
        deadline = time.time() + max(1.0, float(timeout_sec))
        while time.time() < deadline:
            time.sleep(2)
            read = run_cli(
                ["--json", "bridge", "read", "--session", str(session), "--lines", "400"],
                timeout=30,
                log=log,
            )
            rp = parse_json_loose(read.stdout) or parse_json_loose(read.stderr)
            if rp and (str(rp.get("status", "")).lower() == "error" or rp.get("error_code")):
                fail = _asf_failure_message(rp, read.stderr or "")
                wrapper = _make_wrapper(1, str(rp.get("output") or output), fail)
                wrapper._harness_json = {
                    "status": "error",
                    "exit_code": -1,
                    "output": wrapper.stdout,
                    "error": fail,
                }
                return wrapper
            if rp and rp.get("output") is not None:
                output = str(rp.get("output"))
            if BRIDGE_EXIT_MARKER in output:
                complete = True
                break

    cleaned, exit_code = parse_wrapped_remote_result(output)
    if exit_code is None and not complete:
        wrapper = _make_wrapper(1, cleaned, "asf bridge cmd 未完成")
        wrapper._harness_json = {"status": "error", "exit_code": -1, "output": cleaned, "error": wrapper.stderr}
        return wrapper
    code = 0 if exit_code is None else int(exit_code)
    wrapper = _make_wrapper(code, cleaned, result.stderr or "")
    wrapper._harness_json = {
        "status": str(parsed.get("status") or ("ok" if complete else "error")),
        "exit_code": code,
        "output": cleaned,
    }
    return wrapper


def _run_asf_bridge_cmd(
    remote_cmd: str,
    *,
    timeout_sec: float,
    log: LogFn,
    max_retries: int = 3,
) -> Any:
    session = ensure_asf_bridge_session(log=log)
    wrapped = wrap_remote_shell_for_exit_code(remote_cmd)
    wait_sec = asf_bridge_wait_sec(timeout_sec)
    last = None
    for attempt in range(1, max_retries + 1):
        result = _asf_bridge_cmd_once(
            session,
            wrapped,
            wait_sec=wait_sec,
            timeout_sec=timeout_sec,
            log=log,
        )
        blob = f"{getattr(result, 'stderr', '')}\n{getattr(result, 'stdout', '')}"
        if not is_transient_asf_bridge_failure(blob):
            return result
        last = result
        log(f"ASF Bridge 瞬时失败 ({attempt}/{max_retries}): {(result.stderr or 'zellij timeout')[:200]}，同 session 重试")
        try:
            run_cli(
                ["--json", "bridge", "interrupt", "--session", str(session)],
                timeout=15,
                log=log,
            )
        except Exception:
            pass
        time.sleep(1.5)
    return last or _make_wrapper(1, "", "ASF Bridge cmd failed")


def run_remote_shell(
    remote_cmd: str,
    *,
    timeout_sec: float = 300,
    max_retries: int = 3,
    log: Optional[LogFn] = None,
) -> Any:
    """Execute remote shell; auto-select legacy bridge-exec or asf bridge cmd."""
    log = log or _noop_log
    flavor = detect_flavor()
    log(f"Remote exec flavor: {flavor}")
    if flavor == FLAVOR_LEGACY:
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                result = _run_legacy_bridge_exec(remote_cmd, timeout_sec=timeout_sec, log=log)
                hj = getattr(result, "_harness_json", None)
                if isinstance(hj, dict) and str(hj.get("status")) == "error":
                    err = str(hj.get("error") or hj.get("message") or "unknown_error")
                    last_error = err
                    lower = err.lower()
                    is_bridge_like = any(
                        tok in lower
                        for tok in (
                            "bridge",
                            "timeout",
                            "timed out",
                            "not ready",
                            "otp",
                            "qizhi",
                            "bastion",
                        )
                    )
                    if attempt < max_retries and is_bridge_like:
                        delay = 60 - (attempt * 10)
                        log(f"Bridge-channel error detected (attempt {attempt}/{max_retries}): {err}")
                        log(f"Retrying in {delay} seconds (OTP may be required)...")
                        time.sleep(delay)
                        continue
                    return _make_wrapper(1, "", err)
                return result
            except subprocess.TimeoutExpired:
                last_error = f"Command timed out after {int(timeout_sec)}s (attempt {attempt}/{max_retries})"
                log(last_error)
                if attempt < max_retries:
                    delay = 60 - (attempt * 10)
                    log(f"Retrying in {delay} seconds (OTP may be required)...")
                    time.sleep(delay)
                    continue
            except Exception as exc:
                last_error = str(exc)
                log(f"Error running harness command: {exc}")
                if attempt < max_retries:
                    delay = 60 - (attempt * 10)
                    log(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                    continue
        return _make_wrapper(1, "", last_error or "Max retries exceeded")

    if flavor == FLAVOR_ASF:
        try:
            return _run_asf_bridge_cmd(
                remote_cmd,
                timeout_sec=timeout_sec,
                log=log,
                max_retries=max_retries,
            )
        except Exception as exc:
            log(f"ASF Bridge exec failed: {exc}")
            return _make_wrapper(1, "", str(exc))

    return _make_wrapper(
        1,
        "",
        "本机 CLI 无 remote-runner bridge-exec，也无 asf bridge cmd，无法执行远程命令",
    )


def probe_bridge(log: Optional[LogFn] = None) -> bool:
    """Informational connectivity probe."""
    log = log or _noop_log
    flavor = detect_flavor(refresh=True)
    log(f"  Detected remote exec flavor: {flavor}")
    if flavor == FLAVOR_UNAVAILABLE:
        log("  Neither legacy bridge-exec nor asf bridge cmd is available")
        return False
    if flavor == FLAVOR_ASF:
        try:
            slots = list_asf_bridge_sessions(log=log)
            ready = next((s for s in slots if s.get("phase") == "ready"), None)
            if ready:
                log(f"  ASF Bridge ready session={ready['session']}")
                return True
            log("  ASF Bridge has no ready session yet (will try bridge up on first remote cmd)")
            # Soft-ok: first real command will bridge up
            return True
        except Exception as exc:
            log(f"  ASF Bridge probe exception: {exc}")
            return False

    # legacy
    result = run_remote_shell('echo bridge_check', timeout_sec=15, max_retries=1, log=log)
    ok = int(getattr(result, "returncode", 1) or 0) == 0 and "bridge_check" in (result.stdout or "")
    log(f"  Legacy bridge probe returncode={result.returncode} ok={ok}")
    return ok
