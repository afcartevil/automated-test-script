from utils.tdd.apk.call import dial_and_check, reset_dial_sequence
from utils.tdd.device_sim import get_sim_by_slot, sim_phone_number, pick_aux_number
from utils.tdd.sim_setup import (
    NETWORK_TYPE_5G_AUTO,
    enter_sim_sub_page,
    open_sim_only,
    setup_sim_preferred_network,
)
from utils.tdd.ui_first_network import set_preferred_network


def _get_dut_device_id(device_info):
    dut_list = (device_info or {}).get("DUT") or []
    if not dut_list:
        return None, "未获取到测试机设备信息"
    dut_id = dut_list[0].get("device_id", "")
    if not dut_id:
        return None, "测试机 device_id 为空"
    return dut_id, ""


def _dial_and_check(caller_id: str, sim_slot, target_number: str) -> bool:
    return dial_and_check(caller_id, sim_slot, target_number, 2)


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    device_info = device_info or context.get("device_info") or {}

    dut_id, error = _get_dut_device_id(device_info)
    if not dut_id:
        if callable(step_update):
            step_update(error)
        return {"status": "fail", "message": error}

    dut = (device_info.get("DUT") or [{}])[0]
    dut_sim_cards = dut.get("sim_cards") or []
    sim1 = get_sim_by_slot(dut_sim_cards, 0)
    sim2 = get_sim_by_slot(dut_sim_cards, 1)
    sim1_number = sim_phone_number(sim1)
    sim2_number = sim_phone_number(sim2)

    aux_list = device_info.get("Auxiliary") or []
    aux = aux_list[0] if aux_list else {}
    aux_id = (aux.get("device_id") or "").strip()
    aux_sim_cards = aux.get("sim_cards") or []
    aux_sim1 = get_sim_by_slot(aux_sim_cards, 0)
    aux_sim2 = get_sim_by_slot(aux_sim_cards, 1)
    aux_sim1_number = sim_phone_number(aux_sim1)
    aux_sim2_number = sim_phone_number(aux_sim2)
    aux_target_number = pick_aux_number(aux_sim1_number, aux_sim2_number)
    aux_call_slot = 1 if aux_sim1 else (2 if aux_sim2 else None)
    if not aux_id:
        msg = "无辅测机，无法测试"
        return {"status": "fail", "message": msg}
    if not aux_sim1 and not aux_sim2:
        msg = "辅测机未插卡，无法测试"
        return {"status": "fail", "message": msg}
    if not aux_target_number:
        msg = "辅测机无可用号码，无法测试"
        return {"status": "fail", "message": msg}
    if not sim1_number:
        msg = "测试机卡1无可用号码，无法执行辅测机回拨"
        return {"status": "fail", "message": msg}
    if not sim1 and not sim2:
        msg = "无 SIM 卡，无法设置首选网络"
        return {"status": "fail", "message": msg}

    sub_steps = ""
    dial_fail_messages = []
    network_pass = {
        "5g_or_4g_auto": False,
        "4g_auto": False,
        "23g_auto": False,
        "3g_only": False,
        "2g_only": False,
    }
    if sim1:
        sub_steps += "\n卡1设置首选网络模式（5G自动或不支持5g项目4g自动）"
        if callable(step_update):
            step_update(sub_steps)

        if not setup_sim_preferred_network(
            dut_id, sim1, enable=True, network_type=NETWORK_TYPE_5G_AUTO
        ):
            msg = "卡1打开或首选网络设置失败"
            sub_steps += "-失败"
            if callable(step_update):
                step_update(sub_steps)
            return {"status": "fail", "message": msg}

        sub_steps += "-成功"
        if callable(step_update):
            step_update(sub_steps)

        sub_steps += "\n卡2关闭"
        if sim2:
            if callable(step_update):
                step_update(sub_steps)
            if not setup_sim_preferred_network(dut_id, sim2, enable=False):
                msg = "关闭 SIM2 失败"
                sub_steps += "-失败"
                if callable(step_update):
                    step_update(sub_steps)
                return {"status": "fail", "message": msg}
            sub_steps += "-成功"
            if callable(step_update):
                step_update(sub_steps)

        sub_steps += "\n测试机给辅测机打电话，检查是否接通"
        if callable(step_update):
            step_update(sub_steps)
        first_leg_ok = _dial_and_check(dut_id, 1, aux_target_number)
        if not first_leg_ok:
            msg = "拨号未接通（网络: 5G自动或不支持5g项目4g自动）"
            sub_steps += "-失败"
            if callable(step_update):
                step_update(sub_steps)
            dial_fail_messages.append(msg)
        else:
            sub_steps += "-成功"
            if callable(step_update):
                step_update(sub_steps)
            sub_steps += "\n辅测机给测试机卡1拨打电话，检查是否接通"
            if callable(step_update):
                step_update(sub_steps)
            if not _dial_and_check(aux_id, aux_call_slot, sim1_number):
                msg = "辅测机回拨未接通（网络: 5G自动或不支持5g项目4g自动）"
                sub_steps += "-失败"
                if callable(step_update):
                    step_update(sub_steps)
                dial_fail_messages.append(msg)
            else:
                sub_steps += "-成功"
                if callable(step_update):
                    step_update(sub_steps)
                network_pass["5g_or_4g_auto"] = True

        network_steps = [
            (4, "2G/3G/4G 自动", "4g_auto"),
            (3, "2G/3G 自动", "23g_auto"),
            (2, "仅3G", "3g_only"),
            (1, "仅2G", "2g_only"),
        ]
        for network_type, label, key in network_steps:
            reset_dial_sequence()
            sub_steps += f"\n测试机卡1网络切到{label}"
            if callable(step_update):
                step_update(sub_steps)
            if not enter_sim_sub_page(dut_id, sim1):
                msg = f"进入 SIM1 子界面失败（{label}）"
                sub_steps += "-失败"
                if callable(step_update):
                    step_update(sub_steps)
                return {"status": "fail", "message": msg}
            if not set_preferred_network(dut_id, network_type):
                msg = f"切换首选网络失败（{label}）"
                sub_steps += "-失败"
                if callable(step_update):
                    step_update(sub_steps)
                return {"status": "fail", "message": msg}
            sub_steps += "-成功"
            if callable(step_update):
                step_update(sub_steps)

            sub_steps += "\n测试机给辅测机打电话，检查是否接通"
            if callable(step_update):
                step_update(sub_steps)
            first_leg_ok = _dial_and_check(dut_id, 1, aux_target_number)
            if not first_leg_ok:
                msg = f"拨号未接通（网络: {label}）"
                sub_steps += "-失败"
                if callable(step_update):
                    step_update(sub_steps)
                dial_fail_messages.append(msg)
            else:
                sub_steps += "-成功"
                if callable(step_update):
                    step_update(sub_steps)
                sub_steps += "\n辅测机给测试机卡1拨打电话，检查是否接通"
                if callable(step_update):
                    step_update(sub_steps)
                if not _dial_and_check(aux_id, aux_call_slot, sim1_number):
                    msg = f"辅测机回拨未接通（网络: {label}）"
                    sub_steps += "-失败"
                    if callable(step_update):
                        step_update(sub_steps)
                    dial_fail_messages.append(msg)
                else:
                    sub_steps += "-成功"
                    if callable(step_update):
                        step_update(sub_steps)
                    network_pass[key] = True

        if sim2:
            sub_steps += "\n卡2重新打开"
            if callable(step_update):
                step_update(sub_steps)
            if not open_sim_only(dut_id, sim2):
                msg = "重新打开 SIM2 失败"
                sub_steps += "-失败"
                if callable(step_update):
                    step_update(sub_steps)
                return {"status": "fail", "message": msg}
            sub_steps += "-成功"
            if callable(step_update):
                step_update(sub_steps)


    if (
        network_pass["5g_or_4g_auto"]
        and network_pass["4g_auto"]
        and not network_pass["23g_auto"]
        and not network_pass["3g_only"]
        and not network_pass["2g_only"]
    ):
        return {"status": "部分pass", "message": "2、3g无法搜到网"}

    if dial_fail_messages:
        return {"status": "fail", "message": "；".join(dial_fail_messages)}
    return {"status": "pass", "message": "已设置首选网络为 5G 自动或 2G/3G/4G 自动"}
