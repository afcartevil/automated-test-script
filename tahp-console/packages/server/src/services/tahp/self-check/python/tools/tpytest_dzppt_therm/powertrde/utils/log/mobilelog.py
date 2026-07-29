import shutil
import subprocess
import time
import os
import zipfile
from datetime import datetime

import uiautomator2
from uiautomator2 import UiObject

from powertrde.env import ADB_EXE
from powertrde.framework.logs_protocol import logs_p
from powertrde.utils.trde import adb, logs
from powertrde.utils.trde.adb import exec_cmd_timeout, is_mtk, get_platform, is_qcom, is_sprd
from powertrde.framework.dependency.dependency_core import resolve, Depends

SPRD_DEVICE_LOG_DIRS = [
    '/data/minidump/*',
    '/data/minidump2/*',
    '/sdcard/minidump/*',
    '/sdcard/minidump2/*',
    '/sdcard/ylog/*',
    '/data/vendor/ylog/*',
    '/data/ylog/*',
    '/data/anr/*',
]
# 高通平台日志目录定义
QCOM_DEVICE_LOG_DIRS = [
    '/data/debuglogger/mobilelog/*',
    '/data/vendor/debuglogger/mdlog/*',
    '/data/vendor/debuglogger/netlog/*',
    '/data/vendor/debuglogger/connsyslog/bthci/*',
    '/data/vendor/radio/diag_logs/*',
    '/data/vendor/tombstones/*',
    '/data/anr/*',
    '/data/system/dropbox/*',
    '/data/vendor/ramdump/*',
    '/data/vendor/ssrdump/*',
    '/data/misc/qxdm/*',
]


# _sprd_android_log_flg = False

def adb_pull(sn, device_path, local_path):
    cmdline = [ADB_EXE, "-s", sn, "pull", device_path, local_path]
    exec_cmd_timeout(cmdline, timeout=60 * 30)


def reset_bugreport(sn):
    # 清理bugreport历史文件
    clear_bugreports(sn)
    # 重置Bugreport时间
    adb.reset_batterystats_for_bugreport(sn)


def create_platform_info_provider(sn: str):
    """创建平台信息提供者，直接使用adb模块的get_platform函数"""

    def _get_platform_info():
        return get_platform(sn)

    return _get_platform_info

def _stop_mtk_log(sn, u2d):
    adb.poweron_screen_and_unlock(sn)
    time.sleep(2)
    u2d.shell('am start -n com.debug.loggerui/com.debug.loggerui.MainActivity')

    u2d.xpath('//*[@text="DebugLoggerUI"]').wait(timeout=60)
    time.sleep(5)

    if u2d.xpath('//*[@text="MobileLog recording"]').exists:
        u2d.xpath('//*[@resource-id="com.debug.loggerui:id/startStopToggleButton"]').click()
        time.sleep(5)

    assert u2d.xpath('//*[@text="MobileLog stopped"]').exists

def _clear_and_start_mtk_log(sn, u2d, start_log_flag, wait_duration_after_log_start, set_log_size):
    adb.poweron_screen_and_unlock(sn)
    time.sleep(2)
    u2d.shell('am start -n com.debug.loggerui/com.debug.loggerui.MainActivity')
    time.sleep(3)

    # 无论之前是否开启，都清理手机log，避免很久以前开过，手机留着记录
    exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "am", "broadcast", "-a", "com.debug.loggerui.ADB_CMD", "-e"
                         , "cmd_name", "stop", "--ei", "cmd_target", "127", "--receiver-foreground",
                      "--receiver-include-background"])
    time.sleep(5)

    # 清理所有日志
    clear_button: UiObject = u2d(resourceId='com.debug.loggerui:id/clearLogImageButton')
    if not clear_button.wait(timeout=20):
        assert False, "Can not find clear log button from Debug Logger UI"
    clear_button.click()

    time.sleep(5)
    if u2d.xpath('//android.widget.ImageButton').wait(timeout=15):
        u2d.xpath('//android.widget.ImageButton').click()

    if u2d.xpath('//*[translate(@text, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")="clear all"]').wait(15):  #有时候点击完了，反应很慢才进入clear页面
        # logs.log("找到CLEAR ALL")
        time.sleep(2)
        u2d.xpath('//*[translate(@text, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")="clear all"]').click()
        u2d(text="OK").click()
        time.sleep(2)

    # 先设置日志大小
    exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "am", "broadcast", "-a", "com.debug.loggerui.ADB_CMD", "-e"
                         , "cmd_name", f"set_log_size_{set_log_size}", "--ei", "cmd_target", f"{start_log_flag}",
                      "--receiver-foreground",
                      "--receiver-include-background"])
    time.sleep(2)

    # 如果日志没有开启，则进行开启，adb shell am  broadcast -a com.debug.loggerui.ADB_CMD -e cmd_name start --ei cmd_target 5 --receiver-foreground  --receiver-include-background
    exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "am", "broadcast", "-a", "com.debug.loggerui.ADB_CMD", "-e"
                         , "cmd_name", "start", "--ei", "cmd_target", f"{start_log_flag}", "--receiver-foreground",
                      "--receiver-include-background"])
    time.sleep(wait_duration_after_log_start)


