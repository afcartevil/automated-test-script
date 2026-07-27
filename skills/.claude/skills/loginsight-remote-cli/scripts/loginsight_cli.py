#!/usr/bin/env python3
"""LogInsight remote HTTP CLI (stdlib only). See ../SKILL.md."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = SKILL_ROOT / ".env"
CONFIG_PATH = SKILL_ROOT / ".loginsight_cli.json"
DEFAULT_BASE_URL = "https://chat.transsion.com/bugfix/stability-matrix-tools"


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _load_config() -> dict[str, Any]:
    if not CONFIG_PATH.is_file():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_config(data: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _cfg_get(key: str, default: str | None = None) -> str | None:
    env_key = key.upper()
    if os.environ.get(env_key):
        return os.environ[env_key]
    cfg = _load_config()
    val = cfg.get(key) or cfg.get(env_key)
    if val is None or str(val).strip() == "":
        return default
    return str(val).strip()


def base_url() -> str:
    url = (_cfg_get("base_url") or _cfg_get("BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    return url


def operator_user() -> str | None:
    return _cfg_get("operator_user") or _cfg_get("OPERATOR_USER") or _cfg_get("jiraUsername")


def operator_password() -> str | None:
    return (
        _cfg_get("operator_password")
        or _cfg_get("OPERATOR_PASSWORD")
        or _cfg_get("jiraPassword")
    )


def llm_api_key() -> str | None:
    return _cfg_get("llm_api_key") or _cfg_get("LLM_API_KEY")


def llm_provider() -> str:
    return (
        _cfg_get("llm_provider")
        or _cfg_get("LLM_PROVIDER")
        or "sw-aimodel"
    )


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    v = value.strip()
    if len(v) <= 8:
        return "****"
    return "****" + v[-4:]


def persist_local_state(cfg: dict[str, Any]) -> None:
    """Write .loginsight_cli.json + .env (gitignored). Never print secrets."""
    _save_config(cfg)
    lines = [
        f"BASE_URL={cfg.get('base_url', DEFAULT_BASE_URL)}",
        f"OPERATOR_USER={cfg.get('operator_user', '')}",
        f"OPERATOR_PASSWORD={cfg.get('operator_password', '')}",
        f"LLM_PROVIDER={cfg.get('llm_provider', 'sw-aimodel')}",
        f"LLM_API_KEY={cfg.get('llm_api_key', '')}",
    ]
    if cfg.get("llm_model"):
        lines.append(f"LLM_MODEL={cfg['llm_model']}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def emit(obj: Any, *, exit_code: int = 0) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))
    raise SystemExit(exit_code)


def fail(message: str, **extra: Any) -> None:
    body: dict[str, Any] = {"ok": False, "error": message}
    body.update(extra)
    emit(body, exit_code=1)


def http_json(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
    timeout: float = 120.0,
    expect_json: bool = True,
    raise_on_http_error: bool = True,
) -> tuple[int, Any, dict[str, str]]:
    url = base_url() + path
    if query:
        q = {k: str(v) for k, v in query.items() if v is not None}
        url += "?" + urllib.parse.urlencode(q)
    data = None
    headers = {"Accept": "application/json, text/html, */*"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        raw = e.read() if e.fp else b""
        status = e.code
        resp_headers = {k.lower(): v for k, v in (e.headers.items() if e.headers else [])}
        text = raw.decode("utf-8", errors="replace")
        parsed: Any
        try:
            parsed = json.loads(text) if text else None
        except json.JSONDecodeError:
            parsed = text
        if raise_on_http_error:
            fail(
                f"HTTP {status} for {method} {path}",
                status=status,
                url=url,
                body=parsed,
            )
        return status, parsed, resp_headers
    except urllib.error.URLError as e:
        if raise_on_http_error:
            fail(f"network error: {e.reason}", url=url)
        return 0, {"error": str(e.reason)}, {}
    text = raw.decode("utf-8", errors="replace")
    if not expect_json:
        return status, text, resp_headers
    if not text:
        return status, None, resp_headers
    try:
        return status, json.loads(text), resp_headers
    except json.JSONDecodeError:
        return status, text, resp_headers


def download_report_file(path: str) -> dict[str, Any]:
    """Download report; never raises SystemExit — returns ok/error dict."""
    url = base_url() + "/api/reports/file?" + urllib.parse.urlencode({"path": path})
    last_body = ""
    for attempt in range(1, 6):
        req = urllib.request.Request(url, headers={"Accept": "*/*"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=300.0) as resp:
                content = resp.read()
                return {
                    "ok": True,
                    "result_path": path,
                    "bytes": len(content),
                    "content": content,
                    "content_type": resp.headers.get("Content-Type", ""),
                    "browser_url": url,
                }
        except urllib.error.HTTPError as e:
            last_body = (e.read() if e.fp else b"")[:300].decode("utf-8", errors="replace")
            if e.code in (502, 503, 504) and attempt < 5:
                sys.stderr.write(f"[report] HTTP {e.code}, retry {attempt}/5 after 8s\n")
                time.sleep(8.0)
                continue
            return {
                "ok": False,
                "result_path": path,
                "browser_url": url,
                "error": f"HTTP {e.code}",
                "body": last_body,
            }
        except urllib.error.URLError as e:
            if attempt < 5:
                sys.stderr.write(f"[report] network error, retry {attempt}/5\n")
                time.sleep(8.0)
                continue
            return {
                "ok": False,
                "result_path": path,
                "browser_url": url,
                "error": str(e.reason),
            }
    return {"ok": False, "result_path": path, "browser_url": url, "error": "retries exhausted"}


def http_bytes(
    path: str,
    *,
    query: dict[str, Any] | None = None,
    timeout: float = 180.0,
    retries: int = 3,
    retry_sleep: float = 5.0,
) -> tuple[int, bytes, dict[str, str]]:
    url = base_url() + path
    if query:
        q = {k: str(v) for k, v in query.items() if v is not None}
        url += "?" + urllib.parse.urlencode(q)
    last_err: Any = None
    for attempt in range(1, max(1, retries) + 1):
        req = urllib.request.Request(url, headers={"Accept": "*/*"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read(), {k.lower(): v for k, v in resp.headers.items()}
        except urllib.error.HTTPError as e:
            raw = e.read() if e.fp else b""
            last_err = {
                "status": e.code,
                "body": raw[:500].decode("utf-8", errors="replace"),
            }
            if e.code in (502, 503, 504) and attempt < retries:
                sys.stderr.write(f"[report] HTTP {e.code}, retry {attempt}/{retries} after {retry_sleep}s\n")
                time.sleep(retry_sleep)
                continue
            fail(f"HTTP {e.code} downloading {path}", status=e.code, url=url, body=last_err.get("body"))
        except urllib.error.URLError as e:
            last_err = {"error": str(e.reason)}
            if attempt < retries:
                sys.stderr.write(f"[report] network error, retry {attempt}/{retries}\n")
                time.sleep(retry_sleep)
                continue
            fail(f"network error: {e.reason}", url=url)
    fail("download failed", url=url, last=last_err)
    return 0, b"", {}


def require_operator() -> tuple[str, str]:
    user = operator_user()
    password = operator_password()
    if not user or not password:
        fail(
            "missing operator credentials",
            hint="run: python scripts/loginsight_cli.py config set --operator-user U --operator-password P",
        )
    return user, password


def cmd_doctor(_: argparse.Namespace) -> None:
    checks: list[dict[str, Any]] = []
    bu = base_url()
    checks.append({"name": "base_url", "ok": bool(bu), "value": bu})
    user = operator_user()
    password = operator_password()
    checks.append(
        {
            "name": "operator",
            "ok": bool(user and password),
            "user": user or "",
            "password_set": bool(password),
        }
    )
    key = llm_api_key()
    checks.append(
        {
            "name": "local_llm_api_key",
            "ok": bool(key),
            "provider": llm_provider(),
            "masked": mask_secret(key),
            "hint": "run: credentials set --api-key <KEY>  (or config set --llm-api-key)",
        }
    )
    status, providers, _ = http_json(
        "GET", "/api/ai/providers", timeout=30.0, raise_on_http_error=False
    )
    net_ok = 200 <= int(status) < 400
    checks.append(
        {
            "name": "http_providers",
            "ok": net_ok,
            "status": status,
            "error": None if net_ok else providers,
        }
    )
    # Local credentials are enough to analyze; network probe is informational for doctor ok.
    ready = all(
        c.get("ok")
        for c in checks
        if c.get("name") in ("base_url", "operator", "local_llm_api_key", "http_providers")
    )
    emit(
        {
            "ok": ready,
            "base_url": bu,
            "checks": checks,
            "providers_sample": providers if isinstance(providers, (dict, list)) else None,
            "note": "No remote API lists per-operator keys; local_llm_api_key is the source of truth for this CLI.",
        },
        exit_code=0 if ready else 1,
    )


def cmd_config_show(_: argparse.Namespace) -> None:
    cfg = _load_config()
    emit(
        {
            "ok": True,
            "config_file": str(CONFIG_PATH),
            "env_file": str(ENV_PATH),
            "gitignored": [".env", ".loginsight_cli.json", "out/"],
            "effective": {
                "base_url": base_url(),
                "operator_user": operator_user() or "",
                "operator_password_set": bool(operator_password()),
                "llm_provider": llm_provider(),
                "llm_api_key_set": bool(llm_api_key()),
                "llm_api_key_masked": mask_secret(llm_api_key()),
                "llm_model": _cfg_get("llm_model") or _cfg_get("LLM_MODEL") or "",
            },
            "stored": {
                k: ("***" if "password" in k.lower() or "key" in k.lower() else v)
                for k, v in cfg.items()
            },
        }
    )


def cmd_config_set(args: argparse.Namespace) -> None:
    cfg = _load_config()
    mapping = {
        "base_url": args.base_url,
        "operator_user": args.operator_user,
        "operator_password": args.operator_password,
        "llm_provider": args.llm_provider,
        "llm_model": args.llm_model,
        "llm_api_key": args.llm_api_key,
    }
    for k, v in mapping.items():
        if v is not None and str(v).strip() != "":
            cfg[k] = str(v).strip()
    if not cfg.get("llm_provider"):
        cfg["llm_provider"] = "sw-aimodel"
    if not cfg.get("base_url"):
        cfg["base_url"] = DEFAULT_BASE_URL
    persist_local_state(cfg)
    emit(
        {
            "ok": True,
            "saved": str(CONFIG_PATH),
            "env": str(ENV_PATH),
            "operator_user": cfg.get("operator_user", ""),
            "llm_provider": cfg.get("llm_provider", ""),
            "llm_api_key_masked": mask_secret(cfg.get("llm_api_key")),
        }
    )


def cmd_model_overview(_: argparse.Namespace) -> None:
    status, data, _ = http_json("GET", "/api/ai/config/overview")
    emit({"ok": True, "status": status, "data": data})


def cmd_model_providers(_: argparse.Namespace) -> None:
    status, data, _ = http_json("GET", "/api/ai/providers")
    emit({"ok": True, "status": status, "data": data})


def cmd_model_keys(args: argparse.Namespace) -> None:
    user, _ = require_operator()
    keys = [k.strip() for k in (args.api_key or []) if k and str(k).strip()]
    if not keys:
        fail("provide at least one --api-key")
    body = {
        "operatorId": user,
        "providerKey": args.provider_key,
        "apiKeys": keys,
        "append": bool(args.append),
    }
    status, data, _ = http_json("POST", "/api/ai/config/providers/keys", body=body)
    emit({"ok": True, "status": status, "data": data})


def cmd_model_scene_bind(args: argparse.Namespace) -> None:
    body = {
        "bindings": [
            {
                "scenario": args.scenario,
                "providerKey": args.provider_key,
                "modelName": args.model_name,
                "apiKeyIndex": args.api_key_index,
            }
        ]
    }
    status, data, _ = http_json("PUT", "/api/ai/config/scene-bindings", body=body)
    emit({"ok": True, "status": status, "data": data})


def cmd_credentials_sync(args: argparse.Namespace) -> None:
    user, _ = require_operator()
    keys = [k.strip() for k in (args.api_key or []) if k and str(k).strip()]
    if not keys:
        local = llm_api_key()
        if local:
            keys = [local]
    if not keys:
        fail("provide --api-key or save one via credentials set")
    provider = args.provider_key or llm_provider()
    # Persist locally first so later analyze-jira works offline of sync
    cfg = _load_config()
    cfg["llm_api_key"] = keys[0]
    cfg["llm_provider"] = provider
    if user:
        cfg["operator_user"] = user
    if not cfg.get("base_url"):
        cfg["base_url"] = base_url()
    persist_local_state(cfg)
    body = {"jiraUsername": user, "providerKey": provider, "apiKeys": keys}
    status, data, _ = http_json("POST", "/api/ai/credentials/sync", body=body)
    emit(
        {
            "ok": True,
            "status": status,
            "data": data,
            "local": {
                "llm_provider": provider,
                "llm_api_key_masked": mask_secret(keys[0]),
                "saved": str(CONFIG_PATH),
            },
        }
    )


def cmd_credentials_set(args: argparse.Namespace) -> None:
    """Save LLM key locally (+ optional server sync). No remote per-user query API exists."""
    keys = [k.strip() for k in (args.api_key or []) if k and str(k).strip()]
    if not keys:
        fail("provide at least one --api-key")
    provider = args.provider_key or llm_provider()
    cfg = _load_config()
    if args.operator_user:
        cfg["operator_user"] = args.operator_user.strip()
    if args.operator_password:
        cfg["operator_password"] = args.operator_password
    cfg["llm_provider"] = provider
    cfg["llm_api_key"] = keys[0]
    if not cfg.get("base_url"):
        cfg["base_url"] = DEFAULT_BASE_URL
    persist_local_state(cfg)
    sync_result: Any = None
    if not args.local_only:
        user = operator_user()
        if user:
            status, sync_result, _ = http_json(
                "POST",
                "/api/ai/credentials/sync",
                body={"jiraUsername": user, "providerKey": provider, "apiKeys": keys},
                raise_on_http_error=False,
            )
            if int(status) >= 400:
                sync_result = {"ok": False, "status": status, "body": sync_result}
    emit(
        {
            "ok": True,
            "local": {
                "operator_user": operator_user() or "",
                "llm_provider": provider,
                "llm_api_key_masked": mask_secret(keys[0]),
                "files": [str(CONFIG_PATH), str(ENV_PATH)],
            },
            "server_sync": sync_result,
            "note": "Local files are gitignored. Next analyze-jira injects llmApiKey from local state.",
        }
    )


def cmd_credentials_status(_: argparse.Namespace) -> None:
    """
    There is NO API that returns 'keys configured for operator X'.
    Closest remote signal: GET /api/ai/config/overview (platform YAML / _legacy pool only).
    This command reports local saved state + that remote overview hasKey for sw-aimodel.
    """
    local = {
        "operator_user": operator_user() or "",
        "operator_password_set": bool(operator_password()),
        "llm_provider": llm_provider(),
        "llm_api_key_set": bool(llm_api_key()),
        "llm_api_key_masked": mask_secret(llm_api_key()),
        "config_file": str(CONFIG_PATH),
        "env_file": str(ENV_PATH),
        "ready_for_analyze": bool(operator_user() and operator_password() and llm_api_key()),
    }
    status, overview, _ = http_json(
        "GET", "/api/ai/config/overview", timeout=30.0, raise_on_http_error=False
    )
    remote: dict[str, Any] = {"reachable": 200 <= int(status) < 400, "status": status}
    if isinstance(overview, dict):
        providers = overview.get("providers") or []
        sw = next(
            (p for p in providers if isinstance(p, dict) and p.get("providerKey") == "sw-aimodel"),
            None,
        )
        remote["sw_aimodel"] = sw
        remote["note"] = (
            "overview.hasKey reflects server YAML/_legacy pool, NOT per-operator (qing.li3) keys"
        )
    emit(
        {
            "ok": local["ready_for_analyze"],
            "local": local,
            "remote_overview": remote,
            "no_per_user_key_query_api": True,
        },
        exit_code=0 if local["ready_for_analyze"] else 1,
    )


def cmd_account_jira_test(args: argparse.Namespace) -> None:
    user, password = require_operator()
    body = {
        "jiraUsername": user,
        "jiraPassword": password,
        "jiraBaseUrl": args.jira_base_url or "",
    }
    status, data, _ = http_json("POST", "/api/jira/test-connection", body=body)
    emit({"ok": True, "status": status, "data": data})


def _analyze_body(jira_id: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    user, password = require_operator()
    body: dict[str, Any] = {
        "jiraUsername": user,
        "jiraPassword": password,
        "jiraIds": [jira_id.strip().upper()],
        "llmProvider": llm_provider(),
    }
    model = _cfg_get("llm_model") or _cfg_get("LLM_MODEL")
    if model:
        body["llmModelName"] = model
    key = llm_api_key()
    if key:
        # Highest priority on server: request body keys beat YAML platform key
        body["llmApiKey"] = key
        body["llmApiKeys"] = [key]
    if extra:
        body.update(extra)
    return body


def cmd_analyze_jira(args: argparse.Namespace) -> None:
    if not args.jira_id:
        fail("missing --jira-id")
    extra: dict[str, Any] = {}
    if args.force_reanalyze:
        extra["forceReanalyze"] = True
    if args.issue_type:
        extra["issueType"] = args.issue_type
    status, data, _ = http_json("POST", "/api/analysis/jira/start", body=_analyze_body(args.jira_id, extra))
    emit({"ok": True, "status": status, "data": data})


def cmd_status(args: argparse.Namespace) -> None:
    if not args.task_id:
        fail("missing --task-id")
    query = {
        "taskId": args.task_id,
        "fromCursor": args.from_cursor,
        "fromEventCursor": args.from_event_cursor,
    }
    status, data, _ = http_json("GET", "/api/analysis/status", query=query)
    emit({"ok": True, "status": status, "data": data})


def _poll_until_done(task_id: str, *, interval: float, timeout: float, quiet: bool) -> dict[str, Any]:
    deadline = time.time() + timeout
    cursor = 0
    event_cursor = 0
    last: dict[str, Any] = {}
    while time.time() < deadline:
        _, data, _ = http_json(
            "GET",
            "/api/analysis/status",
            query={"taskId": task_id, "fromCursor": cursor, "fromEventCursor": event_cursor},
        )
        if not isinstance(data, dict):
            fail("unexpected status payload", body=data)
        last = data
        cursor = int(data.get("nextCursor") or cursor)
        event_cursor = int(data.get("nextEventCursor") or event_cursor)
        st = data.get("status")
        if not quiet:
            prog = data.get("progress")
            stage = data.get("stageText") or data.get("stageCode") or ""
            lines = data.get("incrementalLogLines") or []
            sys.stderr.write(f"[wait] status={st} progress={prog} stage={stage}\n")
            for line in lines[-5:]:
                sys.stderr.write(f"  | {line}\n")
            sys.stderr.flush()
        if st in ("done", "not_found"):
            return last
        time.sleep(max(1.0, interval))
    fail("wait timeout", task_id=task_id, last=last)


def cmd_wait(args: argparse.Namespace) -> None:
    if not args.task_id:
        fail("missing --task-id")
    last = _poll_until_done(
        args.task_id,
        interval=args.interval,
        timeout=args.timeout,
        quiet=args.quiet,
    )
    emit({"ok": last.get("status") == "done", "data": last}, exit_code=0 if last.get("status") == "done" else 1)


def _result_path_from_status(data: dict[str, Any]) -> str | None:
    result = data.get("result") or {}
    if isinstance(result, dict):
        path = result.get("resultPath")
        if path:
            return str(path)
    return None


def cmd_report(args: argparse.Namespace) -> None:
    task_id = args.task_id
    path = args.path
    if not path:
        if not task_id:
            fail("provide --path or --task-id")
        _, data, _ = http_json("GET", "/api/analysis/status", query={"taskId": task_id})
        if not isinstance(data, dict):
            fail("bad status", body=data)
        if data.get("status") != "done":
            fail("task not done yet", status=data.get("status"), hint="run wait first")
        path = _result_path_from_status(data)
        if not path:
            fail(
                "no resultPath (analysis may have failed)",
                result=data.get("result"),
            )
    out_dir = Path(args.out_dir or (SKILL_ROOT / "out"))
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(path.replace("\\", "/")).name or "report.html"
    if task_id:
        safe_name = f"{task_id}_{safe_name}"
    dest = out_dir / safe_name
    _, content, headers = http_bytes(
        "/api/reports/file", query={"path": path}, timeout=300.0, retries=5, retry_sleep=8.0
    )
    dest.write_bytes(content)
    emit(
        {
            "ok": True,
            "result_path": path,
            "saved_as": str(dest),
            "bytes": len(content),
            "content_type": headers.get("content-type", ""),
        }
    )


def cmd_run_jira(args: argparse.Namespace) -> None:
    if not args.jira_id:
        fail("missing --jira-id")
    extra: dict[str, Any] = {}
    if args.force_reanalyze:
        extra["forceReanalyze"] = True
    if args.issue_type:
        extra["issueType"] = args.issue_type
    status, start, _ = http_json("POST", "/api/analysis/jira/start", body=_analyze_body(args.jira_id, extra))
    if not isinstance(start, dict) or not start.get("taskId"):
        fail("analyze-jira did not return taskId", status=status, body=start)
    task_id = str(start["taskId"])
    sys.stderr.write(f"[run-jira] started taskId={task_id}\n")
    last = _poll_until_done(
        task_id,
        interval=args.interval,
        timeout=args.timeout,
        quiet=args.quiet,
    )
    result = last.get("result") if isinstance(last.get("result"), dict) else {}
    success = bool(result.get("success")) if result else False
    path = _result_path_from_status(last)
    report_info: dict[str, Any] | None = None
    if path:
        out_dir = Path(args.out_dir or (SKILL_ROOT / "out"))
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{task_id}_{Path(path.replace(chr(92), '/')).name or 'report.html'}"
        dl = download_report_file(path)
        if dl.get("ok"):
            dest.write_bytes(dl["content"])
            report_info = {
                "result_path": path,
                "saved_as": str(dest),
                "bytes": dl["bytes"],
                "content_type": dl.get("content_type", ""),
                "browser_url": dl.get("browser_url"),
            }
        else:
            report_info = {
                "result_path": path,
                "browser_url": dl.get("browser_url"),
                "download_error": dl.get("error"),
            }
    emit(
        {
            "ok": bool(success),
            "task_id": task_id,
            "session_id": start.get("sessionId") or last.get("sessionId"),
            "jira_id": args.jira_id.strip().upper(),
            "final_status": last.get("status"),
            "stage_text": last.get("stageText"),
            "progress": last.get("progress"),
            "result": result,
            "report": report_info,
            "report_download_ok": bool(report_info and report_info.get("saved_as")),
            "log_tail": (last.get("incrementalLogLines") or last.get("logLines") or [])[-30:],
        },
        exit_code=0 if success else 1,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="loginsight_cli", description="LogInsight remote CLI")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Check config + reachability").set_defaults(func=cmd_doctor)

    cfg = sub.add_parser("config", help="Show/set local config")
    cfg_sub = cfg.add_subparsers(dest="config_cmd", required=True)
    cfg_sub.add_parser("show").set_defaults(func=cmd_config_show)
    s = cfg_sub.add_parser("set")
    s.add_argument("--base-url")
    s.add_argument("--operator-user")
    s.add_argument("--operator-password")
    s.add_argument("--llm-provider")
    s.add_argument("--llm-model")
    s.add_argument("--llm-api-key")
    s.set_defaults(func=cmd_config_set)

    model = sub.add_parser("model", help="LLM config APIs")
    model_sub = model.add_subparsers(dest="model_cmd", required=True)
    model_sub.add_parser("overview").set_defaults(func=cmd_model_overview)
    model_sub.add_parser("providers").set_defaults(func=cmd_model_providers)
    mk = model_sub.add_parser("keys")
    mk.add_argument("--provider-key", required=True)
    mk.add_argument("--api-key", action="append", default=[])
    mk.add_argument("--append", action="store_true")
    mk.set_defaults(func=cmd_model_keys)
    mb = model_sub.add_parser("scene-bind")
    mb.add_argument("--scenario", required=True)
    mb.add_argument("--provider-key", required=True)
    mb.add_argument("--model-name", required=True)
    mb.add_argument("--api-key-index", type=int, default=None)
    mb.set_defaults(func=cmd_model_scene_bind)

    cred = sub.add_parser("credentials", help="Local + optional server LLM key state")
    cred_sub = cred.add_subparsers(dest="cred_cmd", required=True)
    cs = cred_sub.add_parser("sync", help="Sync keys to server and save locally")
    cs.add_argument("--provider-key", default="sw-aimodel")
    cs.add_argument("--api-key", action="append", default=[])
    cs.set_defaults(func=cmd_credentials_sync)
    cset = cred_sub.add_parser("set", help="Save LLM key locally (gitignored); sync unless --local-only")
    cset.add_argument("--provider-key", default="sw-aimodel")
    cset.add_argument("--api-key", action="append", default=[])
    cset.add_argument("--operator-user")
    cset.add_argument("--operator-password")
    cset.add_argument("--local-only", action="store_true")
    cset.set_defaults(func=cmd_credentials_set)
    cred_sub.add_parser(
        "status",
        help="Show local key state + remote overview (no per-user key query API)",
    ).set_defaults(func=cmd_credentials_status)

    acct = sub.add_parser("account", help="Account / Jira probes")
    acct_sub = acct.add_subparsers(dest="acct_cmd", required=True)
    jt = acct_sub.add_parser("jira-test")
    jt.add_argument("--jira-base-url", default="")
    jt.set_defaults(func=cmd_account_jira_test)

    aj = sub.add_parser("analyze-jira", help="POST /api/analysis/jira/start")
    aj.add_argument("--jira-id", required=True)
    aj.add_argument("--force-reanalyze", action="store_true")
    aj.add_argument("--issue-type", default="")
    aj.set_defaults(func=cmd_analyze_jira)

    st = sub.add_parser("status", help="GET /api/analysis/status")
    st.add_argument("--task-id", required=True)
    st.add_argument("--from-cursor", type=int, default=0)
    st.add_argument("--from-event-cursor", type=int, default=0)
    st.set_defaults(func=cmd_status)

    wt = sub.add_parser("wait", help="Poll status until done")
    wt.add_argument("--task-id", required=True)
    wt.add_argument("--interval", type=float, default=5.0)
    wt.add_argument("--timeout", type=float, default=3600.0)
    wt.add_argument("--quiet", action="store_true")
    wt.set_defaults(func=cmd_wait)

    rp = sub.add_parser("report", help="Download report HTML")
    rp.add_argument("--task-id")
    rp.add_argument("--path")
    rp.add_argument("--out-dir")
    rp.set_defaults(func=cmd_report)

    run = sub.add_parser("run-jira", help="Start + wait + download report")
    run.add_argument("--jira-id", required=True)
    run.add_argument("--force-reanalyze", action="store_true")
    run.add_argument("--issue-type", default="")
    run.add_argument("--interval", type=float, default=5.0)
    run.add_argument("--timeout", type=float, default=3600.0)
    run.add_argument("--out-dir")
    run.add_argument("--quiet", action="store_true")
    run.set_defaults(func=cmd_run_jira)

    return p


def main(argv: list[str] | None = None) -> None:
    _load_dotenv(ENV_PATH)
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
