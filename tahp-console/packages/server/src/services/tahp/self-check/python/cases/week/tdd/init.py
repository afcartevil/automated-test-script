"""week 通信框架模块用例执行前初始化。"""

from utils.tdd.apk.init import set_default_apps_for_test_devices
from utils.device_init import init_devices_for_test
from utils.tdd.sim_setup import ensure_dut_single_sim_mode


def run(device_info=None, **_kwargs):
    if device_info:
        init_devices_for_test(device_info)
        for dut in device_info.get("DUT", []):
            device_id = (dut.get("device_id") or "").strip()
            if not device_id:
                continue
            sim_cards = dut.get("sim_cards") or []
            if not ensure_dut_single_sim_mode(device_id, sim_cards):
                print(f"[init] {device_id} 单卡模式初始化失败")
    set_default_apps_for_test_devices(device_info)
