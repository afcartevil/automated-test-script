#!/usr/bin/env python3
"""Audio feature self-check helper.

This script is intentionally read-only. It parses project options and checks
ProjectConfig.mk style macro values for SOP-based self-checks.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


MACRO_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*(?::=|\?=|\+=|=)\s*(.*?)\s*$")


def split_project_name(project_name: str) -> Dict[str, str]:
    parts = [part for part in project_name.split("_") if part]
    data: Dict[str, str] = {"project_name": project_name}
    for index, part in enumerate(parts, start=1):
        data[f"project_name{index}"] = part
    if len(parts) >= 2:
        data["project_dir_name"] = f"{parts[0]}_{parts[1]}"
    return data


def strip_inline_comment(value: str) -> str:
    if "#" not in value:
        return value.strip()
    return value.split("#", 1)[0].strip()


def collect_macro_values(path: Path, macro: str) -> List[Tuple[int, str, str]]:
    matches: List[Tuple[int, str, str]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = MACRO_RE.match(raw_line)
            if not match:
                continue
            key, value = match.groups()
            if key == macro:
                matches.append((line_no, strip_inline_comment(value), raw_line.rstrip("\n")))
    return matches


def check_macro(path: Path, macro: str, expected: str) -> Dict[str, object]:
    result: Dict[str, object] = {
        "file": str(path),
        "macro": macro,
        "expected": expected,
        "status": "无法判断",
        "evidence": [],
        "reason": "",
    }
    if not path.exists():
        result["reason"] = "检查文件不存在"
        return result
    if not path.is_file():
        result["reason"] = "检查路径不是文件"
        return result

    matches = collect_macro_values(path, macro)
    result["evidence"] = [
        {"line": line_no, "value": value, "content": content}
        for line_no, value, content in matches
    ]
    if not matches:
        result["status"] = "未适配"
        result["reason"] = "未找到有效宏控"
        return result

    values = {value for _, value, _ in matches}
    if len(values) > 1:
        result["status"] = "无法判断"
        result["reason"] = "存在多个互相冲突的有效赋值"
        return result

    actual = next(iter(values))
    if actual == expected:
        result["status"] = "已适配"
        result["reason"] = "宏控值符合 SOP"
    else:
        result["status"] = "未适配"
        result["reason"] = f"宏控值为 {actual!r}，不是期望值 {expected!r}"
    return result


def project_config_path(base_code_sunmao: Path, project_name: str) -> Path:
    data = split_project_name(project_name)
    project_dir_name = data.get("project_dir_name")
    if not project_dir_name:
        raise ValueError("项目编译选项无法拆出 project_name1 和 project_name2")
    return base_code_sunmao / "vendor" / "transsion" / "projects" / project_dir_name / "ProjectConfig.mk"


def command_inspect(args: argparse.Namespace) -> int:
    data = split_project_name(args.project_name)
    if "project_dir_name" not in data:
        print("错误：项目编译选项无法拆出 project_name1 和 project_name2", file=sys.stderr)
        return 2
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def command_check_macro(args: argparse.Namespace) -> int:
    result = check_macro(Path(args.file), args.macro, args.expected)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "已适配" else 1


def command_verify(args: argparse.Namespace) -> int:
    features = {feature.strip().lower() for feature in args.features.split(",") if feature.strip()}
    unsupported = features - {"hac_mtk", "hac", "听力助手-mtk", "听力助手"}
    if unsupported:
        print(f"错误：当前脚本不支持这些特性：{', '.join(sorted(unsupported))}", file=sys.stderr)
        return 2

    config_path = project_config_path(Path(args.base_code_sunmao), args.project_name)
    result = check_macro(config_path, "MTK_HAC_SUPPORT", "yes")
    result["feature"] = "听力助手-MTK"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "已适配" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audio 特性自检只读辅助脚本")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="解析项目编译选项")
    inspect_parser.add_argument("--project-name", required=True, help="从 SPUG 获取的项目编译选项")
    inspect_parser.set_defaults(func=command_inspect)

    macro_parser = subparsers.add_parser("check-macro", help="检查 ProjectConfig.mk 宏控")
    macro_parser.add_argument("--file", required=True, help="待检查文件")
    macro_parser.add_argument("--macro", required=True, help="宏控名称")
    macro_parser.add_argument("--expected", required=True, help="期望值")
    macro_parser.set_defaults(func=command_check_macro)

    verify_parser = subparsers.add_parser("verify", help="执行当前支持特性的自检")
    verify_parser.add_argument("--base-code-sunmao", required=True, help="升级后的 vnd/vendor 侧绝对路径")
    verify_parser.add_argument("--project-name", required=True, help="从 SPUG 获取的项目编译选项")
    verify_parser.add_argument("--features", required=True, help="逗号分隔的特性列表")
    verify_parser.set_defaults(func=command_verify)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except ValueError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
