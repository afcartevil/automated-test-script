#!/usr/bin/env python3
"""一键跑 flow/game 全流程，默认开启调试日志写入 game_test.log。

开关：
  --debug-log / --no-debug-log
  或环境变量 GAME_SKILL_DEBUG=1

双日志：
  - 传入 case 根目录且其下有 ≥2 份 APLog_* → 分别分析后对比输出澄清报告
  - 或显式 --log-compare <对比机APLog>
  - 仅 1 份日志 → 单机输出（不对比）
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

_SCRIPT_DIR = Path(__file__).resolve().parent
_GAME = _SCRIPT_DIR.parent
_SKILLHUB = _GAME.parents[4]  # .../tran_sw_skillhub
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from game_log_paths import resolve_log_pair, resolve_log_path  # noqa: E402
from game_skill_debug import (  # noqa: E402
    add_debug_log_arguments,
    apply_debug_from_args,
    default_log_path,
    is_debug_enabled,
    write_debug,
)

_PRECOND_SCRIPTS = _GAME / "game_precondition" / "scripts"
if str(_PRECOND_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_PRECOND_SCRIPTS))
from game_project_resolve import resolve_project_context  # noqa: E402


def _py() -> str:
    return sys.executable


def _hub_root() -> Path:
    hub = _GAME
    for _ in range(5):
        hub = hub.parent
    return hub


def _waveform_step(
    *,
    py: str,
    log_path: Path,
    jira_for_steps: str,
    args: argparse.Namespace,
    compare_log_path: Path | None = None,
    high_label: str = "测试机",
    low_label: str = "对比机",
) -> list[str]:
    """双机电流图步骤：须在两侧 game_cpu_gpu_ddr 完成后再调度。"""
    cmd = [
        py,
        str(_GAME / "scripts/run_game_current_cpu_spike.py"),
        str(log_path),
        "--jira-key",
        jira_for_steps,
        "--debug-log",
        "--high-label",
        high_label or "测试机",
        "--low-label",
        low_label or "对比机",
    ]
    if args.pt5:
        cmd += ["--pt5", args.pt5]
    if args.pt5_compare:
        cmd += ["--pt5-compare", args.pt5_compare]
    if args.pt5_dir:
        cmd += ["--pt5-dir", args.pt5_dir]
    if compare_log_path is not None:
        cmd += ["--log-compare", str(compare_log_path)]
    return cmd


def _build_side_steps(
    *,
    log_path: Path,
    analysis: Path,
    project: str,
    test_case: str,
    jira_for_resolve: str,
    jira_for_steps: str,
    py: str,
    hub: Path,
    args: argparse.Namespace,
    include_waveform: bool,
    include_diagnosis: bool,
    compare_analysis: Path | None = None,
    compare_log_path: Path | None = None,
    test_label: str = "",
    compare_label: str = "",
) -> list[list[str]]:
    rel = lambda *parts: str((hub.joinpath(*parts)).resolve())

    precond_cmd = [
        py,
        str(_GAME / "game_precondition/scripts/game_precondition.py"),
        str(log_path),
        "--debug-log",
        "--no-interactive",
    ]
    if project:
        precond_cmd += ["--project", project]
    if test_case:
        precond_cmd += ["--test-case", test_case]
    if jira_for_resolve:
        precond_cmd += ["--jira-key", jira_for_resolve]

    brightness_cmd = [
        py,
        str(_GAME / "game_brightness/scripts/game_brightness.py"),
        str(log_path),
        "--debug-log",
    ]
    if project:
        brightness_cmd += ["--project", project]
    if test_case:
        brightness_cmd += ["--test-case", test_case]

    power_model_cmd = [
        py,
        str(_GAME / "game_power_model/scripts/game_power_model.py"),
        "--output",
        str(analysis / "game_power_model.json"),
        "--analysis-dir",
        str(analysis),
        "--debug-log",
    ]
    if project:
        power_model_cmd += ["--project", project]
    if test_case:
        power_model_cmd += ["--test-case", test_case, "--config", test_case]
    if test_label:
        power_model_cmd += ["--test-device", test_label]
    if compare_label:
        power_model_cmd += ["--compare-device", compare_label]
    if getattr(args, "sw_version", ""):
        power_model_cmd += ["--version", str(args.sw_version).strip()]
    if getattr(args, "feishu_hardware_url", ""):
        power_model_cmd += ["--feishu-url", str(args.feishu_hardware_url).strip()]
    if getattr(args, "offline_hardware_power", False):
        power_model_cmd += ["--offline-only"]

    steps: list[list[str]] = [
        [
            py,
            rel("analysis", "base", "mtk_kernellog_convert", "scripts", "time_convert.py"),
            str(log_path),
            "--debug-log",
        ],
        [py, str(_GAME / "game_time_window/scripts/game_time_window.py"), str(log_path), "--debug-log"],
        precond_cmd,
        power_model_cmd,
        brightness_cmd,
        [py, str(_GAME / "game_volume/scripts/game_volume.py"), str(log_path), "--debug-log"],
        [py, str(_GAME / "game_cpu_gpu_ddr/scripts/game_cpu_gpu_ddr.py"), str(log_path), "--debug-log"],
        [py, str(_GAME / "game_background/scripts/game_background.py"), str(log_path), "--debug-log"],
        [py, str(_GAME / "game_network/scripts/game_network.py"), str(log_path), "--debug-log"],
        # 条件步骤：无 networklog/T_game 重叠 cap 时自行 skipped
        [
            py,
            str(_GAME / "game_network_cap/scripts/game_network_cap.py"),
            str(log_path),
            "--debug-log",
        ],
        [py, str(_GAME / "game_thermal/scripts/game_thermal.py"), str(log_path), "--debug-log"],
        [
            py,
            str(_GAME / "game_summary/scripts/game_summary.py"),
            str(log_path),
            "--output-dir",
            str(analysis),
            "--debug-log",
        ],
        [
            py,
            str(_GAME / "game_current_log_correlate/scripts/game_current_log_correlate.py"),
            str(log_path),
            "--jira-key",
            jira_for_steps,
            "--debug-log",
        ]
        + (["--pt5", args.pt5] if args.pt5 else [])
        + (["--pt5-dir", args.pt5_dir] if args.pt5_dir else []),
    ]

    if include_waveform:
        steps.append(
            _waveform_step(
                py=py,
                log_path=log_path,
                jira_for_steps=jira_for_steps,
                args=args,
                compare_log_path=compare_log_path,
                high_label=test_label or "测试机",
                low_label=compare_label or "对比机",
            )
        )

    if include_diagnosis:
        device_model = args.device_model.strip() if getattr(args, "device_model", "") else ""
        if not device_model:
            if compare_label:
                device_model = f"{test_label} / {compare_label}"
            else:
                device_model = "测试机 / 竞品机"
        diag = [
            py,
            str(_GAME / "game_diagnosis_report/scripts/game_diagnosis_report.py"),
            str(log_path),
            "--jira-key",
            jira_for_steps,
            "--device-model",
            device_model,
            "--game-title",
            args.game_title.strip() or "MLBB",
            "--test-power-ma",
            str(args.test_power_ma),
            "--competitor-power-ma",
            str(args.competitor_power_ma),
            "--delta-power-ma",
            str(args.delta_power_ma),
            "--screen-delta-ma",
            str(args.screen_delta_ma),
            "--speaker-delta-ma",
            str(args.speaker_delta_ma),
            "--cpu-delta-ma",
            str(args.cpu_delta_ma),
            "--adjusted-delta-ma",
            str(max(args.delta_power_ma - (args.screen_delta_ma + args.speaker_delta_ma + args.cpu_delta_ma), 0)),
            "--debug-log",
        ]
        if compare_analysis is not None:
            diag += ["--compare-analysis-dir", str(compare_analysis)]
        if test_label:
            diag += ["--test-device-label", test_label]
        if compare_label:
            diag += ["--compare-device-label", compare_label]
        steps.append(diag)

    return steps


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="跑完整 game flow 并写 game_test.log")
    parser.add_argument(
        "log_path",
        nargs="?",
        default=None,
        help="APLog 目录或 case 根目录（多份 APLog 时自动双机对比）",
    )
    parser.add_argument(
        "--log-compare",
        default="",
        help="对比机 APLog；省略时若 case 下有第二份日志则自动配对",
    )
    parser.add_argument(
        "--no-compare",
        action="store_true",
        help="强制单机输出，即使 case 下有多份 APLog 也不对比",
    )
    add_debug_log_arguments(parser)
    parser.add_argument("--jira-key", default="", help="JIRA 单号；有则解析项目/场景，无则路径模式选项目")
    parser.add_argument(
        "--project",
        default="",
        help="项目名（飞书亮度和音量表）；路径模式未指定且无 JIRA 时交互选择",
    )
    parser.add_argument(
        "--test-case",
        default="",
        help="测试用例 basic/nps；可从 JIRA 推断，默认 basic",
    )
    parser.add_argument(
        "--sw-version",
        default="",
        help="软件版本（飞书硬件功耗台账维度；空则按表内最接近项匹配）",
    )
    parser.add_argument(
        "--feishu-hardware-url",
        default="",
        help="覆盖 game_power_model/references/hardware-power-source.yaml 的飞书表 URL",
    )
    parser.add_argument(
        "--offline-hardware-power",
        action="store_true",
        help="硬件功耗仅读本地缓存，不访问飞书",
    )
    parser.add_argument("--no-interactive", action="store_true", help="禁止交互选项目")
    parser.add_argument("--device-model", default="", help="澄清报告机型栏，默认 测试机标签/对比机标签")
    parser.add_argument("--game-title", default="", help="游戏名，默认 MLBB")
    parser.add_argument("--test-power-ma", type=float, default=920)
    parser.add_argument("--competitor-power-ma", type=float, default=850)
    parser.add_argument("--delta-power-ma", type=float, default=70)
    parser.add_argument("--screen-delta-ma", type=float, default=20)
    parser.add_argument("--speaker-delta-ma", type=float, default=5)
    parser.add_argument("--cpu-delta-ma", type=float, default=10)
    parser.add_argument("--pt5", default="", help="步骤13/电流图：测试机电流文件；省略则自动搜索或 skipped")
    parser.add_argument("--pt5-compare", default="", help="电流图对比机 pt5；省略则单机分析")
    parser.add_argument("--pt5-dir", default="", help="步骤13/电流图搜索目录")
    args = parser.parse_args(argv)

    # default ON for this runner unless --no-debug-log
    if not args.no_debug_log and not args.debug_log:
        args.debug_log = True
    apply_debug_from_args(args, reset_file=True)

    if args.no_compare:
        from game_log_paths import infer_device_label

        primary = resolve_log_path(args.log_path)
        compare = None
        primary_label = infer_device_label(primary)
        compare_label = ""
    else:
        primary, compare, primary_label, compare_label = resolve_log_pair(
            args.log_path, args.log_compare or None
        )
        primary = resolve_log_path(str(primary))
    dual = compare is not None
    if dual and compare is not None:
        compare = resolve_log_path(str(compare))

    analysis = primary / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)

    jira_key = (args.jira_key or "").strip()
    # DEMO 仅作演示单号，不触发真实 JIRA 拉取
    jira_for_resolve = "" if jira_key.upper().startswith("DEMO") else jira_key
    proj_ctx = resolve_project_context(
        log_path=primary,
        project=args.project.strip() or None,
        test_case=args.test_case.strip() or None,
        jira_key=jira_for_resolve or None,
        interactive=False if args.no_interactive else None,
        persist=True,
    )
    project = str(proj_ctx.get("project") or proj_ctx.get("project_requested") or "").strip()
    test_case = str(proj_ctx.get("test_case") or "basic").strip()
    write_debug(
        f"PROJECT_CTX project={project} test_case={test_case} "
        f"source={proj_ctx.get('source')} jira={proj_ctx.get('jira_key')}"
    )
    print(
        f"项目上下文: project={project or '未指定'} test_case={test_case} "
        f"source={proj_ctx.get('source')} "
        f"(表: {proj_ctx.get('table_url') or 'brightness-volume-by-project.yaml'})"
    )
    if dual:
        print(f"双日志对比: 测试机={primary_label} ({primary})")
        print(f"            对比机={compare_label} ({compare})")
    else:
        print(f"单日志模式: {primary_label} ({primary})")

    write_debug(f"FLOW START log_path={primary} compare={compare}")
    write_debug(f"DEBUG_LOG={default_log_path()} enabled={is_debug_enabled()}")

    py = _py()
    hub = _hub_root()
    jira_for_steps = jira_key or "DEMO-GAME-001"

    # 若未指定 pt5-dir 且双机，默认用 case 根（两份 APLog 的共同祖先）搜 pt5
    if dual and not args.pt5_dir and compare is not None:
        from os.path import commonpath

        try:
            args.pt5_dir = str(Path(commonpath([str(primary), str(compare)])))
            write_debug(f"auto pt5-dir={args.pt5_dir}")
        except ValueError:
            pass

    steps: list[list[str]] = []
    # 测试机：分维分析。双机时电流图须等对比机 CPU 产物就绪后再跑，
    # 否则 trend 卡片「对比机异常进程」会空（--log-compare 读不到对侧采样）。
    steps += _build_side_steps(
        log_path=primary,
        analysis=analysis,
        project=project,
        test_case=test_case,
        jira_for_resolve=jira_for_resolve,
        jira_for_steps=jira_for_steps,
        py=py,
        hub=hub,
        args=args,
        include_waveform=not dual,
        include_diagnosis=not dual,
        compare_log_path=compare if dual else None,
        test_label=primary_label,
        compare_label=compare_label if dual else "",
    )

    if dual and compare is not None:
        compare_analysis = compare / "analysis"
        compare_analysis.mkdir(parents=True, exist_ok=True)
        # 对比机：完整分维分析，不做电流图/诊断
        steps += _build_side_steps(
            log_path=compare,
            analysis=compare_analysis,
            project=project,
            test_case=test_case,
            jira_for_resolve=jira_for_resolve,
            jira_for_steps=jira_for_steps,
            py=py,
            hub=hub,
            args=args,
            include_waveform=False,
            include_diagnosis=False,
            test_label=compare_label,
        )
        # 两侧 CPU 产物就绪后再做双机电流图 + 时段异常进程匹配
        steps.append(
            _waveform_step(
                py=py,
                log_path=primary,
                jira_for_steps=jira_for_steps,
                args=args,
                compare_log_path=compare,
                high_label=primary_label or "测试机",
                low_label=compare_label or "对比机",
            )
        )
        # 合并诊断：测试机 + 对比机 analysis
        steps += _build_side_steps(
            log_path=primary,
            analysis=analysis,
            project=project,
            test_case=test_case,
            jira_for_resolve=jira_for_resolve,
            jira_for_steps=jira_for_steps,
            py=py,
            hub=hub,
            args=args,
            include_waveform=False,
            include_diagnosis=True,
            compare_analysis=compare_analysis,
            test_label=primary_label,
            compare_label=compare_label,
        )

    if not is_debug_enabled():
        steps = [[c for c in cmd if c != "--debug-log"] for cmd in steps]

    failed = 0
    for cmd in steps:
        code = subprocess.call(cmd)
        write_debug(f"EXIT {code}: {cmd[1] if len(cmd) > 1 else cmd}")
        if code != 0:
            failed += 1
            print(f"FAILED ({code}): {cmd}")
            # continue remaining steps for debug coverage

    write_debug(f"FLOW END failed_steps={failed} dual={dual}")
    print(f"debug log: {default_log_path()}")
    print(f"failed_steps={failed}")
    print(f"clarify report: {analysis / 'game_power_clarify_report.html'}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