def _clear_and_start_sprd_log(sn, u2d, wait_duration_after_log_start):
    adb.poweron_screen_and_unlock(sn)
    time.sleep(2)
    rom_sz = adb.rom_size_MB(device_id=sn)
    sz = int(rom_sz / 2)

    # 清除日志
    for l in SPRD_DEVICE_LOG_DIRS:
        exec_cmd_timeout(f'rm {l} -rf')

    adb.poweron_screen_and_unlock(sn)
    time.sleep(3)
    u2d.shell('am start -n com.sprd.engineermode/.EngineerModeActivity')
    time.sleep(2)
    u2d.xpath('//android.widget.TextView[@text="DEBUG&LOG"]').click_exists(timeout=8)
    time.sleep(2)
    u2d.xpath('//android.widget.TextView[@text="YLog"]').click_exists(timeout=3)
    time.sleep(5)

    # 先清理
    if u2d.xpath('//*[@text="Stop"]').exists:
        u2d.xpath('//*[@text="Stop"]').click()
        time.sleep(2)
    u2d.xpath('//*[@content-desc="More options"]').click(timeout=3)
    time.sleep(2)
    u2d.xpath('//*[@text="Clear"]').click(timeout=15)
    time.sleep(2)

    u2d.xpath('//*[@text="OK"]').click(timeout=15)
    time.sleep(3)
    logs.log("完成日志清理")

    u2d.xpath('//*[@content-desc="More options"]').click(timeout=3)
    time.sleep(2)
    u2d.xpath('//*[@text="Custom"]').click(timeout=15)
    time.sleep(1)
    logs_enable = u2d.xpath('//*[@resource-id="com.sprd.logmanager:id/checkbox"]').all()
    for i, checkbox in enumerate(logs_enable):
        checked = checkbox.info.get('checked')
        if i == 0:
            if not checked:
                checkbox.click()
                time.sleep(2)
        else:
            if checked:
                checkbox.click()
                time.sleep(2)

    u2d.shell("input keyevent KEYCODE_BACK")
    time.sleep(1)

    u2d.xpath('//*[@text="Start"]').click_exists(timeout=5)
    time.sleep(wait_duration_after_log_start)


def _clear_and_start_qcom_log(sn, u2d, start_log_flag, wait_duration_after_log_start, set_log_size):
    adb.poweron_screen_and_unlock(sn)
    time.sleep(2)
    logs.log(f"执行清理log和启动log")
    #todo 暂时全部删除&开启所有日志
    u2d.shell('find /data/debuglogger/ -type f -delete')
    u2d.shell('find /data/vendor/debuglogger/ -type f -delete')
    #todo开启所有日志

    next_flag = 1 if (start_log_flag & 1) else 0
    u2d.shell(f'setprop debug.logd.mainlogcat {next_flag}')
    u2d.shell(f'setprop debug.logd.systemlogcat {next_flag}')
    u2d.shell(f'setprop debug.logd.eventslogcat {next_flag}')
    u2d.shell(f'setprop debug.logd.radiologcat {next_flag}')
    u2d.shell(f'setprop debug.logd.crashlogcat {next_flag}')
    u2d.shell(f'setprop debug.logd.kernellogcat {next_flag}')
    u2d.shell(f'setprop debug.logd.securitylogcat {next_flag}')

    next_flag = 1 if (start_log_flag & 2) else 0
    u2d.shell(f'setprop debug.diag_mdlog.modemlogcat {next_flag}')

    next_flag = 1 if (start_log_flag & 4) else 0
    u2d.shell(f'setprop debug.diag_mdlog.netlogcat {next_flag}')

    exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "setprop", f"debug.logd.applogcat.system.compression_level {5}"])



def stop_mobile_log(sn, u2d):
    logs.log(f"暂停log，不清除")
    if is_mtk(sn):
        _stop_mtk_log(sn, u2d)
    else:
        raise Exception(f"<UNK>{sn}<UNK>")

