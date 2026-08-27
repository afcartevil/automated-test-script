"""流水线适配自动化测试 / 通信模块：基带版本号检查。

复用周版本 week/tdd/case9 的 UI 读取实现（utils.tdd.ui_baseband_version）。
"""

from __future__ import annotations

import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
for _path in (_DIR, _DIR.parent, _DIR.parents[2]):
    p = str(_path)
    if p not in sys.path:
        sys.path.insert(0, p)

from _common import emit, get_dut_device_id
from utils.tdd.ui_baseband_version import get_baseband_version


def run(device_info=None, step_update=None, **context):
    serial, error = get_dut_device_id(device_info or {})
    if not serial:
        if callable(step_update):
            step_update(error)
        return {"status": "fail", "message": error, "full_automation": True}

    steps: list[str] = []
    emit(step_update, steps, "读取基带版本号")

    baseband_version = (get_baseband_version(serial) or "").strip()
    if baseband_version:
        emit(step_update, steps, "读取基带版本号-成功")
        return {
            "status": "pass",
            "message": baseband_version,
            "full_automation": True,
        }

    emit(step_update, steps, "读取基带版本号-失败")
    return {
        "status": "fail",
        "message": "未读取到基带版本号",
        "full_automation": True,
    }
