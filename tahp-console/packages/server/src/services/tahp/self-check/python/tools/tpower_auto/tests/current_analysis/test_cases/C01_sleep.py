import os
import datetime
import re
from time import sleep
from collections import deque
from powertrde.utils.trde import adb
from tests.current_analysis.phoneconfig import PhoneConfig

def C01_Sleep(phone : PhoneConfig, sleep_time=120, filter_period=30):
    pmsn = phone.pmsn
    device = phone.device
    serial = phone.serial
    # 添加功耗测试前截图
    current_time = datetime.datetime.now()
    phone.screenshot(f"{current_time.strftime('%Y-%m-%d_%H-%M-%S')}.png")
    # 计算从当天0点开始的秒数
    seconds_since_midnight = current_time.hour * 3600 + current_time.minute * 60 + current_time.second
    phone.loginfo(f"---灭屏")
    adb.poweroff_phone_screen(serial)
    device.usb_disconnect(pmsn)
    sleep(180)
    device.set_filterperiod(pmsn, filter_period)
    phone.loginfo(f"---开始测量")
    # 3. 功耗测试
    device.start_measure(pmsn)
    sleep(sleep_time)
    result = device.stop_measure(pmsn)
    if result is None:
        phone.logerror(f"---测量失败")
    else:
        phone.loginfo(f"---测量成功")
        device.set_keyvalue(pmsn, "current", result["avgcurrent_mA"])
    device.usb_connect(pmsn)
    # 获取测试后板温
    board_temp_after = phone.get_board_temperature()
    if board_temp_after is not None:
        device.set_keyvalue(pmsn, "ntc_end", board_temp_after)
    # 保存日志
    logdir = phone.phone_log_stop_save()
    if phone.taskid in phone.powerref:
        if ('current' in phone.powerref[phone.taskid] and float(phone.dict_excel['current']) > float(phone.powerref[phone.taskid]['current'])) or \
        ('filtermin' in phone.powerref[phone.taskid]) and float(phone.dict_excel['filtermin']) > float(phone.powerref[phone.taskid]['filtermin']):
            keylogs = C01_Sleep_KeyLogs(phone, f"{logdir}/", seconds_since_midnight)
            if keylogs:
                analysis = phone.tran_ai.analyze(phone.device.get_keyvalue(phone.pmsn, 'task'),phone.powerref[phone.taskid], phone.dict_excel, keylogs)
                phone.loginfo(f"AI分析结果:\n{analysis}")
                phone.dict_excel['analysis'] = analysis
            else:
                phone.loginfo(f"日志筛选失败，跳过AI分析")
    else:
        phone.logwarning(f"任务 {phone.taskid} 不在功耗参考表中，跳过AI分析")
    return result

def _MTK_Sleep_KeyLogs(phone:PhoneConfig, logdir:str) -> str | None:
    log_file = []
    for root, dirs, files in os.walk(logdir):
        for file in files:
            if "kernel_log" in file:
                log_file.append(os.path.join(root, file))
    if log_file:
        log_file = log_file[0]
    else:
        return None
    #print(f"解析日志文件: {log_file}")
    keywords = ("failed", "suspend", "wake up", "pending", "blocked", "healthd", "active", "error", "cpus usage")
    level_pattern = re.compile(r'^<(?:[0-5]|[8-9]|1[0-3])>')
    time_pattern = re.compile(r"\[\s*(\d+\.\d+)\]\[")
    time_suspend = re.compile(r"suspend wake up by.*?timer_out\s*=\s*(\d+)")
    sreen_off = False
    last_lines = deque(maxlen=10000)
    time_flag = 0.0
    with open(log_file, "r", encoding="utf-8", errors="ignore") as fin:
        for line in fin:
            line_lower = line.lower()
            # screen off 开始
            if "screen off" in line_lower:
                sreen_off = True
                #last_lines.clear()
                time_flag = 0.0
                time_delay = True
                continue
            # screen on 结束
            if "screen on" in line_lower:
                sreen_off = False
                continue
            if not sreen_off:
                continue
            if time_delay :
                timestamp_match = time_pattern.search(line)
                if not timestamp_match:
                    continue
                if time_flag == 0.0:
                    time_flag = float(timestamp_match.group(1)) + 120
                    continue
                suspendtime = time_suspend.search(line_lower)
                if suspendtime:
                    time_flag -= (float(suspendtime.group(1)) / 32768.0)
                if float(timestamp_match.group(1)) < time_flag:
                    continue
                time_delay = False
            if level_pattern.match(line) or any(k in line_lower for k in keywords):
                last_lines.append(line.rstrip("\n"))
    #提取last_lines最后一行的时间戳
    if not last_lines:
        return None
    max_time = 0.0
    #过滤掉最后1秒内的日志
    while last_lines:
        line = last_lines.pop()
        suspendtime = time_suspend.search(line_lower)
        if suspendtime:
            last_lines.append(line)
            break
        timestamp_match = time_pattern.search(line)
        if not timestamp_match:
            continue
        timestamp = float(timestamp_match.group(1))
        if max_time == 0.0:
            max_time = float(timestamp_match.group(1))
            continue
        if timestamp < max_time - 2:
            break
    if len(last_lines):
        last_lines.append(f"增加统计日志总时长，休眠时长，24M时钟关闭率")
    # 合并成一个字符串（用换行符连接）
    result_str = "\n".join(last_lines)
    phone.logdebug(f"筛选后剩余 {len(last_lines)} 行有效日志,总字符数 {len(result_str)}")
    return result_str

