"""流水线适配自动化测试 / 通信模块：IMEI 号检查。

工模 MainActivity → 右上角更多(menu_drawer) → 软件信息 → 读取 IMEI号。
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
from utils.driver.tranfacmode_software_info import (
    get_imei_from_factory_software_info,
    validate_imei_text,
)


def run(device_info=None, step_update=None, **context):
    serial, error = get_dut_device_id(device_info or {})
    if not serial:
        if callable(step_update):
            step_update(error)
        return {"status": "fail", "message": error, "full_automation": True}

    steps: list[str] = []
    emit(step_update, steps, "进入工厂模式")
    emit(step_update, steps, "打开更多选项并进入软件信息")
    emit(step_update, steps, "读取IMEI号")

    imei_text = (
        get_imei_from_factory_software_info(
            serial,
            result_dir=context.get("result_dir"),
        )
        or ""
    ).strip()
    ok, reason = validate_imei_text(imei_text)
    if ok:
        emit(step_update, steps, "读取IMEI号-成功")
        return {
            "status": "pass",
            "message": imei_text,
            "full_automation": True,
        }

    emit(step_update, steps, "读取IMEI号-失败")
    return {
        "status": "fail",
        "message": reason or "IMEI号无效（为空或全是0）",
        "full_automation": True,
    }
