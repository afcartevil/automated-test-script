from math import log
import os
import subprocess
import time
import logging
import re

from src.utils.decorator.decorator import adb_repeat
from data.res_list import APP_DIRS

"""
执行命令
"""
import subprocess
import shlex
from typing import Union, Dict, Optional, List


# 一般尝试3次
# 当期望结果就是失败时，可以在方法调用时加上参数 execute_command(cmd, no_retry=True) 跳过重复执行
@adb_repeat(max_attempts=3)
def execute_command(
    command: Union[str, list],
    timeout: Optional[float] = None,
    shell: bool = False,
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
) -> Dict[str, Union[bool, str, int, Exception]]:
    """
    执行 Shell 命令并返回结构化结果

    :param command: 要执行的命令（字符串或参数列表）
    :param timeout: 超时时间（秒）
    :param shell: 是否通过 Shell 执行（谨慎使用）
    :param cwd: 工作目录路径
    :param env: 自定义环境变量字典
    :return: 包含执行结果和元数据的字典

    返回结构:
    {
        "success": bool,           # 是否成功执行 (返回码为0)
        "output": str,             # 标准输出内容 (已去尾随换行)
        "error": str,              # 标准错误内容 (已去尾随换行)
        "return_code": int,        # 进程返回码
        "exception_type": str,     # 异常类型名称 (如有)
        "exception_msg": str      # 异常消息 (如有)
    }
    """
    result_template = {
        "success": False,
        "output": "",
        "error": "",
        "return_code": -1,
        "exception_type": "",
        "exception_msg": "",
    }

    try:
        # 统一处理命令格式
        if isinstance(command, str) and not shell:
            command = shlex.split(command)  # 安全拆分命令参数

        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=shell,
            timeout=timeout,
            cwd=cwd,
            env=env,
            check=True,  # 自抛异常
            text=True,  # 返回字符串而非字节
        )

        # 处理输出内容
        result_template.update(
            {
                "success": process.returncode == 0,
                "output": process.stdout.strip(),
                "error": process.stderr.strip(),
                "return_code": process.returncode,
            }
        )

    except subprocess.CalledProcessError as e:
        # 当 check=True 时可能抛出（但此处已禁用）
        result_template.update(
            {
                "exception_type": type(e).__name__,
                "exception_msg": str(e),
                "output": e.stdout.strip() if e.stdout else "",
                "error": e.stderr.strip() if e.stderr else "",
                "return_code": e.returncode,
            }
        )
    except subprocess.TimeoutExpired as e:
        result_template.update(
            {
                "exception_type": type(e).__name__,
                "exception_msg": f"Command timed out after {timeout} seconds",
                "error": f"Timeout after {timeout}s",
            }
        )
    except FileNotFoundError as e:
        result_template.update(
            {
                "exception_type": "CommandNotFound",
                "exception_msg": f"Command not found: {command[0] if isinstance(command, list) else command.split()[0]}",
            }
        )
    except Exception as e:
        result_template.update(
            {"exception_type": type(e).__name__, "exception_msg": str(e)}
        )

    return result_template


def adb_shell(device_serial, shell_command, timeout: Optional[float] = 30, no_retry=False):
    """执行设备侧 shell 命令并返回 execute_command 的结构化结果。"""
    if not device_serial:
        raise ValueError("device_serial is required")

    cmd = f"adb -s {device_serial} shell {shell_command}"
    return execute_command(cmd, timeout=timeout, no_retry=no_retry)


"""
判断apk是否存在
"""


def is_apk_exist(device_serial, apk_name):
    cmp = f"adb -s {device_serial} shell find {' '.join(map(lambda x: f'/{x}', APP_DIRS))} -name {apk_name}"
    # 执行命令 并判断其是否存在
    res = execute_command(cmp, no_retry=True)
    if res["output"] and "/" in res["output"]:
        if is_file_exist(device_serial, res["output"]):
            logging.info(f"apk_path：{res['output']} is exist")
            return True
    return False


"""
判断file_path是否存在
"""


def is_file_exist(device_serial, file_path):
    cmp = "adb -s " + device_serial + " shell test -e " + file_path
    # 执行命令 并判断其是否存在
    exite = execute_command(cmp, no_retry=True)
    return True if exite["success"] else False


def find_file_in_trregion_etc_asset(device_serial, file_name):
    cmp = (
        "adb -s "
        + device_serial
        + " shell find /tr_region/etc/asset -name "
        + file_name
    )
    # 执行命令 并判断其是否存在
    res = execute_command(cmp)

    return file_name in res["output"] if res["success"] else False


"""
确保手机所有安全patch属性一致
"""


