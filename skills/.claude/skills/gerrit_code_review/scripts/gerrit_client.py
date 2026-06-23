#!/usr/bin/env python3
"""Gerrit HTTP API client for code review bundle fetching."""

from __future__ import annotations

import base64
import json
import os
import platform
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CRED_FILE = SKILL_DIR / "cred.json"
DEFAULT_WIN_REPORT_DIR = Path(r"D:\code_review_report")

DETAIL_OPTIONS = "O=10004&O=10009&O=10014"  # CURRENT_REVISION, CURRENT_FILES, DETAILED_ACCOUNTS


@dataclass(frozen=True)
class AuthConfig:
    host: str
    user: str
    password: str

    @property
    def auth_header(self) -> str:
        token = base64.b64encode(f"{self.user}:{self.password}".encode("utf-8")).decode("ascii")
        return f"Basic {token}"


@dataclass(frozen=True)
class ParsedInput:
    kind: str  # "change" | "topic"
    value: str


def strip_json_xssi_prefix(raw: str) -> str:
    prefix = ")]}'"
    if raw.startswith(prefix):
        return raw.split("\n", 1)[1] if "\n" in raw else ""
    return raw


def load_auth(cred_file: Path | None = None) -> AuthConfig:
    env_user = os.getenv("GERRIT_USER", "").strip()
    env_password = os.getenv("GERRIT_HTTP_PASSWORD", "").strip()
    if env_user and env_password:
        host = os.getenv("GERRIT_HOST", "https://gerrit.transsion.com").strip().rstrip("/")
        return AuthConfig(host=host, user=env_user, password=env_password)

    path = cred_file or DEFAULT_CRED_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"Credential file not found: {path}. "
            "Set GERRIT_USER and GERRIT_HTTP_PASSWORD, or create cred.json."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    host = str(data.get("host", "https://gerrit.transsion.com")).strip().rstrip("/")
    user = str(data.get("user", "")).strip()
    password = str(data.get("password", "")).strip()
    if not user or not password:
        raise ValueError(f"Invalid credential file {path}: user and password are required.")
    return AuthConfig(host=host, user=user, password=password)


def normalize_topic_name(raw_topic: str, *, from_url: bool = False) -> str:
    raw = raw_topic.strip()
    if from_url or "%" in raw:
        topic = urllib.parse.unquote_plus(raw)
    else:
        topic = urllib.parse.unquote(raw)
    if len(topic) >= 2 and topic[0] == topic[-1] == '"':
        topic = topic[1:-1]
    return topic.strip()


def build_topic_search_query(topic_name: str) -> str:
    name = topic_name.strip()
    if not name:
        return "topic:"
    if any(ch in name for ch in ' +:"()'):
        escaped = name.replace("\\", "\\\\").replace('"', '\\"')
        return f'topic:"{escaped}"'
    return f"topic:{name}"


def parse_input(raw: str) -> ParsedInput:
    text = raw.strip()
    lower = text.lower()

    if lower.startswith("topic:"):
        return ParsedInput("topic", normalize_topic_name(text.split(":", 1)[1]))

    if "/q/topic:" in lower:
        token = text[lower.index("/q/topic:") + len("/q/topic:") :]
        topic = token.split("&", 1)[0].split("#", 1)[0].strip().strip("/")
        if not topic:
            raise ValueError(f"Cannot parse topic from input: {raw}")
        return ParsedInput("topic", normalize_topic_name(topic, from_url=True))

    if re.fullmatch(r"\d+", text):
        return ParsedInput("change", text)

    match = re.search(r"/\+/(\d+)(?:/\d+)?(?:[#?].*)?$", text)
    if match:
        return ParsedInput("change", match.group(1))

    if "/c/" in lower and "/+/" in lower:
        raise ValueError(f"Cannot extract change number from URL: {raw}")

    return ParsedInput("change", text)


def _request_text(auth: AuthConfig, url: str, *, method: str = "GET") -> str:
    request = urllib.request.Request(url=url, method=method)
    request.add_header("Authorization", auth.auth_header)
    request.add_header("Content-Type", "application/json; charset=UTF-8")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        detail = strip_json_xssi_prefix(body).strip()
        raise RuntimeError(f"Gerrit HTTP {err.code}: {err.reason} {detail}") from err
    except urllib.error.URLError as err:
        raise RuntimeError(f"Gerrit network error: {err}") from err


