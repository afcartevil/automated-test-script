import os
from datetime import datetime, timedelta
import subprocess
import sys
import argparse

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
_BASE_LIB = os.path.abspath(
    os.path.join(_SCRIPT_DIR, "..", "..", "..", "..", "..", "base", "lib")
)
if _BASE_LIB not in sys.path:
    sys.path.insert(0, _BASE_LIB)
from netlog_paths import (  # noqa: E402
    normalize_standby_type,
    pick_cap_files_for_analysis,
)
from wireshark_cli import (  # noqa: E402
    configure_wireshark_cli,
    convert_tshark_frame_time,
    wireshark_cli_preflight,
    _require_command,
)


def _setup_utf8_stdio() -> None:
    """统一脚本标准输入输出编码为 UTF-8，减少 Windows 终端乱码。"""
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


global_file_path = ""
global_timestamp = ""
global_rrc_count= ""

def set_global_file_path(path):
    global global_file_path
    global_file_path = path

def get_global_file_path():
    return global_file_path

def set_global_rrc_count(count):
    global global_rrc_count
    global_rrc_count = count

def set_global_timestamp(timestamp):
    global global_timestamp
    global_timestamp = timestamp

def merge_cap_files(input_files, output_file):
    """合并多个 cap 文件为一个
    
    Args:
        input_files: 输入的 cap 文件列表
        output_file: 输出的合并文件路径
    """
    try:
        if not _require_command('mergecap', '合并多个 cap 文件'):
            return False
        # 使用 mergecap 命令合并文件（Wireshark 专用合并工具）
        # 构建命令：mergecap -w output.cap file1.cap file2.cap ...
        cmd = ['mergecap', '-w', output_file]
        cmd.extend(input_files)
        
        # 执行命令
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode("utf-8", errors="ignore") if isinstance(e.stderr, bytes) else (e.stderr or "")
        if stderr:
            print(f"mergecap 执行失败: {stderr.strip()}")
        return False
    except Exception as e:
        print(f"mergecap 执行失败: {e}")
        return False

#计算RRC时间，公式：RRC总时长是每个数据包RRC的累加时间
def calculate_default_rrc_time(file_path,threshold=10):
    """
    计算 linli.txt 文件中 RRC 累加时间。

    :param file_path: linli.txt 文件路径
    :param threshold: 时间间隔阈值（秒），默认为 10 秒
    :return: 累加时间（秒）
    """
    total_time = 0  # 累加时间
    last_time = None  # 上一个数据包的时间
    timestamps = [] # 存储所有时间戳

    def parse_time(time_str):
        """解析时间字符串，支持多种格式"""
        formats = [
            "%Y-%m-%d %H:%M:%S.%f",  # 带微秒格式: 2025-12-02 19:19:34.429816
            "%Y-%m-%d %H:%M:%S",      # 不带微秒格式: 2025-12-02 19:19:34
            "%Y-%m-%dT%H:%M:%S.%f%z", # ISO格式: 2025-12-02T19:19:34.429816+0800
        ]
        for fmt in formats:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        # 尝试 ISO format
        try:
            return datetime.fromisoformat(time_str.replace('000+0800', '+08:00'))
        except ValueError:
            return None

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                if line.startswith("Time:"):  # 找到时间行
                    time_str = line.split("Time:")[1].strip()
                    current_time = parse_time(time_str)
                    if current_time is None:
                        # 如果时间格式不正确，跳过该行
                        continue
                    timestamps.append(current_time)
                    if last_time:
                        # 计算当前时间与上一个时间的间隔
                        interval = (current_time - last_time).total_seconds()
                        if interval <= threshold:
                            total_time += interval
                        else:
                            total_time += threshold
                    last_time = current_time  # 更新上一个时间
        
        if not timestamps:
            return -1
            
        time_interval = (timestamps[-1] - timestamps[0]).total_seconds()
        set_global_timestamp(time_interval)
        return total_time
    except FileNotFoundError:
        return -1
    except Exception as e:
        return -1


