"""设置SIM卡PIN码开启，需要输入相关SIM PIN密码。"""

from utils.tdd.device_sim import resolve_dut
from utils.tdd.ui_sim_pin import (
    open_sim_pin_lock_page,
    reboot_and_unlock,
    set_sim_pin_disabled,
    set_sim_pin_enabled,
)
from test.step_runner import StepRunner


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    device_info = device_info or context.get("device_info") or {}
    dut, dut_id = resolve_dut(device_info)
    if not dut:
        return {"status": "fail", "message": dut_id}

    steps = StepRunner(step_update)
    try:
        steps.begin("进入SIM卡锁定页并开启PIN")
        if not open_sim_pin_lock_page(dut_id):
            steps.fail()
            return {"status": "fail", "message": "进入SIM卡锁定页失败"}
        if not set_sim_pin_enabled(dut_id, skip_page_open=True):
            steps.fail()
            return {"status": "fail", "message": "开启SIM卡PIN锁定失败"}
        steps.ok()

        steps.begin("重启并输入PIN解锁")
        if not reboot_and_unlock(dut_id, timeout_seconds=600, unlock_sim_pin=True):
            steps.fail()
            return {"status": "fail", "message": "重启后PIN解锁失败"}
        steps.ok()

        steps.begin("进入SIM卡锁定页并关闭PIN")
        if not open_sim_pin_lock_page(dut_id):
            steps.fail()
            return {"status": "fail", "message": "进入SIM卡锁定页失败"}
        if not set_sim_pin_disabled(dut_id, skip_page_open=True):
            steps.fail()
            return {"status": "fail", "message": "关闭SIM卡PIN锁定失败"}
        steps.ok()

        return {"status": "pass", "message": "SIM PIN 开/关与重启解锁通过"}
    except Exception as exc:
        set_sim_pin_disabled(dut_id)
        return {"status": "fail", "message": f"SIM PIN 用例异常: {exc}"}