def _request_json(auth: AuthConfig, url: str) -> Any:
    body = strip_json_xssi_prefix(_request_text(auth, url)).strip()
    if not body:
        return None
    return json.loads(body)


def fetch_change_detail(auth: AuthConfig, change_id: str) -> dict[str, Any]:
    encoded = urllib.parse.quote(change_id, safe="")
    url = f"{auth.host}/a/changes/{encoded}/detail?{DETAIL_OPTIONS}"
    data = _request_json(auth, url)
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected detail response for change {change_id}")
    return data


def fetch_patch(auth: AuthConfig, change_id: str, revision: str = "current") -> str:
    encoded_change = urllib.parse.quote(change_id, safe="")
    encoded_revision = urllib.parse.quote(revision, safe="")
    url = f"{auth.host}/a/changes/{encoded_change}/revisions/{encoded_revision}/patch"
    raw = _request_text(auth, url)
    raw = strip_json_xssi_prefix(raw).strip()
    if not raw:
        return ""
    try:
        decoded = base64.b64decode(raw)
        return decoded.decode("utf-8", errors="replace")
    except Exception:
        return raw


def fetch_file_diff(
    auth: AuthConfig,
    change_id: str,
    file_path: str,
    revision: str = "current",
    *,
    context: str = "ALL",
) -> dict[str, Any]:
    encoded_change = urllib.parse.quote(change_id, safe="")
    encoded_revision = urllib.parse.quote(revision, safe="")
    encoded_path = urllib.parse.quote(file_path, safe="")
    url = (
        f"{auth.host}/a/changes/{encoded_change}/revisions/"
        f"{encoded_revision}/files/{encoded_path}/diff?context={context}"
    )
    data = _request_json(auth, url)
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected diff response for {file_path}")
    return data


def fetch_file_content(
    auth: AuthConfig,
    change_id: str,
    file_path: str,
    revision: str = "current",
) -> str:
    encoded_change = urllib.parse.quote(change_id, safe="")
    encoded_revision = urllib.parse.quote(revision, safe="")
    encoded_path = urllib.parse.quote(file_path, safe="")
    url = (
        f"{auth.host}/a/changes/{encoded_change}/revisions/"
        f"{encoded_revision}/files/{encoded_path}/content"
    )
    raw = strip_json_xssi_prefix(_request_text(auth, url)).strip()
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
        if isinstance(payload, str):
            raw = payload
    except json.JSONDecodeError:
        pass
    return base64.b64decode(raw).decode("utf-8", errors="replace")


def fetch_topic_changes(auth: AuthConfig, topic: str) -> list[dict[str, Any]]:
    topic_name = normalize_topic_name(topic)
    query = urllib.parse.quote(build_topic_search_query(topic_name), safe="")
    url = f"{auth.host}/a/changes/?q={query}&n=500&{DETAIL_OPTIONS}"
    data = _request_json(auth, url)
    if data is None:
        return []
    if not isinstance(data, list):
        raise RuntimeError("Topic query returned non-list response")
    return [item for item in data if isinstance(item, dict)]


def fetch_revision_files(
    auth: AuthConfig,
    change_id: str,
    revision: str = "current",
) -> dict[str, Any]:
    encoded_change = urllib.parse.quote(change_id, safe="")
    encoded_revision = urllib.parse.quote(revision, safe="")
    url = f"{auth.host}/a/changes/{encoded_change}/revisions/{encoded_revision}/files/"
    data = _request_json(auth, url)
    if not isinstance(data, dict):
        return {}
    return data


