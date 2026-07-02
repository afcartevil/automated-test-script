#!/usr/bin/env python3
"""audio-feature-adaptation Skill 的轻量辅助工具。

该脚本只做信息检查、计划生成、宏控检查和轻量验证。
它不修改文件，也不替代 SOP 对不确定项做决策。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


FEATURES = {
    "dts": {
        "macros": {
            "ProjectConfig.mk": {
                "TRAN_DTS_SUPPORT": "yes",
                "TRAN_DTS_TUNING_PATH": "{project_name1}",
            }
        },
        "scm": ["ro.tr_audio.dts.feature.support=1"],
        "manual": ["如果 DTS 库升级过，需要重新调试 DTS 参数。"],
    },
    "dolby": {
        "macros": {
            "ProjectConfig.mk": {
                "DOLBY_TUNING_PATH": "vendor/transsion/vendor_modules/common/audiodolby/tuning/{project_pair}/",
                "MEDIA_CODECS_C2_FILE": "device/mediatek/{platform_name}/media_codecs_c2_svp.xml",
                "TRAN_AUDIO_DOLBY_SUPPORT": "yes",
            }
        },
        "scm": ["persist.tr_audio.dolby.feature.support"],
        "manual": [],
    },
    "super_volume": {
        "macros": {},
        "scm": ["ro.tr_audio.supervol.feature.support"],
        "manual": [],
    },
    "hac": {
        "macros": {"ProjectConfig.mk": {"MTK_HAC_SUPPORT": "yes"}},
        "scm": [],
        "manual": [],
    },
    "ultrasound_proximity": {
        "macros": {
            "ProjectConfig.mk": {
                "TRAN_AUDIO_ELLIPTIC_USND_SUPPORT": "yes",
                "TRAN_AUDIO_ELLIPTIC_NOSPEAKER_SUPPORT": "yes",
                "MTK_ULTRASND_PROXIMITY": "yes",
            },
            "scp/project.mk": {"CFG_MTK_ULTRASND_PROXIMITY": "yes"},
        },
        "scm": [
            "ro.odm.tr_audio.midtest_ultrasound.support",
            "ro.tr_audio.ultrasound.support",
            "ro.vendor.audio.us.proximity",
        ],
        "manual": [],
    },
    "low_power_call": {
        "macros": {},
        "scm": [],
        "manual": ["执行前需要提供 ADSP 支持情况和 ADSP 类型。"],
    },
    "le_audio_offload": {
        "macros": {},
        "scm": [],
        "manual": ["确认 device-vext.mk 中包含两条 LE Audio offload ODM 属性。"],
    },
    "usnd_anti_touch": {
        "macros": {
            "ProjectConfig.mk": {"TRAN_AUDIO_ANTI_TOUCH_SUPPORT": "yes"},
            "scp/project.mk": {"CFG_ANTI_TOUCH_ULTRASOUND_SUPPORT": "yes"},
        },
        "scm": [],
        "manual": [],
    },
    "bttran_call": {
        "macros": {"ProjectConfig.mk": {"TRAN_AUDIO_BTTRANCALL_SUPPORT": "yes"}},
        "scm": [],
        "manual": [],
    },
}


def project_tokens(project_name: str) -> dict[str, str]:
    parts = [part for part in project_name.split("_") if part]
    if len(parts) < 2:
        raise ValueError("project_name 必须能按 '_' 至少拆出 project_name1 和 project_name2")
    values = {
        "project_name": project_name,
        "project_name1": parts[0],
        "project_name2": parts[1],
        "project_pair": f"{parts[0]}_{parts[1]}",
    }
    for index, part in enumerate(parts, start=1):
        values[f"project_name{index}"] = part
    return values


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def find_macro(text: str, macro: str) -> list[str]:
    pattern = re.compile(rf"^\s*{re.escape(macro)}\s*(?::=|=)\s*(.*?)\s*$", re.MULTILINE)
    return [match.group(1) for match in pattern.finditer(text)]


def find_platform(project_config: Path) -> tuple[str | None, list[str]]:
    if not project_config.exists():
        return None, [f"缺少 ProjectConfig.mk：{project_config}"]
    values = find_macro(read_text(project_config), "MTK_PLATFORM")
    active_values = [value.strip().lower() for value in values if value.strip()]
    if not active_values:
        return None, ["未找到 MTK_PLATFORM"]
    if len(set(active_values)) > 1:
        return None, [f"MTK_PLATFORM 值冲突：{active_values}"]
    return active_values[0], []


def resolve_project_dir(base_code_sunmao: Path, values: dict[str, str]) -> tuple[Path | None, list[str]]:
    projects_dir = base_code_sunmao / "vendor" / "transsion" / "projects"
    default_dir = projects_dir / values["project_pair"]
    if default_dir.exists():
        return default_dir, []
    if not projects_dir.exists():
        return None, [f"未找到 projects 目录：{projects_dir}"]
    matches = [
        child
        for child in projects_dir.iterdir()
        if child.is_dir() and values["project_name1"] in child.name and values["project_name2"] in child.name
    ]
    if len(matches) == 1:
        return matches[0], []
    if not matches:
        return None, [f"未找到匹配 {values['project_pair']} 的升级后项目目录"]
    return None, [f"匹配到多个升级后项目目录：{[match.name for match in matches]}"]


def cmd_inspect(args: argparse.Namespace) -> int:
    try:
        values = project_tokens(args.project_name)
    except ValueError as exc:
        print(json.dumps({"ok": False, "questions": [str(exc)]}, ensure_ascii=False, indent=2))
        return 2

    base_code = Path(args.base_code)
    base_code_sunmao = Path(args.base_code_sunmao)
    project_dir, questions = resolve_project_dir(base_code_sunmao, values)
    platform_name = None
    if project_dir:
        platform_name, platform_questions = find_platform(project_dir / "ProjectConfig.mk")
        questions.extend(platform_questions)

    result = {
        "ok": not questions,
        "base_code": str(base_code),
        "base_code_sunmao": str(base_code_sunmao),
        "project": values,
        "project_dir": str(project_dir) if project_dir else None,
        "platform_name": platform_name,
        "questions": questions,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not questions else 2


def parse_macro_spec(spec: str) -> tuple[Path, str, str]:
    if ":" not in spec or "=" not in spec:
        raise ValueError(f"宏控规格无效：{spec}")
    file_part, macro_part = spec.split(":", 1)
    macro, value = macro_part.split("=", 1)
    return Path(file_part), macro.strip(), value.strip()


def cmd_check_macros(args: argparse.Namespace) -> int:
    failures = []
    checks = []
    for spec in args.macro:
        try:
            path, macro, expected = parse_macro_spec(spec)
        except ValueError as exc:
            failures.append(str(exc))
            continue
        if not path.exists():
            failures.append(f"文件缺失：{path}")
            continue
        values = find_macro(read_text(path), macro)
        status = "missing"
        if values:
            status = "pass" if any(value == expected for value in values) else "mismatch"
        checks.append({"file": str(path), "macro": macro, "expected": expected, "actual": values, "status": status})
        if status != "pass":
            failures.append(f"{path}: {macro} 期望值为 {expected}，实际值为 {values or '缺失'}")
    print(json.dumps({"ok": not failures, "checks": checks, "failures": failures}, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


def format_value(value: str, values: dict[str, str]) -> str:
    return value.format(**values)


def cmd_plan_feature(args: argparse.Namespace) -> int:
    try:
        values = project_tokens(args.project_name)
    except ValueError as exc:
        print(json.dumps({"ok": False, "questions": [str(exc)]}, ensure_ascii=False, indent=2))
        return 2
    values["platform_name"] = args.platform_name or "<platform_name>"

    missing = [feature for feature in args.feature if feature not in FEATURES]
    if missing:
        print(json.dumps({"ok": False, "questions": [f"不支持的特性：{name}" for name in missing]}, ensure_ascii=False, indent=2))
        return 2

    planned = {}
    for feature in args.feature:
        data = FEATURES[feature]
        planned[feature] = {
            "macros": {
                file_name: {macro: format_value(value, values) for macro, value in macros.items()}
                for file_name, macros in data["macros"].items()
            },
            "scm": data["scm"],
            "manual": data["manual"],
        }
    print(json.dumps({"ok": True, "features": planned}, ensure_ascii=False, indent=2))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    failures = []
    files = []
    for file_name in args.file_exists:
        path = Path(file_name)
        exists = path.exists()
        files.append({"file": str(path), "exists": exists})
        if not exists:
            failures.append(f"文件缺失：{path}")

    macro_result = {"checks": []}
    if args.macro:
        namespace = argparse.Namespace(macro=args.macro)
        old_stdout = sys.stdout
        from io import StringIO

        capture = StringIO()
        sys.stdout = capture
        try:
            macro_status = cmd_check_macros(namespace)
        finally:
            sys.stdout = old_stdout
        macro_result = json.loads(capture.getvalue())
        if macro_status != 0:
            failures.extend(macro_result.get("failures", []))

    print(json.dumps({"ok": not failures, "files": files, "macros": macro_result.get("checks", []), "failures": failures}, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查和验证 Audio 特性适配 SOP 工作。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser("inspect", help="推导项目上下文和平台名")
    inspect.add_argument("--base-code", required=True)
    inspect.add_argument("--base-code-sunmao", required=True)
    inspect.add_argument("--project-name", required=True)
    inspect.set_defaults(func=cmd_inspect)

    check = subparsers.add_parser("check-macros", help="检查 MK 宏控值")
    check.add_argument("--macro", action="append", required=True, help="格式：path/to/file.mk:MACRO=value")
    check.set_defaults(func=cmd_check_macros)

    plan = subparsers.add_parser("plan-feature", help="输出特性宏控和提醒")
    plan.add_argument("--project-name", required=True)
    plan.add_argument("--platform-name")
    plan.add_argument("--feature", action="append", required=True, choices=sorted(FEATURES))
    plan.set_defaults(func=cmd_plan_feature)

    verify = subparsers.add_parser("verify", help="验证文件和宏控")
    verify.add_argument("--file-exists", action="append", default=[])
    verify.add_argument("--macro", action="append", default=[], help="格式：path/to/file.mk:MACRO=value")
    verify.set_defaults(func=cmd_verify)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
