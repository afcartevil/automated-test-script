# coding=utf-8
import pytest

from src.conftests.device import get_device_build_brand
from src.utils.adb.adb_utils import adb_shell, getprop


def _skip_unless_build_brand(device_serial, platform_field):
    """将表格「平台适配」字段映射为运行时平台校验（与 marker 同源 get_device_build_brand）。"""
    allowed = []
    for part in platform_field.replace("\\", ",").split(","):
        token = part.strip().upper()
        if token == "QCOM":
            allowed.append("QCOM")
        elif token:
            allowed.append(token)
    brand = get_device_build_brand(device_serial).upper()
    if brand not in allowed:
        pytest.skip(f"需要平台 {allowed}，当前品牌: {brand}")


@pytest.mark.require_spd_feature_support("SF-202507-001974")
def test_smoke_usd_audio_magic_voice(device_serial):
    """
    魔音变声
    适配条件: SPD是否支持 (SF-202507-001974)
    宏控开关:
    测试步骤: v2.0 getprop ro.tr_game.magic_voice_v2.support;
              v1.0 getprop ro.tr_game.magic_voice.support
    预期结果: 1为支持
    平台适配: MTK,SPRD
    """
    _skip_unless_build_brand(device_serial, "MTK,SPRD")

    v2_value = getprop("ro.tr_game.magic_voice_v2.support", device_serial)
    v1_value = getprop("ro.tr_game.magic_voice.support", device_serial)
    is_supported = v2_value == "1" or v1_value == "1"

    assert is_supported, (
        f"魔音变声校验失败: expected v2 or v1 == 1; "
        f"v2={v2_value!r}; v1={v1_value!r}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-001972")
def test_smoke_usd_audio_esport_ap(device_serial):
    """
    沉浸音效
    适配条件: SPD是否支持 (SF-202507-001972)
    宏控开关: V1.0：TRAN_AUDIO_ESPORTSPRO_SUPPORT; v2.0：TRAN_AUDIO_ESPORTS_PRO_SUPPORT
    测试步骤: adb shell getprop ro.tr_audio.esport_ap.feature.support
    预期结果: 显示 1 合入成功
    """
    actual = getprop("ro.tr_audio.esport_ap.feature.support", device_serial)
    assert actual == "1", f"沉浸音效校验失败: expected 1; actual: {actual!r}"


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-001973")
def test_smoke_usd_audio_esport_npu(device_serial):
    """
    沉浸音效-D8300
    适配条件: SPD是否支持 (SF-202507-001973)
    测试步骤: adb shell getprop ro.tr_audio.esport_npu.feature.support
    预期结果: 显示 1 合入成功
    """
    actual = getprop("ro.tr_audio.esport_npu.feature.support", device_serial)
    assert actual == "1", f"沉浸音效-D8300校验失败: expected 1; actual: {actual!r}"


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202508-000161")
def test_smoke_usd_audio_noisereduce_model(device_serial):
    """
    全场景智能降噪
    适配条件: SPD是否支持 (SF-202508-000161)
    测试步骤: adb shell getprop ro.tr_audio.noisereduce.model
    预期结果: 非 NA，且为 F_AINR / F_VPNR / F_AIVPNR（或 C_AINR / C_VPNR / C_AIVPNR）之一
    """
    actual = getprop("ro.tr_audio.noisereduce.model", device_serial)
    allowed = {
        "F_AINR",
        "F_VPNR",
        "F_AIVPNR",
        "C_AINR",
        "C_VPNR",
        "C_AIVPNR",
    }

    assert actual and actual != "NA" and actual in allowed, (
        f"全场景智能降噪校验失败: expected one of {sorted(allowed)}; actual: {actual!r}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002471")
