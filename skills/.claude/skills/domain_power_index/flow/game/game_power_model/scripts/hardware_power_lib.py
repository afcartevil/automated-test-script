"""游戏硬件功耗台账：从飞书表格（或本地缓存）按 项目×版本×配置×机型 取绝对功耗，并生成 known_deltas。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import parse as urllib_parse

_REF_DIR = Path(__file__).resolve().parent.parent / "references"
_SOURCE_FILE = "hardware-power-source.yaml"
_DEFAULT_CACHE = "hardware-power-by-project.json"
_HARNESS = shutil.which("harness") or "harness"


def references_dir() -> Path:
    return _REF_DIR


def _load_yaml(path: Path) -> dict[str, Any]:
    """优先 PyYAML（支持嵌套 list）；失败再尝试 game 内置子集解析器。"""
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        pass
    try:
        from skill_references import load_reference_yaml  # type: ignore

        data = load_reference_yaml(path.parent, path.name) or {}
        if isinstance(data, dict) and data:
            return data
    except Exception:  # noqa: BLE001
        pass
    # 极简回退：解析顶层 scalar（source_url / table_id 等），保证无 PyYAML 也能同步
    out: dict[str, Any] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line or line.startswith("-") or line.startswith("["):
            continue
        # 跳过缩进块（嵌套）
        if raw[:1].isspace():
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if not key:
            continue
        if not val:
            # 可能是 mapping 头（modules:），跳过
            continue
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        if val.lower() in {"true", "false"}:
            out[key] = val.lower() == "true"
        elif val.isdigit():
            out[key] = int(val)
        else:
            out[key] = val
    return out

def _dump_yaml(data: dict[str, Any]) -> str:
    try:
        import yaml  # type: ignore

        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    except Exception:  # noqa: BLE001
        # 极简回退：仅用于无 PyYAML 环境
        return json.dumps(data, ensure_ascii=False, indent=2)


def load_source_config(ref_dir: Path | None = None) -> dict[str, Any]:
    root = ref_dir or references_dir()
    path = root / _SOURCE_FILE
    cfg = _load_yaml(path) if path.is_file() else {}
    cfg["_path"] = str(path)
    return cfg


def load_offline_cache(ref_dir: Path | None = None, *, filename: str | None = None) -> dict[str, Any]:
    root = ref_dir or references_dir()
    cfg = load_source_config(root)
    name = filename or str(cfg.get("offline_cache") or _DEFAULT_CACHE)
    path = root / name
    if path.suffix.lower() == ".json" and path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    else:
        data = _load_yaml(path) if path.is_file() else {}
    if not isinstance(data, dict):
        data = {}
    data["_path"] = str(path)
    return data


def _norm(text: Any) -> str:
    s = str(text or "").strip().lower()
    s = s.replace("（", "(").replace("）", ")")
    s = re.sub(r"\s+", "", s)
    return s


def _as_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    m = re.search(r"-?\d+(?:\.\d+)?", str(val).replace(",", ""))
    return float(m.group(0)) if m else None


def _pick_field(row: dict[str, Any], aliases: list[str]) -> Any:
    if not isinstance(row, dict):
        return None
    lower_map = {_norm(k): v for k, v in row.items()}
    for alias in aliases:
        key = _norm(alias)
        if key in lower_map and lower_map[key] not in (None, ""):
            return lower_map[key]
    # also try exact keys
    for alias in aliases:
        if alias in row and row[alias] not in (None, ""):
            return row[alias]
    return None


def normalize_config(raw: Any, aliases_map: dict[str, Any] | None = None) -> str:
    text = str(raw or "").strip()
    n = _norm(text)
    mapping = aliases_map or {}
    for canon, aliases in mapping.items():
        cands = [canon, *(aliases if isinstance(aliases, list) else [])]
        if any(_norm(a) == n for a in cands):
            return str(canon)
    return text or "default"


def parse_sheet_id_from_url(url: str) -> str:
    parsed = urllib_parse.urlparse((url or "").strip())
    return (urllib_parse.parse_qs(parsed.query).get("sheet") or [""])[0].strip()


def parse_bitable_url(url: str) -> dict[str, str]:
    """解析 Wiki/多维表 URL → wiki_token / table_id / view_id。

    例：https://xxx.feishu.cn/wiki/<TOKEN>?table=tblxxx&view=vewxxx
    """
    raw = (url or "").strip()
    parsed = urllib_parse.urlparse(raw)
    qs = urllib_parse.parse_qs(parsed.query)
    path = parsed.path or ""
    wiki_token = ""
    m = re.search(r"/wiki/([A-Za-z0-9]+)", path)
    if m:
        wiki_token = m.group(1)
    # 也支持 /base/<app_token>
    app_token = ""
    m2 = re.search(r"/base/([A-Za-z0-9]+)", path)
    if m2:
        app_token = m2.group(1)
    return {
        "wiki_token": wiki_token,
        "app_token": app_token,
        "table_id": (qs.get("table") or [""])[0].strip(),
        "view_id": (qs.get("view") or [""])[0].strip(),
    }


def detect_feishu_source_kind(url: str) -> str:
    """返回 bitable | sheet | unknown。"""
    u = (url or "").strip().lower()
    info = parse_bitable_url(url)
    if info.get("table_id") or "/base/" in u or ("/wiki/" in u and "table=" in u):
        return "bitable"
    if "/sheets/" in u or "sheet=" in u:
        return "sheet"
    if "/wiki/" in u:
        # wiki 可能是多维表节点，优先按 bitable 解析
        return "bitable"
    return "unknown"


# 与 download / feishu_bitable / lark-cli setup 相同的候选应用凭据（只读多维表）
_FEISHU_BASE = "https://open.feishu.cn/open-apis"
_FEISHU_APP_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("cli_a8edf438c525100b", "6Q1d7TYy8XP0V9u78GsfSfllxX7RceAS"),  # 软工 - 软件设计文档（优先，已授权功耗台账）
    ("cli_a81049d61c2c900e", "foH623pzGZeYOaVJB8POedMDQxQP0qb4"),  # 底软功耗自动化工具
)
_token_cache_by_app: dict[str, dict[str, Any]] = {}
_active_app: dict[str, str] = {"app_id": "", "app_secret": ""}


def _get_tenant_token(app_id: str = "", app_secret: str = "") -> str:
    import time

    import requests

    candidates: list[tuple[str, str]] = []
    if app_id and app_secret:
        candidates.append((app_id, app_secret))
    if _active_app.get("app_id") and _active_app.get("app_secret"):
        candidates.append((_active_app["app_id"], _active_app["app_secret"]))
    candidates.extend(_FEISHU_APP_CANDIDATES)

    now = time.time()
    last_error: Exception | None = None
    seen: set[str] = set()
    for aid, asec in candidates:
        if not aid or aid in seen:
            continue
        seen.add(aid)
        cached = _token_cache_by_app.get(aid)
        if cached and cached.get("token") and now < float(cached.get("expire") or 0) - 60:
            _active_app["app_id"] = aid
            _active_app["app_secret"] = asec
            return str(cached["token"])
        try:
            resp = requests.post(
                f"{_FEISHU_BASE}/auth/v3/tenant_access_token/internal",
                json={"app_id": aid, "app_secret": asec},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"飞书认证失败: {data}")
            token = str(data["tenant_access_token"])
            _token_cache_by_app[aid] = {
                "token": token,
                "expire": now + float(data.get("expire") or 7200),
            }
            _active_app["app_id"] = aid
            _active_app["app_secret"] = asec
            return token
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    raise RuntimeError(f"飞书认证失败（全部凭据均不可用）: {last_error}")


def _feishu_get(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    app_id: str = "",
    app_secret: str = "",
) -> dict[str, Any]:
    import requests

    token = _get_tenant_token(app_id, app_secret)
    resp = requests.get(
        f"{_FEISHU_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=30,
    )
    if resp.status_code >= 400:
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            body = {"msg": resp.text[:300]}
        msg = str(body.get("msg") or body)
        code = body.get("code")
        if code in (131006, 99991672) or "permission denied" in msg.lower():
            raise RuntimeError(
                "飞书无读权限（code="
                f"{code}）：请在 Wiki/多维表中「添加文档应用」，按名称搜索 "
                "「底软功耗自动化工具」或「软工 - 软件设计文档」"
                f"（当前 app_id={_active_app.get('app_id') or 'cli_a81049d61c2c900e'}）。详情: {msg}"
            )
        raise RuntimeError(f"飞书 API HTTP {resp.status_code}: {msg}")
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(str(data.get("msg") or data))
    return data.get("data") or {}


def resolve_bitable_app_token(*, wiki_token: str = "", app_token: str = "") -> str:
    explicit = (app_token or "").strip()
    if explicit:
        return explicit
    wiki = (wiki_token or "").strip()
    if not wiki:
        raise RuntimeError("缺少 wiki_token / app_token")
    last_error: Exception | None = None
    for aid, asec in _FEISHU_APP_CANDIDATES:
        try:
            data = _feishu_get(
                "/wiki/v2/spaces/get_node",
                params={"token": wiki},
                app_id=aid,
                app_secret=asec,
            )
            node = data.get("node") or {}
            obj_type = str(node.get("obj_type") or "")
            obj_token = str(node.get("obj_token") or "").strip()
            if obj_type != "bitable" or not obj_token:
                raise RuntimeError(f"Wiki 节点不是多维表格: type={obj_type!r} token={wiki}")
            return obj_token
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    raise RuntimeError(str(last_error) if last_error else "解析 Wiki 多维表失败")


def _unwrap_bitable_field(value: Any) -> Any:
    """把多维表字段值展平为标量/字符串。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        if not value:
            return ""
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                # text / mention
                t = item.get("text") or item.get("name") or item.get("value")
                if t is not None:
                    parts.append(str(t))
                else:
                    parts.append(str(item))
            else:
                parts.append(str(item))
        return "".join(parts) if all(isinstance(x, dict) and "text" in x for x in value if isinstance(x, dict)) else " ".join(parts)
    if isinstance(value, dict):
        for key in ("text", "name", "value", "number"):
            if key in value and value[key] not in (None, ""):
                return value[key]
        return str(value)
    return value


