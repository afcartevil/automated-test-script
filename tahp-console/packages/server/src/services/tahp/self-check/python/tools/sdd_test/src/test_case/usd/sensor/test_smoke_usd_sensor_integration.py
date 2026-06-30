# coding=utf-8
import pytest

from src.utils.adb.adb_utils import adb_shell


@pytest.mark.require_build_brand("MTK")
def test_smoke_usd_sensor_step_import(device_serial):
    """
    计步器是否导入
    适配条件: 无
    测试步骤:
    1. dumpsys sensorservice | grep -e "step_counter"
    2. dumpsys sensorservice | grep -e "step_detector"
    3. dumpsys sensorservice | grep -e "step_detect_wakeup"
    预期结果: 输出分别包含 step_counter、step_detector、step_detect_wakeup
    """
    checks = (
        ('dumpsys sensorservice | grep -e "step_counter"', "step_counter"),
        ('dumpsys sensorservice | grep -e "step_detector"', "step_detector"),
        ('dumpsys sensorservice | grep -e "step_detect_wakeup"', "step_detect_wakeup"),
    )

    for shell_command, expected_text in checks:
        result = adb_shell(device_serial, shell_command, no_retry=True)
        actual_output = result["output"]
        assert expected_text in actual_output, (
            f"计步器导入校验失败({expected_text}): "
            f"expected contains: {expected_text}; actual: {actual_output}"
        )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002593")
def test_smoke_usd_sensor_pdb(device_serial):
    """
    背部距感防误触是否导入
    适配条件: SPD是否支持 (SF-202507-002593)
    测试步骤: dumpsys sensorservice | grep -e pdb
    预期结果: 输出包含 android.sensor.pdb
    """
    shell_command = 'dumpsys sensorservice | grep -e pdb'
    expected_text = "android.sensor.pdb"

    result = adb_shell(device_serial, shell_command, no_retry=True)
    actual_output = result["output"]

    assert expected_text in actual_output, (
        f"背部距感防误触导入校验失败: expected contains: {expected_text}; "
        f"actual: {actual_output}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002591")
def test_smoke_usd_sensor_anti_touch(device_serial):
    """
    正面物理距感防误触是否导入
    适配条件: SPD是否支持 (SF-202507-002591)
    测试步骤: dumpsys sensorservice | grep -e anti_touch
    预期结果: 输出包含 android.sensor.anti_touch
    """
    shell_command = 'dumpsys sensorservice | grep -e anti_touch'
    expected_text = "android.sensor.anti_touch"

    result = adb_shell(device_serial, shell_command, no_retry=True)
    actual_output = result["output"]

    assert expected_text in actual_output, (
        f"正面物理距感防误触导入校验失败: expected contains: {expected_text}; "
        f"actual: {actual_output}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-001954")
def test_smoke_usd_sensor_msc(device_serial):
    """
    游戏虚拟操控是否导入
    适配条件: SPD是否支持 (SF-202507-001954)
    测试步骤: dumpsys sensorservice | grep -e msc
    预期结果: 输出包含 android.sensor.msc
    """
    shell_command = 'dumpsys sensorservice | grep -e msc'
    expected_text = "android.sensor.msc"

    result = adb_shell(device_serial, shell_command, no_retry=True)
    actual_output = result["output"]

    assert expected_text in actual_output, (
        f"游戏虚拟操控导入校验失败: expected contains: {expected_text}; "
        f"actual: {actual_output}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002562")
def test_smoke_usd_sensor_head_posture(device_serial):
    """
    口袋模式 机头姿态检测是否导入
    适配条件: SPD是否支持 (SF-202507-002562)
    测试步骤: dumpsys sensorservice | grep -e head_posture
    预期结果: 输出包含 android.sensor.head_posture
    """
    shell_command = 'dumpsys sensorservice | grep -e head_posture'
    expected_text = "android.sensor.head_posture"

    result = adb_shell(device_serial, shell_command, no_retry=True)
    actual_output = result["output"]

    assert expected_text in actual_output, (
        f"机头姿态检测导入校验失败: expected contains: {expected_text}; "
        f"actual: {actual_output}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002575")
def test_smoke_usd_sensor_pickup(device_serial):
    """
    自研抬手亮屏是否导入
    适配条件: SPD是否支持 (SF-202507-002575)
    测试步骤: dumpsys sensorservice | grep -e pickup
    预期结果: 输出包含 android.sensor.pickup
    """
    shell_command = 'dumpsys sensorservice | grep -e pickup'
    expected_text = "android.sensor.pickup"

    result = adb_shell(device_serial, shell_command, no_retry=True)
    actual_output = result["output"]

    assert expected_text in actual_output, (
        f"自研抬手亮屏导入校验失败: expected contains: {expected_text}; "
        f"actual: {actual_output}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002563")
def test_smoke_usd_sensor_elevator(device_serial):
    """
    电梯模式是否导入
    适配条件: SPD是否支持 (SF-202507-002563)
    测试步骤: dumpsys sensorservice | grep -e elevator
    预期结果: 输出包含 android.sensor.elevator
    """
    shell_command = 'dumpsys sensorservice | grep -e elevator'
    expected_text = "android.sensor.elevator"

    result = adb_shell(device_serial, shell_command, no_retry=True)
    actual_output = result["output"]

    assert expected_text in actual_output, (
        f"电梯模式导入校验失败: expected contains: {expected_text}; "
        f"actual: {actual_output}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002564")
def test_smoke_usd_sensor_vehicle(device_serial):
    """
    乘车检测是否导入
    适配条件: SPD是否支持 (SF-202507-002564)
    测试步骤: dumpsys sensorservice | grep -e vehicle
    预期结果: 输出包含 android.sensor.vehicle
    """
    shell_command = 'dumpsys sensorservice | grep -e vehicle'
    expected_text = "android.sensor.vehicle"

    result = adb_shell(device_serial, shell_command, no_retry=True)
    actual_output = result["output"]

    assert expected_text in actual_output, (
        f"乘车检测导入校验失败: expected contains: {expected_text}; "
        f"actual: {actual_output}"
    )
