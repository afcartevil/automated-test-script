"""解析游戏功耗分析用的「项目 / 测试用例」。

来源优先级：
1. CLI 显式 --project / --test-case
2. analysis/game_analysis_meta.json
3. JIRA 单号字段/摘要/描述（含项目与基础/NPS）
4. 交互式选择（仅 TTY；项目列表来自亮度和音量表）
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from brightness_volume_table import (
    load_brightness_volume_table,
    lookup_setting,
    normalize_test_case,
    resolve_project_entry,
)

_META_NAME = "game_analysis_meta.json"


def table_ref_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "references"


def list_projects(ref_dir: Path | None = None) -> list[str]:
    table = load_brightness_volume_table(ref_dir or table_ref_dir())
    projects = table.get("projects") or {}
    return sorted(str(k) for k in projects.keys())


def meta_path(log_path: Path) -> Path:
    return Path(log_path) / "analysis" / _META_NAME


def load_analysis_meta(log_path: Path) -> dict[str, Any]:
    path = meta_path(log_path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_analysis_meta(log_path: Path, meta: dict[str, Any]) -> Path:
    path = meta_path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cur = load_analysis_meta(log_path)
    cur.update({k: v for k, v in meta.items() if v is not None and str(v).strip() != ""})
    path.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def parse_test_case_from_text(text: str) -> str | None:
    raw = text or ""
    if re.search(r"NPS|最大亮度|最大音量", raw, re.IGNORECASE):
        return "nps"
    if re.search(r"基础场景|基础亮度|350\s*nit|72\s*dB", raw, re.IGNORECASE):
        return "basic"
    return None


def parse_project_from_text(text: str, known: list[str] | None = None) -> str | None:
    raw = text or ""
    known = known or list_projects()
    # 精确项目名优先（长名优先）
    for pid in sorted(known, key=len, reverse=True):
        if pid and pid in raw:
            return pid
    # 通用「项目N」
    m = re.search(r"项目\s*([0-9A-Za-z_\-]+)", raw)
    if m:
        cand = f"项目{m.group(1)}"
        if cand in known:
            return cand
        # 表中尚未录入时也返回，便于后续补表
        return cand
    return None


def parse_from_jira_fields(fields: dict[str, Any], *, known: list[str] | None = None) -> dict[str, Any]:
    """从 JIRA 字段对象解析 project / test_case。"""
    known = known or list_projects()
    parts = [
        str(fields.get("summary") or ""),
        str(fields.get("description") or ""),
        str(fields.get("affect_project") or fields.get("customfield_14205") or ""),
        str(fields.get("environment") or ""),
    ]
    blob = "\n".join(parts)
    project = parse_project_from_text(blob, known)
    # affect_project 可能是机型代码，尝试 aliases
    if not project:
        affect = str(fields.get("affect_project") or fields.get("customfield_14205") or "").strip()
        if affect:
            pid, _ = resolve_project_entry(load_brightness_volume_table(table_ref_dir()), affect)
            project = pid
    test_case = parse_test_case_from_text(blob) or "basic"
    return {
        "project": project,
        "test_case": test_case,
        "source": "jira",
        "jira_summary": fields.get("summary"),
    }


def try_fetch_jira_fields(jira_key: str) -> dict[str, Any] | None:
    """尽量读取 JIRA；失败返回 None（不阻断路径模式）。"""
    key = (jira_key or "").strip()
    if not key or key.upper().startswith("DEMO"):
        return None
    try:
        jira_scripts = (
            Path(__file__).resolve().parents[6] / "base" / "jirainfo" / "scripts"
        )
        # scripts -> game_precondition -> game -> flow -> power -> domain -> analysis
        if str(jira_scripts) not in sys.path:
            sys.path.insert(0, str(jira_scripts))
        from jira_info import JiraInfo  # type: ignore

        info = JiraInfo()
        info.jira_number = key
        return {
            "summary": info.summary,
            "description": info.description,
            "affect_project": info.affect_project,
            "environment": info.environment,
            "status": getattr(info, "status", None),
        }
    except Exception:
        return None


def prompt_select_project(known: list[str], *, default: str | None = None) -> str | None:
    if not known:
        print("亮度和音量表中暂无项目，请先补全 brightness-volume-by-project.yaml", file=sys.stderr)
        return None
    print("请选择项目（来自飞书「亮度和音量表」）：")
    for i, pid in enumerate(known, start=1):
        mark = " *" if default and pid == default else ""
        print(f"  {i}. {pid}{mark}")
    print("输入序号或项目名（回车保留默认）：", end="", flush=True)
    try:
        line = sys.stdin.readline()
    except Exception:
        return default
    text = (line or "").strip()
    if not text:
        return default or known[0]
    if text.isdigit():
        idx = int(text)
        if 1 <= idx <= len(known):
            return known[idx - 1]
    if text in known:
        return text
    # 模糊
    for pid in known:
        if text.lower() in pid.lower():
            return pid
    print(f"未识别项目「{text}」，可用：{', '.join(known)}", file=sys.stderr)
    return None


def prompt_select_test_case(default: str = "basic") -> str:
    print("请选择测试用例：")
    print("  1. basic / 基础场景（350nit / 72dB 列）")
    print("  2. nps / NPS场景（最大亮度 / 最大音量 列）")
    print(f"输入序号或名称（回车默认 {default}）：", end="", flush=True)
    try:
        line = sys.stdin.readline()
    except Exception:
        return normalize_test_case(default)
    text = (line or "").strip()
    if not text:
        return normalize_test_case(default)
    if text in ("1",):
        return "basic"
    if text in ("2",):
        return "nps"
    return normalize_test_case(text, default=default)


def resolve_project_context(
    *,
    log_path: Path | None = None,
    project: str | None = None,
    test_case: str | None = None,
    jira_key: str | None = None,
    jira_fields: dict[str, Any] | None = None,
    interactive: bool | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """统一解析并可选落盘 analysis/game_analysis_meta.json。"""
    ref_dir = table_ref_dir()
    known = list_projects(ref_dir)
    meta = load_analysis_meta(log_path) if log_path else {}

    proj = (project or "").strip() or str(meta.get("project") or "").strip() or None
    case = (test_case or "").strip() or str(meta.get("test_case") or "").strip() or None
    source = "cli" if project else ("meta" if meta.get("project") else None)

    # JIRA
    fields = jira_fields
    if fields is None and jira_key:
        fields = try_fetch_jira_fields(jira_key)
    if fields and (not proj or not case):
        parsed = parse_from_jira_fields(fields, known=known)
        if not proj and parsed.get("project"):
            proj = parsed["project"]
            source = "jira"
        if not case and parsed.get("test_case"):
            case = parsed["test_case"]
            source = source or "jira"

    case = normalize_test_case(case, default="basic")

    # 交互：路径模式且无项目
    if interactive is None:
        interactive = sys.stdin is not None and hasattr(sys.stdin, "isatty") and sys.stdin.isatty()
    if not proj and interactive:
        print(
            "未指定项目。日志来自本地路径时，请选择飞书亮度和音量表中的项目：\n"
            "https://transsioner.feishu.cn/wiki/TTAVwmmIrif4uoknp1rcqRatn2V?sheet=4258R0"
        )
        proj = prompt_select_project(known, default=known[0] if known else None)
        source = "prompt"
        if not test_case:
            case = prompt_select_test_case(default=case or "basic")

    setting = lookup_setting(ref_dir, project=proj, test_case=case)
    out = {
        "project": setting.get("project") or proj,
        "project_requested": proj,
        "project_matched": bool(setting.get("project_matched")),
        "test_case": setting.get("test_case") or case,
        "test_case_label": setting.get("test_case_label"),
        "compare_mode": setting.get("compare_mode"),
        "brightness_level": setting.get("brightness_level"),
        "brightness_nits": setting.get("brightness_nits"),
        "volume_index": setting.get("volume_index"),
        "source": source or "unknown",
        "jira_key": (jira_key or "").strip() or meta.get("jira_key"),
        "known_projects": known,
        "table_url": setting.get("source_url"),
        "brightness_volume_setting": setting,
    }
    if persist and log_path is not None:
        save_analysis_meta(
            log_path,
            {
                "project": out.get("project") or out.get("project_requested"),
                "test_case": out.get("test_case"),
                "test_case_label": out.get("test_case_label"),
                "jira_key": out.get("jira_key"),
                "source": out.get("source"),
                "volume_index": out.get("volume_index"),
                "brightness_level": out.get("brightness_level"),
                "brightness_nits": out.get("brightness_nits"),
                "compare_mode": out.get("compare_mode"),
                "table_url": out.get("table_url"),
            },
        )
    return out
