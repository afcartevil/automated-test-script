# coding=utf-8
import re

import pytest

from src.utils.adb.adb_utils import adb_cat, adb_shell, getprop


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-000836")
def test_smoke_usd_lcm_aod_feature(device_serial):
    """
    AOD功能信息查询: AOD给上层的接口
    测试步骤: 1.getprop ro.tr_aod.feature.support
              2. cat /sys/kernel/tran_display/lcm_doze_backlight
    预期结果: 1.若SPD支持，读取该属性输出为1
              2.读AOD三档等级：无输出或lcm_doze_backlight:0;0;0;0;为错误，有数值输出为正确
    """
    aod_support = getprop("ro.tr_aod.feature.support", device_serial)
    assert aod_support == "1", (
        f"AOD功能信息查询校验失败: expected ro.tr_aod.feature.support == 1; "
        f"actual: {aod_support!r}"
    )

    doze_path = "/sys/kernel/tran_display/lcm_doze_backlight"
    doze_output = adb_cat(device_serial, doze_path)
    assert doze_output is not None and doze_output.strip() != "", (
        f"AOD功能信息查询校验失败: 无法读取 {doze_path}"
    )

    invalid_all_zero = "lcm_doze_backlight:0;0;0;0;"
    is_invalid = (
        invalid_all_zero in doze_output
        or doze_output.strip() == "0;0;0;0"
        or doze_output.strip() == "0;0;0;0;"
    )
    assert not is_invalid, (
        f"AOD功能信息查询校验失败: AOD三档等级不应全为0; actual: {doze_output!r}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002500")
def test_smoke_usd_lcm_backlight_5119(device_serial):
    """
    5119背光等级检查
    测试步骤: 1.cat /sys/class/leds/lcd-backlight/max_brightness
              2.cat /sys/class/leds/lcd-backlight/max_hw_brightness
    预期结果: 若SPD支持，读输出均为 5119
    """
    expected_brightness = "5119"
    max_brightness_path = "/sys/class/leds/lcd-backlight/max_brightness"
    max_hw_brightness_path = "/sys/class/leds/lcd-backlight/max_hw_brightness"

    max_brightness = adb_cat(device_serial, max_brightness_path)
    assert max_brightness == expected_brightness, (
        f"5119背光等级检查校验失败: expected {expected_brightness} at {max_brightness_path}; "
        f"actual: {max_brightness!r}"
    )

    hw_result = adb_shell(device_serial, f"cat {max_hw_brightness_path}", no_retry=True)
    max_hw_brightness = hw_result["output"].strip()
    if not max_hw_brightness or "Permission denied" in (
        hw_result.get("error") or ""
    ):
        max_hw_brightness = getprop("ro.tr_light.hbm.v2.oled.level", device_serial)

    assert max_hw_brightness == expected_brightness, (
        f"5119背光等级检查校验失败: expected {expected_brightness} at "
        f"{max_hw_brightness_path} (或 ro.tr_light.hbm.v2.oled.level); "
        f"actual: {max_hw_brightness!r}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002512")
def test_smoke_usd_lcm_colorspace_p3(device_serial):
    """
    OLED全链路P3色域功能检查
    测试步骤: getprop ro.tr_colorspace.p3.feature.support
    预期结果: 若SPD支持，读取该属性输出为1
    """
    actual = getprop("ro.tr_colorspace.p3.feature.support", device_serial)
    assert actual == "1", (
        f"OLED全链路P3色域功能检查校验失败: expected 1; actual: {actual!r}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002510")
def test_smoke_usd_lcm_colormode(device_serial):
    """
    OLED 色彩风格
    测试步骤: getprop ro.tr_display.colormode.feature.support
    预期结果: 若SPD支持，读取该属性输出为1
    """
    actual = getprop("ro.tr_display.colormode.feature.support", device_serial)
    assert actual == "1", (
        f"OLED色彩风格校验失败: expected 1; actual: {actual!r}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002509")
def test_smoke_usd_lcm_color_temperature(device_serial):
    """
    OLED 色温
    测试步骤: getprop ro.tr_display.color.temperature.feature.support
    预期结果: 若SPD支持，读取该属性输出为1
    """
    actual = getprop(
        "ro.tr_display.color.temperature.feature.support", device_serial
    )
    assert actual == "1", (
        f"OLED色温校验失败: expected 1; actual: {actual!r}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002529")
def test_smoke_usd_lcm_lcmepc(device_serial):
    """
    屏幕显示一致性 CCM: 色彩相关
    测试步骤: adb shell cat /proc/device-tree/chosen/tran,fdt | grep 'lcmepc'
    预期结果: 若SPD支持，输出 tran.lcmepc= 全0为失败
    """
    shell_command = 'cat /proc/device-tree/chosen/tran,fdt | grep "lcmepc"'
    result = adb_shell(device_serial, shell_command, no_retry=True)
    actual_output = result["output"].strip()

    assert actual_output, (
        f"屏幕显示一致性CCM校验失败: 未找到 lcmepc 输出; actual: {actual_output!r}"
    )

    match = re.search(r"tran\.lcmepc\s*=\s*([0-9a-fA-Fx,;\s]+)", actual_output)
    assert match, (
        f"屏幕显示一致性CCM校验失败: 输出格式不符合预期; actual: {actual_output!r}"
    )

    lcmepc_value = re.sub(r"[^0-9a-fA-F]", "", match.group(1))
    assert lcmepc_value and not set(lcmepc_value) <= {"0"}, (
        f"屏幕显示一致性CCM校验失败: tran.lcmepc 全0为失败; actual: {actual_output!r}"
    )
