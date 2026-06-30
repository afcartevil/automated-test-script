# coding=utf-8
import pytest

from src.conftests.device import get_device_market
from src.utils.adb.adb_utils import getprop


def _spd_market_supported(spd_config, feature_code, market):
    feature_info = spd_config.get(feature_code)
    if not feature_info:
        return False
    return feature_info.get(market) == "1"


def _require_any_spd_supported(pytestconfig, device_serial, feature_codes):
    spd_config = getattr(pytestconfig, "_spd_feature_config", {})
    market = get_device_market(device_serial)
    if not market:
        pytest.skip("market 为空，无法判断 SPD 支持性")
    if not any(
        _spd_market_supported(spd_config, code, market) for code in feature_codes
    ):
        pytest.skip(
            f"SPD {'/'.join(feature_codes)} 在当前市场 {market} 均不支持，跳过该用例"
        )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002499")
def test_smoke_usd_device_framework_backlight_optimization(device_serial):
    """
    自动亮度开关,基于三星S23拟合的自动背光调节曲线
    适配条件: SPD是否支持 (SF-202507-002499)
    测试步骤: adb shell getprop ro.tr_light.backlight.optimization.feature.support
    预期结果: 1为支持
    """
    prop_key = "ro.tr_light.backlight.optimization.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"自动亮度开关校验失败: expected: {expected_value}; actual: {actual_value}"
    )


@pytest.mark.require_spd_feature_support("SF-202602-000001")
def test_smoke_usd_device_framework_human_centric_abl(device_serial):
    """
    人因背光（16.3）
    适配条件: SPD是否支持 (SF-202602-000001)
    测试步骤:
    adb shell getprop ro.tr_light.always_enable_abl.support
    adb shell getprop ro.tr_light.human_centric_abl.support
    预期结果: 1为支持
    """
    prop_keys = (
        "ro.tr_light.always_enable_abl.support",
        "ro.tr_light.human_centric_abl.support",
    )
    expected_value = "1"

    for prop_key in prop_keys:
        actual_value = getprop(prop_key, device_serial)
        assert actual_value == expected_value, (
            f"人因背光校验失败({prop_key}): "
            f"expected: {expected_value}; actual: {actual_value}"
        )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002500")
def test_smoke_usd_device_framework_backlight_level(device_serial):
    """
    背光调节等级
    适配条件: SPD是否支持 (SF-202507-002500)
    测试步骤: adb shell getprop ro.tr_light.backlight.level
    预期结果: 返回值为空或4095即为合入
    """
    prop_key = "ro.tr_light.backlight.level"

    actual_value = getprop(prop_key, device_serial) or ""
    is_valid = actual_value == "" or actual_value == "4095"
    assert is_valid, (
        f"背光调节等级校验失败: expected empty or 4095; actual: {actual_value!r}"
    )


@pytest.mark.require_spd_feature_support("SF-202507-002501")
def test_smoke_usd_device_framework_backlight_opt_v2(device_serial):
    """
    无感背光调节
    适配条件: SPD是否支持 (SF-202507-002501)
    测试步骤: adb shell getprop ro.tr_light.backlight.opt.v2.config.feature.support
    预期结果: 1为支持
    """
    prop_key = "ro.tr_light.backlight.opt.v2.config.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"无感背光调节校验失败: expected: {expected_value}; actual: {actual_value}"
    )


@pytest.mark.require_spd_feature_support("SF-202507-002502")
def test_smoke_usd_device_framework_hbm_lcd(device_serial):
    """
    HBM高亮-LCD屏幕
    适配条件: SPD是否支持 (SF-202507-002502)
    测试步骤:
    adb shell getprop ro.tr_light.high.brightness.mode.feature.support
    adb shell getprop ro.odm.tr_light.high.brightness.mode.hal.feature.support
    adb shell getprop ro.tr_light.hbm.v2.lcd.feature.support
    预期结果: 1为支持
    """
    prop_keys = (
        "ro.tr_light.high.brightness.mode.feature.support",
        "ro.odm.tr_light.high.brightness.mode.hal.feature.support",
        "ro.tr_light.hbm.v2.lcd.feature.support",
    )
    expected_value = "1"

    for prop_key in prop_keys:
        actual_value = getprop(prop_key, device_serial)
        assert actual_value == expected_value, (
            f"HBM高亮-LCD屏幕校验失败({prop_key}): "
            f"expected: {expected_value}; actual: {actual_value}"
        )


