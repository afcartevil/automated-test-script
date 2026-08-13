import os
import re
import sys
import argparse

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from radio_log_paths import discover_radio_log_files, resolve_radio_log  # noqa: E402


def parse_radio_log_timestamp(ts: str, ref_year: int):
    """
    解析 radio_log 中的时间戳（格式 MM-DD HH:MM:SS），结合参考年份得到绝对时间。

    Args:
        ts: 如 "12-02 17:59:53"
        ref_year: 参考年份，通常取分析窗口中间时刻的年份
    """
    from datetime import datetime

    return datetime.strptime(f"{int(ref_year)}-{ts.strip()}", "%Y-%m-%d %H:%M:%S")


def _pick_nearest_records(items: list, mid, time_key: str = "time") -> list:
    """从全量记录中选取与 mid 时间最近的一条（用于 fallback=nearest）。"""
    if not items:
        return []

    def _dist(item):
        raw = item.get(time_key) if isinstance(item, dict) else str(item)[:14]
        try:
            dt = parse_radio_log_timestamp(raw, mid.year)
        except (ValueError, TypeError):
            return 999999999.0
        return abs((dt - mid).total_seconds())

    return [min(items, key=_dist)]


def _setup_utf8_stdio() -> None:
    """统一脚本标准输入输出编码为 UTF-8，减少 Windows 终端乱码。"""
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def analyze_network(start_time, end_time, log_path, fallback: str = "none"):
    """
    网络分析接口，提供给其他模块使用

    Args:
        start_time (str): 开始时间，格式为"YYYY-MM-DD HH:MM:SS"
        end_time (str): 结束时间，格式为"YYYY-MM-DD HH:MM:SS"
        log_path (str): 日志文件路径或文件夹路径
        fallback (str): 窗口无数据时 none|nearest|full

    Returns:
        dict: 包含网络分析结果的字典
    """
    if os.path.isdir(log_path):
        scan_dir, radio_log_files = discover_radio_log_files(log_path)
        if not radio_log_files:
            probe = resolve_radio_log(log_path)
            return {
                "error": "没有找到以 radio_log 开头的文件",
                "ready": False,
                "scan_dir": probe.get("scan_dir", log_path),
                "radio_log_count": 0,
            }

        unique_files = remove_duplicate_files(radio_log_files)
        sorted_files = sort_files_by_time(unique_files)

        if len(sorted_files) > 1:
            merged_file = os.path.join(scan_dir, "merged_radio_log.txt")
            merge_files(sorted_files, merged_file)
            log_file_path = merged_file
        else:
            log_file_path = sorted_files[0]
    else:
        log_file_path = log_path

    if not os.path.exists(log_file_path):
        return {"error": f"文件 '{log_file_path}' 不存在"}

    result = process_radio_log_for_api(log_file_path, start_time, end_time)
    if "error" in result:
        return result

    sparse = not result.get("service_state_data") and not result.get("ps_cellular_data")
    if not sparse:
        result["data_quality"] = "window"
        return result

    fb = (fallback or "none").lower()
    if fb == "none":
        result["data_quality"] = "sparse"
        return result

    if fb == "full":
        full = process_radio_log_for_api(log_file_path, None, None)
        if "error" not in full:
            full["data_quality"] = "full_fallback"
            full["fallback_reason"] = "window_empty"
        return full

    if fb == "nearest" and start_time and end_time:
        from datetime import datetime as _dt

        try:
            mid = (
                _dt.strptime(start_time, "%Y-%m-%d %H:%M:%S")
                + (
                    _dt.strptime(end_time, "%Y-%m-%d %H:%M:%S")
                    - _dt.strptime(start_time, "%Y-%m-%d %H:%M:%S")
                )
                / 2
            )
        except ValueError:
            result["data_quality"] = "sparse"
            return result
        full = process_radio_log_for_api(log_file_path, None, None)
        if "error" in full:
            return full

        full["service_state_data"] = _pick_nearest_records(
            full.get("service_state_data") or [], mid
        )
        full["ps_cellular_data"] = _pick_nearest_records(
            full.get("ps_cellular_data") or [], mid
        )
        full["data_quality"] = "nearest_fallback"
        full["fallback_reason"] = "window_empty"
        return full

    result["data_quality"] = "sparse"
    return result