def test_smoke_usd_audio_hifiaudio(device_serial):
    """
    高分辨率音频解析
    适配条件: SPD是否支持 (SF-202507-002471)
    备注: 已下架
    测试步骤: 有线 ro.vendor.mtk_hifiaudio_support;
              无线 ro.odm.tr_audio.hifiaudio.feature.support
    预期结果: 显示 1 合入成功
    """
    wired = getprop("ro.vendor.mtk_hifiaudio_support", device_serial)
    wireless = getprop("ro.odm.tr_audio.hifiaudio.feature.support", device_serial)
    is_supported = wired == "1" or wireless == "1"

    assert is_supported, (
        f"高分辨率音频解析校验失败: expected wired or wireless == 1; "
        f"wired={wired!r}; wireless={wireless!r}"
    )


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002469")
def test_smoke_usd_audio_dts(device_serial):
    """
    dts音效
    适配条件: SPD是否支持 (SF-202507-002469)
    宏控开关: TRAN_DTS_SUPPORT
    测试步骤: adb shell getprop ro.tr_audio.dts.feature.support
    预期结果: 显示 1 合入成功
    """
    actual = getprop("ro.tr_audio.dts.feature.support", device_serial)
    assert actual == "1", f"dts音效校验失败: expected 1; actual: {actual!r}"


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002470")
def test_smoke_usd_audio_dolby(device_serial):
    """
    dolby音效
    适配条件: SPD是否支持 (SF-202507-002470)
    宏控开关: TRAN_AUDIO_DOLBY_SUPPORT
    测试步骤: adb shell getprop persist.tr_audio.dolby.feature.support
    预期结果: 显示 true 表示支持
    """
    actual = getprop("persist.tr_audio.dolby.feature.support", device_serial)
    assert actual == "true", f"dolby音效校验失败: expected true; actual: {actual!r}"


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002472")
def test_smoke_usd_audio_supervol(device_serial):
    """
    大音量
    适配条件: SPD是否支持 (SF-202507-002472)
    测试步骤: adb shell getprop ro.tr_audio.supervol.feature.support
    预期结果: 显示 true 表示支持
    """
    actual = getprop("ro.tr_audio.supervol.feature.support", device_serial)
    assert actual == "true", f"大音量校验失败: expected true; actual: {actual!r}"


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002475")
def test_smoke_usd_audio_hac_mtk(device_serial):
    """
    听力助手-mtk
    适配条件: SPD是否支持 (SF-202507-002475)
    宏控开关: MTK_HAC_SUPPORT
    测试步骤: cat /odm/etc/vconfig/audio/audio_param/AudioParamOptions_vext.xml | grep MTK_HAC_SUPPORT
    预期结果: 关键属性返回值为 YES 表示支持，NO 或空为不支持
    """
    shell_command = (
        "cat /odm/etc/vconfig/audio/audio_param/AudioParamOptions_vext.xml "
        "| grep MTK_HAC_SUPPORT"
    )
    result = adb_shell(device_serial, shell_command, no_retry=True)
    actual_output = result["output"]
    matched_lines = [
        line
        for line in actual_output.splitlines()
        if "MTK_HAC_SUPPORT" in line
    ]

    assert matched_lines and any("yes" in line.lower() for line in matched_lines), (
        f"听力助手-mtk校验失败: expected MTK_HAC_SUPPORT line contains YES; "
        f"actual: {actual_output!r}"
    )


@pytest.mark.require_build_brand("UMS")
@pytest.mark.require_spd_feature_support("SF-202507-002476")
def test_smoke_usd_audio_voice_hac_sprd(device_serial):
    """
    听力助手-sprd
    适配条件: SPD是否支持 (SF-202507-002476)
    测试步骤: adb shell getprop ro.vendor.tran.voice_hac_support
    预期结果: 显示 true 表示支持
    """
    actual = getprop("ro.vendor.tran.voice_hac_support", device_serial)
    assert actual == "true", f"听力助手-sprd校验失败: expected true; actual: {actual!r}"


