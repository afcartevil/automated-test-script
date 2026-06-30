# coding=utf-8
import pytest

from src.utils.adb.adb_utils import adb_shell, getprop
from src.conftests.device import get_device_build_brand


@pytest.mark.require_spd_feature_support("SF-202507-002422")
def test_smoke_usd_power_app_hiber(device_serial):
    """
    应用冻结
    功能简介: 对应用的后台行为管理
    测试步骤:
        1. adb shell getprop ro.tran.hiber.support -> 返回值为1
        2. adb shell "dumpsys activity service com.transsion.usf.UsfMainService -hiber dump | grep enable"
           返回值包含 enabled=true
    预期结果:
        1. 返回值为1
        2. 返回值包含 enabled=true
    """
    # 仅支持MTK和SPRD平台，其他平台跳过
    build_brand = get_device_build_brand(device_serial)
    if build_brand not in ["MTK", "SPRD"]:
        pytest.skip(f"当前平台 {build_brand} 不支持此功能，跳过")

    # Step 1: check hiber support property
    prop_value = getprop("ro.tran.hiber.support", device_serial).strip()
    assert prop_value == "1", (
        f"应用冻结 校验失败(step1): expected ro.tran.hiber.support=1; "
        f"actual: {prop_value}"
    )

    # Step 2: check hiber service dump for enabled=true
    shell_command = (
        "dumpsys activity service com.transsion.usf.UsfMainService "
        "-hiber dump | grep enable"
    )
    result = adb_shell(device_serial, shell_command, timeout=15, no_retry=True)
    actual_output = result["output"].strip()

    assert "enabled=true" in actual_output, (
        f"应用冻结 校验失败(step2): expected 'enabled=true' in hiber dump output; "
        f"actual: {actual_output}"
    )
