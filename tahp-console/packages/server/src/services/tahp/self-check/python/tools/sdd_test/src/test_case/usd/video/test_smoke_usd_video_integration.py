# coding=utf-8
import pytest

from src.utils.adb.adb_utils import getprop


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002478")
def test_smoke_usd_video_vee_support(device_serial):
    """
    画质增强
    测试步骤: adb shell getprop ro.tr_video.vee.support
    预期结果: 1为支持，0或空为不支持
    """
    actual = getprop("ro.tr_video.vee.support", device_serial)
    assert actual == "1", f"画质增强校验失败: expected 1; actual: {actual!r}"


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202508-000162")
def test_smoke_usd_video_smartmediaengine(device_serial):
    """
    视频省电
    测试步骤: adb shell getprop ro.tr_media.smartmediaengine.feature.support
    预期结果: true为支持，false或空为不支持
    """
    actual = getprop(
        "ro.tr_media.smartmediaengine.feature.support", device_serial
    )
    assert actual == "true", f"视频省电校验失败: expected true; actual: {actual!r}"
