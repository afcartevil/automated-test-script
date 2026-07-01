import json
import math
import os
import re
import shutil
import statistics
import subprocess
import tempfile
import threading
import time
import zipfile
from datetime import datetime
from enum import Enum
from shlex import quote
from typing import Tuple, List, Optional, Union

from powertrde import env
from powertrde.framework.logs_protocol import logs_p
from powertrde.utils.trde.trde_utils import LEVEL_BATT_CONSUME_FULL, OUTPUT_DIR, DEVICE_AUTOMATOR_DIR, \
    mtk_log_dir, TRDE_APK_PACKAGE, TRDE_APK_ACTIVITY, mkdirs, ADB_EXE
from powertrde.utils import string_utils

TRDE_DEVICE_DIR = '/sdcard/trde'
TRDE_DEVICE_INFO_FILE_KEY = 'battery_info'
MTKLOG_ROM_SIZE_SET = False
g_thread_locks = {}

ANDROID_SETTINGS_PACKAGE = 'com.android.settings'
ANDROID_SETTINGS_ACTIVITY = 'com.android.settings/.Settings'

DISABLE_ADB_ERROR_OUTPUT = False


class MultiScreenStatus(Enum):
    INVALID = -2,
    RESET = -1,
    FOLDED = 0,
    SEMI_OPEN = 1,
    OPEN = 2,


def _log_adb(device_id, cmd):
    # 暂时移除所有adb log的打印，防止占用公共资源
    # log(f'adb log: {cmd}', device_id)
    pass


ignored_thread_lock_devices = {'adb_global', 'log_Global', ''}


def _ignore_lock_device(device_id):
    if device_id in ignored_thread_lock_devices:
        return True
    else:
        return False


def _lock_adb_thread(device_id):
    if not _ignore_lock_device(device_id):
        g_thread_locks.setdefault(device_id, threading.Lock()).acquire()


def _release_adb_thread(device_id):
    if not _ignore_lock_device(device_id):
        g_thread_locks.setdefault(device_id, threading.Lock()).release()


def _exe_adb_cmd(device_id, cmd):
    c = f'{ADB_EXE} -s {device_id} shell {cmd}'
    return _exe_pc_cmd(device_id, c)


def _exe_adb_cmd_raise(device_id, cmd):
    c = f'{ADB_EXE} -s {device_id} shell {cmd}'
    return _exe_pc_cmd_raise(device_id, c)


def _exe_adb_cmd_with_exit_code(device_id, cmd):
    c = f'{ADB_EXE} -s {device_id} shell {cmd}'
    return _exe_pc_cmd_with_exit_code(device_id, c)


def _exe_pc_cmd(device_id, cmd):
    return _exe_pc_cmd_with_exit_code(device_id, cmd)[0]


def _exe_pc_cmd_raise(device_id, cmd):
    cmd_result = _exe_pc_cmd_with_exit_code(device_id, cmd)
    if cmd_result[1]:
        raise Exception(f'ADB CMD Failed with exit code {cmd_result[1]}; cmd line: {cmd}')
    return cmd_result[0]


def _exe_pc_cmd_with_exit_code(device_id, cmd):
    _lock_adb_thread(device_id)
    from powertrde.utils import misc_utils
    out_texts, out_error_texts, exit_code = misc_utils.run_command_get_text_output_exit_code(cmd, shell=True,
                                                                                             capture_error_output=True)
    lines = out_texts.splitlines()
    if out_error_texts and not DISABLE_ADB_ERROR_OUTPUT:
        if exit_code != 0:
            logs_p().log_warning(
                f"ADB CMD ERROR with code {exit_code}: (cmd line)-> '{cmd}'\n(adb error message)-> {out_error_texts}",
                device_id=device_id)
    _release_adb_thread(device_id)
    return lines, exit_code


def _exe_adb_cmd_no_wait(device_id, cmd):
    _lock_adb_thread(device_id)
    _log_adb(device_id, cmd)
    os.popen(f'{ADB_EXE} -s {device_id} shell {cmd}')
    _log_adb(device_id, '_no_wait')
    _release_adb_thread(device_id)


def adb_devices():
    device_ids = []
    cmd = f'{ADB_EXE} devices '
    lines = _exe_pc_cmd('adb_global', cmd)
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('*'):
            continue
        if line.startswith('List '):
            continue
        unit = line.split('\t')
        if unit[0].strip():
            device_ids.append(unit[0])
    return device_ids


def adb_devices_online():
    device_ids = []
    cmd = f'{ADB_EXE} devices '
    lines = _exe_pc_cmd('adb_global', cmd)
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('*'):
            continue
        if line.startswith('List '):
            continue
        if not line.__contains__('device'):
            continue
        unit = line.split('\t')
        if unit[0].strip():
            device_ids.append(unit[0])
    return device_ids


def first_device():
    all_devices = adb_devices()
    if not all_devices:
        return None
    return all_devices[0]


def set_pointer_location(device_id, is_on: bool):
    set_settings_value(device_id, 'system', 'pointer_location', '1' if is_on else '0')


def is_pointer_location_on(device_id):
    v = None
    try:
        v = get_settings_value(device_id, 'system', 'pointer_location')
    except Exception:
        pass
    if v and v == '1':
        return True
    return False


def first_device_isopen_pointer_location(flag):
    # flag = 1,获取第一个打开了pointer_location的机器
    # flag = 0,获取第一个没打开pointer_location的机器
    all_devices = adb_devices_online()
    if not all_devices:
        return None
    for sn in all_devices:
        if is_aod_enabled(sn):
            poweron_phone_screen(sn)
            time.sleep(0.3)
        cmd = f'{ADB_EXE} -s {sn} shell settings get system pointer_location'
        lines = _exe_pc_cmd('adb_global', cmd)
        res = "".join([line.strip() for line in lines])
        if flag == 1 and "1" in res:
            return sn
        if flag == 0 and "1" not in res:  #新机器什么都不显示，不是0，也不是1
            return sn
    return None


def first_device_isopen_pointer_location_no_aod(flag):
    # flag = 1,获取第一个打开了pointer_location的机器
    # flag = 0,获取第一个没打开pointer_location的机器
    all_devices = adb_devices_online()
    if not all_devices:
        return None
    for sn in all_devices:
        cmd = f'{ADB_EXE} -s {sn} shell settings get system pointer_location'
        lines = _exe_pc_cmd('adb_global', cmd)
        res = "".join([line.strip() for line in lines])
        if flag == 1 and "1" in res:
            return sn
        if flag == 0 and "1" not in res:  #新机器什么都不显示，不是0，也不是1
            return sn
    return None


def device_model(device_id):
    "getprop ro.product.model"
    cmd = 'getprop ro.product.model'
    info = _exe_adb_cmd(device_id, cmd)
    return ''.join(info).strip()


def device_model_simple(device_id):
    m = device_model(device_id).upper()
    g = m.find(' ')
    if g > 0:
        return m[g + 1:]
    return m


def device_brand(device_id):
    cmd = 'getprop ro.product.brand'
    info = _exe_adb_cmd(device_id, cmd)
    brand = ''.join(info).strip()
    res = "other"  #可能是飞利浦等贴牌
    if brand == "Itel" or brand == "itel":
        res = "itel"
    elif brand == "Infinix" or brand == "infinix":
        res = "infinix"
    elif brand == "TECNO" or brand == "tecno":
        res = "tecno"
    elif brand == "iQOO":
        res = "iQOO"
    return res


def device_subseries(device_id):
    cmd = 'getprop persist.sys.tran.device.name'
    info = _exe_adb_cmd(device_id, cmd)
    m = ''.join(info).strip()
    return m.split(' ')[1]


def tap_on_screen_by_percent(device_id, x_percent, y_percent):
    """根据屏幕百分比发送点击事件"""
    width, height = screen_size(device_id)
    # 计算具体的坐标位置
    x = int(width * x_percent)
    y = int(height * y_percent)
    cmd = f'input tap {x} {y}'
    _exe_adb_cmd(device_id, cmd)


def get_device_rom_version(device_id):
    cmd = 'getprop ro.build.display.id'
    lines = _exe_adb_cmd(device_id, cmd)
    return ''.join(lines).strip()


def device_android_version(device_id):
    cmd = 'getprop ro.build.version.release'
    info = _exe_adb_cmd(device_id, cmd)
    return ''.join(info).strip()


def get_build_version(device_id):
    cmd = 'getprop ro.tranos.build.version'
    info = _exe_adb_cmd(device_id, cmd)
    return ''.join(info).strip()


def device_cpu_abi(device_id):
    cmd = 'getprop ro.product.cpu.abi'
    lines = _exe_adb_cmd(device_id, cmd)
    return ''.join(lines).strip()


def get_device_brand(device_id):
    "getprop ro.product.brand"
    cmd = 'getprop ro.product.brand'
    lines = _exe_adb_cmd(device_id, cmd)
    info = ''.join(lines).strip()
    return info


def device_is_root(device_id):
    cmd = 'getprop service.adb.root'
    lines = _exe_adb_cmd(device_id, cmd)
    info = ''.join(lines).strip()
    if info in ['1']:
        return True
    return False


def set_heads_up_notify_enabled(device_id, enabled: bool):
    cmd = f"settings put global heads_up_notifications_enabled {1 if enabled else 0}"
    _exe_adb_cmd(device_id, cmd)


def start_battery_consume(device_id, min_batt=30, consume_level=LEVEL_BATT_CONSUME_FULL, max_temp=0, restart_temp=0):
    cmd = f'am broadcast -a com.trs.trde.START_BATTERY_CONSUME ' \
          f'-n com.trs.trde/.MainReceiver --ei min_batt {min_batt} --ei configs {consume_level}'
    if max_temp:
        cmd += f' --ef max_temp {max_temp}'
    if restart_temp:
        cmd += f' --ef restart_temp {restart_temp}'
    _exe_adb_cmd(device_id, cmd)


def stop_battery_consume(device_id):
    cmd = f'am broadcast -a com.trs.trde.STOP_BATTERY_CONSUME ' \
          f'-n com.trs.trde/.MainReceiver'
    _exe_adb_cmd(device_id, cmd)

    # maybe screen off
    time.sleep(1)
    poweron_screen_and_unlock(device_id)
    time.sleep(1)


def reset_battery_status(device_id):
    cmd = f'dumpsys battery reset'
    _exe_adb_cmd(device_id, cmd)


def reset_batterystats_for_bugreport(device_id):
    cmd = f'dumpsys batterystats --reset'
    _exe_adb_cmd(device_id, cmd)


def tds_record_enable(device_id):
    cmd = f'settings put global tds_dns_record_enable 1'
    _exe_adb_cmd(device_id, cmd)


def get_battery_temperature(device_id):
    cmd = f'"dumpsys battery | grep temperature"'
    return float(_exe_adb_cmd(device_id, cmd)[0].split(': ')[1]) / 10


def is_location_service_on(device_id):
    return get_settings_value(device_id, 'secure', 'location_mode') == '3'


def open_close_location_service(device_id, location_flag: bool):
    cmd = f'settings put secure location_mode {3 if location_flag else 0}'
    _exe_adb_cmd(device_id, cmd)


def set_irq_event(device_id, value, delay_seconds=45):
    cmd = f'am broadcast -a com.trs.trde.IQR_EVENT ' \
          f'-n com.trs.trde/.MainReceiver ' \
          f'--ei irq_value {value} ' \
          f'--ei delay_sec {delay_seconds}'
    _exe_adb_cmd(device_id, cmd)


