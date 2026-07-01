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
from powertrde.utils.trde.adb import exec_cmd_timeout, is_mtk

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


# _sprd_android_log_flg = False

def adb_pull(sn, device_path, local_path):
    cmdline = [ADB_EXE, "-s", sn, "pull", device_path, local_path]
    exec_cmd_timeout(cmdline, timeout=60 * 30)


def reset_bugreport(sn):
    # 清理bugreport历史文件
    clear_bugreports(sn)
    # 重置Bugreport时间
    adb.reset_batterystats_for_bugreport(sn)


def clear_and_start_mobile_log(sn, u2d, start_log_flag=5, wait_duration_after_log_start=15, set_log_size=10000,
                               include_bug_report=True):
    is_mtk_device = is_mtk(sn)
    # logs.log(f"执行清理log和启动log")
    if is_mtk_device:
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
        if u2d.xpath('//*[@text="CLEAR ALL"]').wait(15):  #有时候点击完了，反应很慢才进入clear页面
            # logs.log("找到CLEAR ALL")
            time.sleep(2)
            u2d.xpath('//*[@text="CLEAR ALL"]').click()
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
    else:
        adb.poweron_screen_and_unlock(sn)
        time.sleep(2)
        rom_sz = adb.rom_size_MB(sn)
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


def export_logs(sn, export_log_dir, export_bug_reports_mode='full'):
    """
    导出手机的Log到export_log_dir
    export_bug_reports_mode：导出bugreport的模式，可选择full,full_exist,none，当选择full时表示生成并拉取所有的bugreports，当选择full_exist时，仅拉取当前已经存在的所有bugreports，none的话，不导出
    """
    if not adb.is_adb_connected(sn):
        raise Exception(f'Device "{sn}" not connected, can not export logs.')

    mobile_log_path = os.path.join(export_log_dir, "mobile_log")
    logs_p().log(f"执行导出log")
    is_mtk_device = is_mtk(sn)
    os.makedirs(mobile_log_path, exist_ok=True)

    if export_bug_reports_mode and export_bug_reports_mode != 'none':
        logs_p().log(f"正在生成bugreport")
        bug_reports_dir = os.path.join(mobile_log_path, "bugreports")
        if export_bug_reports_mode != 'full_exist':
            target_pc_bugreport_path = os.path.join(bug_reports_dir, 'bugreport.zip')
            os.makedirs(bug_reports_dir, exist_ok=True)
            res = exec_cmd_timeout(
                [ADB_EXE, "-s", sn, "bugreport", target_pc_bugreport_path],
                60 * 30)  # 30分钟内进行生成，防止无限时生成卡住
            logs_p().log(res)

        if export_bug_reports_mode == 'full' or export_bug_reports_mode == 'full_exist':
            shutil.rmtree(bug_reports_dir, ignore_errors=True)
            adb_pull(sn, "/data/user_de/0/com.android.shell/files/bugreports", mobile_log_path)

    logs_p().log(f"正在导出日志...")
    if is_mtk_device:
        # adb_pull(sn, "/data/user_de/0/com.android.shell/files/bugreports", f"{mobile_log_path}/bugreports")
        adb_pull(sn, "/data/debuglogger/netlog", f"{mobile_log_path}/netlog")
        adb_pull(sn, "/data/debuglogger/mobilelog", f"{mobile_log_path}/mobilelog")
        adb_pull(sn, "/data/TNE", f"{mobile_log_path}/TNE")
        exec_cmd_timeout(
            [ADB_EXE, "-s", sn, "shell", "am", "broadcast", "-a", "com.debug.loggerui.ADB_CMD", "-e", "cmd_name",
             "stop", "--ei", "cmd_target", "127", "--receiver-foreground", "--receiver-include-background"])
    else:
        adb_pull(sn, "/sdcard/ylog", mobile_log_path)
        adb_pull(sn, "/data/ylog", mobile_log_path)
        adb_pull(sn, "/data/corefile", mobile_log_path)
        adb_pull(sn, "/sdcard/minidump", mobile_log_path)
        exec_cmd_timeout(
            [ADB_EXE, "-s", sn, "shell", "am", "startservice", "-n", "com.reallytek.wg/.utils.LogControlService", "-e"
                , "from", "adb", "-p", "com.reallytek.wg", "--ei", "magic", "901"])

    logs_p().log(f"开始压缩Log文件夹")
    zip_folder(mobile_log_path, export_log_dir)


if __name__ == '__main__':
    u2d = uiautomator2.connect("142355551N000073")
    clear_and_start_mobile_log("142355551N000073", u2d)
    # export_logs("ASALE3741B000022","logRes")
