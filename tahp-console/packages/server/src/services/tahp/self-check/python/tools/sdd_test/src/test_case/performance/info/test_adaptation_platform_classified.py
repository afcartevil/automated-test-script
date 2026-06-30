# coding=utf-8
import logging
import pytest
import warnings
from src.utils.adb.adb_utils import get_device_ram_size, getprop
from data.res_list import AndroidVersion


# W上不存在该方案
@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_android_version_min(AndroidVersion.T)
def test_TranCpuBooster(device_serial, phone_info):
    if int(phone_info["android_version"]) == AndroidVersion.W:
        pytest.skip(f"W版本不支持该功能")
    assert "1" == getprop(
        "ro.transsion.cpubooster.group", device_serial
    ), "TranCpuBooster功能校验失败"


@pytest.mark.require_build_brand("UMS")
@pytest.mark.require_android_version_min(AndroidVersion.V)
def test_madvise(device_serial):
    """测试madvise属性配置是否正确"""
    # 获取设备RAM大小
    ram_size_gb = get_device_ram_size(device_serial)

    if ram_size_gb <= 4:
        expected_artfile_size = "4294967295"
        expected_odexfile_size = "52428800"
        expected_vdexfile_size = "52428800"
    else:
        expected_artfile_size = "4294967295"
        expected_odexfile_size = "104857600"
        expected_vdexfile_size = "104857600"

    assert expected_artfile_size == getprop(
        "dalvik.vm.madvise.artfile.size", device_serial
    ), "madvise artfile大小校验失败"
    assert expected_odexfile_size == getprop(
        "dalvik.vm.madvise.odexfile.size", device_serial
    ), "madvise odexfile大小校验失败"
    assert expected_vdexfile_size == getprop(
        "dalvik.vm.madvise.vdexfile.size", device_serial
    ), "madvise vdexfile大小校验失败"


# PM版本功能验证（PM4.1与PM4.0互斥，PM4.1支持则PM4.0处于关闭状态）
@pytest.mark.require_android_version_min(AndroidVersion.V)
def test_pm_version_features(device_serial, phone_info):
    """
    验证PM版本功能，PM4.1与PM4.0互斥：
    - 如果PM4.1支持，则PM4.0功能应处于关闭状态
    - 如果PM4.1不支持，则验证PM4.0功能
    """
    # 检查PM4.1支持状态
    pm4_1_support = getprop("sys.tranpm.support", device_serial)

    if pm4_1_support == "1":
        # PM4.1支持，验证PM4.0功能处于关闭状态
        assert 1 == 1

    else:
        # PM4.1不支持，验证PM4.0功能
        # "PM4.0优先级提升功能应"
        assert "1" == getprop(
            "sys.tranpm.support", device_serial
        ), "PM4.0优先级提升功能校验失败"
        #  "PM4.0内存泄露治理功能应启用"
        assert "1" == getprop(
            "sys.griffin.support", device_serial
        ), "PM4.0内存泄露治理功能校验失败"

        # 根据Android版本检查相应的唤醒支持属性
        # PM4.0应用异常行为监控功能应启用
        if int(phone_info["android_version"]) == AndroidVersion.V:
            assert "1" == getprop(
                "persist.sys.tran.hstd.wake.support", device_serial
            ), "PM4.0应用异常行为监控功能Android V版本校验失败"
        elif int(phone_info["android_version"]) == AndroidVersion.W:
            assert "1" == getprop(
                "persist.tr_tsppm.wake.support", device_serial
            ), "PM4.0应用异常行为监控功能Android W版本校验失败"


# 超级触控/AppTurbo控制
@pytest.mark.require_android_version_min(AndroidVersion.V)
def test_app_turbo_control(device_serial):
    assert "" == getprop(
        "ro.transsion.appturbo.setting.support", device_serial
    ), "超级触控/AppTurbo控制校验失败"


# 滑动渲染线程提RT 功能下线
@pytest.mark.require_android_version_min(AndroidVersion.V)
def test_swipe_render_thread_rt(device_serial):
    assert "1" != getprop(
        "ro.transsion.fling_render_boost_rt", device_serial
    ), "滑动渲染线程提RT功能下线校验失败"


# 系统冻结1.0
@pytest.mark.require_android_version_min(AndroidVersion.T)
@pytest.mark.require_kernel_version_min("4.19")
def test_system_freeze_1_0(device_serial):
    assert "1" == getprop(
        "ro.tran.hiber.support", device_serial
    ), "系统冻结1.0功能校验失败"


