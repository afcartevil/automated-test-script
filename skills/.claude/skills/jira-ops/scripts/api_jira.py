import argparse
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import unquote, urlparse

from jira import JIRA
from jira.exceptions import JIRAError

_SCRIPTS_DIR = Path(__file__).resolve().parent
_SKILL_ROOT = _SCRIPTS_DIR.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from log_download.issue_text import build_issue_log_text  # noqa: E402
from log_download.env_config import (  # noqa: E402
    run_setup_check,
    set_env_pairs,
    show_env,
    validate_network_servers_json,
)
from log_download.orchestrator import (  # noqa: E402
    ALL_CHANNELS,
    download_classified_urls,
    load_optional_env,
)
from log_download.recursive_extract import extract_directories  # noqa: E402
from log_download.url_classifier import extract_and_classify_urls  # noqa: E402


CONFIG_PATH = Path.home() / ".jira_cli_config.json"
DEFAULT_DOWNLOAD_DIR = Path.cwd() / "jira_attachments"
ISSUE_ID_PATTERN = re.compile(r"[A-Z][A-Z0-9]+-\d+")
UNC_PATH_PATTERN = re.compile(r"\\\\[^\s\]\)>,]+")
HTTP_URL_PATTERN = re.compile(r"https?://[^\s\]\)>\",|]+", re.IGNORECASE)
LOG_URL_HINTS = (".zip", ".gz", ".tgz", ".tar", ".log", "/log", "fanslog", "taglog", "bugreport")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")
DOWNLOAD_USER_AGENT = "jira-ops-cli/1.1"


def load_config() -> Dict[str, str]:
    """Jira credentials: bugtool yaml → ~/.jira_cli_config.json → jira-ops/.env (JIRA_*)."""
    load_optional_env(_SKILL_ROOT)
    config: Dict[str, str] = {}

    bugtool_yaml = Path.home() / ".integration_bug_tool" / "env.yaml"
    if bugtool_yaml.is_file():
        try:
            import yaml  # type: ignore

            with bugtool_yaml.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            jira = data.get("jira") if isinstance(data, dict) else None
            if isinstance(jira, dict) and jira.get("user") and jira.get("password"):
                config = {
                    "server": str(jira.get("server", "")).strip(),
                    "user": str(jira.get("user", "")).strip(),
                    "password": str(jira.get("password", "")),
                }
        except Exception:
            pass

    if not config and CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                config = data
        except (json.JSONDecodeError, OSError):
            pass

    # Supplement or fallback from jira-ops/.env (same keys as modem-analysis-local)
    if not config.get("server") and os.environ.get("JIRA_SERVER"):
        config["server"] = os.environ.get("JIRA_SERVER", "").strip()
    if not config.get("user") and os.environ.get("JIRA_USERNAME"):
        config["user"] = os.environ.get("JIRA_USERNAME", "").strip()
    if not config.get("password") and os.environ.get("JIRA_PASSWORD"):
        config["password"] = os.environ.get("JIRA_PASSWORD", "")

    return config


def save_config(config: Dict[str, str]) -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def normalize_issue_key(issue_ref: str) -> str:
    issue_ref = (issue_ref or "").strip()
    if not issue_ref:
        raise ValueError("issue_id 不能为空")

    match = ISSUE_ID_PATTERN.search(issue_ref.upper())
    if not match:
        raise ValueError(f"无法从输入中解析 Jira ID: {issue_ref}")
    return match.group(0)


def ok(data: Any) -> Dict[str, Any]:
    return {"ok": True, "data": data}


def err(code: str, message: str) -> Dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}


def extract_http_urls(text: str) -> List[str]:
    seen = set()
    urls: List[str] = []
    for raw in HTTP_URL_PATTERN.findall(text or ""):
        url = raw.rstrip(".,;")
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def is_likely_log_url(url: str) -> bool:
    lower = url.lower()
    path = urlparse(lower).path
    if any(path.endswith(ext) for ext in IMAGE_EXTS):
        return False
    return any(hint in lower for hint in LOG_URL_HINTS)