def _QCOM_Sleep_KeyLogs(phone:PhoneConfig, logdir:str, start_time:float) -> str | None:
    log_file = []
    for root, dirs, files in os.walk(logdir):
        for file in files:
            if "kernellog" in file:
                log_file.append(os.path.join(root, file))
    if log_file:
        log_file = log_file[0]
    else:
        return None
    #print(f"解析日志文件: {log_file}")
    keywords = ("failed", "suspend", "wake up", "pending", "blocked", "healthd", "active", "error", "cpus usage")
    level_pattern = re.compile(r'\s[WEF]\s')
    time_pattern = re.compile(r"^\s*\d{2}-\d{2}\s+(\d{2}):(\d{2}):(\d{2})")
    sreen_off = False
    last_lines = deque(maxlen=10000)
    time_flag = start_time + 120
    time_flag %= 86400
    with open(log_file, "r", encoding="utf-8", errors="ignore") as fin:
        for line in fin:
            line_lower = line.lower()
            # screen off 开始
            if "wired pulgout" in line_lower:
                sreen_off = True
                time_delay = True
                continue
            # screen on 结束
            if "wired plugin" in line_lower:
                sreen_off = False
                continue
            if not sreen_off:
                continue
            if time_delay :
                timestamp_match = time_pattern.search(line_lower)
                if not timestamp_match:
                    continue
                hours = int(timestamp_match.group(1))
                minutes = int(timestamp_match.group(2))
                seconds = int(timestamp_match.group(3))
                logtime = hours * 3600 + minutes * 60 + seconds
                if logtime < time_flag or logtime > (time_flag + 43200):
                    continue
                phone.logdebug(f"筛选日志时间:{hours}:{minutes}:{seconds}")
                time_delay = False
            if level_pattern.match(line) or any(k in line_lower for k in keywords):
                last_lines.append(line.rstrip("\n"))
    #提取last_lines最后一行的时间戳
    if not last_lines:
        return None
    max_time = 0.0
    #过滤掉最后1秒内的日志
    while last_lines:
        line = last_lines.pop()
        timestamp_match = time_pattern.search(line)
        if not timestamp_match:
            continue
        hours = int(timestamp_match.group(1))
        minutes = int(timestamp_match.group(2))
        seconds = int(timestamp_match.group(3))
        logtime = hours * 3600 + minutes * 60 + seconds
        if max_time == 0.0:
            max_time = (logtime + 86400 - 2) % 86400
            continue
        if logtime < max_time and (max_time - logtime) < 1000:
            break
    if len(last_lines):
        last_lines.append(f"增加统计日志总时长，休眠时长，24M时钟关闭率")
    # 合并成一个字符串（用换行符连接）
    result_str = "\n".join(last_lines)
    phone.logdebug(f"筛选后剩余 {len(last_lines)} 行有效日志,总字符数 {len(result_str)}")
    return result_str

def C01_Sleep_KeyLogs(phone:PhoneConfig, logdir:str, start_time:float) -> str | None:
    if phone.u2d_helper.is_mtk:
        return _MTK_Sleep_KeyLogs(phone, logdir)
    elif phone.u2d_helper.is_qcom:
        return _QCOM_Sleep_KeyLogs(phone, logdir, start_time)
    return None
