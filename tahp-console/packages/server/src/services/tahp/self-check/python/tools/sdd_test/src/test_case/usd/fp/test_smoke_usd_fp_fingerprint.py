# coding=utf-8
import pytest

from src.utils.adb.adb_utils import adb_shell, getprop


@pytest.mark.require_build_brand("MTK")
def test_smoke_usd_fp_tran_keys(device_serial):
    """
    指纹输入设备
    测试步骤: getevent -lp
    """
    shell_command = "getevent -lp"
    expected_text = "tran-keys"

    result = adb_shell(device_serial, shell_command, no_retry=True)
    actual_output = result["output"]

    assert expected_text in actual_output, (
        f"指纹输入设备校验失败: expected contains: {expected_text}; actual: {actual_output}"
    )


@pytest.mark.require_build_brand("MTK")
def test_smoke_usd_fp_fingerprint_service(device_serial):
    """
    指纹服务检查
    测试步骤: ps -A | grep fingerprint
    """
    shell_command = "ps -A | grep fingerprint"
    expected_text = "fingerprint"

    result = adb_shell(device_serial, shell_command, no_retry=True)
    actual_output = result["output"]

    assert expected_text in actual_output, (
        f"指纹服务检查失败: expected contains: {expected_text}; actual: {actual_output}"
    )


@pytest.mark.require_build_brand("MTK")
def test_smoke_usd_fp_fingerprint_type(device_serial):
    """
    指纹类型
    测试步骤:
    1. getprop ro.tr_fingerprint.optical.feature.support
    2. getprop ro.tr_fingerprint.side.feature.support
    3. getprop ro.tr_fingerprint.local.hbm.support
    预期结果：当ro.tr_fingerprint.optical.feature.suppor为1，则ro.tr_fingerprint.local.hbm.support为1， ro.tr_fingerprint.side.feature.support不为1
            当ro.tr_fingerprint.optical.feature.suppor不为1，则ro.tr_fingerprint.local.hbm.support不为1，ro.tr_fingerprint.side.feature.support为1
    """
    optical_prop = "ro.tr_fingerprint.optical.feature.support"
    side_prop = "ro.tr_fingerprint.side.feature.support"
    local_hbm_prop = "ro.tr_fingerprint.local.hbm.support"

    optical_support = getprop(optical_prop, device_serial)
    side_support = getprop(side_prop, device_serial)
    local_hbm_support = getprop(local_hbm_prop, device_serial)

    if optical_support == "1":
        assert local_hbm_support == "1", (
            f"指纹类型校验失败: {optical_prop}=1 时预期 {local_hbm_prop}=1; "
            f"actual: {local_hbm_support}"
        )
        assert side_support != "1", (
            f"指纹类型校验失败: {optical_prop}=1 时预期 {side_prop} 不为 1; "
            f"actual: {side_support}"
        )
    else:
        assert local_hbm_support != "1", (
            f"指纹类型校验失败: {optical_prop} 不为 1 时预期 {local_hbm_prop} 不为 1; "
            f"actual: {local_hbm_support}"
        )
        assert side_support == "1", (
            f"指纹类型校验失败: {optical_prop} 不为 1 时预期 {side_prop}=1; "
            f"actual: {side_support}"
        )
