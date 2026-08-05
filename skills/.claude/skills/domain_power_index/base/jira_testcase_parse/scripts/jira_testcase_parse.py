#!/usr/bin/env python3
"""CLI：解析 JIRA 描述中的测试用例结构化字段 → JSON。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from jira_testcase_parse_lib import (  # noqa: E402
    parse_jira_testcase,
    self_check,
)


def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _load_jira_info(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"jira_info 不是对象: {path}")
    return data


def _fetch_jira(jira_key: str) -> dict:
    jira_scripts = (
        Path(__file__).resolve().parents[5] / "base" / "jirainfo" / "scripts"
    )
    # scripts → jira_testcase_parse → base → power → domain → analysis
    if str(jira_scripts) not in sys.path:
        sys.path.insert(0, str(jira_scripts))
    from jira_info import JiraInfo  # type: ignore

    info = JiraInfo()
    info.jira_number = jira_key
    return {
        "key": jira_key,
        "summary": info.summary,
        "description": info.description,
        "affect_project": info.affect_project,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="解析功耗 JIRA 描述 Precondition/Test Result 等字段"
    )
    p.add_argument("--jira-key", default="", help="JIRA 单号（需凭证）")
    p.add_argument("--jira-info", default="", help="jira_info.json 路径")
    p.add_argument("--description", default="", help="描述原文")
    p.add_argument("--description-file", default="", help="描述文本文件")
    p.add_argument("--summary", default="", help="摘要（辅助派生功耗/场景）")
    p.add_argument("--affect-project", default="", help="影响项目/机型")
    p.add_argument(
        "-w",
        "--workspace",
        default="",
        help="工作区；有则默认写 analysis/jira_testcase_parse.json",
    )
    p.add_argument("--output", default="", help="输出 JSON 路径")
    p.add_argument("--self-test", action="store_true", help="运行内置样例自检")
    return p


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    args = build_parser().parse_args(argv)

    if args.self_test:
        self_check()
        print("self-test ok")
        return 0

    summary = args.summary or ""
    description = args.description or ""
    affect = args.affect_project or None
    jira_key = (args.jira_key or "").strip() or None

    if args.jira_info:
        info = _load_jira_info(Path(args.jira_info))
        description = description or str(info.get("description") or "")
        summary = summary or str(info.get("summary") or "")
        affect = affect or (str(info.get("affect_project") or "").strip() or None)
        jira_key = jira_key or (str(info.get("key") or "").strip() or None)
    elif args.description_file:
        description = Path(args.description_file).read_text(encoding="utf-8")
    elif jira_key and not description:
        info = _fetch_jira(jira_key)
        description = str(info.get("description") or "")
        summary = summary or str(info.get("summary") or "")
        affect = affect or (str(info.get("affect_project") or "").strip() or None)

    if not description.strip() and not summary.strip():
        print("缺少 description / summary / jira-info / jira-key", file=sys.stderr)
        return 2

    result = parse_jira_testcase(
        description=description,
        summary=summary,
        affect_project=affect,
        jira_key=jira_key,
    )

    out = (args.output or "").strip()
    if not out and args.workspace:
        ws = Path(args.workspace)
        out = str(ws / "analysis" / "jira_testcase_parse.json")
    if not out and jira_key:
        # 默认不强制写盘
        pass

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if out:
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"已写入: {out_path.resolve()}")
    else:
        # 无 --output 时仍写到 cwd/analysis，避免大段 print（AI-02）
        out_path = Path.cwd() / "analysis" / "jira_testcase_parse.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"已写入: {out_path.resolve()}")
    return 0 if result.get("status") != "empty" else 1


if __name__ == "__main__":
    raise SystemExit(main())