def clear_and_start_mobile_log(sn, u2d, start_log_flag=5, wait_duration_after_log_start=15, set_log_size=10000,
                               include_bug_report=True):

    logs.log(f"执行清理log和启动log")
    if is_mtk(sn):
        _clear_and_start_mtk_log(sn, u2d, start_log_flag, wait_duration_after_log_start, set_log_size)
    elif is_qcom(sn):
        _clear_and_start_qcom_log(sn, u2d, start_log_flag, wait_duration_after_log_start, set_log_size)
    elif is_sprd(sn):
        _clear_and_start_sprd_log(sn, u2d, wait_duration_after_log_start)
    else:
        raise Exception(f"<UNK>{sn}<UNK>")

        # # user版本使用ui 清理所有日志
        # u2d.shell('am start -n com.sprd.engineermode/.EngineerModeActivity')
        # time.sleep(3)

        # 清理 bug report
        # exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "rm", "-rf",
        #                   "/data/user_de/0/com.android.shell/files/bugreports/*"])

        # exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "rm", "-rf", "/data/debuglogger/*"]) #包含Mobilelog和network
        # exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "rm", "-rf",
        #                   "/data/user_de/0/com.android.shell/files/bugreports/*"])  # 包含Mobilelog和network
        # exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "rm", "-rf", "/data/TNE/*"])

        # 如果日志没有开启，则进行开启，adb shell am  broadcast -a com.debug.loggerui.ADB_CMD -e cmd_name start --ei cmd_target 5 --receiver-foreground  --receiver-include-background
        # exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "am", "startservice", "-n", "com.reallytek.wg/.utils.LogControlService",
        #                  "-e", "from", "adb", "-p", "com.reallytek.wg", "--ei", "magic", "902", "-e", "android", "1",
        #                  "-e", "kernel", "1", "-e", "uboot", "1", "-e", "lastkmsg", "1", "-e", "thermal", "0", "-e", "bthci", "0",
        #                  "-e", "apcap", "1"])

    # 通信需要的日志
    adb.tds_record_enable(sn)
    if include_bug_report:
        reset_bugreport(sn)


def zip_folder(mobile_log_path, base_log):
    for i in range(1, 10):
        zip_name = os.path.join(base_log, f"mobile_log{i}.zip")
        if not os.path.exists(zip_name):
            with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(mobile_log_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, mobile_log_path)
                        zipf.write(file_path, arcname)
            break
    # 删除原文件夹
    shutil.rmtree(mobile_log_path)


