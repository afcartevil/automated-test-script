"""流水线适配自动化测试 / 通信模块：拨打运营商服务号码。

根据插入 SIM（优先卡1）识别运营商，拨打对应客服号（移动10086/联通10010/电信10000等）。
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
from utils.tdd.carrier_service_dial import dial_carrier_service_number


def run(device_info=None, step_update=None, **context):
    serial, error = get_dut_device_id(device_info or {})
    if not serial:
        if callable(step_update):
            step_update(error)
        return {"status": "fail", "message": error, "full_automation": True}

    steps: list[str] = []
    emit(step_update, steps, "检查SIM卡并识别运营商（优先卡1）")
    emit(step_update, steps, "打开拨号盘并拨打运营商服务号码")

    result = dial_carrier_service_number(
        serial,
        result_dir=context.get("result_dir"),
    )
    status = result.get("status") or "fail"
    message = result.get("message") or ""

    if status == "pass":
        emit(step_update, steps, "拨打运营商服务号码-成功")
        return {"status": "pass", "message": message, "full_automation": True}
    if status == "skip":
        emit(step_update, steps, "拨打运营商服务号码-跳过")
        return {"status": "skip", "message": message, "full_automation": True}

    emit(step_update, steps, "拨打运营商服务号码-失败")
    return {
        "status": "fail",
        "message": message or "拨打运营商服务号码失败",
        "full_automation": True,
    }