@pytest.mark.require_spd_feature_support("SF-202507-002503")
def test_smoke_usd_device_framework_hbm_oled(device_serial):
    """
    HBM高亮-OLED屏幕
    适配条件: SPD是否支持 (SF-202507-002503)
    测试步骤:
    adb shell getprop ro.tr_light.high.brightness.mode.feature.support
    adb shell getprop ro.tr_light.hbm.v2.oled.level
    预期结果: mode为1；W等级时 oled.level=512，4095等级时需 lcd.feature.support=1
    """
    mode_support = getprop(
        "ro.tr_light.high.brightness.mode.feature.support", device_serial
    )
    oled_level = getprop("ro.tr_light.hbm.v2.oled.level", device_serial) or ""

    assert mode_support == "1", (
        f"HBM高亮-OLED屏幕校验失败: expected mode support 1; actual: {mode_support}"
    )

    if oled_level == "512":
        return

    lcd_support = getprop("ro.tr_light.hbm.v2.lcd.feature.support", device_serial)
    assert lcd_support == "1", (
        f"HBM高亮-OLED屏幕校验失败: 4095等级需 ro.tr_light.hbm.v2.lcd.feature.support=1; "
        f"oled.level={oled_level!r}; lcd.support={lcd_support!r}"
    )


@pytest.mark.require_spd_feature_support("SF-202509-000214")
def test_smoke_usd_device_framework_xdr(device_serial):
    """
    XDR
    适配条件: SPD是否支持 (SF-202509-000214)
    测试步骤: adb shell getprop ro.tr_light.xdr.support
    预期结果: 1为支持
    """
    prop_key = "ro.tr_light.xdr.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"XDR校验失败: expected: {expected_value}; actual: {actual_value}"
    )


@pytest.mark.require_spd_feature_support("SF-202507-002530")
def test_smoke_usd_device_framework_app_brightness_limit(device_serial):
    """
    APP动态降背光
    适配条件: SPD是否支持 (SF-202507-002530)
    测试步骤: adb shell getprop ro.tr_light.app_brightness_limit_v2.feature.support
    预期结果: 1为支持
    """
    prop_key = "ro.tr_light.app_brightness_limit_v2.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"APP动态降背光校验失败: expected: {expected_value}; actual: {actual_value}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202508-000164")
def test_smoke_usd_device_framework_indoor_max_brightness_limit(device_serial):
    """
    室内非强光环境下最大亮度限制
    适配条件: SPD是否支持 (SF-202508-000164)
    测试步骤: adb shell getprop ro.tr_light.max_brightness_limit.support
    预期结果: 1为支持
    """
    prop_key = "ro.tr_light.max_brightness_limit.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"室内非强光环境下最大亮度限制校验失败: expected: {expected_value}; actual: {actual_value}"
    )


@pytest.mark.require_spd_feature_support("SF-202507-002556")
def test_smoke_usd_device_framework_ai_charging_protect(device_serial):
    """
    AI智能充电保护
    适配条件: SPD是否支持 (SF-202507-002556)
    测试步骤: adb shell getprop ro.tr_battery.ai_charging_event_track.feature.support
    预期结果: 1为支持
    """
    prop_key = "ro.tr_battery.ai_charging_event_track.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"AI智能充电保护校验失败: expected: {expected_value}; actual: {actual_value}"
    )


@pytest.mark.require_spd_feature_support("SF-202511-000012")
def test_smoke_usd_device_framework_travel_fast_charge(device_serial):
    """
    差旅疾充(16.2)
    适配条件: SPD是否支持 (SF-202511-000012)
    测试步骤: adb shell getprop ro.tr_tce.travel.feature.support
    预期结果: 1为支持
    """
    prop_key = "ro.tr_tce.travel.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"差旅疾充校验失败: expected: {expected_value}; actual: {actual_value}"
    )


def test_smoke_usd_device_framework_bypass_charging(device_serial, pytestconfig):
    """
    旁路充电
    适配条件: SPD是否支持 (SF-202508-000010/SF-202508-000011)
    测试步骤: adb shell getprop ro.tr_battery.full_scene_bypass_charging.feature.support
    预期结果: 1为支持
    """
    _require_any_spd_supported(
        pytestconfig,
        device_serial,
        ["SF-202508-000010", "SF-202508-000011"],
    )

    prop_key = "ro.tr_battery.full_scene_bypass_charging.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"旁路充电校验失败: expected: {expected_value}; actual: {actual_value}"
    )


