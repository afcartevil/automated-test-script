# coding=utf-8
import pytest

from src.utils.adb.adb_utils import adb_shell
from src.conftests.device import get_device_build_brand


@pytest.mark.require_spd_feature_support("SF-202507-002416")
def test_smoke_usd_power_sleep_standby(device_serial):
    """
    睡眠待机优化
    功能简介: 学习用户的作息时间,在用户睡眠期间周期性断开网络以节省功耗(即智能断网)
    测试步骤:
        Android 16:
        1. adb shell dumpsys activity service com.transsion.usf.UsfMainService -ainet state
           检查返回值包含 ImNetController SUPPORT = true , UiSwitch = true ,mIsOtaAllowPolicy = true
    预期结果: 返回值包含 ImNetController SUPPORT = true , UiSwitch = true ,mIsOtaAllowPolicy = true
    """
    # 仅支持MTK和SPRD平台，其他平台跳过
    build_brand = get_device_build_brand(device_serial)
    if build_brand not in ["MTK", "SPRD"]:
        pytest.skip(f"当前平台 {build_brand} 不支持此功能，跳过")

    shell_command = (
        "dumpsys activity service com.transsion.usf.UsfMainService -ainet state"
    )
    result = adb_shell(device_serial, shell_command, timeout=15, no_retry=True)
    actual_output = result["output"].strip()

    assert "ImNetController SUPPORT = true" in actual_output, (
        f"睡眠待机优化 校验失败: "
        f"expected 'ImNetController SUPPORT = true' in output; actual: {actual_output}"
    )
    assert "UiSwitch = true" in actual_output, (
        f"睡眠待机优化 校验失败: "
        f"expected 'UiSwitch = true' in output; actual: {actual_output}"
    )
    assert "mIsOtaAllowPolicy = true" in actual_output, (
        f"睡眠待机优化 校验失败: "
        f"expected 'mIsOtaAllowPolicy = true' in output; actual: {actual_output}"
    )