def start_repeat_reboot(device_id, repeat_times, delay_time_sec):
    cmd = f'am broadcast -a com.trs.trde.REPEAT_REBOOT ' \
          f'-n com.trs.trde/.MainReceiver ' \
          f'--ei repeat_times {repeat_times} --ei delay_time {delay_time_sec}'
    _exe_adb_cmd_no_wait(device_id, cmd)
    time.sleep(0.1)


def stop_repeat_reboot(device_id):
    cmd = f'am broadcast -a com.trs.trde.REPEAT_REBOOT_STOP ' \
          f'-n com.trs.trde/.MainReceiver'
    _exe_adb_cmd(device_id, cmd)
    time.sleep(1)
    kill_app_by_key(device_id, TRDE_APK_PACKAGE)
    start_apk_activity(device_id, TRDE_APK_PACKAGE, TRDE_APK_ACTIVITY)


def reboot_phone_with_off_anim(device_id):
    cmd = f'am broadcast -a com.trs.trde.DEVICE_REBOOT -n com.trs.trde/.MainReceiver'
    _exe_adb_cmd_no_wait(device_id, cmd)
    time.sleep(0.1)


def open_close_nfc(device_id, is_open):
    is_open = bool(is_open) and is_open != "0"
    content = 'enable' if is_open else 'disable'
    _exe_adb_cmd_no_wait(device_id, f'svc nfc {content}')


def open_close_auto_rotate(device_id, is_open):
    is_open = bool(is_open) and is_open != "0"
    content = '1' if is_open else '0'
    set_settings_value(device_id, 'system', 'accelerometer_rotation', content)
    if content == '0':
        set_settings_value(device_id, 'system', 'user_rotation', 0)


def is_screen_on(device_id):
    cmd = '"dumpsys window policy | grep State="'
    content = _exe_adb_cmd(device_id, cmd)
    content = ''.join(content)
    if 'SCREEN_STATE_ON' in content and 'INTERACTIVE_STATE_AWAKE' in content:
        return True
    else:
        return False


def is_screen_on_desktop(device_id):
    cmd = '"dumpsys window | grep entF"'
    content = _exe_adb_cmd(device_id, cmd)
    content = ''.join(content)
    return '/' in content


def is_boot_completed(device_id):
    cmd = 'getprop sys.boot_completed'
    content = _exe_adb_cmd(device_id, cmd)
    if content and content[0] == "1":
        return True
    else:
        return False


def poweron_phone_screen(device_id):
    if is_screen_on(device_id):
        return
    cmd = 'input keyevent KEYCODE_POWER'
    _exe_adb_cmd(device_id, cmd)


def poweron_screen_and_unlock(device_id):
    # log('unlock_screen()', device_id)
    poweron_phone_screen(device_id)
    time.sleep(1)

    cmd = 'wm dismiss-keyguard'
    _exe_adb_cmd(device_id, cmd)


def off_screen(device_id):
    if not is_screen_on(device_id):
        return
    cmd = 'input keyevent KEYCODE_POWER'
    _exe_adb_cmd(device_id, cmd)


def unlock_keyguard(device_id):
    cmd = 'wm dismiss-keyguard'
    _exe_adb_cmd(device_id, cmd)


def make_dirs(device_id, path: str):
    cmd = f'mkdir -p "{path}"'
    _exe_adb_cmd(device_id, cmd)


def delete_file_or_dir(device_id, path: str):
    cmd = f'rm -rf "{path}"'
    _exe_adb_cmd(device_id, cmd)


def poweroff_phone_screen(device_id):
    if not is_screen_on(device_id):
        return
    cmd = 'input keyevent KEYCODE_POWER'
    _exe_adb_cmd(device_id, cmd)
    time.sleep(0.5)


def enter_keyguard(device_id):
    if is_screen_on(device_id):
        cmd = 'input keyevent KEYCODE_POWER'
        _exe_adb_cmd(device_id, cmd)
        time.sleep(0.1)
    cmd = 'input keyevent KEYCODE_POWER'
    _exe_adb_cmd(device_id, cmd)


def is_in_keyguard(device_id):
    cmd = '"dumpsys activity | grep mTopFullscreenOpaqueWindowState"'
    lines = _exe_adb_cmd(device_id, cmd)
    return not bool(lines)


def granting_high_level_permission(device_id: str, package_name: str, permission: str):
    cmd = f'"appops set {package_name} {permission} allow"'
    _exe_adb_cmd(device_id, cmd)


def deny_high_level_permission(device_id: str, package_name: str, permission: str):
    cmd = f'"appops set {package_name} {permission} deny"'
    _exe_adb_cmd(device_id, cmd)


def granting_high_level_permissions(device_id: str, package_name: str, permissions: List[str]):
    for permission in permissions:
        cmd = f'"appops set {package_name} {permission} allow"'
        _exe_adb_cmd(device_id, cmd)


def poweroff_phone(device_id):
    cmd = f'{ADB_EXE} -s {device_id} reboot -p'
    _exe_pc_cmd(device_id, cmd)


def reboot_phone(device_id):
    cmd = f'{ADB_EXE} -s {device_id} reboot'
    _exe_pc_cmd(device_id, cmd)


def start_settings_activity(device_id, is_restart=True):
    if is_restart:
        stop_app(device_id, ANDROID_SETTINGS_PACKAGE)
    return start_activity(device_id, ANDROID_SETTINGS_ACTIVITY)


def install_apk(device_id, apk_file, force_install=True) -> bool:
    if force_install:
        cmd = f'{ADB_EXE} -s {device_id} install -t -r -g {apk_file}'
    else:
        cmd = f'{ADB_EXE} -s {device_id} install {apk_file}'
    _, exit_code = _exe_pc_cmd_with_exit_code(device_id, cmd)
    return bool(not exit_code)


def install_xapk(deviceid, apk_xapk_path):
    # 解压XAPK文件
    with zipfile.ZipFile(apk_xapk_path, 'r') as zip_ref:
        extract_path = apk_xapk_path.replace('.xapk', '')
        shutil.rmtree(extract_path, ignore_errors=True)
        zip_ref.extractall(extract_path)

    # 读取manifest.json以确定主APK
    manifest_path = os.path.join(extract_path, 'manifest.json')
    with open(manifest_path, 'r', encoding="utf-8") as manifest_file:
        manifest_data = json.load(manifest_file)

    main_apk_name = manifest_data.get('package_name', '')  # 默认主APK
    main_apk_name = main_apk_name + ".apk"
    # 收集所有需要安装的APK文件
    apk_files = []

    for root, _, files in os.walk(extract_path):
        for file in files:
            if file.endswith('.apk'):
                apk_files.append(os.path.join(root, file))

    # 确保主APK在第一个位置
    apk_files.sort(key=lambda x: 0 if main_apk_name in x else 1)

    # 使用ADB安装这些APK
    cmd = [ADB_EXE, '-s', deviceid, 'install-multiple']
    cmd.extend(apk_files)
    result = subprocess.run(cmd, capture_output=True, text=True)

    shutil.rmtree(extract_path)
    # 处理安装结果
    if "Success" in result.stdout:
        # print("APK安装成功：{main_apk_name}")
        return True
    else:
        # print(f"安装失败: {result.stderr}")
        return False


def uninstall_apk(device_id, apk_package_name):
    cmd = f'{ADB_EXE} -s ' + device_id + ' uninstall ' + apk_package_name
    _exe_pc_cmd(device_id, cmd)


def get_running_package_pid(device_id, package_name):
    cmd = f'pidof {package_name}'
    lines = _exe_adb_cmd(device_id, cmd)
    return lines[0].strip() if lines else ''


def start_apk_activity(device_id, pkg_name, activity, wait_time=True, flag=''):
    # flag 0x10200000 for old android version
    activity = pkg_name + '/' + activity

    am_cmd = 'am start'
    am_cmd = am_cmd + f' -f {flag}' if flag else am_cmd
    am_cmd = am_cmd + ' -W' if wait_time else am_cmd
    cmd = f'{am_cmd} {activity}'
    _exe_adb_cmd(device_id, cmd)


def start_activity(device_id, activity_with_package, wait_time=True, flag=''):
    am_cmd = 'am start'
    am_cmd = am_cmd + f' -f {flag}' if flag else am_cmd
    am_cmd = am_cmd + ' -W' if wait_time else am_cmd
    cmd = f'{am_cmd} {activity_with_package}'
    _exe_adb_cmd(device_id, cmd)


def start_launcher_activity(device_id, pkg_name, wait_time=True, flag=''):
    launcher_activity = get_launcher_activity(device_id, pkg_name)
    assert launcher_activity and launcher_activity != 'No activity found', f'Can not resolve launcher activity for {pkg_name}! May you not install this app.'
    start_activity(device_id, launcher_activity, wait_time, flag)


def stop_settings_activity(device_id):
    stop_app(device_id, 'com.android.settings')


def open_settings_activity(device_id, wait_time=True):
    start_apk_activity(device_id, 'com.android.settings', '.Settings', wait_time)


def launch_app(device_id, pkg_name, raise_exception=True):
    cmd = f'"monkey -p {pkg_name} -c android.intent.category.LAUNCHER 1 > /dev/null 2>&1"'
    result = _exe_adb_cmd_with_exit_code(device_id, cmd)[1] == 0
    if not result and raise_exception:
        raise Exception(f'Can not launch {pkg_name}')
    return result


# 读取当前手机电量为多少，返回值为 int型， 需要再加上 %
def read_battery(device_id):
    # cat /sys/class/power_supply/battery/capacity can read battery also!
    cmd = f'dumpsys battery'
    info = _exe_adb_cmd(device_id, cmd)
    for line in info:
        if line.strip().startswith('level:'):
            return int(line.strip().split()[1])
    # log(f'adb read empty, cmd: {cmd}, return{str(info)}', device_id)

    # read error, read node instead
    cmd = f'cat /sys/class/power_supply/battery/capacity'
    lines = _exe_adb_cmd(device_id, cmd)
    if lines:
        bat = ''.join(lines).strip()
        return int(bat)
    logs_p().log_error(f'read device error!! cmd: {cmd}, return{str(info)}', device_id)
    return 0


def is_charging(device_id):
    cmd = f'dumpsys battery'
    lines = _exe_adb_cmd(device_id, cmd)
    for line in lines:
        if line and 'powered:' in line and line.strip().endswith('true'):
            return True
    return False


def get_sim_count(device_id):
    _count = 0
    for sim_stat in getprop(device_id, 'gsm.sim.state').split(','):
        if sim_stat and sim_stat != 'ABSENT':
            _count += 1

    return _count


def get_enabled_sim_count(device_id):
    if is_sprd(device_id) or is_qcom(device_id):
        return getprop(device_id, 'gsm.sim.state').count('LOADED')
    return sum(1 for element in getprop(device_id, 'gsm.operator.alpha').split(',') if element)


def get_cn_sim_index(device_id):
    sim_count = get_sim_count(device_id)
    if sim_count == 0:
        return 0
    for i, t in enumerate(getprop(device_id, 'gsm.sim.operator.iso-country').split(',')):
        if t == 'cn':
            if sim_count == 1:
                return 1
            return i + 1
    return 0


def get_overseas_sim_index(device_id):
    sim_count = get_sim_count(device_id)
    if sim_count == 0:
        return 0
    for i, t in enumerate(getprop(device_id, 'gsm.sim.operator.iso-country').split(',')):
        if t and t != 'cn':
            if sim_count == 1:
                return 1
            return i + 1
    return 0


def get_sim_is_plugged(device_id, slot):
    """
    查询sim卡是否插入
    slot = 1表示卡1
    slot = 2表示卡2
    """
    return getprop(device_id, 'gsm.sim.state').split(",")[slot - 1] == 'LOADED'