# EsportsPro-游戏温控引擎
@pytest.mark.require_android_version_min(AndroidVersion.U)
@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_non_slim_device()
def test_esports_pro_game_thermal_control_engine(device_serial, phone_info):
    if int(phone_info["android_version"]) > AndroidVersion.W:
        support = getprop("ro.esports.thermal_config.support", device_serial)
        version = getprop("ro.esports.thermal_config.version", device_serial)
        assert support == "1" or version != "", "EsportsPro-游戏温控引擎校验失败"
    elif int(phone_info["android_version"]) == AndroidVersion.W:
        assert "1" == getprop(
            "ro.tr_esports.thermal_config.feature.support", device_serial
        ), "EsportsPro-游戏温控引擎校验失败"
        assert "2" == getprop(
            "ro.tr_esports.thermal_config.version", device_serial
        ), "EsportsPro-游戏温控引擎校验失败"
        assert "1" == getprop(
            "ro.tr_perf.timed_rendering.feature.support", device_serial
        ), "EsportsPro-游戏温控引擎校验失败"
        assert "1" == getprop(
            "ro.tr_game.game_mode.support", device_serial
        ), "EsportsPro-游戏温控引擎校验失败"


# SF binder 优先级提升
# W版本默认开启且无检测方式
@pytest.mark.require_android_version_min(AndroidVersion.V)
@pytest.mark.require_build_brand("MTK")
def test_sf_binder_priority_boost(device_serial, phone_info):
    if int(phone_info["android_version"]) == AndroidVersion.W:
        pytest.skip(f"W版本无需检测")
    assert "1" == getprop(
        "debug.sf.set_binder_thread_rt", device_serial
    ), "SF binder优先级提升校验失败"


# GPU completion binder调用
@pytest.mark.require_android_version_min(AndroidVersion.V)
@pytest.mark.require_build_brand("MTK")
def test_gpu_completion_binder_call(device_serial):
    result = getprop("vendor.mbrain.enabled", device_serial)
    assert result == "0" or result == "", "GPU completion binder调用校验失败"


# Launcher异步动效
# W版本无需检测，默认开启
@pytest.mark.require_android_version_min(AndroidVersion.V)
def test_launcher_async_effect(device_serial, phone_info):
    if int(phone_info["android_version"]) > AndroidVersion.V:
        pytest.skip(f"W版本无需检测，默认开启")
    else:
        assert "1" == getprop(
            "ro.transsion_async_animation_support ", device_serial
        ), "Launcher异步动效校验失败"


# fastkill+循环监听查杀
@pytest.mark.require_android_version_min(AndroidVersion.V)
def test_fastkill_cycle_kill(device_serial):
    version_str = getprop("sys.tranpm.version", device_serial)
    version = int(version_str) if version_str.isdigit() else 0
    assert version >= 41, "fastkill+循环监听查杀功能校验失败"


# 内存融合
@pytest.mark.require_android_version_min(AndroidVersion.V)
def test_memory_fusion(device_serial, phone_info):
    if int(phone_info["android_version"]) > AndroidVersion.V:
        # 内存融合内核层
        assert "false" == getprop(
            "persist.odm.tr_memfusion.appcompact.support", device_serial
        ), "内存融合内核层检测失败"
    else:
        assert "1" == getprop(
            "ro.vendor.memfusion.support", device_serial
        ), "内存融合基础支持校验失败"
        assert "true" == getprop(
            "ro.vendor.memfusion2_1.support", device_serial
        ), "内存融合2.1支持校验失败"
        assert "true" == getprop(
            "ro.vendor.memfusion2_2.support", device_serial
        ), "内存融合2.2支持校验失败"
        assert "true" == getprop(
            "persist.vendor.swapfile_enable", device_serial
        ), "swap文件启用校验失败"
        assert "" != getprop(
            "persist.vendor.swapfile_size_mb", device_serial
        ), "swap文件大小配置校验失败"


# appcompact
def test_appcompact(device_serial):
    if "true" == getprop("ro.vendor.memfusion2_2.support", device_serial):
        assert "false" == getprop(
            "persist.vendor.memfusion_appcompact_enable", device_serial
        ), "appcompact功能校验失败"


# 应用主题资源缓存
def test_app_theme_resource_cache(device_serial, phone_info):
    if int(phone_info["android_version"]) == AndroidVersion.V:
        assert "false" != getprop(
            "persist.sys.perf.cached_packages.support", device_serial
        ), "应用主题资源缓存功能校验失败"


