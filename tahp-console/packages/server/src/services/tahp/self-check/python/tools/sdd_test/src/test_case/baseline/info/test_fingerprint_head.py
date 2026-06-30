import pytest
import logging
from src.utils.adb.adb_utils import getprop


def test_fingerprint_head(device_serial, phone_info):
    fingerprint = phone_info["fingerprint"]
    # [TECNO/CM5-OP/TECNO-CM5:16/BP2A.250605.031.A3/010010:user/release-keys]
    combo = f"{phone_info['ro_product_brand']}/{phone_info['product_name']}/{phone_info['ro_product_device']}:{phone_info['android_version']}"
    logging.info(f"fingerprint: {fingerprint}")
    logging.info(f"combo: {combo}")
    assert (
        fingerprint.startswith(combo) if fingerprint else 1 == 0
    ), " fingerprint 配置错误 "