def clear_bugreports(device_id: str, reset_bugreport_time_also=False):
    # 定义bugreports目录路径
    bugreport_path = '/data/user_de/0/com.android.shell/files/bugreports'

    # 使用ADB命令删除该路径下的所有文件
    result = subprocess.run([ADB_EXE, '-s', device_id, 'shell', 'rm', '-rf', f'{bugreport_path}/*'],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # 检查命令执行是否成功
    if result.returncode != 0:
        logs_p().log("Error clearing files:", result.stderr.decode())

    if reset_bugreport_time_also:
        adb.reset_batterystats_for_bugreport(device_id)


def find_next_closest_bugreport(device_id: str, target_datetime: datetime):
    # 定义查找bugreport文件的路径
    bugreport_path = '/data/user_de/0/com.android.shell/files/bugreports'

    # 使用ADB命令列出指定路径下的文件
    result = subprocess.run([ADB_EXE, '-s', device_id, 'shell', 'ls', bugreport_path],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # 检查命令执行是否成功
    if result.returncode != 0:
        logs_p().log("Error executing ADB command:", result.stderr.decode())
        return None

    # 解析文件列表
    files = result.stdout.decode().splitlines()

    closest_file = None
    min_difference = None  # 用于记录最小的时间差

    for file in files:
        if file.startswith('bugreport-') and file.endswith('.zip'):
            # 提取文件名中的时间戳部分
            timestamp_str = file[-23:-4]

            try:
                # 将时间戳字符串转换为datetime对象
                file_datetime = datetime.strptime(timestamp_str, "%Y-%m-%d-%H-%M-%S")

                # 计算与目标时间的差值
                time_difference = (file_datetime - target_datetime).total_seconds()

                # 只考虑目标时间点之后的文件（时间差为正）
                if time_difference > 0:
                    # 查找时间差最小的文件
                    if min_difference is None or time_difference < min_difference:
                        min_difference = time_difference
                        closest_file = file

            except ValueError:
                logs_p().log(f"Error parsing datetime from filename: {file}")
                continue

    if closest_file:
        return f"{bugreport_path}/{closest_file}"
    else:
        return None


def find_previous_closest_bugreport(device_id: str, target_datetime: datetime):
    """查找指定设备在目标时间点之前最近的bugreport文件"""
    bugreport_path = '/data/user_de/0/com.android.shell/files/bugreports'

    # 获取设备文件列表
    result = subprocess.run([ADB_EXE, '-s', device_id, 'shell', 'ls', bugreport_path],
                            shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode != 0:
        logs_p().log("Error executing ADB command:", result.stderr.decode())
        return None

    files = result.stdout.decode().splitlines()
    closest_file = None
    min_difference = None  # 记录最小正向时间差（目标时间 - 文件时间）

    for file in files:
        if file.startswith('bugreport-') and file.endswith('.zip'):
            timestamp_str = file[-23:-4]  # 提取时间戳部分

            try:
                file_datetime = datetime.strptime(timestamp_str, "%Y-%m-%d-%H-%M-%S")
                time_difference = (target_datetime - file_datetime).total_seconds()

                # 只考虑目标时间之前的文件（时间差非负）
                if time_difference >= 0:
                    # 寻找最接近目标时间的文件
                    if (min_difference is None) or (time_difference < min_difference):
                        min_difference = time_difference
                        closest_file = file
            except ValueError:
                logs_p().log(f"文件名时间戳解析失败: {file}")
                continue

    return f"{bugreport_path}/{closest_file}" if closest_file else None


def _export_mtk_log(sn: str, mobile_log_path: str):
    adb_pull(sn, "/data/debuglogger/netlog", f"{mobile_log_path}/netlog")
    adb_pull(sn, "/data/debuglogger/mobilelog", f"{mobile_log_path}/mobilelog")
    adb_pull(sn, "/data/TNE", f"{mobile_log_path}/TNE")
    exec_cmd_timeout(
        [ADB_EXE, "-s", sn, "shell", "am", "broadcast", "-a", "com.debug.loggerui.ADB_CMD", "-e", "cmd_name",
         "stop", "--ei", "cmd_target", "127", "--receiver-foreground", "--receiver-include-background"])


def _export_spro_log(sn: str, mobile_log_path: str):
    adb_pull(sn, "/sdcard/ylog", mobile_log_path)
    adb_pull(sn, "/data/ylog", mobile_log_path)
    adb_pull(sn, "/data/corefile", mobile_log_path)
    adb_pull(sn, "/sdcard/minidump", mobile_log_path)
    exec_cmd_timeout(
        [ADB_EXE, "-s", sn, "shell", "am", "startservice", "-n", "com.reallytek.wg/.utils.LogControlService", "-e"
            , "from", "adb", "-p", "com.reallytek.wg", "--ei", "magic", "901"])


def _export_qcom_log(sn: str, mobile_log_path: str):
    adb_pull(sn, "/data/debuglogger/mobilelog/", mobile_log_path)
    adb_pull(sn, "/data/vendor/debuglogger/netlog/", mobile_log_path)


# ============= 高通平台 diag 日志管理方法 =============

def get_qcom_log_service_status(sn: str):
    """
    获取高通平台各项 diag 日志服务的状态
    
    参数:
        sn: 设备序列号
    
    返回:
        字典，包含各日志服务的状态 (1=运行中, 0=已停止)
    """
    status = {}
    services = {
        'modemlogcat': 'debug.diag_mdlog.modemlogcat',
        'fwlogcat': 'debug.diag_mdlog.fwlogcat',
        'bthcilogcat': 'debug.diag_mdlog.bthcilogcat',
        'adspSensorlogcat': 'debug.diag_mdlog.adspSensorlogcat',
        'adspAudiologcat': 'debug.diag_mdlog.adspAudiologcat',
        'adspChargerlogcat': 'debug.diag_mdlog.adspChargerlogcat',
    }
    
    for name, prop in services.items():
        success, result = exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "getprop", prop])
        status[name] = result[0].strip() if success and result else '0'
    
    return status


def list_qcom_diag_log_files(sn: str):
    """
    列出高通平台日志目录下的所有 diag 日志文件
    
    参数:
        sn: 设备序列号
    
    返回:
        字典，包含各日志目录的文件列表
    """
    log_dirs = {
        'root': '/data/vendor/debuglogger/',
        'mdlog': '/data/vendor/debuglogger/mdlog/',
        'netlog': '/data/vendor/debuglogger/netlog/',
        'bthci': '/data/vendor/debuglogger/connsyslog/bthci/',
        'fw': '/data/vendor/debuglogger/connsyslog/fw/',
        'sensor': '/data/vendor/debuglogger/adsp/sensor',
        'audio': '/data/vendor/debuglogger/adsp/audio',
        'charger': '/data/vendor/debuglogger/adsp/charger',
    }
    
    files = {}
    for name, path in log_dirs.items():
        success, result = exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "ls", "-l", path])
        files[name] = '\n'.join(result) if success and result else ''
    
    return files


def export_qcom_all_vendor_logs(sn: str, export_dir: str):
    """
    导出高通平台所有 vendor 日志
    
    参数:
        sn: 设备序列号
        export_dir: 导出目录路径
    """
    os.makedirs(export_dir, exist_ok=True)
    logs_p().log(f"Starting to export all vendor logs to {export_dir}")
    adb_pull(sn, "/data/vendor/debuglogger/", export_dir)
    logs_p().log(f"All vendor logs exported successfully")


