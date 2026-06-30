# coding=utf-8
import logging
import pytest
from src.utils.adb.adb_utils import getprop
from data.res_list import AndroidVersion
from src.utils.adb.adb_utils import get_device_ram_size


# Griffin 4.0
@pytest.mark.require_packages(["com.transsion.trancare"])
@pytest.mark.require_android_version_min(AndroidVersion.V)
def test_griffin_4_0(device_serial):
    assert "1" == getprop(
        "sys.pm_buriedpoint.support", device_serial
    ), "griffin 4.0 feature校验失败"


# Griffin 4.1
@pytest.mark.require_packages(["com.transsion.trancare"])
@pytest.mark.require_android_version_min(AndroidVersion.V)
def test_griffin_4_1(device_serial, phone_info):
    # 获取Android版本
    android_version = int(phone_info.get("android_version", 0))

    if android_version >= AndroidVersion.W:
        pass
    # V需要满足芯片平台大于G99和RAM≥8GB
    elif android_version == AndroidVersion.V:
        from src.conftests.device import get_soc_model_code
        from src.conftests.marker_check import SOC_MODEL_PRIORITY

        soc_model_code = get_soc_model_code(device_serial)
        logging.info(f"当前芯片平台: {soc_model_code}")
        ram_size = get_device_ram_size(device_serial)

        if soc_model_code not in SOC_MODEL_PRIORITY:
            pytest.skip(f"未知芯片型号: {soc_model_code}")

        current_priority = SOC_MODEL_PRIORITY.get(soc_model_code, 0)
        logging.info(f"当前芯片平台: {soc_model_code}，优先级: {current_priority}")
        g99_priority = SOC_MODEL_PRIORITY.get("G99", 0)

        if current_priority < g99_priority:
            pytest.skip(f"V版本需要芯片平台大于等于G99，当前芯片平台: {soc_model_code}")

        if ram_size < 8:
            pytest.skip(f"V版本需要RAM至少8GB，当前RAM: {ram_size}GB")

    assert "1" == getprop(
        "sys.apm.limit_block_mode", device_serial
    ), "griffin 4.1 feature校验失败"
