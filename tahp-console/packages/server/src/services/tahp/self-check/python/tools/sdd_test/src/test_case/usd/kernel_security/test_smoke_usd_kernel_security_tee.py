# coding=utf-8
import pytest

from src.utils.adb.adb_utils import getprop


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002292")
def test_smoke_usd_kernel_security_vendor_tee_googlekey_status(device_serial):
    """
    AttestationKey写入&检查
    适配条件: SPD是否支持 (SF-202507-002292)
    测试步骤: adb shell -> getprop | grep vendor.tee.googlekey.status
    预期结果: [vendor.tee.googlekey.status]: [ok]
    """
    prop_key = "vendor.tee.googlekey.status"
    expected_value = "ok"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"AttestationKey写入&检查校验失败: expected: {expected_value!r}; "
        f"actual: {actual_value!r}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002780")
def test_smoke_usd_kernel_security_ta_crashdebug(device_serial):
    """
    TEE/TA异常埋点
    适配条件: SPD是否支持 (SF-202507-002780)
    测试步骤: adb shell getprop | grep -i ta.crashdebug.support
    预期结果: [ro.vendor.tran.ta.crashdebug.support]: [1]
    """
    prop_key = "ro.vendor.tran.ta.crashdebug.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"TEE/TA异常埋点校验失败: expected: {expected_value!r}; actual: {actual_value!r}"
    )
