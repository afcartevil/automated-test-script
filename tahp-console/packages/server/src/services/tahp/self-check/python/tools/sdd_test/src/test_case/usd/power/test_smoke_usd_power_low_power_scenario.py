# coding=utf-8
import pytest

from src.utils.adb.adb_utils import adb_shell


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002415")
def test_smoke_usd_power_low_power_scenario(device_serial):
    """
    低电量使用场景
    功能简介: 低电量使用场景下的功耗优化方案
    测试步骤:
        1. adb shell "dumpsys activity service com.transsion.usf.UsfMainService -lowpower state"
    预期结果: 返回值包含LowPower Manager State
    """
    shell_command = (
        "dumpsys activity service com.transsion.usf.UsfMainService -lowpower state"
    )
    result = adb_shell(device_serial, shell_command, timeout=15, no_retry=True)
    actual_output = result["output"].strip()

    assert "LowPower Manager State" in actual_output, (
        f"低电量使用场景 校验失败: expected 'LowPower Manager State' in output; "
        f"actual: {actual_output}"
    )
