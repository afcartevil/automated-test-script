from utils.tdd.apk.call import dial_and_check, reset_dial_sequence
from utils.tdd.device_sim import fail_result_if_camera_unavailable_for_video
from utils.tdd.device_sim import get_sim_by_slot, pick_aux_number, sim_phone_number
from utils.tdd.sim_setup import (
    NETWORK_TYPE_5G_AUTO,
    open_sim_only,
    setup_sim_preferred_network,
)


def _dial_and_check(caller_id: str, sim_slot, target_number: str, call_type: int) -> bool:
    return dial_and_check(caller_id, sim_slot, target_number, call_type)


def _restore_sim2(dut_id: str, sim2, sub_steps: str, step_update) -> tuple[str, bool]:
    sub_steps += "\n卡2重新打开"
    if callable(step_update):
        step_update(sub_steps)
    ok = open_sim_only(dut_id, sim2)
    sub_steps += "-成功" if ok else "-失败"
    if callable(step_update):
        step_update(sub_steps)
    return sub_steps, ok


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    device_info = device_info or context.get("device_info") or {}

    cam_fail = fail_result_if_camera_unavailable_for_video(device_info)
    if cam_fail:
        return cam_fail

    dut_list = (device_info or {}).get("DUT") or []
    if not dut_list:
        return {"status": "fail", "message": "未获取到测试机设备信息"}
    dut = dut_list[0]
    dut_id = (dut.get("device_id") or "").strip()
    if not dut_id:
        return {"status": "fail", "message": "测试机 device_id 为空"}

    dut_sim_cards = dut.get("sim_cards") or []
    sim1 = get_sim_by_slot(dut_sim_cards, 0)
    sim2 = get_sim_by_slot(dut_sim_cards, 1)
    sim1_number = sim_phone_number(sim1)
    sim2_number = sim_phone_number(sim2)
    if not sim1:
        return {"status": "fail", "message": "测试机未检测到卡1，无法执行"}
    if not sim1_number:
        return {"status": "fail", "message": "测试机卡1无号码，无法执行辅测机回拨"}

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
    sim2_disabled = False
    # 卡1切 5G 自动（不支持时回退 4G 自动）
    sub_steps += "\n卡1切5G自动或4G自动（不支持5g时）"
    if callable(step_update):
        step_update(sub_steps)
    if not setup_sim_preferred_network(
        dut_id, sim1, enable=True, network_type=NETWORK_TYPE_5G_AUTO
    ):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "卡1打开或首选网络设置失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    # 卡2关闭
    if sim2:
        sub_steps += "\n卡2关闭"
        if callable(step_update):
            step_update(sub_steps)
        if not setup_sim_preferred_network(dut_id, sim2, enable=False):
            sub_steps += "-失败"
            if callable(step_update):
                step_update(sub_steps)
            return {"status": "fail", "message": "关闭 SIM2 失败"}
        sub_steps += "-成功"
        if callable(step_update):
            step_update(sub_steps)
        sim2_disabled = True

    # 视频通话双向
    sub_steps += "\n测试机给辅测机拨打视频通话，检查是否接通"
    if callable(step_update):
        step_update(sub_steps)
    first_leg_ok = _dial_and_check(dut_id, 1, aux_target_number, call_type=1)
    if not first_leg_ok:
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        if sim2_disabled:
            sub_steps, _ = _restore_sim2(dut_id, sim2, sub_steps, step_update)
        return {"status": "fail", "message": "测试机主叫视频通话失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n辅测机回拨视频通话，检查是否接通"
    if callable(step_update):
        step_update(sub_steps)
    if not _dial_and_check(aux_id, aux_call_slot, sim1_number, call_type=1):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        if sim2_disabled:
            sub_steps, _ = _restore_sim2(dut_id, sim2, sub_steps, step_update)
        return {"status": "fail", "message": "辅测机回拨视频通话失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    reset_dial_sequence()
    # 语音视频切换通话双向
    sub_steps += "\n测试机给辅测机拨打语音视频切换通话，检查是否接通"
    if callable(step_update):
        step_update(sub_steps)
    first_leg_ok = _dial_and_check(dut_id, 1, aux_target_number, call_type=4)
    if not first_leg_ok:
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        if sim2_disabled:
            sub_steps, _ = _restore_sim2(dut_id, sim2, sub_steps, step_update)
        return {"status": "fail", "message": "测试机主叫语音视频切换通话失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n辅测机回拨语音视频切换通话，检查是否接通"
    if callable(step_update):
        step_update(sub_steps)
    if not _dial_and_check(aux_id, aux_call_slot, sim1_number, call_type=4):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        if sim2_disabled:
            sub_steps, _ = _restore_sim2(dut_id, sim2, sub_steps, step_update)
        return {"status": "fail", "message": "辅测机回拨语音视频切换通话失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    if sim2_disabled:
        sub_steps, restored = _restore_sim2(dut_id, sim2, sub_steps, step_update)
        if not restored:
            return {"status": "fail", "message": "重新打开 SIM2 失败"}

    return {"status": "pass", "message": "视频通话与语音视频切换双向拨打通过"}
