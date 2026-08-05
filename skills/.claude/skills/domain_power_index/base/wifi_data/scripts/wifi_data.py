import os
import pyshark
from datetime import datetime
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
global_rrc_count = ""

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
        mergecap = _require_command("mergecap", "合并多个 cap 文件")
        if not mergecap:
            return False
        cmd = [mergecap, "-w", output_file]
        cmd.extend(input_files)
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except Exception:
        return False

#计算RRC时间，公式：RRC总时长是每个数据包RRC的累加时间
def calculate_default_rrc_time(file_path,threshold=1):
    """
    计算 linli.txt 文件中 RRC 累加时间。

    :param file_path: linli.txt 文件路径
    :param threshold: 时间间隔阈值（秒），默认为 1 秒
    :return: 累加时间（秒）, WiFi_datactt（数据包密集时间）, WiFi_data_spt（数据包稀疏时间）
    """
    total_time = 0  # 累加时间
    wifi_datactt = 0  # 数据包密集时间（间隔<=3秒）
    wifi_data_spt = 0  # 数据包稀疏时间（间隔>3秒）
    last_time = None  # 上一个数据包的时间
    timestamps = [] # 存储所有时间戳

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                if line.startswith("Time:"):  # 找到时间行
                    time_str = line.split("Time:")[1].strip()
                    try:
                        # 解析时间字符串为 datetime 对象
                        # 支持多种时间格式：tshark 输出格式和 pyshark 输出格式
                        if 'T' in time_str and '+' in time_str:
                            # tshark 格式: 2025-12-02T19:19:34.429816000+0800
                            current_time = datetime.fromisoformat(time_str.replace('000+0800', '+08:00'))
                        else:
                            # pyshark 格式: 2025-12-02 19:19:34.429816
                            current_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
                        timestamps.append(current_time)
                        if last_time:
                            # 计算当前时间与上一个时间的间隔
                            interval = (current_time - last_time).total_seconds()
                            if interval <= threshold:
                                total_time += interval
                                wifi_datactt += interval
                            else:
                                total_time += threshold
                                wifi_data_spt += threshold
                        last_time = current_time  # 更新上一个时间
                    except ValueError:
                        # 如果时间格式不正确，跳过该行
                        continue
            
            # 检查 timestamps 列表是否为空
            if len(timestamps) == 0:
                return 0, 0, 0
            
            if len(timestamps) >= 2:
                time_interval = (timestamps[-1] - timestamps[0]).total_seconds()
                set_global_timestamp(time_interval)
            else:
                set_global_timestamp(0)
        return total_time, wifi_datactt, wifi_data_spt
    except FileNotFoundError:
        return -1, 0, 0
    except Exception as e:
        return -1, 0, 0


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
    timestamps = []  # 存储所有时间戳

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
                    try:
                        # 解析时间字符串为 datetime 对象
                        current_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
                        
                        # 存储所有时间戳
                        timestamps.append(current_time)

                        # 检查时间范围
                        if start_time_dt and current_time < start_time_dt:
                            continue  # 如果当前时间小于 start_time，跳过
                        if end_time_dt and current_time > end_time_dt:
                            continue  # 如果当前时间大于 end_time，跳过

                        # 计算 RRC 时长
                        if last_time:
                            interval = (current_time - last_time).total_seconds()
                            if interval <= threshold:
                                total_time += interval
                            else:
                                total_time += threshold
                        last_time = current_time  # 更新上一个时间
                    except ValueError:
                        # 如果时间格式不正确，跳过该行
                        continue

            # 如果没有时间戳，直接返回
            if not timestamps:
                return 0, 0

            # 根据 start_time 和 end_time 的情况调整范围
            if start_time and not end_time:
                # 只有 start_time，计算 start_time 到最后一个数据包
                start_time_dt = max(start_time_dt, timestamps[0])  # 确保 start_time 在范围内
                end_time_dt = timestamps[-1]
            elif end_time and not start_time:
                # 只有 end_time，计算第一个数据包到 end_time
                start_time_dt = timestamps[0]
                end_time_dt = min(end_time_dt, timestamps[-1])
            elif start_time and end_time:
                # 两者都有，确保范围在文件时间戳内
                start_time_dt = max(start_time_dt, timestamps[0])
                end_time_dt = min(end_time_dt, timestamps[-1])

            time = (end_time_dt - start_time_dt).total_seconds()
        total_time = round(total_time, 1) 
        return total_time, time
    except FileNotFoundError:
        return -1, 0
    except Exception as e:
        return -1, 0


