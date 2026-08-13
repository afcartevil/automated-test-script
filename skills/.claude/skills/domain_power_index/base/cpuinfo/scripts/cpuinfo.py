import os
import re
from datetime import datetime
import sys
import argparse

_BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "base", "lib")
)
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from repo_paths import (
    find_repo_root,
    jira_workspace_dir,
    resolve_workspace_dir,
    temp_root,
    workspace_analysis,
)

def _setup_utf8_stdio() -> None:
    """统一脚本标准输入输出编码为 UTF-8，减少 Windows 终端乱码。"""
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

def select_folder():
    """选择文件夹（CLI模式）"""
    folder_path = input("请输入包含日志文件的文件夹路径: ").strip()
    while not folder_path or not os.path.isdir(folder_path):
        if not folder_path:
            print("错误：路径不能为空")
        else:
            print(f"错误：'{folder_path}' 不是有效的文件夹路径")
        folder_path = input("请重新输入文件夹路径: ").strip()
    return folder_path

def get_linli_666_files(folder_path, recursive=True):
    """获取以linli_666结尾的文件
    
    Args:
        folder_path: 文件夹路径
        recursive: 是否递归搜索子文件夹
        
    Returns:
        list: 符合条件的文件路径列表
    """
    linli_files = []
    
    if recursive:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if "linli_666" in file:
                    linli_files.append(os.path.join(root, file))
    else:
        for file in os.listdir(folder_path):
            file_path = os.path.join(folder_path, file)
            if os.path.isfile(file_path) and "linli_666" in file:
                linli_files.append(file_path)
    
    return linli_files

def sort_files_by_time(file_paths):
    """按文件修改时间排序
    
    Args:
        file_paths: 文件路径列表
        
    Returns:
        list: 按时间排序后的文件路径列表
    """
    # 获取文件的修改时间并排序
    file_with_time = []
    for file_path in file_paths:
        try:
            mtime = os.path.getmtime(file_path)
            file_with_time.append((mtime, file_path))
        except Exception as e:
            print(f"获取文件时间失败: {file_path}, 错误: {str(e)}")
    
    # 按时间排序
    file_with_time.sort(key=lambda x: x[0])
    
    # 返回排序后的文件路径
    return [file_path for _, file_path in file_with_time]