def process_radio_log_for_api(log_file_path, start_time, end_time):
    """
    处理radio_log文件并返回分析结果

    Args:
        log_file_path (str): 日志文件路径
        start_time (str): 开始时间
        end_time (str): 结束时间

    Returns:
        dict: 包含网络分析结果的字典
    """
    from datetime import datetime
    
    card_data = {
        "card1": {"ps_data": [], "cs_data": [], "mcc": None, "mnc": None},
        "card2": {"ps_data": [], "cs_data": [], "mcc": None, "mnc": None}
    }

    service_state_data = []
    ps_cellular_data = []

    # 解析用户输入的时间范围
    start_dt = None
    end_dt = None
    base_year = None

    if start_time:
        try:
            start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            base_year = start_dt.year
        except Exception as e:
            start_dt = None

    if end_time:
        try:
            end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
            if base_year is None:
                base_year = end_dt.year
        except Exception as e:
            end_dt = None

    def parse_log_time(time_str):
        """解析日志中的时间格式 'MM-DD HH:MM:SS' 并返回完整的 datetime 对象"""
        try:
            parts = time_str.split('.')
            main_part = parts[0]
            dt = datetime.strptime(main_part, "%m-%d %H:%M:%S")
            if base_year:
                dt = dt.replace(year=base_year)
            else:
                dt = dt.replace(year=2026)
            return dt
        except Exception as e:
            return None

    def is_in_time_range(time_str):
        """检查时间是否在指定范围内"""
        nonlocal base_year
        
        if not start_dt and not end_dt:
            return True
        
        line_dt = parse_log_time(time_str)
        if line_dt is None:
            return True
        
        if base_year and line_dt.year != base_year:
            if start_dt and line_dt < start_dt and line_dt.month > 6:
                line_dt = line_dt.replace(year=base_year - 1)
            elif end_dt and line_dt > end_dt and line_dt.month < 6:
                line_dt = line_dt.replace(year=base_year + 1)
        
        if start_dt and line_dt < start_dt:
            return False
        if end_dt and line_dt > end_dt:
            return False
        return True

    try:
        with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as file:
            for line_num, line in enumerate(file, 1):
                if "< DATA_REGISTRATION_STATE" in line or "< VOICE_REGISTRATION" in line:
                    time_str = line[:14].strip() if len(line) >= 14 else line.strip()
                    
                    if not is_in_time_range(time_str):
                        continue
                        
                    card_key = None
                    if "[PHONE0]" in line:
                        card_key = "card1"
                        if not card_data[card_key]["mcc"] and not card_data[card_key]["mnc"]:
                            mcc, mnc = extract_mcc_mnc(line)
                            card_data[card_key]["mcc"] = mcc
                            card_data[card_key]["mnc"] = mnc
                    elif "[PHONE1]" in line:
                        card_key = "card2"
                        if not card_data[card_key]["mcc"] and not card_data[card_key]["mnc"]:
                            mcc, mnc = extract_mcc_mnc(line)
                            card_data[card_key]["mcc"] = mcc
                            card_data[card_key]["mnc"] = mnc

                    if card_key:
                        if "< DATA_REGISTRATION_STATE" in line:
                            card_data[card_key]["ps_data"].append((line_num, line.strip()))
                        elif "< VOICE_REGISTRATION" in line:
                            card_data[card_key]["cs_data"].append((line_num, line.strip()))
                elif "Poll ServiceState done: newSS" in line:
                    time_str = line[:14].strip() if len(line) >= 14 else line.strip()
                    
                    if is_in_time_range(time_str):
                        service_state_data.append((line_num, line.strip()))
                elif "handlePollStateResultMessage: PS cellular" in line:
                    time_str = line[:14].strip() if len(line) >= 14 else line.strip()
                    
                    if is_in_time_range(time_str):
                        ps_cellular_data.append((line_num, line.strip()))

    except Exception as e:
        return {"error": f"读取文件时出错：{str(e)}"}

    result = {
        "card1": {
            "mcc": card_data["card1"]["mcc"],
            "mnc": card_data["card1"]["mnc"],
            "ps_data": [],
            "cs_data": []
        },
        "card2": {
            "mcc": card_data["card2"]["mcc"],
            "mnc": card_data["card2"]["mnc"],
            "ps_data": [],
            "cs_data": []
        },
        "service_state_data": [],
        "ps_cellular_data": []
    }

    for card_key in ["card1", "card2"]:
        if card_data[card_key]["ps_data"]:
            ps_groups = group_by_status(card_data[card_key]["ps_data"])
            for group in ps_groups:
                result[card_key]["ps_data"].append({
                    "start_time": group["start_time"],
                    "end_time": group["end_time"],
                    "reg_state": group["reg_state"],
                    "rat": group["rat"],
                    "cell": group["cell"],
                    "bands": group["bands"]
                })

        if card_data[card_key]["cs_data"]:
            cs_groups = group_by_status(card_data[card_key]["cs_data"])
            for group in cs_groups:
                result[card_key]["cs_data"].append({
                    "start_time": group["start_time"],
                    "end_time": group["end_time"],
                    "reg_state": group["reg_state"],
                    "rat": group["rat"],
                    "cell": group["cell"],
                    "bands": group["bands"]
                })

    if service_state_data:
        for line_num, line in service_state_data:
            time_str = line[:14].strip() if len(line) >= 14 else line.strip()

            cs_state = extract_service_state_info(line, "mVoiceRegState=")
            ps_state = extract_service_state_info(line, "mDataRegState=")
            duplex_mode = extract_service_state_info(line, "duplexMode()=")

            bandwidth = ""
            start = line.find("mCellBandwidths=")
            if start != -1:
                start += len("mCellBandwidths=")
                end = line.find(", m", start)
                if end != -1:
                    bandwidth = line[start:end].strip()
                else:
                    bandwidth = line[start:].strip()

            network_selection = extract_service_state_info(line, "isManualNetworkSelection=")
            network_type = extract_service_state_info(line, "getRilDataRadioTechnology=")
            is_ca = extract_service_state_info(line, "isUsingCarrierAggregation=")

            result["service_state_data"].append({
                "time": time_str,
                "cs_state": cs_state,
                "ps_state": ps_state,
                "duplex_mode": duplex_mode,
                "bandwidth": bandwidth,
                "network_selection": network_selection,
                "network_type": network_type,
                "is_ca": is_ca
            })

    if ps_cellular_data:
        for line_num, line in ps_cellular_data:
            time_str = line[:14].strip() if len(line) >= 14 else line.strip()

            ps_state = extract_ps_cellular_info(line, "registrationState=")
            roaming_type = extract_ps_cellular_info(line, "roamingType=")
            network_tech = extract_ps_cellular_info(line, "accessNetworkTechnology=")
            reject_cause = extract_ps_cellular_info(line, "rejectCause=")
            pci = extract_ps_cellular_info(line, "mPci=")
            bands = extract_ps_cellular_info(line, "mBands=")

            result["ps_cellular_data"].append({
                "time": time_str,
                "ps_state": ps_state,
                "roaming_type": roaming_type,
                "network_tech": network_tech,
                "reject_cause": reject_cause,
                "pci": pci,
                "bands": bands
            })

    return result

