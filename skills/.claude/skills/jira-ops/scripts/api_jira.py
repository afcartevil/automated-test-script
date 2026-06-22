import argparse
import json
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List
from urllib.parse import unquote, urlparse

from jira import JIRA
from jira.exceptions import JIRAError


CONFIG_PATH = Path.home() / ".jira_cli_config.json"
DEFAULT_DOWNLOAD_DIR = Path.cwd() / "jira_attachments"
ISSUE_ID_PATTERN = re.compile(r"[A-Z][A-Z0-9]+-\d+")
UNC_PATH_PATTERN = re.compile(r"\\\\[^\s\]\)>,]+")
HTTP_URL_PATTERN = re.compile(r"https?://[^\s\]\)>\",|]+", re.IGNORECASE)
LOG_URL_HINTS = (".zip", ".gz", ".tgz", ".tar", ".log", "/log", "fanslog", "taglog", "bugreport")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")
DOWNLOAD_USER_AGENT = "jira-ops-cli/1.1"


def load_config() -> Dict[str, str]:
    bugtool_yaml = Path.home() / ".integration_bug_tool" / "env.yaml"
    if bugtool_yaml.is_file():
        try:
            import yaml  # type: ignore

            with bugtool_yaml.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            jira = data.get("jira") if isinstance(data, dict) else None
            if isinstance(jira, dict) and jira.get("user") and jira.get("password"):
                return {
                    "server": str(jira.get("server", "")).strip(),
                    "user": str(jira.get("user", "")).strip(),
                    "password": str(jira.get("password", "")),
                }
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

    def list_log_urls_from_description(
        self, issue_ref: str, all_urls: bool = False
    ) -> Dict[str, Any]:
        issue_key = normalize_issue_key(issue_ref)
        issue = self.jira.issue(issue_key, fields="description")
        description = str(getattr(issue.fields, "description", "") or "")
        http_urls = extract_http_urls(description)
        unc_paths = [m.strip() for m in UNC_PATH_PATTERN.findall(description)]
        if all_urls:
            log_urls = http_urls
        else:
            log_urls = [u for u in http_urls if is_likely_log_url(u)]
        return {
            "issue_id": issue_key,
            "http_urls": http_urls,
            "log_http_urls": log_urls,
            "unc_paths": unc_paths,
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
        issue_key = normalize_issue_key(issue_ref)
        issue = self.jira.issue(issue_key, fields="description")
        description = str(getattr(issue.fields, "description", "") or "")

        save_root = Path(output_dir or DEFAULT_DOWNLOAD_DIR)
        save_root.mkdir(parents=True, exist_ok=True)

        http_urls = extract_http_urls(description)
        if all_urls:
            selected_http = http_urls
        else:
            selected_http = [u for u in http_urls if is_likely_log_url(u)]

        unc_paths = [m.strip() for m in UNC_PATH_PATTERN.findall(description)]
        downloaded: List[Dict[str, Any]] = []
        download_errors: List[Dict[str, str]] = []
        unc_copied: List[Dict[str, Any]] = []
        unc_errors: List[Dict[str, str]] = []

        if not http_only:
            for unc in unc_paths:
                src_dir = Path(unc)
                try:
                    if not src_dir.exists() or not src_dir.is_dir():
                        raise ValueError(f"网络路径不可访问或不是目录: {src_dir}")
                    for item in src_dir.iterdir():
                        dst = save_root / item.name
                        if item.is_dir():
                            shutil.copytree(item, dst, dirs_exist_ok=True)
                        else:
                            shutil.copy2(item, dst)
                    unc_copied.append({"source": unc, "target": str(save_root.resolve())})
                except (OSError, ValueError) as e:
                    unc_errors.append({"source": unc, "message": str(e)})

        if not unc_only:
            for url in selected_http:
                try:
                    downloaded.append(download_http_file(url, save_root, timeout=timeout))
                except (urllib.error.URLError, OSError, TimeoutError) as e:
                    download_errors.append({"url": url, "message": str(e)})

        if not downloaded and not unc_copied:
            if http_urls or unc_paths:
                raise ValueError(
                    "description 中找到了日志相关链接/路径，但全部下载或拷贝失败。"
                    f" http_errors={download_errors}, unc_errors={unc_errors}"
                )
            raise ValueError(
                "description 中未找到可下载的日志链接（http/https）或 UNC 网络路径"
            )

        return {
            "issue_id": issue_key,
            "download_dir": str(save_root.resolve()),
            "http_downloaded": downloaded,
            "http_errors": download_errors,
            "unc_copied": unc_copied,
            "unc_errors": unc_errors,
            "skipped_http_urls": [
                u for u in http_urls if u not in selected_http and u not in {d["url"] for d in downloaded}
            ],
        }

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
    add_comment.add_argument("--comment", required=True, help="评论内容")

    download = subparsers.add_parser("download-attachments", help="下载 issue 附件")
    download.add_argument("--issue", required=True, help="例如 AAA-123")
    download.add_argument(
        "--output-dir",
        default=str(DEFAULT_DOWNLOAD_DIR),
        help=f"下载目录，默认: {DEFAULT_DOWNLOAD_DIR}",
    )

    list_log_urls = subparsers.add_parser(
        "list-log-urls-from-description",
        help="解析 description 中的日志 http(s) 链接与 UNC 路径（不下载）",
    )
    list_log_urls.add_argument("--issue", required=True, help="例如 AAA-123 或完整 issue 链接")
    list_log_urls.add_argument(
        "--all-urls",
        action="store_true",
        help="返回全部 http(s) 链接（默认仅返回疑似日志链接）",
    )

    copy_log = subparsers.add_parser(
        "copy-log-from-description",
        help="从 description 下载 http(s) 日志链接，并/或拷贝 UNC 网络路径到本地",
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

    return parser


def command_config_set(args: argparse.Namespace) -> Dict[str, Any]:
    config = {
        "server": args.server.strip(),
        "user": args.user.strip(),
        "password": args.password,
    }
    save_config(config)
    return ok({"config_path": str(CONFIG_PATH.resolve()), "message": "配置已保存"})


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
    if not args.comment.strip():
        raise ValueError("comment 不能为空")
    return ok(get_client().add_comment(args.issue, args.comment))


def command_download_attachments(args: argparse.Namespace) -> Dict[str, Any]:
    return ok(get_client().download_attachments(args.issue, args.output_dir))


def command_get_changelog(args: argparse.Namespace) -> Dict[str, Any]:
    return ok({"issue_id": normalize_issue_key(args.issue), "changes": get_client().get_changelog(args.issue)})


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


COMMANDS: Dict[str, CommandHandler] = {
    "get-issue": command_get_issue,
    "add-comment": command_add_comment,
    "download-attachments": command_download_attachments,
    "get-changelog": command_get_changelog,
    "list-log-urls-from-description": command_list_log_urls_from_description,
    "copy-log-from-description": command_copy_log_from_description,
}


def main() -> int:
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
