"""通过 adb 直接打开系统设置中的指定页面。"""
"""通过 adb 直接打开系统设置中的 SIM 卡网络设置页。"""

import subprocess
import time

# 来自 Settings/AndroidManifest.xml：
# - action: android.settings.MOBILE_NETWORK_LIST
MOBILE_NETWORK_LIST_ACTION = "android.settings.MOBILE_NETWORK_LIST"
NETWORK_OPERATOR_ACTION = "android.settings.NETWORK_OPERATOR_SETTINGS"
DEVICE_INFO_SETTINGS_ACTION = "android.settings.DEVICE_INFO_SETTINGS"
RADIO_INFO_COMPONENT = "com.android.phone/.settings.RadioInfo"
MORE_SECURITY_SETTINGS_ACTION = "com.android.settings.security.SECURITY_ADVANCED_SETTINGS"
ICC_LOCK_SETTINGS_COMPONENT = "com.android.settings/.Settings$IccLockSettingsActivity"
TRAN_BLOCK_SETTINGS_COMPONENT = (
    "com.android.server.telecom/"
    "com.transsion.server.telecom.settings.os14.TranBlockSettingsActivity"
)
SETTINGS_PACKAGES = ("com.android.settings", "com.google.android.settings")


# 方法说明：执行 adb 子命令（工具方法，不进入具体界面）。
def _run_adb(device_id: str, *args: str, timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["adb", "-s", device_id, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


# 方法说明：结束设置进程（工具方法，不进入具体界面）。
def _kill_settings(device_id: str) -> bool:
    if not device_id:
        return False
    try:
        for package in SETTINGS_PACKAGES:
            _run_adb(device_id, "shell", "am", "force-stop", package, timeout=10)
        return True
    except Exception:
        return False

# 手动命令: adb -s <device_id> shell am start -a android.settings.MOBILE_NETWORK_LIST
# 方法说明：进入界面「SIM 卡网络设置（列表页）」。
def enter_sim_network_settings_by_adb(device_id: str) -> bool:
    """
    通过 adb 进入「SIM 卡网络设置」页面。

    参数:
        device_id: 设备 adb 序列号。

    返回:
        成功 True，失败 False。
    """
    if not device_id:
        return False

    try:
        if not _kill_settings(device_id):
            return False
        result = _run_adb(
            device_id,
            "shell",
            "am",
            "start",
            "-a",
            MOBILE_NETWORK_LIST_ACTION,
        )
        return result.returncode == 0
    except Exception:
        return False


# 手动命令: adb -s <device_id> shell am start -a android.settings.NETWORK_OPERATOR_SETTINGS --ei android.provider.extra.SUB_ID <sub_id>
# 方法说明：进入界面「指定 SIM 卡子界面（移动网络详情页）」。
def enter_sim_sub_settings_by_adb(device_id: str, sub_id: int) -> bool:
    """
    通过 adb 直接进入指定 SIM 卡子界面（移动网络详情页）。

    参数:
        device_id: 设备 adb 序列号。
        sub_id: 目标 SIM 的 Subscription ID。

    返回:
        成功 True，失败 False。
    """
    if not device_id:
        return False

    try:
        sub_id = int(sub_id)
    except (TypeError, ValueError):
        return False

    try:
        if not _kill_settings(device_id):
            return False
        result = _run_adb(
            device_id,
            "shell",
            "am",
            "start",
            "-a",
            NETWORK_OPERATOR_ACTION,
            "--ei",
            "android.provider.extra.SUB_ID",
            str(sub_id),
        )
        return result.returncode == 0
    except Exception:
        return False


# 手动命令: adb -s <device_id> shell am start -a android.settings.DEVICE_INFO_SETTINGS
# 方法说明：进入界面「我的手机」（Settings$MyDeviceInfoActivity）。
def enter_my_phone_settings_by_adb(device_id: str) -> bool:
    """
    通过 adb 直接进入「我的手机」页面。

    参数:
        device_id: 设备 adb 序列号。

    返回:
        成功 True，失败 False。
    """
    if not device_id:
        return False

    try:
        if not _kill_settings(device_id):
            return False
        result = _run_adb(
            device_id,
            "shell",
            "am",
            "start",
            "-a",
            DEVICE_INFO_SETTINGS_ACTION,
        )
        return result.returncode == 0
    except Exception:
        return False


# 手动命令: adb -s <device_id> shell am start -n com.android.phone/.settings.RadioInfo
# 方法说明：进入界面「手机信息」（com.android.phone.settings.RadioInfo）。
# 设置路径：我的手机 → 手机信息；可先调用 enter_my_phone_settings_by_adb 打开「我的手机」。
def enter_phone_info_settings_by_adb(device_id: str) -> bool:
    """
    通过 adb 直接进入「手机信息」页面。

    参数:
        device_id: 设备 adb 序列号。

    返回:
        成功 True，失败 False。
    """
    if not device_id:
        return False

    try:
        if not _kill_settings(device_id):
            return False
        result = _run_adb(
            device_id,
            "shell",
            "am",
            "start",
            "-n",
            RADIO_INFO_COMPONENT,
        )
        return result.returncode == 0
    except Exception:
        return False


# 手动命令: adb -s <device_id> shell am start -a com.android.settings.security.SECURITY_ADVANCED_SETTINGS
# 方法说明：进入界面「更多安全设置」。
def enter_more_security_settings_by_adb(device_id: str) -> bool:
    """
    通过 adb 直接进入「更多安全设置」页面。

    参数:
        device_id: 设备 adb 序列号。

    返回:
        成功 True，失败 False。
    """
    if not device_id:
        return False

    try:
        if not _kill_settings(device_id):
            return False
        result = _run_adb(
            device_id,
            "shell",
            "am",
            "start",
            "-a",
            MORE_SECURITY_SETTINGS_ACTION,
        )
        return result.returncode == 0
    except Exception:
        return False


def _start_settings_component(device_id: str, component: str) -> subprocess.CompletedProcess:
    """
    启动 Settings 子 Activity。组件名含 $ 时须加引号，避免设备 shell 把 $xxx 当变量展开。
    """
    safe = component.replace("'", "'\\''")
    return _run_adb(
        device_id,
        "shell",
        f"am start -n '{safe}'",
        timeout=20,
    )


# 手动命令: adb -s <device_id> shell am start -n 'com.android.settings/.Settings$IccLockSettingsActivity'
# 方法说明：进入界面「SIM卡锁定」。
def enter_sim_pin_lock_settings_by_adb(device_id: str) -> bool:
    """
    通过 adb 直接进入「SIM卡锁定」页面（IccLockSettings）。

    参数:
        device_id: 设备 adb 序列号。

    返回:
        成功 True，失败 False。
    """
    if not device_id:
        return False

    try:
        if not _kill_settings(device_id):
            return False
        result = _start_settings_component(device_id, ICC_LOCK_SETTINGS_COMPONENT)
        output = f"{result.stdout or ''}{result.stderr or ''}"
        if result.returncode != 0 or "Error" in output:
            return False
        return ICC_LOCK_SETTINGS_COMPONENT.split("/")[-1] in output or "Starting:" in output
    except Exception:
        return False


# 手动命令:
# adb -s <device_id> shell am start -n
# com.android.server.telecom/com.transsion.server.telecom.settings.os14.TranBlockSettingsActivity
# 方法说明：进入界面「骚扰拦截」。
def enter_harassment_block_settings_by_adb(device_id: str) -> bool:
    """
    通过 adb 直接进入「骚扰拦截」页面。

    参数:
        device_id: 设备 adb 序列号。

    返回:
        成功 True，失败 False。
    """
    if not device_id:
        return False

    try:
        _kill_settings(device_id)
        _run_adb(device_id, "shell", "am", "force-stop", "com.android.server.telecom", timeout=10)
        result = _run_adb(
            device_id,
            "shell",
            "am",
            "start",
            "-n",
            TRAN_BLOCK_SETTINGS_COMPONENT,
        )
        if result.returncode != 0:
            return False
        time.sleep(1.0)
        return True
    except Exception:
        return False
