# coding=utf-8
import re

import pytest

from src.utils.adb.adb_utils import adb_cat, adb_shell, getprop

_FIRMWARE_VERSION_PATTERN = re.compile(r"0x[0-9a-fA-F]+,bv:0x[0-9a-fA-F]+")
_VENDOR_PATTERN = re.compile(r"^[A-Z]{2,}_[A-Z0-9]+_\d{2}$")

_ESPORTS_FEATURE_PROPS = (
    "ro.tr_game.tp_esports10.feature.support",
    "ro.tr_game.tp_esports20.feature.support",
    "ro.tr_game.tp_esports30.feature.support",
)


@pytest.mark.require_build_brand("MTK")
def test_smoke_usd_tp_firmware_version(device_serial):
    """
    TP基础功能以及信息检查: 获取固件版本
    测试步骤: cat /sys/devices/platform/mtk-tpd/tp_firmware_version
    预期结果: 0xxx,bv:0xxx (示例 0x22,bv:0x22)
    """
    file_path = "/sys/devices/platform/mtk-tpd/tp_firmware_version"

    actual_output = adb_cat(device_serial, file_path)
    assert actual_output, "TP固件版本读取失败"
    assert _FIRMWARE_VERSION_PATTERN.search(actual_output.strip()), (
        f"TP固件版本格式校验失败: expected pattern like 0x22,bv:0x22; actual: {actual_output}"
    )


@pytest.mark.require_build_brand("MTK")
def test_smoke_usd_tp_vendor(device_serial):
    """
    TP基础功能以及信息检查: 获取供应商信息
    测试步骤: cat /sys/devices/platform/mtk-tpd/tp_vendor
    预期结果: 模块厂商名大写字母_芯片型号_序号 (示例 TM_FT3683G_00)
    """
    file_path = "/sys/devices/platform/mtk-tpd/tp_vendor"

    actual_output = adb_cat(device_serial, file_path)
    assert actual_output, "TP供应商信息读取失败"
    assert _VENDOR_PATTERN.match(actual_output.strip()), (
        f"TP供应商信息格式校验失败: expected pattern like TM_FT3683G_00; actual: {actual_output}"
    )


@pytest.mark.require_build_brand("MTK")
def test_smoke_usd_tp_mtk_tpd(device_serial):
    """
    TP基础功能以及信息检查: 判断是否加载mtk-tpd
    测试步骤: getevent -il
    预期结果: name:     "mtk-tpd"
    """
    shell_command = "getevent -il"
    expected_text = '"mtk-tpd"'

    result = adb_shell(device_serial, shell_command, no_retry=True)
    actual_output = result["output"]

    assert expected_text in actual_output, (
        f"TP mtk-tpd 加载校验失败: expected contains: {expected_text}; actual: {actual_output}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-001952")
def test_smoke_usd_tp_esports_control(device_serial):
    """
    电竞操控: Esport 电竞操控1.0
    适配条件: SPD是否支持 (SF-202507-001952)
    测试步骤:
    1. getprop ro.tr_game.tp_esports10.feature.support
    2. getprop ro.tr_game.tp_esports20.feature.support
    3. getprop ro.tr_game.tp_esports30.feature.support
    预期结果: 1
    """
    expected_value = "1"
    prop_values = {prop: getprop(prop, device_serial) for prop in _ESPORTS_FEATURE_PROPS}

    assert any(value == expected_value for value in prop_values.values()), (
        "电竞操控宏控校验失败: 预期至少一个电竞操控版本特性为 1; "
        f"actual: {prop_values}"
    )
