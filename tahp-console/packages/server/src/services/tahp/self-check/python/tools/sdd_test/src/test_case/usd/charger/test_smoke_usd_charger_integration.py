# coding=utf-8
import pytest

from src.utils.adb.adb_utils import adb_cat, adb_shell, is_file_exist


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002552")
def test_smoke_usd_charger_burn_debug(device_serial):
    """
    高温防烧检测和提示: 充电端口高温异常检测及时保护手机
    测试步骤: adb命令执行 ls /sys/devices/platform/odm/odm:port_burning/burn
    预期结果: ls命令正常执行，并输出包含burn_debug文件
    """
    shell_command = "ls /sys/devices/platform/odm/odm:port_burning/burn"
    expected_text = "burn_debug"

    result = adb_shell(device_serial, shell_command, no_retry=True)
    actual_output = result["output"]

    assert expected_text in actual_output, (
        f"高温防烧检测校验失败: expected contains: {expected_text}; actual: {actual_output}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002551")
def test_smoke_usd_charger_water_detect(device_serial):
    """
    进水检测: 充电端口液体检测及时保护手机
    测试步骤: adb命令执行 ls /sys/devices/platform/odm/odm:water_detect/tran_class
    预期结果: ls命令正常执行，并输出包含water_detect目录
    """
    shell_command = "ls /sys/devices/platform/odm/odm:water_detect/tran_class"
    expected_text = "water_detect"

    result = adb_shell(device_serial, shell_command, no_retry=True)
    actual_output = result["output"].strip()
    stderr_text = (result.get("error") or "").strip()

    assert expected_text in actual_output, (
        f"进水检测校验失败: 输出不符合预期; "
        f"expected contains: {expected_text}; "
        f"stdout: {actual_output!r}; stderr: {stderr_text!r}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002660")
def test_smoke_usd_charger_tran_led_cmd(device_serial):
    """
    背板灯效芯片: 灯效底层驱动能力适配
    测试步骤: adb命令执行 find /sys/devices/platform/odm -name tran_led_cmd
    预期结果: /sys/devices/platform/odm/odm:tran_led_core/tran_led_cmd
    """
    expected_path = "/sys/devices/platform/odm/odm:tran_led_core/tran_led_cmd"

    is_support = is_file_exist(device_serial, expected_path)
    assert is_support, "背板灯效芯片节点校验失败"


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002543")
def test_smoke_usd_charger_wireless_manager(device_serial):
    """
    无线充电芯片: 无线充电协议能力适配
    测试步骤: adb命令执行 ls /sys/devices/platform/odm/odm:wireless_manager/switching_charger
    预期结果: ls命令正常执行，并输出包含wireless_manager目录
    """
    shell_command = (
        "ls /sys/devices/platform/odm/odm:wireless_manager/switching_charger"
    )
    expected_text = "wireless_manager"

    result = adb_shell(device_serial, shell_command, no_retry=True)
    actual_output = result["output"].strip()

    assert expected_text in actual_output, (
        f"无线充电芯片校验失败: expected contains: {expected_text}; actual: {actual_output}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002401")
def test_smoke_usd_charger_si_battery_poweroff_voltage(device_serial):
    """
    硅负极电池拓展: 把关机电压从3.4V降到3.0V以获得更多的电量
    测试步骤: adb命令执行 cat /sys/devices/platform/charger/Si_Battery_Poweroff_Voltage
    预期结果: <3400
    """
    sysfs_path = "/sys/devices/platform/charger/Si_Battery_Poweroff_Voltage"
    max_voltage_mv = 3400

    actual_value = adb_cat(device_serial, sysfs_path)
    assert actual_value is not None and actual_value != "", (
        f"硅负极电池拓展校验失败: 无法读取 {sysfs_path}"
    )

    voltage_mv = int(actual_value.strip())
    assert voltage_mv < max_voltage_mv, (
        f"硅负极电池拓展校验失败: expected < {max_voltage_mv}; actual: {voltage_mv}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002560")
def test_smoke_usd_charger_battery_health_percent(device_serial):
    """
    电池健康度: 电池健康管理
    测试步骤: adb命令执行 cat /sys/devices/platform/charger/battery_health_percent
    预期结果: >0
    """
    sysfs_path = "/sys/devices/platform/charger/battery_health_percent"

    actual_value = adb_cat(device_serial, sysfs_path)
    assert actual_value is not None and actual_value != "", (
        f"电池健康度校验失败: 无法读取 {sysfs_path}"
    )

    health_percent = int(actual_value.strip())
    assert health_percent > 0, (
        f"电池健康度校验失败: expected > 0; actual: {health_percent}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202508-000003")
def test_smoke_usd_charger_port_corrosion(device_serial):
    """
    端口防腐蚀: 通过typec插入检测达成防腐蚀效果
    测试步骤: adb命令执行 ls /sys/devices/platform/odm/odm:port_corrosion/burn
    预期结果: ls命令正常执行，并输出包含port_corrosion文件
    """
    shell_command = "ls sys/bus/platform/drivers/port_corrosion"
    expected_text = "port_corrosion"

    result = adb_shell(device_serial, shell_command, no_retry=True)
    actual_output = result["output"].strip()

    assert expected_text in actual_output, (
        f"端口防腐蚀校验失败: expected contains: {expected_text}; actual: {actual_output}"
    )