def export_qcom_cellular_logs(sn: str, export_dir: str):
    """
    导出高通平台蜂窝通信日志 (mdlog)
    
    参数:
        sn: 设备序列号
        export_dir: 导出目录路径
    """
    mdlog_dir = os.path.join(export_dir, "mdlog")
    os.makedirs(mdlog_dir, exist_ok=True)
    logs_p().log(f"Exporting cellular communication logs to {mdlog_dir}")
    adb_pull(sn, "/data/vendor/debuglogger/mdlog/", mdlog_dir)
    logs_p().log(f"Cellular communication logs exported successfully")


def export_qcom_wifi_logs(sn: str, export_dir: str):
    """
    导出高通平台 WiFi 相关日志
    
    参数:
        sn: 设备序列号
        export_dir: 导出目录路径
    """
    wifi_dir = os.path.join(export_dir, "wifilog")
    os.makedirs(wifi_dir, exist_ok=True)
    logs_p().log(f"Exporting WiFi logs to {wifi_dir}")
    adb_pull(sn, "/data/vendor/debuglogger/connsyslog/fw/", wifi_dir)
    logs_p().log(f"WiFi logs exported successfully")


def export_qcom_bluetooth_logs(sn: str, export_dir: str):
    """
    导出高通平台蓝牙相关日志
    
    参数:
        sn: 设备序列号
        export_dir: 导出目录路径
    """
    bt_dir = os.path.join(export_dir, "bluetooth")
    os.makedirs(bt_dir, exist_ok=True)
    logs_p().log(f"Exporting Bluetooth logs to {bt_dir}")
    adb_pull(sn, "/data/vendor/debuglogger/connsyslog/bthci/", bt_dir)
    logs_p().log(f"Bluetooth logs exported successfully")


def export_qcom_audio_logs(sn: str, export_dir: str):
    """
    导出高通平台音频相关日志
    
    参数:
        sn: 设备序列号
        export_dir: 导出目录路径
    """
    audio_dir = os.path.join(export_dir, "audio")
    os.makedirs(audio_dir, exist_ok=True)
    logs_p().log(f"Exporting audio logs to {audio_dir}")
    adb_pull(sn, "/data/vendor/debuglogger/adsp/audio/", audio_dir)
    logs_p().log(f"Audio logs exported successfully")


def export_qcom_sensor_logs(sn: str, export_dir: str):
    """
    导出高通平台传感器相关日志
    
    参数:
        sn: 设备序列号
        export_dir: 导出目录路径
    """
    sensor_dir = os.path.join(export_dir, "sensor")
    os.makedirs(sensor_dir, exist_ok=True)
    logs_p().log(f"Exporting sensor logs to {sensor_dir}")
    adb_pull(sn, "/data/vendor/debuglogger/adsp/sensor/", sensor_dir)
    logs_p().log(f"Sensor logs exported successfully")


def export_qcom_charger_logs(sn: str, export_dir: str):
    """
    导出高通平台充电相关日志
    
    参数:
        sn: 设备序列号
        export_dir: 导出目录路径
    """
    charger_dir = os.path.join(export_dir, "charger")
    os.makedirs(charger_dir, exist_ok=True)
    logs_p().log(f"Exporting charger logs to {charger_dir}")
    adb_pull(sn, "/data/vendor/debuglogger/adsp/charger/", charger_dir)
    logs_p().log(f"Charger logs exported successfully")


def stop_all_qcom_diag_services(sn: str, wait_seconds: int = 10):
    """
    关闭高通平台所有 diag 日志服务
    
    参数:
        sn: 设备序列号
        wait_seconds: 关闭服务后的等待时间（秒），确保进程已终止，默认为 10 秒
    """
    logs_p().log("Disabling all diag log services...")
    exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "setprop", "debug.diag_mdlog.alllogcat", "0"])
    
    logs_p().log(f"Waiting {wait_seconds} seconds to confirm process termination...")
    time.sleep(wait_seconds)
    
    # Check if diag_mdlog process is still running
    success, result = exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "ps", "-A"])
    if success and result and any('diag_mdlog' in line for line in result):
        logs_p().log("Warning: diag_mdlog process still running")
    else:
        logs_p().log("All diag services stopped successfully")