def search_keyword_in_files(files, keyword, start_time=None, end_time=None):
    """在文件中搜索关键字
    
    Args:
        files: 文件路径列表
        keyword: 要搜索的关键字
        start_time: 开始时间（格式：YYYY-MM-DD HH:MM:SS），可选
        end_time: 结束时间（格式：YYYY-MM-DD HH:MM:SS），可选
        
    Returns:
        dict: 包含搜索结果的字典
    """
    total_matches = 0
    matches = []  # 存储所有匹配项及其时间戳
    cpus_usage_matches = []  # 存储Cpus Usage信息
    thread_load_matches = []  # 存储线程负载信息（包含"ns"关键字的行）
    file_info = []  # 存储文件信息
    
    # 转换时间格式
    start_dt = None
    end_dt = None
    if start_time:
        try:
            start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        except:
            pass
    if end_time:
        try:
            end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        except:
            pass
    
    for file_path in files:
        file_matches = 0
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                for line in file:
                    if keyword in line:
                        # 取消打印前三个字符
                        processed_line = line[3:].strip()
                        # 提取第一组"["和"]"之间的时间
                        time_match = re.search(r'\[(.*?)\]', processed_line)
                        if time_match:
                            time_str = time_match.group(1)
                            time_part = time_str[:19]  # 提取前19位作为时间部分
                            
                            # 检查时间范围
                            if start_dt or end_dt:
                                try:
                                    current_dt = datetime.strptime(time_part, "%Y-%m-%d %H:%M:%S")
                                    if start_dt and current_dt < start_dt:
                                        continue  # 在开始时间之前，跳过
                                    if end_dt and current_dt > end_dt:
                                        continue  # 在结束时间之后，跳过
                                except:
                                    pass  # 时间解析失败，跳过时间范围检查
                            
                            file_matches += 1
                            total_matches += 1
                            
                            # 移除第一组"["和"]"
                            remaining_content = processed_line[time_match.end():].strip()
                            if remaining_content:
                                formatted_line = f"{time_str} {remaining_content}"
                            else:
                                formatted_line = time_str
                            # 存储匹配项及其时间戳
                            matches.append((time_str, formatted_line))
                            
                            # 检查是否包含"Cpus Usage"关键字
                            if "Cpus Usage" in remaining_content:
                                # 提取前19位作为时间
                                time_part = time_str[:19]
                                # 提取Cpus Usage后的内容
                                cpus_usage_part = remaining_content.split("Cpus Usage", 1)[1].strip() if "Cpus Usage" in remaining_content else ""
                                # 存储Cpus Usage信息
                                cpus_usage_matches.append((time_str, time_part, cpus_usage_part))
                            
                            # 检查是否包含"ns"关键字（线程负载信息）
                            if "ns" in remaining_content:
                                # 提取前19位作为时间
                                time_part = time_str[:19]
                                
                                # 提取负载：[K]和%之间的有效数字（包括%）
                                load = ""
                                load_match = re.search(r'\[K\](.*?)%', remaining_content)
                                if load_match:
                                    load = load_match.group(1).strip() + "%"
                                
                                # 提取PID：%之后到第56位字符之间的有效数字
                                pid = ""
                                percent_pos = remaining_content.find("%")
                                if percent_pos != -1:
                                    # 获取%之后到第56位的子串（包含空格）
                                    pid_sub = remaining_content[percent_pos + 1:56]
                                    # 提取数字
                                    pid = ''.join(c for c in pid_sub if c.isdigit())
                                
                                # 提取包名：第46位到第73位之间的有效文本（包含空格）
                                package_name = ""
                                if len(remaining_content) >= 46:
                                    package_sub = remaining_content[46:73]
                                    # 提取有效文本（字母、数字、点、下划线、空格）
                                    package_name = re.sub(r'[^a-zA-Z0-9._ ]', '', package_sub).strip()
                                
                                # 存储线程负载信息
                                thread_load_matches.append((time_str, time_part, load, pid, package_name))
                        # 移除else部分，不存储没有时间戳的行
        except Exception as e:
            continue
        
        file_info.append((os.path.basename(file_path), file_matches))
    
    # 按时间戳排序
    def get_time_key(item):
        time_str = item[0]
        try:
            # 尝试解析时间戳
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
        except:
            # 如果解析失败，返回一个较早的时间
            return datetime.min
    
    matches.sort(key=get_time_key)
    
    # 处理Cpus Usage信息
    if cpus_usage_matches:
        # 按时间排序
        cpus_usage_matches.sort(key=get_time_key)
    
    # 处理线程负载信息
    if thread_load_matches:
        # 按时间排序
        thread_load_matches.sort(key=get_time_key)
    
    # 按包名分组统计线程负载信息（筛选掉负载为0的项）
    thread_load_by_package = {}
    for time_str, time_part, load, pid, package_name in thread_load_matches:
        if package_name:
            # 筛选掉负载为0的项
            if load and load != "0%" and load != "0":
                if package_name not in thread_load_by_package:
                    thread_load_by_package[package_name] = []
                thread_load_by_package[package_name].append((time_str, time_part, load, pid))
    
    # 计算每个包的统计信息：打印次数和平均负载
    package_stats = {}
    for package_name, load_info in thread_load_by_package.items():
        count = len(load_info)
        total_load = 0
        valid_load_count = 0
        for _, _, load, _ in load_info:
            try:
                # 提取数字部分（去掉%）
                load_value = float(load.replace('%', ''))
                total_load += load_value
                valid_load_count += 1
            except:
                pass
        avg_load = total_load / valid_load_count if valid_load_count > 0 else 0
        package_stats[package_name] = {
            'count': count,
            'avg_load': avg_load
        }
    
    # 对包名进行排序：先按数量排序，数量相同则按平均负载排序
    def get_package_sort_key(item):
        package_name, load_info = item
        count = len(load_info)
        # 计算平均负载
        total_load = 0
        valid_load_count = 0
        for _, _, load, _ in load_info:
            try:
                # 提取数字部分（去掉%）
                load_value = float(load.replace('%', ''))
                total_load += load_value
                valid_load_count += 1
            except:
                pass
        avg_load = total_load / valid_load_count if valid_load_count > 0 else 0
        # 返回排序键：数量（降序），平均负载（降序）
        return (-count, -avg_load)
    
    # 对字典进行排序
    sorted_thread_load_by_package = dict(sorted(thread_load_by_package.items(), key=get_package_sort_key))
    
    # 对统计信息也进行排序
    sorted_package_stats = dict(sorted(package_stats.items(), key=lambda x: (-x[1]['count'], -x[1]['avg_load'])))
    
    # 构建结果字典
    result = {
        'total_matches': total_matches,
        'matches': matches,  # 列表格式：[(time_str, formatted_line), ...]
        'cpus_usage_matches': cpus_usage_matches,  # 列表格式：[(time_str, time_part, cpus_usage_part), ...]
        'thread_load_matches': thread_load_matches,  # 列表格式：[(time_str, time_part, load, pid, package_name), ...]
        'thread_load_by_package': sorted_thread_load_by_package,  # 字典格式：{package_name: [(time_str, time_part, load, pid), ...], ...}
        'package_stats': package_stats,  # 字典格式：{package_name: {'count': int, 'avg_load': float}, ...}
        'sorted_package_stats': sorted_package_stats,  # 排序后的包统计信息
        'file_info': file_info,  # 列表格式：[(filename, match_count), ...]
        'keyword': keyword
    }
    
    return result

