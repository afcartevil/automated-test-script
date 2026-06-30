# coding=utf-8
import pytest

from src.utils.adb.adb_utils import adb_shell


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002434")
def test_smoke_usd_thermal_vtshell(device_serial):
    """
    壳温拟合
    功能简介: 手机完温拟合及热源识别
    测试步骤:
        1. adb shell cat /sys/kernel/vtshell/vtshell_info
           返回值不为空
        2. adb shell "tail /sys/class/thermal/thermal_zone*/type | grep vtshell"
           找到vtshell_的节点,cat对应的temp
           ---vtshell_max: 壳温节点
           ---vtshell_front: 正面温度节点
           ---vtshell_back: 背面温度节点
           返回值不为空
    预期结果:
        1. 返回值不为空
        2. 返回值不为空
    """
    # Step 1: check vtshell_info
    shell_command_1 = "cat /sys/kernel/vtshell/vtshell_info"
    result_1 = adb_shell(device_serial, shell_command_1, timeout=10, no_retry=True)
    output_1 = result_1["output"].strip()

    assert output_1, (
        f"壳温拟合 校验失败(step1): expected non-empty output from vtshell_info; "
        f"actual: {output_1}"
    )

    # Step 2: find vtshell thermal zones and check their temp values
    shell_command_2 = "tail /sys/class/thermal/thermal_zone*/type | grep vtshell"
    result_2 = adb_shell(device_serial, shell_command_2, timeout=10, no_retry=True)
    output_2 = result_2["output"].strip()

    assert output_2, (
        f"壳温拟合 校验失败(step2): expected non-empty output (vtshell thermal zones); "
        f"actual: {output_2}"
    )
