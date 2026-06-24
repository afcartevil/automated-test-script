"""week 驱动模块用例执行前初始化。"""

from utils.device_init import init_devices_for_test


def run(device_info=None, **_kwargs):
    if device_info:
        init_devices_for_test(device_info)