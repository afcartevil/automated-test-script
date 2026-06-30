# coding=utf-8
import logging
import pytest
from src.utils.adb.adb_utils import getprop
from data.res_list import AndroidVersion
from src.conftests.device import (
    get_device_build_brand,
    get_soc_model_code,
)
from src.conftests.marker_check import SOC_MODEL_PRIORITY


# dex2oat绑小核方案
@pytest.mark.require_soc_model_min("G99")
def test_high_performance_feature_g99_plus(device_serial, phone_info):
    if int(phone_info["android_version"]) >= AndroidVersion.W:
        pytest.skip(f"W版本无需宏控检测dex2oat绑小核方案")
    assert "4" == getprop(
        "persist.sys.dex2oat.threads", device_serial
    ), "dex2oat绑小核方案检测失败"


# 高性能模式
@pytest.mark.require_soc_model_min("D8200")
@pytest.mark.require_kernel_version_min("5.10")
def test_high_performance_feature(device_serial, phone_info):
    assert "1" == getprop(
        "ro.vendor.power_mode.support", device_serial
    ), "高性能模式检测失败"


# PQE1.0
@pytest.mark.require_non_slim_device()
def test_pqe1_0(device_serial, phone_info):
    """
    PQE1.0功能检测
    - MTK平台: 需要G70或更高版本的芯片
    - 展锐平台: 需要Android 14以上且芯片高于T606
    """
    build_brand = get_device_build_brand(device_serial)
    soc_model = get_soc_model_code(device_serial)
    android_version = int(phone_info["android_version"])

    if build_brand == "MTK":
        # MTK: >= G70才支持检测
        if soc_model not in SOC_MODEL_PRIORITY:
            pytest.skip(f"MTK平台未知芯片型号: {soc_model}")

        # 检查芯片优先级是否达到G70或更高
        current_priority = SOC_MODEL_PRIORITY.get(soc_model, 0)
        g70_priority = SOC_MODEL_PRIORITY.get("G70", 0)

        if current_priority < g70_priority:
            pytest.skip(f"MTK平台需要G70或更高版本芯片，当前芯片: {soc_model}")

    elif build_brand == "UMS":
        # 展锐 Android > 14且芯片 >T606

        if android_version <= AndroidVersion.U:
            pytest.skip(f"展锐平台需要Android 14以上版本，当前版本: {android_version}")

        if soc_model not in SOC_MODEL_PRIORITY:
            pytest.skip(f"展锐平台未知芯片型号: {soc_model}")

        # 检查芯片优先级是否高于T606
        current_priority = SOC_MODEL_PRIORITY.get(soc_model, 0)
        t606_priority = SOC_MODEL_PRIORITY.get("T606", 0)

        if current_priority <= t606_priority:
            pytest.skip(f"展锐平台需要高于T606的芯片，当前芯片: {soc_model}")
    else:
        pytest.skip(f"PQE1.0功能仅支持MTK和展锐平台，当前平台: {build_brand}")

    if android_version == AndroidVersion.W:
        assert "true" == getprop(
            "ro.tr_perf.game.pq.support", device_serial
        ), "PQE1.0功能检测失败"
    else:
        assert "1" == getprop(
            "ro.product.tran_pq_support", device_serial
        ), "PQE1.0功能检测失败"