def _files_from_revision_map(files_map: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path, info in files_map.items():
        if path == "/COMMIT_MSG":
            continue
        if not isinstance(info, dict):
            continue
        result.append(
            {
                "path": path,
                "status": info.get("status"),
                "lines_inserted": info.get("lines_inserted", 0) or 0,
                "lines_deleted": info.get("lines_deleted", 0) or 0,
            }
        )
    return result


def _extract_files(detail: dict[str, Any], files_map: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if files_map:
        return _files_from_revision_map(files_map)

    revision = detail.get("current_revision")
    if not revision:
        return []
    revisions = detail.get("revisions", {})
    if not isinstance(revisions, dict):
        return []
    rev_data = revisions.get(revision, {})
    if not isinstance(rev_data, dict):
        return []
    files = rev_data.get("files", {})
    if isinstance(files, dict) and files:
        return _files_from_revision_map(files)
    return []


def _summarize_change(
    auth: AuthConfig,
    change_id: str,
    *,
    expand_files: bool = False,
) -> dict[str, Any]:
    detail = fetch_change_detail(auth, change_id)
    number = detail.get("_number", change_id)
    owner = detail.get("owner", {}) if isinstance(detail.get("owner"), dict) else {}
    try:
        files_map = fetch_revision_files(auth, str(number))
    except Exception:
        files_map = {}
    files = _extract_files(detail, files_map)
    patch_text = fetch_patch(auth, str(number))

    expanded_files: dict[str, str] = {}
    if expand_files:
        for item in files:
            path = item["path"]
            try:
                expanded_files[path] = fetch_file_content(auth, str(number), path)
            except Exception as err:
                expanded_files[path] = f"<fetch error: {err}>"

    return {
        "number": number,
        "change_id": detail.get("change_id"),
        "subject": detail.get("subject", ""),
        "status": detail.get("status", ""),
        "branch": detail.get("branch", ""),
        "project": detail.get("project", ""),
        "topic": detail.get("topic", ""),
        "owner": owner.get("name") or owner.get("username") or "",
        "owner_email": owner.get("email", ""),
        "created": detail.get("created", ""),
        "updated": detail.get("updated", ""),
        "insertions": detail.get("insertions", 0) or 0,
        "deletions": detail.get("deletions", 0) or 0,
        "files": files,
        "patch_text": patch_text,
        "expanded_files": expanded_files,
        "url": f"{auth.host}/c/{detail.get('project', '')}/+/{number}",
    }


def build_review_bundle(
    raw_input: str,
    *,
    auth: AuthConfig | None = None,
    cred_file: Path | None = None,
    expand_files: bool = False,
) -> dict[str, Any]:
    auth = auth or load_auth(cred_file)
    parsed = parse_input(raw_input)

    if parsed.kind == "change":
        change = _summarize_change(auth, parsed.value, expand_files=expand_files)
        return {
            "input": raw_input,
            "kind": "change",
            "host": auth.host,
            "changes": [change],
        }

    topic_name = parsed.value
    topic_items = fetch_topic_changes(auth, topic_name)
    if not topic_items:
        return {
            "input": raw_input,
            "kind": "topic",
            "host": auth.host,
            "topic": topic_name,
            "changes": [],
        }

    changes: list[dict[str, Any]] = []
    for item in topic_items:
        number = item.get("_number")
        if not isinstance(number, int):
            continue
        changes.append(_summarize_change(auth, str(number), expand_files=expand_files))

    return {
        "input": raw_input,
        "kind": "topic",
        "host": auth.host,
        "topic": topic_name,
        "changes": changes,
    }


def topic_slug(topic_name: str) -> str:
    slug = re.sub(r"[^\w\-]+", "_", topic_name.strip(), flags=re.UNICODE)
    return slug.strip("_") or "topic"


def get_report_dir() -> Path:
    """Return code review report output directory."""
    override = os.getenv("GERRIT_REPORT_DIR", "").strip()
    if override:
        return Path(override)
    if platform.system() == "Windows":
        return DEFAULT_WIN_REPORT_DIR
    return Path.cwd()


def ensure_report_dir() -> Path:
    """Create report directory if missing and return its path."""
    report_dir = get_report_dir()
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


def report_path_for_change(change_id: str | int) -> Path:
    return ensure_report_dir() / f"review-report-{change_id}.html"


def report_path_for_topic(topic_name: str) -> Path:
    return ensure_report_dir() / f"review-report-topic-{topic_slug(topic_name)}.html"


def report_file_url(report_path: Path) -> str:
    """Return a file:// URL that opens the HTML report in a browser."""
    return report_path.resolve().as_uri()