@pytest.mark.require_spd_feature_support("SF-202507-002562")
def test_smoke_usd_device_framework_pocket_mode(device_serial):
    """
    口袋模式
    适配条件: SPD是否支持 (SF-202507-002562)
    测试步骤: adb shell getprop ro.tr_sensor.anti.touch.pocketmode.feature.support
    预期结果: 1为支持
    """
    prop_key = "ro.tr_sensor.anti.touch.pocketmode.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"口袋模式校验失败: expected: {expected_value}; actual: {actual_value}"
    )


@pytest.mark.require_spd_feature_support("SF-202507-002567")
def test_smoke_usd_device_framework_heartrate_oximetry(device_serial):
    """
    心率血氧检测
    适配条件: SPD是否支持 (SF-202507-002567)
    测试步骤: adb shell getprop ro.tr_sensor.heartrate_oximetry.support
    预期结果: 1为支持
    """
    prop_key = "ro.tr_sensor.heartrate_oximetry.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"心率血氧检测校验失败: expected: {expected_value}; actual: {actual_value}"
    )


@pytest.mark.require_spd_feature_support(
    ["SF-202507-002590", "SF-202507-002589"]
)
def test_smoke_usd_device_framework_motion_sickness_ui(device_serial):
    """
    晕动舒缓显示-界面显示/手动开关
    适配条件: SPD是否支持 (SF-202507-002590/SF-202507-002589)
    测试步骤: adb shell getprop ro.tr_microIntelligence.motion_sickness.feature.support
    预期结果: 1为支持
    """
    prop_key = "ro.tr_microIntelligence.motion_sickness.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"晕动舒缓显示-界面显示/手动开关校验失败: expected: {expected_value}; actual: {actual_value}"
    )


@pytest.mark.require_spd_feature_support("SF-202507-002588")
def test_smoke_usd_device_framework_motion_sickness_vehicle(device_serial):
    """
    晕动舒缓显示-自动乘车/下车识别
    适配条件: SPD是否支持 (SF-202507-002588)
    测试步骤: adb shell getprop ro.tr_sensor.vehicle_mode.feature.support
    预期结果: 1为支持
    """
    prop_key = "ro.tr_sensor.vehicle_mode.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"晕动舒缓显示-自动乘车/下车识别校验失败: expected: {expected_value}; actual: {actual_value}"
    )


@pytest.mark.require_spd_feature_support("SF-202507-000882")
def test_smoke_usd_device_framework_notify_screenon(device_serial):
    """
    通知亮屏控制
    适配条件: SPD是否支持 (SF-202507-000882)
    测试步骤: adb shell getprop ro.tr_power.notify_screenon.feature.support
    预期结果: 1为支持
    """
    prop_key = "ro.tr_power.notify_screenon.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"通知亮屏控制校验失败: expected: {expected_value}; actual: {actual_value}"
    )


@pytest.mark.require_spd_feature_support("SF-202507-002401")
def test_smoke_usd_device_framework_si_battery_shutdown_lowvolt(device_serial):
    """
    硅负极电池容量扩展
    适配条件: SPD是否支持 (SF-202507-002401)
    测试步骤: adb shell getprop ro.tr_battery.shutdown_lowvolt.feature.support
    预期结果: 1为支持
    """
    prop_key = "ro.tr_battery.shutdown_lowvolt.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"硅负极电池容量扩展校验失败: expected: {expected_value}; actual: {actual_value}"
    )


@pytest.mark.require_spd_feature_support("SF-202507-002402")
def test_smoke_usd_device_framework_non_si_battery_shutdown_lowvolt(device_serial):
    """
    非硅负极电池容量扩展
    适配条件: SPD是否支持 (SF-202507-002402)
    测试步骤: adb shell getprop ro.tr_battery.shutdown_lowvolt.feature.support
    预期结果: 1为支持
    """
    prop_key = "ro.tr_battery.shutdown_lowvolt.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"非硅负极电池容量扩展校验失败: expected: {expected_value}; actual: {actual_value}"
    )


@pytest.mark.require_spd_feature_support("SF-202508-000072")
def test_smoke_usd_device_framework_lock_brightness(device_serial):
    """
    显示与亮度·显示设置
    适配条件: SPD是否支持 (SF-202508-000072)
    测试步骤: adb shell getprop ro.tr_light.lock_brightness.feature.support
    预期结果: 1为支持
    """
    prop_key = "ro.tr_light.lock_brightness.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"显示与亮度·显示设置校验失败: expected: {expected_value}; actual: {actual_value}"
    )


