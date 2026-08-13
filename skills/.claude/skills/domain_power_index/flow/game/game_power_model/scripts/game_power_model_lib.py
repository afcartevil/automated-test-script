"""flow_power_game 步骤 4：功耗拆解模型与归因分类。

输出 JSON（game_power_model.json）: power_formula, subsystems, cause_categories
"""

from __future__ import annotations

import sys
from typing import Any


def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


POWER_FORMULA = "P_total = P_AP + P_Display + P_Audio + P_RF + P_Others"

SUBSYSTEMS: dict[str, dict[str, str]] = {
    "AP": {"modules": "CPU、GPU、DDR", "flow_step": "7"},
    "Display": {"modules": "亮度、刷新率、HDR", "flow_step": "5"},
    "Audio": {"modules": "Codec/DSP、Smart PA", "flow_step": "6"},
    "RF": {"modules": "蜂窝、WiFi、蓝牙", "flow_step": "9"},
    "Others": {"modules": "后台唤醒、温控、传感器", "flow_step": "8、10"},
}

CAUSE_CATEGORIES: list[dict[str, str]] = [
    {"id": "1", "name": "测试手法不符", "version_issue": "否", "steps": "1~3、5~7、9、11"},
    {"id": "2", "name": "器件差异", "version_issue": "否", "steps": "报告拆解表"},
    {"id": "3", "name": "软件策略差异", "version_issue": "是", "steps": "5、7"},
    {"id": "4", "name": "功能差异", "version_issue": "是", "steps": "功能特性扫描"},
    {"id": "5", "name": "异常问题", "version_issue": "是", "steps": "8~10"},
]

DEFAULT_CAUSE_PRIORITY = (
    "CPU/后台异常 > 射频弱网/数传 > 显示(亮度+刷新率) > 音频 > 传感器/其它"
)

OPTIONAL_MTK_LOGS: dict[str, str] = {
    "ged_fps_log": "FPSGO/GED boost（对照步骤 7 调频）",
    "spm_log": "浅睡/唤醒（对照步骤 8 后台）",
    "pmic_log": "电源轨（对照步骤 11 电流）",
    "dramc_log": "DDR/EMI（对照步骤 7 调频）",
}


def build_power_model() -> dict[str, Any]:
    return {
        "power_formula": POWER_FORMULA,
        "subsystems": SUBSYSTEMS,
        "cause_categories": CAUSE_CATEGORIES,
        "default_cause_priority": DEFAULT_CAUSE_PRIORITY,
        "optional_mtk_logs": OPTIONAL_MTK_LOGS,
    }


def summary_text() -> str:
    lines = [POWER_FORMULA, "", "子系统映射:"]
    for domain, info in SUBSYSTEMS.items():
        lines.append(f"  {domain}: {info['modules']} (步骤 {info['flow_step']})")
    lines.append(f"\n默认主因排序: {DEFAULT_CAUSE_PRIORITY}")
    return "\n".join(lines)


if __name__ == "__main__":
    _setup_utf8_stdio()
    print(summary_text())