def is_uniform_patchtime(device_serial):
    # 获取所有安全patch属性
    cmd = "adb -s " + device_serial + " shell getprop | grep security_patch"
    res = execute_command(cmd)
    if res["success"]:
        # 提取属性值
        patch_times = [line.split(": ")[1] for line in res["output"].split("\n")]
        return patch_times[0][1:-1] if len(set(patch_times)) == 1 else False
    else:
        return False


"""
查询 feature（按设备缓存 pm list features 结果，避免重复 ADB 与 grep 重试）
"""

_device_features_cache: Dict[str, List[str]] = {}


def _get_device_features_list(device_serial: Optional[str]) -> List[str]:
    cache_key = device_serial or ""
    if cache_key in _device_features_cache:
        return _device_features_cache[cache_key]

    if device_serial:
        cmd = f"adb -s {device_serial} shell pm list features"
    else:
        logging.warning("未指定设备序列号，默认使用第一个设备")
        cmd = "adb shell pm list features"

    res = execute_command(cmd, no_retry=True)
    if not res["success"] or not res["output"]:
        return []

    lines = [line.strip() for line in res["output"].splitlines() if line.strip()]
    _device_features_cache[cache_key] = lines
    return lines


def get_feature(device_serial, feature_name):
    if not feature_name:
        return None

    for line in _get_device_features_list(device_serial):
        if feature_name in line:
            return line
    return None


def is_google_one_product(device_serial):
    result = get_feature(
        device_serial, "com.google.android.feature.ANDROID_ONE_EXPERIENCE"
    )
    return False if result == None else True


"""
检查是否是root版本
"""


def is_root_product(device_serial):
    result = getprop("ro.build.type", sn=device_serial)
    if result == "userdebug" or result == "user_root" or result == "eng":
        return True
    else:
        return False


"""
获取属性
"""


def getprop(prop_key, sn=None):
    if sn:
        cmd = f"adb -s {sn} shell getprop {prop_key}"
    else:
        logging.warning("未指定设备序列号，默认使用第一个设备")
        cmd = f"adb shell getprop {prop_key}"
    res = execute_command(cmd)
    return res["output"]


def get_device_android_version(device_serial):
    """获取设备 Android 版本"""
    try:
        return getprop("ro.product.build.version.release", device_serial)
    except Exception:
        return 0

def get_device_android_version_sdk_full(device_serial):
    """获取设备 Android 版本"""
    try:
        return getprop("ro.build.version.sdk_full", device_serial)
    except Exception:
        return 0

def get_device_ram_size(device_serial):
    """获取设备 RAM 大小（GB，向上取整）"""
    try:
        result = execute_command(
            f"adb -s {device_serial} shell cat /proc/meminfo | grep MemTotal"
        )
        if result["success"] and result["output"]:
            mem_info = result["output"].strip().split()
            if len(mem_info) >= 2:
                mem_kb = int(mem_info[1])
                mem_gb = mem_kb / (1024 * 1024)
                integer_part = int(mem_gb)
                decimal_part = mem_gb - integer_part
                return integer_part + 1 if decimal_part >= 0.01 else integer_part
        return 0
    except Exception:
        return 0


def get_device_fps(device_serial):
    """获取设备支持的最大 fps"""
    cmd = f"adb -s {device_serial} shell dumpsys display | grep DisplayModeRecord"
    res = execute_command(cmd)
    fps_values = re.findall(r"fps=([0-9]+\.?[0-9]*)", res["output"])
    fps_numbers = [int(float(fps)) for fps in fps_values]
    return max(fps_numbers) if fps_numbers else 0


def get_tOS_version(device_serial):
    return getprop("ro.tranos.version", device_serial)

def get_tOS_version_number(device_serial):
    raw_tos_version = getprop("ro.tranos.version", device_serial).strip()
    tos_version_match = re.search(r"(\d+(?:\.\d+)+)", raw_tos_version)
    tos_version = tos_version_match.group(1) if tos_version_match else raw_tos_version
    return tos_version

def get_product_name_without_market(device_serial):
    return getprop("ro.product.name", device_serial).strip().split("-")[0]

def is_GO_device(device_serial):
    return getprop("ro.vendor.gmo.rom_optimize", device_serial) == 1


def is_slim_device(device_serial):
    return getprop("ro.tr_build.device.type", device_serial) == "slim"


def is_gmse_plus_device(device_serial):
    """是否为 GMSE+（GMS Express Plus）项目。"""
    return bool(
        get_feature(device_serial, "com.google.android.feature.GMSEXPRESS_PLUS_BUILD")
    )


def is_cuttlefish_device(device_serial):
    """是否为 CuttleFish 类虚拟设备（vendor.model 含参考串且 product.device 一致）。"""
    cuttlefish_vendor_model = "MTK arm64 Cuttlestone 64-bit only"
    cuttlefish_product_device = "cs_arm64_only"
    vendor_model = (getprop("ro.product.vendor.model", device_serial) or "").strip()
    product_device = (getprop("ro.product.device", device_serial) or "").strip()
    return (
        cuttlefish_vendor_model in vendor_model
        and product_device == cuttlefish_product_device
    )