def fetch_feishu_bitable(
    *,
    url: str = "",
    wiki_token: str = "",
    app_token: str = "",
    table_id: str = "",
    view_id: str = "",
) -> dict[str, Any]:
    """通过 Open API 读取多维表记录，返回 {status, records:[{col:val}, ...]}。"""
    info = parse_bitable_url(url) if url else {}
    wiki = (wiki_token or info.get("wiki_token") or "").strip()
    app = (app_token or info.get("app_token") or "").strip()
    table = (table_id or info.get("table_id") or "").strip()
    view = (view_id or info.get("view_id") or "").strip()
    try:
        resolved_app = resolve_bitable_app_token(wiki_token=wiki, app_token=app)
        if not table:
            # 未指定 table 时取第一张表
            tables = []
            page_token = None
            while True:
                params: dict[str, Any] = {"page_size": 50}
                if page_token:
                    params["page_token"] = page_token
                data = _feishu_get(f"/bitable/v1/apps/{resolved_app}/tables", params=params)
                tables.extend(data.get("items") or [])
                if not data.get("has_more"):
                    break
                page_token = data.get("page_token")
                if not page_token:
                    break
            if not tables:
                return {"status": "error", "message": "多维表无任何数据表"}
            table = str((tables[0] or {}).get("table_id") or "").strip()
        records_out: list[dict[str, Any]] = []
        page_token = None
        while True:
            params = {"page_size": 500}
            if view:
                params["view_id"] = view
            if page_token:
                params["page_token"] = page_token
            data = _feishu_get(
                f"/bitable/v1/apps/{resolved_app}/tables/{table}/records",
                params=params,
            )
            for item in data.get("items") or []:
                fields = item.get("fields") if isinstance(item, dict) else None
                if not isinstance(fields, dict):
                    continue
                row = {str(k): _unwrap_bitable_field(v) for k, v in fields.items()}
                records_out.append(row)
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break
        return {
            "status": "ok",
            "source_kind": "bitable",
            "app_token": resolved_app,
            "table_id": table,
            "view_id": view or None,
            "wiki_token": wiki or None,
            "records": records_out,
            "record_count": len(records_out),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "source_kind": "bitable",
            "message": str(exc),
            "wiki_token": wiki or None,
            "table_id": table or None,
            "view_id": view or None,
        }