@pytest.mark.require_build_brand("QCOM")
def test_smoke_usd_audio_hac_qcom(device_serial):
    """
    听力助手-qcom
    适配条件: SPD是否支持（SPD编码 NA，仅按平台适配执行）
    宏控开关: TRAN_AUDIO_CALL_HAC_ENABLE
    测试步骤: adb shell getprop ro.odm.tr_audio.hac.feature.support
    预期结果: 显示 true 表示支持
    """
    actual = getprop("ro.odm.tr_audio.hac.feature.support", device_serial)
    assert actual == "true", f"听力助手-qcom校验失败: expected true; actual: {actual!r}"


@pytest.mark.require_spd_feature_support("SF-202507-002521")
def test_smoke_usd_audio_monitor_rotation(device_serial):
    """
    声道自适应
    适配条件: SPD是否支持 (SF-202507-002521)
    测试步骤: adb shell getprop ro.audio.monitorRotation
    预期结果: 显示 true 表示支持
    平台适配: MTK,SPRD,Qcom
    """
    _skip_unless_build_brand(device_serial, "MTK,SPRD,Qcom")

    actual = getprop("ro.audio.monitorRotation", device_serial)
    assert actual == "true", f"声道自适应校验失败: expected true; actual: {actual!r}"


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002523")
def test_smoke_usd_audio_ultrasound(device_serial):
    """
    超声距感
    适配条件: SPD是否支持 (SF-202507-002523)
    测试步骤: adb shell getprop ro.tr_audio.ultrasound.support
    预期结果: 显示 1 表示支持
    """
    actual = getprop("ro.tr_audio.ultrasound.support", device_serial)
    assert actual == "1", f"超声距感校验失败: expected 1; actual: {actual!r}"


@pytest.mark.require_spd_feature_support("SF-202507-002526")
def test_smoke_usd_audio_check_silence_mtk_qcom(device_serial):
    """
    静音省功耗-mtk/qcom
    适配条件: SPD是否支持 (SF-202507-002526)
    测试步骤: adb shell getprop persist.tr_audio.check_silence.feature.support
    预期结果: 显示 true 表示支持
    平台适配: MTK,Qcom
    """
    _skip_unless_build_brand(device_serial, "MTK,Qcom")

    actual = getprop("persist.tr_audio.check_silence.feature.support", device_serial)
    assert actual == "true", f"静音省功耗-mtk/qcom校验失败: expected true; actual: {actual!r}"


@pytest.mark.require_build_brand("UMS")
@pytest.mark.require_spd_feature_support("SF-202507-002526")
def test_smoke_usd_audio_check_silence_sprd(device_serial):
    """
    静音省功耗-sprd
    适配条件: SPD是否支持 (SF-202507-002526)
    测试步骤: adb shell getprop ro.vendor.af.check_silence
    预期结果: 显示 true 表示支持
    """
    actual = getprop("ro.vendor.af.check_silence", device_serial)
    assert actual == "true", f"静音省功耗-sprd校验失败: expected true; actual: {actual!r}"


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support("SF-202507-002498")
def test_smoke_usd_audio_wireless_microphone(device_serial):
    """
    无线麦克风(无线传声)
    适配条件: SPD是否支持 (SF-202507-002498)
    测试步骤: adb shell getprop ro.vendor.tran_audio_wireless_microphone.support
    预期结果: 显示 1 表示支持
    """
    actual = getprop("ro.vendor.tran_audio_wireless_microphone.support", device_serial)
    assert actual == "1", f"无线麦克风校验失败: expected 1; actual: {actual!r}"


@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_spd_feature_support(
    ["SF-202507-001694", "SF-202507-001700"]
)
def test_smoke_usd_audio_livecaption(device_serial):
    """
    通话翻译\通话摘要
    适配条件: SPD是否支持 (SF-202507-001694, SF-202507-001700)
    测试步骤: adb shell getprop ro.tr_aiservice.aicorespeech_livecaption.feature.support
    预期结果: 显示 true 或 1 表示支持
    """
    actual = getprop(
        "ro.tr_aiservice.aicorespeech_livecaption.feature.support", device_serial
    )
    assert actual in ("true", "1"), (
        f"通话翻译/通话摘要校验失败: expected true or 1; actual: {actual!r}"
    )