def get_timestamp(device_id):
    cmd = f'date "+%s"'
    info = _exe_adb_cmd(device_id, cmd)
    info = ''.join(info)
    return int(info.strip())


# pc_ticks - device_ticks
def pc_time_tick_gap(device_id):
    gap = int(time.time()) - get_timestamp(device_id)
    # log(f"pc ticks - device ticks: tick gap is {gap}", device_id)
    return gap


def last_charge_protocol(device_id):
    cmd = f'"cat /sdcard/Documents/trda_test/bat_info_*"'
    lines = _exe_adb_cmd(device_id, cmd)
    pro_index = lines[0].split().index('charging_protocol')
    pro = ''
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].split()[pro_index] == 'Unknown' and lines[i - 1].split()[pro_index] != 'Unknown':
            pro = lines[i - 1].split()[pro_index]
            break
    assert pro, "!" * 20 + "error, do not detect ta"
    return pro


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
_sprd_android_log_flg = False


def set_sprd_android_log(flg):
    global _sprd_android_log_flg
    _sprd_android_log_flg = flg


def start_sprd_log(device_id, set_size_flag=True):
    if set_size_flag:
        try:
            rom_sz = rom_size_MB(device_id)
            sz = int(rom_sz / 2)
            cmd = f'am startservice -n com.reallytek.wg/.utils.LogControlService -e from adb -p com.reallytek.wg' \
                  f' --ei magic 903 -e maxsize {sz}'
            _exe_adb_cmd(device_id, cmd)
            logs_p().log(f"start sprd log, set size {sz}MB", device_id)
        except BaseException as e:
            logs_p().log_exception(e)

    android_log = 1 if _sprd_android_log_flg else 0
    cmd = f'am startservice ' \
          f'-n com.reallytek.wg/.utils.LogControlService ' \
          f'-e from adb -p com.reallytek.wg  --ei magic 902 -e android {android_log} ' \
          f'-e kernel 1 -e uboot 1 -e lastkmsg 1 -e thermal 0 -e bthci 0 -e apcap 0'
    _exe_adb_cmd(device_id, cmd)


def stop_sprd_log(device_id):
    cmd = f'am startservice -n com.reallytek.wg/.utils.LogControlService ' \
          f'-e from adb -p com.reallytek.wg  --ei magic 901'
    _exe_adb_cmd(device_id, cmd)
    time.sleep(20)


def clear_sprd_log(device_id):
    for l in SPRD_DEVICE_LOG_DIRS:
        cmd = f'rm {l} -rf'
        _exe_adb_cmd(device_id, cmd)


def readout_sprd_logs(device_id, sub_dir):
    from . import trde_utils
    sprd_log_dir = trde_utils.sprd_log_dir(sub_dir)
    for l in SPRD_DEVICE_LOG_DIRS:
        l = l.strip('\\*')
        cmd = f'ls {l} 2>&1'
        lines = _exe_adb_cmd(device_id, cmd)
        val = ''.join(lines).strip()
        if 'No such ' not in val:
            cmd = f'{ADB_EXE} -s {device_id} pull {l} {sprd_log_dir}'
            lines = _exe_pc_cmd(device_id, cmd)
            for line in lines:
                if line and 'failed to copy' in line:
                    logs_p().log('=' * 10 + ' PULL ERROR: ' + line)


# rom size of MB
def rom_size_MB(device_id) -> float:
    cmd = f'df -k /sdcard'
    lines = _exe_adb_cmd(device_id, cmd)
    if lines and len(lines) == 2:
        sz_index = lines[0].split().index('1K-blocks')
        sz_str = lines[1].split()[sz_index]
        sz = int(sz_str)
        return sz / 1024
    raise 'read rom size error!'


def ram_size_MB(device_id) -> float:
    cmd = '"cat /proc/meminfo | grep MemTotal | awk \'{print $2}\'"'
    lines = _exe_adb_cmd(device_id, cmd)
    return int(lines[0].strip()) / 1024


def nearest_power_of_2(value: float) -> int:
    if value <= 0:
        raise ValueError("The value must be a positive number.")
    upper_power = 2 ** math.ceil(math.log2(value))
    lower_power = 2 ** math.floor(math.log2(value))
    if (upper_power - value) < (value - lower_power):
        return upper_power
    else:
        return lower_power


def get_ram_nominal_size_MB(device_id) -> int:
    """
    获取设备标称的内存大小（MB）
    """
    act_size = ram_size_MB(device_id)
    size_num_gb_float = act_size / 1024 / 0.93132 - 0.2
    return round(size_num_gb_float) * 1024


def get_ram_nominal_size_GB(device_id) -> float:
    """
    获取设备标称的内存大小（GB）
    """
    return get_ram_nominal_size_MB(device_id) / 1024


def get_rom_nominal_size_MB(device_id) -> int:
    """
    获取设备标称的内部储存空间大小（MB）
    """
    size_num_gb_float = (rom_size_MB(device_id) + 10240) / 0.93132
    return nearest_power_of_2(size_num_gb_float)


def get_rom_nominal_size_GB(device_id) -> float:
    """
    获取设备标称的内部储存空间大小（GB）
    """
    return get_rom_nominal_size_MB(device_id) / 1024


# https://online.mediatek.com/FAQ#/SW/FAQ06939
# 127-all, 1-MobileLog, 2-ModemLog, 4-NetworkLog, 8-METlog, 16-GPSLog, 32-ConnsysFWLog`, 64-BTHostLog
def start_mtklog_mobilelog(device_id, set_size_flag=True, log_types_number=1):
    # log_types_number = 117
    cmd = f'am broadcast -a com.debug.loggerui.ADB_CMD -e cmd_name start ' \
          f'--ei cmd_target {log_types_number} -n com.debug.loggerui/.framework.LogReceiver'

    _exe_adb_cmd(device_id, cmd)

    if set_size_flag:
        try:
            rom_sz = rom_size_MB(device_id)
            sz = int(rom_sz / 2)
            cmd = f'am broadcast -a com.debug.loggerui.ADB_CMD' \
                  f' -e cmd_name set_log_size_{sz}  --ei cmd_target {log_types_number}' \
                  f' -n com.debug.loggerui/.framework.LogReceiver'
            _exe_adb_cmd(device_id, cmd)
            logs_p().log(f'set log size to {sz}MB')
        except BaseException as e:
            logs_p().log(e)


def stop_mtklog(device_id):
    cmd = 'am broadcast -a com.debug.loggerui.ADB_CMD -e cmd_name stop' \
          ' --ei cmd_target 127 -n com.debug.loggerui/.framework.LogReceiver'
    _exe_adb_cmd(device_id, cmd)


def adb_root(device_id):
    cmd = f'{ADB_EXE} -s {device_id} root'
    _exe_pc_cmd(device_id, cmd)


def write_node(device_id, node_name, value):
    # /sys/class/power_supply/tran-auto-test/
    cmd = f'"echo {value} > {node_name}"'
    _exe_adb_cmd(device_id, cmd)


DEVICE_LOG_DIRS = [
    '/data/aee_exp/*',
    '/data/anr/*',
    '/data/vendor/mtklog/aee_exp/*',
    '/data/vendor/aee_exp/*',
    '/sdcard/mtklog/aee_exp/*',
    '/sdcard/mtklog/*',
    '/sdcard/debuglogger/*',
    '/data/debuglogger/*',
]


def clear_mtklog_cache_and_history_logs(device_id):
    # cmd = 'am broadcast -a com.debug.loggerui.ADB_CMD -e cmd_name clear_all_logs' \
    #       ' --ei cmd_target 127 -n com.debug.loggerui/.framework.LogReceiver'
    cmd = 'logcat -b all -c'
    _exe_adb_cmd(device_id, cmd)
    for d in DEVICE_LOG_DIRS:
        cmd = f'rm {d} -rf'
        _exe_adb_cmd(device_id, cmd)
    time.sleep(1)


def readout_mtklog_and_crash_db(device_id, sub_dir):
    pc_dir = mtk_log_dir(sub_dir)
    os.makedirs(pc_dir, exist_ok=True)

    for d in DEVICE_LOG_DIRS:
        d = d.strip('\\*')
        cmd = f'{ADB_EXE} -s {device_id} pull {d} {pc_dir}'
        _exe_pc_cmd(device_id, cmd)
    time.sleep(1)
    return pc_dir

def get_bugreport(device_id, pc_dir):
    os.makedirs(pc_dir, exist_ok=True)
    cmd = f'cd {pc_dir} && {ADB_EXE} -s {device_id} bugreport'
    return _exe_pc_cmd(device_id, cmd)

def started_sec(device_id):
    cmd = f'cat /proc/uptime'
    lines = _exe_adb_cmd(device_id, cmd)
    s = ''.join(lines).strip().split()[0]
    t = float(s)
    return t


def device_exist(device_id):
    return device_id in adb_devices()


def wait_device(device_id):
    cmd = f'{ADB_EXE} -s {device_id} wait-for-device'
    _exe_pc_cmd(device_id, cmd)


def adb_kill_server():
    devices = adb_devices()

    cmd = f'{ADB_EXE} kill-server'
    _exe_pc_cmd('', cmd)

    time.sleep(1)

    devices_2 = adb_devices()
    wifi_devices = set(devices) - set(devices_2)
    for d in wifi_devices:
        cmd = f'{ADB_EXE} connect {d}'
        # g_thread_lock.locked()
        os.popen(cmd).read()
        # g_thread_lock.release()
    return wifi_devices


def read_auto_test_node(device_id, node_name):
    cmd = f'cat /sys/class/power_supply/tran-auto-test/{node_name}'
    lines = _exe_adb_cmd(device_id, cmd)
    return ''.join(lines)


def read_node(device_id, node_path_name):
    cmd = f'cat {node_path_name}'
    lines = _exe_adb_cmd(device_id, cmd)
    return ''.join(lines).strip()


def set_forward_port(device_id, port: int):
    cmd = f'{ADB_EXE} -s {device_id} forward tcp:{port} tcp:{port}'
    _exe_pc_cmd(device_id, cmd)


def set_forward_localport_deviceport(device_id, localport: int, deviceport: int):
    cmd = f'{ADB_EXE} -s {device_id} forward tcp:{localport} tcp:{deviceport}'
    _exe_pc_cmd(device_id, cmd)


def kill_app_by_key(device_id, key_str):
    cmd = '" ps -ef | grep \'{}\'"'.format(key_str)
    lines = _exe_adb_cmd(device_id, cmd)

    for line in lines:
        pid_str = line.split()[1].strip()
        if pid_str:
            cmd = '" kill {} >/dev/null 2>&1"'.format(pid_str)
            _exe_adb_cmd(device_id, cmd)


def package_is_installed(device_id, package_name):
    cmd = f'"pm list packages | grep -F {package_name}"'
    lines = _exe_adb_cmd(device_id, cmd)
    for line in lines:
        if line.strip() and line.strip().endswith(package_name) and ' grep ' not in line:
            return True
    return False


def stop_app(device_id, package_name):
    cmd = f'am force-stop {package_name}'
    _exe_adb_cmd(device_id, cmd)


def soft_stop_app(device_id, package_name):
    cmd = f'am stop-app {package_name}'
    _exe_adb_cmd(device_id, cmd)


def is_package_activity_exist(device_id, package_name, activity_name):
    cmd = f'"dumpsys package {package_name} | grep -F {activity_name}"'
    lines = _exe_adb_cmd(device_id, cmd)
    for line in lines:
        if line.strip() and f'{activity_name} ' in line.strip() and ' grep ' not in line:
            return True
    return False