def test_smoke_usd_device_framework_ru_camera_lowwarning(device_serial):
    """
    RU市场配置
    适配条件: RU市场支持
    测试步骤:
    1. adb shell getprop ro.product.name，返回值包含RU字段则继续，否则跳过
    2. adb shell getprop ro.tr_battery.camera_lowwarning.feature.support
    预期结果: 返回值为1
    """
    product_name = getprop("ro.product.name", device_serial) or ""
    if "RU" not in product_name.upper():
        pytest.skip(f"非RU市场设备，ro.product.name={product_name!r}")

    prop_key = "ro.tr_battery.camera_lowwarning.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"RU市场配置校验失败: expected: {expected_value}; actual: {actual_value}"
    )


def test_smoke_usd_device_framework_shutdown_emergency(device_serial):
    """
    倒计时关机功能
    测试步骤: adb shell getprop ro.tr_battery.shutdown_emergency.feature.support
    预期结果: 返回值为1
    """
    prop_key = "ro.tr_battery.shutdown_emergency.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"倒计时关机功能校验失败: expected: {expected_value}; actual: {actual_value}"
    )


def test_smoke_usd_device_framework_low_temperature(device_serial):
    """
    低温关机
    测试步骤: adb shell getprop ro.tr_power.low_temperature.feature.support
    预期结果: 返回值为1
    """
    prop_key = "ro.tr_power.low_temperature.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"低温关机校验失败: expected: {expected_value}; actual: {actual_value}"
    )


def test_smoke_usd_device_framework_trancharge(device_serial):
    """
    自研TranCharge架构
    测试步骤: adb shell getprop ro.tr_battery.trancharge.feature.support
    预期结果: 返回值为1
    """
    prop_key = "ro.tr_battery.trancharge.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"自研TranCharge架构校验失败: expected: {expected_value}; actual: {actual_value}"
    )


def test_smoke_usd_device_framework_vibration_time(device_serial):
    """
    充电震动240
    测试步骤: adb shell getprop ro.tr_battery.viration.time.feature.support
    预期结果: 返回值为1
    """
    prop_key = "ro.tr_battery.viration.time.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"充电震动240校验失败: expected: {expected_value}; actual: {actual_value}"
    )


def test_smoke_usd_device_framework_screenon_wake_reason(device_serial):
    """
    亮屏信息存储
    测试步骤: adb shell getprop ro.tr_power.anti_touch_screenon_wake_reason.feature.support
    预期结果: 返回值为1
    """
    prop_key = "ro.tr_power.anti_touch_screenon_wake_reason.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"亮屏信息存储校验失败: expected: {expected_value}; actual: {actual_value}"
    )


def test_smoke_usd_device_framework_lightsensor_optimiz(device_serial):
    """
    亮屏首次自动背光rate值
    测试步骤: adb shell getprop ro.tr_light.lightsensor.optimiz.feature.support
    预期结果: 返回值为1
    """
    prop_key = "ro.tr_light.lightsensor.optimiz.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"亮屏首次自动背光rate值校验失败: expected: {expected_value}; actual: {actual_value}"
    )


def test_smoke_usd_device_framework_multi_scene_backlight(device_serial):
    """
    传音定制的override功能
    测试步骤: adb shell getprop ro.tr_light.multi.scene.backlight.feature.support
    预期结果: 返回值为1
    """
    prop_key = "ro.tr_light.multi.scene.backlight.feature.support"
    expected_value = "1"

    actual_value = getprop(prop_key, device_serial)
    assert actual_value == expected_value, (
        f"传音定制的override功能校验失败: expected: {expected_value}; actual: {actual_value}"
    )


def test_smoke_usd_device_framework_ps_debounce_optimization(device_serial, pytestconfig):
    """
    PS防抖优化
    适配条件: 默认支持；支持超声波距感(SF-202507-002523)就不支持PS防抖优化
    测试步骤: adb shell getprop ro.tr_sensor.proximity.debounce.optimization.support
    预期结果: 默认返回值为1；支持超声波距感时不为1
    """
    prop_key = "ro.tr_sensor.proximity.debounce.optimization.support"
    actual_value = getprop(prop_key, device_serial) or ""

    spd_config = getattr(pytestconfig, "_spd_feature_config", {})
    market = get_device_market(device_serial)
    ultrasonic_supported = (
        market
        and _spd_market_supported(spd_config, "SF-202507-002523", market)
    )

    if ultrasonic_supported:
        assert actual_value != "1", (
            f"PS防抖优化校验失败: 支持超声波距感时不应开启PS防抖优化; actual: {actual_value!r}"
        )
    else:
        assert actual_value == "1", (
            f"PS防抖优化校验失败: expected: 1; actual: {actual_value!r}"
        )
