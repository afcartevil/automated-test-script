# coding=utf-8
import pytest

from src.utils.adb.adb_utils import adb_shell


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002435")
def test_smoke_usd_thermal_architecture(device_serial):
    """
    thermal温升架构
    功能简介: 自研温升架构,应用场景分类
    测试步骤:
        1. adb shell dumpsys activity service com.transsion.usf.UsfMainService -thermal state
           返回值不为空
        2. adb shell dumpsys activity service com.transsion.usf.UsfMainService -thermal thermal_engine_config | grep "cpu=11"
           返回值不为空
    预期结果:
        1. 返回值不为空
        2. 返回值不为空
    """
    service = "com.transsion.usf.UsfMainService"

    # Step 1: check thermal state
    shell_command_1 = f"dumpsys activity service {service} -thermal state"
    result_1 = adb_shell(device_serial, shell_command_1, timeout=15, no_retry=True)
    output_1 = result_1["output"].strip()

    assert output_1, (
        f"thermal温升架构 校验失败(step1): expected non-empty thermal state output; "
        f"actual: {output_1}"
    )

    # Step 2: check thermal_engine_config for cpu=11
    shell_command_2 = (
        f"dumpsys activity service {service} -thermal thermal_engine_config | grep cpu=11"
    )
    result_2 = adb_shell(device_serial, shell_command_2, timeout=15, no_retry=True)
    output_2 = result_2["output"].strip()

    assert output_2, (
        f"thermal温升架构 校验失败(step2): expected non-empty output containing 'cpu=11' "
        f"in thermal_engine_config; actual: {output_2}"
    )
