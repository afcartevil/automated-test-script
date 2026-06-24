"""用户可以进入对应SIM卡的流量使用页面查看对应阶段的数据使用状态。"""

from utils.tdd.device_sim import enter_sim_sub_settings_by_sim, get_sim_by_slot, resolve_dut
from utils.tdd.ui_data_usage import read_mobile_data_usage_mb
from test.step_runner import StepRunner


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    device_info = device_info or context.get("device_info") or {}
    dut, dut_id = resolve_dut(device_info)
    if not dut:
        return {"status": "fail", "message": dut_id}

    sim_cards = dut.get("sim_cards") or []
    slots = [s for s in (get_sim_by_slot(sim_cards, 0), get_sim_by_slot(sim_cards, 1)) if s]

    steps = StepRunner(step_update)
    for idx, sim in enumerate(slots, start=1):
        label = f"卡{idx}"
        steps.begin(f"{label}进入子界面并查看移动数据用量")
        if not enter_sim_sub_settings_by_sim(dut_id, sim):
            steps.fail()
            return {"status": "fail", "message": f"{label}进入SIM子界面失败"}
        ok, _, snippet = read_mobile_data_usage_mb(dut_id)
        if not ok:
            steps.fail()
            return {
                "status": "fail",
                "message": f"{label}移动数据用量未大于0({snippet or '未解析到用量'})",
            }
        steps.ok()

    return {
        "status": "pass",
        "message": "各卡移动数据用量页面显示已使用流量大于0",
    }
