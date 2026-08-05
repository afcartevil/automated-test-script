#!/usr/bin/env python3
"""功耗拆解模型 CLI（flow 步骤 5）：框架 + 飞书硬件功耗台账。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_GAME_SCRIPTS = _SCRIPT_DIR.parent.parent / "scripts"
for p in (_SCRIPT_DIR, _GAME_SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from game_power_model_lib import build_power_model, summary_text  # noqa: E402
from game_skill_debug import (  # noqa: E402
    add_debug_log_arguments,
    debug_begin,
    debug_end,
)
from hardware_power_lib import resolve_hardware_power  # noqa: E402


def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _load_meta_hints(analysis_dir: Path) -> dict[str, str]:
    """从 game_analysis_meta / precondition 继承项目与用例。"""
    out: dict[str, str] = {}
    for name in ("game_analysis_meta.json", "game_precondition.json"):
        path = analysis_dir / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if name == "game_analysis_meta.json":
            for k in ("project", "test_case", "version", "sw_version", "device_model"):
                if data.get(k) not in (None, "") and k not in out:
                    out[k if k != "sw_version" else "version"] = str(data.get(k))
            if data.get("sw_version") and "version" not in out:
                out["version"] = str(data["sw_version"])
        else:
            pc = data.get("project_context") if isinstance(data.get("project_context"), dict) else {}
            if pc.get("project") and "project" not in out:
                out["project"] = str(pc.get("project"))
            tc = data.get("test_conditions") if isinstance(data.get("test_conditions"), dict) else {}
            scen = tc.get("scenario") if isinstance(tc.get("scenario"), dict) else {}
            if scen.get("test_case") and "test_case" not in out:
                out["test_case"] = str(scen.get("test_case"))
            if data.get("project") and "project" not in out:
                out["project"] = str(data.get("project"))
    return out


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="游戏功耗拆解模型（含飞书硬件功耗台账）")
    add_debug_log_arguments(parser)
    parser.add_argument("--output", default="", help="JSON 输出路径")
    parser.add_argument("--print-text", action="store_true", help="仅打印文本说明")
    parser.add_argument("--project", default="", help="项目名（飞书台账维度）")
    parser.add_argument("--version", default="", help="软件版本（飞书台账维度）")
    parser.add_argument(
        "--config",
        default="",
        help="配置/场景（basic/nps 等；默认取 test_case 或 basic）",
    )
    parser.add_argument("--test-case", default="", help="测试用例；可映射为 config")
    parser.add_argument("--test-device", default="", help="测试机机型标签（如 CN6）")
    parser.add_argument("--compare-device", default="", help="对比机机型标签（如 X6887）")
    parser.add_argument("--feishu-url", default="", help="覆盖 hardware-power-source.yaml 的 source_url")
    parser.add_argument("--sheet-id", default="", help="飞书 sheet tab id")
    parser.add_argument("--offline-only", action="store_true", help="仅读本地缓存，不访问飞书")
    parser.add_argument(
        "--analysis-dir",
        default="",
        help="可选：从此目录的 game_analysis_meta.json 继承 project/test_case",
    )
    args = parser.parse_args(argv)
    debug_begin(args, "game_power_model", inputs={k: getattr(args, k) for k in vars(args)})

    if args.print_text:
        out_txt = (
            Path(args.output).resolve()
            if args.output
            else (Path.cwd() / "analysis" / "game_power_model.txt").resolve()
        )
        out_txt.parent.mkdir(parents=True, exist_ok=True)
        out_txt.write_text(summary_text(), encoding="utf-8")
        print(f"已写入: {out_txt}")
        debug_end("game_power_model", {"mode": "print_text"}, output_path=out_txt, ok=True)
        return 0

    hints: dict[str, str] = {}
    if args.analysis_dir.strip():
        hints = _load_meta_hints(Path(args.analysis_dir))
    elif args.output:
        # 常见：--output <analysis>/game_power_model.json
        out_parent = Path(args.output).resolve().parent
        if out_parent.name == "analysis":
            hints = _load_meta_hints(out_parent)

    project = (args.project or hints.get("project") or "").strip()
    version = (args.version or hints.get("version") or "").strip()
    test_case = (args.test_case or hints.get("test_case") or "").strip()
    config = (args.config or test_case or "basic").strip()
    test_device = (args.test_device or "").strip()
    compare_device = (args.compare_device or "").strip()

    hardware: dict | None = None
    if test_device:
        # 飞书台账「项目」列即为机型代号；project 可空，用 test_device 匹配
        hardware = resolve_hardware_power(
            project=project or test_device,
            version=version,
            config=config,
            test_device=test_device,
            compare_device=compare_device,
            source_url=args.feishu_url,
            sheet_id=args.sheet_id,
            offline_only=bool(args.offline_only),
        )
        print(
            f"硬件功耗台账: status={hardware.get('status')} source={hardware.get('source')} "
            f"known_deltas={len(hardware.get('known_deltas') or [])}"
        )
        sync = hardware.get("sync") if isinstance(hardware.get("sync"), dict) else {}
        if sync:
            print(
                f"  同步: devices={sync.get('devices')} changed={sync.get('changed')} "
                f"updated={sync.get('updated')} reason={sync.get('reason')}"
            )
        for miss in hardware.get("missing") or []:
            print(f"  ! {miss}")
        for err in hardware.get("errors") or []:
            print(f"  ! {err}")
    else:
        print(
            "硬件功耗台账: 跳过（需 --test-device 机型代号，如 CN6；"
            "可先配置 references/hardware-power-source.yaml 的 source_url）"
        )

    result = {
        "skill": "flow_power_game_power_model",
        "status": "ok",
        "power_model": build_power_model(),
        "hardware_power": hardware,
        "analysis_time": datetime.now().isoformat(timespec="seconds"),
    }
    if args.output:
        out_path = Path(args.output).resolve()
    else:
        out_path = (Path.cwd() / "analysis" / "game_power_model.json").resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入: {out_path}")
    debug_end("game_power_model", result, output_path=out_path, ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