def get_soc_paltform(device_serial):
    return getprop("ro.board.platform", device_serial)


def get_kernel_version(device_serial):
    return getprop("ro.kernel.version", device_serial)


"""
获取手机sn
"""


def get_first_sn():
    res = execute_command("adb devices")["output"]
    try:
        sn = res.split("\n")[1].split("\t")[0]
        return sn
    except Exception:
        return None


# 判断是否是tssi项目
def is_tssi_product(device_serial):
    res = getprop("ro.product.tran.version.release", sn=device_serial)
    if res == "":
        return False
    else:
        return True


"""
获取手机资源到指定路径
需带上文件名
若指定路径有资源，会被覆盖
"""


def pull_file(device_serial, remote_path, local_path):
    # 先检查指定位置是否有资源避免冲突
    if os.path.exists(local_path):
        os.remove(local_path)
    cmd = f"adb -s {device_serial} pull {remote_path} {local_path}"
    execute_command(cmd)
    # 检查指定资源是否存在
    if os.path.exists(local_path):
        return True
    else:
        return False


def ls_dir(device_serial, dir_name):
    cmd = f"adb -s {device_serial} shell ls {dir_name}"
    res = execute_command(cmd)
    if res["success"]:
        return res["output"].split("\n") if res["output"] != "" else []
    else:
        return None


def is_dir_exist(device_serial, path):
    cmd = f"adb -s {device_serial} shell test -d {path}"
    res = execute_command(cmd, no_retry=True)
    return res["success"]


def is_package_exist(device_serial, package_name):
    # 使用更可靠的包检测方法：直接使用pm path命令
    cmd = f"adb -s {device_serial} shell pm path {package_name}"
    res = execute_command(cmd, no_retry=True)
    # 如果命令成功执行并且输出包含package:前缀，说明包存在
    return res["success"] and "package:" in res["output"]


def get_apkpath_by_package(device_serial, package_name):
    cmd = f"adb -s {device_serial} shell pm path {package_name}"
    res = execute_command(cmd, no_retry=True)
    if res["success"]:
        return res["output"].split(":")[1].strip()
    else:
        return None


def adb_cat(device_serial, file_path):
    cmd = f"adb -s {device_serial} shell cat {file_path}"
    res = execute_command(cmd, no_retry=True)
    if res["success"]:
        return res["output"].strip()
    else:
        return None
    
def get_desktop_widget(device_serial):
    """
    获取桌面上摆放的widget
    """
    cmd = f"adb -s {device_serial} shell dumpsys appwidget "
    res = execute_command(cmd, no_retry=True)
    if not res['success']:
        return None
    widgets = res['output'].split('Widgets:')[1].split('Hosts:')[0].strip()
    widgets_list = re.findall(r"ComponentInfo\{(.*?)\}", widgets)
    logging.info(f"当前桌面上的widget列表: {widgets_list}")
    return widgets_list
    
def get_cmd_overlay_lookup(device_serial, string_type, string):
    """
    获取overlay value的值
    """
    cmd = f"adb -s {device_serial} shell cmd overlay lookup android android:" + string_type + "/" + string
    res = execute_command(cmd, no_retry=True)

    if not res['success']:
        return None

    string_value = res['output']
    return string_value

def get_dumpsys_package(device_serial, package_name, string):
    """
    获取 dumpsys package 的值
    """
    cmd = f"adb -s {device_serial} shell dumpsys package " + package_name + " | grep " + string
    res = execute_command(cmd, no_retry=True)

    if not res['success']:
        return None

    string_value = res['output']
    return string_value

def get_dumpsys_role_adb(device_serial, role_holders_name):
    """
    获取 role_holders_name 的值，即获取角色持有者
    """
    cmd = f"adb -s {device_serial} shell cmd role get-role-holders " + role_holders_name
    res = execute_command(cmd, no_retry=True)

    if not res['success']:
        return None

    string_value = res['output']
    return string_value

def is_device_connect_wifi(device_serial):
    """
    判断设备是否连接wifi
    """
    cmd = f"adb -s {device_serial} shell dumpsys wifi"
    res = execute_command(cmd, no_retry=True)

    if not res['success']:
        return False

    if "Wi-Fi is disabled" in res['output']:
        return False
    else:
        return True

def adb_shell_settings_get_secure(device_serial, string_value):
    """
    获取 settings get secure 的值
    """
    cmd = f"adb -s {device_serial} shell settings get secure {string_value}"
    res = execute_command(cmd, no_retry=True)

    if not res['success']:
        return None

    string_value = res['output']
    return string_value

