"""流水线适配自动化测试 / 通信模块：检查上网。

关闭 Wi‑Fi → 打开移动数据 → ping www.baidu.com / www.qq.com。
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
from utils.tdd.mobile_data_ping import check_mobile_internet


def run(device_info=None, step_update=None, **context):
    serial, error = get_dut_device_id(device_info or {})
    if not serial:
        if callable(step_update):
            step_update(error)
        return {"status": "fail", "message": error, "full_automation": True}

    steps: list[str] = []
    emit(step_update, steps, "关闭Wi‑Fi")
    emit(step_update, steps, "打开移动数据")
    emit(step_update, steps, "ping www.baidu.com / www.qq.com")

    result = check_mobile_internet(serial)
    status = result.get("status") or "fail"
    message = result.get("message") or ""

    if status == "pass":
        emit(step_update, steps, "检查上网-成功")
        return {"status": "pass", "message": message, "full_automation": True}
    if status == "skip":
        emit(step_update, steps, "检查上网-跳过")
        return {"status": "skip", "message": message, "full_automation": True}

    emit(step_update, steps, "检查上网-失败")
    return {
        "status": "fail",
        "message": message or "检查上网失败",
        "full_automation": True,
    }
