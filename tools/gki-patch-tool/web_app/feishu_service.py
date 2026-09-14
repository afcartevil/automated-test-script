"""Feishu OpenAPI client using enterprise app credentials (App ID / Secret)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import httpx

from web_app.lark_cli_runner import LarkCliError, ensure_lark_user_auth, lark_cli_available, run_lark


class FeishuError(RuntimeError):
    pass


ENV_APP_ID = "GKI_FEISHU_APP_ID"
ENV_APP_SECRET = "GKI_FEISHU_APP_SECRET"
ENV_FOLDER = "GKI_FEISHU_FOLDER_TOKEN"
ENV_OPEN_BASE = "GKI_FEISHU_OPEN_BASE"
ENV_OWNER = "GKI_FEISHU_OWNER"
ENV_SECURE_LABEL = "GKI_FEISHU_SECURE_LABEL"
ENV_WEBHOOK = "GKI_FEISHU_WEBHOOK_URL"
ENV_WEBHOOK_SECRET = "GKI_FEISHU_WEBHOOK_SECRET"
ENV_NOTIFY_USERS = "GKI_FEISHU_NOTIFY_USERS"
DEFAULT_OPEN_BASE = "https://open.feishu.cn"
# 企业四档密级默认：S2-内部公开（按名称前缀匹配）
DEFAULT_SECURE_LABEL = "S2"

_token_cache: Dict[str, Any] = {"token": "", "expire_at": 0.0, "app_id": ""}
_secure_label_cache: Dict[str, str] = {}  # want -> label_id
_secure_label_unavailable: str = ""  # once set, skip further secure-label attempts this process
_http: Optional[httpx.Client] = None


def get_feishu_config() -> Dict[str, str]:
    cfg = {
        "app_id": "",
        "app_secret": "",
        "folder_token": "",
        "open_base": DEFAULT_OPEN_BASE,
        "owner": "",
        "secure_label": DEFAULT_SECURE_LABEL,
        "webhook_url": "",
        "webhook_secret": "",
        "notify_users": "",
    }
    try:
        import yaml
        from web_app.app_paths import settings_file
        path = settings_file()
        if path.is_file():
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            feishu = raw.get("feishu") if isinstance(raw, dict) else {}
            if isinstance(feishu, dict):
                for key in cfg:
                    value = str(feishu.get(key) or "").strip()
                    if value:
                        cfg[key] = value.rstrip("/") if key == "open_base" else value
    except Exception:
        pass
    env_map = {
        "app_id": os.environ.get(ENV_APP_ID, "").strip(),
        "app_secret": os.environ.get(ENV_APP_SECRET, "").strip(),
        "folder_token": os.environ.get(ENV_FOLDER, "").strip(),
        "open_base": os.environ.get(ENV_OPEN_BASE, "").strip().rstrip("/"),
        "owner": os.environ.get(ENV_OWNER, "").strip(),
        "secure_label": os.environ.get(ENV_SECURE_LABEL, "").strip(),
        "webhook_url": os.environ.get(ENV_WEBHOOK, "").strip(),
        "webhook_secret": os.environ.get(ENV_WEBHOOK_SECRET, "").strip(),
        "notify_users": os.environ.get(ENV_NOTIFY_USERS, "").strip(),
    }
    for key, value in env_map.items():
        if value:
            cfg[key] = value
    try:
        from web_app.database import get_db_feishu_config
        db_cfg = get_db_feishu_config()
        for key in (
            "app_id", "app_secret", "folder_token", "open_base", "owner",
            "secure_label", "webhook_url", "webhook_secret", "notify_users",
        ):
            value = str(db_cfg.get(key) or "").strip()
            if value:
                cfg[key] = value.rstrip("/") if key == "open_base" else value
    except Exception:
        pass
    if not cfg["open_base"]:
        cfg["open_base"] = DEFAULT_OPEN_BASE
    if not cfg.get("secure_label"):
        cfg["secure_label"] = DEFAULT_SECURE_LABEL
    return cfg


def normalize_folder_token(raw: str) -> str:
    """Accept a folder token or a Feishu folder URL."""
    text = (raw or "").strip()
    if not text:
        return ""
    text = text.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    for marker in ("/drive/folder/", "/folder/"):
        idx = text.lower().find(marker)
        if idx >= 0:
            return text[idx + len(marker):].split("/")[0].strip()
    return text


def save_feishu_config(
    app_id: str,
    app_secret: str,
    folder_token: str = "",
    open_base: str = "",
    owner: str = "",
    secure_label: str = "",
    webhook_url: str = "",
    webhook_secret: str = "",
    notify_users: str = "",
) -> None:
    global _secure_label_unavailable
    from web_app.database import save_db_feishu_config
    save_db_feishu_config(
        app_id=app_id.strip(),
        app_secret=app_secret.strip(),
        folder_token=normalize_folder_token(folder_token),
        open_base=(open_base or DEFAULT_OPEN_BASE).strip().rstrip("/"),
        owner=owner.strip(),
        secure_label=(secure_label or DEFAULT_SECURE_LABEL).strip() or DEFAULT_SECURE_LABEL,
        webhook_url=webhook_url.strip(),
        webhook_secret=webhook_secret.strip(),
        notify_users=notify_users.strip(),
    )
    _token_cache["token"] = ""
    _token_cache["expire_at"] = 0.0
    _secure_label_cache.clear()
    _secure_label_unavailable = ""


def is_feishu_app_configured() -> bool:
    cfg = get_feishu_config()
    return bool(cfg["app_id"] and cfg["app_secret"])


def is_feishu_webhook_configured() -> bool:
    return bool(str(get_feishu_config().get("webhook_url") or "").strip())


def is_feishu_app_notify_configured() -> bool:
    """App IM notify needs tenant app credentials plus at least one recipient."""
    if not is_feishu_app_configured():
        return False
    return bool(get_notify_recipients())


def parse_notify_recipients(raw: str) -> List[str]:
    """Extract send targets from JSON picker payload or comma/newline text."""
    return [item["id"] for item in parse_notify_targets(raw) if item.get("id")]


def parse_notify_targets(raw: str) -> List[Dict[str, str]]:
    """Parse stored notify_users into [{id, name, email, kind}]."""
    text = str(raw or "").strip()
    if not text:
        return []
    items: List[Dict[str, str]] = []
    if text.startswith("["):
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            data = None
        if isinstance(data, list):
            for entry in data:
                parsed = _notify_target_from_value(entry)
                if parsed:
                    items.append(parsed)
            return _dedupe_notify_targets(items)
    for chunk in text.replace(";", ",").replace("\r", "\n").replace("\n", ",").split(","):
        parsed = _notify_target_from_value(chunk.strip())
        if parsed:
            items.append(parsed)
    return _dedupe_notify_targets(items)


def _notify_target_from_value(value: Any) -> Optional[Dict[str, str]]:
    if isinstance(value, str):
        ident = value.strip()
        if not ident:
            return None
        kind = "chat" if ident.startswith("oc_") else "user"
        return {"id": ident, "name": ident, "email": ident if "@" in ident else "", "kind": kind}
    if not isinstance(value, dict):
        return None
    ident = str(
        value.get("id")
        or value.get("open_id")
        or value.get("chat_id")
        or value.get("email")
        or ""
    ).strip()
    if not ident:
        return None
    kind = str(value.get("kind") or "").strip().lower()
    if kind not in ("user", "chat"):
        kind = "chat" if ident.startswith("oc_") else "user"
    email = str(value.get("email") or "").strip()
    name = str(value.get("name") or email or ident).strip()
    return {"id": ident, "name": name, "email": email, "kind": kind}


def _dedupe_notify_targets(items: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen: set = set()
    for item in items:
        ident = str(item.get("id") or "").strip()
        if not ident or ident in seen:
            continue
        seen.add(ident)
        out.append(item)
    return out


def serialize_notify_targets(items: Sequence[Dict[str, Any]]) -> str:
    cleaned = _dedupe_notify_targets(
        [item for item in (_notify_target_from_value(x) or {} for x in items) if item]
    )
    return json.dumps(cleaned, ensure_ascii=False) if cleaned else ""


def get_notify_recipients() -> List[str]:
    """People to IM: notify_users list, falling back to default owner."""
    cfg = get_feishu_config()
    people = parse_notify_recipients(str(cfg.get("notify_users") or ""))
    if people:
        return people
    owner = str(cfg.get("owner") or "").strip()
    return [owner] if owner else []


def is_feishu_notify_configured() -> bool:
    return is_feishu_webhook_configured() or is_feishu_app_notify_configured()


def list_secure_labels(*, lang: str = "zh") -> List[Dict[str, str]]:
    """Return available secure labels for the current identity: [{id, name, description}]."""
    params = {"page_size": 10, "lang": lang}
    labels: List[Dict[str, str]] = []
    page_token = ""
    use_app = is_feishu_app_configured()
    while True:
        query = dict(params)
        if page_token:
            query["page_token"] = page_token
        if use_app:
            # 已配置应用时只用应用身份，不再回退 lark-cli（避免刷授权错误）
            data = _api("GET", "/open-apis/drive/v2/my_secure_labels", params=query)
        else:
            data = _list_secure_labels_cli(query)
        items = data.get("items") or data.get("secure_labels") or []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                lid = str(item.get("id") or item.get("label_id") or "").strip()
                name = str(item.get("name") or item.get("label_name") or "").strip()
                if lid:
                    labels.append({
                        "id": lid,
                        "name": name,
                        "description": str(item.get("description") or ""),
                    })
        page_token = str(data.get("page_token") or data.get("next_page_token") or "").strip()
        if not page_token or not data.get("has_more"):
            break
    return labels


def _list_secure_labels_cli(params: Dict[str, Any]) -> Dict[str, Any]:
    if not lark_cli_available():
        raise FeishuError("无法查询密级标签：请配置飞书应用或登录 lark-cli")
    ensure_lark_user_auth()
    import json as _json
    from web_app.lark_cli_runner import write_lark_json
    params_path = write_lark_json(params, prefix="secure-label-params")
    try:
        raw = run_lark([
            "api", "GET", "/open-apis/drive/v2/my_secure_labels",
            "--as", "user",
            "--params", f"@{params_path}",
        ])
    except LarkCliError as exc:
        raise FeishuError(str(exc)) from exc
    return raw.get("data") if isinstance(raw.get("data"), dict) else (raw if isinstance(raw, dict) else {})


def resolve_secure_label_id(want: str = "") -> str:
    """Resolve configured label name/id (default S2) to Feishu label id."""
    target = (want or get_feishu_config().get("secure_label") or DEFAULT_SECURE_LABEL).strip()
    if not target:
        return ""
    if target in _secure_label_cache:
        return _secure_label_cache[target]
    # Numeric / long digit id passed directly
    if target.isdigit() and len(target) >= 8:
        _secure_label_cache[target] = target
        return target
    labels = list_secure_labels()
    picked = _pick_secure_label(labels, target)
    if not picked:
        names = "、".join(f"{x.get('name')}({x.get('id')})" for x in labels) or "(无可用标签)"
        raise FeishuError(f"未找到密级标签「{target}」，可用: {names}")
    _secure_label_cache[target] = picked
    return picked


def _pick_secure_label(labels: Sequence[Dict[str, str]] | List[Dict[str, str]], want: str) -> str:
    want_l = want.strip().lower()
    if not want_l:
        return ""
    # 1) exact id
    for item in labels:
        if str(item.get("id") or "") == want:
            return str(item["id"])
    # 2) exact name
    for item in labels:
        if str(item.get("name") or "").strip() == want:
            return str(item["id"])
    # 3) name startswith, prefer S2-内部公开 for "S2"
    starts = [item for item in labels if str(item.get("name") or "").startswith(want)]
    if starts:
        for item in starts:
            name = str(item.get("name") or "")
            if "内部公开" in name or name.upper().startswith("S2-"):
                return str(item["id"])
        return str(starts[0]["id"])
    # 4) contains
    for item in labels:
        name = str(item.get("name") or "")
        if want in name or want_l in name.lower():
            return str(item["id"])
    return ""


def set_secure_label(file_token: str, file_type: str, label_id: str = "") -> None:
    """Set secure label on a sheet/file. file_type: sheet|file|docx|bitable|..."""
    global _secure_label_unavailable
    if _secure_label_unavailable:
        raise FeishuError(_secure_label_unavailable)
    token = (file_token or "").strip()
    typ = (file_type or "").strip().lower()
    if not token or not typ:
        return
    lid = (label_id or "").strip() or resolve_secure_label_id()
    if not lid:
        return
    body = {"id": lid}
    params = {"type": typ}

    def _mark_unavailable(exc: BaseException) -> None:
        global _secure_label_unavailable
        text = str(exc)
        if "99991679" in text or "Permission denied" in text or "docs:secure_label" in text:
            _secure_label_unavailable = (
                "飞书应用缺少 docs:secure_label 权限，已跳过后续密级设置。"
                "请在开放平台开通该权限并发布后重试；密级不影响表格/HTML 导出本身。"
            )

    def _should_retry_with_user(exc: BaseException) -> bool:
        text = str(exc or "").lower()
        return any(
            hint in text
            for hint in (
                "invalid access token",
                "please make a request with token attached",
                "authorization",
                "access token",
            )
        )

    if is_feishu_app_configured():
        try:
            _api(
                "PATCH",
                f"/open-apis/drive/v2/files/{token}/secure_label",
                params=params,
                json_body=body,
            )
            return
        except FeishuError as exc:
            _mark_unavailable(exc)
            # 某些 file/html 资源由用户身份创建或归属在用户空间，应用 token 会报鉴权错误；
            # 这类场景回退到 user token 重试一次，避免导出成功但密级设置失败。
            if _secure_label_unavailable or not _should_retry_with_user(exc):
                raise

    if not lark_cli_available():
        raise FeishuError("无法设置密级：请配置飞书应用（推荐）或登录 lark-cli（需 docs:secure_label）")
    ensure_lark_user_auth()
    from web_app.lark_cli_runner import write_lark_json
    data_path = write_lark_json(body, prefix="secure-label-body")
    params_path = write_lark_json(params, prefix="secure-label-q")
    try:
        run_lark([
            "api", "PATCH", f"/open-apis/drive/v2/files/{token}/secure_label",
            "--as", "user",
            "--params", f"@{params_path}",
            "--data", f"@{data_path}",
        ])
    except LarkCliError as exc:
        _mark_unavailable(exc)
        raise FeishuError(str(exc)) from exc


def apply_default_secure_label(file_token: str, file_type: str) -> bool:
    """Best-effort apply configured default secure label (S2). Returns True on success."""
    if _secure_label_unavailable:
        return False
    try:
        set_secure_label(file_token, file_type)
        print(
            f"[FEISHU] 已设置密级 {get_feishu_config().get('secure_label') or DEFAULT_SECURE_LABEL} "
            f"type={file_type} token={file_token[:12]}…",
            flush=True,
        )
        return True
    except Exception as exc:
        # 权限不足时只提示一次，避免每个 HTML 刷屏
        if _secure_label_unavailable:
            print(f"[FEISHU] {_secure_label_unavailable}", flush=True)
        else:
            print(f"[FEISHU] 设置密级失败 type={file_type}: {exc}", flush=True)
        return False


def test_feishu_connection() -> Dict[str, Any]:
    if not is_feishu_app_configured():
        raise FeishuError("请先填写飞书 App ID 和 App Secret")
    token = _tenant_access_token()
    return {"ok": True, "token_prefix": token[:8] + "…", "via": "app"}


def _http_client() -> httpx.Client:
    global _http
    if _http is None:
        _http = httpx.Client(timeout=60.0)
    return _http


def _tenant_access_token() -> str:
    cfg = get_feishu_config()
    if not cfg["app_id"] or not cfg["app_secret"]:
        raise FeishuError("未配置飞书 App ID / App Secret")
    now = time.time()
    if (
        _token_cache.get("token")
        and _token_cache.get("app_id") == cfg["app_id"]
        and now < float(_token_cache.get("expire_at") or 0) - 60
    ):
        return str(_token_cache["token"])
    url = f"{cfg['open_base']}/open-apis/auth/v3/tenant_access_token/internal"
    try:
        resp = _http_client().post(
            url,
            json={"app_id": cfg["app_id"], "app_secret": cfg["app_secret"]},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        raise FeishuError(f"获取飞书 tenant_access_token 失败: {exc}") from exc
    if data.get("code") not in (0, "0", None) and "tenant_access_token" not in data:
        raise FeishuError(str(data.get("msg") or data.get("message") or "获取飞书 token 失败"))
    token = str(data.get("tenant_access_token") or "").strip()
    if not token:
        raise FeishuError(str(data.get("msg") or "飞书未返回 tenant_access_token"))
    _token_cache["token"] = token
    _token_cache["app_id"] = cfg["app_id"]
    _token_cache["expire_at"] = now + int(data.get("expire") or 7200)
    return token


def _api(method: str, path: str, *, json_body: Any = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = get_feishu_config()
    url = path if path.startswith("http") else f"{cfg['open_base']}{path}"
    headers = {
        "Authorization": f"Bearer {_tenant_access_token()}",
        "Content-Type": "application/json",
    }
    try:
        resp = _http_client().request(method, url, json=json_body, params=params, headers=headers, timeout=60.0)
        data = resp.json()
    except httpx.HTTPError as exc:
        raise FeishuError(f"飞书 API 请求失败: {exc}") from exc
    except ValueError as exc:
        raise FeishuError(f"飞书 API 响应不是 JSON: {exc}") from exc
    code = data.get("code")
    if code not in (0, "0", None):
        raise FeishuError(str(data.get("msg") or data.get("message") or f"飞书 API 错误 ({code})"))
    payload = data.get("data")
    return payload if isinstance(payload, dict) else data


def create_spreadsheet(title: str, folder_token: str = "") -> Dict[str, str]:
    folder = normalize_folder_token(folder_token or get_feishu_config().get("folder_token") or "")
    if is_feishu_app_configured():
        body: Dict[str, Any] = {"title": title}
        if folder:
            body["folder_token"] = folder
        data = _api("POST", "/open-apis/sheets/v3/spreadsheets", json_body=body)
        sheet = data.get("spreadsheet") if isinstance(data.get("spreadsheet"), dict) else data
        token = str(sheet.get("spreadsheet_token") or sheet.get("token") or "").strip()
        url = str(sheet.get("url") or "").strip()
        if not token:
            raise FeishuError("创建飞书表格成功但未返回 spreadsheet_token")
        if not url:
            url = f"https://transsioner.feishu.cn/sheets/{token}"
        try:
            share_spreadsheet_in_tenant(token)
        except Exception as exc:
            print(f"[FEISHU] 设置租户内链接分享失败: {exc}", flush=True)
        apply_default_secure_label(token, "sheet")
        return {"token": token, "url": url, "title": str(sheet.get("title") or title)}

    if not lark_cli_available():
        raise FeishuError("请在设置中配置飞书应用 App ID / App Secret，或在本机安装并登录 lark-cli")
    try:
        ensure_lark_user_auth()
        args = ["sheets", "+create", "--as", "user", "--title", title]
        if folder:
            args.extend(["--folder-token", folder])
        created = run_lark(args)
    except LarkCliError as exc:
        raise FeishuError(str(exc)) from exc
    spreadsheet = created.get("spreadsheet") if isinstance(created.get("spreadsheet"), dict) else created
    token = str(spreadsheet.get("spreadsheet_token") or spreadsheet.get("token") or "").strip()
    url = str(spreadsheet.get("url") or "").strip()
    if not token:
        raise FeishuError("创建飞书表格成功但未返回 spreadsheet_token")
    if not url:
        url = f"https://transsioner.feishu.cn/sheets/{token}"
    apply_default_secure_label(token, "sheet")
    return {"token": token, "url": url, "title": title}


def list_sheets(token: str) -> List[Dict[str, str]]:
    if is_feishu_app_configured():
        data = _api("GET", f"/open-apis/sheets/v3/spreadsheets/{token}/sheets/query")
        sheets = data.get("sheets") or []
        out: List[Dict[str, str]] = []
        if isinstance(sheets, list):
            for item in sheets:
                if not isinstance(item, dict):
                    continue
                sheet_id = str(item.get("sheet_id") or item.get("sheetId") or "").strip()
                title = str(item.get("title") or "").strip()
                if sheet_id:
                    out.append({"sheet_id": sheet_id, "title": title})
        return out
    try:
        info = run_lark(["sheets", "+info", "--as", "user", "--spreadsheet-token", token])
    except LarkCliError as exc:
        raise FeishuError(str(exc)) from exc
    return _sheet_list_from_info(info)


def update_sheet_props(
    token: str,
    sheet_id: str,
    *,
    title: str = "",
    frozen_row_count: Optional[int] = None,
) -> None:
    if is_feishu_app_configured():
        props: Dict[str, Any] = {"sheetId": sheet_id}
        if title:
            props["title"] = title
        if frozen_row_count is not None:
            props["frozenRowCount"] = int(frozen_row_count)
        _api(
            "POST",
            f"/open-apis/sheets/v2/spreadsheets/{token}/sheets_batch_update",
            json_body={"requests": [{"updateSheet": {"properties": props}}]},
        )
        return
    args = [
        "sheets", "+update-sheet", "--as", "user",
        "--spreadsheet-token", token,
        "--sheet-id", sheet_id,
    ]
    if title:
        args.extend(["--title", title])
    if frozen_row_count is not None:
        args.extend(["--frozen-row-count", str(int(frozen_row_count))])
    try:
        run_lark(args)
    except LarkCliError as exc:
        raise FeishuError(str(exc)) from exc


def add_sheet(token: str, title: str, index: int = 1) -> str:
    if is_feishu_app_configured():
        data = _api(
            "POST",
            f"/open-apis/sheets/v2/spreadsheets/{token}/sheets_batch_update",
            json_body={
                "requests": [{
                    "addSheet": {
                        "properties": {"title": title, "index": int(index)},
                    }
                }]
            },
        )
        replies = data.get("replies") or []
        if replies and isinstance(replies[0], dict):
            added = (replies[0].get("addSheet") or {}).get("properties") or {}
            sheet_id = str(added.get("sheetId") or added.get("sheet_id") or "").strip()
            if sheet_id:
                return sheet_id
        for item in list_sheets(token):
            if item.get("title") == title:
                return item["sheet_id"]
        raise FeishuError(f"创建工作表失败：{title}")
    try:
        second = run_lark([
            "sheets", "+create-sheet", "--as", "user",
            "--spreadsheet-token", token,
            "--title", title,
            "--index", str(index),
        ])
    except LarkCliError as exc:
        raise FeishuError(str(exc)) from exc
    for key in ("sheet_id", "sheetId"):
        value = second.get(key)
        if value:
            return str(value)
    sheet = second.get("sheet")
    if isinstance(sheet, dict):
        return str(sheet.get("sheet_id") or sheet.get("sheetId") or "")
    for item in list_sheets(token):
        if item.get("title") == title:
            return item["sheet_id"]
    raise FeishuError(f"创建工作表失败：{title}")


def write_values(token: str, a1_range: str, values: List[List[Any]]) -> None:
    if is_feishu_app_configured():
        _api(
            "PUT",
            f"/open-apis/sheets/v2/spreadsheets/{token}/values",
            json_body={"valueRange": {"range": a1_range, "values": values}},
        )
        return
    from web_app.lark_cli_runner import write_lark_json
    payload_path = write_lark_json(
        {"valueRange": {"range": a1_range, "values": values}},
        prefix="sheet-values",
    )
    try:
        run_lark([
            "api", "PUT", f"/open-apis/sheets/v2/spreadsheets/{token}/values",
            "--as", "user",
            "--data", f"@{payload_path}",
        ])
    except LarkCliError as exc:
        raise FeishuError(str(exc)) from exc


def feishu_link_cell(text: str, url: str) -> Dict[str, str]:
    """Cell payload that Feishu Sheets renders as a hyperlink."""
    return {"type": "url", "text": text or url, "link": url}


def create_folder(name: str, parent_token: str = "") -> Dict[str, str]:
    """Create a Drive folder. Returns {token, url, name}."""
    parent = normalize_folder_token(parent_token or get_feishu_config().get("folder_token") or "")
    if is_feishu_app_configured():
        body: Dict[str, Any] = {"name": name}
        if parent:
            body["folder_token"] = parent
        data = _api("POST", "/open-apis/drive/v1/files/create_folder", json_body=body)
        token = str(data.get("token") or "").strip()
        if not token and isinstance(data.get("file"), dict):
            token = str(data["file"].get("token") or "").strip()
        url = str(data.get("url") or "").strip()
        if token and not url:
            url = f"https://transsioner.feishu.cn/drive/folder/{token}"
        if not token:
            raise FeishuError("创建文件夹成功但未返回 token")
        return {"token": token, "url": url, "name": name}
    args = ["drive", "+create-folder", "--as", "user", "--name", name]
    if parent:
        args.extend(["--folder-token", parent])
    try:
        data = run_lark(args)
    except LarkCliError as exc:
        raise FeishuError(str(exc)) from exc
    token = str(data.get("token") or data.get("folder_token") or "").strip()
    if not token and isinstance(data.get("data"), dict):
        token = str(data["data"].get("token") or "").strip()
    url = str(data.get("url") or "").strip()
    if token and not url:
        url = f"https://transsioner.feishu.cn/drive/folder/{token}"
    if not token:
        raise FeishuError("创建文件夹成功但未返回 token")
    return {"token": token, "url": url, "name": name}


def task_run_stamp(
    task: Optional[Dict[str, Any]] = None,
    *,
    when: str = "",
    fallback_now: bool = True,
) -> str:
    """Compact execution-time stamp for Feishu file/folder names: ``YYYYMMDD_HHMMSS``."""
    from datetime import datetime

    raw = (when or "").strip()
    if not raw and task:
        raw = str(task.get("completed_at") or task.get("created_at") or "").strip()
    dt: Optional[datetime] = None
    if raw:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
        except ValueError:
            dt = None
    if dt is None and fallback_now:
        dt = datetime.now()
    if dt is None:
        return ""
    return dt.strftime("%Y%m%d_%H%M%S")


def task_result_folder_name(
    from_tag: str,
    to_tag: str,
    *,
    run_stamp: str = "",
) -> str:
    """Folder name under the configured Drive root: ``fromTag-toTag_YYYYMMDD_HHMMSS``."""
    import re

    def clean(tag: str) -> str:
        text = str(tag or "").strip()
        text = re.sub(r'[\\/:*?"<>|\s]+', "_", text)
        return text.strip("._") or "unknown"

    left = clean(from_tag)
    right = clean(to_tag)
    name = f"{left}-{right}" if left != right else left
    stamp = str(run_stamp or "").strip()
    if stamp:
        name = f"{name}_{stamp}"
    return name[:200]


def list_folder_children(folder_token: str) -> List[Dict[str, str]]:
    """List files/folders directly under a Drive folder."""
    parent = normalize_folder_token(folder_token)
    if not parent:
        return []
    out: List[Dict[str, str]] = []
    page_token = ""
    while True:
        params: Dict[str, Any] = {"folder_token": parent, "page_size": 200}
        if page_token:
            params["page_token"] = page_token
        if is_feishu_app_configured():
            data = _api("GET", "/open-apis/drive/v1/files", params=params)
        else:
            if not lark_cli_available():
                break
            ensure_lark_user_auth()
            args = [
                "api", "GET", "/open-apis/drive/v1/files",
                "--as", "user",
                "--params", f"folder_token={parent}&page_size=200",
            ]
            if page_token:
                args[-1] = f"folder_token={parent}&page_size=200&page_token={page_token}"
            try:
                raw = run_lark(args)
            except LarkCliError as exc:
                raise FeishuError(str(exc)) from exc
            data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
        files = data.get("files") if isinstance(data, dict) else None
        if isinstance(files, list):
            for item in files:
                if not isinstance(item, dict):
                    continue
                token = str(item.get("token") or "").strip()
                name = str(item.get("name") or "").strip()
                typ = str(item.get("type") or item.get("file_type") or "").strip()
                if token:
                    out.append({"token": token, "name": name, "type": typ})
        page_token = str((data or {}).get("next_page_token") or "").strip()
        if not page_token or not (data or {}).get("has_more"):
            break
    return out


def ensure_folder(name: str, parent_token: str = "") -> Dict[str, str]:
    """Find an existing child folder by name, or create it under parent."""
    parent = normalize_folder_token(parent_token or get_feishu_config().get("folder_token") or "")
    folder_name = (name or "").strip()
    if not folder_name:
        raise FeishuError("文件夹名称不能为空")
    if parent:
        try:
            for item in list_folder_children(parent):
                if item.get("name") != folder_name:
                    continue
                typ = (item.get("type") or "").lower()
                if typ and typ not in ("folder", "drive#folder"):
                    continue
                token = item.get("token") or ""
                if token:
                    return {
                        "token": token,
                        "url": f"https://transsioner.feishu.cn/drive/folder/{token}",
                        "name": folder_name,
                        "existed": "1",
                    }
        except Exception as exc:
            print(f"[FEISHU] 列举目录失败，将直接创建文件夹: {exc}", flush=True)
    created = create_folder(folder_name, parent_token=parent)
    created["existed"] = "0"
    return created


def ensure_task_result_folder(
    from_tag: str,
    to_tag: str,
    *,
    existing_token: str = "",
    run_stamp: str = "",
) -> Dict[str, str]:
    """Ensure ``{configuredRoot}/{fromTag-toTag_YYYYMMDD_HHMMSS}/`` exists and return {token,url,name}."""
    stamp = (run_stamp or "").strip() or task_run_stamp()
    name = task_result_folder_name(from_tag, to_tag, run_stamp=stamp)
    token = normalize_folder_token(existing_token)
    if token:
        try:
            # Probe: deleted / inaccessible folders must not be reused as upload parent.
            list_folder_children(token)
            return {
                "token": token,
                "url": f"https://transsioner.feishu.cn/drive/folder/{token}",
                "name": name,
                "existed": "1",
            }
        except Exception as exc:
            print(
                f"[FEISHU] 任务结果目录已失效，将重建: {token} ({exc})",
                flush=True,
            )
    parent = normalize_folder_token(get_feishu_config().get("folder_token") or "")
    folder = ensure_folder(name, parent_token=parent)
    print(
        f"[FEISHU] 任务结果目录: {name} "
        f"({'已存在' if folder.get('existed') == '1' else '新建'}) "
        f"{folder.get('url')}",
        flush=True,
    )
    return folder


def upload_drive_file(
    local_path: Path | str,
    *,
    folder_token: str = "",
    name: str = "",
) -> Dict[str, str]:
    """Upload a local file to Feishu Drive. Returns {token, url, name}."""
    path = Path(local_path)
    if not path.is_file():
        raise FeishuError(f"文件不存在: {path}")
    file_name = name or path.name
    parent = normalize_folder_token(folder_token or get_feishu_config().get("folder_token") or "")

    if is_feishu_app_configured():
        size = path.stat().st_size
        # Small/medium files: upload_all. Large files (>20MB) still try upload_all first;
        # Feishu accepts up to ~20MB here; larger should use multipart (lark-cli handles it).
        if size > 20 * 1024 * 1024:
            # Prefer CLI multipart when available.
            if lark_cli_available():
                return _upload_drive_file_cli(path, parent, file_name)
            raise FeishuError("文件超过 20MB，请改用 lark-cli 上传或缩小报告")
        cfg = get_feishu_config()
        url = f"{cfg['open_base']}/open-apis/drive/v1/files/upload_all"
        headers = {"Authorization": f"Bearer {_tenant_access_token()}"}
        form = {
            "file_name": (None, file_name),
            "parent_type": (None, "explorer"),
            "parent_node": (None, parent or ""),
            "size": (None, str(size)),
        }
        try:
            with path.open("rb") as fh:
                files = {"file": (file_name, fh)}
                resp = _http_client().post(url, headers=headers, data={k: v[1] for k, v in form.items()}, files=files, timeout=300.0)
                data = resp.json()
        except httpx.HTTPError as exc:
            raise FeishuError(f"上传文件失败: {exc}") from exc
        except ValueError as exc:
            raise FeishuError(f"上传文件响应不是 JSON: {exc}") from exc
        if data.get("code") not in (0, "0", None):
            raise FeishuError(str(data.get("msg") or data.get("message") or "上传文件失败"))
        payload = data.get("data") if isinstance(data.get("data"), dict) else data
        token = str(payload.get("file_token") or payload.get("token") or "").strip()
        open_url = str(payload.get("url") or "").strip()
        if token and not open_url:
            open_url = f"https://transsioner.feishu.cn/file/{token}"
        if not token:
            raise FeishuError("上传成功但未返回 file_token")
        try:
            _share_file_in_tenant(token)
        except Exception as exc:
            print(f"[FEISHU] 设置文件分享失败: {exc}", flush=True)
        apply_default_secure_label(token, "file")
        return {"token": token, "url": open_url, "name": file_name}

    return _upload_drive_file_cli(path, parent, file_name)


def _upload_drive_file_cli(path: Path, parent: str, file_name: str) -> Dict[str, str]:
    if not lark_cli_available():
        raise FeishuError("请配置飞书应用或安装并登录 lark-cli 后再上传文件")
    ensure_lark_user_auth()
    args = [
        "drive", "+upload", "--as", "user",
        "--file", str(path),
        "--name", file_name,
    ]
    if parent:
        args.extend(["--folder-token", parent])
    try:
        data = run_lark(args)
    except LarkCliError as exc:
        raise FeishuError(str(exc)) from exc
    token = str(data.get("file_token") or data.get("token") or "").strip()
    if not token and isinstance(data.get("data"), dict):
        token = str(data["data"].get("file_token") or data["data"].get("token") or "").strip()
    open_url = str(data.get("url") or "").strip()
    if not open_url and isinstance(data.get("data"), dict):
        open_url = str(data["data"].get("url") or "").strip()
    if token and not open_url:
        open_url = f"https://transsioner.feishu.cn/file/{token}"
    if not token:
        raise FeishuError("上传成功但未返回 file_token")
    apply_default_secure_label(token, "file")
    return {"token": token, "url": open_url, "name": file_name}


def _share_file_in_tenant(file_token: str) -> None:
    """Enable tenant link access for an uploaded Drive file (zip/html)."""
    # link_share_entity 合法值是 tenant_readable / tenant_editable，不能用 tenant_viewable
    body = {
        "external_access": False,
        "security_entity": "anyone_can_view",
        "comment_entity": "anyone_can_view",
        "share_entity": "anyone",
        "link_share_entity": "tenant_readable",
        "invite_external": False,
    }
    try:
        _api(
            "PATCH",
            f"/open-apis/drive/v1/permissions/{file_token}/public",
            params={"type": "file"},
            json_body=body,
        )
        return
    except FeishuError:
        # 部分租户对 file 类型字段更严，退化为仅开组织内可读链接
        _api(
            "PATCH",
            f"/open-apis/drive/v1/permissions/{file_token}/public",
            params={"type": "file"},
            json_body={
                "external_access": False,
                "link_share_entity": "tenant_readable",
            },
        )


def unmerge_cells(token: str, a1_range: str) -> None:
    if is_feishu_app_configured():
        _api(
            "POST",
            f"/open-apis/sheets/v2/spreadsheets/{token}/unmerge_cells",
            json_body={"range": a1_range},
        )
        return
    run_lark([
        "sheets", "+unmerge-cells", "--as", "user",
        "--spreadsheet-token", token,
        "--range", a1_range,
    ])


def merge_cells(token: str, a1_range: str, merge_type: str = "MERGE_ALL") -> None:
    if is_feishu_app_configured():
        _api(
            "POST",
            f"/open-apis/sheets/v2/spreadsheets/{token}/merge_cells",
            json_body={"range": a1_range, "mergeType": merge_type},
        )
        return
    run_lark([
        "sheets", "+merge-cells", "--as", "user",
        "--spreadsheet-token", token,
        "--range", a1_range,
        "--merge-type", merge_type,
    ])


def styles_batch_update(token: str, items: List[Dict[str, Any]]) -> None:
    if is_feishu_app_configured():
        _api(
            "PUT",
            f"/open-apis/sheets/v2/spreadsheets/{token}/styles_batch_update",
            json_body={"data": items},
        )
        return
    from web_app.lark_cli_runner import write_lark_json
    style_path = write_lark_json({"data": items}, prefix="sheet-style")
    run_lark([
        "api", "PUT",
        f"/open-apis/sheets/v2/spreadsheets/{token}/styles_batch_update",
        "--as", "user",
        "--data", f"@{style_path}",
    ])


def update_dimension(
    token: str,
    sheet_id: str,
    dimension: str,
    start: int,
    end: int,
    *,
    fixed_size: Optional[int] = None,
    visible: Optional[bool] = None,
) -> None:
    """start/end are 1-indexed inclusive (Feishu dimension_range API)."""
    start_i = max(1, int(start))
    end_i = max(start_i, int(end))
    if is_feishu_app_configured():
        props: Dict[str, Any] = {}
        if visible is not None:
            props["visible"] = bool(visible)
        if fixed_size is not None:
            props["fixedSize"] = int(fixed_size)
        if not props:
            return
        _api(
            "PUT",
            f"/open-apis/sheets/v2/spreadsheets/{token}/dimension_range",
            json_body={
                "dimension": {
                    "sheetId": sheet_id,
                    "majorDimension": dimension,
                    "startIndex": start_i,
                    "endIndex": end_i,
                },
                "dimensionProperties": props,
            },
        )
        return
    args = [
        "sheets", "+update-dimension", "--as", "user",
        "--spreadsheet-token", token,
        "--sheet-id", sheet_id,
        "--dimension", dimension,
        "--start-index", str(start_i),
        "--end-index", str(end_i),
    ]
    if fixed_size is not None:
        args.extend(["--fixed-size", str(int(fixed_size))])
    if visible is False:
        args.append("--visible=false")
    elif visible is True:
        args.append("--visible=true")
    run_lark(args)


def add_columns(token: str, sheet_id: str, length: int) -> None:
    if length <= 0:
        return
    if is_feishu_app_configured():
        _api(
            "POST",
            f"/open-apis/sheets/v2/spreadsheets/{token}/insert_dimension_range",
            json_body={
                "dimension": {
                    "sheetId": sheet_id,
                    "majorDimension": "COLUMNS",
                    "startIndex": 20,
                    "endIndex": 20 + int(length),
                },
                "inheritStyle": "BEFORE",
            },
        )
        return
    run_lark([
        "sheets", "+add-dimension", "--as", "user",
        "--spreadsheet-token", token,
        "--sheet-id", sheet_id,
        "--dimension", "COLUMNS",
        "--length", str(int(length)),
    ])


def set_dropdown(
    token: str,
    a1_range: str,
    options: List[str],
    *,
    colors: Optional[List[str]] = None,
    highlight: bool = True,
    multiple: bool = False,
) -> None:
    """Apply list data validation (dropdown) on a cell range."""
    if not options:
        return
    validation: Dict[str, Any] = {
        "conditionValues": options,
        "options": {
            "multipleValues": multiple,
            "highlightValidData": bool(highlight and colors),
        },
    }
    if highlight and colors and len(colors) == len(options):
        validation["options"]["colors"] = colors
    body = {
        "range": a1_range,
        "dataValidationType": "list",
        "dataValidation": validation,
    }
    if is_feishu_app_configured():
        _api(
            "POST",
            f"/open-apis/sheets/v2/spreadsheets/{token}/dataValidation",
            json_body=body,
        )
        return
    import json as _json

    args = [
        "sheets", "+set-dropdown", "--as", "user",
        "--spreadsheet-token", token,
        "--range", a1_range,
        "--condition-values", _json.dumps(options, ensure_ascii=False),
    ]
    if highlight and colors and len(colors) == len(options):
        args.extend(["--highlight", "--colors", _json.dumps(colors)])
    if multiple:
        args.append("--multiple")
    run_lark(args)


def delete_dropdown(token: str, a1_range: str) -> None:
    if is_feishu_app_configured():
        _api(
            "DELETE",
            f"/open-apis/sheets/v2/spreadsheets/{token}/dataValidation",
            json_body={"range": a1_range},
        )
        return
    import json as _json

    run_lark([
        "sheets", "+delete-dropdown", "--as", "user",
        "--spreadsheet-token", token,
        "--ranges", _json.dumps([a1_range]),
    ])


def add_rows(token: str, sheet_id: str, length: int) -> None:
    if length <= 0:
        return
    if is_feishu_app_configured():
        _api(
            "POST",
            f"/open-apis/sheets/v2/spreadsheets/{token}/insert_dimension_range",
            json_body={
                "dimension": {
                    "sheetId": sheet_id,
                    "majorDimension": "ROWS",
                    "startIndex": 200,
                    "endIndex": 200 + int(length),
                },
                "inheritStyle": "BEFORE",
            },
        )
        return
    run_lark([
        "sheets", "+add-dimension", "--as", "user",
        "--spreadsheet-token", token,
        "--sheet-id", sheet_id,
        "--dimension", "ROWS",
        "--length", str(int(length)),
    ])


def share_spreadsheet_in_tenant(token: str) -> None:
    """Allow anyone in the tenant to open/edit via link."""
    _api(
        "PATCH",
        f"/open-apis/drive/v1/permissions/{token}/public",
        params={"type": "sheet"},
        json_body={
            "external_access": False,
            "security_entity": "anyone_can_view",
            "comment_entity": "anyone_can_view",
            "share_entity": "anyone",
            "link_share_entity": "tenant_editable",
            "invite_external": False,
        },
    )


def transfer_spreadsheet_owner(token: str, owner: str = "") -> bool:
    """Transfer sheet ownership to the configured or given user.

    owner accepts Feishu email, open_id (ou_...), or user_id.
    Keeps the app as collaborator so later refresh/write still works.
    Returns True if transfer was attempted and succeeded.
    """
    if not is_feishu_app_configured():
        return False
    target = (owner or get_feishu_config().get("owner") or "").strip()
    if not target:
        return False
    member_type, member_id = _owner_member(target)
    stay_put = bool(normalize_folder_token(get_feishu_config().get("folder_token") or ""))
    _api(
        "POST",
        f"/open-apis/drive/v1/permissions/{token}/members/transfer_owner",
        params={"type": "sheet"},
        json_body={
            "member_type": member_type,
            "member_id": member_id,
            "remove_old_owner": False,
            "stay_put": stay_put,
        },
    )
    print(f"[FEISHU] 已将表格所有者转移给 {member_type}={member_id}", flush=True)
    return True


def _owner_member(owner: str) -> tuple[str, str]:
    text = owner.strip()
    if "@" in text:
        return "email", text
    if text.startswith("ou_"):
        return "openid", text
    return "userid", text


def _im_receive_id(target: str) -> tuple[str, str]:
    """Map configured recipient to Feishu IM receive_id_type + receive_id."""
    text = (target or "").strip()
    if not text:
        raise FeishuError("未指定飞书通知接收人")
    if text.startswith("oc_"):
        return "chat_id", text
    if text.startswith("ou_"):
        return "open_id", text
    if text.startswith("on_"):
        return "union_id", text
    if "@" in text:
        return "email", text
    return "user_id", text


def _sheet_list_from_info(info: Dict[str, Any]) -> List[Dict[str, str]]:
    sheets = info.get("sheets") or info.get("sheet") or []
    if isinstance(sheets, dict):
        sheets = sheets.get("sheets") or []
    out: List[Dict[str, str]] = []
    if not isinstance(sheets, list):
        return out
    for item in sheets:
        if not isinstance(item, dict):
            continue
        sheet_id = str(item.get("sheet_id") or item.get("sheetId") or "").strip()
        title = str(item.get("title") or "").strip()
        if sheet_id:
            out.append({"sheet_id": sheet_id, "title": title})
    return out


# ── Custom bot webhook notify ───────────────────────────

def _webhook_sign(secret: str, timestamp: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def send_webhook_message(
    payload: Dict[str, Any],
    *,
    webhook_url: str = "",
    webhook_secret: str = "",
) -> Dict[str, Any]:
    """POST a custom-bot payload to Feishu webhook. Soft-usable without app credentials."""
    cfg = get_feishu_config()
    url = (webhook_url or cfg.get("webhook_url") or "").strip()
    if not url:
        raise FeishuError("未配置飞书机器人 Webhook")
    secret = (webhook_secret or cfg.get("webhook_secret") or "").strip()
    body = dict(payload)
    if secret:
        ts = str(int(time.time()))
        body["timestamp"] = ts
        body["sign"] = _webhook_sign(secret, ts)
    client = _http_client()
    resp = client.post(url, json=body, timeout=20.0)
    try:
        data = resp.json()
    except Exception:
        data = {"StatusCode": resp.status_code, "msg": resp.text[:200]}
    if not isinstance(data, dict):
        data = {"raw": data}
    code = data.get("code")
    status_code = data.get("StatusCode")
    # Custom bot: {code:0} or legacy {StatusCode:0}
    ok = (code in (0, "0")) or (status_code in (0, "0"))
    if not ok and code is None and status_code is None and resp.is_success:
        ok = True
    if not ok:
        raise FeishuError(str(data.get("msg") or data.get("StatusMessage") or data))
    return data


def _notify_ok(status: str) -> bool:
    return str(status or "").strip().lower() == "completed"


def _md_field(label: str, value: str, *, short: bool = True) -> Dict[str, Any]:
    return {
        "is_short": short,
        "text": {"tag": "lark_md", "content": f"**{label}**\n{value}"},
    }


def _interval_field(from_tag: str, to_tag: str) -> Dict[str, Any]:
    return _md_field(
        "升级区间",
        f"`{str(from_tag or '?').strip()} → {str(to_tag or '?').strip()}`",
        short=False,
    )


def _elapsed_field(elapsed: Any) -> Optional[Dict[str, Any]]:
    if elapsed in ("", None):
        return None
    try:
        return _md_field("耗时", f"{int(elapsed)}s")
    except (TypeError, ValueError):
        return None


def _error_field(err: str) -> Optional[Dict[str, Any]]:
    text = str(err or "").strip()
    if not text:
        return None
    return _md_field("备注", text[:300], short=False)


def _interactive_card(
    title: str,
    template: str,
    fields: List[Dict[str, Any]],
    actions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    elements: List[Dict[str, Any]] = [{"tag": "div", "fields": fields}]
    if actions:
        elements.append({"tag": "action", "actions": actions})
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": template,
            },
            "elements": elements,
        },
    }


def _task_notify_card(task: Dict[str, Any], *, status: str) -> Dict[str, Any]:
    """Build an interactive card for analysis task completion / failure."""
    ok = _notify_ok(status)
    title = "GKI 分析任务完成" if ok else "GKI 分析任务失败"
    template = "green" if ok else "red"
    from_tag = str(task.get("from_tag") or "").strip()
    to_tag = str(task.get("to_tag") or "").strip()
    repo = str(task.get("repo") or "").strip()
    task_id = str(task.get("id") or "").strip()
    total = task.get("total") or task.get("analyzed") or ""
    err = str(task.get("error_msg") or "").strip()
    checklist = str(task.get("feishu_checklist_url") or "").strip()
    report = str(
        task.get("feishu_module_report_folder")
        or task.get("feishu_module_report_url")
        or ""
    ).strip()

    fields = [
        _md_field("仓库", repo or "-"),
        _md_field("状态", "成功" if ok else "失败"),
        _interval_field(from_tag, to_tag),
        _md_field("Task ID", f"`{task_id or '-'}`"),
    ]
    if total not in ("", None):
        fields.append(_md_field("Patch 数", str(total)))
    elapsed = _elapsed_field(task.get("elapsed_seconds"))
    if elapsed:
        fields.append(elapsed)
    err_field = _error_field(err)
    if err_field:
        fields.append(err_field)

    actions: List[Dict[str, Any]] = []
    if checklist:
        actions.append({
            "tag": "button",
            "text": {"tag": "plain_text", "content": "打开验收表格"},
            "type": "primary",
            "url": checklist,
        })
    if report:
        actions.append({
            "tag": "button",
            "text": {"tag": "plain_text", "content": "模块代码详情"},
            "type": "default",
            "url": report,
        })
    return _interactive_card(title, template, fields, actions or None)


def _crash_notify_card(crash: Dict[str, Any], *, status: str) -> Dict[str, Any]:
    """Card for crash / 故障诊断 completion or failure."""
    ok = _notify_ok(status)
    title = "GKI 故障诊断完成" if ok else "GKI 故障诊断失败"
    template = "green" if ok else "red"
    crash_id = str(crash.get("id") or "").strip()
    summary = crash.get("crash_summary") if isinstance(crash.get("crash_summary"), dict) else {}
    from_tag = str(crash.get("from_tag") or "").strip()
    to_tag = str(crash.get("to_tag") or "").strip()
    mode = str((summary or {}).get("analysis_mode") or "").strip()
    current_tag_mode = mode == "current_tag" or not from_tag

    caused_raw = crash.get("is_caused_by_merge")
    if caused_raw in (1, True, "1"):
        caused_text = "是"
    elif caused_raw in (0, False, "0"):
        caused_text = "否"
    else:
        caused_text = "-"
    suspected = crash.get("suspected_patches")
    suspected_n = len(suspected) if isinstance(suspected, list) else None
    fixes = crash.get("fix_commits")
    fix_n = len(fixes) if isinstance(fixes, list) else None
    confidence = summary.get("confidence") if isinstance(summary, dict) else None
    crash_type = str((summary or {}).get("crash_type") or "").strip()
    crash_fn = str((summary or {}).get("crash_function") or "").strip()
    latest = (summary or {}).get("latest_compare")
    latest = latest if isinstance(latest, dict) else {}

    fields = [
        _md_field("状态", "成功" if ok else "失败"),
        _md_field("任务 ID", f"`{crash_id or '-'}`"),
    ]
    if current_tag_mode:
        fields.append(_md_field("当前 Tag", f"`{to_tag or from_tag or '?'}`", short=False))
    else:
        fields.append(_interval_field(from_tag, to_tag))

    if ok:
        if crash_type or crash_fn:
            point = " / ".join(
                p for p in (
                    crash_type or "",
                    f"`{crash_fn}`" if crash_fn else "",
                ) if p
            )
            fields.append(_md_field("崩溃点", point or "-", short=False))
        if not current_tag_mode:
            fields.append(_md_field("合入引起", caused_text))
            if suspected_n is not None:
                fields.append(_md_field("疑似引入", str(suspected_n)))
        if fix_n is not None:
            fields.append(_md_field("社区修复", str(fix_n)))
            if fix_n > 0 and isinstance(fixes, list):
                from web_app.crash_fix_search import community_commit_url

                search_meta = (summary or {}).get("fix_search")
                fetch_src = (
                    str(search_meta.get("fetch_source") or "")
                    if isinstance(search_meta, dict)
                    else ""
                )
                lines: List[str] = []
                for fc in fixes[:5]:
                    if not isinstance(fc, dict):
                        continue
                    sha = str(fc.get("sha") or "").strip()
                    title_txt = str(fc.get("title") or "").strip()
                    conf = str(fc.get("confidence") or "").strip()
                    url = str(fc.get("commit_url") or "").strip() or community_commit_url(sha, fetch_src)
                    if url and sha:
                        bit = f"[`{sha[:12]}`]({url})"
                    elif sha:
                        bit = f"`{sha[:12]}`"
                    else:
                        bit = "-"
                    if title_txt:
                        bit += f" {title_txt[:72]}"
                    if conf:
                        bit += f" ({conf})"
                    lines.append(bit)
                if lines:
                    more = f"\n…共 {fix_n} 笔" if fix_n > 5 else ""
                    fields.append(_md_field("修复 Patch", "\n".join(lines) + more, short=False))
        latest_status = str(latest.get("latest_status") or "").strip()
        if latest_status:
            status_label = {
                "likely_fixed": "最新已避开该路径",
                "still_buggy": "最新仍可能存在",
                "cannot_compare": "无法对照最新源码",
            }.get(latest_status, latest_status)
            fields.append(_md_field("最新源码", status_label))
        if confidence not in ("", None):
            fields.append(_md_field("置信度", str(confidence)))
    elapsed = _elapsed_field(crash.get("elapsed_seconds"))
    if elapsed:
        fields.append(elapsed)
    err_field = _error_field(str(crash.get("error_msg") or ""))
    if err_field:
        fields.append(err_field)
    return _interactive_card(title, template, fields)


def _upgrade_notify_card(job: Dict[str, Any], *, status: str) -> Dict[str, Any]:
    """Card for patch 入库 / upgrade job completion or failure."""
    ok = _notify_ok(status)
    title = "GKI 入库任务完成" if ok else "GKI 入库任务失败"
    template = "green" if ok else "red"
    job_id = str(job.get("id") or "").strip()
    repo = str(job.get("repo") or job.get("target_repo_dir") or "").strip()
    phase = str(job.get("phase") or "").strip()
    commit_sha = str(job.get("commit_sha") or "").strip()
    timings = (job.get("options") or {}).get("phase_timings") or {}
    elapsed = timings.get("total_wall_sec") if isinstance(timings, dict) else None

    fields = [
        _md_field("目标仓", repo or "-"),
        _md_field("状态", "成功" if ok else "失败"),
        _interval_field(str(job.get("from_tag") or ""), str(job.get("to_tag") or "")),
        _md_field("Job ID", f"`{job_id or '-'}`"),
    ]
    if phase:
        fields.append(_md_field("阶段", phase))
    if commit_sha:
        fields.append(_md_field("Commit", f"`{commit_sha[:12]}`"))
    elapsed_field = _elapsed_field(elapsed)
    if elapsed_field:
        fields.append(elapsed_field)
    err_field = _error_field(str(job.get("error_msg") or ""))
    if err_field:
        fields.append(err_field)
    return _interactive_card(title, template, fields)


def _dispatch_interactive_notify(
    payload: Dict[str, Any],
    *,
    log_id: str,
    kind: str,
    status: str,
) -> Optional[Dict[str, Any]]:
    """Webhook first, else app IM. Shared by analysis / crash / upgrade."""
    if not is_feishu_notify_configured():
        return None
    if is_feishu_webhook_configured():
        result = send_webhook_message(payload)
        via = "webhook"
    else:
        people = get_notify_recipients()
        result = send_app_im_to_recipients(
            people,
            msg_type="interactive",
            content=payload.get("card") or {},
        )
        via = "app"
        n_fail = len(result.get("failed") or [])
        print(
            f"[FEISHU] 应用私信 {len(result.get('sent') or [])} 人成功"
            + (f"，{n_fail} 人失败" if n_fail else ""),
            flush=True,
        )
    print(f"[FEISHU] 已发送{kind}通知 id={log_id} status={status} via={via}", flush=True)
    return result


def send_app_im_message(
    *,
    receive_id: str = "",
    msg_type: str = "text",
    content: Any,
) -> Dict[str, Any]:
    """Send a message via the configured Feishu app (IM API, not custom-bot webhook)."""
    if not is_feishu_app_configured():
        raise FeishuError("未配置飞书 App ID / App Secret")
    target = (receive_id or "").strip()
    if not target:
        people = get_notify_recipients()
        if not people:
            raise FeishuError("未指定飞书通知接收人")
        if len(people) == 1:
            target = people[0]
        else:
            return send_app_im_to_recipients(people, msg_type=msg_type, content=content)
    id_type, ident = _im_receive_id(target)
    if isinstance(content, (dict, list)):
        body_content = json.dumps(content, ensure_ascii=False)
    else:
        body_content = str(content)
    data = _api(
        "POST",
        "/open-apis/im/v1/messages",
        params={"receive_id_type": id_type},
        json_body={
            "receive_id": ident,
            "msg_type": msg_type,
            "content": body_content,
        },
    )
    return data if isinstance(data, dict) else {"data": data}


def send_app_im_to_recipients(
    recipients: Sequence[str],
    *,
    msg_type: str = "text",
    content: Any,
) -> Dict[str, Any]:
    """Send the same IM to each recipient; collect per-user success/failure."""
    sent: List[str] = []
    failed: List[Dict[str, str]] = []
    last: Dict[str, Any] = {}
    for raw in recipients:
        target = str(raw or "").strip()
        if not target:
            continue
        try:
            last = send_app_im_message(receive_id=target, msg_type=msg_type, content=content)
            sent.append(target)
        except Exception as exc:
            failed.append({"to": target, "error": str(exc)})
            print(f"[FEISHU] 通知 {target} 失败: {exc}", flush=True)
    if not sent and failed:
        raise FeishuError("；".join(f"{item['to']}: {item['error']}" for item in failed[:4]))
    return {"sent": sent, "failed": failed, "last": last}


def notify_task_finished(task_id: str, *, status: str = "") -> Optional[Dict[str, Any]]:
    """Notify that an analysis task finished. Webhook first, else app IM to recipients."""
    from web_app.database import get_task
    task = get_task(task_id)
    if not task:
        return None
    st = (status or str(task.get("status") or "")).strip().lower() or "completed"
    return _dispatch_interactive_notify(
        _task_notify_card(task, status=st),
        log_id=task_id,
        kind="分析任务",
        status=st,
    )


def try_notify_task_finished(task_id: str, *, status: str = "") -> None:
    try:
        notify_task_finished(task_id, status=status)
    except Exception as exc:
        print(f"[FEISHU] 分析任务通知失败: {exc}", flush=True)


def notify_crash_finished(crash_id: str, *, status: str = "") -> Optional[Dict[str, Any]]:
    """Notify that a crash / 故障诊断 task finished."""
    from web_app.database import get_crash_analysis
    crash = get_crash_analysis(crash_id)
    if not crash:
        return None
    st = (status or str(crash.get("status") or "")).strip().lower() or "completed"
    return _dispatch_interactive_notify(
        _crash_notify_card(crash, status=st),
        log_id=crash_id,
        kind="故障诊断",
        status=st,
    )


def try_notify_crash_finished(crash_id: str, *, status: str = "") -> None:
    try:
        notify_crash_finished(crash_id, status=status)
    except Exception as exc:
        print(f"[FEISHU] 故障诊断通知失败: {exc}", flush=True)


def notify_upgrade_finished(job_id: str, *, status: str = "") -> Optional[Dict[str, Any]]:
    """Notify that a patch 入库 / upgrade job finished (completed or failed)."""
    from web_app.database import get_upgrade_job
    job = get_upgrade_job(job_id)
    if not job:
        return None
    st = (status or str(job.get("status") or "")).strip().lower() or "completed"
    if st not in ("completed", "failed"):
        return None
    return _dispatch_interactive_notify(
        _upgrade_notify_card(job, status=st),
        log_id=job_id,
        kind="入库任务",
        status=st,
    )


def try_notify_upgrade_finished(job_id: str, *, status: str = "") -> None:
    try:
        notify_upgrade_finished(job_id, status=status)
    except Exception as exc:
        print(f"[FEISHU] 入库任务通知失败: {exc}", flush=True)


def test_webhook_notify() -> Dict[str, Any]:
    """Send a short test message via webhook or Feishu app IM."""
    if not is_feishu_notify_configured():
        raise FeishuError("请填写通知接收人（多人邮箱），或配置群机器人 Webhook")
    text = "GKI Patch Tool：飞书通知测试成功 ✅"
    if is_feishu_webhook_configured():
        data = send_webhook_message({
            "msg_type": "text",
            "content": {"text": text},
        })
        return {"ok": True, "via": "webhook", "response": data}
    people = get_notify_recipients()
    data = send_app_im_to_recipients(
        people,
        msg_type="text",
        content={"text": text},
    )
    return {"ok": True, "via": "app", "response": data}
