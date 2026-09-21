from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .proc import CommandError
from .progress import emit, make_event_callback
from .sync import sync_checklist


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="checklist-scmp-sync",
        description="根据飞书 checklist 标题解析项目/tOS，查询 SCMP 市场支持并回写「此特性是否支持」。",
    )
    parser.add_argument("--url", required=True, help="飞书电子表格或 Wiki 链接")
    parser.add_argument("--dry-run", action="store_true", help="只生成报告，不写飞书")
    parser.add_argument("--project", help="覆盖标题中的项目编码，如 X6879")
    parser.add_argument(
        "--tos-version",
        help="覆盖标题中的 tOS 版本，如 16.3 / 16.3.0 / 17",
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="包含隐藏表和名称带「废弃」的 sheet",
    )
    parser.add_argument(
        "--sheet-name",
        action="append",
        default=[],
        help="只处理指定 sheet，可重复",
    )
    parser.add_argument(
        "--tones-cli",
        help="tones-scmp scripts/run.py 路径；默认自动查找或读 TONES_SCMP_CLI",
    )
    parser.add_argument(
        "--format",
        choices=["jsonl", "json"],
        default="jsonl",
        help="jsonl=运行中逐行输出进展（默认，适合 Web UI）；json=结束后输出完整报告",
    )
    parser.add_argument(
        "--log-file",
        help="JSONL 日志路径。默认写入 logs/checklist-scmp-sync-<时间戳>.jsonl",
    )
    parser.add_argument(
        "--no-log-file",
        action="store_true",
        help="不写日志文件，只走 stdout",
    )
    return parser


def default_log_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path.cwd() / "logs" / f"checklist-scmp-sync-{stamp}.jsonl"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    stream = args.format == "jsonl"
    log_fp = None
    log_path: Path | None = None
    if not args.no_log_file:
        log_path = Path(args.log_file) if args.log_file else default_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fp = log_path.open("a", encoding="utf-8")
    on_event = make_event_callback(to_stdout=stream, log_fp=log_fp)
    try:
        if log_path is not None:
            emit(on_event, "log_file", path=str(log_path), message=f"日志文件：{log_path}")
        result = sync_checklist(
            args.url,
            dry_run=args.dry_run,
            project=args.project,
            tos_version=args.tos_version,
            include_hidden=args.include_hidden,
            sheet_names=args.sheet_name,
            tones_cli=args.tones_cli,
            on_event=on_event,
        )
        emit(
            on_event,
            "report",
            ok=result.get("ok"),
            data=result.get("data"),
            message="完整报告已生成",
        )
        if not stream:
            print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return 0 if result.get("ok") else 2
    except (CommandError, ValueError, FileNotFoundError, RuntimeError) as exc:
        emit(
            on_event,
            "error",
            ok=False,
            error={"message": str(exc)},
            message=str(exc),
        )
        if not stream:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "event": "error",
                        "error": {"message": str(exc)},
                        "message": str(exc),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                flush=True,
            )
        return 1
    finally:
        if log_fp is not None:
            log_fp.close()


if __name__ == "__main__":
    sys.exit(main())