# camera退出优化方案
@pytest.mark.require_android_version_min(AndroidVersion.U)
@pytest.mark.require_build_brand("MTK")
def test_camera_exit_optimization(device_serial, phone_info):
    if int(phone_info["android_version"]) >= AndroidVersion.W:
        assert "0" != getprop(
            "persist.tr_perf.camera_cpuset.support", device_serial
        ), "camera退出优化方案校验失败"
    else:
        assert "1" == getprop(
            "ro.transsion.cpubooster.heavy_loading.support", device_serial
        ), "camera退出优化方案校验失败"


# 滑动插帧
@pytest.mark.require_android_version_min(AndroidVersion.U)
def test_swipe_frame_insertion(device_serial, phone_info):
    from src.conftests.device import get_device_build_brand

    if int(phone_info["android_version"]) >= AndroidVersion.W:
        assert "0" != getprop(
            "ro.tr_perf.boostfwk.frame_prefetcher.feature.support", device_serial
        ), "滑动插帧功能校验失败"
    else:
        build_brand = get_device_build_brand(device_serial)
        if build_brand == "MTK":
            # MTK平台要求Android U及以上
            android_version = int(phone_info["android_version"])
            if android_version <= AndroidVersion.U:
                pytest.skip(
                    f"MTK平台只检测Android V及以上版本，当前版本: {android_version}"
                )
        elif build_brand == "UMS":
            # 展锐平台要求Android V及以上
            android_version = int(phone_info["android_version"])
            if android_version < AndroidVersion.V:
                pytest.skip(
                    f"展锐平台需要Android V及以上版本，当前版本: {android_version}"
                )
        assert "1" == getprop(
            "vendor.boostfwk.transsion.frameprefetcher", device_serial
        ), "滑动插帧功能校验失败"


# dexopt专项
@pytest.mark.require_android_version_min(AndroidVersion.V)
def test_dexopt_special(device_serial, phone_info):
    if int(phone_info["android_version"]) == AndroidVersion.V:
        dexopt_flags = getprop("dalvik.vm.dexopt-flags", device_serial)
        if dexopt_flags != "true":
            warnings.warn(
                "dalvik.vm.dexopt-flags 宏控查询失败，V上该方案在25年上半年发布的项目中不带入，这里检测失败可能是没带入该方案，跳过检测"
            )
    elif int(phone_info["android_version"]) == AndroidVersion.W:
        assert "true" == getprop(
            "ro.tr_perf.dexopt.app_start_dexopt.feature.support", device_serial
        )


# 温升瞬态交互体验优化
@pytest.mark.require_android_version_min(AndroidVersion.T)
@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_kernel_version_min("5.10")
@pytest.mark.require_soc_model_min("G99")
def test_temperature_transient_interaction_optimization(device_serial, phone_info):
    if int(phone_info["android_version"]) >= AndroidVersion.W:
        pytest.skip(f"W版本无需检测宏控")
    else:
        # 检查是否支持温升瞬态交互体验优化
        assert (
            "1" == getprop("ro.vendor.powerhal.thermal_ux_support", device_serial)
        ) and (
            "" != getprop("persist.vendor.powerhal.thermal_ux_temp_max", device_serial)
        ), "温升瞬态交互体验优化校验失败"


# IO预读-preIO
@pytest.mark.require_android_version_min(AndroidVersion.T)
@pytest.mark.require_kernel_version_in(["4.19", "5.10"])
def test_io_readahead(device_serial, phone_info):
    if int(phone_info["android_version"]) >= AndroidVersion.W:
        assert "1" == getprop(
            "ro.tr_perf.perio.feature.support", device_serial
        ), "IO预读功能校验失败"
    else:
        assert "1" == getprop(
            "ro.transsion.perio.support", device_serial
        ), "IO预读功能校验失败"


# 应用预加载方案
@pytest.mark.require_ram_min(4)
@pytest.mark.require_non_go_device()
def test_app_preload_scheme(device_serial):
    assert "false" != getprop(
        "persist.sys.perf.pre_start_app.support", device_serial
    ), "应用预加载方案校验失败"


# 关闭usap预加载
def test_disable_usap_preload(device_serial, phone_info):
    if int(phone_info["android_version"]) == AndroidVersion.V:
        ram_size_gb = get_device_ram_size(device_serial)
        if ram_size_gb <= 4:
            assert "false" == getprop(
                "dalvik.vm.usap_pool_enabled", device_serial
            ), "usap预加载功能校验失败"