def count_large_intervals(file_path, threshold=1):
    """
    统计 linli.txt 文件中间隔超过指定秒数的数据包数量。

    :param file_path: linli.txt 文件路径
    :param threshold: 时间间隔阈值（秒），默认为 1 秒
    :return: 超过阈值的间隔数量
    """
    count = 0
    last_time = None  # 用于存储上一个数据包的时间
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                if line.startswith("Time:"):  # 找到时间行
                    time_str = line.split("Time:")[1].strip()
                    try:
                        # 解析时间字符串为 datetime 对象
                        current_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
                        if last_time:
                            # 计算当前时间与上一个时间的间隔
                            interval = (current_time - last_time).total_seconds()
                            if interval > threshold:
                                count += 1
                        last_time = current_time  # 更新上一个时间
                    except ValueError:
                        # 如果时间格式不正确，跳过该行
                        continue
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
    # 解包返回的元组
    rrc_time_total = rrc_time[0]
    wifi_datactt = rrc_time[1]
    wifi_data_spt = rrc_time[2]

    # 保护：总时长为 0 或空值时无数据，返回 0
    try:
        ts = float(global_timestamp) if global_timestamp else 0
    except (ValueError, TypeError):
        ts = 0
    if ts <= 0:
        first_time, last_time = get_time_range_from_linli(output_file)
        return 0, 0, first_time, last_time

    rrc_datactt_power = wifi_datactt * 60 / ts     #计算连接态功耗
    wifi_data_spt_power = wifi_data_spt * 180 / ts     #计算稀疏态功耗
    idle_power = (ts - (wifi_datactt + wifi_data_spt)) * 9.6 / ts  #计算空闲态功耗
    total_power = rrc_datactt_power + wifi_data_spt_power + idle_power
    total_power = round(total_power, 2)  # 四舍五入到百分位
    rrc_time_total = round(rrc_time_total, 1)  # 四舍五入到十分位
    
    # 获取时间范围
    first_time, last_time = get_time_range_from_linli(output_file)
    
    return total_power, rrc_time_total, first_time, last_time


def calculate_power(output_file, start_time, end_time):
    time = convert_to_linli_timestamp(start_time, end_time)
    rrc_time = calculate_rrc_time(output_file, time[0], time[1])  #计算RRC时长

    # 保护：总时长为 0 或负值时无数据，返回 0
    if not rrc_time[1] or rrc_time[1] <= 0:
        return 0, 0

    rrc_power = rrc_time[0] * 100 / rrc_time[1]     #计算连接态功耗
    idle_power = (rrc_time[1] - rrc_time[0]) * 9.6 / rrc_time[1]  #计算空闲态功耗
    total_power = rrc_power + idle_power
    total_power = round(total_power, 2)  # 四舍五入到百分位
    return total_power, rrc_time[0]


