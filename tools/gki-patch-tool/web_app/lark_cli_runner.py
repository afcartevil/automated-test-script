"""Run lark-cli and unwrap success/error envelopes."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


class LarkCliError(RuntimeError):
    pass


def lark_cli_available() -> bool:
    return bool(_lark_executable())


def _lark_executable() -> str:
    for name in ("lark-cli.cmd", "lark-cli.CMD", "lark-cli", "lark-cli.ps1"):
        found = shutil.which(name)
        if found:
            return found
    return ""


def _lark_command() -> List[str]:
    """Prefer invoking the Node entrypoint so stdin/JSON args work on Windows."""
    cmd_path = _lark_executable()
    if cmd_path:
        run_js = Path(cmd_path).resolve().parent / "node_modules" / "@larksuite" / "cli" / "scripts" / "run.js"
        node = shutil.which("node")
        if run_js.is_file() and node:
            return [node, str(run_js)]
        if cmd_path:
            return [cmd_path]
    return ["lark-cli"]


def ensure_lark_user_auth() -> Dict[str, Any]:
    if not lark_cli_available():
        raise LarkCliError("未找到 lark-cli，请先安装：npx @larksuite/cli@latest install")
    data = run_lark(["auth", "status", "--verify"])
    status = str(data.get("tokenStatus") or "").lower()
    verified = data.get("verified")
    if verified is False or status not in ("", "valid", "ok"):
        raise LarkCliError("lark-cli 未授权或登录已过期，请先执行 lark-cli auth login")
    if data.get("identity") not in (None, "", "user", "auto"):
        # still OK if user token is valid
        pass
    if status and status not in ("valid", "ok"):
        raise LarkCliError("lark-cli 用户登录无效，请重新授权")
    return data


def write_lark_json(obj: Any, prefix: str = "payload") -> str:
    """Write JSON for lark-cli @file flags; returns a cwd-relative posix path."""
    from web_app.app_paths import outputs_dir

    folder = outputs_dir("lark_tmp")
    path = folder / f"{prefix}-{uuid.uuid4().hex[:10]}.json"
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    try:
        rel = path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        from web_app.app_paths import install_root
        rel = path.resolve().relative_to(install_root().resolve())
    return "./" + rel.as_posix()


def run_lark(
    args: List[str],
    *,
    stdin_obj: Any = None,
    json_flag: str = "",
    timeout: int = 180,
) -> Dict[str, Any]:
    cmd = _lark_command()
    if not cmd:
        raise LarkCliError("未找到 lark-cli，请先安装：npx @larksuite/cli@latest install")
    args = list(args)
    payload = None
    if stdin_obj is not None:
        payload = json.dumps(stdin_obj, ensure_ascii=False)
        if "-" not in args:
            if json_flag:
                args.extend([json_flag, "-"])
            else:
                args.append("-")
    cmd = [*cmd, *args]
    run_kw: Dict[str, Any] = {
        "input": payload,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
    }
    try:
        proc = subprocess.run(cmd, **run_kw)
    except FileNotFoundError as exc:
        raise LarkCliError("未找到 lark-cli，请先安装：npx @larksuite/cli@latest install") from exc
    except subprocess.TimeoutExpired as exc:
        raise LarkCliError(f"lark-cli 超时: {' '.join(args)}") from exc

    parsed = _parse_json_output(proc.stdout) or _parse_json_output(proc.stderr)
    if proc.returncode != 0:
        message = _error_message(parsed) or (proc.stderr or proc.stdout or "").strip() or f"lark-cli 失败 ({proc.returncode})"
        raise LarkCliError(message)
    return _unwrap(parsed)


def _parse_json_output(raw: str) -> Optional[Dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    # CLI may print logs before JSON
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _unwrap(parsed: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not parsed:
        return {}
    if parsed.get("ok") is False:
        raise LarkCliError(_error_message(parsed))
    if parsed.get("ok") is True:
        data = parsed.get("data")
        return data if isinstance(data, dict) else parsed
    if "code" in parsed and parsed.get("code") not in (0, "0", None):
        raise LarkCliError(_error_message(parsed))
    data = parsed.get("data")
    if isinstance(data, dict):
        return data
    return parsed


def _error_message(parsed: Optional[Dict[str, Any]]) -> str:
    if not parsed:
        return "lark-cli 调用失败"
    err = parsed.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("hint") or err)
    if parsed.get("msg") and parsed.get("code") not in (0, "0", None):
        return str(parsed.get("msg"))
    if parsed.get("message"):
        return str(parsed["message"])
    return json.dumps(parsed, ensure_ascii=False)