def extract_mcc_mnc(line_content):
    mcc_pattern = r'mcc[^\d]*([\d]+)'
    mnc_pattern = r'mnc[^\d]*([\d]+)'
    mcc_match = re.search(mcc_pattern, line_content, re.IGNORECASE)
    mnc_match = re.search(mnc_pattern, line_content, re.IGNORECASE)
    return (mcc_match.group(1) if mcc_match else None,
            mnc_match.group(1) if mnc_match else None)

def extract_info_from_line(line_content):
    time_str = line_content[:14].strip()

    reg_state = ""
    if "regState" in line_content and "rat" in line_content:
        start_idx = line_content.find("regState")
        end_idx = line_content.find("rat", start_idx)
        if start_idx != -1 and end_idx != -1:
            match = re.search(r'regState[^a-zA-Z0-9]*(\w+)', line_content[start_idx:end_idx])
            if match:
                reg_state = match.group(1)

    rat = ""
    if "rat" in line_content and "reasonForDenial" in line_content:
        start_idx = line_content.find("rat")
        end_idx = line_content.find("reasonForDenial", start_idx)
        if start_idx != -1 and end_idx != -1:
            match = re.search(r'rat[^a-zA-Z0-9]*(\w+)', line_content[start_idx:end_idx])
            if match:
                rat = match.group(1)

    cell = ""
    if "pci" in line_content and "tac" in line_content:
        start_idx = line_content.find("pci")
        end_idx = line_content.find("tac", start_idx)
        if start_idx != -1 and end_idx != -1:
            match = re.search(r'pci[^0-9]*(\d+)', line_content[start_idx:end_idx])
            if match:
                cell = match.group(1)

    bands = ""
    if "bands" in line_content and "registered" in line_content:
        start_idx = line_content.find("bands")
        end_idx = line_content.find("registered", start_idx)
        if start_idx != -1 and end_idx != -1:
            match = re.search(r'bands[^a-zA-Z0-9]*(\w+)', line_content[start_idx:end_idx])
            if match:
                bands = match.group(1)

    return time_str, reg_state, rat, cell, bands

