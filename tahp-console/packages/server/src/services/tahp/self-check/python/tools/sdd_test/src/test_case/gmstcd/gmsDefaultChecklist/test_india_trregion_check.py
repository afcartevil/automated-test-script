# -*- coding: utf-8 -*-
import pytest
import logging

from data.res_list import CARRIAR_MARKETS
from src.utils.adb.adb_utils import (
    getprop
)
from src.conftests.device import get_device_market


@pytest.mark.require_android_version_min(15)
@pytest.mark.require_go_device()
def test_dse_support_check(device_serial):

    mDevice_market = get_device_market(device_serial)
    logging.info(f"mDevice_market : {mDevice_market} ")

    if mDevice_market != "IN" \
            and mDevice_market != "EU":
        pytest.skip("非 IN/EU 市场, 跳过测试")

    ro_deferred_setup_low_ram_filter_value = getprop('setupwizard.feature.deferred_setup_low_ram_filter', sn=device_serial)
    logging.info(f"ro_deferred_setup_low_ram_filter_value = {ro_deferred_setup_low_ram_filter_value}")

    if "false" != ro_deferred_setup_low_ram_filter_value:
        reason = "setupwizard.feature.deferred_setup_low_ram_filter set error for IN/EU market!"
        pytest.fail(reason)

