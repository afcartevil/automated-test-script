# coding=utf-8
import pytest

from src.utils.adb.adb_utils import getprop

_EXPECTED_TRUE = "true"


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002636")
def test_smoke_usd_motor_vibrate10_feature_support_sf2636(device_serial):
    """
    铃声无级振动强度调节
    适配条件: SPD是否支持 (SF-202507-002636)
    测试步骤: getprop ro.tr_vibrate.vibrate10.feature.support
    预期结果: 输出true
    """
    prop_key = "ro.tr_vibrate.vibrate10.feature.support"
    actual_value = (getprop(prop_key, device_serial) or "").strip().lower()

    assert actual_value == _EXPECTED_TRUE, (
        f"铃声无级振动强度调节宏控校验失败: expected: {_EXPECTED_TRUE}; actual: {actual_value}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002644")
def test_smoke_usd_motor_vibrate10_feature_support_sf2644(device_serial):
    """
    铃声无级振动强度调节
    适配条件: SPD是否支持 (SF-202507-002644)
    测试步骤: getprop ro.tr_vibrate.vibrate10.feature.support
    预期结果: 输出true
    """
    prop_key = "ro.tr_vibrate.vibrate10.feature.support"
    actual_value = (getprop(prop_key, device_serial) or "").strip().lower()

    assert actual_value == _EXPECTED_TRUE, (
        f"铃声无级振动强度调节宏控校验失败: expected: {_EXPECTED_TRUE}; actual: {actual_value}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002643")
def test_smoke_usd_motor_vibrate20_vibrate30_feature_support(device_serial):
    """
    铃声随振
    适配条件: SPD是否支持 (SF-202507-002643)
    测试步骤:
    1. getprop ro.tr_vibrate.vibrate20.feature.support
    2. getprop ro.tr_vibrate.vibrate30.feature.support
    预期结果: 输出true
    """
    prop_keys = (
        "ro.tr_vibrate.vibrate20.feature.support",
        "ro.tr_vibrate.vibrate30.feature.support",
    )
    vibrate20_value = (getprop(prop_keys[0], device_serial) or "").strip().lower()
    vibrate30_value = (getprop(prop_keys[1], device_serial) or "").strip().lower()
    prop_values = {prop_keys[0]: vibrate20_value, prop_keys[1]: vibrate30_value}

    assert vibrate20_value == _EXPECTED_TRUE and vibrate30_value == _EXPECTED_TRUE, (
        f"铃声随振宏控校验失败: expected all: {_EXPECTED_TRUE}; actual: {prop_values}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002642")
def test_smoke_usd_motor_realvib05_feature_support(device_serial):
    """
    真实触感动画
    适配条件: SPD是否支持 (SF-202507-002642)
    测试步骤: getprop ro.tr_vibrate.realvib05.feature.support
    预期结果: 输出true
    """
    prop_key = "ro.tr_vibrate.realvib05.feature.support"
    actual_value = (getprop(prop_key, device_serial) or "").strip().lower()

    assert actual_value == _EXPECTED_TRUE, (
        f"真实触感动画宏控校验失败: expected: {_EXPECTED_TRUE}; actual: {actual_value}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002635")
def test_smoke_usd_motor_vibrate30_z_feature_support(device_serial):
    """
    Z轴铃声随振
    适配条件: SPD是否支持 (SF-202507-002635)
    测试步骤: getprop ro.tr_vibrate.vibrate30_z.feature.support
    预期结果: 输出true
    """
    prop_key = "ro.tr_vibrate.vibrate30_z.feature.support"
    actual_value = (getprop(prop_key, device_serial) or "").strip().lower()

    assert actual_value == _EXPECTED_TRUE, (
        f"Z轴铃声随振宏控校验失败: expected: {_EXPECTED_TRUE}; actual: {actual_value}"
    )