def start_qcom_diag_service(sn: str, service_type: str, stop_all_first: bool = True, wait_seconds: int = 10):
    """
    启动高通平台特定的 diag 日志服务
    
    参数:
        sn: 设备序列号
        service_type: 要启动的服务类型，可选值:
            - 'modem': 蜂窝通信日志
            - 'wifi': WiFi 日志
            - 'bluetooth': 蓝牙日志
            - 'sensor': 传感器日志
            - 'audio': 音频日志
            - 'charger': 充电日志
        stop_all_first: 启动前是否先关闭所有服务（默认: True）
        wait_seconds: 关闭服务后的等待时间（秒），默认为 10 秒
    """
    service_map = {
        'modem': ('debug.diag_mdlog.modemlogcat', 'communication'),
        'wifi': ('debug.diag_mdlog.fwlogcat', 'WiFi'),
        'bluetooth': ('debug.diag_mdlog.bthcilogcat', 'Bluetooth'),
        'sensor': ('debug.diag_mdlog.adspSensorlogcat', 'sensor'),
        'audio': ('debug.diag_mdlog.adspAudiologcat', 'audio'),
        'charger': ('debug.diag_mdlog.adspChargerlogcat', 'charger'),
    }
    
    if service_type not in service_map:
        raise ValueError(f"Invalid service type: {service_type}. Must be one of {list(service_map.keys())}")
    
    prop_name, display_name = service_map[service_type]
    
    if stop_all_first:
        logs_p().log("Stopping all log services first...")
        exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "setprop", "debug.diag_mdlog.alllogcat", "0"])
        logs_p().log(f"Waiting for service to shut down ({wait_seconds} seconds)...")
        time.sleep(wait_seconds)
        
        # Check if process is closed, force kill if needed
        success, result = exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "ps", "-A"])
        if success and result and any('diag_mdlog' in line for line in result):
            logs_p().log("Warning: Logger process not shut down cleanly, trying to force termination...")
            exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "pkill", "diag_mdlog"])
            time.sleep(3)
    
    # Start the specified service
    logs_p().log(f"Starting {display_name} log service...")
    exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "setprop", prop_name, "1"])
    
    # Display current status
    success, status = exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "getprop", prop_name])
    status_str = status[0].strip() if success and status else 'unknown'
    logs_p().log(f"Current status of {display_name} log service: {status_str}")


def clear_all_qcom_log_files(sn: str):
    """
    清空高通平台所有日志文件
    
    参数:
        sn: 设备序列号
    
    注意:
        此操作会删除所有文件，但保留文件夹结构
    """
    logs_p().log("Clearing all log files...")
    logs_p().log("WARNING: This operation will delete all log files in /data/debuglogger/ and /data/vendor/debuglogger/")
    
    # Clear all files under /data/debuglogger/
    logs_p().log("Clearing /data/debuglogger/ directory...")
    exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "find", "/data/debuglogger/", "-type", "f", "-delete"])
    
    # Clear all files under /data/vendor/debuglogger/
    logs_p().log("Clearing /data/vendor/debuglogger/ directory...")
    exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "find", "/data/vendor/debuglogger/", "-type", "f", "-delete"])
    
    logs_p().log("Clear operation completed")


def clear_qcom_log_folder(sn: str, folder_type: str):
    """
    清空高通平台指定日志文件夹的内容
    
    参数:
        sn: 设备序列号
        folder_type: 要清空的文件夹类型，可选值:
            - 'mobilelog': /data/debuglogger/mobilelog
            - 'mdlog': /data/vendor/debuglogger/mdlog (蜂窝通信日志)
            - 'netlog': /data/vendor/debuglogger/netlog (网络相关日志)
            - 'bthci': /data/vendor/debuglogger/connsyslog/bthci (蓝牙日志)
            - 'fw': /data/vendor/debuglogger/connsyslog/fw (WiFi 日志)
            - 'sensor': /data/vendor/debuglogger/adsp/sensor (传感器日志)
            - 'audio': /data/vendor/debuglogger/adsp/audio (音频日志)
            - 'charger': /data/vendor/debuglogger/adsp/charger (充电日志)
    """
    folder_map = {
        'mobilelog': '/data/debuglogger/mobilelog',
        'mdlog': '/data/vendor/debuglogger/mdlog',
        'netlog': '/data/vendor/debuglogger/netlog',
        'bthci': '/data/vendor/debuglogger/connsyslog/bthci',
        'fw': '/data/vendor/debuglogger/connsyslog/fw',
        'sensor': '/data/vendor/debuglogger/adsp/sensor',
        'audio': '/data/vendor/debuglogger/adsp/audio',
        'charger': '/data/vendor/debuglogger/adsp/charger',
    }
    
    if folder_type not in folder_map:
        raise ValueError(f"Invalid folder type: {folder_type}. Must be one of {list(folder_map.keys())}")
    
    folder_path = folder_map[folder_type]
    logs_p().log(f"Clearing folder contents: {folder_path}")
    
    # Delete files first
    exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "find", folder_path, "-type", "f", "-delete"])
    # Then delete subdirectories (if any)
    exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "find", folder_path, "-mindepth", "1", "-type", "d", "-exec", "rm", "-rf", "{}", "+"])
    
    logs_p().log(f"Folder {folder_path} cleared successfully")