def _infer_platform_hints(description: str, components: List[str], labels: List[str]) -> Dict[str, str]:
    blob = " ".join([description or "", " ".join(components), " ".join(labels)]).upper()
    chip = ""
    if any(k in blob for k in ["UNISOC", "展锐", "SPRD"]):
        chip = "UNISOC"
    elif any(k in blob for k in ["MTK", "MEDIATEK", "联发科"]):
        chip = "MTK"
    elif any(k in blob for k in ["QCOM", "QUALCOMM", "高通"]):
        chip = "QCOM"
    domain = ""
    lower_blob = blob.lower()
    if any(k in lower_blob for k in ["modem", "call", "sms", "sim", "volte", "通信"]):
        domain = "comm"
    elif any(k in lower_blob for k in ["tp", "touch", "vib", "charge", "usb", "audio", "sensor"]):
        domain = "driver"
    elif any(k in lower_blob for k in ["kernel", "crash", "panic"]):
        domain = "kernel"
    return {"chip": chip, "domain": domain}


def unique_dest_path(dest_dir: Path, filename: str) -> Path:
    dest = dest_dir / filename
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    index = 1
    while True:
        candidate = dest_dir / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def download_http_file(url: str, dest_dir: Path, timeout: int = 300) -> Dict[str, Any]:
    parsed = urlparse(url)
    filename = unquote(Path(parsed.path).name) or "download.bin"
    dest_path = unique_dest_path(dest_dir, filename)
    request = urllib.request.Request(url, headers={"User-Agent": DOWNLOAD_USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
    dest_path.write_bytes(data)
    return {
        "url": url,
        "name": dest_path.name,
        "path": str(dest_path.resolve()),
        "size": len(data),
    }


class JiraClient:
    def __init__(self, server: str, user: str, password: str):
        self.jira = JIRA(server=server, basic_auth=(user, password))

    @classmethod
    def from_config(cls, config: Dict[str, str]) -> "JiraClient":
        server = config.get("server", "").strip()
        user = config.get("user", "").strip()
        password = config.get("password", "")
        missing = [k for k in ["server", "user", "password"] if not config.get(k)]
        if missing:
            raise ValueError(f"缺少配置项: {', '.join(missing)}。请先执行 config set。")
        return cls(server=server, user=user, password=password)

    def get_issue_detail(self, issue_ref: str) -> Dict[str, Any]:
        issue_key = normalize_issue_key(issue_ref)
        issue = self.jira.issue(
            issue_key,
            fields="summary,description,comment,components,labels,issuetype",
        )
        comments = []
        for c in issue.fields.comment.comments:
            author = getattr(c, "author", None)
            comments.append(
                {
                    "id": getattr(c, "id", ""),
                    "author": getattr(author, "displayName", getattr(author, "name", "")),
                    "created": getattr(c, "created", ""),
                    "updated": getattr(c, "updated", ""),
                    "body": getattr(c, "body", ""),
                }
            )
        components = [getattr(c, "name", str(c)) for c in (getattr(issue.fields, "components", None) or [])]
        labels = list(getattr(issue.fields, "labels", None) or [])
        issuetype = getattr(getattr(issue.fields, "issuetype", None), "name", None)
        description = getattr(issue.fields, "description", "") or ""
        platform_hints = _infer_platform_hints(description, components, labels)
        return {
            "issue_id": issue_key,
            "title": getattr(issue.fields, "summary", ""),
            "description": description,
            "comments": comments,
            "components": components,
            "labels": labels,
            "issuetype": issuetype,
            "platform_hints": platform_hints,
        }

    def add_comment(self, issue_ref: str, comment_text: str) -> Dict[str, Any]:
        issue_key = normalize_issue_key(issue_ref)
        issue = self.jira.issue(issue_key)
        comment = self.jira.add_comment(issue, comment_text)
        return {
            "issue_id": issue_key,
            "comment_id": getattr(comment, "id", ""),
            "created": getattr(comment, "created", ""),
            "body": getattr(comment, "body", comment_text),
        }

    def download_attachments(self, issue_ref: str, output_dir: str) -> Dict[str, Any]:
        issue_key = normalize_issue_key(issue_ref)
        issue = self.jira.issue(issue_key, fields="attachment")

        save_root = Path(output_dir or DEFAULT_DOWNLOAD_DIR)
        save_root.mkdir(parents=True, exist_ok=True)

        files = []
        for attachment in getattr(issue.fields, "attachment", []):
            filename = getattr(attachment, "filename", "unknown.bin")
            raw_data = attachment.get()
            abs_path = (save_root / filename).resolve()
            with open(abs_path, "wb") as f:
                f.write(raw_data)
            files.append(
                {
                    "name": filename,
                    "size": getattr(attachment, "size", None),
                    "path": str(abs_path),
                }
            )

        return {"issue_id": issue_key, "download_dir": str(save_root.resolve()), "files": files}

    def list_log_sources(self, issue_ref: str) -> Dict[str, Any]:
        """Classify log URLs/paths from description + comments (modem pipeline parity)."""
        detail = self.get_issue_detail(issue_ref)
        issue_key = detail["issue_id"]
        all_text = build_issue_log_text(detail)
        urls_by_type = extract_and_classify_urls(all_text)
        legacy_http = (
            urls_by_type.get("http_direct", [])
            + urls_by_type.get("box", [])
            + urls_by_type.get("feishu_file", [])
        )
        return {
            "issue_id": issue_key,
            "urls_by_type": urls_by_type,
            "http_urls": legacy_http,
            "log_http_urls": legacy_http,
            "unc_paths": urls_by_type.get("network_share", []),
        }

    def list_log_urls_from_description(
        self, issue_ref: str, all_urls: bool = False
    ) -> Dict[str, Any]:
        data = self.list_log_sources(issue_ref)
        if all_urls:
            data["log_http_urls"] = data["http_urls"]
        else:
            data["log_http_urls"] = [u for u in data["http_urls"] if is_likely_log_url(u)]
        return data

    def download_logs_multi_channel(
        self,
        issue_ref: str,
        output_dir: str,
        *,
        channels: Optional[Set[str]] = None,
        prefer_box_http: bool = True,
        box_headless: bool = True,
        box_max_retries: int = 3,
    ) -> Dict[str, Any]:
        sources = self.list_log_sources(issue_ref)
        issue_key = sources["issue_id"]
        urls_by_type = sources["urls_by_type"]
        total = sum(len(urls_by_type.get(k) or []) for k in urls_by_type)
        if total == 0:
            raise ValueError("工单描述/评论中未找到可下载的日志链接或网络路径")

        save_root = Path(output_dir or DEFAULT_DOWNLOAD_DIR)
        outcome = download_classified_urls(
            urls_by_type,
            str(save_root),
            channels=channels,
            prefer_box_http=prefer_box_http,
            box_headless=box_headless,
            box_max_retries=box_max_retries,
        )
        if not outcome.get("downloaded_any"):
            errors = [r for r in outcome.get("results", []) if not r.get("success")]
            raise ValueError(f"全部渠道下载失败: {errors}")

        http_downloaded = []
        http_errors = []
        unc_copied = []
        unc_errors = []
        for row in outcome.get("results", []):
            if row.get("success"):
                if row.get("url_type") == "network_share":
                    unc_copied.append({"source": row.get("url"), "target": outcome["download_dir"]})
                else:
                    for name in row.get("downloaded_files") or []:
                        http_downloaded.append(
                            {
                                "url": row.get("url"),
                                "name": name,
                                "path": str((save_root / name).resolve()),
                                "channel": row.get("url_type"),
                                "method": row.get("download_method"),
                            }
                        )
            else:
                if row.get("url_type") == "network_share":
                    unc_errors.append({"source": row.get("url"), "message": row.get("error") or ""})
                else:
                    http_errors.append({"url": row.get("url"), "message": row.get("error") or ""})

        return {
            "issue_id": issue_key,
            "download_dir": outcome["download_dir"],
            "urls_by_type": urls_by_type,
            "results": outcome.get("results", []),
            "http_downloaded": http_downloaded,
            "http_errors": http_errors,
            "unc_copied": unc_copied,
            "unc_errors": unc_errors,
        }

    def copy_log_from_description(
        self,
        issue_ref: str,
        output_dir: str,
        all_urls: bool = False,
        http_only: bool = False,
        unc_only: bool = False,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        channels: Optional[Set[str]] = None
        if http_only:
            channels = {"box", "feishu_file", "http_direct"}
        elif unc_only:
            channels = {"network_share"}
        return self.download_logs_multi_channel(issue_ref, output_dir, channels=channels)

    def get_changelog(self, issue_ref: str) -> List[Dict[str, Any]]:
        issue_key = normalize_issue_key(issue_ref)
        issue = self.jira.issue(issue_key, expand="changelog")
        changes = []
        changelog = getattr(issue, "changelog", None)
        histories = getattr(changelog, "histories", []) if changelog else []
        for h in histories:
            author = getattr(h, "author", None)
            author_name = getattr(author, "displayName", getattr(author, "name", ""))
            created = getattr(h, "created", "")
            items = getattr(h, "items", [])
            for it in items:
                field = getattr(it, "field", "")
                from_s = getattr(it, "fromString", None)
                to_s = getattr(it, "toString", None)
                from_v = from_s if from_s is not None else str(getattr(it, "from", ""))
                to_v = to_s if to_s is not None else str(getattr(it, "to", ""))
                changes.append(
                    {
                        "created": created,
                        "author": author_name,
                        "field": field,
                        "from": from_v,
                        "to": to_v,
                    }
                )
        return changes


CommandHandler = Callable[[argparse.Namespace], Dict[str, Any]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Jira CLI (Windows-friendly, extensible)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    config_parser = subparsers.add_parser("config", help="配置 Jira 连接参数")
    config_sub = config_parser.add_subparsers(dest="config_cmd", required=True)

    config_set = config_sub.add_parser("set", help="设置 server/user/password")
    config_set.add_argument("--server", required=True, help="Jira 服务器 URL")
    config_set.add_argument("--user", required=True, help="登录用户名")
    config_set.add_argument("--password", required=True, help="登录密码")

    config_sub.add_parser("show", help="显示当前配置（密码脱敏）")

    get_issue = subparsers.add_parser("get-issue", help="按 Jira ID/链接获取标题、描述、评论")
    get_issue.add_argument("--issue", required=True, help="例如 AAA-123 或完整 issue 链接")

    add_comment = subparsers.add_parser("add-comment", help="给单个 Jira ID 新增评论")
    add_comment.add_argument("--issue", required=True, help="例如 AAA-123")
    add_comment.add_argument("--comment", default="", help="评论内容（单行；多行请用 --comment-file）")
    add_comment.add_argument(
        "--comment-file",
        default="",
        help="从 UTF-8 文件读取评论正文（适合 TAHP BFF / 多行备注）",
    )

    download = subparsers.add_parser("download-attachments", help="下载 issue 附件")
    download.add_argument("--issue", required=True, help="例如 AAA-123")
    download.add_argument(
        "--output-dir",
        default=str(DEFAULT_DOWNLOAD_DIR),
        help=f"下载目录，默认: {DEFAULT_DOWNLOAD_DIR}",
    )

    list_log_urls = subparsers.add_parser(
        "list-log-urls-from-description",
        help="解析 description+评论 中的日志链接（兼容旧命令；推荐 list-log-sources）",
    )
    list_log_urls.add_argument("--issue", required=True, help="例如 AAA-123 或完整 issue 链接")
    list_log_urls.add_argument(
        "--all-urls",
        action="store_true",
        help="返回全部 http(s) 链接（默认仅返回疑似日志链接）",
    )

    list_sources = subparsers.add_parser(
        "list-log-sources",
        help="从 description+评论 提取并分类日志来源（box/feishu/network/http）",
    )
    list_sources.add_argument("--issue", required=True, help="例如 AAA-123 或完整 issue 链接")

    download_logs = subparsers.add_parser(
        "download-logs",
        help="多渠道下载 Jira 日志（FRBOX/SGBOX、飞书文件、UNC、HTTP 直链）",
    )
    download_logs.add_argument("--issue", required=True, help="例如 AAA-123")
    download_logs.add_argument(
        "--output-dir",
        default=str(DEFAULT_DOWNLOAD_DIR),
        help=f"目标目录，默认: {DEFAULT_DOWNLOAD_DIR}",
    )
    download_logs.add_argument(
        "--channels",
        default="",
        help="逗号分隔: box,feishu_file,network_share,http_direct（默认全部）",
    )
    download_logs.add_argument(
        "--no-box-http",
        action="store_true",
        help="FRBOX/SGBOX 跳过 PDS HTTP，直接浏览器下载",
    )
    download_logs.add_argument(
        "--headed",
        action="store_true",
        help="Box 浏览器下载使用有界面模式（默认 headless）",
    )
    download_logs.add_argument(
        "--box-max-retries",
        type=int,
        default=3,
        help="每个 Box URL 浏览器重试次数",
    )

    copy_log = subparsers.add_parser(
        "copy-log-from-description",
        help="从工单下载日志（内部调用多渠道 download-logs；兼容旧命令）",
    )
    copy_log.add_argument("--issue", required=True, help="例如 AAA-123")
    copy_log.add_argument(
        "--output-dir",
        default=str(DEFAULT_DOWNLOAD_DIR),
        help=f"目标目录，默认: {DEFAULT_DOWNLOAD_DIR}",
    )
    copy_log.add_argument(
        "--all-urls",
        action="store_true",
        help="下载 description 中全部 http(s) 链接（默认跳过图片等非日志 URL）",
    )
    copy_log.add_argument(
        "--http-only",
        action="store_true",
        help="仅下载 http(s) 链接，不尝试 UNC 拷贝",
    )
    copy_log.add_argument(
        "--unc-only",
        action="store_true",
        help="仅拷贝 UNC 路径，不下载 http(s) 链接",
    )
    copy_log.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="单个 http(s) 下载超时秒数，默认 300",
    )

    changelog = subparsers.add_parser("get-changelog", help="获取 issue 变更历史")
    changelog.add_argument("--issue", required=True, help="例如 AAA-123 或 issue 链接")

    extract_logs = subparsers.add_parser(
        "extract-logs",
        help="递归解压目录中的 zip/tar/gz/rar/7z 等压缩包",
    )
    extract_logs.add_argument(
        "--input-dir",
        action="append",
        dest="input_dirs",
        required=True,
        help="待解压目录，可重复传入",
    )
    extract_logs.add_argument("--output-root", default="", help="统一解压输出目录（默认就地解压）")
    extract_logs.add_argument("--no-recursive", action="store_true", help="关闭嵌套压缩包递归解压")

    prepare_logs = subparsers.add_parser(
        "prepare-logs",
        help="一站式：多渠道下载 + 递归解压（推荐）",
    )
    prepare_logs.add_argument("--issue", required=True, help="例如 OS162-37733")
    prepare_logs.add_argument(
        "--output-dir",
        default="",
        help="工作目录，默认 ./jira_workspace/<ISSUE_KEY>",
    )
    prepare_logs.add_argument("--channels", default="", help="逗号分隔渠道，默认全部")
    prepare_logs.add_argument("--no-box-http", action="store_true")
    prepare_logs.add_argument("--headed", action="store_true")
    prepare_logs.add_argument("--box-max-retries", type=int, default=3)
    prepare_logs.add_argument("--no-recursive", action="store_true", help="解压时不递归嵌套包")

    subparsers.add_parser("setup-check", help="检查依赖、Jira 凭据与 .env 配置是否就绪")

    env_parser = subparsers.add_parser("env", help="管理 jira-ops/.env 持久化配置")
    env_sub = env_parser.add_subparsers(dest="env_cmd", required=True)
    env_sub.add_parser("show", help="显示 .env（敏感项脱敏）")
    env_set = env_sub.add_parser("set", help="写入/更新 .env 键值")
    env_set.add_argument("pairs", nargs="+", help="KEY=VALUE，可一次传多个")
    env_init = env_sub.add_parser("init-from-user", help="从 JSON 批量写入 .env（Agent 收集用户输入后用）")
    env_init.add_argument("--json", required=True, help='JSON 对象，如 {"FEISHU_APP_ID":"cli_xxx",...}')

    return parser


def command_config_set(args: argparse.Namespace) -> Dict[str, Any]:
    config = {
        "server": args.server.strip(),
        "user": args.user.strip(),
        "password": args.password,
    }
    save_config(config)
    set_env_pairs(
        _SKILL_ROOT,
        {
            "JIRA_SERVER": config["server"],
            "JIRA_USERNAME": config["user"],
            "JIRA_PASSWORD": config["password"],
        },
    )
    return ok({"config_path": str(CONFIG_PATH.resolve()), "message": "配置已保存（已同步到 .env）"})


def command_config_show(_: argparse.Namespace) -> Dict[str, Any]:
    config = load_config()
    if not config:
        return err("CONFIG_NOT_FOUND", f"未找到配置文件: {CONFIG_PATH}")
    safe_config = dict(config)
    if safe_config.get("password"):
        safe_config["password"] = "******"
    return ok({"config_path": str(CONFIG_PATH.resolve()), "config": safe_config})


def get_client() -> JiraClient:
    config = load_config()
    return JiraClient.from_config(config)


def command_get_issue(args: argparse.Namespace) -> Dict[str, Any]:
    return ok(get_client().get_issue_detail(args.issue))


def command_add_comment(args: argparse.Namespace) -> Dict[str, Any]:
    text = str(args.comment or "")
    if getattr(args, "comment_file", None):
        cf = Path(str(args.comment_file))
        if not cf.is_file():
            raise ValueError(f"comment-file 不存在: {cf}")
        text = cf.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("comment 不能为空（使用 --comment 或 --comment-file）")
    return ok(get_client().add_comment(args.issue, text))


def command_download_attachments(args: argparse.Namespace) -> Dict[str, Any]:
    return ok(get_client().download_attachments(args.issue, args.output_dir))


def command_get_changelog(args: argparse.Namespace) -> Dict[str, Any]:
    return ok({"issue_id": normalize_issue_key(args.issue), "changes": get_client().get_changelog(args.issue)})


def _parse_channels(raw: str) -> Optional[Set[str]]:
    if not raw or not raw.strip():
        return None
    parts = {p.strip() for p in raw.split(",") if p.strip()}
    return parts


def command_list_log_sources(args: argparse.Namespace) -> Dict[str, Any]:
    return ok(get_client().list_log_sources(args.issue))


def command_download_logs(args: argparse.Namespace) -> Dict[str, Any]:
    return ok(
        get_client().download_logs_multi_channel(
            args.issue,
            args.output_dir,
            channels=_parse_channels(args.channels),
            prefer_box_http=not args.no_box_http,
            box_headless=not args.headed,
            box_max_retries=args.box_max_retries,
        )
    )


def command_list_log_urls_from_description(args: argparse.Namespace) -> Dict[str, Any]:
    return ok(
        get_client().list_log_urls_from_description(args.issue, all_urls=args.all_urls)
    )


def command_copy_log_from_description(args: argparse.Namespace) -> Dict[str, Any]:
    if args.http_only and args.unc_only:
        raise ValueError("--http-only 与 --unc-only 不能同时使用")
    return ok(
        get_client().copy_log_from_description(
            args.issue,
            args.output_dir,
            all_urls=args.all_urls,
            http_only=args.http_only,
            unc_only=args.unc_only,
            timeout=args.timeout,
        )
    )


def command_extract_logs(args: argparse.Namespace) -> Dict[str, Any]:
    outcome = extract_directories(
        args.input_dirs,
        output_root=args.output_root or None,
        recursive=not args.no_recursive,
    )
    if not outcome.get("extracted_any"):
        failed = [r for r in outcome.get("results", []) if not r.get("success")]
        raise ValueError(f"解压失败或无有效目录: {failed}")
    return ok(outcome)


def _default_prepare_dir(issue_ref: str, output_dir: str) -> str:
    if output_dir and output_dir.strip():
        return output_dir.strip()
    issue_key = normalize_issue_key(issue_ref)
    return str((Path.cwd() / "jira_workspace" / issue_key).resolve())


def command_prepare_logs(args: argparse.Namespace) -> Dict[str, Any]:
    out_dir = _default_prepare_dir(args.issue, args.output_dir)
    download_data = get_client().download_logs_multi_channel(
        args.issue,
        out_dir,
        channels=_parse_channels(args.channels),
        prefer_box_http=not args.no_box_http,
        box_headless=not args.headed,
        box_max_retries=args.box_max_retries,
    )
    extract_data = extract_directories(
        [download_data["download_dir"]],
        recursive=not args.no_recursive,
    )
    if not extract_data.get("extracted_any"):
        raise ValueError(
            f"下载成功但解压失败: download_dir={download_data.get('download_dir')} "
            f"extract_results={extract_data.get('results')}"
        )
    return ok(
        {
            "issue_id": download_data.get("issue_id"),
            "workspace_dir": out_dir,
            "download": download_data,
            "extraction": extract_data,
            "log_root_dirs": extract_data.get("extracted_dirs", []),
        }
    )


def command_setup_check(_: argparse.Namespace) -> Dict[str, Any]:
    return ok(run_setup_check(_SKILL_ROOT, load_config()))


def _parse_env_pair(token: str) -> tuple[str, str]:
    if "=" not in token:
        raise ValueError(f"env set 参数必须是 KEY=VALUE 格式: {token}")
    key, _, val = token.partition("=")
    key = key.strip()
    if not key:
        raise ValueError(f"空的 env key: {token}")
    return key, val


def command_env_show(_: argparse.Namespace) -> Dict[str, Any]:
    return ok(show_env(_SKILL_ROOT))


def command_env_set(args: argparse.Namespace) -> Dict[str, Any]:
    pairs: Dict[str, str] = {}
    for token in args.pairs:
        key, val = _parse_env_pair(token)
        pairs[key] = val
    if "NETWORK_SERVERS" in pairs:
        ok_json, msg = validate_network_servers_json(pairs["NETWORK_SERVERS"])
        if not ok_json:
            raise ValueError(msg)
    return ok(set_env_pairs(_SKILL_ROOT, pairs))


def command_env_init_from_user(args: argparse.Namespace) -> Dict[str, Any]:
    try:
        data = json.loads(args.json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--json 不是合法 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("--json 必须是 JSON 对象")
    str_data = {str(k): str(v) for k, v in data.items()}
    if "NETWORK_SERVERS" in str_data:
        ok_json, msg = validate_network_servers_json(str_data["NETWORK_SERVERS"])
        if not ok_json:
            raise ValueError(msg)
    return ok(set_env_pairs(_SKILL_ROOT, str_data))


COMMANDS: Dict[str, CommandHandler] = {
    "get-issue": command_get_issue,
    "add-comment": command_add_comment,
    "download-attachments": command_download_attachments,
    "get-changelog": command_get_changelog,
    "list-log-sources": command_list_log_sources,
    "list-log-urls-from-description": command_list_log_urls_from_description,
    "download-logs": command_download_logs,
    "copy-log-from-description": command_copy_log_from_description,
    "extract-logs": command_extract_logs,
    "prepare-logs": command_prepare_logs,
    "setup-check": command_setup_check,
}


def main() -> int:
    load_optional_env(_SKILL_ROOT)
    # Force UTF-8 output on Windows terminals to avoid GBK encode failures.
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
        elif args.command == "env":
            if args.env_cmd == "show":
                result = command_env_show(args)
            elif args.env_cmd == "set":
                result = command_env_set(args)
            elif args.env_cmd == "init-from-user":
                result = command_env_init_from_user(args)
            else:
                raise ValueError("不支持的 env 子命令")
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
    except JIRAError as e:
        message = getattr(e, "text", None) or str(e)
        print(json.dumps(err("JIRA_ERROR", message), ensure_ascii=False, indent=2))
        return 3
    except OSError as e:
        print(json.dumps(err("IO_ERROR", str(e)), ensure_ascii=False, indent=2))
        return 4
    except Exception as e:
        print(json.dumps(err("UNEXPECTED_ERROR", str(e)), ensure_ascii=False, indent=2))
        return 99


if __name__ == "__main__":
    sys.exit(main())
