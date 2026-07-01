import csv
import os
import pathlib
import platform
import shutil
import socket
import sys
import tarfile
import time

import yaml

from powertrde import env

PROJ_NAME = env.PROJ_NAME
# print("Current TRDE Project Name: " + PROJ_NAME)

MAC_LOG_DIR = f'/Users/zhouzhigang/Documents/{PROJ_NAME}_logs'
UBUNTU_LOG_DIR = f'/home/{PROJ_NAME}_logs'
WINDOW_LOG_DIR = f'D:\\{PROJ_NAME}_logs'

sys_str = platform.system().lower()
if sys_str == 'darwin':
    _LOG_DIR = MAC_LOG_DIR
elif sys_str == 'windows':
    _LOG_DIR = WINDOW_LOG_DIR
else:
    _LOG_DIR = UBUNTU_LOG_DIR

_PYTHON_LOG_DIR = os.path.join(_LOG_DIR, f'{PROJ_NAME}_python')
_DEVICE_LOG_DIR = os.path.join(_LOG_DIR, f'{PROJ_NAME}_python', 'device_log')
if getattr(sys, 'frozen', False):  # 生成exe执行
    _LOG_DIR = pathlib.Path().cwd()
    _PYTHON_LOG_DIR = os.path.join(_LOG_DIR, 'logs')
    _DEVICE_LOG_DIR = os.path.join(_LOG_DIR, 'dev_large_logs')

OUTPUT_DIR = os.path.join(_PYTHON_LOG_DIR,
                          time.strftime('%Y%m%d', time.localtime(time.time())),
                          time.strftime('logs_%H%M%S_', time.localtime(time.time())) + str(time.time())[-4:])

# BATTERY_INFO_GLOBAL_DIR = os.path.join(_LOG_DIR, 'battery_info_global')

# os.makedirs(_LOG_DIR, exist_ok=True)
# os.makedirs(OUTPUT_DIR, exist_ok=True)
# if not os.path.exists(_LOG_DIR):
#     os.mkdir(_LOG_DIR)
# if not os.path.exists(OUTPUT_DIR):
#     os.mkdir(OUTPUT_DIR)

# if not os.path.exists(BATTERY_INFO_GLOBAL_DIR):
#     os.mkdir(BATTERY_INFO_GLOBAL_DIR)

CONTROL_DATA_FILE = os.path.join(OUTPUT_DIR, 'control_data_all.txt')
DEVICES_YML_FILE = os.path.join(OUTPUT_DIR, 'devices')

LOG_FILE = os.path.join(OUTPUT_DIR, 'log.txt')

# LOG_BACKUP_DIR = os.path.join(PRJ_DIR, '..', 'trde_logs_backup')
PRJ_DIR = env.PROJ_DIR
ADB_EXE = env.ADB_EXE

TRDE_DAILY_APK_FILE = os.path.join(PRJ_DIR, 'resource', 'trde-daily.apk')
TRDE_BUILD_APK_FILE = os.path.join(PRJ_DIR, 'resource', 'trde-build.apk')
TRDE_X_DAILY_APK_FILE = os.path.join(PRJ_DIR, 'resource', 'trde-xdaily.apk')
TRDE_IDAILY_SPRD_APK_FILE = os.path.join(PRJ_DIR, 'resource', 'trde-idaily-sprd.apk')
TRDE_BUILD_SPRD_APK_FILE = os.path.join(PRJ_DIR, 'resource', 'trde-build-sprd.apk')
TRDE_APK_PACKAGE = 'com.trs.trde'
TRDE_APK_ACTIVITY = 'com.trs.trde.func_consume.ConsumeActivity'

# TRDE_AUTOMATOR_PACKAGE = 'com.transsion.emmctest'
# TRDE_AUTOMATOR_APK_FILE = os.path.join(PRJ_DIR, 'resource', 'trde_automator.apk')
# TRDE_AUTOMATOR_PACKAGE2 = 'com.transsion.emmctest.test'
# TRDE_AUTOMATOR_APK_FILE2 = os.path.join(PRJ_DIR, 'resource', 'trde_automator_androidTest.apk')

