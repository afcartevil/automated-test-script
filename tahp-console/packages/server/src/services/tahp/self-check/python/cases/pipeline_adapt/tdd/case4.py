"""流水线适配自动化测试 / 通信模块：检查收发短信。

向运营商服务号发短信并等待回复，用于验证短信发送与接收能力
（内容选用各运营商常用查询指令，仅为探针，用例目标不是查话费）。
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
from utils.tdd.carrier_balance_sms import query_balance_via_sms


def run(device_info=None, step_update=None, **context):
    serial, error = get_dut_device_id(device_info or {})
    if not serial:
        if callable(step_update):
            step_update(error)
        return {"status": "fail", "message": error, "full_automation": True}

    steps: list[str] = []
    emit(step_update, steps, "检查SIM卡并识别运营商（优先卡1）")
    emit(step_update, steps, "发送短信并等待运营商回复")

    result = query_balance_via_sms(
        serial,
        result_dir=context.get("result_dir"),
    )
    status = result.get("status") or "fail"
    message = result.get("message") or ""

    if status == "pass":
        emit(step_update, steps, "检查收发短信-成功")
        return {"status": "pass", "message": message, "full_automation": True}
    if status == "skip":
        emit(step_update, steps, "检查收发短信-跳过")
        return {"status": "skip", "message": message, "full_automation": True}

    emit(step_update, steps, "检查收发短信-失败")
    return {
        "status": "fail",
        "message": message or "检查收发短信失败",
        "full_automation": True,
    }
