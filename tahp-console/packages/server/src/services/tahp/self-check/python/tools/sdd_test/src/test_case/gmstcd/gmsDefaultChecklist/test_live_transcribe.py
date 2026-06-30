# -*- coding: utf-8 -*-
import logging

import pytest

from src.utils.adb.adb_utils import get_apkpath_by_package, getprop


LIVE_TRANSCRIBE_PACKAGE = "com.google.audio.hearing.visualization.accessibility.scribe"


def _get_market_product_names(device_serial, phone_info):
    candidates = [
        phone_info.get("market_product_name"),
        phone_info.get("ro_transsion_device_name"),
        phone_info.get("ro_product_model"),
        getprop("ro.product.marketname", device_serial),
        getprop("ro.product.tran.device.name", device_serial),
        getprop("persist.sys.tran.device.name", device_serial),
        getprop("ro.product.model", device_serial),
    ]
    return [str(name).strip() for name in candidates if str(name).strip()]


def _is_note_product(market_product_names):
    for name in market_product_names:
        normalized_name = name.upper()
        if normalized_name.startswith("NOTE") or " NOTE" in normalized_name:
            return True
    return False


@pytest.mark.require_android_version_min(16)
def test_live_transcribe_check(device_serial, phone_info):
    market_product_names = _get_market_product_names(device_serial, phone_info)
    logging.info(f"market_product_names: {market_product_names}")

    if not _is_note_product(market_product_names):
        pytest.skip(
            f"Non-NOTE product, skip Live Transcribe check: {market_product_names}"
        )

    live_transcribe_path = get_apkpath_by_package(device_serial, LIVE_TRANSCRIBE_PACKAGE)
    logging.info(f"Live Transcribe package path: {live_transcribe_path}")

    if not live_transcribe_path:
        pytest.fail("NOTE product should preload Live Transcribe!")