def parse_cap_file(cap_file_path):
    """解析 .cap 文件并生成 linli.txt，时间格式为 YYYY-MM-DD HH:MM:SS"""
    output_file = os.path.join(os.path.dirname(cap_file_path), "linli.txt")
    
    try:
        tshark = _require_command("tshark", "解析 cap 文件")
        if not tshark:
            return False
        cmd = [
            tshark,
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
            return False
        
        lines = result.stdout.strip().split('\n')
        
        if not lines or (len(lines) == 1 and not lines[0].strip()):
            return False
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for line in lines:
                if not line.strip():
                    continue
                parts = line.split('|')
                if len(parts) >= 5:
                    packet_no = parts[0].strip()
                    time_str = parts[1].strip()
                    protocol = parts[2].strip()
                    src_ip = parts[3].strip() if parts[3].strip() else 'N/A'
                    dst_ip = parts[4].strip() if parts[4].strip() else 'N/A'
                    
                    formatted_time = convert_tshark_frame_time(time_str)
                    
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
                return False
        else:
            return False
        
        return True
    except Exception as e:
        return False


# 运行数传功耗模型
if __name__ == "__main__":
    _setup_utf8_stdio()
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="计算WiFi数传功耗")
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
        default='WIFI',
        help='待机类型：WIFI（默认）/ DATA；DATA 时应使用 modem_data.py',
    )
    parser.add_argument(
        '--detect-caps',
        action='store_true',
        help='仅探测 cap 路径（JSON），不分析；需 -d 指向工作区/NTLog/converted',
    )

    args = parser.parse_args()
    if args.check_wireshark_cli:
        ok, msg = wireshark_cli_preflight(
            auto_install=args.auto_install_wireshark,
            wireshark_dir=args.wireshark_dir or "",
        )
        print(msg)
        sys.exit(0 if ok else 1)

    standby_type = normalize_standby_type(args.standby_type) or "WIFI"
    if standby_type != "WIFI":
        parser.error("wifi_data.py 仅用于 WIFI 待机；蜂窝/Data 待机请使用 modem_data.py")

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
        sys.exit(1)
    
    # 检查是文件还是文件夹
    if os.path.isfile(input_path) and input_path.lower().endswith('.cap'):
        selected_file = input_path
    elif os.path.isdir(input_path):
        scan_path, cap_file_paths = pick_cap_files_for_analysis(input_path, "WIFI")
        if not cap_file_paths:
            # 无 WiFi cap 文件（NTLog 可能仅含蜂窝 tcpdump），输出结构化 "no data" 信息后正常退出
            print(f"WIFI_CAP_NOT_FOUND: 未在 {scan_path} 找到 WLAN .cap 文件。")
            print("说明：NTLog 目录可能仅含蜂窝数传 tcpdump cap（非 wlan cap），WiFi 数传量化不适用。")
            if start_time and end_time:
                print(f"Start_time: {start_time}, End_time: {end_time}, WiFi_transfer_power: N/A (no wlan cap)")
            else:
                print("WiFi_transfer_power: N/A (no wlan cap)")
            sys.exit(0)
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
                selected_file = cap_file_paths[0]
        else:
            selected_file = cap_file_paths[0]
    else:
        sys.exit(1)
    
    # 设置全局文件路径
    set_global_file_path(selected_file)
    
    # 生成 linli.txt 文件路径
    output_file = os.path.join(os.path.dirname(selected_file), "linli.txt")
    
    first_time, _ = get_time_range_from_linli(output_file) if os.path.exists(output_file) else (None, None)
    if first_time is None:
        success = parse_cap_file(selected_file)
        if not success:
            # tshark 不可用或 cap 文件为空，优雅退出
            time_desc = f"{start_time}~{end_time}" if start_time or end_time else "all"
            print(f"CAP_PARSE_FAILED: cap 文件解析失败（可能 tshark 不可用或 cap 为空）。")
            print(f"Start_time: {time_desc}, WiFi_transfer_power: N/A (cap parse failed)")
            sys.exit(0)
    
    # 计算功耗
    try:
        if start_time or end_time:
            # 有时间参数，使用 calculate_power
            total_power, rrc_time = calculate_power(output_file, start_time, end_time)
            if total_power == 0 and rrc_time == 0:
                print(f"Start_time: {start_time}, End_time: {end_time}, WiFi_transfer_power: N/A (no data in window)")
            else:
                print(f"Start_time: {start_time}, End_time: {end_time}, WiFi_transfer_power: {total_power:.2f}mA")
        else:
            # 无时间参数，使用 calculate_default_power
            total_power, rrc_time, first_time, last_time = calculate_default_power(output_file)
            # 使用实际的时间范围，如果获取失败则显示 all
            start_display = first_time if first_time else "all"
            end_display = last_time if last_time else "all"
            if total_power == 0:
                print(f"Start_time: {start_display}, End_time: {end_display}, WiFi_transfer_power: N/A (no data)")
            else:
                print(f"Start_time: {start_display}, End_time: {end_display}, WiFi_transfer_power: {total_power:.2f}mA")
    except Exception as e:
        # 输出结构化错误信息供 Agent 解读，不静默吞掉
        time_desc = f"{start_time}~{end_time}" if start_time or end_time else "all"
        print(f"WIFI_POWER_CALC_ERROR: 计算 WiFi 数传功耗异常（时间窗 {time_desc}）：{e}")
        print("WiFi_transfer_power: N/A (calc error)")
