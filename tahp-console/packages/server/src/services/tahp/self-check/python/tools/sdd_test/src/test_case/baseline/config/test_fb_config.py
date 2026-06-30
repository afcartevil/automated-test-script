# coding: utf-8

import pytest
import logging

from data.res_list import CARRIAR_MARKETS, FacebookPartnerId
from src.utils.adb.adb_utils import getprop, is_google_one_product


def test_fb_config(device_serial):
    """
    测试设备fb配置是否正确

    Args:
        device_serial: 设备序列号
    """
    if is_google_one_product(device_serial):
        pytest.skip("Google One产品, 跳过测试")

    if getprop("ro.tran.sw.market", device_serial) == "tocc":
        pytest.skip("TOCC产品, 跳过测试")

    version_phone = getprop("ro.build.display.id", device_serial)

    prop_value = getprop("ro.facebook.partnerid", device_serial)
    logging.info(f"ro.facebook.partnerid: {prop_value}")
    for market in CARRIAR_MARKETS:
        if market in version_phone:
            assert (
                prop_value == FacebookPartnerId.CARRIAR.value
            ), f"ro.facebook.partnerid: {prop_value} 不等于 {FacebookPartnerId.CARRIAR.value}"
        else:
            assert (
                prop_value == FacebookPartnerId.COMMON.value
            ), f"ro.facebook.partnerid: {prop_value} 不等于 {FacebookPartnerId.COMMON.value}"
