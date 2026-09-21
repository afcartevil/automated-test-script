from __future__ import annotations

import importlib.util
from pathlib import Path

ITEM_ID = 19


def run(device_info=None, step_update=None, **context):
    helper = Path(__file__).with_name("_item_case.py")
    spec = importlib.util.spec_from_file_location(
        "kernel_feature_stability_item_case", helper
    )
    if spec is None or spec.loader is None:
        return {"status": "fail", "message": f"无法加载 {helper}", "full_automation": True}
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run_checklist_item(
        ITEM_ID, device_info=device_info, step_update=step_update, **context
    )