def is_prop_enabled(device_id, prop_name) -> bool:
    cmd = f'getprop {prop_name}'
    lines = _exe_adb_cmd(device_id, cmd)
    result = lines and lines[0].strip() == '1'
    return bool(result)


def is_support_aod(device_id) -> bool:
    # return package_is_installed(device_id, 'com.transsion.aod')
    cmd = f'"getprop | grep aod_support"'
    lines = _exe_adb_cmd(device_id, cmd)
    result = lines and lines[0].strip().endswith('[1]')
    return bool(result)


def is_support_aod_always_show(device_id) -> bool:
    # return package_is_installed(device_id, 'com.transsion.aod')
    return is_prop_enabled(device_id, 'ro.aod_alwaysshow_support')


def is_support_hbm(device_id) -> bool:
    return is_prop_enabled(device_id, 'ro.vendor.transsion.hbm_mode_hal.support')


def get_lcm_full_name(device_id, screen_index: int) -> str:
    if screen_index != 0 and screen_index != 1:
        raise ValueError(f'Not support screen index: {screen_index}')
    screen_extra = "_sub" if screen_index == 1 else ""
    cmd = f'"cat /sys/kernel/tran_display/lcm{screen_extra}_name 2>/dev/null"'
    lines = _exe_adb_cmd(device_id, cmd)
    if lines:
        return lines[0].strip()
    adb_root(device_id)
    if screen_index == 0:
        cmd = '"cat proc/pl_lk | grep lcmname"'
        lines = _exe_adb_cmd(device_id, cmd)
        if lines and 'Permission denied' not in lines[0]:
            return lines[0].strip().split(' ')[-1]
    else:
        cmd = '"cat /proc/pl_lk | grep \'we will check lcm\' | grep i=1"'
        lines = _exe_adb_cmd(device_id, cmd)
        if lines and 'Permission denied' not in lines[0]:
            return lines[0].strip().split(' ')[-2][0:-1]
    raise Exception(f'Failed to get lcm name for screen index {screen_index}, you may need debug version or root user')


def get_mtk_tp_vendor(device_id) -> str:
    cmd = "cat /sys/devices/platform/mtk-tpd/tp_vendor"
    lines = _exe_adb_cmd(device_id, cmd)
    return lines[0].strip()


def get_lcm_pretty_name(device_id, screen_index: int) -> str:
    lcm_name = get_lcm_full_name(device_id, screen_index).lower()
    lcm_header = lcm_name.split('_')[0]
    tp_vendor_header = get_mtk_tp_vendor(device_id).split('_')[0].lower()
    if f"_{tp_vendor_header}_" in lcm_name:
        lcm_vendor = tp_vendor_header
    elif "_tm_" in lcm_name:
        lcm_vendor = "tm"
    elif "_csot_" in lcm_name:
        lcm_vendor = "csot"
    elif "_gvo_" in lcm_name:
        lcm_vendor = "gvo"
    else:
        dsc_index = lcm_name.find("_dsc_")
        if dsc_index != -1:
            dsc_index += 4
            lcm_vendor = lcm_name[dsc_index:lcm_name.index("_", dsc_index)]
        else:
            vdo_cmd_index = lcm_name.find("_vdo_")
            if vdo_cmd_index == -1:
                vdo_cmd_index = lcm_name.find("_cmd_")
            if vdo_cmd_index == -1:
                raise Exception(f"Failed to get lcm vendor from {lcm_name}")
            vdo_cmd_index += 4
            lcm_vendor = lcm_name[vdo_cmd_index:lcm_name.index("_", vdo_cmd_index)]
    extra_info = ""
    if "_vdo_" in lcm_name:
        extra_info = "_vdo"
    elif "_cmd_" in lcm_name:
        extra_info = "_cmd"
    return f"{lcm_vendor}_{lcm_header}{extra_info}"


def get_skin_temperature(device_id) -> float:
    """
    获取指定Android设备的温度值，优先获取SKIN的温度，若没有则获取Battery的温度。

    :param device_id: 设备的序列号
    :return: 温度值（float）
    :raises: RuntimeError 如果无法找到SKIN或Battery的温度
    """
    try:
        # 执行ADB命令获取thermalservice信息
        result = subprocess.run(
            [ADB_EXE, '-s', device_id, 'shell', 'dumpsys', 'thermalservice'],
            capture_output=True, text=True, check=True
        )
        output = result.stdout

        # 提取 "Current temperatures from HAL:" 段落
        hal_start = output.find("Current temperatures from HAL:")
        if hal_start == -1:
            raise RuntimeError("Unable to find the 'Current temperatures from HAL:' section.")

        hal_end = output.find("Current cooling devices from HAL:", hal_start)
        hal_section = output[hal_start:hal_end if hal_end != -1 else None]

        # 定义正则表达式，用于匹配温度信息
        skin_pattern = re.compile(r'Temperature{mValue=([\d.]+),[^}]*mName=[^}]*skin[^}]*}', re.IGNORECASE)
        battery_pattern = re.compile(r'Temperature{mValue=([\d.]+),[^}]*mName=[^}]*battery[^}]*}', re.IGNORECASE)

        # 尝试查找SKIN温度
        skin_match = skin_pattern.search(hal_section)
        if skin_match:
            return float(skin_match.group(1))

        # 若找不到SKIN温度，则尝试查找Battery温度
        battery_match = battery_pattern.search(hal_section)
        if battery_match:
            return float(battery_match.group(1))

        # 如果都找不到，抛出错误
        raise RuntimeError(
            "Unable to find SKIN or Battery temperature in the 'Current temperatures from HAL:' section.")

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ADB command failed: {e}")


def set_aod_enabled(device_id, enabled: bool):
    cmd = f'settings put secure aod_is_show {1 if enabled else 0}'
    _exe_adb_cmd(device_id, cmd)
    cmd = f'settings put secure doze_enabled {1 if enabled else 0}'
    _exe_adb_cmd(device_id, cmd)


def is_aod_enabled(device_id) -> bool:
    cmd = 'settings get secure aod_is_show'
    lines = _exe_adb_cmd(device_id, cmd)
    return bool(lines and lines[0].strip() == '1')


def set_aod_brightness(device_id, brightness: int):
    cmd = f'settings put system aod_brightness {brightness}'
    _exe_adb_cmd(device_id, cmd)


def is_support_double_click_wake(device_id) -> bool:
    #return is_package_activity_exist(device_id, 'com.transsion.microintelligence', '.TappingWakeActivity')
    return is_prop_enabled(device_id, "ro.tapping_wake_support")


def is_double_click_wake_enabled(device_id) -> bool:
    cmd = f'"settings list system | grep -F os_action_tapping_wake"'
    lines = _exe_adb_cmd(device_id, cmd)
    result = lines and "os_action_tapping_wake=1" in lines[0]
    return bool(result)


# def set_double_click_wake_enabled(device_id, enable: bool):
#     cmd = f'"settings put system os_action_tapping_wake {1 if enable else 0}"'
#     _exe_adb_cmd(device_id, cmd)


def get_installed_package_version(device_id, package_name) -> str:
    cmd = f'"dumpsys package {package_name} | grep versionName"'
    lines = _exe_adb_cmd(device_id, cmd)
    if lines:
        line = lines[0]
        return line[line.index("=") + 1:].strip()
    return ""


def get_installed_package_version_code(device_id, package_name) -> int:
    cmd = f'"dumpsys package {package_name} | grep versionCode"'
    lines = _exe_adb_cmd(device_id, cmd)
    if lines:
        line = lines[0]
        index_start = line.index("=") + 1
        index_end = line.index(" ", index_start)
        return int(line[index_start:index_end])
    return -1


def package_is_running(device_id, package_name):
    cmd = f'" ps -ef | grep {package_name}"'
    lines = _exe_adb_cmd(device_id, cmd)
    for line in lines:
        if line.strip() and line.strip().endswith(package_name) and ' grep ' not in line:
            return True
    return False


def set_screen_off_timeout(device_id, timeout):
    cmd = f'"settings put system screen_off_timeout {timeout}"'
    _exe_adb_cmd(device_id, cmd)


def get_screen_off_timeout(device_id):
    cmd = f'"settings get system screen_off_timeout"'
    lines = _exe_adb_cmd(device_id, cmd)
    assert lines, f"get_screen_off_timeout failed, no output"
    return int(lines[0])


def get_screen_count(device_id):
    """
    获取屏幕数量（比如2个屏幕一般是双屏手机或者带2个屏幕的折叠屏手机）
    :param device_id: 设备id
    :return: 屏幕数量
    """
    cmd = '"dumpsys display | grep DisplayDeviceInfo{"'
    lines = _exe_adb_cmd(device_id, cmd)
    return len(lines)


def set_screen_status(device_id, status: MultiScreenStatus):
    if get_screen_count(device_id) > 1:
        str_status = "reset" if status == MultiScreenStatus.RESET else str(status.value[0])
        cmd = f'cmd device_state state {str_status}'
        _exe_adb_cmd(device_id, cmd)


def set_screen_fps_mode(device_id, mode: int):
    cmd = f'service call SurfaceFlinger 1035 i32 {mode}'
    _exe_adb_cmd(device_id, cmd)


def get_screen_resolution(device_id, screen_index: int):
    cmd = '"dumpsys display | grep DisplayDeviceInfo{"'
    lines = _exe_adb_cmd(device_id, cmd)
    line = lines[screen_index]
    w = string_utils.get_substring_between_symbols(line, "physicalDisplayWidth=", " ")
    h = string_utils.get_substring_between_symbols(line, "physicalDisplayHeight=", " ")
    return int(w), int(h)


def get_screen_diagonal_len_in_inch(device_id, screen_index: int) -> float:
    cmd = '"dumpsys display | grep DisplayDeviceInfo{"'
    lines = _exe_adb_cmd(device_id, cmd)
    line = lines[screen_index]
    w = int(string_utils.get_substring_between_symbols(line, "physicalDisplayWidth=", " "))
    h = int(string_utils.get_substring_between_symbols(line, "physicalDisplayHeight=", " "))
    density_index = line.index("density ")
    dpi_index = line.index(" dpi,", density_index)
    x_dpi = float(string_utils.get_substring_between_symbols(line, ", ", " x ", density_index, dpi_index))
    y_dpi = float(string_utils.get_substring_between_symbols(line, " x ", " dpi", density_index, dpi_index + 5))
    diagonal_len = math.sqrt(pow(w / x_dpi, 2) + pow(h / y_dpi, 2))
    return round(diagonal_len, 2)


def get_screen_default_fps_mode(device_id, screen_index: int) -> int:
    cmd = '"dumpsys display | grep DisplayDeviceInfo{"'
    lines = _exe_adb_cmd(device_id, cmd)
    assert len(lines) > screen_index, f"屏幕数量不足，当前屏幕数量：{len(lines)}，需要获取的屏幕索引：{screen_index}"
    line = lines[screen_index]
    mode_id_index_start = line.index("defaultModeId ")
    mode_id_index_end = line.index(",", mode_id_index_start)
    mode_id = int(line[mode_id_index_start + len("defaultModeId "):mode_id_index_end])
    return mode_id - 1


def is_settings_screen_fps_auto(device_id):
    return get_settings_screen_fps(device_id) == '10000'


def set_settings_screen_fps_auto(device_id):
    if not is_settings_screen_fps_auto(device_id):
        force_restore_screen_fps_mode(device_id)


def get_settings_screen_fps(device_id):
    return get_settings_value(device_id, 'system', 'tran_refresh_mode')


def set_settings_screen_fps(device_id, fps: int):
    set_settings_value(device_id, 'system', 'tran_refresh_mode', str(fps))