def calculate_rrc_time(file_path, start_time, end_time, threshold=10):
    """
    计算 linli.txt 文件中 RRC 累加时间，考虑 start_time 和 end_time 的不同情况。

    :param file_path: linli.txt 文件路径
    :param start_time: 开始时间，格式为 "YYYY-MM-DD HH:MM:SS"
    :param end_time: 结束时间，格式为 "YYYY-MM-DD HH:MM:SS"
    :param threshold: 时间间隔阈值（秒），默认为 10 秒
    :return: 累加时间（秒）
    """
    total_time = 0  # 累加时间
    last_time = None  # 上一个数据包的时间
    timestamps_in_range = []  # 存储在时间范围内的时间戳

    def parse_time(time_str):
        """解析时间字符串，支持多种格式"""
        formats = [
            "%Y-%m-%d %H:%M:%S.%f",  # 带微秒格式: 2025-12-02 19:19:34.429816
            "%Y-%m-%d %H:%M:%S",      # 不带微秒格式: 2025-12-02 19:19:34
            "%Y-%m-%dT%H:%M:%S.%f%z", # ISO格式: 2025-12-02T19:19:34.429816+0800
        ]
        for fmt in formats:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        # 尝试 ISO format
        try:
            return datetime.fromisoformat(time_str.replace('000+0800', '+08:00'))
        except ValueError:
            return None

    # 转换 start_time 和 end_time 为 datetime 对象
    start_time_dt = None
    end_time_dt = None

    try:
        if start_time:
            start_time_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        if end_time:
            end_time_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return -1

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                if line.startswith("Time:"):  # 找到时间行
                    time_str = line.split("Time:")[1].strip()
                    current_time = parse_time(time_str)
                    if current_time is None:
                        # 如果时间格式不正确，跳过该行
                        continue
                        
                    # 检查时间范围
                    in_range = True
                    if start_time_dt and current_time < start_time_dt:
                        in_range = False
                    if end_time_dt and current_time > end_time_dt:
                        in_range = False
                    
                    if in_range:
                        # 只存储在时间范围内的时间戳
                        timestamps_in_range.append(current_time)
                        
                        # 计算 RRC 时长
                        if last_time:
                            interval = (current_time - last_time).total_seconds()
                            if interval <= threshold:
                                total_time += interval
                            else:
                                total_time += threshold
                        last_time = current_time  # 更新上一个时间

            # 如果没有时间戳，返回 (RRC累加秒, 时间窗秒) 与正常路径一致
            if not timestamps_in_range:
                return 0, 0

            # 根据时间范围内的数据包计算总时长
            actual_start = timestamps_in_range[0]
            actual_end = timestamps_in_range[-1]
            time_interval = (actual_end - actual_start).total_seconds()
            
        total_time = round(total_time, 1) 
        return total_time, time_interval
    except FileNotFoundError:
        return -1
    except Exception as e:
        return -1


#计算数据包的次数，公式：RRC次数=中间隔超过指定秒数的数据包数量
def count_large_intervals(file_path, threshold=10):
    """
    统计 linli.txt 文件中间隔超过指定秒数的数据包数量。

    :param file_path: linli.txt 文件路径
    :param threshold: 时间间隔阈值（秒），默认为 10 秒
    :return: 超过阈值的间隔数量
    """
    count = 0
    last_time = None  # 用于存储上一个数据包的时间
    
    def parse_time(time_str):
        """解析时间字符串，支持多种格式"""
        formats = [
            "%Y-%m-%d %H:%M:%S.%f",  # 带微秒格式: 2025-12-02 19:19:34.429816
            "%Y-%m-%d %H:%M:%S",      # 不带微秒格式: 2025-12-02 19:19:34
            "%Y-%m-%dT%H:%M:%S.%f%z", # ISO格式: 2025-12-02T19:19:34.429816+0800
        ]
        for fmt in formats:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        # 尝试 ISO format
        try:
            return datetime.fromisoformat(time_str.replace('000+0800', '+08:00'))
        except ValueError:
            return None

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                if line.startswith("Time:"):  # 找到时间行
                    time_str = line.split("Time:")[1].strip()
                    current_time = parse_time(time_str)
                    if current_time is None:
                        # 如果时间格式不正确，跳过该行
                        continue
                    if last_time:
                        # 计算当前时间与上一个时间的间隔
                        interval = (current_time - last_time).total_seconds()
                        if interval > threshold:
                            count += 1
                    last_time = current_time  # 更新上一个时间
        set_global_rrc_count(count)
        return count
    except FileNotFoundError:
        return -1
    except Exception as e:
        return -1

