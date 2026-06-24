#!/usr/bin/env python3
"""Manifest 更新工具（固定脚本，禁止 AI 自建临时脚本替代）。

推荐用法（Windows 友好，避免命令行 JSON 转义）::

    python scripts/update_manifest.py \\
        --manifest Z:\\skills\\data_store_linux\\OS162-37733\\job_manifest.json \\
        --stage l0 \\
        --data-file Z:\\skills\\data_store_linux\\OS162-37733\\.stage_l0.json

每层分析完成后调用一次；L3 的 data JSON 可含 ``final_report`` 字段（与 l3_conclusion 同级写入 manifest）。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent
SHARED_DIR = SCRIPT_DIR / "_shared"
for _p in (str(SHARED_DIR), str(SCRIPT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from skill_env import load_skill_env  # noqa: E402

load_skill_env()


def load_manifest(manifest_path: Path) -> dict:
    if not manifest_path.exists():
        logger.error("manifest 文件不存在: %s", manifest_path)
        sys.exit(1)
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error("manifest JSON 格式错误: %s", e)
        sys.exit(1)


def save_manifest(manifest_path: Path, manifest: dict) -> None:
    try:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        logger.info("Manifest 已更新: %s", manifest_path)
    except OSError as e:
        logger.error("保存 manifest 失败: %s", e)
        sys.exit(1)


def touch_meta(manifest: dict) -> None:
    manifest.setdefault("_meta", {})
    manifest["_meta"]["updated_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def load_stage_data(args: argparse.Namespace) -> dict:
    if args.data_file:
        data_path = Path(args.data_file)
        if not data_path.is_file():
            logger.error("--data-file 不存在: %s", data_path)
            sys.exit(1)
        try:
            with open(data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error("--data-file 不是有效 JSON: %s", e)
            sys.exit(1)
    if args.data:
        try:
            return json.loads(args.data)
        except json.JSONDecodeError as e:
            logger.error("--data 不是有效 JSON: %s", e)
            sys.exit(1)
    logger.error("必须提供 --data-file 或 --data 之一")
    sys.exit(1)


def resolve_manifest_path(args: argparse.Namespace) -> Path:
    if args.manifest:
        return Path(args.manifest)
    if not args.issue_key:
        logger.error("未指定 --manifest 时必须提供 --issue-key")
        sys.exit(1)
    workspace = args.workspace or os.environ.get("WORKSPACE_ROOT", "")
    if not workspace:
        logger.error("未指定 --workspace 且 WORKSPACE_ROOT 未配置")
        sys.exit(1)
    return Path(workspace) / args.issue_key / "job_manifest.json"


def update_l0(manifest: dict, data: dict) -> dict:
    manifest.setdefault("analysis", {})
    manifest["analysis"]["l0_baseline"] = data
    return manifest


def update_l1(manifest: dict, data: dict) -> dict:
    manifest.setdefault("analysis", {})
    manifest["analysis"]["l1_business"] = data
    return manifest


def update_l2(manifest: dict, domain: str, data: dict) -> dict:
    manifest.setdefault("analysis", {})
    manifest["analysis"].setdefault("l2_domains", {})
    manifest["analysis"]["l2_domains"][domain] = data
    return manifest


def update_l3(manifest: dict, data: dict) -> dict:
    manifest.setdefault("analysis", {})
    payload = dict(data)
    final_report = payload.pop("final_report", None)
    manifest["analysis"]["l3_conclusion"] = payload
    if final_report is not None:
        manifest["analysis"]["final_report"] = final_report
    return manifest


def main() -> None:
    default_workspace = os.environ.get("WORKSPACE_ROOT", "")

    parser = argparse.ArgumentParser(description="更新 manifest 分析字段（固定脚本）")
    parser.add_argument("--manifest", help="job_manifest.json 完整路径（优先于 issue-key + workspace）")
    parser.add_argument("--issue-key", help="Jira 单号（与 --workspace 组合定位 manifest）")
    parser.add_argument("--stage", required=True, choices=["l0", "l1", "l2", "l3"], help="分析阶段")
    parser.add_argument("--domain", help="L2 域名（l2 必填）")
    data_group = parser.add_mutually_exclusive_group(required=True)
    data_group.add_argument("--data-file", help="阶段结果 JSON 文件路径（Windows 推荐）")
    data_group.add_argument("--data", help="阶段结果 JSON 字符串（Linux/Mac 短数据可用）")
    parser.add_argument(
        "--workspace",
        default=default_workspace,
        help="工作空间根目录（默认 WORKSPACE_ROOT）",
    )
    args = parser.parse_args()

    data = load_stage_data(args)
    manifest_path = resolve_manifest_path(args)
    manifest = load_manifest(manifest_path)

    if args.stage == "l0":
        manifest = update_l0(manifest, data)
    elif args.stage == "l1":
        manifest = update_l1(manifest, data)
    elif args.stage == "l2":
        if not args.domain:
            logger.error("L2 阶段需要 --domain 参数")
            sys.exit(1)
        manifest = update_l2(manifest, args.domain, data)
    elif args.stage == "l3":
        manifest = update_l3(manifest, data)

    touch_meta(manifest)
    save_manifest(manifest_path, manifest)

    analysis = manifest.get("analysis", {})
    if args.stage == "l0":
        preview = analysis.get("l0_baseline", {})
    elif args.stage == "l1":
        preview = analysis.get("l1_business", {})
    elif args.stage == "l2":
        preview = analysis.get("l2_domains", {}).get(args.domain, {})
    else:
        preview = {
            "l3_conclusion": analysis.get("l3_conclusion", {}),
            "final_report_len": len(analysis.get("final_report", "") or ""),
        }
    logger.info("更新后的内容:\n%s", json.dumps(preview, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