LEVEL_FLAG_BIT_FLASHLIGHT = 0x01
LEVEL_FLAG_BIT_FLAG_BIT_SCREEN_ON = 0x02
LEVEL_FLAG_BIT_FLAG_BIT_CPU = 0x04
LEVEL_FLAG_BIT_FLAG_BIT_BLUETOOTH = 0x08
LEVEL_FLAG_BIT_FLAG_BIT_VIB = 0x10
LEVEL_FLAG_BIT_FLAG_BIT_NETWORK = 0x20
LEVEL_FLAG_BIT_FLAG_BIT_GPS = 0x40
LEVEL_FLAG_BIT_FLAG_BIT_CAMERA = 0x80
LEVEL_FLAG_BIT_SCREEN_ON_FINISHED = 0x8000
LEVEL_BATT_CONSUME_FULL_UNSLEEP = 0xffff
LEVEL_BATT_CONSUME_FULL = LEVEL_BATT_CONSUME_FULL_UNSLEEP - LEVEL_FLAG_BIT_SCREEN_ON_FINISHED  # 全速急速放电

TA_POWER = {
    'RFC': 45,
    'PD_PPS': 45,  # PE5
    'PD': 18,
    'HVDCP': 18,
    # 'PE4': ,
    'PE2': 18,
    # 'PE': ,
    'TC30': 18,
    'CDP': 7.5,
    'DCP': 10,
    'SDP': 2.5,
    'NONSTAND': 7.5,
    'Unknown': 0,  # 未插充电器
}
ALL_TA_LIST = [_ta_key for _ta_key, _ in TA_POWER.items()]

DEVICE_AUTOMATOR_DIR = '/sdcard/automator'


def device_log_dir(current_dir):
    if _PYTHON_LOG_DIR in current_dir:
        d = current_dir.replace(_PYTHON_LOG_DIR, _DEVICE_LOG_DIR)
        mkdirs(d)
        return d
    return current_dir


def get_device_dir(device_id):
    return os.path.join(OUTPUT_DIR, device_id)


def get_output_sub_dir(device_id, key_words=''):
    key_words = str(key_words)
    d_dir = os.path.join(OUTPUT_DIR, device_id)
    d_dir = file_name_transform(d_dir)
    sub_dir = os.path.join(d_dir, key_words) if key_words else d_dir
    sub_dir = file_name_transform(sub_dir)
    if not os.path.exists(d_dir):
        os.mkdir(d_dir)
    if not os.path.exists(sub_dir):
        os.mkdir(sub_dir)
    return sub_dir


def mtk_log_dir(sub_dir):
    return os.path.join(sub_dir, 'mtk_log')


def sprd_log_dir(sub_dir):
    return os.path.join(sub_dir, 'sprd_log')


def trde_files_under_sub_dir(sub_dir):
    trde_dir = os.path.join(sub_dir, 'trda_test')
    batt_info_file = ''
    run_path_file = ''
    event_path_file = ''
    if os.path.exists(trde_dir):
        names = os.listdir(trde_dir)
        batt_info_l = [n for n in names if n.startswith('bat_info')]
        run_path_l = [n for n in names if n.startswith('run_path')]
        event_path_l = [n for n in names if n.startswith('event_')]
        batt_n = batt_info_l[0] if batt_info_l else ''
        run_path_n = run_path_l[0] if run_path_l else ''
        event_n = event_path_l[0] if event_path_l else ''
        batt_info_file = os.path.join(trde_dir, batt_n)
        run_path_file = os.path.join(trde_dir, run_path_n)
        event_path_file = os.path.join(trde_dir, event_n)

    return batt_info_file, run_path_file, event_path_file


def batt_info(info_file_name, pc_tick1, pc_tick2, tick_gap):
    keys = []
    values_list = []

    def parse_first_line(line):
        # 1660902899-17:54:59-877	charging_flag	battery_remain	battery_current	battery_voltage
        # charging_protocol	board_voltage	board_current	battery_temperature	board_temperature
        keys.extend(['time'] + line.split()[1:])

    def read_tick(time_str):
        return int(time_str.split('-')[0])

    first_line = True
    with open(info_file_name, 'r') as f:
        for line in f:
            if first_line:
                parse_first_line(line)
                first_line = False
            else:
                values = line.split()
                t = read_tick(values[0]) + tick_gap
                if t < pc_tick1 or t > pc_tick2:
                    continue
                dct = {k: v for k, v in zip(keys, values)}
                dct['pc_tick'] = t
                values_list.append(dct)

    return values_list


