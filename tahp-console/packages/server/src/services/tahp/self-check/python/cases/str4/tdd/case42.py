"""STK（SIM卡工具包）各级子菜单能够响应对应的功能反馈。"""

from utils.tdd.device_sim import resolve_dut
from utils.tdd.ui_stk import random_stk_traverse
from test.step_runner import StepRunner


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    device_info = device_info or context.get("device_info") or {}
    dut, dut_id = resolve_dut(device_info)
    if not dut:
        return {"status": "fail", "message": dut_id}

    steps = StepRunner(step_update)
    steps.begin("进入STK并随机点击50次")
    ok, detail = random_stk_traverse(dut_id, clicks=50)
    if not ok:
        steps.fail()
        return {"status": "fail", "message": detail or "STK菜单遍历失败"}
    steps.ok()
    return {"status": "pass", "message": detail or "STK随机点击未离开工具包"}