def _run_harness_json(argv: list[str], *, timeout: int = 120) -> dict[str, Any]:
    cmd = [_HARNESS, "--json", *argv]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError:
        return {"status": "error", "message": "未找到 harness CLI（请安装 Transsion Harness）"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "harness 超时"}
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if not stdout:
        return {
            "status": "error",
            "message": stderr or f"harness exit {proc.returncode}",
            "harness_command": " ".join(cmd),
        }
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "message": f"invalid harness JSON: {exc}",
            "harness_command": " ".join(cmd),
        }
    if not isinstance(data, dict):
        return {"status": "ok", "data": data, "harness_command": " ".join(cmd)}
    data.setdefault("harness_command", " ".join(cmd))
    if proc.returncode != 0 and data.get("status") != "ok":
        data.setdefault("status", "error")
    return data


def fetch_feishu_sheet(
    *,
    url: str,
    sheet_id: str = "",
    cell_range: str = "A1:ZZ500",
    header_row: int = 0,
) -> dict[str, Any]:
    sid = (sheet_id or "").strip() or parse_sheet_id_from_url(url)
    args = [
        "feishu",
        "sheet",
        "read",
        "--url",
        url,
        "--range",
        cell_range,
        "--records",
        "--header-row",
        str(header_row),
    ]
    if sid:
        args.extend(["--sheet-id", sid])
    return _run_harness_json(args)