def force_restore_screen_fps_mode(device_id):
    # set_screen_fps_mode(device_id, get_screen_default_fps_mode(device_id, screen_index))
    set_screen_fps_mode(device_id, -1)
    cmd = f'"settings put system tran_refresh_mode 60"'
    _exe_adb_cmd(device_id, cmd)
    cmd = f'"settings put system tran_refresh_mode 10000"'
    _exe_adb_cmd(device_id, cmd)


def get_supported_screen_fps_mode_count(device_id, screen_index: int):
    cmd = '"dumpsys display | grep DisplayDeviceInfo{"'
    lines = _exe_adb_cmd(device_id, cmd)
    assert len(lines) > screen_index, f"屏幕数量不足，当前屏幕数量：{len(lines)}，需要获取的屏幕索引：{screen_index}"
    line = lines[screen_index]
    mode_id_index_pre_start = line.index("supportedModes ")
    from powertrde.utils.algorithm_utils import match_char_symbol_pair
    _, mode_id_index_end = match_char_symbol_pair(line, '[', ']', mode_id_index_pre_start)
    last_id_index_start = line.rindex('{id=', mode_id_index_pre_start, mode_id_index_end)
    last_id_index_end = line.index(',', last_id_index_start)
    count = int(line[last_id_index_start + len('{id='):last_id_index_end])
    return count


def get_supported_screen_fps_mode_list(device_id, screen_index: int) -> list:
    cmd = '"dumpsys display | grep DisplayDeviceInfo{"'
    lines = _exe_adb_cmd(device_id, cmd)
    assert len(lines) > screen_index, f"屏幕数量不足，当前屏幕数量：{len(lines)}，需要获取的屏幕索引：{screen_index}"
    line = lines[screen_index]
    mode_id_index_pre_start = line.index("supportedModes ")
    from powertrde.utils.algorithm_utils import match_char_symbol_pair
    mode_id_index_start, mode_id_index_end = match_char_symbol_pair(line, '[', ']', mode_id_index_pre_start)
    return _parse_shell_display_info(line[mode_id_index_start:mode_id_index_end + 1])


def _parse_shell_display_info(input_str: str) -> list:
    # 将 `=` 替换为 `:`
    formatted_str = input_str.replace('=', ':')
    # 将 `{` 和 `}` 之间的字符串用引号括起来
    formatted_str = re.sub(r'([{,]\s*)(\w+)\s*:', r'\1"\2":', formatted_str)
    # 处理嵌套的数组和其他值
    formatted_str = re.sub(r'([{,]\s*)\'(\w+)\'\s*:', r'\1"\2":', formatted_str)
    formatted_str = re.sub(r':\s*(\w+)\s*([\]},])', r':"\1"\2', formatted_str)
    # 将单引号改为双引号
    formatted_str = formatted_str.replace("'", '"')
    # 处理数字和布尔值
    formatted_str = re.sub(r':\s*"(true|false|[0-9.]+)"', r':\1', formatted_str)
    # 将处理后的字符串解析为 JSON
    return json.loads(formatted_str)


def get_screen_fps_mode_and_fps(device_id, screen_index: int) -> Tuple[int, float]:
    cmd = '"dumpsys display | grep DisplayDeviceInfo{"'
    lines = _exe_adb_cmd(device_id, cmd)
    assert len(lines) > screen_index, f"屏幕数量不足，当前屏幕数量：{len(lines)}，需要获取的屏幕索引：{screen_index}"
    line = lines[screen_index]
    mode_id_index_start = line.index("modeId ")
    mode_id_index_end = line.index(",", mode_id_index_start)
    mode_id = int(line[mode_id_index_start + len("modeId "):mode_id_index_end])
    mode_fps_index_pre_start = line.index(f"{{id={mode_id}")
    mode_fps_index_start = line.index("fps=", mode_fps_index_pre_start)
    mode_fps_index_end = line.index(",", mode_fps_index_start)
    mode_fps = float(line[mode_fps_index_start + len("fps="):mode_fps_index_end])
    return mode_id - 1, mode_fps


def set_screen_brightness(device_id, brightness: int):
    cmd = f'"echo {brightness} > /sys/class/leds/lcd-backlight/brightness"'
    _exe_adb_cmd(device_id, cmd)


def quit_hbm_brightness_mode_and_set_brightness(device_id, brightness: int):
    now_brightness = brightness
    if now_brightness <= 1:
        temp_brightness = 2
    else:
        temp_brightness = now_brightness - 1
    settings_set_screen_brightness(device_id, temp_brightness)
    settings_set_screen_brightness(device_id, now_brightness)


def quit_hbm_brightness_mode(device_id):
    quit_hbm_brightness_mode_and_set_brightness(device_id, settings_get_screen_brightness(device_id))


def enter_hbm_brightness_mode(device_id):
    set_screen_brightness(device_id, get_screen_max_brightness(device_id))


def settings_set_screen_brightness(device_id, brightness: int):
    cmd = f'"settings put system screen_brightness {brightness}"'
    _exe_adb_cmd(device_id, cmd)


def get_screen_brightness(device_id) -> int:
    cmd = f'"cat /sys/class/leds/lcd-backlight/brightness"'
    lines = _exe_adb_cmd(device_id, cmd)
    assert lines, f'get_screen_brightness failed, no lines'
    return int(lines[0])


def settings_get_screen_brightness(device_id) -> int:
    cmd = '"settings get system screen_brightness"'
    lines = _exe_adb_cmd(device_id, cmd)
    assert lines, f'get_screen_brightness failed, no lines'
    return int(lines[0])


def get_screen_max_brightness(device_id) -> int:
    cmd = f'"cat /sys/class/leds/lcd-backlight/max_brightness"'
    lines = _exe_adb_cmd(device_id, cmd)
    assert lines, f'get_screen_max_brightness failed, no lines'
    return int(lines[0])


def settings_get_screen_auto_brightness(device_id) -> bool:
    cmd = f'"settings get system screen_brightness_mode"'
    lines = _exe_adb_cmd(device_id, cmd)
    return int(lines[0]) != 0


def settings_set_screen_auto_brightness(device_id, enabled: bool):
    cmd = f'"settings put system screen_brightness_mode {1 if enabled else 0}"'
    _exe_adb_cmd(device_id, cmd)


def set_fps_show(device_id, enabled: bool):
    cmd = f'service call SurfaceFlinger 1034 i32 {1 if enabled else 0}'
    _exe_adb_cmd(device_id, cmd)


def is_fps_show(device_id):
    cmd = '"dumpsys SurfaceFlinger | grep -i RefreshRateOverlay#"'
    ret = _exe_adb_cmd(device_id, cmd)
    return bool(ret and _exe_adb_cmd(device_id, cmd)[0].strip())


def package_is_foreground(device_id, package_name):
    package_name += '/'
    cmd = f'"dumpsys activity | grep mFocusedWindow | grep -F {package_name}"'
    lines = _exe_adb_cmd(device_id, cmd)
    for line in lines:
        if package_name in line and ' grep ' not in line:
            return True
    return False


def get_notify_number(device_id, pkg=None):
    """查询的时候，需要把group去掉，因为如果一个引用有一个通知，会查询到1个，如果有1个以上会加一个group通知，整体数量会加1"""
    if not pkg:
        res = exec_cmd(device_id,
                       "dumpsys notification | grep 'NotificationRecord(' | grep -v 'tag=ranker_group'| wc -l")
    else:
        res = exec_cmd(device_id,
                       f"dumpsys notification | grep 'NotificationRecord(' | grep -v 'group'| grep {pkg}| wc -l")
    return int(res[0])


def grant_permissions(device_id, package_name, permissions: List[str]):
    for permission in permissions:
        cmd = f'"pm grant {package_name} {permission}"'
        _exe_adb_cmd(device_id, cmd)


def grant_android_permissions(device_id, package_name, android_permissions: List[str]):
    for permission in android_permissions:
        cmd = f'"pm grant {package_name} android.permission.{permission}"'
        _exe_adb_cmd(device_id, cmd)


def revoke_android_permissions(device_id, package_name, android_permissions: List[str]):
    for permission in android_permissions:
        cmd = f'"pm revoke {package_name} android.permission.{permission}"'
        _exe_adb_cmd(device_id, cmd)


def activity_is_foreground(device_id, activity_name):
    activity_name += '}'
    cmd = f'"dumpsys activity | grep mFocusedWindow | grep -F {activity_name}"'
    lines = _exe_adb_cmd(device_id, cmd)
    for line in lines:
        if line.strip() and line.strip().endswith(activity_name) and ' grep ' not in line:
            return True
    return False


def get_foreground_package_and_activity(device_id):
    cmd = '"dumpsys activity | grep mFocusedWindow"'
    lines = _exe_adb_cmd(device_id, cmd)
    return lines[0].strip().split()[2].replace('}', '')


def get_settings_value(device_id, category, item):
    cmd = f'"settings get {category} {item}"'
    lines = _exe_adb_cmd(device_id, cmd)
    return lines[0].strip()


def set_settings_value(device_id, category, item, value):
    cmd = f'"settings put {category} {item} {value}"'
    _exe_adb_cmd(device_id, cmd)


def get_foreground_package(device_id):
    return get_foreground_package_and_activity(device_id).split('/')[0]


def get_foreground_activity(device_id):
    return get_foreground_package_and_activity(device_id).split('/')[1]


def activity_is_top_fullscreen(device_id, activity_name):
    activity_name += '}'
    cmd = f'"dumpsys activity | grep mTopFullscreenOpaqueWindowState | grep -F {activity_name}"'
    lines = _exe_adb_cmd(device_id, cmd)
    for line in lines:
        if line.strip() and line.strip().endswith(activity_name) and ' grep ' not in line:
            return True
    return False


def list_dir(device_id, dir_path) -> List[Tuple[str, bool]]:
    """返回目录下的所有文件，返回元组列表，元组元素为文件名、是否是文件夹"""
    if not dir_path.endswith('/'):
        dir_path += '/'
    cmd = f'"ls -l {dir_path}"'
    lines = _exe_adb_cmd(device_id, cmd)
    # 需要兼容文件夹为空或者文件夹不存在的情况
    if not lines:
        return []
    lines = lines[1:] if lines[0].startswith('total') else lines
    return [
        (line.split()[-1], line.startswith('d'))
        for line in lines
        if line.startswith('d') or line.startswith('-')
    ]


def clear_app_data(device_id, package):
    cmd = f'pm clear {package}'
    exec_cmd(device_id, cmd)


def play_music(device_id, music_path_file='file:///sdcard/resource/audio.mp3'):
    cmd = f'am start -a "android.intent.action.VIEW" -t "audio/mp3" ' \
          f'-d "{music_path_file}" -n com.tencent.qqmusiclite/.SplashActivity'
    _exe_adb_cmd(device_id, cmd)
    time.sleep(3)


def stop_music(device_id):
    pkg_name = 'com.tencent.qqmusiclite'
    activity_name = 'com.tencent.qqmusiclite.SplashActivity'
    if package_is_running(device_id, pkg_name):
        start_apk_activity(device_id, pkg_name, activity_name)
        time.sleep(2)
        kill_app_by_key(device_id, pkg_name)
        time.sleep(2)


def play_video(device_id, video_path_file='file:///sdcard/resource/video.mp4'):
    cmd = f'am start -a "android.intent.action.VIEW" -t "video/*" ' \
          f'-d "{video_path_file}" -n com.google.android.apps.nbu.files/.gateway.preview.PreviewActivity'
    _exe_adb_cmd(device_id, cmd)
    time.sleep(3)