def group_by_status(data):
    if not data:
        return []

    groups = []
    current_group = None

    for line_num, line_content in data:
        time_str, reg_state, rat, cell, bands = extract_info_from_line(line_content)

        status_key = (reg_state, rat, cell, bands)

        if current_group is None:
            current_group = {
                'start_time': time_str,
                'end_time': time_str,
                'reg_state': reg_state,
                'rat': rat,
                'cell': cell,
                'bands': bands
            }
        else:
            current_status = (current_group['reg_state'], current_group['rat'],
                           current_group['cell'], current_group['bands'])
            if status_key != current_status:
                groups.append(current_group)
                current_group = {
                    'start_time': time_str,
                    'end_time': time_str,
                    'reg_state': reg_state,
                    'rat': rat,
                    'cell': cell,
                    'bands': bands
                }
            else:
                current_group['end_time'] = time_str

    if current_group:
        groups.append(current_group)

    return groups

def get_radio_log_files(folder_path, recursive=False):
    files = []

    def scan_directory(directory):
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            if os.path.isdir(file_path) and recursive:
                scan_directory(file_path)
            elif os.path.isfile(file_path):
                if filename.startswith("radio_log_"):
                    files.append(file_path)

    scan_directory(folder_path)
    return files

def remove_duplicate_files(files):
    file_groups = {}
    no_timestamp_files = []
    duplicate_count = 0

    for file_path in files:
        filename = os.path.basename(file_path)
        match = re.search(r'(?:__)?(\d{4}_\d{4}_\d{6})', filename)
        if match:
            timestamp = match.group(1)
            if timestamp not in file_groups:
                file_groups[timestamp] = []
            file_groups[timestamp].append(file_path)
        else:
            no_timestamp_files.append(file_path)

    unique_files = []
    for timestamp, group_files in file_groups.items():
        if len(group_files) > 1:
            duplicate_count += len(group_files) - 1
        unique_files.append(group_files[0])

    unique_files.extend(no_timestamp_files)

    return unique_files