def convert_to_linli_timestamp(start_time, end_time):
    """
    将用户输入的不规则时间格式转换为 linli.txt 的时间戳格式。
    linli.txt 时间戳格式为 "YYYY-MM-DD HH:MM:SS"。

    参数:
        start_time (str): 用户输入的开始时间（可以为空）。
        end_time (str): 用户输入的结束时间（可以为空）。

    返回:
        tuple: 转换后的 (start_timestamp, end_timestamp)，格式为 "YYYY-MM-DD HH:MM:SS"。
    """
    def normalize_time(input_time):
        """
        将单个时间字符串转换为 linli.txt 的时间戳格式。
        """
        if not input_time:
            return None  # 如果时间为空，直接返回 None
        try:
            # 尝试解析用户输入的时间（支持多种格式）
            possible_formats = [
                "%Y:%m:%d %H:%M:%S",  # 格式 1: "2025:05:21 18:03:05"
                "%Y/%m/%d %H:%M:%S",  # 格式 2: "2025/05/21 18:03:05"
                "%Y-%m-%d %H:%M:%S",  # 格式 3: "2025-05-21 18:03:05"
                "%Y%m%d %H:%M:%S",    # 格式 4: "20250521 18:03:05"
                "%Y.%m.%d %H:%M:%S"   # 格式 5: "2025.05.21 18:03:05"
            ]
            for fmt in possible_formats:
                try:
                    # 尝试使用不同格式解析时间
                    parsed_time = datetime.strptime(input_time, fmt)
                    # 转换为 linli.txt 的时间戳格式
                    return parsed_time.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
            # 如果所有格式都无法解析，抛出异常
            raise ValueError(f"无法解析时间格式: {input_time},时间格式应为 YYYY-MM-DD HH:MM:SS")
        except Exception as e:
            return None

    # 转换 start_time 和 end_time
    start_timestamp = normalize_time(start_time)
    end_timestamp = normalize_time(end_time)

    return start_timestamp, end_timestamp


def get_time_range_from_linli(file_path):
    """
    从 linli.txt 文件中获取第一个包和最后一个包的时间。
    
    :param file_path: linli.txt 文件路径
    :return: (first_time, last_time) 元组，格式为 "YYYY-MM-DD HH:MM:SS"
    """
    first_time = None
    last_time = None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                if line.startswith("Time:"):  # 找到时间行
                    time_str = line.split("Time:")[1].strip()
                    try:
                        # 解析时间字符串
                        if len(time_str) >= 19:
                            # 提取 YYYY-MM-DD HH:MM:SS 部分
                            time_str_short = time_str[:19]
                            if first_time is None:
                                first_time = time_str_short
                            last_time = time_str_short
                    except Exception:
                        continue
    except Exception:
        pass
    
    return first_time, last_time


#计算功耗，公式：功耗=RRC时长*100/总时长+空闲时长*9.6/总时长
def calculate_default_power(output_file):
    rrc_time = calculate_default_rrc_time(output_file)  #计算RRC时长
    if rrc_time == -1:
        raise ValueError("无法计算 RRC 时长，可能是文件未找到或格式错误")
    if global_timestamp == "" or global_timestamp <= 0:
        raise ValueError("全局时间戳无效")
    rrc_power=rrc_time*100/global_timestamp     #计算连接态功功耗
    idle_power=(global_timestamp-rrc_time)*9.6/global_timestamp  #计算空闲态功耗
    total_power=rrc_power+idle_power
    total_power = round(total_power, 2)  # 四舍五入到百分位
    rrc_time = round(rrc_time, 1)  # 四舍五入到十分位
    
    # 获取时间范围
    first_time, last_time = get_time_range_from_linli(output_file)
    
    return total_power,rrc_time, first_time, last_time

