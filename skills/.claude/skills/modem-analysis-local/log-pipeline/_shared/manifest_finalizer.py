"""manifest 落盘前的最终化处理：路径相对化 + schema 校验。

Phase 1 的输出对 Phase 2 是契约性的，因此本模块负责：
1. 把 manifest 中所有跨平台敏感字段（final_log_root / aggregated_files /
   copied_support_files 等）落地为相对于 manifest 所在目录的 POSIX 相对路径；
2. 写入 schema_version 与 _meta（含 phase1_completed_at / phase1_host）；
3. 用 JSON Schema 强校验 manifest，校验失败立即抛错。

任何 Phase 1 步骤希望进入"契约状态"时都应调用 finalize_manifest_for_phase2()。
"""

from __future__ import annotations

import json
import os
import socket
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


SCHEMA_VERSION = "1.1.0"
SCHEMA_FILENAME = "job_manifest.schema.json"


def _project_root() -> Path:
    """返回 modem-log-pipeline 工程根目录。"""
    return Path(__file__).resolve().parent.parent


def _schema_path() -> Path:
    return _project_root() / "schemas" / SCHEMA_FILENAME


def to_relative_posix(path: str, base_dir: str) -> str:
    """将 path 转为相对于 base_dir 的 POSIX 风格相对路径。

    - 若 path 已是相对路径，先与 base_dir 拼绝对再转回相对，保证幂等。
    - 若 path 不在 base_dir 之内，返回原始绝对路径（兜底，避免误丢失数据），并打 warning。
    """
    if not path:
        return ""
    base_abs = os.path.abspath(base_dir)
    path_abs = os.path.abspath(path if os.path.isabs(path) else os.path.join(base_abs, path))
    try:
        rel = os.path.relpath(path_abs, base_abs)
    except ValueError:
        return path_abs.replace(os.sep, "/")
    rel = rel.replace(os.sep, "/")
    if rel.startswith("../"):
        return path_abs.replace(os.sep, "/")
    return rel


def _relativize_aggregated_files(aggregated_files: Dict[str, Any], base_dir: str) -> Dict[str, Any]:
    """aggregated_files 结构：{"DUT": {"ota": "<abs>", "ps": "<abs>", ...}, ...}"""
    if not isinstance(aggregated_files, dict):
        return {}
    result: Dict[str, Any] = {}
    for group_key, files in aggregated_files.items():
        if not isinstance(files, dict):
            continue
        result[group_key] = {
            file_key: to_relative_posix(path, base_dir)
            for file_key, path in files.items()
            if isinstance(path, str) and path
        }
    return result


def _relativize_support_files(support_files: Dict[str, Any], base_dir: str) -> Dict[str, Any]:
    """copied_support_files 结构：
    {"DUT": {"radio": ["<abs>", ...], "main": [...], ...}, ...}
    """
    if not isinstance(support_files, dict):
        return {}
    result: Dict[str, Any] = {}
    for group_key, files_by_type in support_files.items():
        if not isinstance(files_by_type, dict):
            continue
        group_out: Dict[str, Any] = {}
        for type_key, paths in files_by_type.items():
            if not isinstance(paths, list):
                continue
            group_out[type_key] = [
                to_relative_posix(p, base_dir)
                for p in paths
                if isinstance(p, str) and p
            ]
        result[group_key] = group_out
    return result


def finalize_manifest_for_phase2(manifest: Dict[str, Any], manifest_path: str) -> Dict[str, Any]:
    """把 manifest 转换为符合 Phase 1→Phase 2 契约的最终形态。

    Args:
        manifest: 已经经过各 step 写入的 manifest dict
        manifest_path: manifest 文件路径（base_dir 取其所在目录）

    Returns:
        修改后的 manifest（原 dict 被就地修改）
    """
    base_dir = os.path.abspath(os.path.dirname(manifest_path))

    # 1. 写入 schema 版本与运行元数据
    manifest["schema_version"] = SCHEMA_VERSION
    meta = manifest.setdefault("_meta", {})
    meta["updated_at"] = datetime.now().isoformat(timespec="seconds")
    meta["phase1_completed_at"] = meta.get("phase1_completed_at") or meta["updated_at"]
    try:
        meta["phase1_host"] = meta.get("phase1_host") or socket.gethostname()
    except Exception:
        meta.setdefault("phase1_host", "")

    # 2. final_log_root 固定为 final_logs（相对 manifest 所在目录）
    final_root = manifest.get("final_log_root", "")
    if final_root:
        manifest["final_log_root"] = to_relative_posix(final_root, base_dir) or "final_logs"
    else:
        manifest["final_log_root"] = "final_logs"

    # 3. trace_exports 内部的路径字段相对化
    #    schema 要求两个 key 必须存在（可以是空对象），保证 AEE 单（无 trace）也通过校验
    trace_exports = manifest.setdefault("trace_exports", {})
    trace_exports.setdefault("aggregated_files", {})
    trace_exports.setdefault("copied_support_files", {})
    trace_exports["aggregated_files"] = _relativize_aggregated_files(
        trace_exports["aggregated_files"], base_dir
    )
    trace_exports["copied_support_files"] = _relativize_support_files(
        trace_exports["copied_support_files"], base_dir
    )

    # 4. 兼容字段：清理过去存的绝对路径（不直接删，置空，避免误用）
    for legacy_key in ("workspace_root", "final_log_dirs"):
        if legacy_key in manifest:
            manifest[legacy_key] = ""

    return manifest