def camera_start_capture_preview(device_id):
    cmd = f'am start -a android.media.action.STILL_IMAGE_CAMERA'
    _exe_adb_cmd(device_id, cmd)
    time.sleep(3)


def camera_capture_key(device_id):
    cmd = f'input keyevent KEYCODE_CAMERA '
    _exe_adb_cmd(device_id, cmd)
    time.sleep(1)


def camera_start_record_video(device_id):
    cmd = f'am start -a android.media.action.VIDEO_CAPTURE'
    _exe_adb_cmd(device_id, cmd)
    time.sleep(3)
    camera_capture_key(device_id)


def browser_web(device_id, web_url='http://news.163.com'):
    cmd = f'am start -a android.intent.action.VIEW -d {web_url} -n com.android.chrome/com.google.android.apps.chrome.Main'
    _exe_adb_cmd(device_id, cmd)
    time.sleep(2)


def set_dialer(device_id, dialer_package='com.sh.smart.caller'):
    cmd = f'cmd role add-role-holder android.app.role.DIALER {dialer_package}'
    _exe_adb_cmd(device_id, cmd)
    time.sleep(1)


# start 抖音, douyin
def start_tiktok(device_id):
    cmd = f'am start -f 0x10200000 -W com.ss.android.ugc.aweme/.splash.SplashActivity'
    _exe_adb_cmd(device_id, cmd)
    time.sleep(5)
    press_back_key(device_id)  # 退出可能的弹框
    time.sleep(1)


def mk_automator_dir(device_id):
    cmd = f'mkdir {DEVICE_AUTOMATOR_DIR}'
    _exe_adb_cmd(device_id, cmd)


def start_continue_scroll_screen(device_id):
    gap = 15
    cmd = f'am broadcast -a com.trs.trde.SCROLL_SCREEN ' \
          f'-n com.trs.trde/.MainReceiver --ei gap {gap}'
    _exe_adb_cmd(device_id, cmd)


def stop_continue_scroll_screen(device_id):
    cmd = f'am broadcast -a com.trs.trde.SCROLL_SCREEN_STOP -n com.trs.trde/.MainReceiver'
    _exe_adb_cmd(device_id, cmd)


def start_continue_capture(device_id):
    gap = 10
    cmd = f'am broadcast -a com.trs.trde.CONTINUE_CAPTURE ' \
          f'-n com.trs.trde/.MainReceiver --ei gap {gap}'
    _exe_adb_cmd(device_id, cmd)


def stop_continue_capture(device_id):
    cmd = f'am broadcast -a com.trs.trde.CONTINUE_CAPTURE_STOP -n com.trs.trde/.MainReceiver'
    _exe_adb_cmd(device_id, cmd)


def press_key(device_id, keycode):
    cmd = f'input keyevent {keycode}'
    _exe_adb_cmd(device_id, cmd)


def press_key_close_anr(device_id):
    cmd = f'input keyevent 187'
    _exe_adb_cmd(device_id, cmd)


def press_back_key(device_id):
    cmd = 'input keyevent KEYCODE_BACK'
    _exe_adb_cmd(device_id, cmd)


def press_app_switch_key(device_id):
    cmd = 'input keyevent KEYCODE_APP_SWITCH'
    _exe_adb_cmd(device_id, cmd)


def press_end_call_key(device_id):
    cmd = 'input keyevent KEYCODE_ENDCALL'
    _exe_adb_cmd(device_id, cmd)


def press_menu_key(device_id):
    """该键可以用来开屏和解锁屏幕"""
    cmd = 'input keyevent KEYCODE_MENU'
    _exe_adb_cmd(device_id, cmd)


def press_recent_key(device_id):
    """该键可以用来开屏和解锁屏幕"""
    cmd = 'input keyevent 187'
    _exe_adb_cmd(device_id, cmd)


def is_phone_calling(device_id):
    cmd = '"dumpsys telephony.registry | grep \'mCallState\'"'
    line = ''.join(_exe_adb_cmd(device_id, cmd))
    if '=1' in line or '=2' in line:
        return True
    return False


def double_press_back_key(device_id):
    back_cmd = 'input keyevent KEYCODE_BACK'
    cmd = f'"{back_cmd} && {back_cmd}"'
    _exe_adb_cmd(device_id, cmd)


def press_home_key(device_id):
    cmd = f'input keyevent KEYCODE_HOME'
    _exe_adb_cmd(device_id, cmd)


# def open_master_batt(device_id, model):
#     node_a, node_b = prj_switch_battery_node(model)
#     cmd = f'"echo 1 > ' \
#           f'{node_a}"'
#     _exe_adb_cmd(device_id, cmd)
#     return cmd
#
#
# def close_master_batt(device_id, model):
#     node_a, node_b = prj_switch_battery_node(model)
#     cmd = f'"echo 0 > ' \
#           f'{node_a}"'
#     _exe_adb_cmd(device_id, cmd)
#     return cmd
#
#
# def read_master_batt_flag(device_id, model):
#     node_a, node_b = prj_switch_battery_node(model)
#     cmd = f'"cat ' \
#           f'{node_a}"'
#     lines = _exe_adb_cmd(device_id, cmd)
#     flag_str = ''.join(lines).strip().split('=')[1].strip().strip('\x00')
#     if flag_str == '1':
#         return True
#     else:
#         return False


def read_serial_no(device_id):
    cmd = f'getprop ro.serialno'
    lines = _exe_adb_cmd(device_id, cmd)
    serial = ''.join(lines).strip()
    return serial


def is_wifi_open(device_id):
    return get_settings_value(device_id, 'global', 'wifi_on') == '1'


def is_mobile_data_open(device_id):
    return get_settings_value(device_id, 'global', 'mobile_data') == '1'


def is_bluetooth_open(device_id):
    return get_settings_value(device_id, 'global', 'bluetooth_on') == '1'


def is_hotspot_open(device_id):
    return getprop(device_id, 'init.svc.hostapd') == 'running'


def open_close_wifi(device_id, is_open):
    enable_str = 'enable' if is_open else 'disable'
    cmd = f'svc wifi {enable_str}'
    _exe_adb_cmd(device_id, cmd)


def open_close_bluetooth(device_id, is_open):
    enable_str = 'enable' if is_open else 'disable'
    cmd = f'svc bluetooth {enable_str}'
    _exe_adb_cmd(device_id, cmd)


def open_close_mobile_data(device_id, is_open):
    enable_str = 'enable' if is_open else 'disable'
    cmd = f'svc data {enable_str}'
    _exe_adb_cmd(device_id, cmd)


def connect_wifi(device_id):
    cmd = f'am broadcast -a com.trs.trde.CONNECT_WIFI ' \
          f'-n com.trs.trde/.MainReceiver'
    _exe_adb_cmd(device_id, cmd)


def disconnect_wifi(device_id):
    cmd = f'am broadcast -a com.trs.trde.DISCONNECT_WIFI ' \
          f'-n com.trs.trde/.MainReceiver'
    _exe_adb_cmd(device_id, cmd)


def is_network_valid(device_id):
    cmd = f'"timeout 3s ping www.baidu.com 2>&1"'
    lines = _exe_adb_cmd(device_id, cmd)
    print(lines)
    line = ''.join(lines)
    if 'unknown host' in line:
        return False
    else:
        return True


def push_file(device_id, file_from, file_to):
    cmd = f'{ADB_EXE} -s {device_id} push "{file_from}" "{file_to}"'
    _exe_pc_cmd(device_id, cmd)


def pull_file(device_id, file_from, file_to):
    cmd = f'{ADB_EXE} -s {device_id} pull "{file_from}" "{file_to}"'
    _exe_pc_cmd(device_id, cmd)


def check_files_exist(device_id, file_list, output_dir):
    if not file_list:
        return []

    chk_sh_n = f'_check_files_exist_{device_id}.sh'
    chk_sh = os.path.join(OUTPUT_DIR, chk_sh_n)
    device_sh = f'{output_dir}/{chk_sh_n}'
    with open(chk_sh, 'w+') as f:
        f.write('\n'.join([f'[ -f {n} ] && echo "exist {n}"' for n in file_list]))
    push_file(device_id, chk_sh, device_sh)

    cmd = f'sh {device_sh}'
    lines = _exe_adb_cmd(device_id, cmd)

    exist_file_list = [l.split()[1].strip() for l in lines if l.strip() and l.startswith('exist ')]
    return exist_file_list


def exec_cmd(device_id, shell_cmd):
    cmd = f'"{shell_cmd}"'
    lines = _exe_adb_cmd(device_id, cmd)
    return lines


def exec_cmd_raise(device_id, shell_cmd):
    cmd = f'"{shell_cmd}"'
    lines = _exe_adb_cmd_raise(device_id, cmd)
    return lines


def exec_cmd_no_nohup(device_id, shell_cmd):
    # nohup sh /data/xxx.sh &
    cmd = f'nohup {shell_cmd} &'
    _exe_adb_cmd_no_wait(device_id, cmd)


def execute_adb_command_and_save(device_id, shell_cmd, result_path, filename):
    """执行 adb 命令并将输出保存到指定的文件"""

    # 生成动态文件名
    log_file_path = f"{result_path}/{filename}"
    if not os.path.exists(os.path.dirname(log_file_path)):
        os.makedirs(os.path.dirname(log_file_path))

    # 执行命令
    output = exec_cmd(device_id, shell_cmd)

    # 将输出保存到文件
    with open(log_file_path, 'w') as f:
        f.write(str(output))


def ensure_folder(device_id: str, remote_dir_path: str):
    make_dirs(device_id, remote_dir_path)


def ensure_file(device_id: str, remote_path: str):
    """
    在 Android 设备上确保存在一个空文件：
      - 若文件已存在，什么也不做。
      - 若不存在，则：
          1. 若父目录不存在，递归创建目录；
          2. 然后创建空文件。

    :param device_id: 要操作的设备 ID（adb -s ...）
    :param remote_path: 设备上的目标文件全路径，比如 /sdcard/auto/testlog.txt
    """
    # 需要在一条 shell 里做所有判断，以减少 adb 调用次数
    # quote() 用于对路径中的空格等字符做安全转义
    safe_path = quote(remote_path)
    shell_cmd = (
        f'if [ ! -e {safe_path} ]; then '
        f'dirname="$(dirname {safe_path})"; '
        f'if [ ! -d "$dirname" ]; then mkdir -p "$dirname"; fi; '
        f'touch {safe_path}; '
        f'fi'
    )

    full_cmd = [ADB_EXE, "-s", device_id, "shell", shell_cmd]
    try:
        subprocess.run(full_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"adb shell 命令执行失败: {err}") from e


def get_file_size(device_id: str, remote_path: str) -> int:
    """
    返回 Android 设备上指定文件的字节大小；如果文件不存在或发生错误，返回 -1。

    :param device_id: 设备序列号，用于 adb -s <device_id>
    :param remote_path: 设备上的目标文件路径（绝对路径）
    """
    # 对路径作安全转义
    safe_path = quote(remote_path)
    # Shell 脚本：若文件存在则用 stat 输出大小，否则输出 -1
    shell_cmd = (
        f'if [ -e {safe_path} ]; then '
        f'stat -c %s {safe_path} 2>/dev/null || echo -1; '
        f'else echo -1; fi'
    )

    # 调用 adb shell
    cmd = [ADB_EXE, "-s", device_id, "shell", shell_cmd]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=False
        )
    except FileNotFoundError as e:
        # adb 未找到
        raise RuntimeError(f"ADB not found: {e}") from e

    # 解析输出
    out = proc.stdout.strip()
    if proc.returncode != 0 or not out:
        return -1

    try:
        size = int(out)
    except ValueError:
        # 如果 stat 不可用，尝试用 ls -l 解析
        try:
            ls_cmd = [ADB_EXE, "-s", device_id,
                      "shell", f'ls -l {safe_path} 2>/dev/null || echo -1']
            ls_proc = subprocess.run(
                ls_cmd, capture_output=True, text=True, check=False, encoding='utf-8'
            )
            parts = ls_proc.stdout.strip().split()
            size = int(parts[4]) if len(parts) >= 5 else -1
        except Exception:
            return -1

    return size if size >= 0 else -1