def export_qcom_today_logs(sn: str, export_dir: str, target_date: str = None):  # type: ignore
    """
    导出高通平台指定日期生成的日志
    
    参数:
        sn: 设备序列号
        export_dir: 导出目录路径
        target_date: 目标日期，格式为 'YYYY-MM-DD'，如果不提供则默认为今天
    """
    from datetime import datetime, timedelta
    
    if target_date is None:
        today = datetime.now()
        target_date = today.strftime('%Y-%m-%d')
    else:
        today = datetime.strptime(target_date, '%Y-%m-%d')
    
    tomorrow = today + timedelta(days=1)
    tomorrow_str = tomorrow.strftime('%Y-%m-%d')
    
    logs_p().log(f"Exporting logs for date: {target_date}")
    
    # Create local export directories
    local_dir = os.path.join(export_dir, f"today_logs_{target_date}")
    os.makedirs(local_dir, exist_ok=True)
    
    log_types = {
        'mobilelog': '/data/debuglogger/mobilelog',
        'mdlog': '/data/vendor/debuglogger/mdlog',
        'wifilog': '/data/vendor/debuglogger/connsyslog/fw',
        'bluetooth': '/data/vendor/debuglogger/connsyslog/bthci',
        'sensor': '/data/vendor/debuglogger/adsp/sensor',
        'audio': '/data/vendor/debuglogger/adsp/audio',
        'charger': '/data/vendor/debuglogger/adsp/charger',
    }
    
    for log_name, device_path in log_types.items():
        log_dir = os.path.join(local_dir, log_name)
        os.makedirs(log_dir, exist_ok=True)
        
        logs_p().log(f"Exporting {log_name} logs for the day...")
        
        # Find files modified on the target date
        cmd = f"find {device_path} -type f -newermt {target_date} ! -newermt {tomorrow_str}"
        success, result = exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", cmd])
        
        if success and result:
            for file_path in result:
                file_path = file_path.strip()
                if file_path:
                    adb_pull(sn, file_path, log_dir)
                    logs_p().log(f"Exported: {file_path}")
    
    logs_p().log(f"Log export for {target_date} completed! Saved to: {local_dir}")


def check_qcom_logd_services_status(sn: str):
    """
    检查高通平台核心 logd 服务 (debug.logd.*) 的状态
    
    参数:
        sn: 设备序列号
    
    返回:
        字典，包含各 logd 服务的状态 (1=运行中, 0=已停止)
    """
    status = {}
    services = {
        'mainlogcat': 'debug.logd.mainlogcat',
        'systemlogcat': 'debug.logd.systemlogcat',
        'crashlogcat': 'debug.logd.crashlogcat',
        'kernellogcat': 'debug.logd.kernellogcat',
        'eventslogcat': 'debug.logd.eventslogcat',
        'radiologcat': 'debug.logd.radiologcat',
        'securitylogcat': 'debug.logd.securitylogcat',
    }
    
    for name, prop in services.items():
        success, result = exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "getprop", prop])
        status[name] = result[0].strip() if success and result else '0'
    
    return status


def list_mobilelog_files(sn: str):
    """
    列出 mobilelog 目录下的所有日志文件
    
    参数:
        sn: 设备序列号
    
    返回:
        文件列表字符串
    """
    success, result = exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "ls", "-l", "/data/debuglogger/mobilelog/"])
    return '\n'.join(result) if success and result else ''


def export_all_mobilelog(sn: str, export_dir: str):
    """
    导出 mobilelog 目录下的所有文件
    
    参数:
        sn: 设备序列号
        export_dir: 导出目录路径
    """
    os.makedirs(export_dir, exist_ok=True)
    logs_p().log(f"Starting to export all logs to {export_dir}")
    adb_pull(sn, "/data/debuglogger/mobilelog/", export_dir)
    logs_p().log(f"All logs exported successfully")


def export_crash_logs(sn: str, export_dir: str):
    """
    从 mobilelog 目录导出崩溃日志
    
    参数:
        sn: 设备序列号
        export_dir: 导出目录路径
    
    说明:
        导出主崩溃日志文件和所有压缩归档文件
    """
    crash_dir = os.path.join(export_dir, "crash_logs")
    os.makedirs(crash_dir, exist_ok=True)
    
    logs_p().log(f"Starting to export crash logs to {crash_dir}")
    
    # Export the main crash log
    adb_pull(sn, "/data/debuglogger/mobilelog/crashlogcat-log", crash_dir)
    
    # Export compressed archives of crash logs
    # Note: adb pull with wildcards may not work, so we list files first
    success, result = exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "ls", "/data/debuglogger/mobilelog/crashlogcat-log.I*.gz"])
    if success and result:
        for file_path in result:
            file_path = file_path.strip()
            if file_path and '.gz' in file_path:
                adb_pull(sn, file_path, crash_dir)
    
    logs_p().log(f"Crash logs exported successfully to {crash_dir}")


