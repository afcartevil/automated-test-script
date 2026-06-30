# -*- coding: utf-8 -*-
import pytest
import logging

from data.res_list import CARRIAR_MARKETS
from src.utils.adb.adb_utils import (
    getprop,
    get_cmd_overlay_lookup,
)
from src.conftests.device import get_device_market


@pytest.mark.require_android_version_min(15)
@pytest.mark.require_go_device()
def test_carrier_check(device_serial):

    mDevice_market = get_device_market(device_serial)
    logging.info(f"mDevice_market : {mDevice_market} ")

    if mDevice_market != "COCL":
        pytest.skip("非 COCL 市场, 跳过测试")
    

    mDefaultAssistant = get_cmd_overlay_lookup(device_serial,"string","config_defaultAssistant")
    logging.info("COCL mDefaultAssistant=" + mDefaultAssistant)

    if "com.google.android.googlequicksearchbox" not in mDefaultAssistant:
        reason = "Default Assistant should be com.google.android.googlequicksearchbox for COCL"
        pytest.fail(reason)
