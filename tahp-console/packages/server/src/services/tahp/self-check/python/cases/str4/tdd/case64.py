"""检查UE双卡SA飞模驻网功能：双卡分别视频主叫。"""

from utils.tdd.apk.call import dial_and_check
from utils.tdd.device_sim import fail_result_if_camera_unavailable_for_video, get_sim_by_slot, resolve_aux, resolve_dut
from utils.tdd.sim_setup import NETWORK_TYPE_5G_AUTO, enable_mobile_data, setup_sim_preferred_network
from test.step_runner import StepRunner


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    device_info = device_info or context.get("device_info") or {}
    cam_fail = fail_result_if_camera_unavailable_for_video(device_info)
    if cam_fail:
        return cam_fail
    dut, dut_id = resolve_dut(device_info)
    if not dut:
        return {"status": "fail", "message": dut_id}
    sim1 = get_sim_by_slot(dut.get("sim_cards") or [], 0)
    sim2 = get_sim_by_slot(dut.get("sim_cards") or [], 1)
    if not sim1 or not sim2:
        return {"status": "fail", "message": "测试机非双卡"}
    aux_id, aux_number, _, err = resolve_aux(device_info)
    if err:
        return {"status": "fail", "message": err}

    steps = StepRunner(step_update)
    if not enable_mobile_data(dut_id):
        return {"status": "fail", "message": "打开移动数据失败"}

    for slot_idx, sim, sim_slot in ((0, sim1, 1), (1, sim2, 2)):
        label = f"卡{slot_idx + 1}"
        steps.begin(f"{label}打开，首选网络5G或4G")
        if not setup_sim_preferred_network(dut_id, sim, enable=True, network_type=NETWORK_TYPE_5G_AUTO):
            steps.fail()
            return {"status": "fail", "message": f"{label}设置失败"}
        steps.ok()
        steps.begin(f"{label}视频主叫辅测机")
        if not dial_and_check(dut_id, sim_slot, aux_number, 1):
            steps.fail()
            return {"status": "fail", "message": f"{label}视频主叫失败"}
        steps.ok()

    return {"status": "pass", "message": "双卡分别视频主叫辅测机通过"}