def detect_anomaly_apps(thread_load_by_package, threshold=10.0, time_window_minutes=10):
    """检测异常应用

    判断标准（自适应阈值）：
    - 常规：在 time_window_minutes 时间窗口内，平均负载超过 threshold 的应用
    - 突发高负载：平均负载 > threshold×5 且持续 >3 分钟，或 > threshold×10 且持续 >1 分钟
      （捕获短时间剧烈 CPU 消耗，如 8 分钟窗口内 114% 负载）

    Args:
        thread_load_by_package: 按包名分组的线程负载信息
        threshold: 负载阈值（百分比），默认10%
        time_window_minutes: 时间窗口（分钟），默认10分钟

    Returns:
        list: 异常应用列表，每个元素包含包名、PID、持续时间、时间段、平均负载、最高负载、最低负载
    """
    anomaly_apps = []
    
    for package_name, load_info in thread_load_by_package.items():
        if not load_info:
            continue
        
        # 按时间排序
        sorted_load_info = sorted(load_info, key=lambda x: x[0])
        n = len(sorted_load_info)
        
        # 使用滑动窗口检测10分钟内的平均负载
        i = 0
        while i < n:
            window_loads = []
            window_pids = set()
            window_start_time = None
            window_end_time = None
            
            # 从当前点开始，收集10分钟窗口内的所有数据点
            for j in range(i, n):
                time_str, time_part, load, pid = sorted_load_info[j]
                try:
                    load_value = float(load.replace('%', ''))
                except:
                    continue
                
                # 检查相邻打印之间的时间间隔是否小于10分钟
                if j > i:
                    try:
                        prev_time_str = sorted_load_info[j-1][1]
                        prev_dt = datetime.strptime(prev_time_str, "%Y-%m-%d %H:%M:%S")
                        current_dt = datetime.strptime(time_part, "%Y-%m-%d %H:%M:%S")
                        interval = (current_dt - prev_dt).total_seconds() / 60
                        if interval > 10:  # 相邻打印间隔超过10分钟，结束当前窗口
                            break
                    except:
                        pass
                
                # 收集所有数据点，不管是否超过阈值
                window_loads.append(load_value)
                window_pids.add(pid)
                
                if window_start_time is None:
                    window_start_time = time_part
                window_end_time = time_part
                
                # 检查时间窗口是否超过10分钟
                if j > i:
                    try:
                        start_dt = datetime.strptime(sorted_load_info[i][1], "%Y-%m-%d %H:%M:%S")
                        current_dt = datetime.strptime(time_part, "%Y-%m-%d %H:%M:%S")
                        duration = (current_dt - start_dt).total_seconds() / 60
                        if duration > time_window_minutes:
                            break
                    except:
                        pass
            
            # 计算窗口内的平均负载
            if len(window_loads) >= 2:
                avg_load = sum(window_loads) / len(window_loads)
                max_load = max(window_loads)
                min_load = min(window_loads)
                
                # 计算持续时间
                try:
                    start_dt = datetime.strptime(window_start_time, "%Y-%m-%d %H:%M:%S")
                    end_dt = datetime.strptime(window_end_time, "%Y-%m-%d %H:%M:%S")
                    duration_minutes = (end_dt - start_dt).total_seconds() / 60
                except:
                    duration_minutes = 0
                
                # 检查打印密度：每5分钟至少有一次打印
                # 计算在这个时间段内，平均每5分钟有多少次打印
                print_density = len(window_loads) / (duration_minutes / 5) if duration_minutes > 0 else 0
                
                # 自适应异常检测：根据负载严重程度使用不同时长门槛
                # - 常规：avg > threshold 且持续 > time_window_minutes（默认10分钟）
                # - 突发高负载：avg > threshold×5 且持续 > 3分钟（如 50% 负载 8 分钟）
                # - 极端负载：avg > threshold×10 且持续 > 1分钟（如 114% 负载 8 分钟）
                is_anomalous = False
                if avg_load > threshold and print_density >= 1:
                    if duration_minutes > time_window_minutes:
                        is_anomalous = True
                    elif avg_load > threshold * 5 and duration_minutes > 3:
                        is_anomalous = True
                    elif avg_load > threshold * 10 and duration_minutes > 1:
                        is_anomalous = True

                if is_anomalous:
                    # 获取PID
                    pid_list = list(window_pids)
                    main_pid = pid_list[0] if pid_list else "N/A"
                    
                    anomaly_apps.append({
                        'package_name': package_name,
                        'pid': main_pid,
                        'duration': duration_minutes,
                        'start_time': window_start_time,
                        'end_time': window_end_time,
                        'avg_load': avg_load,
                        'max_load': max_load,
                        'min_load': min_load,
                        'print_count': len(window_loads)  # 添加打印次数
                    })
                    
                    # 跳过已检测的窗口，移动到窗口结束位置
                    i = j
                    continue
            
            i += 1
    
    # 合并连续的异常时间段
    anomaly_apps = merge_continuous_anomalies(anomaly_apps)
    
    return anomaly_apps

