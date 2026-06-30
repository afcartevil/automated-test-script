# coding=utf-8
import pytest
import warnings
from src.utils.adb.adb_utils import get_device_ram_size, getprop
from data.res_list import AndroidVersion

@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_kernel_version_min("5.00")
@pytest.mark.require_android_version_min(AndroidVersion.V)
def test_kernel_sbe_version(device_serial ):
    """MTK kernel版本对应sbe版本校验"""
    if getprop("vendor.boostfwk.version", device_serial) != "4":
        pytest.skip(f"wbs修改验证结果，W新平台返回4，W旧平台(如g99,g85):返回值跟上一代平台一致，由于当前无法判断项目是否是新平台，WBS检查项跳过")
    # assert getprop("vendor.boostfwk.version", device_serial) in {"2", "4"}, "SBE版本校验失败"
    # wbs修改为W新平台返回4，W旧平台(如g99,g85):返回值跟上一代平台一致，由于当前无法判断项目是否是新平台，WBS检查项跳过
    
@pytest.mark.require_build_brand("MTK")
def test_aegean_cloud_control(device_serial, phone_info):
    """异常APP退后台30分钟查杀方案"""
    # 判断版本getprop ro.build.version.release
    # version = getprop("ro.build.version.release", device_serial)
    if int(phone_info["android_version"]) == AndroidVersion.V:
        assert getprop("persist.sys.tran.aegean.enable", device_serial) == "1", "异常APP退后台30分钟查杀方案Android V版本校验失败"
    if int(phone_info["android_version"]) == AndroidVersion.W:
        assert getprop("persist.tr_perf.aegean.support", device_serial) == "1", "异常APP退后台30分钟查杀方案Android W版本校验失败"

@pytest.mark.require_build_brand("MTK")
def test_recent_task_priority(device_serial):
    """近期任务前4个提升adj增强保活"""
    assert getprop("persist.sys.apm.recent_keep_alive_support", device_serial) != "0", "近期任务前4个提升adj增强保活校验失败"

# W默认打开
@pytest.mark.require_build_brand("MTK")
def test_powerhal_encryption(device_serial, phone_info):
    """PowerHal加密校验"""
    if int(phone_info["android_version"]) == AndroidVersion.V:
        assert getprop("ro.vendor.powerhal.encode", device_serial) == "1", "PowerHal加密校验失败"

# W默认打开
@pytest.mark.require_build_brand("MTK")
def test_powerhal_cloud_control(device_serial, phone_info):
    """powerhal云控检测"""
    if int(phone_info["android_version"]) == AndroidVersion.V:
        assert getprop("ro.vendor.powerhal.cloud", device_serial) == "1", "powerhal云控检测失败"

# gms 首次开机后dexopt
# W上不存在该方案
def test_first_boot_dexopt(device_serial, phone_info):
    """首次开机后dexopt"""
    if int(phone_info["android_version"]) == AndroidVersion.V:
        assert getprop("ro.transsion.enable_gms_secondary_dex2oat", device_serial) == "true", "首次开机后dexopt校验失败"

@pytest.mark.require_build_brand("MTK")
def test_topapp_uclamp_setting(device_serial):
    """TOPAPP cgroup uclamp设置校验"""
    assert getprop("ro.transsion.feature.top_app_uclamp.suppor", device_serial) != "false", "TOPAPP cgroup uclamp设置校验失败"


def test_animation_optimization(device_serial, phone_info):
    """滑动帧间距"""
    if int(phone_info["android_version"]) == AndroidVersion.V:
        assert getprop("persist.sys.opt.animation_distance", device_serial) == "true", "滑动帧间距优化校验失败"
    elif int(phone_info["android_version"]) == AndroidVersion.W:
        assert getprop("persist.tr_perf.opt_animation_distance.feature.support", device_serial) == "true", "滑动帧间距优化校验失败"

