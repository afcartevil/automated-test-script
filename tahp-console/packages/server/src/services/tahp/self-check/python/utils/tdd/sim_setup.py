"""SIM 详情页：启用卡、首选网络、VoLTE 等组合设置。"""

import time

from utils.tdd.device_sim import enter_sim_sub_settings_by_sim
from utils.tdd.ui_automatic import set_mobile_data_enable
from utils.tdd.ui_first_network import set_preferred_network
from utils.tdd.ui_turn_onoff_sim import set_sim_enable
from utils.tdd.ui_volte_button import set_volte_enable

PAGE_SETTLE_SECONDS = 1.0
SIM_OFF_SETTLE_SECONDS = 1.0
DATA_SETTLE_SECONDS = 2.0
CALL_CALLBACK_DELAY_SECONDS = 2.0

NETWORK_TYPE_5G_AUTO = 5
NETWORK_TYPE_LTE_AUTO = 4


def enter_sim_sub_page(device_id: str, sim) -> bool:
    """进入指定 SIM 子界面并等待页面稳定。"""
    if not enter_sim_sub_settings_by_sim(device_id, sim):
        return False
    if PAGE_SETTLE_SECONDS > 0:
        time.sleep(PAGE_SETTLE_SECONDS)
    return True


def setup_sim_preferred_network(
    device_id: str,
    sim,
    *,
    enable: bool,
    network_type: int = NETWORK_TYPE_5G_AUTO,
) -> bool:
    if not enter_sim_sub_settings_by_sim(device_id, sim):
        return False
    if PAGE_SETTLE_SECONDS > 0:
        time.sleep(PAGE_SETTLE_SECONDS)
    if not set_sim_enable(device_id, enable):
        return False
    if not enable:
        if SIM_OFF_SETTLE_SECONDS > 0:
            time.sleep(SIM_OFF_SETTLE_SECONDS)
        return True
    return set_preferred_network(device_id, network_type)


def open_sim_only(device_id: str, sim) -> bool:
    if not enter_sim_sub_settings_by_sim(device_id, sim):
        return False
    if PAGE_SETTLE_SECONDS > 0:
        time.sleep(PAGE_SETTLE_SECONDS)
    if not set_sim_enable(device_id, True):
        return False
    if PAGE_SETTLE_SECONDS > 0:
        time.sleep(PAGE_SETTLE_SECONDS)
    return True


def setup_sim_volte_network(
    device_id: str,
    sim,
    *,
    volte: bool = True,
    network_type: int = NETWORK_TYPE_5G_AUTO,
) -> bool:
    if not enter_sim_sub_settings_by_sim(device_id, sim):
        return False
    if PAGE_SETTLE_SECONDS > 0:
        time.sleep(PAGE_SETTLE_SECONDS)
    if not set_sim_enable(device_id, True):
        return False
    if PAGE_SETTLE_SECONDS > 0:
        time.sleep(PAGE_SETTLE_SECONDS)
    if not set_volte_enable(device_id, volte):
        return False
    return set_preferred_network(device_id, network_type)


def enable_mobile_data(device_id: str) -> bool:
    if not set_mobile_data_enable(device_id, True):
        return False
    if DATA_SETTLE_SECONDS > 0:
        time.sleep(DATA_SETTLE_SECONDS)
    return True