def calculate_power(output_file,start_time,end_time):
    time=convert_to_linli_timestamp(start_time,end_time)
    rrc_result = calculate_rrc_time(output_file, time[0], time[1])  # (RRC累加秒, 时间窗秒)
    if rrc_result == -1:
        raise ValueError("无法计算 RRC 时长，可能是文件未找到或格式错误")
    if isinstance(rrc_result, (int, float)):
        rrc_sec = float(rrc_result)
        span_sec = float(global_timestamp) if global_timestamp else 0.0
    else:
        rrc_sec, span_sec = rrc_result
        rrc_sec = float(rrc_sec)
        span_sec = float(span_sec)
    if span_sec <= 0:
        raise ValueError("时间窗无效或 linli 日志在指定时段无数据包")
    rrc_power = rrc_sec * 100 / span_sec
    idle_power = (span_sec - rrc_sec) * 9.6 / span_sec
    total_power = rrc_power + idle_power
    total_power = round(total_power, 2)
    return total_power, round(rrc_sec, 1)


def count_packets_in_window(output_file: str, start_time: str | None, end_time: str | None) -> int:
    """统计时间窗内数据包数量（linli.txt 中 Time: 行数）。"""
    start_ts, end_ts = convert_to_linli_timestamp(start_time, end_time)
    start_dt = end_dt = None
    fmts = ["%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"]
    if start_ts:
        for fmt in fmts:
            try:
                start_dt = datetime.strptime(start_ts, fmt)
                break
            except ValueError:
                continue
    if end_ts:
        for fmt in fmts:
            try:
                end_dt = datetime.strptime(end_ts, fmt)
                break
            except ValueError:
                continue
    count = 0
    try:
        with open(output_file, "r", encoding="utf-8") as fh:
            for line in fh:
                if not line.startswith("Time:"):
                    continue
                time_str = line.split("Time:", 1)[1].strip()[:19]
                dt = None
                for fmt in fmts:
                    try:
                        dt = datetime.strptime(time_str, fmt)
                        break
                    except ValueError:
                        continue
                if dt is None:
                    continue
                if start_dt and dt < start_dt:
                    continue
                if end_dt and dt > end_dt:
                    continue
                count += 1
    except OSError:
        return 0
    return count


def analyze_transfer_window(
    output_file: str,
    start_time: str | None,
    end_time: str | None,
) -> dict:
    """结构化数传指标，供 flow 输出与 runner 消费。"""
    total_power, rrc_sec = calculate_power(output_file, start_time, end_time)
    start_ts, end_ts = convert_to_linli_timestamp(start_time, end_time)
    rrc_result = calculate_rrc_time(output_file, start_ts, end_ts)
    span_sec = 0.0
    if isinstance(rrc_result, tuple) and rrc_result != -1:
        span_sec = float(rrc_result[1])
    window_h = round(span_sec / 3600.0, 3) if span_sec > 0 else 0.0
    transfer_duration_h = round(float(rrc_sec) / 3600.0, 3) if rrc_sec else 0.0
    packet_count = count_packets_in_window(output_file, start_time, end_time)
    freq_per_h = round(packet_count / window_h, 2) if window_h > 0 else 0.0
    return {
        "start_time": start_time,
        "end_time": end_time,
        "data_transfer_power_ma": total_power,
        "transfer_duration_h": transfer_duration_h,
        "window_duration_h": window_h,
        "packet_count": packet_count,
        "freq_per_h": freq_per_h,
        "rrc_active_sec": rrc_sec,
    }

