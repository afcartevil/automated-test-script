from __future__ import annotations

import importlib.util
from pathlib import Path

ITEM_ID = 9
MODULE = "memory"


def run(device_info=None, step_update=None, **context):
    helper = Path(__file__).with_name("_item_case.py")
    spec = importlib.util.spec_from_file_location(
        "kernel_feature_memory_item_case", helper
    )
    if spec is None or spec.loader is None:
        return {"status": "fail", "message": f"无法加载 {helper}", "full_automation": True}
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # 勿把 run_case 注入的 module 再经 **context 传入，会与 module= 冲突
    return mod.run_spd_item(
        ITEM_ID,
        device_info=device_info,
        step_update=step_update,
        module=MODULE,
    )