def sanitize_schema_typed_optional_blocks(manifest: Dict[str, Any]) -> None:
    """修复 pipeline 曾将「进程退出码」等误写入 schema 声明为 object 的字段。

    - ``mddb``：fetch 步骤返回值曾为 ``0``，真实负载在 ``mddb_fetch``。
    - ``pcap_export``：pcap 脚本写入 ``pcap_exports``，返回值曾为 ``0``。
    - ``analysis``：若被写成非 object，重置为 ``{}`` 以满足 schema。
    """
    mddb_val = manifest.get("mddb")
    if mddb_val is not None and not isinstance(mddb_val, dict):
        mf = manifest.get("mddb_fetch")
        manifest["mddb"] = deepcopy(mf) if isinstance(mf, dict) else {"results": []}

    pexp = manifest.get("pcap_export")
    if pexp is not None and not isinstance(pexp, dict):
        pes = manifest.get("pcap_exports")
        manifest["pcap_export"] = deepcopy(pes) if isinstance(pes, dict) else {"results": []}
    if "pcap_export" not in manifest and isinstance(manifest.get("pcap_exports"), dict):
        manifest["pcap_export"] = deepcopy(manifest["pcap_exports"])

    analysis_val = manifest.get("analysis")
    if analysis_val is not None and not isinstance(analysis_val, dict):
        manifest["analysis"] = {}


def _ensure_jira_required_fields(manifest: Dict[str, Any]) -> None:
    """补齐 jira 字段，保证 schema 必填项存在（允许空字符串）。"""
    jira = manifest.setdefault("jira", {})
    defaults = {
        "summary": "",
        "description": "",
        "comments_text": "",
        "url_roles": {},
        "affected_versions": [],
        "urls_by_type": {
            "box": [],
            "feishu_file": [],
            "network_share": [],
            "http_direct": [],
        },
        "time_points": [],
        "test_steps": "",
        "expected_result": "",
        "actual_result": "",
        "time_window": {"start": None, "end": None},
        "platform": "",
        "chip_vendor": "",
        "chip_model": "",
        "sw_version": "",
    }
    for key, default_value in defaults.items():
        if key not in jira:
            jira[key] = deepcopy(default_value)


def validate_manifest_strict(manifest: Dict[str, Any]) -> None:
    """对 manifest 做严格 schema 校验，失败立即 raise。

    依赖 jsonschema 库。"""
    try:
        from jsonschema import Draft202012Validator
    except ImportError as e:
        raise RuntimeError(
            "缺少 jsonschema 依赖。请执行：pip install jsonschema>=4.0.0"
        ) from e

    schema_path = _schema_path()
    if not schema_path.is_file():
        raise RuntimeError(f"未找到 schema 文件: {schema_path}")
    with open(schema_path, "r", encoding="utf-8") as fp:
        schema = json.load(fp)

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(manifest), key=lambda e: list(e.absolute_path))
    if errors:
        lines = ["Manifest schema 校验失败："]
        for err in errors[:20]:
            path_str = "/".join(str(p) for p in err.absolute_path) or "<root>"
            lines.append(f"  - [{path_str}] {err.message}")
        if len(errors) > 20:
            lines.append(f"  ... 共 {len(errors)} 条错误，仅显示前 20 条")
        raise ValueError("\n".join(lines))


def finalize_and_validate(manifest: Dict[str, Any], manifest_path: str) -> Dict[str, Any]:
    """便捷入口：finalize + ensure_jira + strict validate 三连。"""
    sanitize_schema_typed_optional_blocks(manifest)
    _ensure_jira_required_fields(manifest)
    finalize_manifest_for_phase2(manifest, manifest_path)
    validate_manifest_strict(manifest)
    return manifest