def is_rfc(values_list):
    for val in values_list:
        if 'charging_protocol' not in val.keys() or val['charging_protocol'] != 'RFC':
            return False
    return True


def run_path(path_file, pc_tick1, pc_tick2, tick_gap):
    ret_list = []
    start_tick = pc_tick1 - tick_gap
    stop_tick = pc_tick2 - tick_gap
    try:
        with open(path_file, 'r+') as f:
            for line in f:
                tick, func = line.split(',')
                tick = tick.strip()
                func = func.strip()
                if start_tick <= int(tick) <= stop_tick:
                    ret_list.append((tick, func))
    except BaseException as e:
        from powertrde.utils.trde.logs import log_exception, log_error
        log_error(f'file read error: {path_file}')
        log_exception(e)

    return ret_list


def last_event(event_file, event_name='trde_irq_set'):
    if not os.path.exists(event_file):
        return ()
    last_line = ''
    with open(event_file) as f:
        # 1663179624-19:20:24-775 trde_irq_set    irq_test        2
        for line in f:
            if event_name == line.split()[1].strip():
                last_line = line
    if last_line:
        time_tick = int(last_line.split()[0].split('-')[0])
        v = last_line.strip().split()[1:4]
        # time_tick, event_name, node_name, irq_value
        return tuple([time_tick] + v)
    return ()


def save_result_yml(device_id, result: dict, sub_dir=''):
    #   {
    #       'pass_flag': True,
    #       'pass_count': xx,
    #       'fail_count': xx,
    #       'fail_index': [xx, xx, xx ...]
    #       'result': [{
    #                       'pass_flag': True,
    #                       'index': xx,
    #                       'start_tick': xx, 'start_tick_pc': xx, 'stop_tick': xx, 'stop_tick_pc': xx, 'tick_gap: xx,
    #                  }]
    #   }
    file_name = os.path.join(OUTPUT_DIR, f'result_{device_id}.yml')
    saved = read_yml(file_name) if os.path.exists(file_name) else {}
    saved.update(result)
    with open(file_name, 'w') as f:
        yaml.dump(saved, f, allow_unicode=True, Dumper=yaml.Dumper)

    if sub_dir:
        sub_fn = os.path.join(sub_dir, f'result_{device_id}.yml')
        with open(sub_fn, 'w') as f:
            yaml.dump(saved, f, allow_unicode=True, Dumper=yaml.Dumper)


def save_result_summary_yml(value: dict):
    # { 'pass_flag': True
    #   'results': {device_id:
    #       {case_name:
    #           {   'pass_flag': True,
    #               'pass_count': 10,
    #               'fail_count': 3,
    #               'fail_index': [0, 3, 7],
    #               'loops': [...]
    # } } }}
    file_name = os.path.join(OUTPUT_DIR, f'result_summary.yml')
    saved = read_yml(file_name) if os.path.exists(file_name) else {}
    saved.update(value)
    with open(file_name, 'w') as f:
        yaml.dump(saved, f, allow_unicode=True, Dumper=yaml.Dumper)


def read_yml(file_name, encoding="utf-8"):
    if os.path.exists(file_name):
        with open(file_name, 'r', encoding=encoding) as file:
            dic = yaml.load(file, Loader=yaml.Loader)
    else:
        dic = None
    return dic


def save_yml(info, file_name, encoding="utf-8", add_yml_ext=True):
    if add_yml_ext:
        file_name = f'{file_name}' if file_name.endswith('.yml') else f'{file_name}.yml'
    else:
        file_name = str(file_name)
    with open(file_name, 'w', encoding=encoding) as f:
        yaml.dump(info, f, allow_unicode=True, Dumper=yaml.Dumper)
    return file_name


def save_csv(info_list, csv_file_name):
    csv_file = csv_file_name if csv_file_name.endswith('.csv') else csv_file_name + '.csv'

    with open(csv_file, 'w', newline='') as f:
        w = csv.writer(f, delimiter=',',
                       quotechar='|', quoting=csv.QUOTE_MINIMAL)
        for v in info_list:
            w.writerow(v)
    return csv_file