def merge_continuous_anomalies(anomaly_apps):
    """合并连续的异常时间段
    
    Args:
        anomaly_apps: 异常应用列表
        
    Returns:
        list: 合并后的异常应用列表
    """
    if not anomaly_apps:
        return anomaly_apps
    
    # 按包名分组
    apps_by_package = {}
    for app in anomaly_apps:
        package_name = app['package_name']
        if package_name not in apps_by_package:
            apps_by_package[package_name] = []
        apps_by_package[package_name].append(app)
    
    merged_apps = []
    
    # 对每个包的异常时间段进行合并
    for package_name, apps in apps_by_package.items():
        # 按开始时间排序
        sorted_apps = sorted(apps, key=lambda x: x['start_time'])
        
        i = 0
        while i < len(sorted_apps):
            current_app = sorted_apps[i]
            merged_segment = {
                'package_name': package_name,
                'pid': current_app['pid'],
                'duration': current_app['duration'],
                'start_time': current_app['start_time'],
                'end_time': current_app['end_time'],
                'avg_load': current_app['avg_load'],
                'max_load': current_app['max_load'],
                'min_load': current_app['min_load'],
                'segment_count': 1,
                'print_count': current_app.get('print_count', 0)  # 添加打印次数
            }
            
            # 检查后续时间段是否连续
            j = i + 1
            while j < len(sorted_apps):
                next_app = sorted_apps[j]
                
                # 检查是否连续（前一个的结束时间等于后一个的开始时间）
                if next_app['start_time'] == current_app['end_time']:
                    # 合并时间段
                    merged_segment['end_time'] = next_app['end_time']
                    merged_segment['duration'] += next_app['duration']
                    merged_segment['segment_count'] += 1
                    
                    # 累加打印次数
                    merged_segment['print_count'] += next_app.get('print_count', 0)
                    
                    # 更新最高和最低负载
                    merged_segment['max_load'] = max(merged_segment['max_load'], next_app['max_load'])
                    merged_segment['min_load'] = min(merged_segment['min_load'], next_app['min_load'])
                    
                    # 重新计算平均负载（加权平均）
                    total_load = merged_segment['avg_load'] * merged_segment['segment_count'] + next_app['avg_load']
                    merged_segment['avg_load'] = total_load / merged_segment['segment_count']
                    
                    current_app = next_app
                    j += 1
                else:
                    break
            
            merged_apps.append(merged_segment)
            i = j
    
    return merged_apps

