"""flow_power_game 步骤 3：游戏测试前置条件探测。

输出 JSON（game_precondition.json）: test_conditions, completeness, evidence
配置: references/test-condition-standards.yaml
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from precondition_probe import probe_test_conditions


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def references_dir() -> Path:
    return skill_root() / "references"


def analyze_game_precondition(
    log_path: Path,
    start: datetime,
    end: datetime,
    *,
    game_package: str = "",
    project: str = "",
    test_case: str = "",
    pre_minutes: int = 5,
    brightness_summary: dict[str, Any] | None = None,
    discover_logs: Callable[..., dict[str, list[Path]]],
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    fmt_time: Callable[[datetime | None], str],
) -> dict[str, Any]:
    pre_s = max(0, pre_minutes) * 60
    logs = discover_logs(log_path)
    test_conditions = probe_test_conditions(
        log_path,
        logs,
        start,
        end,
        pre_s,
        brightness_summary or {},
        references_dir(),
        extract_ts,
        iter_lines,
        game_package.strip(),
        project=project.strip(),
        test_case=test_case.strip(),
    )
    complete = test_conditions.get("completeness", {})
    if not isinstance(complete, dict):
        complete = {"score": complete}
    missing = test_conditions.get("missing_items") or complete.get("missing_items") or complete.get("missing") or []
    status = "ok" if not missing else "partial"
    if not logs.get("main_log") and not logs.get("sys_log"):
        status = "failed"

    scenario = test_conditions.get("scenario") or {}
    setting = test_conditions.get("brightness_volume_setting") or {}
    return {
        "status": status,
        "log_path": str(log_path),
        "game_window": {
            "start": fmt_time(start),
            "end": fmt_time(end),
            "duration_seconds": int((end - start).total_seconds()),
            "package": game_package.strip(),
        },
        "test_conditions": test_conditions,
        "notes": [
            f"前置条件完整度: {test_conditions.get('completeness', 'unknown')}",
            f"缺失项: {len(missing)}",
            (
                f"项目={setting.get('project') or setting.get('project_requested') or '未指定'} "
                f"用例={scenario.get('label') or scenario.get('id')} "
                f"目标亮度等级={scenario.get('target_brightness_level')} "
                f"目标音量档={scenario.get('target_volume_index')}"
            ),
            "当前读取测试亮度+音量（按项目×用例查表）；其它前置条件暂未启用",
            f"物理标定说明: { (setting.get('physical_standard') or {}).get('brightness_nits', 350) }nit / "
            f"{ (setting.get('physical_standard') or {}).get('volume_db', 72) }dB（不直接比对日志）",
        ],
    }