def extract_time_from_cap_filename(cap_file_path):
    """从 cap 文件名中提取时间
    
    :param cap_file_path: cap 文件路径
    :return: 提取的时间（datetime 对象），如果无法提取返回 None
    """
    import re
    filename = os.path.basename(cap_file_path)
    # 匹配格式: tcpdump_NTLog_V2_2025_1125_224412_start_1
    match = re.search(r'tcpdump_NTLog_V2_(\d{4})_(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})', filename)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        hour = int(match.group(4))
        minute = int(match.group(5))
        second = int(match.group(6))
        return datetime(year, month, day, hour, minute, second)
    return None

def get_first_time_from_linli(linli_file_path):
    """获取 linli.txt 文件中第一个包的时间
    
    :param linli_file_path: linli.txt 文件路径
    :return: 第一个包的时间（datetime 对象），如果无法提取返回 None
    """
    try:
        with open(linli_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith("Time:"):
                    time_str = line.split("Time:")[1].strip()
                    # 尝试解析时间
                    formats = [
                        "%Y-%m-%d %H:%M:%S.%f",
                        "%Y-%m-%d %H:%M:%S",
                    ]
                    for fmt in formats:
                        try:
                            return datetime.strptime(time_str, fmt)
                        except ValueError:
                            continue
                    return None
        return None
    except Exception as e:
        return None

def correct_linli_time(linli_file_path, cap_file_path):
    """校正 linli.txt 文件中的时间
    
    :param linli_file_path: linli.txt 文件路径
    :param cap_file_path: cap 文件路径
    :return: 是否校正成功
    """
    cap_time = extract_time_from_cap_filename(cap_file_path)
    if cap_time is None:
        return True
    
    first_time = get_first_time_from_linli(linli_file_path)
    if first_time is None:
        return True
    
    cap_time_minutes = cap_time.hour * 60 + cap_time.minute
    first_time_minutes = first_time.hour * 60 + first_time.minute
    
    time_diff_minutes = first_time_minutes - cap_time_minutes
    
    if time_diff_minutes > 720:
        time_diff_minutes -= 1440
    elif time_diff_minutes < -720:
        time_diff_minutes += 1440
    
    if time_diff_minutes == 0:
        return True
    
    corrected_lines = []
    try:
        with open(linli_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith("Time:"):
                    time_str = line.split("Time:")[1].strip()
                    parsed_time = None
                    formats = [
                        "%Y-%m-%d %H:%M:%S.%f",
                        "%Y-%m-%d %H:%M:%S",
                    ]
                    for fmt in formats:
                        try:
                            parsed_time = datetime.strptime(time_str, fmt)
                            break
                        except ValueError:
                            continue
                    
                    if parsed_time is not None:
                        corrected_time = parsed_time - timedelta(minutes=time_diff_minutes)
                        corrected_lines.append(f"Time: {corrected_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    else:
                        corrected_lines.append(line)
                else:
                    corrected_lines.append(line)
        
        with open(linli_file_path, 'w', encoding='utf-8') as f:
            f.writelines(corrected_lines)
        
        return True
    except Exception:
        return False

def parse_cap_file(cap_file_path):
    """解析 .cap 文件并生成 linli.txt，时间格式为 YYYY-MM-DD HH:MM:SS"""
    output_file = os.path.join(os.path.dirname(cap_file_path), "linli.txt")
    
    try:
        if not _require_command('tshark', '解析 cap 文件'):
            return False
        # 使用 tshark 命令行工具解析文件
        cmd = [
            'tshark',
            '-r', cap_file_path,
            '-T', 'fields',
            '-e', 'frame.number',
            '-e', 'frame.time',
            '-e', '_ws.col.Protocol',
            '-e', 'ip.src',
            '-e', 'ip.dst',
            '-E', 'separator=|'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        
        if result.returncode != 0:
            if result.stderr:
                print(f"tshark 解析失败: {result.stderr.strip()}")
            return False
        
        lines = result.stdout.strip().split('\n')
        
        if not lines or (len(lines) == 1 and not lines[0].strip()):
            print("tshark 未解析出任何数据包，未生成 linli.txt")
            return False
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for line in lines:
                if not line.strip():
                    continue
                parts = line.split('|')
                if len(parts) >= 5:
                    packet_no = parts[0].strip()
                    time_str = parts[1].strip()
                    # 将时间格式转换为 YYYY-MM-DD HH:MM:SS
                    formatted_time = convert_tshark_frame_time(time_str)
                    protocol = parts[2].strip()
                    src_ip = parts[3].strip() if parts[3].strip() else 'N/A'
                    dst_ip = parts[4].strip() if parts[4].strip() else 'N/A'
                    
                    f.write(f"Packet No: {packet_no}\n")
                    f.write(f"Time: {formatted_time}\n")
                    f.write(f"Protocol: {protocol}\n")
                    f.write(f"Source: {src_ip}\n")
                    f.write(f"Destination: {dst_ip}\n")
                    f.write("\n" + "=" * 50 + "\n")
        
        # 检查生成的文件大小
        if os.path.exists(output_file):
            file_size = os.path.getsize(output_file)
            if file_size == 0:
                print("linli.txt 已生成但内容为空")
                return False
        else:
            print("未生成 linli.txt")
            return False
        
        return True
    except Exception as e:
        print(f"解析 cap 文件失败: {e}")
        return False

# 运行数传功耗模型
if __name__ == "__main__":
    _setup_utf8_stdio()
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="计算蜂窝数传功耗")
    parser.add_argument('-d', '--directory', help='日志路径（cap文件路径或包含cap文件的文件夹路径）')
    parser.add_argument('-t', '--time', nargs='*', metavar=('START_TIME', 'END_TIME'), help='开始时间和结束时间（格式：YYYY-MM-DD HH:MM:SS），可选。若只指定一个时间，则视为开始时间；若第一个时间为空，则视为只指定结束时间')
    parser.add_argument('--wireshark-dir', help='可选：指定 Wireshark 安装目录（包含 tshark/mergecap）')
    parser.add_argument('--auto-install-wireshark', action='store_true', help='Windows 下若缺少 tshark/mergecap，尝试使用 winget 自动安装 Wireshark CLI')
    parser.add_argument(
        '--check-wireshark-cli',
        action='store_true',
        help='仅检测（或自动安装）主机上的 tshark/mergecap，不分析 cap；无需 -d',
    )
    parser.add_argument(
        '--standby-type',
        default='DATA',
        help='待机类型：DATA（蜂窝，默认）/ WIFI；WIFI 时应使用 wifi_data.py',
    )
    parser.add_argument(
        '--detect-caps',
        action='store_true',
        help='仅探测 cap 路径（JSON），不分析；需 -d 指向工作区/NTLog/converted',
    )
    parser.add_argument('--format', choices=('text', 'json'), default='text', help='输出格式')

    args = parser.parse_args()
    if args.check_wireshark_cli:
        ok, msg = wireshark_cli_preflight(
            auto_install=args.auto_install_wireshark,
            wireshark_dir=args.wireshark_dir or "",
        )
        print(msg)
        sys.exit(0 if ok else 1)

    standby_type = normalize_standby_type(args.standby_type) or "DATA"
    if standby_type != "DATA":
        parser.error("modem_data.py 仅用于 DATA/蜂窝待机；WiFi 待机请使用 wifi_data.py")

    if args.detect_caps:
        if not args.directory:
            parser.error("--detect-caps 需要 -d/--directory")
        import json
        from netlog_paths import resolve_data_transfer  # noqa: E402

        print(
            json.dumps(
                resolve_data_transfer(args.directory, standby_type),
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(0)

    if not args.directory:
        parser.error("分析 cap 时必须指定 -d/--directory；仅检测工具时用 --check-wireshark-cli")

    configure_wireshark_cli(
        auto_install=args.auto_install_wireshark,
        wireshark_dir=args.wireshark_dir or "",
    )

    input_path = args.directory
    start_time = None
    end_time = None
    
    # 规范化路径（处理空格和特殊字符）
    input_path = os.path.normpath(input_path.strip())
    
    # 处理长路径（超过 260 字符）问题，使用 UNC 路径前缀
    if len(input_path) > 250 and not input_path.startswith('\\\\?\\'):
        # 转换为绝对路径并添加 UNC 前缀
        input_path = '\\\\?\\' + os.path.abspath(input_path)
    
    if args.time:
        if len(args.time) == 1:
            start_time = args.time[0]
        elif len(args.time) >= 2:
            start_time = args.time[0]
            end_time = args.time[1]
            if not start_time:
                start_time = None
    
    if not os.path.exists(input_path):
        print(f"错误：路径不存在: {input_path}")
        sys.exit(1)
    
    # 检查是文件还是文件夹
    if os.path.isfile(input_path) and input_path.lower().endswith('.cap'):
        selected_file = input_path
        scan_path = os.path.dirname(input_path)
    elif os.path.isdir(input_path):
        scan_path, cap_file_paths = pick_cap_files_for_analysis(input_path, "DATA")
        if not cap_file_paths:
            print(f"错误：未在 {scan_path} 找到适用于 DATA/蜂窝 的 .cap 文件。")
            print("提示：先 base_prepare_workspace，再对 temp/<DATE>/<KEY>/ 或 converted/NTLog/ 执行。")
            sys.exit(1)
        if len(cap_file_paths) > 1:
            merged_name = (
                "merged_tcp.cap"
                if os.path.basename(cap_file_paths[0]).lower().startswith("tcp")
                else "merged.cap"
            )
            merged_file = os.path.join(scan_path, merged_name)
            success = merge_cap_files(cap_file_paths, merged_file)
            if success:
                selected_file = merged_file
            else:
                print("警告：多个 cap 合并失败，回退为仅分析第一个 cap 文件，结果可能不完整。")
                selected_file = cap_file_paths[0]
        else:
            selected_file = cap_file_paths[0]
    else:
        print("错误：输入必须是 .cap 文件或包含 .cap 文件的目录。")
        sys.exit(1)
    
    set_global_file_path(selected_file)
    
    output_file = os.path.join(os.path.dirname(selected_file), "linli.txt")
    
    linli_usable = os.path.exists(output_file) and get_first_time_from_linli(output_file) is not None
    if not linli_usable:
        success = parse_cap_file(selected_file)
        if not success:
            print("错误：cap 解析失败，无法继续计算数传功耗。")
            sys.exit(1)
    correct_linli_time(output_file, selected_file)
    
    # 计算功耗
    try:
        import json

        if start_time or end_time:
            metrics = analyze_transfer_window(output_file, start_time, end_time)
            if args.format == "json":
                print(json.dumps(metrics, ensure_ascii=False, indent=2))
            else:
                print(
                    f"Start_time: {metrics['start_time']}, End_time: {metrics['end_time']}, "
                    f"data_transfer_power: {metrics['data_transfer_power_ma']:.2f}mA, "
                    f"freq_per_h: {metrics['freq_per_h']}, "
                    f"transfer_duration_h: {metrics['transfer_duration_h']}"
                )
        else:
            total_power, rrc_time, first_time, last_time = calculate_default_power(output_file)
            start_display = first_time if first_time else "all"
            end_display = last_time if last_time else "all"
            payload = {
                "start_time": start_display,
                "end_time": end_display,
                "data_transfer_power_ma": total_power,
                "transfer_duration_h": round(float(rrc_time) / 3600.0, 3),
                "rrc_active_sec": rrc_time,
            }
            if args.format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(
                    f"Start_time: {start_display}, End_time: {end_display}, "
                    f"data_transfer_power: {total_power:.2f}mA"
                )
    except Exception as e:
        print(f"计算功耗时发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)