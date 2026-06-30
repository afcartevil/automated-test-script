# coding=utf-8
import pytest

from src.utils.adb.adb_utils import adb_shell
from src.conftests.device import get_device_build_brand


@pytest.mark.require_spd_feature_support("SF-202507-002436")
def test_smoke_usd_thermal_light(device_serial):
    """
    高温背光
    功能简介: 高温场景下的背光配置策略
    测试步骤:
        1. adb shell dumpsys activity thermal_light state
           返回值不为空
        2. adb shell "logcat -d | grep thermallight"
           切换应用查看log打印
           返回值不为空
    预期结果:
        1. 返回值不为空
        2. 返回值不为空
    """
    # 仅支持MTK和SPRD平台，其他平台跳过
    build_brand = get_device_build_brand(device_serial)
    if build_brand not in ["MTK", "SPRD"]:
        pytest.skip(f"当前平台 {build_brand} 不支持此功能，跳过")

    # Step 1: check thermal_light state
    shell_command_1 = "dumpsys activity thermal_light state"
    result_1 = adb_shell(device_serial, shell_command_1, timeout=15, no_retry=True)
    output_1 = result_1["output"].strip()

    assert output_1, (
        f"高温背光 校验失败(step1): expected non-empty thermal_light state output; "
        f"actual: {output_1}"
    )

    # Step 2: check logcat for thermallight
    # 先打开 Settings 应用以触发 log 打印
    shell_command_open_settings = (
        "am start -a android.intent.action.MAIN -n "
        "com.android.settings/.Settings"
    )
    adb_shell(device_serial, shell_command_open_settings, timeout=10, no_retry=True)
    import time
    time.sleep(2)

    shell_command_2 = "logcat -d | grep -i thermallight"
    result_2 = adb_shell(device_serial, shell_command_2, timeout=10, no_retry=True)
    output_2 = result_2["output"].strip()

    assert output_2, (
        f"高温背光 校验失败(step2): expected non-empty logcat output containing 'thermallight'; "
        f"actual: {output_2}"
    )