def start_all_qcom_logd_services(sn: str):
    """
    启动高通平台所有核心 logd 服务
    
    参数:
        sn: 设备序列号
    """
    logs_p().log("Starting all logd services...")
    
    services = [
        'debug.logd.mainlogcat',
        'debug.logd.systemlogcat',
        'debug.logd.eventslogcat',
        'debug.logd.radiologcat',
        'debug.logd.crashlogcat',
        'debug.logd.kernellogcat',
        'debug.logd.securitylogcat',
    ]
    
    for service in services:
        exec_cmd_timeout([ADB_EXE, "-s", sn, "shell", "setprop", service, "1"])
    
    logs_p().log("All logd services have been started")

def get_all_qcom_log_services_status(sn: str):
    """
    获取高通平台所有日志服务的状态（包括 diag_mdlog 和 logd 服务）
    
    参数:
        sn: 设备序列号
    
    返回:
        组合字典，包含所有服务状态:
            - 'diag_services': diag 日志服务状态
            - 'logd_services': logd 服务状态
    """
    diag_status = get_qcom_log_service_status(sn)
    logd_status = check_qcom_logd_services_status(sn)

    return {
        'diag_services': diag_status,
        'logd_services': logd_status,
    }
def export_bugreports(sn, export_bugreports_dir, export_mode='full'):
    """
    export_mode == 'full'：重新生成bugreport，并将所有bugreports拉出
    export_mode == 'full_exist'：不重新生成bugreport，直接将所有已经存在的bugreports拉出
    export_mode == 'single'：重新生成bugreport，并仅拉出这个文件
    """
    if export_mode and export_mode != 'none':
        sub_bug_reports_dir = os.path.join(export_bugreports_dir, "bugreports")
        if export_mode != 'full_exist':
            logs_p().log(f"mobilelog：正在生成bugreport")
            target_pc_bugreport_path = os.path.join(sub_bug_reports_dir, 'bugreport.zip')
            os.makedirs(sub_bug_reports_dir, exist_ok=True)
            res = exec_cmd_timeout(
                [ADB_EXE, "-s", sn, "bugreport", target_pc_bugreport_path], 60 * 30)  # 30分钟内进行生成，防止无限时生成卡住
            logs_p().log(res)

        if export_mode == 'full' or export_mode == 'full_exist':
            shutil.rmtree(sub_bug_reports_dir, ignore_errors=True)
            adb_pull(sn, "/data/user_de/0/com.android.shell/files/bugreports", export_bugreports_dir)


def export_logs(sn, export_log_dir, export_bug_reports_mode='full'):
    """
    导出手机的Log到export_log_dir
    export_bug_reports_mode：导出bugreport的模式，可选择full,full_exist,none，当选择full时表示生成并拉取所有的bugreports，当选择full_exist时，仅拉取当前已经存在的所有bugreports，none的话，不导出
    """
    if not adb.is_adb_connected(sn):
        raise Exception(f'Device "{sn}" not connected, can not export logs.')

    mobile_log_path = os.path.join(export_log_dir, "mobile_log")
    logs_p().log(f"执行导出log")
    os.makedirs(mobile_log_path, exist_ok=True)

    export_bugreports(sn, mobile_log_path, export_bug_reports_mode)

    logs_p().log(f"正在导出日志...")
    # deps = resolve(
    #     platform_info=Depends(create_platform_info_provider(sn))
    # )
    # platform_info = deps['platform_info']
    if is_mtk(sn):
        # adb_pull(sn, "/data/user_de/0/com.android.shell/files/bugreports", f"{mobile_log_path}/bugreports")
        _export_mtk_log(sn=sn, mobile_log_path=mobile_log_path)
    elif is_qcom(sn):
        _export_qcom_log(sn=sn, mobile_log_path=mobile_log_path)
    elif is_sprd(sn):
        _export_spro_log(sn=sn, mobile_log_path=mobile_log_path)
    else:
        raise Exception(f"<UNK>{sn}<UNK>")


    logs_p().log(f"开始压缩Log文件夹")
    zip_folder(mobile_log_path, export_log_dir)


if __name__ == '__main__':
    _u2d = uiautomator2.connect("1234567891234560")
    clear_and_start_mobile_log("1234567891234560",u2d=_u2d)
    # export_logs("1234567891234560","logRes")
