# -*- coding: utf-8 -*-
import re

import pytest

from src.utils.adb.adb_utils import get_feature, getprop


def _parse_mtk_platform_value(platform):
    if not platform:
        return None
    match = re.search(r"MT(\d+)", platform.upper())
    return int(match.group(1)) if match else None

@pytest.mark.require_android_version_min(15)
@pytest.mark.require_non_cuttlefish
def test_chre_support_check(device_serial):
    mtk_platform = getprop("ro.vendor.mediatek.platform", device_serial) or ""
    platform_value = _parse_mtk_platform_value(mtk_platform)
    if platform_value is None:
        pytest.skip("Non-MTK platform, skip CHRE threshold check")

    should_support_chre = platform_value > 6991
    has_context_hub_feature = bool(
        get_feature(device_serial, "android.hardware.context_hub")
    )

    if should_support_chre and not has_context_hub_feature:
        pytest.fail(
            f"Platform {mtk_platform} should support CHRE, "
            "but android.hardware.context_hub is missing."
        )

    if (not should_support_chre) and has_context_hub_feature:
        pytest.fail(
            f"Platform {mtk_platform} should not support CHRE, "
            "but android.hardware.context_hub exists."
        )