def resolve_report_path(log_dir, output_dir=None, report_name="cpuinfo_report.txt"):
    """解析报告输出路径，默认落到 temp 工作区的 analysis/ 目录。"""
    safe_name = os.path.basename((report_name or "").strip()) or "cpuinfo_report.txt"
    repo_root = find_repo_root(__file__)

    if output_dir:
        target_dir = os.path.abspath(output_dir)
    else:
        workspace_dir = resolve_workspace_dir(log_dir, repo_root=repo_root)
        workspace_abs = os.path.abspath(workspace_dir)
        repo_temp = os.path.abspath(temp_root(repo_root))

        # 若输入目录本身不在 temp 工作区下，则回退到 temp/<DATE>/<输入目录名>/analysis/
        if workspace_abs != repo_temp and not workspace_abs.startswith(repo_temp + os.sep):
            workspace_dir = jira_workspace_dir(repo_root, os.path.basename(os.path.abspath(log_dir)))

        target_dir = workspace_analysis(workspace_dir)

    os.makedirs(target_dir, exist_ok=True)
    return os.path.join(target_dir, safe_name)

def generate_report(result, report_path):
    """生成报告文件，包含Cpus Usage信息和按包名统计信息
    
    Args:
        result: 搜索结果字典
        report_path: 报告文件绝对路径
    """
    report_lines = []
    
    # 添加Cpus Usage信息
    report_lines.append("=== Cpus Usage ===")
    if result['cpus_usage_matches']:
        for _, time_part, cpus_usage_part in result['cpus_usage_matches']:
            report_lines.append(f"{time_part} {cpus_usage_part}")
    else:
        report_lines.append("No Cpus Usage information found")
    report_lines.append("")
    
    # 添加按包名统计信息
    report_lines.append("=== Package Statistics ===")
    if result['sorted_package_stats']:
        report_lines.append(f"{'Package':<30} {'Load Print Count':<15} {'Avg Load':<10}")
        report_lines.append("-" * 55)
        for package_name, stats in result['sorted_package_stats'].items():
            report_lines.append(f"{package_name:<30} {stats['count']:<15} {stats['avg_load']:.2f}%")
        report_lines.append("")
        
        # 添加每个包的具体信息
        if result['thread_load_by_package']:
            for package_name, load_info in result['thread_load_by_package'].items():
                report_lines.append(f"=== Package: {package_name} ===")
                report_lines.append(f"{'Time':<20} {'Load':<10} {'PID':<10}")
                report_lines.append("-" * 40)
                for _, time_part, load, pid in load_info:
                    report_lines.append(f"{time_part:<20} {load:<10} {pid:<10}")
                report_lines.append("")
    else:
        report_lines.append("No thread load information found")
    
    # 检测并添加异常应用信息
    anomaly_apps = detect_anomaly_apps(result['thread_load_by_package'])
    
    # 过滤掉包含"binder"关键字的包名
    anomaly_apps = [app for app in anomaly_apps if 'binder' not in app['package_name'].lower()]
    
    # 合并连续的异常时间段
    merged_anomaly_apps = merge_continuous_anomalies(anomaly_apps)
    
    report_lines.append("")
    report_lines.append("=== Anomaly Applications Detection (adaptive: >10%/10min, >50%/3min, >100%/1min) ===")
    
    # 按包名分组统计
    apps_by_package = {}
    for app in merged_anomaly_apps:
        package_name = app['package_name']
        if package_name not in apps_by_package:
            apps_by_package[package_name] = []
        apps_by_package[package_name].append(app)
    
    if apps_by_package:
        terminal_output = []
        terminal_output.append("\n" + "=" * 90)
        terminal_output.append("Detected anomaly applications (adaptive threshold: >10%/10min, >50%/3min, >100%/1min):")
        terminal_output.append("=" * 90)
        
        for package_name, apps in apps_by_package.items():
            # 计算该包名的异常持续总时间
            total_duration = sum(app['duration'] for app in apps)
            pid = apps[0]['pid']
            
            # 添加包名汇总信息
            summary_line = f"Package: {package_name}   PID: {pid}  Total anomaly duration: {total_duration:.1f}min"
            report_lines.append(summary_line)
            terminal_output.append(summary_line)
            
            # 添加时间段详情表头
            report_lines.append("")
            report_lines.append(f"{'Duration':<12} {'Time Range':<30} {'Print Count':<12} {'Avg Load':<10} {'Max Load':<10} {'Min Load':<10}")
            report_lines.append("-" * 90)
            
            terminal_output.append("")
            terminal_output.append(f"{'Duration':<12} {'Time Range':<30} {'Print Count':<12} {'Avg Load':<10} {'Max Load':<10} {'Min Load':<10}")
            terminal_output.append("-" * 90)
            
            # 添加每个时间段的详细信息
            for app in apps:
                time_range = f"{app['start_time']} ~ {app['end_time']}"
                print_count = app.get('print_count', 0)
                detail_line = f"{app['duration']:.1f}min{'':<6} {time_range:<30} {print_count:<12} {app['avg_load']:.2f}%{'':<5} {app['max_load']:.2f}%{'':<5} {app['min_load']:.2f}%"
                report_lines.append(detail_line)
                terminal_output.append(detail_line)
            
            # 添加空行分隔
            report_lines.append("")
            terminal_output.append("")
        
        terminal_output.append("=" * 90)
        print('\n'.join(terminal_output), flush=True)
    else:
        report_lines.append("No anomaly applications detected (All apps avg load <= 10% or burst too short)")
        print("\nNo anomaly applications detected (All apps avg load <= 10% or burst too short)", flush=True)
    
    # 写入报告文件
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_lines))
    except Exception as e:
        pass
    return report_path

