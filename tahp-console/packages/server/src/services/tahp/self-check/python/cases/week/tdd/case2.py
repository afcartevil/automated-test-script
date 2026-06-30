from utils.tdd.apk.call import dial_and_check, reset_dial_sequence
from utils.tdd.device_sim import (
    dut_dial_slot,
    fail_result_if_camera_unavailable_for_video,
    get_sim_by_slot,
    pick_aux_number,
    resolve_dut_active,
    sim_phone_number,
)
from utils.tdd.sim_setup import (
    NETWORK_TYPE_5G_AUTO,
    setup_sim_preferred_network,
)


def _dial_and_check(caller_id: str, sim_slot, target_number: str, call_type: int) -> bool:
    return dial_and_check(caller_id, sim_slot, target_number, call_type)


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    device_info = device_info or context.get("device_info") or {}

    cam_fail = fail_result_if_camera_unavailable_for_video(device_info)
    if cam_fail:
        return cam_fail

    _, dut_id, active_sim, slot_index, dut_number, sim_err = resolve_dut_active(device_info)
    if sim_err:
        return {"status": "fail", "message": sim_err}
    dial_slot = dut_dial_slot(slot_index)

    aux_list = device_info.get("Auxiliary") or []
    aux = aux_list[0] if aux_list else {}
    aux_id = (aux.get("device_id") or "").strip()
    if not aux_id:
        return {"status": "fail", "message": "无辅测机，无法测试"}
    aux_sim_cards = aux.get("sim_cards") or []
    aux_sim1 = get_sim_by_slot(aux_sim_cards, 0)
    aux_sim2 = get_sim_by_slot(aux_sim_cards, 1)
    if not aux_sim1 and not aux_sim2:
        return {"status": "fail", "message": "辅测机未插卡，无法测试"}
    aux_target_number = pick_aux_number(
        sim_phone_number(aux_sim1), sim_phone_number(aux_sim2)
    )
    if not aux_target_number:
        return {"status": "fail", "message": "辅测机无可用号码，无法测试"}
    aux_call_slot = 1 if aux_sim1 else 2

    sub_steps = ""
    sub_steps += "\n活动卡切5G自动或4G自动（不支持5g时）"
    if callable(step_update):
        step_update(sub_steps)
    if not setup_sim_preferred_network(
        dut_id, active_sim, enable=True, network_type=NETWORK_TYPE_5G_AUTO
    ):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "活动卡打开或首选网络设置失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n测试机给辅测机拨打视频通话，检查是否接通"
    if callable(step_update):
        step_update(sub_steps)
    first_leg_ok = _dial_and_check(dut_id, dial_slot, aux_target_number, call_type=1)
    if not first_leg_ok:
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "测试机主叫视频通话失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n辅测机回拨视频通话，检查是否接通"
    if callable(step_update):
        step_update(sub_steps)
    if not _dial_and_check(aux_id, aux_call_slot, dut_number, call_type=1):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "辅测机回拨视频通话失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    reset_dial_sequence()
    sub_steps += "\n测试机给辅测机拨打语音视频切换通话，检查是否接通"
    if callable(step_update):
        step_update(sub_steps)
    first_leg_ok = _dial_and_check(dut_id, dial_slot, aux_target_number, call_type=4)
    if not first_leg_ok:
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "测试机主叫语音视频切换通话失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n辅测机回拨语音视频切换通话，检查是否接通"
    if callable(step_update):
        step_update(sub_steps)
    if not _dial_and_check(aux_id, aux_call_slot, dut_number, call_type=4):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "辅测机回拨语音视频切换通话失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    return {"status": "pass", "message": "视频通话与语音视频切换双向拨打通过"}