def get_filename_time(file_path):
    filename = os.path.basename(file_path)
    match = re.search(r'(?:__)?(\d{4})_(\d{4})_(\d{6})$', filename)
    if match:
        year = match.group(1)
        month_day = match.group(2)
        hour_min_sec = match.group(3)
        time_str = f"{year}-{month_day[:2]}-{month_day[2:]} {hour_min_sec[:2]}:{hour_min_sec[2:4]}:{hour_min_sec[4:]}"
        return time_str
    return ""

def sort_files_by_time(files):
    return sorted(files, key=get_filename_time)

def merge_files(files, output_path):
    with open(output_path, 'w', encoding='utf-8', errors='ignore') as outfile:
        for file_path in files:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as infile:
                outfile.write(infile.read())
                outfile.write('\n')

def extract_service_state_info(line, key):
    start = line.find(key)
    if start != -1:
        start += len(key)
        end = line.find(',', start)
        if end != -1:
            return line[start:end].strip()
        else:
            return line[start:].strip()
    return ""

def extract_ps_cellular_info(line, key):
    start = line.find(key)
    if start != -1:
        start += len(key)
        end = line.find(' ', start)
        if end != -1:
            return line[start:end].strip()
        else:
            return line[start:].strip()
    return ""

def process_radio_log(log_file_path):
    if not os.path.exists(log_file_path):
        print(f"错误：文件 '{log_file_path}' 不存在。")
        return

    card_data = {
        "card1": {"ps_data": [], "cs_data": [], "mcc": None, "mnc": None},
        "card2": {"ps_data": [], "cs_data": [], "mcc": None, "mnc": None}
    }

    service_state_data = []
    ps_cellular_data = []

    try:
        with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as file:
            for line_num, line in enumerate(file, 1):
                if "< DATA_REGISTRATION_STATE" in line or "< VOICE_REGISTRATION" in line:
                    card_key = None
                    if "[PHONE0]" in line:
                        card_key = "card1"
                        if not card_data[card_key]["mcc"] and not card_data[card_key]["mnc"]:
                            mcc, mnc = extract_mcc_mnc(line)
                            card_data[card_key]["mcc"] = mcc
                            card_data[card_key]["mnc"] = mnc
                    elif "[PHONE1]" in line:
                        card_key = "card2"
                        if not card_data[card_key]["mcc"] and not card_data[card_key]["mnc"]:
                            mcc, mnc = extract_mcc_mnc(line)
                            card_data[card_key]["mcc"] = mcc
                            card_data[card_key]["mnc"] = mnc

                    if card_key:
                        if "< DATA_REGISTRATION_STATE" in line:
                            card_data[card_key]["ps_data"].append((line_num, line.strip()))
                        elif "< VOICE_REGISTRATION" in line:
                            card_data[card_key]["cs_data"].append((line_num, line.strip()))
                elif "Poll ServiceState done: newSS" in line:
                    service_state_data.append((line_num, line.strip()))
                elif "handlePollStateResultMessage: PS cellular" in line:
                    ps_cellular_data.append((line_num, line.strip()))

    except Exception as e:
        print(f"读取文件时出错：{str(e)}")
        return

    print("\n===== 提取结果 =====")
    print(f"卡1 ([PHONE0]) - MCC: {card_data['card1']['mcc']}, MNC: {card_data['card1']['mnc']}")
    print(f"卡2 ([PHONE1]) - MCC: {card_data['card2']['mcc']}, MNC: {card_data['card2']['mnc']}")
    print(f"\n卡1 ([PHONE0]) PS域提取行数: {len(card_data['card1']['ps_data'])}")
    print(f"卡1 ([PHONE0]) CS域提取行数: {len(card_data['card1']['cs_data'])}")
    print(f"卡2 ([PHONE1]) PS域提取行数: {len(card_data['card2']['ps_data'])}")
    print(f"卡2 ([PHONE1]) CS域提取行数: {len(card_data['card2']['cs_data'])}")
    print(f"ServiceState提取行数: {len(service_state_data)}")
    print(f"PS cellular提取行数: {len(ps_cellular_data)}")

    for card_name in ["卡1 ([PHONE0])", "卡2 ([PHONE1])"]:
        card_key = "card1" if "卡1" in card_name else "card2"

        if card_data[card_key]["ps_data"]:
            print(f"\n===== {card_name} PS域详细信息（按状态切换分组）=====")
            print(f"{'开始时间':<15} {'结束时间':<15} {'注册状态':<15} {'制式':<15} {'小区':<15} {'频段':<15}")
            print("-" * 95)

            ps_groups = group_by_status(card_data[card_key]["ps_data"])
            for group in ps_groups:
                print(f"{group['start_time']:<15} {group['end_time']:<15} {group['reg_state']:<15} {group['rat']:<15} {group['cell']:<15} {group['bands']:<15}")

        if card_data[card_key]["cs_data"]:
            print(f"\n===== {card_name} CS域详细信息（按状态切换分组）=====")
            print(f"{'开始时间':<15} {'结束时间':<15} {'注册状态':<15} {'制式':<15} {'小区':<15} {'频段':<15}")
            print("-" * 95)

            cs_groups = group_by_status(card_data[card_key]["cs_data"])
            for group in cs_groups:
                print(f"{group['start_time']:<15} {group['end_time']:<15} {group['reg_state']:<15} {group['rat']:<15} {group['cell']:<15} {group['bands']:<15}")

    if service_state_data:
        print("\n===== ServiceState详细信息 =====")
        print(f"{'时间':<15} {'CS状态':<20} {'PS状态':<20} {'双工模式':<15} {'带宽':<20} {'网络选择':<15} {'网络制式':<20} {'CA':<15}")
        print("-" * 150)

        for line_num, line in service_state_data:
            time_str = line[:14].strip() if len(line) >= 14 else line.strip()

            cs_state = extract_service_state_info(line, "mVoiceRegState=")
            ps_state = extract_service_state_info(line, "mDataRegState=")
            duplex_mode = extract_service_state_info(line, "duplexMode()=")

            bandwidth = ""
            start = line.find("mCellBandwidths=")
            if start != -1:
                start += len("mCellBandwidths=")
                end = line.find(", m", start)
                if end != -1:
                    bandwidth = line[start:end].strip()
                else:
                    bandwidth = line[start:].strip()

            network_selection = extract_service_state_info(line, "isManualNetworkSelection=")
            network_type = extract_service_state_info(line, "getRilDataRadioTechnology=")
            is_ca = extract_service_state_info(line, "isUsingCarrierAggregation=")

            print(f"{time_str:<15} {cs_state:<20} {ps_state:<20} {duplex_mode:<15} {bandwidth:<20} {network_selection:<15} {network_type:<20} {is_ca:<15}")

    if ps_cellular_data:
        print("\n===== PS cellular详细信息 =====")
        print(f"{'时间':<15} {'PS状态':<20} {'漫游状态':<15} {'网络制式':<15} {'rejectCause':<15} {'小区':<15} {'band':<15}")
        print("-" * 115)

        for line_num, line in ps_cellular_data:
            time_str = line[:14].strip() if len(line) >= 14 else line.strip()

            ps_state = extract_ps_cellular_info(line, "registrationState=")
            roaming_type = extract_ps_cellular_info(line, "roamingType=")
            network_tech = extract_ps_cellular_info(line, "accessNetworkTechnology=")
            reject_cause = extract_ps_cellular_info(line, "rejectCause=")
            pci = extract_ps_cellular_info(line, "mPci=")
            bands = extract_ps_cellular_info(line, "mBands=")

            print(f"{time_str:<15} {ps_state:<20} {roaming_type:<15} {network_tech:<15} {reject_cause:<15} {pci:<15} {bands:<15}")

