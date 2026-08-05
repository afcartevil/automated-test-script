#!/usr/bin/env python3
"""游戏功耗数据汇总与报告 CLI（flow 步骤 12）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_GAME_SCRIPTS = _SCRIPT_DIR.parent.parent / "scripts"

if str(_GAME_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_GAME_SCRIPTS))

from game_log_paths import add_log_path_argument, resolve_log_path  # noqa: E402
from game_power_parser import build_parser, main as run_full_parser  # noqa: E402
from game_skill_debug import (  # noqa: E402
    add_debug_log_arguments,
    debug_begin,
    debug_end,
)


def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="游戏功耗数据汇总（game_summary，封装 game_power_parser）"
    )
    add_log_path_argument(parser)
    add_debug_log_arguments(parser)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--game-package", default="")
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--soc-model", default="")
    parser.add_argument("--pre-minutes", type=int, default=5)
    parser.add_argument("--post-minutes", type=int, default=3)
    parser.add_argument("--min-segment-seconds", type=int, default=120)
    parser.add_argument("--merge-gap-seconds", type=int, default=30)
    parser.add_argument("--startup-seconds", type=int, default=60)
    parser.add_argument("--exit-seconds", type=int, default=30)
    args, extra = parser.parse_known_args(argv)
    debug_begin(args, "game_summary", inputs={k: getattr(args, k) for k in vars(args)})

    log_path = resolve_log_path(args.log_path)
    output_dir = args.output_dir or str(log_path / "analysis")

    fwd = [
        str(log_path),
        "--pre-minutes",
        str(args.pre_minutes),
        "--post-minutes",
        str(args.post_minutes),
        "--min-segment-seconds",
        str(args.min_segment_seconds),
        "--merge-gap-seconds",
        str(args.merge_gap_seconds),
        "--startup-seconds",
        str(args.startup_seconds),
        "--exit-seconds",
        str(args.exit_seconds),
    ]
    if output_dir:
        fwd.extend(["--output-dir", output_dir])
    if args.game_package:
        fwd.extend(["--game-package", args.game_package])
    if args.start:
        fwd.extend(["--start", args.start])
    if args.end:
        fwd.extend(["--end", args.end])
    if args.soc_model:
        fwd.extend(["--soc-model", args.soc_model])
    fwd.extend(extra)
    _code = run_full_parser(fwd)
    debug_end("game_summary", {"forward_argv": fwd, "exit_code": _code}, output_path=output_dir, ok=_code == 0)
    return _code


if __name__ == "__main__":
    raise SystemExit(main())