def main():
    """主函数（CLI模式）"""
    _setup_utf8_stdio()
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="CPU负载信息分析工具")
    parser.add_argument('-d', '--directory', required=True, help='日志路径（包含linli_666文件的文件夹路径）')
    parser.add_argument('-t', '--time', nargs='*', metavar=('START_TIME', 'END_TIME'), help='开始时间和结束时间（格式：YYYY-MM-DD HH:MM:SS），可选。若只指定一个时间，则视为开始时间；若第一个时间为空，则视为只指定结束时间')
    parser.add_argument('-o', '--output-dir', help='报告输出目录；建议传 temp/<DATE>/<JIRA_KEY>/analysis，省略时自动落到 temp 工作区 analysis/')
    parser.add_argument('--report-name', default='cpuinfo_report.txt', help='报告文件名，默认 cpuinfo_report.txt')
    
    args = parser.parse_args()
    
    folder_path = args.directory
    start_time = None
    end_time = None
    
    # 规范化路径（处理空格和特殊字符）
    folder_path = os.path.normpath(folder_path.strip())
    
    # 处理长路径（超过 260 字符）问题，使用 UNC 路径前缀
    if len(folder_path) > 250 and not folder_path.startswith('\\\\?\\'):
        # 转换为绝对路径并添加 UNC 前缀
        folder_path = '\\\\?\\' + os.path.abspath(folder_path)
    
    # 处理时间参数
    if args.time:
        if len(args.time) == 1:
            start_time = args.time[0]
        elif len(args.time) >= 2:
            start_time = args.time[0]
            end_time = args.time[1]
            if not start_time:
                start_time = None
    
    # 验证文件夹路径
    if not os.path.exists(folder_path):
        print(f"错误：路径不存在: {folder_path}")
        sys.exit(1)
    
    if not os.path.isdir(folder_path):
        print(f"错误：'{folder_path}' 不是有效的文件夹路径")
        sys.exit(1)
    
    # 获取linli_666结尾的文件
    linli_files = get_linli_666_files(folder_path, recursive=True)
    
    if not linli_files:
        sys.exit(1)
    
    # 按时间排序文件
    sorted_files = sort_files_by_time(linli_files)
    
    # 搜索关键字
    keyword = "[K] "  # 含空格
    result = search_keyword_in_files(sorted_files, keyword, start_time, end_time)
    
    # 生成报告文件
    report_path = resolve_report_path(folder_path, args.output_dir, args.report_name)
    generate_report(result, report_path)
    print(f"\n详细报告已保存到: {report_path}", flush=True)

if __name__ == "__main__":
    main()