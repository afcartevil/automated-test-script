# -*- coding: utf-8 -*-
import logging

import pytest

from src.utils.adb.adb_utils import getprop

@pytest.mark.require_android_version_min(15)
def test_RkpOnlyPropertyTee(device_serial):
    """
    ID: TOS1610-43437
    DESCRIPTION: [GTS]GtsGoogleAttestationHostTestCases---com.google.android.gts.security.AttestationRootHostTest#testRkpOnlyPropertyTee
    """
    first_api_level = int(getprop("ro.product.first_api_level", sn=device_serial) or 0)
    logging.info(f"ro.product.first_api_level={first_api_level}")

    if first_api_level <= 35:
        pytest.skip("首发 API level <= 35，跳过 RKP only 检查")

    rkp_prop = getprop("remote_provisioning.tee.rkp_only", sn=device_serial)
    logging.info(f"remote_provisioning.tee.rkp_only={rkp_prop}")

    if not rkp_prop:
        pytest.fail(
            "Devices launched on Android 16 and newer must be RKP only. "
            "Set the remote_provisioning.tee.rkp_only property to true."
        )