def _read_info_file(device_id, sub_dir, name_key):
    local_dir = os.path.join(sub_dir, 'trde')
    mkdirs(local_dir)

    cmd = f'{ADB_EXE} -s {device_id} pull {TRDE_DEVICE_DIR} {sub_dir}'
    _exe_pc_cmd(device_id, cmd)

    info_files = []
    for root, dirs, files in os.walk(local_dir, topdown=False):
        for n in files:
            if n.startswith(TRDE_DEVICE_INFO_FILE_KEY) and n.endswith('csv'):
                info_files.append(os.path.join(root, n))

    fn = os.path.join(sub_dir, f'{TRDE_DEVICE_INFO_FILE_KEY}_{name_key}.csv')
    cur_fn = os.path.join(local_dir, f'{TRDE_DEVICE_INFO_FILE_KEY}.csv')
    with open(fn, 'w+') as wf:
        files = sorted(list(set(info_files) - {cur_fn}))
        files.append(cur_fn)
        if os.path.exists(cur_fn):
            with open(cur_fn, 'r+') as rf:
                line = rf.readline()
                wf.write(line)
        for n in files:
            if os.path.exists(n):
                with open(n, 'r+') as rf:
                    rf.readline()
                    wf.writelines(rf.readlines())

    return fn, files


def reset_battery_info_file(device_id):
    kill_app_by_key(device_id, TRDE_APK_PACKAGE)
    time.sleep(0.5)
    _exe_adb_cmd(device_id,
                 f'am broadcast -a com.trs.trde.start_service_only -n com.trs.trde/.MainReceiver')
    time.sleep(10)

    csv_files = f'{TRDE_DEVICE_DIR}/{TRDE_DEVICE_INFO_FILE_KEY}_*.csv'
    cmd = f'rm {csv_files} -rf'
    _exe_adb_cmd(device_id, cmd)


def read_and_reset_info_file(device_id, sub_dir, name_key):
    info_file, org_info_files = _read_info_file(device_id, sub_dir, name_key)
    reset_battery_info_file(device_id)
    return info_file, org_info_files


def is_spreadtrum(device_id):
    cmd = f'getprop ro.soc.manufacturer'
    lines = _exe_adb_cmd(device_id, cmd)
    val = ''.join(lines).strip()
    ret = True if val == 'Spreadtrum' else False
    return ret


def get_soc_manufacturer(device_id):
    cmd = f'getprop ro.soc.manufacturer'
    lines = _exe_adb_cmd(device_id, cmd)
    return lines[0].strip()


def set_wifi_adb_enabled(device_id, enabled):
    set_settings_value(device_id, 'global', 'adb_wifi_enabled', f'{(1 if enabled else 0)}')


def set_wifi_auto_wake_enable(device_id, enabled):
    set_settings_value(device_id, 'global', 'wifi_wakeup_enabled', f'{(1 if enabled else 0)}')


def is_wifi_adb_enabled(device_id):
    try:
        v = get_settings_value(device_id, 'global', 'adb_wifi_enabled')
        return v == '1'
    except:
        return False


def getprop(device_id, prop_name):
    cmd = f'getprop {prop_name}'
    lines = _exe_adb_cmd(device_id, cmd)
    return lines[0].strip()


def setprop(device_id, prop_name, val):
    cmd = f'setprop {prop_name} {val}'
    _exe_adb_cmd(device_id, cmd)


def setenforce(device_id, val):
    cmd = f'setenforce {val}'
    _exe_adb_cmd(device_id, cmd)


def oobe_exit(device_id):
    cmd = f'pm disable com.google.android.setupwizard'
    _exe_adb_cmd(device_id, cmd)

    cmd = f'settings put secure user_setup_complete 1'
    _exe_adb_cmd(device_id, cmd)

    cmd = f'settings put global device_provisioned 1'
    _exe_adb_cmd(device_id, cmd)

    cmd = f'settings put system show_inadvertent 0'
    _exe_adb_cmd(device_id, cmd)


def screen_size(device_id):
    cmd = f'wm size'
    lines = _exe_adb_cmd(device_id, cmd)
    s = ''.join(lines).strip().split(':')[1]
    w, h = s.split('x')
    return int(w.strip()), int(h.strip())


def clear_camera_photos_videos(device_id):
    cmd = f'"rm /sdcard/DCIM/Camera -rf"'
    _exe_adb_cmd(device_id, cmd)


def device_network_valid(device_id):
    cmd = f'"ping -c 3 www.baidu.com 2>&1"'
    lines = _exe_adb_cmd(device_id, cmd)
    if not lines or 'unknown host www.baidu.com' in ''.join(lines):
        return False
    else:
        return True


# 需要root权限
def entry_airplane_mode(device_id):
    cmd = f'settings put global airplane_mode_on 1'
    _exe_adb_cmd(device_id, cmd)
    time.sleep(1)
    cmd = f'am broadcast -a android.intent.action.AIRPLANE_MODE --ez state true'
    _exe_adb_cmd(device_id, cmd)


def exit_airplane_mode(device_id, broadcast_for_system_app=False):
    cmd = f'settings put global airplane_mode_on 0'
    _exe_adb_cmd(device_id, cmd)
    time.sleep(1)
    if broadcast_for_system_app:
        cmd = f'am broadcast -a android.intent.action.AIRPLANE_MODE --ez state false'
        _exe_adb_cmd(device_id, cmd)


def is_airplane_mode_on(device_id):
    cmd = f'settings get global airplane_mode_on'
    lines = _exe_adb_cmd(device_id, cmd)
    return lines and lines[0].strip() == '1'


# closeAnrDialog
def close_anr_dialog(device_id):
    try:
        cmdline = [ADB_EXE, "-s", device_id, "shell", "input keyevent 187"]
        exec_cmd(device_id, cmdline)
        time.sleep(3)
    except:
        pass


"""以下为zk新增方法"""


def exec_cmd_timeout(cmdline, timeout=60, run_in_shell=None):
    """
    在超时时间内，执行指定命令
    :param cmdline: 执行命令
    :param timeout: 超时时间
    :param run_in_shell: 是否通过shell执行，如果置为None则自动判断
    :return:
    """
    from powertrde.utils import misc_utils
    out_texts, out_error_texts, exit_code = misc_utils.run_command_get_text_output_exit_code(cmdline,
                                                                                             shell=env.suggest_shell_run(
                                                                                                 cmdline) if run_in_shell is None else run_in_shell,
                                                                                             timeout=timeout)
    if out_error_texts:
        logs_p().log_warning(
            f"ADB CMD ERROR with code {exit_code}: (cmd line)-> '{cmdline}'\n(adb error message)-> {out_error_texts}")

    exec_successfully = (exit_code == 0)
    exec_out = out_texts.splitlines()
    return exec_successfully, exec_out