def append_csv(info_list, csv_file_name):
    csv_file = csv_file_name if csv_file_name.endswith('.csv') else csv_file_name + '.csv'

    with open(csv_file, 'a', newline='') as f:
        w = csv.writer(f, delimiter=',',
                       quotechar='|', quoting=csv.QUOTE_MINIMAL)
        for v in info_list:
            w.writerow(v)
    return csv_file


# def save_html_file(device_id, content, sub_dir=''):
#     fn = os.path.join(OUTPUT_DIR, f'html_{device_id}.html')
#     with open(fn, 'w+') as f:
#         f.write(str(content))
#
#     if sub_dir:
#         sub_name = os.path.join(sub_dir, f'html_{device_id}.html')
#         with open(sub_name, 'w+') as f:
#             f.write(str(content))

# return seconds


def cur_date_time_string():
    return time.strftime('%Y%m%d_%H:%M:%S', time.localtime(time.time()))


def cur_date_time_string_key():
    return time.strftime('%m%d_%H%M%S', time.localtime(time.time())) + str(time.time())[-4:]


def save_lines(lines, file_name):
    with open(file_name, 'w+') as f:
        f.writelines(lines)


def append_line(line, file_name):
    with open(file_name, 'a+') as f:
        if not line.endswith('\n'):
            line = line + '\n'
        f.write(line)


def file_save_line(sub_dir, line, key_wd=''):
    if not line:
        return
    file_name = os.path.join(sub_dir, f'data_{key_wd}.txt')
    with open(file_name, 'a+') as f:
        if not line.endswith('\n'):
            line = line + '\n'
        f.write(line)


def compress_and_del_dir(dir_path, label_error=False, to_log_dir=True):
    n = os.path.basename(dir_path)
    d = os.path.dirname(dir_path)
    if label_error:
        n += '_error'
    if to_log_dir:
        zip_d = device_log_dir(d)
    else:
        zip_d = d
    zip_file = os.path.join(zip_d, n + '.tar.gz')

    with tarfile.open(zip_file, 'w:gz') as f:
        f.add(dir_path, arcname=os.path.basename(dir_path))
    time.sleep(0.1)

    shutil.rmtree(dir_path)


def divide_kernel_logs(mtk_log_dir, output_dir, zip_name_key='', compress_kernel_log=True):
    try:
        k_files = []
        for root, dirs, files in os.walk(mtk_log_dir, topdown=False):
            for n in files:
                if 'kernel' in n or 'crash' in n or 'kmsg' in n:
                    k_files.append(os.path.join(root, n))
        for k in k_files:
            to_file = k.replace(mtk_log_dir, output_dir)
            mkdirs(os.path.dirname(to_file))
            shutil.copy(k, to_file)

        if compress_kernel_log:
            n = os.path.basename(output_dir)
            d = os.path.dirname(output_dir)
            zip_file = os.path.join(d, n + f'_{zip_name_key}.tar.gz')
            with tarfile.open(zip_file, 'w:gz') as f:
                f.add(output_dir, arcname=os.path.basename(output_dir))
            time.sleep(0.1)

            shutil.rmtree(output_dir)
    except BaseException as e:
        from powertrde.utils.trde import logs
        logs.log_exception(e)


def divide_sprd_ap_logs(sprd_log_dir, output_dir, zip_name_key=''):
    try:
        log_d = pathlib.Path(sprd_log_dir)
        ap_dir = pathlib.Path(output_dir)
        ap_dir.mkdir(exist_ok=True)

        index = 0
        for ylog_d in log_d.rglob('ylog'):
            for d in ylog_d.rglob('ap'):
                d1 = ap_dir.joinpath(f'ap{index}') if index else ap_dir
                d1.mkdir(exist_ok=True)
                shutil.copytree(d, d1.joinpath('ap'))
                index += 1

        zip_file = ap_dir.parent.joinpath(ap_dir.name + f'_{zip_name_key}.tar.gz')
        with tarfile.open(zip_file, 'w:gz') as f:
            f.add(ap_dir, arcname=ap_dir.name)
        time.sleep(0.1)
        shutil.rmtree(output_dir)
    except BaseException as e:
        from powertrde.utils.trde import logs
        logs.log_exception(e)