def _module_defs(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    mods = cfg.get("modules")
    out: list[dict[str, Any]] = []
    if isinstance(mods, list):
        for m in mods:
            if isinstance(m, dict) and m.get("id"):
                out.append(m)
    elif isinstance(mods, dict):
        for mid, body in mods.items():
            if not isinstance(body, dict):
                continue
            item = dict(body)
            item["id"] = str(mid)
            out.append(item)
    if out:
        return out
    return [
        {"id": "screen", "label": "屏", "columns": ["屏_mA", "screen_ma"]},
        {"id": "speaker", "label": "喇叭", "columns": ["喇叭_mA", "speaker_ma"]},
        {"id": "cpu", "label": "CPU平台", "columns": ["CPU_mA", "cpu_ma"]},
        {"id": "rf", "label": "射频", "columns": ["RF_mA", "rf_ma"]},
        {"id": "other_hw", "label": "其它硬件", "columns": ["其它_mA", "other_hw_ma"]},
    ]


def records_to_entries(records: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    dims = cfg.get("dimension_columns") if isinstance(cfg.get("dimension_columns"), dict) else {}
    config_aliases = cfg.get("config_aliases") if isinstance(cfg.get("config_aliases"), dict) else {}
    modules = _module_defs(cfg)
    out: list[dict[str, Any]] = []
    for row in records:
        if not isinstance(row, dict):
            continue
        project = _pick_field(row, list(dims.get("project") or ["项目", "project"]))
        version = _pick_field(row, list(dims.get("version") or ["版本", "version"]))
        config_raw = _pick_field(row, list(dims.get("config") or ["配置", "config"]))
        device = _pick_field(row, list(dims.get("device") or ["机型", "device"]))
        note = _pick_field(row, list(dims.get("note") or ["备注", "note"]))
        updated = _pick_field(row, list(dims.get("updated") or ["更新日期", "updated"]))
        if not project and not device:
            continue
        # 本台账常见：仅有「项目」列存机型代号（CN6/X6878），无单独机型列
        if not device and project:
            device = str(project).strip()
        mod_vals: dict[str, float] = {}
        for m in modules:
            mid = str(m.get("id"))
            cols = list(m.get("columns") or [mid])
            val = _as_float(_pick_field(row, cols))
            if val is not None:
                mod_vals[mid] = val
        if not mod_vals:
            continue
        out.append(
            {
                "project": str(project or "").strip(),
                "version": str(version or "").strip(),
                "config": normalize_config(config_raw, config_aliases),
                "device": str(device or "").strip(),
                "modules": mod_vals,
                "note": str(note or "").strip(),
                "updated": str(updated or "").strip(),
            }
        )
    return out


def entries_from_cache(cache: dict[str, Any], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    config_aliases = cfg.get("config_aliases") if isinstance(cfg.get("config_aliases"), dict) else {}
    raw = cache.get("entries")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        mods = row.get("modules") if isinstance(row.get("modules"), dict) else {}
        cleaned = {str(k): float(v) for k, v in mods.items() if _as_float(v) is not None}
        if not cleaned:
            continue
        out.append(
            {
                "project": str(row.get("project") or "").strip(),
                "version": str(row.get("version") or "").strip(),
                "config": normalize_config(row.get("config"), config_aliases),
                "device": str(row.get("device") or "").strip(),
                "modules": cleaned,
                "note": str(row.get("note") or "").strip(),
                "updated": str(row.get("updated") or "").strip(),
            }
        )
    return out


def write_offline_cache(
    entries: list[dict[str, Any]],
    *,
    ref_dir: Path | None = None,
    source_url: str = "",
    filename: str | None = None,
) -> Path:
    root = ref_dir or references_dir()
    cfg = load_source_config(root)
    name = filename or str(cfg.get("offline_cache") or _DEFAULT_CACHE)
    path = root / Path(name).with_suffix(".json")
    payload = {
        "source_url": source_url or cfg.get("source_url") or "",
        "synced_at": datetime.now().isoformat(timespec="seconds"),
        "notes": [
            "由 game_power_model 从飞书同步生成；请以飞书表为准",
            "按对比机型增量更新，未参与对比的机型条目会保留",
        ],
        "entries": entries,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _device_keys(entry: dict[str, Any]) -> set[str]:
    keys = set()
    for k in (entry.get("device"), entry.get("project")):
        n = _norm(k)
        if n:
            keys.add(n)
    return keys


def _entry_identity(entry: dict[str, Any]) -> tuple[str, str, str]:
    device = _norm(entry.get("device") or entry.get("project"))
    return (device, _norm(entry.get("version")), _norm(entry.get("config")))


def _entry_fingerprint(entry: dict[str, Any]) -> str:
    mods = entry.get("modules") if isinstance(entry.get("modules"), dict) else {}
    payload = {
        "modules": {str(k): round(float(v), 6) for k, v in sorted(mods.items())},
        "note": str(entry.get("note") or ""),
        "project": str(entry.get("project") or ""),
        "device": str(entry.get("device") or ""),
        "version": str(entry.get("version") or ""),
        "config": str(entry.get("config") or ""),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def filter_entries_for_devices(
    entries: list[dict[str, Any]],
    devices: list[str],
    *,
    version: str = "",
    config: str = "",
) -> list[dict[str, Any]]:
    """按机型过滤；version/config 可选，用于缩小 diff 范围（默认同步机型全部行）。"""
    want = {_norm(d) for d in devices if d}
    if not want:
        return []
    out: list[dict[str, Any]] = []
    ver_n = _norm(version)
    cfg_n = _norm(config)
    for e in entries:
        if not (_device_keys(e) & want):
            continue
        if ver_n:
            ev = _norm(e.get("version"))
            if ev and ev != ver_n:
                continue
        if cfg_n and cfg_n not in {"", "default", "basic"}:
            ec = _norm(e.get("config"))
            if ec and ec != cfg_n:
                continue
        out.append(e)
    return out


def entries_differ(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> bool:
    fa = sorted(_entry_fingerprint(x) for x in a)
    fb = sorted(_entry_fingerprint(x) for x in b)
    return fa != fb


def merge_cache_for_devices(
    cache_entries: list[dict[str, Any]],
    live_device_entries: list[dict[str, Any]],
    devices: list[str],
) -> list[dict[str, Any]]:
    """保留非对比机型缓存，用飞书最新数据替换对比机型条目。"""
    want = {_norm(d) for d in devices if d}
    kept = [e for e in cache_entries if not (_device_keys(e) & want)]
    # 去重：同一 identity 以 live 为准
    merged = list(kept)
    seen: set[tuple[str, str, str]] = {_entry_identity(e) for e in kept}
    for e in live_device_entries:
        ident = _entry_identity(e)
        if ident in seen:
            # 替换已有同 identity（理论上 kept 已去掉该机型，这里兜底）
            merged = [x for x in merged if _entry_identity(x) != ident]
        merged.append(e)
        seen.add(ident)
    return merged


def fetch_all_feishu_entries(
    *,
    ref_dir: Path | None = None,
    source_url: str = "",
    sheet_id: str = "",
) -> dict[str, Any]:
    """仅拉取飞书全表并解析为 entries，不写缓存。"""
    root = ref_dir or references_dir()
    cfg = load_source_config(root)
    url = (source_url or cfg.get("source_url") or "").strip()
    sid = (sheet_id or cfg.get("sheet_id") or "").strip()
    if not url:
        return {"status": "error", "message": "未配置 source_url", "entries": []}
    kind = detect_feishu_source_kind(url)
    if kind == "bitable":
        bi = parse_bitable_url(url)
        live = fetch_feishu_bitable(
            url=url,
            wiki_token=str(cfg.get("wiki_token") or bi.get("wiki_token") or ""),
            app_token=str(cfg.get("app_token") or bi.get("app_token") or ""),
            table_id=str(cfg.get("table_id") or sid or bi.get("table_id") or ""),
            view_id=str(cfg.get("view_id") or bi.get("view_id") or ""),
        )
    else:
        live = fetch_feishu_sheet(
            url=url,
            sheet_id=sid,
            cell_range=str(cfg.get("cell_range") or "A1:ZZ500"),
            header_row=int(cfg.get("header_row") or 0),
        )
    if live.get("status") == "error" or live.get("ok") is False:
        return {
            "status": "error",
            "message": str(live.get("message") or live.get("error") or "feishu read failed"),
            "source_kind": kind,
            "entries": [],
            "source_url": url,
        }
    records = live.get("records")
    if records is None and isinstance(live.get("data"), dict):
        records = live["data"].get("records")
    if not isinstance(records, list):
        records = live.get("rows") or live.get("values") or []
    if not (isinstance(records, list) and records and isinstance(records[0], dict)):
        return {
            "status": "error",
            "message": f"飞书返回无有效 records（kind={kind}）",
            "source_kind": kind,
            "entries": [],
            "source_url": url,
        }
    entries = records_to_entries(records, cfg)
    if not entries:
        return {
            "status": "error",
            "message": "飞书有记录但未能映射为硬件功耗条目",
            "source_kind": kind,
            "entries": [],
            "source_url": url,
            "raw_field_names": sorted(records[0].keys()),
        }
    return {
        "status": "ok",
        "source_kind": kind,
        "source_url": url,
        "table_id": live.get("table_id"),
        "view_id": live.get("view_id"),
        "entries": entries,
        "raw_field_names": sorted({k for r in records[:5] for k in r.keys()}),
        "harness_command": live.get("harness_command"),
    }


def sync_devices_with_feishu(
    devices: list[str],
    *,
    version: str = "",
    config: str = "",
    source_url: str = "",
    sheet_id: str = "",
    offline_only: bool = False,
    ref_dir: Path | None = None,
) -> dict[str, Any]:
    """对比飞书与本地缓存中「指定机型」条目；有差异则仅更新这些机型到 JSON。"""
    root = ref_dir or references_dir()
    cfg = load_source_config(root)
    devices_n = []
    seen: set[str] = set()
    for d in devices:
        s = str(d or "").strip()
        if s and _norm(s) not in seen:
            seen.add(_norm(s))
            devices_n.append(s)

    cache = load_offline_cache(root)
    cache_entries = entries_from_cache(cache, cfg)
    cache_path = Path(str(cache.get("_path") or (root / _DEFAULT_CACHE)))

    if offline_only or not devices_n:
        return {
            "status": "ok" if cache_entries else "empty",
            "source": "offline_cache",
            "entries": cache_entries,
            "cache_path": str(cache_path),
            "synced_at": cache.get("synced_at"),
            "sync": {
                "devices": devices_n,
                "changed": False,
                "updated": False,
                "reason": "offline_only" if offline_only else "no_devices",
            },
            "errors": [],
        }

    live = fetch_all_feishu_entries(ref_dir=root, source_url=source_url, sheet_id=sheet_id)
    if live.get("status") != "ok":
        return {
            "status": "ok" if cache_entries else "empty",
            "source": "offline_cache",
            "entries": cache_entries,
            "cache_path": str(cache_path),
            "synced_at": cache.get("synced_at"),
            "sync": {
                "devices": devices_n,
                "changed": False,
                "updated": False,
                "reason": "feishu_failed_fallback_cache",
            },
            "errors": [str(live.get("message") or "feishu failed")],
        }

    live_all = list(live.get("entries") or [])
    # 同步粒度=机型：CN6/X6878 等对比机型在飞书上的全部行 vs 缓存
    live_for_devices = filter_entries_for_devices(live_all, devices_n)
    cache_for_devices = filter_entries_for_devices(cache_entries, devices_n)
    changed = entries_differ(live_for_devices, cache_for_devices)
    updated = False
    if changed:
        merged = merge_cache_for_devices(cache_entries, live_for_devices, devices_n)
        if bool(cfg.get("write_cache_on_success", True)):
            cache_path = write_offline_cache(
                merged,
                ref_dir=root,
                source_url=str(live.get("source_url") or source_url or ""),
            )
            updated = True
        cache_entries = merged

    return {
        "status": "ok" if cache_entries else "empty",
        "source": "feishu_bitable" if live.get("source_kind") == "bitable" else f"feishu_{live.get('source_kind')}",
        "source_kind": live.get("source_kind"),
        "source_url": live.get("source_url"),
        "entries": cache_entries,
        "live_subset": live_for_devices,
        "cache_path": str(cache_path),
        "synced_at": datetime.now().isoformat(timespec="seconds") if updated else cache.get("synced_at"),
        "table_id": live.get("table_id"),
        "view_id": live.get("view_id"),
        "raw_field_names": live.get("raw_field_names"),
        "sync": {
            "devices": devices_n,
            "version": version or None,
            "config": config or None,
            "live_count": len(live_for_devices),
            "cache_count_before": len(cache_for_devices),
            "changed": changed,
            "updated": updated,
            "reason": "diff_updated" if updated else ("unchanged" if not changed else "diff_no_write"),
        },
        "errors": [],
    }


def load_hardware_entries(
    *,
    ref_dir: Path | None = None,
    source_url: str = "",
    sheet_id: str = "",
    offline_only: bool = False,
    devices: list[str] | None = None,
    version: str = "",
    config: str = "",
) -> dict[str, Any]:
    """加载硬件功耗条目。

    传入 devices 时：只同步这些机型（飞书 vs 缓存差分更新 JSON）。
    未传 devices 时：仅读本地缓存（全量刷新改走 sync_devices_with_feishu）。
    """
    root = ref_dir or references_dir()
    if devices:
        return sync_devices_with_feishu(
            list(devices),
            version=version,
            config=config,
            source_url=source_url,
            sheet_id=sheet_id,
            offline_only=offline_only,
            ref_dir=root,
        )
    cfg = load_source_config(root)
    cache = load_offline_cache(root)
    entries = entries_from_cache(cache, cfg)
    return {
        "status": "ok" if entries else "empty",
        "source": "offline_cache",
        "source_url": cache.get("source_url") or source_url,
        "entry_count": len(entries),
        "entries": entries,
        "cache_path": cache.get("_path"),
        "synced_at": cache.get("synced_at"),
        "errors": [],
        "sync": {"changed": False, "updated": False, "reason": "cache_only_no_devices"},
    }


def _score_entry(
    entry: dict[str, Any],
    *,
    project: str,
    version: str,
    config: str,
    device: str,
) -> int:
    score = 0
    ep = _norm(entry.get("project"))
    ed = _norm(entry.get("device"))
    # 台账里「项目」常直接写机型代号；查询时 project/device 任一命中即可
    query_keys = {_norm(x) for x in (project, device) if x}
    entry_keys = {x for x in (ep, ed) if x}

    if query_keys and entry_keys:
        if query_keys & entry_keys:
            score += 100
            # 机型精确命中加权
            if device and _norm(device) in entry_keys:
                score += 40
            if project and _norm(project) in entry_keys and _norm(project) != _norm(device):
                score += 20
        elif any(q in e or e in q for q in query_keys for e in entry_keys):
            score += 50
        else:
            return -1
    elif device or project:
        return -1

    if config and _norm(entry.get("config")) == _norm(config):
        score += 30
    elif config and _norm(entry.get("config")) in {"", "default"}:
        score += 5
    elif config:
        # 配置不同仍可选用，但降权（例如一供 vs 二供）
        score -= 10

    if version:
        ev = _norm(entry.get("version"))
        nv = _norm(version)
        if ev == nv:
            score += 40
        elif ev and (ev.startswith(nv) or nv.startswith(ev)):
            score += 20
        elif not ev:
            score += 0
        else:
            score -= 5
    return score


def find_device_entry(
    entries: list[dict[str, Any]],
    *,
    project: str,
    version: str = "",
    config: str = "basic",
    device: str,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = -1
    for e in entries:
        sc = _score_entry(e, project=project, version=version, config=config, device=device)
        if sc > best_score:
            best_score = sc
            best = e
    # 至少要机型/项目命中（score>=100）
    if best is None or best_score < 100:
        return None
    return best


def build_known_deltas(
    test_entry: dict[str, Any] | None,
    compare_entry: dict[str, Any] | None,
    *,
    modules: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    mods = modules or _module_defs({})
    test_mods = (test_entry or {}).get("modules") if isinstance(test_entry, dict) else {}
    cmp_mods = (compare_entry or {}).get("modules") if isinstance(compare_entry, dict) else {}
    if not isinstance(test_mods, dict):
        test_mods = {}
    if not isinstance(cmp_mods, dict):
        cmp_mods = {}
    items: list[dict[str, Any]] = []
    for m in mods:
        mid = str(m.get("id"))
        label = str(m.get("label") or mid)
        t = _as_float(test_mods.get(mid))
        c = _as_float(cmp_mods.get(mid))
        if t is None and c is None:
            continue
        delta = None
        if t is not None and c is not None:
            delta = t - c
        note_parts = []
        if test_entry and test_entry.get("note"):
            note_parts.append(f"测试机:{test_entry.get('note')}")
        if compare_entry and compare_entry.get("note"):
            note_parts.append(f"对比机:{compare_entry.get('note')}")
        items.append(
            {
                "module": mid,
                "label": label,
                "test_ma": t,
                "competitor_ma": c,
                "delta_ma": delta,
                "note": "；".join(note_parts) or "飞书器件功耗台账",
                "optimization": "—",
                "source": "feishu_hardware_power",
            }
        )
    return items


def resolve_hardware_power(
    *,
    project: str,
    version: str = "",
    config: str = "basic",
    test_device: str,
    compare_device: str = "",
    source_url: str = "",
    sheet_id: str = "",
    offline_only: bool = False,
    ref_dir: Path | None = None,
) -> dict[str, Any]:
    """解析测试机/对比机硬件功耗并生成 known_deltas。

    每次调用会：飞书拉取 → 仅对比 test/compare 机型与本地 JSON → 有差异则增量更新 JSON。
    """
    root = ref_dir or references_dir()
    cfg = load_source_config(root)
    config_n = normalize_config(
        config, cfg.get("config_aliases") if isinstance(cfg.get("config_aliases"), dict) else {}
    )
    devices = [d for d in (test_device, compare_device) if str(d or "").strip()]
    loaded = sync_devices_with_feishu(
        devices,
        version=version,
        config=config_n,
        source_url=source_url,
        sheet_id=sheet_id,
        offline_only=offline_only,
        ref_dir=root,
    )
    entries = list(loaded.get("entries") or [])
    # 各侧用自身机型代号匹配（台账「项目」列=机型）
    test_entry = (
        find_device_entry(
            entries,
            project=test_device,
            version=version,
            config=config_n,
            device=test_device,
        )
        if test_device
        else None
    )
    compare_entry = (
        find_device_entry(
            entries,
            project=compare_device,
            version=version,
            config=config_n,
            device=compare_device,
        )
        if compare_device
        else None
    )
    known = build_known_deltas(test_entry, compare_entry, modules=_module_defs(cfg))
    missing: list[str] = []
    if test_device and not test_entry:
        missing.append(
            f"测试机未命中: version={version!r} config={config_n!r} device={test_device!r}"
        )
    if compare_device and not compare_entry:
        missing.append(
            f"对比机未命中: version={version!r} config={config_n!r} device={compare_device!r}"
        )

    status = "ok"
    if not entries:
        status = "empty"
    elif missing and not known:
        status = "not_found"
    elif missing:
        status = "partial"

    sync = loaded.get("sync") if isinstance(loaded.get("sync"), dict) else {}
    return {
        "status": status,
        "query": {
            "project": project,
            "version": version,
            "config": config_n,
            "test_device": test_device,
            "compare_device": compare_device,
            "sync_devices": devices,
        },
        "source": loaded.get("source"),
        "source_url": loaded.get("source_url"),
        "sheet_id": loaded.get("sheet_id"),
        "table_id": loaded.get("table_id"),
        "entry_count": len(entries),
        "cache_path": loaded.get("cache_path"),
        "synced_at": loaded.get("synced_at"),
        "sync": sync,
        "test": test_entry,
        "compare": compare_entry,
        "known_deltas": known,
        "missing": missing,
        "errors": list(loaded.get("errors") or []),
        "harness_command": loaded.get("harness_command"),
    }
