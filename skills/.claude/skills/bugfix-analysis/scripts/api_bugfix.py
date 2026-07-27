#!/usr/bin/env python3
"""Bugfix AI 分析平台 CLI — 对接 chat.transsion.com/bugfix API v1."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Optional

DEFAULT_BASE_URL = "https://chat.transsion.com/bugfix"
CONFIG_PATH = Path.home() / ".bugfix_cli_config.json"
DEFAULT_ANALYZE_TIMEOUT = 600
# 默认关闭登录；平台要求认证时执行 config set --auth-required true
DEFAULT_AUTH_REQUIRED = False


def ok(data: Any) -> Dict[str, Any]:
    return {"ok": True, "data": data}


def err(code: str, message: str, *, status: Optional[int] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"ok": False, "error": {"code": code, "message": message}}
    if status is not None:
        payload["error"]["http_status"] = status
    return payload


def load_config() -> Dict[str, Any]:
    bugtool_yaml = Path.home() / ".integration_bug_tool" / "env.yaml"
    if bugtool_yaml.is_file():
        try:
            import yaml  # type: ignore

            with bugtool_yaml.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            bugfix = data.get("bugfix") if isinstance(data, dict) else None
            if isinstance(bugfix, dict):
                merged = dict(bugfix)
                if merged.get("access_token") or (
                    merged.get("username") and merged.get("password")
                ):
                    return merged
        except Exception:
            pass

    if not CONFIG_PATH.exists():
        return {}
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(config: Dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def base_url(config: Dict[str, Any]) -> str:
    return str(config.get("base_url") or DEFAULT_BASE_URL).rstrip("/")


def auth_enabled(config: Dict[str, Any]) -> bool:
    if "auth_required" in config:
        return bool(config["auth_required"])
    return DEFAULT_AUTH_REQUIRED


def request_json(
    method: str,
    url: str,
    *,
    token: Optional[str] = None,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = 60,
) -> tuple[int, Any]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        raise ValueError(f"网络请求失败: {e.reason}") from e

    if not raw.strip():
        return status, None

    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, {"raw": raw}


def ensure_token(config: Dict[str, Any], *, force_login: bool = False) -> str:
    if not force_login and config.get("access_token"):
        return str(config["access_token"])
    username = str(config.get("username") or "").strip()
    password = str(config.get("password") or "")
    if not username or not password:
        raise ValueError(
            "未配置 access_token 或 username/password。"
            "请先执行 config set 或 login。"
        )
    status, payload = request_json(
        "POST",
        f"{base_url(config)}/api/v1/auth/login",
        body={"username": username, "password": password},
        timeout=60,
    )
    if status != 200 or not isinstance(payload, dict) or not payload.get("access_token"):
        detail = payload.get("detail") if isinstance(payload, dict) else payload
        raise ValueError(f"登录失败 (HTTP {status}): {detail}")

    config["access_token"] = payload["access_token"]
    config["token_type"] = payload.get("token_type", "bearer")
    save_config(config)
    return str(config["access_token"])


def resolve_token(config: Dict[str, Any], *, force_login: bool = False) -> Optional[str]:
    if not auth_enabled(config):
        manual = str(config.get("access_token") or "").strip()
        return manual or None
    return ensure_token(config, force_login=force_login)


def auth_request(
    config: Dict[str, Any],
    method: str,
    path: str,
    *,
    body: Optional[Dict[str, Any]] = None,
    query: Optional[Dict[str, Any]] = None,
    timeout: int = 60,
    retry_login: bool = True,
) -> tuple[int, Any]:
    token = resolve_token(config)
    url = f"{base_url(config)}{path}"
    if query:
        from urllib.parse import urlencode

        params = {k: v for k, v in query.items() if v is not None and v != ""}
        if params:
            url = f"{url}?{urlencode(params)}"

    status, payload = request_json(method, url, token=token, body=body, timeout=timeout)
    if (
        status == 401
        and auth_enabled(config)
        and retry_login
        and config.get("username")
        and config.get("password")
    ):
        token = ensure_token(config, force_login=True)
        status, payload = request_json(method, url, token=token, body=body, timeout=timeout)
    return status, payload


def write_markdown_if_requested(markdown: Optional[str], output_file: Optional[str]) -> Optional[str]:
    if not output_file or not markdown:
        return None
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return str(path.resolve())


def command_config_set(args: argparse.Namespace) -> Dict[str, Any]:
    config = load_config()
    if args.base_url:
        config["base_url"] = args.base_url.strip().rstrip("/")
    if args.username:
        config["username"] = args.username.strip()
    if args.password:
        config["password"] = args.password
    if args.access_token:
        config["access_token"] = args.access_token.strip()
    if args.auth_required is not None:
        config["auth_required"] = args.auth_required
    if not config:
        raise ValueError("至少提供一个配置项")
    save_config(config)
    return ok(
        {
            "config_path": str(CONFIG_PATH.resolve()),
            "message": "配置已保存",
            "auth_required": auth_enabled(config),
        }
    )


def command_config_show(_: argparse.Namespace) -> Dict[str, Any]:
    config = load_config()
    if not config:
        return err("CONFIG_NOT_FOUND", f"未找到配置文件: {CONFIG_PATH}")
    safe = dict(config)
    if safe.get("password"):
        safe["password"] = "******"
    if safe.get("access_token"):
        token = str(safe["access_token"])
        safe["access_token"] = token[:8] + "..." if len(token) > 8 else "******"
    safe["auth_required"] = auth_enabled(config)
    return ok({"config_path": str(CONFIG_PATH.resolve()), "config": safe})


def command_login(args: argparse.Namespace) -> Dict[str, Any]:
    config = load_config()
    if not auth_enabled(config):
        return err(
            "AUTH_DISABLED",
            "当前 auth_required=false，无需登录。"
            "启用认证：python scripts/api_bugfix.py config set --auth-required true",
        )
    if args.base_url:
        config["base_url"] = args.base_url.strip().rstrip("/")
    if args.username:
        config["username"] = args.username.strip()
    if args.password:
        config["password"] = args.password
    token = ensure_token(config, force_login=True)  # auth_enabled 已校验
    status, payload = auth_request(config, "GET", "/api/v1/users/me", retry_login=False)
    me = payload if status == 200 else None
    return ok(
        {
            "message": "登录成功",
            "token_preview": token[:8] + "...",
            "config_path": str(CONFIG_PATH.resolve()),
            "user": me,
        }
    )


def command_analyze(args: argparse.Namespace) -> Dict[str, Any]:
    config = load_config()
    body: Dict[str, Any] = {
        "jira_number": args.jira_number.strip(),
    }
    if args.gerrit_project is not None:
        body["gerrit_project"] = args.gerrit_project.strip()
    if args.branch is not None:
        body["branch"] = args.branch.strip()
    if args.keywords:
        body["keywords"] = args.keywords.strip()
    if args.code_root_relative is not None:
        body["code_root_relative"] = args.code_root_relative
    if args.business_type:
        body["business_type"] = args.business_type.strip()
    if args.auto_comment is not None:
        body["auto_comment"] = args.auto_comment
    if args.skip_if_marker_present is not None:
        body["skip_if_marker_present"] = args.skip_if_marker_present
    if args.comment_marker:
        body["comment_marker"] = args.comment_marker.strip()

    status, payload = auth_request(
        config,
        "POST",
        "/api/v1/jira-mcp/analyze",
        body=body,
        timeout=args.timeout,
    )
    if status != 200:
        detail = payload.get("detail") if isinstance(payload, dict) else payload
        return err("ANALYZE_FAILED", str(detail), status=status)

    markdown = payload.get("analysis_markdown") if isinstance(payload, dict) else None
    saved_path = write_markdown_if_requested(markdown, args.output_file)
    result: Dict[str, Any] = {"response": payload}
    if saved_path:
        result["report_file"] = saved_path
    return ok(result)


def command_get_progress(args: argparse.Namespace) -> Dict[str, Any]:
    config = load_config()
    query: Dict[str, Any] = {}
    if args.jira_issue_key:
        query["jira_issue_key"] = args.jira_issue_key.strip()
    if args.gerrit_project:
        query["gerrit_project"] = args.gerrit_project.strip()
    if args.gerrit_project_prefix:
        query["gerrit_project_prefix"] = args.gerrit_project_prefix.strip()
    if args.preview_chars is not None:
        query["preview_chars"] = args.preview_chars

    if not query.get("jira_issue_key") and not query.get("gerrit_project") and not query.get(
        "gerrit_project_prefix"
    ):
        raise ValueError(
            "至少提供 --jira-issue-key、--gerrit-project 或 --gerrit-project-prefix 之一"
        )

    status, payload = auth_request(
        config,
        "GET",
        "/api/v1/analysis-task-records",
        query=query,
        timeout=args.timeout,
    )
    if status != 200:
        detail = payload.get("detail") if isinstance(payload, dict) else payload
        return err("PROGRESS_QUERY_FAILED", str(detail), status=status)
    return ok({"records": payload})


def command_get_report(args: argparse.Namespace) -> Dict[str, Any]:
    config = load_config()
    record_id = int(args.record_id)
    status, payload = auth_request(
        config,
        "GET",
        f"/api/v1/analysis-task-records/{record_id}",
        timeout=args.timeout,
    )
    if status == 404:
        detail = payload.get("detail") if isinstance(payload, dict) else "记录不存在"
        return err("RECORD_NOT_FOUND", str(detail), status=status)
    if status != 200:
        detail = payload.get("detail") if isinstance(payload, dict) else payload
        return err("REPORT_QUERY_FAILED", str(detail), status=status)

    markdown = None
    process_markdown = None
    if isinstance(payload, dict):
        markdown = payload.get("analysis_markdown") or payload.get("markdown")
        process_markdown = payload.get("process_markdown")
    saved_path = write_markdown_if_requested(markdown, args.output_file)
    process_path = write_markdown_if_requested(process_markdown, args.output_process_file)
    result: Dict[str, Any] = {"record": payload}
    if saved_path:
        result["report_file"] = saved_path
    if process_path:
        result["process_file"] = process_path
    return ok(result)


def _optional_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes", "y"}:
        return True
    if lowered in {"false", "0", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"期望 true/false，收到: {value}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bugfix AI 分析平台 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    config_parser = sub.add_parser("config", help="配置 base_url / 凭据 / token")
    config_sub = config_parser.add_subparsers(dest="config_cmd", required=True)
    config_set = config_sub.add_parser("set", help="保存配置")
    config_set.add_argument("--base-url", help=f"API Base URL，默认 {DEFAULT_BASE_URL}")
    config_set.add_argument("--username", help="登录用户名")
    config_set.add_argument("--password", help="登录密码")
    config_set.add_argument("--access-token", help="直接设置 Bearer token（跳过 login）")
    config_set.add_argument(
        "--auth-required",
        type=_optional_bool,
        help=f"是否启用登录认证，true/false（默认 {str(DEFAULT_AUTH_REQUIRED).lower()}）",
    )
    config_sub.add_parser("show", help="显示当前配置（敏感字段脱敏）")

    login = sub.add_parser("login", help="用户登录并缓存 access_token")
    login.add_argument("--base-url", help="覆盖 base_url")
    login.add_argument("--username", help="覆盖用户名")
    login.add_argument("--password", help="覆盖密码")

    analyze = sub.add_parser("analyze", help="Jira 通用缺陷分析（同步，可能耗时数分钟）")
    analyze.add_argument("--jira-number", required=True, help="Jira 工单号，如 TOS163-123")
    analyze.add_argument(
        "--gerrit-project",
        default=None,
        help="Gerrit 工程路径；省略则服务端按工单关键词匹配 module_repo_mapping",
    )
    analyze.add_argument(
        "--branch",
        default=None,
        help="分支名；省略则传空串由服务端决定",
    )
    analyze.add_argument(
        "--keywords",
        help="关键词（英文逗号分隔），用于落库 mapping",
    )
    analyze.add_argument(
        "--business-type",
        choices=["communication", "stability", "general", "diruan"],
        help="业务类型：communication/stability/general/diruan；省略走原有路由",
    )
    analyze.add_argument("--code-root-relative", default=None, help="代码子目录（相对仓库根）；省略不传")
    analyze.add_argument(
        "--auto-comment",
        type=_optional_bool,
        help="是否自动写回 Jira 评论，true/false",
    )
    analyze.add_argument(
        "--skip-if-marker-present",
        type=_optional_bool,
        help="存在标记评论时跳过，true/false",
    )
    analyze.add_argument("--comment-marker", help="去重标记，默认 [AUTO-ANALYSIS]")
    analyze.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_ANALYZE_TIMEOUT,
        help=f"请求超时秒数，默认 {DEFAULT_ANALYZE_TIMEOUT}",
    )
    analyze.add_argument("--output-file", help="将 analysis_markdown 写入本地文件")

    progress = sub.add_parser("get-progress", help="查询分析进展（分析任务记录列表，仅预览）")
    progress.add_argument("--jira-issue-key", help="Jira 工单号")
    progress.add_argument("--gerrit-project", help="Gerrit 工程路径（精确匹配）")
    progress.add_argument("--gerrit-project-prefix", help="Gerrit 工程路径前缀")
    progress.add_argument(
        "--preview-chars",
        type=int,
        help="结果 Markdown 预览长度（0-8000），默认 500",
    )
    progress.add_argument("--timeout", type=int, default=60, help="请求超时秒数")

    report = sub.add_parser("get-report", help="获取分析报告详情（含结果与过程）")
    report.add_argument("--record-id", required=True, help="分析记录 ID")
    report.add_argument("--timeout", type=int, default=60, help="请求超时秒数")
    report.add_argument("--output-file", help="将 analysis_markdown（结果）写入本地文件")
    report.add_argument("--output-process-file", help="将 process_markdown（过程）写入本地文件")

    return parser


CommandHandler = Callable[[argparse.Namespace], Dict[str, Any]]

COMMANDS: Dict[str, CommandHandler] = {
    "login": command_login,
    "analyze": command_analyze,
    "get-progress": command_get_progress,
    "get-report": command_get_report,
}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "config":
            if args.config_cmd == "set":
                result = command_config_set(args)
            elif args.config_cmd == "show":
                result = command_config_show(args)
            else:
                raise ValueError("不支持的 config 子命令")
        else:
            handler = COMMANDS.get(args.command)
            if not handler:
                raise ValueError(f"不支持的命令: {args.command}")
            result = handler(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    except ValueError as e:
        print(json.dumps(err("INVALID_INPUT", str(e)), ensure_ascii=False, indent=2))
        return 2
    except Exception as e:
        print(json.dumps(err("UNEXPECTED_ERROR", str(e)), ensure_ascii=False, indent=2))
        return 99


if __name__ == "__main__":
    sys.exit(main())