def file_name_transform(s):
    s = s[:4] + s[4:].replace(':', '-')
    return s


def is_windows():
    s = platform.system().lower()
    return s == 'windows'


def is_linux():
    s = platform.system().lower()
    return s == 'linux'


def is_mac():
    s = platform.system().lower()
    return s == 'darwin'


def find_files_startswith(dir_name, file_name):
    ret = []
    for root, dirs, files in os.walk(dir_name, topdown=False):
        for name in files:
            if name.startswith(file_name):
                ret.append(os.path.join(root, name))
            # print(os.path.join(root, name))
        # for name in dirs:
        #     print(os.path.join(root, name))
    return ret


def pc_name():
    switch_names = {
        "SHCYSHC-S3II521": "上海-lab-01",
        'SHCYqijiang222-pc': '上海-lab-02',
        'zzgmac.local': 'mac.zhigang.zhou',
        'SHCYhdtest11-pc': '上海-lab-03',
        'SHCYhdtest10-pc': '上海-lab-04',
        'DESKTOP-IDD61CC': '上海-lab-05',
        'SHCYzhouzg': '上海-lab-06',
        'cqrt1zhichen03-pc': '重庆-03',
        'cqrt1zhichen04-pc': '重庆-04',
    }
    n = socket.gethostname()
    n2 = os.getlogin().strip()
    r = switch_names.get(n, f'{n}__{n2}')
    return r


def pc_ip():
    ip = 'error ip'
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
        return ip


def rename_dir(old_path_name, new_path_name):
    os.rename(old_path_name, new_path_name)


def dir_name_add_error_label(dir_path):
    n = os.path.basename(dir_path)
    d = os.path.dirname(dir_path)
    e = n + '_error'
    err_path = os.path.join(d, e)
    rename_dir(dir_path, err_path)


def new_file_not_exist(file_name):
    mkdirs(os.path.dirname(file_name))
    if not os.path.exists(file_name):
        with open(file_name, 'w+'):
            pass


def new_file(file_name):
    mkdirs(os.path.dirname(file_name))
    with open(file_name, 'w+'):
        pass


def mkdirs(dir_name):
    os.makedirs(dir_name, exist_ok=True)
    if not os.path.exists(dir_name):
        os.mkdir(dir_name)


def duration_time_str(sec):
    if sec < 120:
        return f'{sec} 秒'
    elif sec < 10 * 60:
        return f'{round(sec / 60, 1)} 分钟'
    elif sec < 120 * 60:
        return f'{int(sec / 60)} 分钟'
    elif sec < 10 * 60 * 60:
        return f'{round(sec / 60 / 60, 1)} 小时'
    elif sec < 2 * 24 * 60 * 60:
        return f'{int(sec / 60 / 60)} 小时'
    elif sec < 10 * 24 * 60 * 60:
        return f'{round(sec / 24 / 60 / 60, 1)} 天'
    else:
        return f'{int(sec / 24 / 60 / 60)} 天'


###################################################

def _test():
    # divide_kernel_logs('D:\\temp\\sub_dir\\mtklog2', 'D:\\temp\\sub_dir\\kernel_log', 'abc_001')
    # divide_sprd_ap_logs(r'D:\temp\sub_dir\0cycle\sprd_log', r'D:\temp\sub_dir\0cycle\ap_logs')
    for i in [1, 5, 10, 60, 90, 60 * 3, 190, 60 * 8, 60 * 15, 60 * 20, 60 * 90, 60 * 60 * 5, 18200, 60 * 60 * 10,
              60 * 60 * 20, 60 * 60 * 24, 60 * 60 * 30, 60 * 60 * 50, 60 * 60 * 90, 60 * 60 * 24 * 5, 60 * 60 * 24 * 10,
              60 * 60 * 24 * 30]:
        s = duration_time_str(i)
        print(i, s)


if __name__ == '__main__':
    _test()
    # print(time.strftime('%Y%m%d_%H:%M:%S', time.localtime(1680024929)))
