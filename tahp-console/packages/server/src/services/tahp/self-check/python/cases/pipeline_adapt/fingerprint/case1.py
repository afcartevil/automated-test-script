"""流水线适配自动化测试 / 指纹+人脸模块入口（参考 tp：一模块一 case）。"""

from __future__ import annotations

import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
for _path in (_DIR, _DIR.parent, _DIR.parents[2]):
    p = str(_path)
    if p not in sys.path:
        sys.path.insert(0, p)

from _common import emit, get_dut_device_id
from test_cases import run_all_test_cases


def run(device_info=None, step_update=None, **context):
    serial, error = get_dut_device_id(device_info or {})
    if not serial:
        if callable(step_update):
            step_update(error)
        return {"status": "fail", "message": error, "full_automation": True}

    results, steps = run_all_test_cases(
        serial,
        step_update=step_update,
        result_dir=context.get("result_dir"),
    )
    total = len(results)
    failed = [r for r in results if r.get("status") not in ("pass", "skip")]
    skip_n = sum(1 for r in results if r.get("status") == "skip")

    if not failed:
        hint = f"，跳过 {skip_n} 项" if skip_n else ""
        msg = f"指纹/人脸适配检查通过，共 {total} 项{hint}"
        emit(step_update, steps, msg)
        return {"status": "pass", "message": msg, "full_automation": True}

    first = failed[0]
    reason = f"{first.get('name')}: {first.get('message')}"
    msg = f"{len(failed)}/{total} 项失败; {reason}"
    emit(step_update, steps, msg)
    return {"status": "fail", "message": msg, "full_automation": True}
