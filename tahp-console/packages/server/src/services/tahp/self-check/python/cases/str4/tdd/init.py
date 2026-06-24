"""str4 通信框架模块用例执行前初始化。"""

from utils.tdd.apk.init import set_default_apps_for_test_devices
from utils.device_init import init_devices_for_test


def run(device_info=None, **_kwargs):
    if device_info:
        init_devices_for_test(device_info)
    set_default_apps_for_test_devices(device_info)
