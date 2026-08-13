import os
import re
import sys
import json
import argparse
from datetime import datetime, timedelta

def _setup_utf8_stdio() -> None:
    """统一脚本标准输入输出编码为 UTF-8，减少 Windows 终端乱码。"""
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _safe_path(path):
    """Windows 下为超长路径添加 long-path 前缀，其它平台原样返回。"""
    if os.name != "nt":
        return path
    abs_path = os.path.abspath(path)
    if abs_path.startswith("\\\\?\\"):
        return abs_path
    if abs_path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + abs_path.lstrip("\\")
    return "\\\\?\\" + abs_path


def _open_text(path, mode, encoding="utf-8", errors="ignore"):
    return open(_safe_path(path), mode, encoding=encoding, errors=errors)


def _path_exists(path):
    return os.path.exists(_safe_path(path))

def get_event_log_files(folder_path, recursive=True):
    """获取以event_log开头的文件

    Args:
        folder_path: 文件夹路径
        recursive: 是否递归搜索子文件夹

    Returns:
        list: event_log文件路径列表
    """
    event_log_files = []

    search_root = _safe_path(folder_path)

    if recursive:
        for root, dirs, files in os.walk(search_root):
            for file in files:
                if file.startswith("events_log"):
                    event_log_files.append(os.path.join(root, file))
    else:
        for file in os.listdir(search_root):
            file_path = os.path.join(search_root, file)
            if os.path.isfile(_safe_path(file_path)) and file.startswith("events_log"):
                event_log_files.append(file_path)

    return event_log_files

def extract_year_from_filename(file_path):
    """从文件名中提取年份

    Args:
        file_path: 文件路径

    Returns:
        int: 年份，如果未找到则返回None
    """
    # 文件名格式示例：kernel_log_113__2026_0305_085522_linli_666.txt
    # 查找4位数字年份模式
    match = re.search(r'_(\d{4})_\d{4}_', os.path.basename(file_path))
    if match:
        year = int(match.group(1))
        if 2000 <= year <= 2100:
            return year
    return None


def extract_year_from_healthd_time(time_str):
    """从healthd记录的时间字符串中提取年份

    Args:
        time_str: 时间字符串，格式如 2026-05-04 23:40:01 或 05-04 23:40:01.123

    Returns:
        tuple: (年份, 是否从实际时间中提取到的年份)
    """
    # 尝试匹配 YYYY-MM-DD HH:MM:SS 格式
    match = re.match(r'^(\d{4})-\d{2}-\d{2}', time_str)
    if match:
        year = int(match.group(1))
        if 2000 <= year <= 2100:
            return year, True
    return None, False

