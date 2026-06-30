# coding=utf-8
import pytest

from src.utils.adb.adb_utils import adb_shell
from src.conftests.device import get_device_build_brand


@pytest.mark.require_spd_feature_support("SF-202507-002413")
def test_smoke_usd_power_video_call_save(device_serial):
    """
    视频畅聊
    功能简介: 降低camera帧率以节省功耗
    测试步骤:
        Android 16:
        1. adb shell dumpsys activity service com.transsion.usf.UsfMainService
           -videocallsave -package com.google.android.apps.meetings
           -activity com.google.android.libraries.communications.conference.ui.greenroom.GreenroomActivity
           查看输出是否有相关fps range信息输出
    预期结果: 返回值不为空
    """
    # 仅支持MTK和SPRD平台，其他平台跳过
    build_brand = get_device_build_brand(device_serial)
    if build_brand not in ["MTK", "SPRD"]:
        pytest.skip(f"当前平台 {build_brand} 不支持此功能，跳过")

    package = "com.google.android.apps.meetings"
    activity = "com.google.android.libraries.communications.conference.ui.greenroom.GreenroomActivity"

    shell_command = (
        f"dumpsys activity service com.transsion.usf.UsfMainService "
        f"-videocallsave -package {package} -activity {activity}"
    )
    result = adb_shell(device_serial, shell_command, timeout=10, no_retry=True)
    output = result["output"].strip()
    assert output, (
        f"视频畅聊 校验失败: expected non-empty output with fps range info; "
        f"actual: {output}"
    )