# launcher新版精简动效
def test_launcher_simplified_animation(device_serial, phone_info):
    """
    launcher新版精简动效功能检测
    V:
    根据芯片平台返回不同的属性值：
    - G99/G100以下：1 1 0
    - G99/G100~D7300(不包括)：2 2 2
    - D7300及以上：3 3 3

    W:
    G99/G100以下:
    1101
    G99/G100~D7300(不包括):
    2222
    D7300及以上:
    3333

    U版本不检测
    """
    from src.conftests.marker_check import SOC_MODEL_PRIORITY
    from src.conftests.device import get_soc_model_code

    soc_model = get_soc_model_code(device_serial)
    if soc_model not in SOC_MODEL_PRIORITY:
        pytest.skip(f"未知芯片型号: {soc_model}")

    current_priority = SOC_MODEL_PRIORITY.get(soc_model, 0)
    # 根据芯片优先级判断期望值
    g99_priority = SOC_MODEL_PRIORITY.get("G99", 13)  # G99/G100优先级为13
    d7300_priority = SOC_MODEL_PRIORITY.get("D7300", 16)  # D7300优先级为16

    # 获取三个属性的值
    unlock_mode = getprop("ro.transsion_unlock_mode_support", device_serial)
    launch_start_exit = getprop("ro.transsion_launch_start_exit_support", device_serial)
    power_keyguard_animation = getprop(
        "ro.transsion_power_keyguard_animation_support", device_serial
    )

    if int(phone_info["android_version"]) == AndroidVersion.V:
        if current_priority == 0:
            pytest.skip(f"未知芯片型号: {soc_model}")
        if current_priority < g99_priority:
            expected_values = ("1", "1", "0")
            expected_desc = "G99/G100以下芯片平台"
        elif current_priority < d7300_priority:
            expected_values = ("2", "2", "2")
            expected_desc = "G99/G100~D7300(不包括)芯片平台"
        else:
            expected_values = ("3", "3", "3")
            expected_desc = "D7300及以上芯片平台"

        # 验证三个属性的值
        actual_values = (unlock_mode, launch_start_exit, power_keyguard_animation)

        if actual_values != expected_values:
            pytest.fail(
                f"launcher新版精简动效检测失败 ({expected_desc})\n"
                f"期望: unlock_mode={expected_values[0]}, launch_start_exit={expected_values[1]}, power_keyguard_animation={expected_values[2]}\n"
                f"实际: unlock_mode={actual_values[0]}, launch_start_exit={actual_values[1]}, power_keyguard_animation={actual_values[2]}"
            )
    elif int(phone_info["android_version"]) > AndroidVersion.V:
        # 获取四个属性的值
        unlock_mode = getprop("ro.tr_perf.unlock_mode.model", device_serial)
        launch_start_exit = getprop("ro.tr_perf.launch_start_exit.model", device_serial)
        recent_animation = getprop("ro.tr_perf.recent_animation.model", device_serial)

        if current_priority == 0:
            pytest.skip(f"未知芯片型号: {soc_model}")
        if current_priority < g99_priority:
            # G99/G100以下: 1 1 1
            expected_values = ("1", "1",  "1")
            expected_desc = "G99/G100以下芯片平台"
        elif current_priority < d7300_priority:
            # G99/G100~D7300(不包括): 2 2 2
            expected_values = ("2", "2",  "2")
            expected_desc = "G99/G100~D7300(不包括)芯片平台"
        else:
            # D7300及以上: 3 3 3
            expected_values = ("3", "3",  "3")
            expected_desc = "D7300及以上芯片平台"

        # 验证四个属性的值
        actual_values = (
            unlock_mode,
            launch_start_exit,
            recent_animation,
        )

        if actual_values != expected_values:
            # recent_animation的值1和2是同样的效果
            if expected_values[2] in ("1", "2") and actual_values[2] in ("1", "2") and expected_values[0] == actual_values[0] and expected_values[1] == actual_values[1] :
                pytest.skip(
                    f"launcher新版精简动效检测成功 ({expected_desc})\n"
                    f"期望: unlock_mode={expected_values[0]}, launch_start_exit={expected_values[1]}, recent_animation={expected_values[2]}\n"
                    f"实际: unlock_mode={actual_values[0]}, launch_start_exit={actual_values[1]},  recent_animation={actual_values[2]}\n"
                    f"说明: recent_animation的值1和2是同样的效果"
                )
            else:
                pytest.fail(
                f"launcher新版精简动效检测失败 ({expected_desc})\n"
                f"期望: unlock_mode={expected_values[0]}, launch_start_exit={expected_values[1]}, recent_animation={expected_values[2]}\n"
                f"实际: unlock_mode={actual_values[0]}, launch_start_exit={actual_values[1]},  recent_animation={actual_values[2]}"
            )