def exec_cmd_not_wait(cmdline):
    """
    执行不等待
    """
    process = subprocess.Popen(cmdline, shell=env.suggest_shell_run(cmdline), stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    return process


def is_adb_connected(sn):
    """
    判断手机是否连接adb
    :param sn:
    :return:
    """
    cmdline = [ADB_EXE, "devices"]
    _, exec_out = exec_cmd_timeout(cmdline, timeout=15)
    for line in exec_out:
        line = line.strip()
        if sn in line and "device" in line:
            return True
    return False


def check_bootanim_done(sn):
    """
    检查手机开机动画是否完成
    :param sn:
    :return:
    """
    cmdline = [ADB_EXE, "-s", sn, "shell", "getprop init.svc.bootanim"]
    _, exec_out = exec_cmd_timeout(cmdline, timeout=15)
    for line in exec_out:
        line = line.strip()
        if "running" in line:
            return False
    return True


def get_android_device_time(sn):
    # 使用adb命令获取设备的当前时间
    result = subprocess.run([ADB_EXE, '-s', sn, 'shell', 'date', "+%Y-%m-%d' '%H:%M:%S.%N |cut -b 1-23"],
                            capture_output=True, text=True)
    # 原始时间字符串
    time_str = result.stdout.strip()
    log_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
    # 将时间转换为UNIX时间戳（毫秒）
    timestamp = int(log_time.timestamp() * 1000)
    return timestamp


def get_battery_percent(device_id):
    cmd = f'"dumpsys battery | grep level"'
    return int(_exe_adb_cmd(device_id, cmd)[0].split(': ')[1])


def get_battery_voltage(device_id):
    cmd = f'"dumpsys battery | grep voltage| grep -v charging"'
    return int(_exe_adb_cmd(device_id, cmd)[0].split(': ')[1])


def get_battery_design_capacity(device_id):
    cmd = f'"cat /sys/class/power_supply/battery/charge_full_design"'
    c = int(_exe_adb_cmd(device_id, cmd)[0])
    if c > 2000000:
        c //= 1000
    else:
        c //= 100
    return c


def get_battery_coulomb(device_id):
    cmd = f'"cat /sys/devices/platform/odm/odm:tran_battery/fg_coulomb"'
    return float(_exe_adb_cmd(device_id, cmd)[0])


def kill_instrument_process(device_id):
    try:
        # 构建ADB命令来获取instrument进程的PID
        command_to_get_pids = f"{ADB_EXE} -s {device_id} shell \"ps -ef | grep instrument | grep -v grep\""

        # 执行命令并获取输出
        result = subprocess.run(command_to_get_pids, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print("获取进程列表失败：", result.stderr)
            return

        # 解析输出并提取进程ID
        for line in result.stdout.splitlines():
            parts = line.split()
            pid = parts[2]  # PID在第三列
            print(pid)

            # 杀死进程
            command_to_kill = f"{ADB_EXE} -s {device_id} shell kill -9 {pid}"
            kill_result = subprocess.run(command_to_kill, shell=True)
            if kill_result.returncode == 0:
                print("Success")
            else:
                print(f"无法杀死进程 {pid}")

    except Exception as e:
        print(f"发生错误: {e}")

    try:
        # 获取设备上的所有进程
        command_to_get_processes = f"{ADB_EXE} -s {device_id} shell ps -ef"
        result = subprocess.run(command_to_get_processes, shell=True, capture_output=True, text=True)

        # 检查命令是否执行成功
        if result.returncode != 0:
            print("获取进程列表失败：", result.stderr)
            return

        # 解析PID
        pid = None
        for line in result.stdout.splitlines():
            if "instrument" in line and "app_process" in line:
                parts = line.split()
                pid = parts[1]  # 获取进程ID
                break

        if pid:
            # 杀死进程
            command_to_kill = f"{ADB_EXE} -s {device_id} shell kill {pid}"
            kill_result = subprocess.run(command_to_kill, shell=True, capture_output=True, text=True)

            if kill_result.returncode == 0:
                print(f"已杀死进程 {pid}")
            else:
                print("无法杀死进程：", kill_result.stderr)
        else:
            print("未找到instrument进程")

    except Exception as e:
        print(f"发生错误: {e}")


def is_mtk(sn):
    """
    通过 getprop ro.hardware 获取芯片类型，判断是否为MTK芯片
    """
    cmdline = [ADB_EXE, "-s", sn, "shell", "getprop ro.hardware"]
    exec_cmd_timeout(cmdline)
    _, exec_out = exec_cmd_timeout(cmdline)
    for line in exec_out:
        line = line.strip()
        if line.startswith("mt"):
            return True
    return False


def is_qcom(sn):
    """
    通过 getprop ro.hardware 获取芯片类型，判断是否为qcom
    """
    cmdline = [ADB_EXE, "-s", sn, "shell", "getprop ro.hardware"]
    exec_cmd_timeout(cmdline)
    _, exec_out = exec_cmd_timeout(cmdline)
    for line in exec_out:
        line = line.strip()
        if line.startswith("qcom"):
            return True
    return False

def is_sprd(device_id):
    return package_is_installed(device_id, 'com.sprd.engineermode')


def adb_pull(sn, device_path, local_path):
    cmdline = [ADB_EXE, "-s", sn, "pull", device_path, local_path]
    exec_cmd_timeout(cmdline, timeout=60 * 30)


def dex2oat_transform_package_to_speed_profile(device_id: str, package_name: str):
    try:
        result = subprocess.check_output(
            [ADB_EXE, '-s', device_id, 'shell', 'cmd', 'package', 'compile', '-m', 'speed-profile', '-f', package_name],
            stderr=subprocess.STDOUT,
            encoding='utf-8',
            text=True
        )
    except subprocess.CalledProcessError as e:
        logs_p().log_error(f"Failed to get package info: {e.output}")
        return


def grant_all_runtime_permissions(device_id: str, package_name: str):
    # 读取 dumpsys package 输出
    try:
        result = subprocess.check_output(
            [ADB_EXE, '-s', device_id, 'shell', 'dumpsys', 'package', package_name],
            stderr=subprocess.STDOUT,
            encoding='utf-8',
            text=True
        )
    except subprocess.CalledProcessError as e:
        logs_p().log_error(f"Failed to get package info: {e.output}")
        return

    # 提取 runtime permissions 部分
    runtime_section = ''
    in_runtime = False
    for line in result.splitlines():
        if 'runtime permissions:' in line:
            in_runtime = True
            continue
        if in_runtime:
            if 'permission' not in line:
                break
            runtime_section += line + '\n'

    # 匹配未授予的权限
    pattern = re.compile(r'^\s+([a-zA-Z0-9_.]+): granted=false', re.MULTILINE)
    denied_permissions = set(pattern.findall(runtime_section))

    if not denied_permissions:
        #logs_p().log_debug(f"All permissions already granted for {package_name}")
        return

    #logs_p().log_debug(f"Granting {len(denied_permissions)} permissions...")
    for perm in denied_permissions:
        cmd = [ADB_EXE, '-s', device_id, 'shell', 'pm', 'grant', package_name, perm]
        try:
            subprocess.run(cmd, check=True)
            # logs_p().log_debug(f"Granted: {perm}")
        except subprocess.CalledProcessError:
            logs_p().log_error(f"Failed to grant: {perm}")


def open_playstore_page(device_id: str, package_name: str):
    _cmd = f'am start -n com.android.vending/.AssetBrowserActivity -a android.intent.action.VIEW -d market://details?id={package_name}'
    return _exe_adb_cmd(device_id, _cmd)


def get_launcher_activity(device_id: str, package_name: str):
    """
    返回指定包的首个 Launcher Activity 的 ComponentName（如 "com.example/.MainActivity"）。
    如果未找到或出错，则返回 None。
    """
    cmd = [
        ADB_EXE, '-s', device_id, "shell", "cmd", "package", "resolve-activity",
        "--brief",
        "-a", "android.intent.action.MAIN",
        "-c", "android.intent.category.LAUNCHER",
        package_name
    ]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, encoding='utf-8', text=True)
    except subprocess.CalledProcessError as e:
        # adb 不支持 cmd package 或者包不存在
        logs_p().log_error(f"[Error] adb failed: {e.output.strip()}")
        return None

    # 通常输出两行：第一行为包名，第二行为 ComponentName
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return None
    if len(lines) >= 2:
        return lines[1].replace('$', '\\$')
    # 只有一行时，直接返回
    return lines[0].replace('$', '\\$')


def get_device_timezone_offset_ms(device_id: str) -> Optional[int]:
    """
    获取设备当前时区与 UTC 的偏移，单位毫秒。
    原理：adb shell date +%z，返回形如 +0800
    """
    try:
        proc = subprocess.run(
            [ADB_EXE, "-s", device_id, "shell", "date +%z"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=20
        )
        output = proc.stdout.strip()
        if len(output) != 5 or output[0] not in "+-":
            return None
        sign = 1 if output[0] == "+" else -1
        hours = int(output[1:3])
        minutes = int(output[3:5])
        total_minutes = sign * (hours * 60 + minutes)
        return total_minutes * 60_000  # 转换为毫秒
    except Exception:
        return None


def get_pc_timezone_offset_ms() -> int:
    """获取当前PC系统的本地时间与UTC的偏差（毫秒）"""
    now = datetime.now().astimezone()
    offset = now.utcoffset()
    return int(offset.total_seconds() * 1000)


def measure_device_time_offset_ms(
        device_id: str,
        samples: int = 5,
        calib_samples: int = 5,
        sleep_interval: float = 0.05
) -> Optional[float]:
    """
    高精度测量并返回指定 ADB 设备与主机时间的偏差（毫秒），

    :param device_id: 设备ID
    :param samples: 正式测量采样次数（>=3 推荐）
    :param calib_samples: 校准空跑采样次数
    :param sleep_interval: 采样间隔（秒）
    """

    def _calibrate_empty_run(n: int) -> float:
        """用相同命令空跑 n 次，测量平均往返延迟（毫秒）。"""
        costs = []
        for _ in range(n):
            t0 = time.time() * 1000
            # 空跑但执行同样的命令
            subprocess.run(
                [ADB_EXE, "-s", device_id, "shell", "date +%s%3N"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20
            )
            t1 = time.time() * 1000
            costs.append(t1 - t0)
            time.sleep(sleep_interval)
        return statistics.mean(costs) if costs else 0.0

    # 1) 空跑校准
    C = _calibrate_empty_run(calib_samples)

    # 2) 正式测量
    offsets = []
    for _ in range(samples):
        t1 = time.time() * 1000
        try:
            proc = subprocess.run(
                [ADB_EXE, "-s", device_id, "shell", "date +%s%3N"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=20
            )
            t_dev = int(proc.stdout.strip())
        except Exception:
            time.sleep(sleep_interval)
            continue
        t2 = time.time() * 1000

        t_mid = (t1 + t2) / 2
        offsets.append(t_mid - t_dev)
        time.sleep(sleep_interval)

    if not offsets:
        return None

    # 去掉最大/最小各一次，再平均
    if len(offsets) >= 3:
        offsets.sort()
        offsets = offsets[1:-1]
    raw_offset = statistics.mean(offsets)

    # 3) 校准：中点法已抵消约一半往返延迟，再减去剩余 C/2
    utc_offset_ms = (C / 2) - raw_offset

    # 3. 获取设备和PC的时区偏移
    dev_tz = get_device_timezone_offset_ms(device_id)
    pc_tz = get_pc_timezone_offset_ms()

    if dev_tz is None:
        raise Exception(f"Can not read timezone offset from device {device_id}")

    # 4. 计算本地时间差
    local_time_offset = utc_offset_ms + (dev_tz - pc_tz)

    return local_time_offset


def check_path_type(device_id: str, device_path):
    result = subprocess.run([ADB_EXE, '-s', device_id, 'shell', 'stat', device_path], capture_output=True,
                            text=True, encoding='utf-8')

    output = result.stdout.strip()

    if 'No such file or directory' in output:
        return None
    elif 'File: ' in output:
        if 'directory' in output:
            return 'dir'
        else:
            return 'file'
    return None


def push_file_ext(device_id: str, src_path: Union[str, os.PathLike], target_path: Union[str, os.PathLike],
                  overwrite=True):
    """
    将文件或文件夹推送到Android设备的指定路径（拓展版）。

    :param device_id: 设备ID
    :param src_path: 源文件或文件夹路径
    :param target_path: 目标路径
    :param overwrite: 如果为True，允许覆盖已存在的文件；否则跳过
    """
    if not os.path.exists(src_path):
        raise Exception(f'Not exists {src_path}')

    if target_path.endswith('/'):
        make_dirs(device_id, target_path)
    elif check_path_type(device_id, target_path) == 'dir':
        target_path += '/'

    if overwrite:
        cmd_push = [ADB_EXE, '-s', device_id, 'push', str(src_path), str(target_path)]
        subprocess.check_call(cmd_push)
        return

    # 获取目标路径的文件列表
    target_files = set()
    if not overwrite:
        # 使用 adb shell ls 递归列出所有文件
        cmd_list = [ADB_EXE, '-s', device_id, 'shell', f'find "{target_path}" -type f']
        result = subprocess.run(cmd_list, capture_output=True, text=True, encoding='utf-8')

        if result.returncode == 0:
            target_files = set(result.stdout.splitlines())

    # 检查src_path是文件还是文件夹
    if os.path.isdir(src_path):
        # 获取顶层目录名
        top_dir_name = os.path.basename(os.path.normpath(src_path))
        # 构建顶层目标路径
        top_level_target_path = os.path.join(target_path, top_dir_name).replace('\\', '/')

        # 遍历文件夹中的所有文件
        for root, dirs, files in os.walk(src_path):
            for file in files:
                # 构建源文件绝对路径
                file_path = os.path.join(root, file)
                # 计算文件相对于src_path的相对路径
                rel_path = os.path.relpath(file_path, src_path)
                # 构建目标文件路径
                remote_file_path = os.path.join(top_level_target_path, rel_path).replace('\\', '/')

                # 检查文件是否需要跳过（完整路径比较）
                if not overwrite and remote_file_path in target_files:
                    # print(f"File {remote_file_path} already exists. Skipping.")
                    continue

                # 推送文件
                cmd_push = [ADB_EXE, '-s', device_id, 'push', file_path, remote_file_path]
                result = subprocess.run(cmd_push, capture_output=True, text=True, encoding='utf-8')
                if result.returncode != 0:
                    raise Exception(f"Error pushing file {file_path}:", result.stderr)
                # else:
                #     print(f"Successfully pushed {file_path} to {remote_file_path}")

    else:
        # 单文件推送
        remote_file_path = target_path if not target_path.endswith('/') else os.path.join(target_path, os.path.basename(
            src_path)).replace('\\', '/')
        if not overwrite and remote_file_path in target_files:
            # print(f"File {remote_file_path} already exists. Skipping.")
            return

        cmd_push = [ADB_EXE, '-s', device_id, 'push', src_path, remote_file_path]
        result = subprocess.run(cmd_push, capture_output=True, text=True, encoding='utf-8')
        if result.returncode != 0:
            raise Exception("Error pushing file:", result.stderr)


if __name__ == '__main__':
    ...
    #_test()
    # set_screen_fps_mode(first_device(), 0)
    # restore_screen_fps_mode(first_device())
    # enter_hbm_brightness_mode(first_device())
    # quit_hbm_brightness_mode_and_set_brightness(first_device(), 255)
    # install_xapk(first_device(), r"D:\hehe\HonorOfKings_com.levelinfinite.sgameGlobal.xapk")
    # a = get_launcher_activity(first_device(), 'com.google.android.youtube')
    # print(a)
    # start_launcher_activity(first_device(), 'com.google.android.youtube')
    # start_apk_activity(first_device(), 'com.instagram.android', '.activity.MainTabActivity')