@pytest.mark.require_build_brand("MTK")
def test_accessibility_mode(device_serial, phone_info):
    """无障碍模式优化"""
    if phone_info["android_version"] == AndroidVersion.V:
        assert getprop("ro.transsion.feature.systemserver.rt", device_serial) == "true", "无障碍模式优化校验失败"
    elif phone_info["android_version"] == AndroidVersion.W:
        assert getprop("ro.tr_perf.system_server.sched_rt.feature.support", device_serial) == "true", "无障碍模式优化校验失败"

def test_launcher_systemui_systemgc_bind_small_core(device_serial, phone_info):
    """launcher/systemui/systemGC绑小核"""
    if int(phone_info["android_version"]) == AndroidVersion.V:
        assert getprop("ro.transsion.gc_group_opt.support", device_serial) == "true", "launcher/systemui/systemGC绑小核优化校验失败"
    elif int(phone_info["android_version"]) == AndroidVersion.W:
        assert getprop("persist.sys.perf.gc_bg.support", device_serial) != "false", "launcher/systemui/systemGC绑小核优化校验失败"

# vmheap参数确认
def test_vmheap_parameter_confirmation(device_serial, phone_info):
    """vmheap参数确认"""
    android_version_int = int(phone_info["android_version"])
    
    if android_version_int >= AndroidVersion.U:
        if get_device_ram_size(device_serial) in {"6", "8", "12"}:
            heaptargetutilization = getprop("dalvik.vm.heaptargetutilization", device_serial)
            heapmaxfree = getprop("dalvik.vm.heapmaxfree", device_serial)
            heapminfree = getprop("dalvik.vm.heapminfree", device_serial)
            
            if not (heaptargetutilization == "0.75" and
                    heapmaxfree == "16m" and
                    heapminfree == "16m"):
                warnings.warn(f"Android U+版本vmheap参数校验失败: "
                            f"heaptargetutilization={heaptargetutilization}(期望0.75), "
                            f"heapmaxfree={heapmaxfree}(期望16m), "
                            f"heapminfree={heapminfree}(期望16m), "
                            f"该参数值可在项目上自行调整，未强行要求按照wbs中设定值检测，跳过检测")
    elif android_version_int < AndroidVersion.U:
        if get_device_ram_size(device_serial) in {"6", "8"}:
            heaptargetutilization = getprop("dalvik.vm.heaptargetutilization", device_serial)
            heapmaxfree = getprop("dalvik.vm.heapmaxfree", device_serial)
            heapminfree = getprop("dalvik.vm.heapminfree", device_serial)
            
            if not (heaptargetutilization == "0.5" and
                    heapmaxfree == "16m" and
                    heapminfree == "32m"):
                warnings.warn(f"Android U-版本vmheap参数校验失败: "
                            f"heaptargetutilization={heaptargetutilization}(期望0.5), "
                            f"heapmaxfree={heapmaxfree}(期望16m), "
                            f"heapminfree={heapminfree}(期望32m), "
                            f"该参数值可在项目上自行调整，未强行要求按照wbs中设定值检测，跳过检测")


# TranFling动效调整
@pytest.mark.require_android_version_min(AndroidVersion.V)
@pytest.mark.require_build_brand("MTK")
@pytest.mark.require_ram_min(4.0)
@pytest.mark.require_non_slim_device()
@pytest.mark.require_non_go_device()
def test_tranfling_motion_effect_adjustment(device_serial, phone_info): 
    if int(phone_info["android_version"]) == AndroidVersion.W:
        assert "1" == getprop("ro.tran.fling.support", device_serial), "TranFling动效调整校验失败"
    elif int(phone_info["android_version"]) == AndroidVersion.V:
        if "1" != getprop("ro.tran.fling.support", device_serial):
            warnings.warn(f"TranFling动效调整校验失败: Android V版本期望ro.tran.fling.support=1, 实际值={getprop('ro.tran.fling.support', device_serial)}，可能原因是早期V版本未启用该功能，跳过检测")