if __name__ == "__main__":
    _setup_utf8_stdio()
    import json

    parser = argparse.ArgumentParser(description="计算蜂窝网络信息")
    parser.add_argument(
        '-d',
        '--directory',
        required=True,
        help='工作区根/converted/、converted/APLog/ 或含 radio_log_* 的目录',
    )
    parser.add_argument(
        '--probe',
        action='store_true',
        help='仅探测 radio_log 是否就绪（输出 JSON，不分析）',
    )
    parser.add_argument('-t', '--time', nargs='*', metavar=('START_TIME', 'END_TIME'), help='开始时间和结束时间（格式：YYYY-MM-DD HH:MM:SS），可选。若只指定一个时间，则视为开始时间；若第一个时间为空，则视为只指定结束时间')
    parser.add_argument(
        '--fallback',
        choices=('none', 'nearest', 'full'),
        default='none',
        help='时间窗无 ServiceState/PS cellular 记录时的回退策略',
    )
    parser.add_argument('--format', choices=('text', 'json'), default='text', help='输出格式')

    args = parser.parse_args()

    input_path = args.directory
    start_time = None
    end_time = None

    if args.time:
        if len(args.time) == 1:
            start_time = args.time[0]
        elif len(args.time) >= 2:
            start_time = args.time[0]
            end_time = args.time[1]
            if not start_time:
                start_time = None

    if not os.path.exists(input_path):
        print(f"错误：路径 '{input_path}' 不存在。")
        sys.exit(1)

    if args.probe:
        print(json.dumps(resolve_radio_log(input_path), ensure_ascii=False, indent=2))
        sys.exit(0)

    result = analyze_network(start_time, end_time, input_path, fallback=args.fallback)
    if "error" in result:
        if args.format == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0 if not result.get("ready", True) else 1)
        print(f"错误：{result['error']}")
        sys.exit(1)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)

    print("\n=== 网络信息分析结果 ===")
    if start_time or end_time:
        print(f"开始时间: {start_time if start_time else '全部'}, 结束时间: {end_time if end_time else '全部'}")

    print(f"\n卡1 ([PHONE0]) - MCC: {result['card1']['mcc']}, MNC: {result['card1']['mnc']}")
    print(f"卡2 ([PHONE1]) - MCC: {result['card2']['mcc']}, MNC: {result['card2']['mnc']}")

    print(f"\n卡1 PS域状态变化次数: {len(result['card1']['ps_data'])}")
    print(f"卡1 CS域状态变化次数: {len(result['card1']['cs_data'])}")
    print(f"卡2 PS域状态变化次数: {len(result['card2']['ps_data'])}")
    print(f"卡2 CS域状态变化次数: {len(result['card2']['cs_data'])}")
    print(f"ServiceState记录数: {len(result['service_state_data'])}")
    print(f"PS cellular记录数: {len(result['ps_cellular_data'])}")

    if result['service_state_data']:
        print("\n===== ServiceState详细信息 =====")
        print(f"{'时间':<15} {'CS状态':<20} {'PS状态':<20} {'双工模式':<15} {'带宽':<20} {'网络选择':<15} {'网络制式':<20} {'CA':<15}")
        print("-" * 150)
        
        for item in result['service_state_data']:
            print(f"{item['time']:<15} {item['cs_state']:<20} {item['ps_state']:<20} {item['duplex_mode']:<15} {item['bandwidth']:<20} {item['network_selection']:<15} {item['network_type']:<20} {item['is_ca']:<15}")

    if result['ps_cellular_data']:
        print("\n===== PS cellular详细信息 =====")
        print(f"{'时间':<15} {'PS状态':<20} {'漫游状态':<15} {'网络制式':<15} {'rejectCause':<15} {'小区':<15} {'band':<15}")
        print("-" * 115)
        
        for item in result['ps_cellular_data']:
            print(f"{item['time']:<15} {item['ps_state']:<20} {item['roaming_type']:<15} {item['network_tech']:<15} {item['reject_cause']:<15} {item['pci']:<15} {item['bands']:<15}")