def extract_battery_capacity(folder_path):
    """从日志中提取电池容量

    从第一条healthd: battery关键字所在行提取fc=后的前四位数值作为电池容量默认值

    Args:
        folder_path: 文件夹路径

    Returns:
        int: 电池容量(mAh)，如果未找到则返回5000作为默认值
    """
    # 获取以linli_666结尾的文件
    linli_files = get_linli_666_files(folder_path, recursive=True)

    if not linli_files:
        return 5000

    # 搜索关键字
    keyword = "healthd: battery"

    for file_path in linli_files:
        try:
            with _open_text(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                for line in file:
                    if keyword in line:
                        # 提取fc=后的前四位数值
                        fc_match = re.search(r'fc=(\d{4})', line)
                        if fc_match:
                            capacity = int(fc_match.group(1))
                            print(f"从日志中提取到电池容量: {capacity} mAh")
                            return capacity
                        break  # 只读取第一条healthd记录
        except Exception as e:
            continue

    print("未能在日志中找到电池容量，使用默认值: 5000 mAh")
    return 5000

def parse_log_time(time_str, base_year=None):
    """解析日志中的时间格式

    Args:
        time_str: 时间字符串
        base_year: 基准年份（当时间字符串不包含年份时使用，可选）

    Returns:
        datetime: 解析后的datetime对象，解析失败返回None
    """
    # 尝试多种时间格式解析，优先尝试包含年份的格式
    formats = [
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%m-%d %H:%M:%S.%f",
        "%m-%d %H:%M:%S"
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(time_str, fmt)
            # 如果格式包含年份（%Y），直接使用解析出的年份
            if '%Y' in fmt:
                return dt
            # 如果格式不包含年份，使用传入的base_year
            if base_year:
                return dt.replace(year=base_year)
            # 如果没有提供base_year，返回原始解析结果
            return dt
        except ValueError:
            continue

    # 无法解析的时间，返回None
    return None

def parse_user_time(time_str, base_year=None):
    """解析用户输入的时间字符串，支持多种格式

    Args:
        time_str: 用户输入的时间字符串
        base_year: 基准年份（当时间字符串不包含年份时使用，可选）

    Returns:
        datetime: 解析后的datetime对象，解析失败返回None
    """
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%H:%M:%S",
        "%H:%M"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(time_str, fmt)
            # 如果没有年份（默认1900），使用base_year
            if dt.year == 1900:
                if base_year:
                    dt = dt.replace(year=base_year, month=1, day=1)
                else:
                    dt = dt.replace(year=1, month=1, day=1)
            # 如果有年份且指定了base_year，转换为base_year
            elif base_year and dt.year != base_year:
                dt = dt.replace(year=base_year)
            return dt
        except ValueError:
            continue
    return None


def is_in_time_range(time_str, start_time, end_time, base_year=None):
    """检查时间是否在指定范围内

    Args:
        time_str: 日志中的时间字符串
        start_time: 开始时间字符串
        end_time: 结束时间字符串
        base_year: 基准年份（可选）

    Returns:
        bool: 是否在时间范围内
    """
    # 解析日志时间
    line_dt = parse_log_time(time_str, base_year)
    if line_dt is None:
        return True

    # 解析开始时间（支持时分格式和完整日期时间格式）
    if start_time:
        start_dt = parse_user_time(start_time, base_year)
        if start_dt:
            # 检查是否包含日期信息（只有当用户明确指定了非默认日期时才认为包含日期）
            # 默认值为1月1日，所以只有月不为1或日不为1时才认为包含日期
            has_date = start_dt.month != 1 or start_dt.day != 1
            if has_date:
                # 完整日期时间比较
                # 如果用户指定了年份，使用用户的年份进行比较
                compare_line_dt = line_dt
                if start_dt.year != 1900:
                    compare_line_dt = line_dt.replace(year=start_dt.year)
                if compare_line_dt < start_dt:
                    return False
            else:
                # 只比较时间部分
                if line_dt.time() < start_dt.time():
                    return False

    # 解析结束时间（支持时分格式和完整日期时间格式）
    if end_time:
        end_dt = parse_user_time(end_time, base_year)
        if end_dt:
            # 检查是否包含日期信息（只有当用户明确指定了非默认日期时才认为包含日期）
            has_date = end_dt.month != 1 or end_dt.day != 1
            if has_date:
                # 完整日期时间比较
                # 如果用户指定了年份，使用用户的年份进行比较
                compare_line_dt = line_dt
                if end_dt.year != 1900:
                    compare_line_dt = line_dt.replace(year=end_dt.year)
                if compare_line_dt > end_dt:
                    return False
            else:
                # 只比较时间部分
                if line_dt.time() > end_dt.time():
                    return False

    return True

def get_linli_666_files(folder_path, recursive=True):
    """获取以linli_666结尾的文件

    Args:
        folder_path: 文件夹路径
        recursive: 是否递归搜索子文件夹

    Returns:
        list: 符合条件的文件路径列表
    """
    linli_files = []

    search_root = _safe_path(folder_path)

    if recursive:
        for root, dirs, files in os.walk(search_root):
            for file in files:
                # 检查文件名是否包含"linli_666"，不管是否有扩展名
                if "linli_666" in file:
                    linli_files.append(os.path.join(root, file))
    else:
        for file in os.listdir(search_root):
            file_path = os.path.join(search_root, file)
            if os.path.isfile(_safe_path(file_path)) and "linli_666" in file:
                linli_files.append(file_path)

    return linli_files

def extract_timestamp_from_filename(file_path):
    """从文件名中提取时间戳
    
    文件名格式示例：kernel_log_113__2025_1203_074247_linli_666.txt
    提取格式：2025_1203_074247
    
    Args:
        file_path: 文件路径
        
    Returns:
        str: 时间戳字符串，如 "2025_1203_074247"，提取失败返回空字符串
    """
    filename = os.path.basename(file_path)
    # 匹配格式：数字_数字_数字_linli_666
    match = re.search(r'(\d{4}_\d{4}_\d{6})_linli_666', filename)
    if match:
        return match.group(1)
    # 尝试其他可能的格式
    match = re.search(r'_(\d{4})_(\d{4})_(\d{6})_', filename)
    if match:
        return f"{match.group(1)}_{match.group(2)}_{match.group(3)}"
    return ""

def merge_linli_files(input_path):
    """合并所有linli_666文件，按时间排序
    
    Args:
        input_path: 输入文件夹路径
        
    Returns:
        str: 合并后的文件路径，如果没有文件返回None
    """
    linli_files = get_linli_666_files(input_path, recursive=True)
    
    if not linli_files:
        print("未找到linli_666文件")
        return None
    
    # 为每个文件提取时间戳并排序
    files_with_timestamp = []
    for file_path in linli_files:
        timestamp = extract_timestamp_from_filename(file_path)
        files_with_timestamp.append((timestamp, file_path))
    
    # 按时间戳排序
    files_with_timestamp.sort(key=lambda x: x[0])
    
    merged_path = os.path.join(input_path, "merged_kernel_log")
    
    # 合并文件
    with _open_text(merged_path, 'w', encoding='utf-8', errors='ignore') as outfile:
        for timestamp, file_path in files_with_timestamp:
            try:
                with _open_text(file_path, 'r', encoding='utf-8', errors='ignore') as infile:
                    outfile.write(infile.read())
                    outfile.write("\n")  # 在文件之间添加分隔
                print(f"已合并: {os.path.basename(file_path)}")
            except Exception as e:
                print(f"合并文件 {file_path} 时出错: {e}")
    
    print(f"合并完成，输出文件: {merged_path}")
    
    # 搜索合并后的文件中的healthd: battery关键字并打印 - 已注释，不再打印原始数据
    # search_and_print_healthd(merged_path)
    
    return merged_path

def search_and_print_healthd(file_path):
    """搜索文件中的healthd: battery关键字并按指定格式打印
    
    Args:
        file_path: 文件路径
    """
    keyword = "healthd: battery"
    
    print(f"\n===== 从 {os.path.basename(file_path)} 搜索 healthd: battery =====")
    print(f"{'时间':<22} {'电量':<8} {'电压':<10} {'温度':<8} {'瞬时电流':<10}")
    print("-" * 60)
    
    try:
        with _open_text(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            for line in file:
                if keyword in line:
                    # 提取时间：第一组方括号之间的数值
                    time_match = re.search(r'\[([^\]]+)\]', line)
                    time_str = time_match.group(1) if time_match else ""
                    
                    # 提取电量 l=xxx
                    level_match = re.search(r'l=(\d+)', line)
                    level = level_match.group(1) if level_match else ""
                    
                    # 提取电压 v=xxx
                    voltage_match = re.search(r'v=(\d+)', line)
                    voltage = f"{int(voltage_match.group(1))/1000:.3f}" if voltage_match else ""
                    
                    # 提取温度 t=xxx
                    temp_match = re.search(r't=([\d.]+)', line)
                    temp = temp_match.group(1) if temp_match else ""
                    
                    # 提取瞬时电流 c=xxx
                    current_match = re.search(r'c=(-?\d+)', line)
                    current = str(int(int(current_match.group(1)) / 1000)) if current_match else ""
                    
                    # 格式化时间（只到秒）
                    formatted_time = ""
                    if time_str:
                        try:
                            if "." in time_str:
                                dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
                            else:
                                dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                            formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            formatted_time = time_str
                    
                    print(f"{formatted_time:<22} {level:<8} {voltage:<10} {temp:<8} {current:<10}")
    except Exception as e:
        print(f"搜索文件 {file_path} 时出错: {e}")

def search_healthd_battery(folder_path, start_time=None, end_time=None):
    """搜索以linli_666结尾的文件中的healthd: battery关键字

    Args:
        folder_path: 文件夹路径
        start_time: 开始时间
        end_time: 结束时间

    Returns:
        list: 所有电池数据
    """
    merged_path = os.path.join(folder_path, "merged_kernel_log")
    
    # 检查是否存在merged_kernel_log文件
    if _path_exists(merged_path):
        print(f"检测到已合并文件: {merged_path}")
        files_to_process = [merged_path]
    else:
        print("未检测到merged_kernel_log，进行文件合并...")
        merged_path = merge_linli_files(folder_path)
        if not merged_path:
            return [], None, None
        files_to_process = [merged_path]

    # 先从第一条healthd记录中提取年份
    base_year = None
    year_from_log = False
    for file_path in files_to_process:
        try:
            with _open_text(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                for line in file:
                    if "healthd: battery" in line:
                        time_match = re.search(r'\[([^\]]+)\]', line)
                        if time_match:
                            time_str = time_match.group(1)
                            base_year, year_from_log = extract_year_from_healthd_time(time_str)
                        break
        except Exception:
            continue
        if year_from_log:
            break

    # 如果没有从healthd记录中找到有效年份，则从文件名中提取
    if not year_from_log and files_to_process:
        base_year = extract_year_from_filename(files_to_process[0])

    # 搜索关键字
    keyword = "healthd: battery"

    total_matches = 0
    all_battery_data = []  # 存储所有文件的电池数据（未过滤时间范围）
    original_first_data = None  # 保存原始第一条记录
    original_last_data = None  # 保存原始最后一条记录

    for file_path in files_to_process:
        file_matches = 0

        try:
            with _open_text(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                for line in file:
                    if keyword in line:
                        # 提取时间：第一组方括号之间的数值
                        time_match = re.search(r'\[([^\]]+)\]', line)
                        time_str = time_match.group(1) if time_match else ""

                        # 解析电池信息
                        # 提取电量：battery l=和之后的第一个空格之间的数值
                        level_match = re.search(r'battery l=(\d+)', line)
                        level_str = level_match.group(1) if level_match else ""

                        # 提取电压：v=和之后的第一个空格之间的数值
                        voltage_match = re.search(r'v=(\d+)', line)
                        voltage_str = voltage_match.group(1) if voltage_match else ""

                        # 提取温度：t=和之后的第一个空格之间的数值
                        temp_match = re.search(r't=(\d+)', line)
                        temp_str = temp_match.group(1) if temp_match else ""

                        # 提取瞬时电流：c=和之后的第一个空格之间的数值
                        current_match = re.search(r'c=(-?\d+)', line)
                        current_str = current_match.group(1) if current_match else ""

                        # 提取充电状态：chg=之后的内容
                        chg_match = re.search(r'chg=(.*?)(?:\s|$)', line)
                        chg_str = chg_match.group(1) if chg_match else ""

                        # 存储数据到临时字典
                        battery_data = {
                            'time': time_str,
                            'level': level_str,
                            'voltage': voltage_str,
                            'temp': temp_str,
                            'current': current_str,
                            'chg': chg_str
                        }

                        # 保存原始第一条和最后一条记录
                        if original_first_data is None:
                            original_first_data = battery_data.copy()
                        original_last_data = battery_data.copy()

                        file_matches += 1
                        total_matches += 1

                        # 存储所有数据（不进行时间范围过滤）
                        all_battery_data.append(battery_data)
        except Exception as e:
            continue

    # 保持文件合并后的原始顺序，不进行时间排序
    return all_battery_data, original_first_data, original_last_data

def calculate_average_current(all_battery_data, battery_capacity, base_year=None, start_time=None):
    """计算每条记录的平均电流

    平均电流计算：电池容量 * (上一次电量 - 当前电量) / 上一次与本条记录的时间差(小时)
    
    当指定了start_time时，从第一条匹配记录的下一条开始计算。

    Args:
        all_battery_data: 电池数据列表
        battery_capacity: 电池容量(mAh)
        base_year: 基准年份
        start_time: 用户指定的开始时间（可选）

    Returns:
        list: 平均电流列表，与all_battery_data一一对应
    """
    average_currents = []

    # 按时间排序函数
    def parse_time(time_str):
        # 优先尝试包含年份的格式
        formats = [
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%m-%d %H:%M:%S.%f",
            "%m-%d %H:%M:%S"
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(time_str, fmt)
                # 如果格式包含年份，直接使用解析出的年份
                if '%Y' in fmt:
                    return dt
                # 如果格式不包含年份，使用从日志中提取的base_year
                return dt.replace(year=base_year)
            except ValueError:
                continue
        return datetime.min

    # 找到第一条匹配开始时间的记录索引
    start_index = 0
    if start_time:
        start_dt = parse_time(start_time)
        for i, data in enumerate(all_battery_data):
            data_dt = parse_time(data['time'])
            if data_dt >= start_dt:
                start_index = i
                break

    for i, data in enumerate(all_battery_data):
        # 第一条记录（索引0）的平均电流为0（没有上一条记录可以计算）
        # 如果指定了start_time，则从匹配到的记录开始计算（start_index之前的记录平均电流为0）
        if i == 0 or (start_time and i < start_index):
            average_currents.append(0.0)
        else:
            prev_data = all_battery_data[i - 1]
            curr_level = float(data['level'])
            prev_level = float(prev_data['level'])

            # 检查上一条记录是否有充电状态有值，如果有则当前记录平均电流记为0
            if prev_data['chg'] and prev_data['chg'] != '无' and prev_data['chg'] != '':
                average_currents.append(0.0)
                continue

            # 计算时间差
            curr_time = parse_time(data['time'])
            prev_time = parse_time(prev_data['time'])
            time_diff = (curr_time - prev_time).total_seconds() / 3600.0  # 转换为小时

            if time_diff > 0:
                # 计算平均电流
                # 电量是百分比值，需要除以100转换为实际电量比例
                level_diff = prev_level - curr_level  # 电量差（下降为正）
                avg_current = battery_capacity * level_diff / 100.0 / time_diff
                average_currents.append(avg_current)
            else:
                average_currents.append(0.0)

    return average_currents

def format_datetime(time_str, base_year=None):
    """格式化时间字符串为标准格式

    Args:
        time_str: 时间字符串
        base_year: 基准年份（当时间字符串不包含年份时使用，可选）

    Returns:
        str: 格式化后的时间字符串
    """
    # 优先尝试包含年份的格式
    formats_with_year = ["%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"]
    formats_without_year = ["%m-%d %H:%M:%S.%f", "%m-%d %H:%M:%S"]
    
    for fmt in formats_with_year:
        try:
            dt = datetime.strptime(time_str, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    
    for fmt in formats_without_year:
        try:
            dt = datetime.strptime(time_str, fmt)
            if base_year:
                dt = dt.replace(year=base_year)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    
    return time_str

def parse_datetime(time_str, base_year=None):
    """解析时间字符串为datetime对象，支持多种格式

    Args:
        time_str: 时间字符串
        base_year: 基准年份（当时间字符串不包含年份时使用，可选）

    Returns:
        datetime: 解析后的datetime对象，解析失败返回None
    """
    # 优先尝试包含年份的格式
    formats_with_year = [
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S"
    ]
    formats_without_year = [
        "%m-%d %H:%M:%S.%f",
        "%m-%d %H:%M:%S",
        "%H:%M:%S",
        "%H:%M"
    ]
    
    for fmt in formats_with_year:
        try:
            dt = datetime.strptime(time_str, fmt)
            # 如果格式包含年份，直接使用解析出的年份
            return dt
        except ValueError:
            continue
    
    for fmt in formats_without_year:
        try:
            dt = datetime.strptime(time_str, fmt)
            # 如果没有年份（默认1900），使用base_year
            if dt.year == 1900:
                if base_year:
                    dt = dt.replace(year=base_year, month=1, day=1)
                else:
                    dt = dt.replace(year=1, month=1, day=1)
            return dt
        except ValueError:
            continue
    return None

def analyze_battery_data(all_battery_data, average_currents, base_year=None,
                        standby_threshold=25, hardware_threshold=3000,
                        user_start_time=None, user_end_time=None,
                        original_first_data=None, original_last_data=None,
                        battery_capacity=5000):
    """分析电池数据，生成结构化摘要

    Args:
        all_battery_data: 电池数据列表
        average_currents: 平均电流列表
        base_year: 基准年份
        standby_threshold: 待机电流阈值(mA)，同时作为PASS/FAIL平均电流阈值
        hardware_threshold: 硬件放电异常阈值(mA)
        user_start_time: 用户手动指定的开始时间
        user_end_time: 用户手动指定的结束时间

    Returns:
        dict: 结构化分析摘要
    """
    summary = {
        'META': {},
        'THRESHOLD': {
            'standby_current_threshold_ma': standby_threshold,
            'hardware_discharge_abnormal_threshold_ma': hardware_threshold
        },
        'JUMP_CHECK': {
            'has_soc_or_voltage_jump': False,
            'jump_count': 0,
            'jumps': []
        },
        'HARDWARE_ABNORMAL': {
            'has_discharge_over_3a': False,
            'abnormal_count': 0,
            'abnormal_detail': 'none'
        },
        'POWER_SEGMENT': {
            'pass_duration_h': 0.0,
            'pass_avg_current_ma': 0.0,  # 按时间加权平均
            'fail_duration_h': 0.0,
            'fail_avg_current_ma': 0.0,  # 按时间加权平均
            'min_power_window_start': '',
            'min_power_window_end': '',
            'min_power_window_avg_current_ma': float('inf'),
            'max_power_window_start': '',
            'max_power_window_end': '',
            'max_power_window_avg_current_ma': float('-inf')
        }
    }
    
    # 用于计算加权平均电流的累积变量
    pass_current_sum = 0.0  # pass时段的电流*时间累积和
    fail_current_sum = 0.0  # fail时段的电流*时间累积和

    if len(all_battery_data) < 1:
        return summary

    # META信息：使用去重后数据的时间（与详细电池信息显示的一致）
    # analysis_start规则：
    # - 如果用户指定了开始时间，使用用户指定的时间
    # - 如果没有充电状态有值的记录，则使用第一条记录
    # - 如果有充电状态有值的记录，则使用最后一条充电状态结束后的第一条记录
    first_data = all_battery_data[0]
    
    if user_start_time:
        # 用户指定了开始时间，找到对应的记录
        start_dt = parse_datetime(user_start_time, base_year)
        for i, d in enumerate(all_battery_data):
            data_dt = parse_datetime(d['time'], base_year)
            if data_dt and data_dt >= start_dt:
                first_data = d
                break
    else:
        # 默认规则：跳过充电阶段
        last_chg_index = -1
        for j, d in enumerate(all_battery_data):
            if d['chg'] and d['chg'] != '无' and d['chg'] != '':
                last_chg_index = j
        if last_chg_index != -1 and last_chg_index + 1 < len(all_battery_data):
            first_data = all_battery_data[last_chg_index + 1]
    
    # analysis_end：
    # - 如果用户指定了结束时间，使用用户指定的时间
    # - 否则使用去重后数据的最后一条记录的时间
    last_data = all_battery_data[-1]
    
    if user_end_time:
        # 用户指定了结束时间，找到对应的记录
        end_dt = parse_datetime(user_end_time, base_year)
        for i, d in enumerate(all_battery_data):
            data_dt = parse_datetime(d['time'], base_year)
            if data_dt and data_dt >= end_dt:
                last_data = d
                break
    
    summary['META']['analysis_start'] = f"{format_datetime(first_data['time'], base_year)} (电量: {first_data['level']}%)"
    summary['META']['analysis_end'] = f"{format_datetime(last_data['time'], base_year)} (电量: {last_data['level']}%)"
    
    # 计算持续时间（先提取纯时间部分）
    start_time_str = summary['META']['analysis_start'].split(' (')[0] if ' (' in summary['META']['analysis_start'] else summary['META']['analysis_start']
    end_time_str = summary['META']['analysis_end'].split(' (')[0] if ' (' in summary['META']['analysis_end'] else summary['META']['analysis_end']
    start_dt = parse_datetime(start_time_str, base_year)
    end_dt = parse_datetime(end_time_str, base_year)
    if start_dt and end_dt:
        summary['META']['analysis_duration_h'] = round((end_dt - start_dt).total_seconds() / 3600.0, 2)
    else:
        summary['META']['analysis_duration_h'] = 0.0
        summary['META']['analysis_end'] = 'unknown'
        summary['META']['analysis_duration_h'] = 0.0
    
    # 计算整体平均电流：电池容量 * (analysis_start对应电量百分比 - analysis_end对应电量百分比) / 时间差（小时）
    if start_dt and end_dt and summary['META']['analysis_duration_h'] > 0:
        start_level = float(first_data['level'])
        end_level = float(last_data['level'])
        level_diff = start_level - end_level  # 电量差（下降为正）
        avg_total_current_ma = round(battery_capacity * level_diff / 100.0 / summary['META']['analysis_duration_h'], 2)
        summary['META']['avg_total_current_ma'] = avg_total_current_ma
    else:
        summary['META']['avg_total_current_ma'] = 0.0
    
    # 找到analysis_start和analysis_end在all_battery_data中的索引
    analysis_start_index = 0
    analysis_end_index = len(all_battery_data) - 1
    
    # 标准化时间精度为秒（去除毫秒），避免精度不匹配导致查找失败
    start_dt_normalized = start_dt.replace(microsecond=0) if start_dt else None
    end_dt_normalized = end_dt.replace(microsecond=0) if end_dt else None
    
    for i, data in enumerate(all_battery_data):
        data_dt = parse_datetime(data['time'], base_year)
        if data_dt:
            data_dt_normalized = data_dt.replace(microsecond=0)
            if data_dt_normalized == start_dt_normalized:
                analysis_start_index = i
                break
    
    for i, data in enumerate(all_battery_data):
        data_dt = parse_datetime(data['time'], base_year)
        if data_dt:
            data_dt_normalized = data_dt.replace(microsecond=0)
            if data_dt_normalized == end_dt_normalized:
                analysis_end_index = i
                break
    
    # 重新计算analysis_start到analysis_end范围内的平均电流
    # 确保平均电流的计算也只在analysis_start到analysis_end范围内进行
    analysis_range_data = all_battery_data[analysis_start_index:analysis_end_index + 1]
    analysis_range_average_currents = []
    
    for i, data in enumerate(analysis_range_data):
        # 第一条记录的平均电流为0
        if i == 0:
            analysis_range_average_currents.append(0.0)
        else:
            prev_data = analysis_range_data[i - 1]
            curr_level = float(data['level'])
            prev_level = float(prev_data['level'])
            
            # 检查上一条记录是否有充电状态有值，如果有则当前记录平均电流记为0
            if prev_data['chg'] and prev_data['chg'] != '无' and prev_data['chg'] != '':
                analysis_range_average_currents.append(0.0)
                continue
            
            # 计算时间差
            curr_time = parse_datetime(data['time'], base_year)
            prev_time = parse_datetime(prev_data['time'], base_year)
            time_diff = (curr_time - prev_time).total_seconds() / 3600.0  # 转换为小时
            
            if time_diff > 0:
                # 计算平均电流
                level_diff = prev_level - curr_level  # 电量差（下降为正）
                avg_current = battery_capacity * level_diff / 100.0 / time_diff
                analysis_range_average_currents.append(avg_current)
            else:
                analysis_range_average_currents.append(0.0)
    
    # 使用重新计算的平均电流进行统计
    average_currents = analysis_range_average_currents
    all_battery_data = analysis_range_data
    
    # JUMP_CHECK和POWER_SEGMENT分析：只统计analysis_start到analysis_end之间的数据
    abnormal_details = []
    
    # 遍历analysis_start到analysis_end之间的数据
    # 从第二条记录开始（因为第一条记录没有上一条记录）
    for i in range(1, len(all_battery_data)):
        prev_data = all_battery_data[i - 1]
        curr_data = all_battery_data[i]
        
        # 计算时间差
        curr_dt = parse_datetime(curr_data['time'], base_year)
        prev_dt = parse_datetime(prev_data['time'], base_year)
        time_diff_h = (curr_dt - prev_dt).total_seconds() / 3600.0 if curr_dt and prev_dt else 0.0
        
        # 获取平均电流
        avg_current = average_currents[i]
        
        # 提取充电状态
        curr_chg = curr_data['chg'] if curr_data['chg'] else '无'
        prev_chg = prev_data['chg'] if prev_data['chg'] else '无'
        
        # JUMP_CHECK: 检测电量或电压跳变（只在充电状态为"无"时统计）
        prev_level = int(prev_data['level']) if prev_data['level'] else 0
        curr_level = int(curr_data['level']) if curr_data['level'] else 0
        prev_voltage = int(prev_data['voltage']) if prev_data['voltage'] else 0
        curr_voltage = int(curr_data['voltage']) if curr_data['voltage'] else 0
        
        # 获取平均电流变化
        prev_avg_current = round(average_currents[i-1], 1) if i > 0 and len(average_currents) > i-1 else 0.0
        curr_avg_current = round(avg_current, 1)
        
        # 跳变检测规则：满足以下任一条件视为跳变
        # 1. 电量变化≥2
        # 2. 电压变化>0.2V
        # 3. 平均电流变化≥2000mA
        if curr_chg == '无' or prev_chg == '无':
            has_jump = False
            jump_parts = []
            
            # 计算各项变化值
            level_diff = abs(prev_level - curr_level)
            voltage_diff = abs(prev_voltage - curr_voltage) / 1000.0  # 转换为V
            current_diff = abs(prev_avg_current - curr_avg_current)
            
            # 规则1：电量变化≥2
            if level_diff >= 2:
                has_jump = True
                jump_parts.append(f"SOC {prev_level}->{curr_level} (变化{level_diff})")
                jump_parts.append(f"VOLT {prev_voltage/1000:.3f}V->{curr_voltage/1000:.3f}V")
                jump_parts.append(f"AVG_CURRENT {prev_avg_current}->{curr_avg_current}")
            
            # 规则2：电压变化>0.2V
            if voltage_diff > 0.2:
                has_jump = True
                jump_parts.append(f"VOLT {prev_voltage/1000:.3f}V->{curr_voltage/1000:.3f}V (变化{voltage_diff:.3f}V)")
            
            # 规则3：平均电流变化≥2000mA
            if current_diff >= 2000:
                has_jump = True
                jump_parts.append(f"AVG_CURRENT {prev_avg_current}->{curr_avg_current} (变化{current_diff:.1f}mA)")
            
            # 充电状态变化
            if (prev_chg == '无' or curr_chg == '无') and prev_chg != curr_chg:
                has_jump = True
                jump_parts.append(f"CHG_STATE {prev_chg}->{curr_chg}")
            
            if has_jump:
                summary['JUMP_CHECK']['has_soc_or_voltage_jump'] = True
                summary['JUMP_CHECK']['jump_count'] += 1
                jump_time = format_datetime(curr_data['time'], base_year)
                summary['JUMP_CHECK']['jumps'].append({
                    'time': jump_time,
                    'detail': '; '.join(jump_parts)
                })
        
        # HARDWARE_ABNORMAL: 检测瞬时电流超过阈值（只在没有充电状态时检测）
        prev_current = int(int(prev_data['current']) / 1000) if prev_data['current'] else 0  # 转换为毫安
        curr_current = int(int(curr_data['current']) / 1000) if curr_data['current'] else 0  # 转换为毫安
        if curr_chg == '无' and curr_current > hardware_threshold / 1000:
            summary['HARDWARE_ABNORMAL']['has_discharge_over_3a'] = True
            summary['HARDWARE_ABNORMAL']['abnormal_count'] += 1
            abnormal_details.append(f"{format_datetime(curr_data['time'], base_year)}: {int(curr_current * 1000)}mA")
        
        # POWER_SEGMENT: PASS/FAIL统计（分析范围内的所有时间都统计）
        # 充电状态时平均电流为0，会被计入pass
        if avg_current <= standby_threshold:
            summary['POWER_SEGMENT']['pass_duration_h'] += time_diff_h
            pass_current_sum += avg_current * time_diff_h  # 累积电流*时间
        elif avg_current > standby_threshold:
            summary['POWER_SEGMENT']['fail_duration_h'] += time_diff_h
            fail_current_sum += avg_current * time_diff_h  # 累积电流*时间
        
        # 更新最小/最大功耗窗口：排除硬件异常尖峰段（>hardware_threshold mA）
        if avg_current <= hardware_threshold:
            if avg_current < summary['POWER_SEGMENT']['min_power_window_avg_current_ma']:
                summary['POWER_SEGMENT']['min_power_window_avg_current_ma'] = round(avg_current, 2)
                summary['POWER_SEGMENT']['min_power_window_start'] = format_datetime(prev_data['time'], base_year)
                summary['POWER_SEGMENT']['min_power_window_end'] = format_datetime(curr_data['time'], base_year)

            if avg_current > summary['POWER_SEGMENT']['max_power_window_avg_current_ma']:
                summary['POWER_SEGMENT']['max_power_window_avg_current_ma'] = round(avg_current, 2)
                summary['POWER_SEGMENT']['max_power_window_start'] = format_datetime(prev_data['time'], base_year)
                summary['POWER_SEGMENT']['max_power_window_end'] = format_datetime(curr_data['time'], base_year)
    
    # 处理异常详情
    if abnormal_details:
        summary['HARDWARE_ABNORMAL']['abnormal_detail'] = '; '.join(abnormal_details)
    
    # 计算按时间加权的平均电流
    pass_duration = summary['POWER_SEGMENT']['pass_duration_h']
    fail_duration = summary['POWER_SEGMENT']['fail_duration_h']
    
    if pass_duration > 0:
        summary['POWER_SEGMENT']['pass_avg_current_ma'] = round(pass_current_sum / pass_duration, 2)
    else:
        summary['POWER_SEGMENT']['pass_avg_current_ma'] = 0.0
    
    if fail_duration > 0:
        summary['POWER_SEGMENT']['fail_avg_current_ma'] = round(fail_current_sum / fail_duration, 2)
    else:
        summary['POWER_SEGMENT']['fail_avg_current_ma'] = 0.0
    
    # 四舍五入
    summary['POWER_SEGMENT']['pass_duration_h'] = round(pass_duration, 2)
    summary['POWER_SEGMENT']['fail_duration_h'] = round(fail_duration, 2)

    if summary['POWER_SEGMENT']['min_power_window_avg_current_ma'] == float('inf'):
        summary['POWER_SEGMENT']['min_power_window_avg_current_ma'] = 0.0
    if summary['POWER_SEGMENT']['max_power_window_avg_current_ma'] == float('-inf'):
        summary['POWER_SEGMENT']['max_power_window_avg_current_ma'] = 0.0

    return summary

def print_summary(summary):
    """打印结构化分析摘要"""
    print("\n=== 结构化分析摘要(供下游SKILL输入) ===")
    
    print("[META]")
    print(f"analysis_start={summary['META'].get('analysis_start', 'unknown')}")
    print(f"analysis_end={summary['META'].get('analysis_end', 'unknown')}")
    print(f"analysis_duration_h={summary['META'].get('analysis_duration_h', 0)}")
    print(f"avg_total_current_ma={summary['META'].get('avg_total_current_ma', 0)}")
    
    print("\n[THRESHOLD]")
    print(f"standby_current_threshold_ma={summary['THRESHOLD']['standby_current_threshold_ma']}")
    print(f"hardware_discharge_abnormal_threshold_ma={summary['THRESHOLD']['hardware_discharge_abnormal_threshold_ma']}")
    
    print("\n[JUMP_CHECK]")
    print(f"has_soc_or_voltage_jump={str(summary['JUMP_CHECK']['has_soc_or_voltage_jump']).lower()}")
    print(f"jump_count={summary['JUMP_CHECK']['jump_count']}")
    for i, jump in enumerate(summary['JUMP_CHECK']['jumps'], 1):
        print(f"jump_{i}_time={jump['time']}")
        print(f"jump_{i}_detail={jump['detail']}")
    
    print("\n[HARDWARE_ABNORMAL]")
    print(f"has_discharge_over_3a={str(summary['HARDWARE_ABNORMAL']['has_discharge_over_3a']).lower()}")
    print(f"abnormal_count={summary['HARDWARE_ABNORMAL']['abnormal_count']}")
    print(f"abnormal_detail={summary['HARDWARE_ABNORMAL']['abnormal_detail']}")
    
    print("\n[POWER_SEGMENT]")
    print(f"pass_duration_h={summary['POWER_SEGMENT']['pass_duration_h']}")
    print(f"pass_avg_current_ma={summary['POWER_SEGMENT']['pass_avg_current_ma']}")
    print(f"fail_duration_h={summary['POWER_SEGMENT']['fail_duration_h']}")
    print(f"fail_avg_current_ma={summary['POWER_SEGMENT']['fail_avg_current_ma']}")
    print(f"min_power_window_start={summary['POWER_SEGMENT']['min_power_window_start']}")
    print(f"min_power_window_end={summary['POWER_SEGMENT']['min_power_window_end']}")
    print(f"min_power_window_avg_current_ma={summary['POWER_SEGMENT']['min_power_window_avg_current_ma']}")
    print(f"max_power_window_start={summary['POWER_SEGMENT']['max_power_window_start']}")
    print(f"max_power_window_end={summary['POWER_SEGMENT']['max_power_window_end']}")
    print(f"max_power_window_avg_current_ma={summary['POWER_SEGMENT']['max_power_window_avg_current_ma']}")

def main():
    """主函数"""
    _setup_utf8_stdio()
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="计算电池信息")
    parser.add_argument('-d', '--directory', required=True, help='日志路径（包含events_log文件的文件夹路径）')
    parser.add_argument('--start', help='待机开始时间（格式：YYYY-MM-DD HH:MM:SS），可选')
    parser.add_argument('--end', help='待机结束时间（格式：YYYY-MM-DD HH:MM:SS），可选')
    parser.add_argument('-c', '--capacity', type=int, help='电池容量(mAh)，可选。如果未指定，则自动从日志中提取fc=后的前四位数值作为默认值')
    parser.add_argument('-s', '--standby-threshold', type=int, default=25, help='待机电流阈值(mA)，可选。默认25，同时作为PASS/FAIL平均电流阈值')
    parser.add_argument('-H', '--hardware-threshold', type=int, default=3000, help='硬件放电异常阈值(mA)，可选。默认3000')
    parser.add_argument(
        '--format',
        choices=('text', 'json'),
        default='text',
        help='输出格式：text（默认，含详细表格）或 json（仅结构化摘要）',
    )

    args = parser.parse_args()

    input_path = args.directory
    start_time = args.start
    end_time = args.end

    if not _path_exists(input_path):
        print(f"错误：路径 '{input_path}' 不存在。")
        sys.exit(1)

    # 获取电池容量
    battery_capacity = args.capacity if args.capacity else extract_battery_capacity(input_path)
    if args.format != "json":
        print(f"使用电池容量: {battery_capacity} mAh")

    # 搜索linli_666文件中的healthd: battery关键字
    all_battery_data, original_first_data, original_last_data = search_healthd_battery(input_path, start_time, end_time)
    if not all_battery_data:
        print("错误：未找到有效的 healthd: battery 记录。")
        print("建议检查以下前置条件：")
        print("1. 目录中是否已生成 *_linli_666.txt 或 merged_kernel_log；若没有，请先运行 base_mtk_kernellog_convert。")
        print("2. kernel 日志中是否存在 healthd: battery 记录。")
        print("3. Windows 下若日志路径过深，请先将 APLog 复制到较短目录后重试。")
        sys.exit(2)

    # 显示详细电池信息
    if all_battery_data:
        # 先从第一条电池数据的时间中提取年份（使用原始数据）
        first_time_str = all_battery_data[0]['time']
        base_year, year_from_log = extract_year_from_healthd_time(first_time_str)
        if not year_from_log:
            linli_files = get_linli_666_files(input_path, recursive=True)
            if linli_files:
                base_year = extract_year_from_filename(linli_files[0])
        
        # 如果仍然无法获取年份，使用当前年份作为默认值
        if base_year is None:
            base_year = datetime.now().year

        # 计算平均电流（传递start_time，使计算从第一条匹配记录的下一条开始）
        average_currents = calculate_average_current(all_battery_data, battery_capacity, base_year, start_time)

        # 输出所有原始数据到report（不进行去重）- 已注释，不再输出
        # report_lines = []
        # report_lines.append(f"{'时间':<20} {'电量':<6} {'电压':<8} {'温度':<6} {'瞬时电流':<10}")
        # 
        # for i, data in enumerate(all_battery_data):
        #     # 计算瞬时电流（除以1000）
        #     try:
        #         current = float(data['current']) / 1000
        #     except ValueError:
        #         current = 0.0
        #     
        #     # 格式化时间
        #     time_str = data['time']
        #     formatted_time = format_datetime(time_str, base_year)
        #     
        #     # 电压格式：3.804（去掉V单位）
        #     voltage_val = f"{int(data['voltage']) / 1000:.3f}" if data['voltage'] else ""
        #     
        #     # 瞬时电流格式：-167（整数）
        #     current_int = int(round(current))
        #     
        #     report_lines.append(f"{formatted_time:<20} {data['level']:<6} {voltage_val:<8} {data['temp']:<6} {current_int:<10}")
        # 
        # # 将report写入文件
        # report_path = r"D:\Desktop\ai\jira\ai2d_powerandthermal\.agents\skills\tran_sw_skillhub\analysis\base\base_batteryinfo\report"
        # with open(report_path, 'w', encoding='utf-8') as report_file:
        #     report_file.write('\n'.join(report_lines))
        #     report_file.write('\n')
        # print(f"\n原始数据已输出到report文件: {report_path}")
        
        # 去重：仅当电量变化时才保留记录 - 仅用于控制台显示
        unique_battery_data = []
        unique_average_currents = []
        last_level = None
        for i, data in enumerate(all_battery_data):
            current_level = data['level']
            if current_level != last_level:
                unique_battery_data.append(data)
                unique_average_currents.append(average_currents[i])
                last_level = current_level
        
        # 更新为去重后的数据用于控制台显示
        all_battery_data = unique_battery_data
        average_currents = unique_average_currents
        
        # 重新计算去重后数据的平均电流（确保正确）
        if len(unique_battery_data) > 1:
            average_currents = calculate_average_current(unique_battery_data, battery_capacity, base_year, None)

        if args.format != "json":
            print("\n===== 详细电池信息 =====")
            print("-" * 170)
            print(f"{'开始时间':<23} {'结束时间':<23} {'电量(%)':<10} {'电压(V)':<10} {'温度(℃)':<10} {'瞬时电流(mA)':<15} {'平均电流(mA)':<15} {'充电状态':<20}")
            print("-" * 170)
            
            # 先处理第一条记录（索引0），开始时间和结束时间都使用第一条记录的时间
            if len(all_battery_data) > 0:
                data = all_battery_data[0]
                try:
                    current = float(data['current']) / 1000
                except ValueError:
                    current = 0.0
                avg_current = average_currents[0] if len(average_currents) > 0 else 0.0
                time_str = data['time']
                formatted_time = format_datetime(time_str, base_year)
                voltage_v = f"{int(data['voltage']) / 1000:.3f}V" if data['voltage'] else ""
                print(f"{formatted_time:<23} {formatted_time:<23} {data['level']:<10} {voltage_v:<10} {data['temp']:<10} {current:<15.3f} {avg_current:<15.3f} {data['chg']:<20}")
            
            # 处理从第二条记录开始的数据（使用上一条记录的时间作为开始时间）
            for i in range(1, len(all_battery_data)):
                data = all_battery_data[i]
                prev_data = all_battery_data[i - 1]
                
                try:
                    current = float(data['current']) / 1000
                except ValueError:
                    current = 0.0

                avg_current = average_currents[i] if i < len(average_currents) else 0.0

                start_time_str = prev_data['time']
                formatted_start_time = format_datetime(start_time_str, base_year)

                end_time_str = data['time']
                formatted_end_time = format_datetime(end_time_str, base_year)

                voltage_v = f"{int(data['voltage']) / 1000:.3f}V" if data['voltage'] else ""
                print(f"{formatted_start_time:<23} {formatted_end_time:<23} {data['level']:<10} {voltage_v:<10} {data['temp']:<10} {current:<15.3f} {avg_current:<15.3f} {data['chg']:<20}")
            print("-" * 170)
        
        # 生成并打印结构化分析摘要（使用完整的去重后数据）
        # 开始时间为扫描到的第一条电量信息对应的时间
        display_data = all_battery_data
        display_average_currents = average_currents
        
        summary = analyze_battery_data(
            display_data, 
            display_average_currents, 
            base_year,
            standby_threshold=args.standby_threshold,
            hardware_threshold=args.hardware_threshold,
            user_start_time=start_time,
            user_end_time=end_time,
            original_first_data=original_first_data,
            original_last_data=original_last_data,
            battery_capacity=battery_capacity
        )
        if args.format == "json":
            # 保持 analyze_battery_data 原生分段结构，由各领域 flow/runner 自行解读
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print_summary(summary)

if __name__ == "__main__":
    main()
