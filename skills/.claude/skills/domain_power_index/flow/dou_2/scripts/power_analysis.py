"""
功耗分析模块 - 独立封装功耗分析相关功能
包含Wi-Fi和Modem功耗计算、对比分析等功能
"""
import os
import sys
import json
import math
import pandas as pd
from datetime import datetime


def calculate_power_consumption(report_df, current_df):
    """计算Wi-Fi和Modem功耗"""
    print(f"开始计算功耗...")
    print(f"current_df 形状: {current_df.shape}")
    print(f"current_df 列名: {list(current_df.columns)}")
    print(f"report_df 形状: {report_df.shape}")
    print(f"report_df 列名: {list(report_df.columns)}")
    
    # 数据起始行固定为第2行（索引1，对应Excel第2行）
    start_row = 1  # 第2行，pandas索引从0开始
    end_row = len(current_df) - 1  # 最后一行
    
    print(f"数据范围: 起始行(Excel)={start_row+1}, 结束行(Excel)={end_row+1}")
    
    # 查找Wi-Fi数据起始行X（返回的是Excel行号，从1开始）
    wifi_excel_row = 2  # 默认值
    try:
        wifi_excel_row = find_wifi_start_row(report_df, current_df)
        print(f"Wi-Fi起始行(Excel): {wifi_excel_row}")
    except Exception as e:
        print(f"查找Wi-Fi起始行失败: {e}, 使用默认值2")
        wifi_excel_row = 2
    
    # 转换为pandas索引（从0开始）
    wifi_pandas_idx = wifi_excel_row - 1
    
    # Modem数据：第2行到X-1行（Excel行号）
    modem_start = start_row  # pandas索引1（Excel第2行）
    modem_end = wifi_pandas_idx - 1 if wifi_pandas_idx > start_row else start_row
    
    # Wi-Fi数据：X行到结束行（Excel行号）
    wifi_start = wifi_pandas_idx  # pandas索引（对应Excel第X行）
    wifi_end = end_row
    
    print(f"Modem数据范围(pandas): {modem_start} 到 {modem_end}")
    print(f"Wi-Fi数据范围(pandas): {wifi_start} 到 {wifi_end}")
    print(f"Modem数据范围(Excel): {modem_start+1} 到 {modem_end+1}")
    print(f"Wi-Fi数据范围(Excel): {wifi_start+1} 到 {wifi_end+1}")
    
    try:
        # 计算Modem功耗
        modem_on_power = calculate_weighted_average(current_df, 'H', 'D', 'E', 'on', modem_start, modem_end)
        modem_off_power = calculate_weighted_average(current_df, 'H', 'D', 'E', 'off', modem_start, modem_end)
        modem_on_time = calculate_sum(current_df, 'D', 'E', 'on', modem_start, modem_end) / 3600
        modem_off_time = calculate_sum(current_df, 'D', 'E', 'off', modem_start, modem_end) / 3600
        
        # 计算Wi-Fi功耗
        wifi_on_power = calculate_weighted_average(current_df, 'H', 'D', 'E', 'on', wifi_start, wifi_end)
        wifi_off_power = calculate_weighted_average(current_df, 'H', 'D', 'E', 'off', wifi_start, wifi_end)
        wifi_on_time = calculate_sum(current_df, 'D', 'E', 'on', wifi_start, wifi_end) / 3600
        wifi_off_time = calculate_sum(current_df, 'D', 'E', 'off', wifi_start, wifi_end) / 3600
        
        print(f"计算结果: Modem功耗={modem_on_power}/{modem_off_power}, Wi-Fi功耗={wifi_on_power}/{wifi_off_power}")

        def _safe_float(v, default=0.0):
            try:
                fv = float(v)
                if math.isnan(fv):
                    return float(default)
                return fv
            except Exception:
                return float(default)

        def _combined_power(on_or_off: str) -> float:
            if on_or_off == "on":
                denom = _safe_float(modem_on_time) + _safe_float(wifi_on_time)
                if denom <= 0:
                    return 0.0
                return (
                    _safe_float(modem_on_power) * _safe_float(modem_on_time)
                    + _safe_float(wifi_on_power) * _safe_float(wifi_on_time)
                ) / denom
            else:
                denom = _safe_float(modem_off_time) + _safe_float(wifi_off_time)
                if denom <= 0:
                    return 0.0
                return (
                    _safe_float(modem_off_power) * _safe_float(modem_off_time)
                    + _safe_float(wifi_off_power) * _safe_float(wifi_off_time)
                ) / denom

        combined_on_power = _combined_power("on")
        combined_off_power = _combined_power("off")
        
        # 确保所有值都是JSON可序列化的浮点数
        return {
            'modem': {
                'on_power': _safe_float(modem_on_power),
                'off_power': _safe_float(modem_off_power),
                'on_time': _safe_float(modem_on_time),
                'off_time': _safe_float(modem_off_time),
            },
            'wifi': {
                'on_power': _safe_float(wifi_on_power),
                'off_power': _safe_float(wifi_off_power),
                'on_time': _safe_float(wifi_on_time),
                'off_time': _safe_float(wifi_off_time),
            },
            # 新增：亮屏/灭屏综合加权功耗（mA）
            'combined': {
                'on_power': _safe_float(combined_on_power),
                'off_power': _safe_float(combined_off_power),
            },
            'wifi_start_row': int(wifi_excel_row)
        }
        
    except Exception as e:
        print(f"计算功耗时出错: {e}")
        # 返回默认值
        return {
            'modem': {
                'on_power': 0.0,
                'off_power': 0.0,
                'on_time': 0.0,
                'off_time': 0.0
            },
            'wifi': {
                'on_power': 0.0,
                'off_power': 0.0,
                'on_time': 0.0,
                'off_time': 0.0
            },
            'combined': {
                'on_power': 0.0,
                'off_power': 0.0,
            },
            'wifi_start_row': wifi_excel_row
        }


def find_wifi_start_row(report_df, current_df):
    """查找Wi-Fi数据起始行X - 基于时间匹配"""
    print(f"开始查找Wi-Fi起始行...")
    print(f"report_df 形状: {report_df.shape}, 列名: {list(report_df.columns)}")
    print(f"current_df 形状: {current_df.shape}, 列名: {list(current_df.columns)}")
    
    # 步骤1: 在report页面的desc列中查找第一个后缀是WIFI的行
    wifi_row_report = None
    wifi_starttime = None
    
    print("=== 开始WIFI后缀检测 ===")
    
    # 显示所有行的desc内容和E列时间用于调试
    print("=== report_df 所有行的desc内容和E列时间 ===")
    for idx, row in report_df.iterrows():
        if len(row) > 4:  # 确保有E列
            desc_val = row['desc'] if 'desc' in row and pd.notna(row['desc']) else "无desc"
            e_col_val = row.iloc[4]  # 直接获取E列数据
            print(f"行 {idx}: desc='{desc_val}', E列时间='{e_col_val}'")
    print("=== 结束 desc和E列时间 ===")
    
    # 记录所有找到的WIFI行
    all_wifi_rows = []
    
    for idx, row in report_df.iterrows():
        if 'desc' in row and pd.notna(row['desc']):
            desc_str = str(row['desc']).strip()
            print(f"检查行 {idx}: {desc_str}")
            
            # 专门检测后缀是WIFI的情况
            wifi_found = False
            
            # 1. 检测以-WIFI结尾（如"TikTok播放视频并切换-WIFI"）
            if desc_str.endswith('-WIFI'):
                wifi_found = True
                print(f"  ✓ 检测到-WIFI后缀")
            
            # 2. 检测以_WIFI结尾
            elif desc_str.endswith('_WIFI'):
                wifi_found = True
                print(f"  ✓ 检测到_WIFI后缀")
            
            # 3. 检测以 WIFI结尾（空格+WIFI）
            elif desc_str.endswith(' WIFI'):
                wifi_found = True
                print(f"  ✓ 检测到 WIFI后缀")
            
            # 4. 检测以+WIFI结尾
            elif desc_str.endswith('+WIFI'):
                wifi_found = True
                print(f"  ✓ 检测到+WIFI后缀")
            
            # 5. 检测以.WIFI结尾
            elif desc_str.endswith('.WIFI'):
                wifi_found = True
                print(f"  ✓ 检测到.WIFI后缀")
            
            # 6. 检测以:WIFI结尾
            elif desc_str.endswith(':WIFI'):
                wifi_found = True
                print(f"  ✓ 检测到:WIFI后缀")
            
            # 如果找到WIFI后缀，记录这一行（不break，继续检查后面的行）
            if wifi_found:
                # 使用和CPU对比相同的时间解析方法
                starttime_value = None
                starttime_raw = None
                
                print(f"  🔍 使用CPU对比方法解析时间...")
                
                # 方法1: 按列名'starttime'提取（和CPU对比相同）
                if 'starttime' in row:
                    raw_time = row['starttime']
                    print(f"  📍 原始starttime: '{raw_time}' (类型: {type(raw_time)})")
                    
                    # 和CPU对比相同：直接提取字符串
                    starttime_raw = str(raw_time)
                    print(f"  ✅ 提取到starttime字符串: '{starttime_raw}'")
                    
                    # 和CPU对比相同：使用datetime.strptime解析
                    try:
                        if "." in starttime_raw:
                            parsed_datetime = datetime.strptime(starttime_raw, "%Y-%m-%d %H:%M:%S.%f")
                        else:
                            parsed_datetime = datetime.strptime(starttime_raw, "%Y-%m-%d %H:%M:%S")
                        
                        starttime_value = parsed_datetime.timestamp()
                        print(f"  🕐 CPU方法解析成功: '{starttime_raw}' → 时间戳: {starttime_value}")
                    except Exception as e:
                        print(f"  ⚠️ CPU方法解析失败: {e}")
                
                # 方法2: 按位置提取E列（第5列）
                if starttime_value is None and len(row) > 4:
                    e_col_value = row.iloc[4]
                    print(f"  📍 E列数据: '{e_col_value}' (类型: {type(e_col_value)})")
                    
                    # 和CPU对比相同：直接提取字符串
                    e_col_str = str(e_col_value)
                    print(f"  ✅ 提取到E列字符串: '{e_col_str}'")
                    
                    # 和CPU对比相同：使用datetime.strptime解析
                    try:
                        if "." in e_col_str:
                            parsed_datetime = datetime.strptime(e_col_str, "%Y-%m-%d %H:%M:%S.%f")
                        else:
                            parsed_datetime = datetime.strptime(e_col_str, "%Y-%m-%d %H:%M:%S")
                        
                        starttime_value = parsed_datetime.timestamp()
                        print(f"  🕐 CPU方法解析E列成功: '{e_col_str}' → 时间戳: {starttime_value}")
                    except Exception as e:
                        print(f"  ⚠️ CPU方法解析E列失败: {e}")
                
                # 存储提取的值（不管是不是nan）
                wifi_info = {
                    'row': idx,
                    'desc': desc_str,
                    'starttime': starttime_raw,  # 直接存储原始值
                    'starttime_raw': starttime_raw
                }
                all_wifi_rows.append(wifi_info)
                print(f"  📋 记录WIFI行: 行号={idx}, desc='{desc_str}', starttime='{starttime_raw}'")
            else:
                print(f"  ✗ 未检测到WIFI后缀")

    # 显示所有找到的WIFI行
    print(f"\n=== 总共找到 {len(all_wifi_rows)} 个WIFI行 ===")
    for i, wifi_info in enumerate(all_wifi_rows):
        print(f"WIFI行 {i+1}: 行号={wifi_info['row']}, desc={wifi_info['desc']}, starttime={wifi_info['starttime']}")
    
    # 使用第一个有E列时间的WIFI行
    wifi_row_report = None
    wifi_starttime = None
    for wifi_info in all_wifi_rows:
        if wifi_info['starttime'] is not None:
            wifi_row_report = wifi_info['row']
            wifi_starttime = wifi_info['starttime']
            print(f"\n🎯 选择WIFI行: {wifi_row_report}")
            break
    
    if wifi_row_report is None or wifi_starttime is None:
        if wifi_row_report is None:
            print("⚠️  未找到任何WIFI后缀行")
        else:
            print(f"⚠️  找到WIFI后缀行（行号{wifi_row_report}），但starttime为空/不存在")
        print("使用默认行号2")
        return 2
    
    # 步骤2: 解析时间字符串
    try:
        # 尝试将时间字符串解析为datetime对象
        if isinstance(wifi_starttime, str):
            # 处理格式如 "2025-12-29 22:01:24.005086"
            r_datetime = pd.to_datetime(wifi_starttime, format='%Y-%m-%d %H:%M:%S.%f', errors='coerce')
            if pd.isna(r_datetime):
                # 尝试其他格式
                r_datetime = pd.to_datetime(wifi_starttime, errors='coerce')
            
            if pd.notna(r_datetime):
                # 转换为时间戳（秒）
                r = r_datetime.timestamp()
            else:
                print(f"无法解析时间字符串: {wifi_starttime}")
                return 2
        elif isinstance(wifi_starttime, (int, float)):
            # 已经是数值类型
            r = float(wifi_starttime)
        else:
            print(f"不支持的r类型: {type(wifi_starttime)}, 值: {wifi_starttime}")
            return 2
        
        print(f"解析后的时间r: {r} (时间戳)")
    except Exception as e:
        print(f"时间解析失败: {e}, 使用默认值2")
        return 2
    
    # 步骤3: 在current页面中找到starttime ≤ r ≤ endtime的行
    print(f"开始在current中查找时间匹配...")
    best_match_idx = None
    best_distance = float('inf')
    
    for idx, row in current_df.iterrows():
        if idx < 1:  # 跳过标题行（通常第0行是标题）
            continue
            
        current_starttime = row['starttime'] if 'starttime' in row and pd.notna(row['starttime']) else None
        current_endtime = row['endtime'] if 'endtime' in row and pd.notna(row['endtime']) else None
        
        if current_starttime is not None and current_endtime is not None:
            try:
                # 解析时间字符串
                start_time = None
                end_time = None
                
                if isinstance(current_starttime, str):
                    start_datetime = pd.to_datetime(current_starttime, format='%Y-%m-%d %H:%M:%S.%f', errors='coerce')
                    if pd.isna(start_datetime):
                        start_datetime = pd.to_datetime(current_starttime, errors='coerce')
                    if pd.notna(start_datetime):
                        start_time = start_datetime.timestamp()
                elif isinstance(current_starttime, (int, float)):
                    start_time = float(current_starttime)
                
                if isinstance(current_endtime, str):
                    end_datetime = pd.to_datetime(current_endtime, format='%Y-%m-%d %H:%M:%S.%f', errors='coerce')
                    if pd.isna(end_datetime):
                        end_datetime = pd.to_datetime(current_endtime, errors='coerce')
                    if pd.notna(end_datetime):
                        end_time = end_datetime.timestamp()
                elif isinstance(current_endtime, (int, float)):
                    end_time = float(current_endtime)
                
                if start_time is not None and end_time is not None:
                    print(f"行 {idx}: starttime={start_time}, endtime={end_time}, 目标r={r}")
                    
                    # 检查r是否在该时间范围内
                    if start_time <= r <= end_time:
                        # 计算r到starttime的距离
                        dist_to_start = abs(r - start_time)
                        dist_to_end = abs(end_time - r)
                        
                        print(f"  找到匹配: dist_to_start={dist_to_start}, dist_to_end={dist_to_end}")
                        
                        # 根据规则确定X行
                        if dist_to_start < dist_to_end:
                            # r更接近starttime，X为当前行号
                            print(f"  选择当前行号: {idx}")
                            return idx
                        else:
                            # r更接近endtime，X为当前行号+1
                            print(f"  选择当前行号+1: {idx + 1}")
                            return idx + 1
                        
            except Exception as e:
                print(f"  行 {idx} 时间解析失败: {e}")
                continue
    
    print("未找到时间匹配，使用默认行号2")
    # 如果没有找到匹配的行，默认从第2行开始
    return 2


def calculate_weighted_average(df, power_col, time_col, screen_col, screen_state, start_row, end_row):
    """计算加权平均值 - 按照Excel列字母对应实际数据列"""
    try:
        print(f"计算加权平均值: power_col={power_col}, time_col={time_col}, screen_col={screen_col}")
        print(f"数据范围: {start_row} 到 {end_row}")
        
        # 根据Excel列字母确定实际列名
        power_col_map = {
            'H': 'avg_cur_4v',
            'avg_cur_4v': 'avg_cur_4v'
        }
        
        time_col_map = {
            'D': 'duration_sec',
            'duration_sec': 'duration_sec'
        }
        
        screen_col_map = {
            'E': 'screen',  # 修正：实际列名是'screen'，不是'screen_state'
            'screen_state': 'screen',
            'screen': 'screen'
        }
        
        # 获取实际列名
        actual_power_col = power_col_map.get(power_col, power_col)
        actual_time_col = time_col_map.get(time_col, time_col)
        actual_screen_col = screen_col_map.get(screen_col, screen_col)
        
        print(f"实际列名: power={actual_power_col}, time={actual_time_col}, screen={actual_screen_col}")
        print(f"可用列名: {list(df.columns)}")
        
        power_data = []
        time_data = []
        
        for idx in range(start_row, end_row + 1):
            if idx < len(df):
                row = df.iloc[idx]
                
                # 获取屏幕状态
                screen_val = None
                if actual_screen_col in df.columns:
                    screen_val = str(row[actual_screen_col]).strip().lower()
                
                if screen_val == screen_state.lower():
                    # 获取功耗值
                    power_val = None
                    if actual_power_col in df.columns:
                        power_val = pd.to_numeric(row[actual_power_col], errors='coerce')
                    
                    # 获取时间值
                    time_val = None
                    if actual_time_col in df.columns:
                        time_val = pd.to_numeric(row[actual_time_col], errors='coerce')
                    
                    if power_val is not None and time_val is not None and not pd.isna(power_val) and not pd.isna(time_val):
                        power_data.append(float(power_val))
                        time_data.append(float(time_val))
        
        print(f"找到 {len(power_data)} 个有效数据点")
        
        if not power_data or not time_data:
            return 0.0
        
        # 计算加权平均值
        weighted_sum = sum(p * t for p, t in zip(power_data, time_data))
        total_time = sum(time_data)
        
        result = weighted_sum / total_time if total_time != 0 else 0.0
        print(f"加权平均值结果: {result:.4f} mA")
        return result
        
    except Exception as e:
        print(f"计算加权平均值错误: {e}")
        return 0.0


def calculate_sum(df, time_col, screen_col, screen_state, start_row, end_row):
    """计算总和 - 按照Excel列字母对应实际数据列"""
    try:
        print(f"计算总和: time_col={time_col}, screen_col={screen_col}, screen_state={screen_state}")
        print(f"数据范围: {start_row} 到 {end_row}")
        
        # 根据Excel列字母确定实际列名
        time_col_map = {
            'D': 'duration_sec',
            'duration_sec': 'duration_sec'
        }
        
        screen_col_map = {
            'E': 'screen',  # 修正：实际列名是'screen'，不是'screen_state'
            'screen_state': 'screen',
            'screen': 'screen'
        }
        
        # 获取实际列名
        actual_time_col = time_col_map.get(time_col, time_col)
        actual_screen_col = screen_col_map.get(screen_col, screen_col)
        
        print(f"实际列名: time={actual_time_col}, screen={actual_screen_col}")
        print(f"可用列名: {list(df.columns)}")
        
        total = 0.0
        valid_count = 0
        
        for idx in range(start_row, end_row + 1):
            if idx < len(df):
                row = df.iloc[idx]
                
                # 获取屏幕状态
                screen_val = None
                if actual_screen_col in df.columns:
                    screen_val = str(row[actual_screen_col]).strip().lower()
                
                if screen_val == screen_state.lower():
                    # 获取时间值
                    time_val = None
                    if actual_time_col in df.columns:
                        time_val = pd.to_numeric(row[actual_time_col], errors='coerce')
                    
                    if time_val is not None and not pd.isna(time_val):
                        total += float(time_val)
                        valid_count += 1
        
        print(f"找到 {valid_count} 个有效数据点，总和: {total:.2f} 秒")
        return total
        
    except Exception as e:
        print(f"计算总和错误: {e}")
        return 0.0


def compare_power_consumption(result1, result2):
    """对比两个版本的功耗数据。result1=高功耗侧，result2=低功耗侧；差值为高−低，比例为 (高−低)/高。"""
    import math
    
    comparison = {}

    components_metrics = {
        'modem': ['on_power', 'off_power', 'on_time', 'off_time'],
        'wifi': ['on_power', 'off_power', 'on_time', 'off_time'],
        # 新增：综合亮屏/灭屏加权功耗（mA）
        'combined': ['on_power', 'off_power'],
    }

    for component, metrics in components_metrics.items():
        comparison[component] = {}
        for metric in metrics:
            val1 = (result1.get(component) or {}).get(metric, 0.0)
            val2 = (result2.get(component) or {}).get(metric, 0.0)
            try:
                val1 = float(val1)
            except Exception:
                val1 = 0.0
            try:
                val2 = float(val2)
            except Exception:
                val2 = 0.0
            
            # 处理NaN值
            if math.isnan(val1) or math.isnan(val2):
                difference = 0.0
                difference_percent = 0.0
                is_high_power = False
            else:
                # version1=高功耗目录，version2=低功耗目录：差值 = 高 − 低
                difference = val1 - val2
                
                # 百分比：(高 − 低) / 高 × 100%
                if val1 == 0:
                    if val2 == 0:
                        difference_percent = 0.0
                    else:
                        difference_percent = 999.99  # 用一个大的数值代替无穷大
                else:
                    difference_percent = ((val1 - val2) / val1) * 100
                    # 限制百分比范围，避免过大的数值
                    if abs(difference_percent) > 999.99:
                        difference_percent = 999.99 if difference_percent > 0 else -999.99
            
            # 将Python布尔值转换为JSON兼容的布尔值
            comparison[component][metric] = {
                'version1': float(val1) if not math.isnan(val1) else 0.0,
                'version2': float(val2) if not math.isnan(val2) else 0.0,
                'difference': float(difference),
                'difference_percent': float(difference_percent),
                'is_high_power': bool(difference_percent > 10)  # 差异超过10%认为是高功耗
            }
    
    return comparison


class HighPowerAnalyzer:
    """高功耗场景分析器类 - 完整封装高功耗分析功能"""
    
    def __init__(self, scene1_folder=None, scene2_folder=None):
        """初始化高功耗分析器"""
        self.scene1_folder = scene1_folder
        self.scene2_folder = scene2_folder
    
    def set_folders(self, scene1_folder, scene2_folder):
        """设置分析文件夹"""
        self.scene1_folder = scene1_folder
        self.scene2_folder = scene2_folder
        return self
    
    def find_test_report(self, folder_path):
        """在文件夹中查找testReport.xlsx文件 - 使用原来的查找逻辑"""
        try:
            # 直接使用原来的find_test_report函数
            from utils import find_test_report as original_find_test_report
            return original_find_test_report(folder_path)
        except ImportError:
            # 如果导入失败，使用简单的查找逻辑
            import os
            
            if not folder_path or not os.path.exists(folder_path):
                return None
            
            # 首先在meta_report文件夹中查找
            meta_report_path = os.path.join(folder_path, 'meta_report')
            if os.path.exists(meta_report_path) and os.path.isdir(meta_report_path):
                for filename in os.listdir(meta_report_path):
                    if filename.lower() == "testreport.xlsx":
                        return os.path.join(meta_report_path, filename)
            
            # 如果没有找到，在根目录下查找
            for dirpath, _, filenames in os.walk(folder_path):
                for filename in filenames:
                    if filename.lower() == "testreport.xlsx":
                        return os.path.join(dirpath, filename)
            
            return None
    
    def validate_folders(self):
        """验证文件夹设置"""
        if not self.scene1_folder or not self.scene2_folder:
            return {'success': False, 'message': '请先设置两个版本的文件夹'}
        
        if not os.path.exists(self.scene1_folder):
            return {'success': False, 'message': f'版本1文件夹不存在: {self.scene1_folder}'}
        
        if not os.path.exists(self.scene2_folder):
            return {'success': False, 'message': f'版本2文件夹不存在: {self.scene2_folder}'}
        
        return {'success': True}
    
    def _count_valid_data_points(self, df):
        """计算有效数据点数量"""
        print(f"=== 开始计算有效数据点 ===")
        print(f"数据框形状: {df.shape}")
        
        if df.empty:
            print("数据框为空")
            return 0
        
        # 检查关键列是否存在
        required_columns = ['duration_sec', 'avg_cur']
        available_columns = [col for col in required_columns if col in df.columns]
        
        print(f"需要的列: {required_columns}")
        print(f"可用的列: {available_columns}")
        
        if not available_columns:
            print("没有找到需要的列")
            return 0
        
        # 确保数据类型正确转换
        if 'duration_sec' in df.columns:
            print(f"duration_sec 列前5个值: {df['duration_sec'].head().tolist()}")
            df['duration_sec'] = pd.to_numeric(df['duration_sec'], errors='coerce')
            print(f"duration_sec 列转换后前5个值: {df['duration_sec'].head().tolist()}")
            print(f"duration_sec 列非空值数量: {df['duration_sec'].notna().sum()}")
            print(f"duration_sec > 0 的数量: {(df['duration_sec'] > 0).sum()}")
        
        if 'avg_cur' in df.columns:
            print(f"avg_cur 列前5个值: {df['avg_cur'].head().tolist()}")
            df['avg_cur'] = pd.to_numeric(df['avg_cur'], errors='coerce')
            print(f"avg_cur 列转换后前5个值: {df['avg_cur'].head().tolist()}")
            print(f"avg_cur 列非空值数量: {df['avg_cur'].notna().sum()}")
        
        # 计算有效数据点（duration_sec > 0 且 avg_cur 不为空）
        if 'duration_sec' in df.columns and 'avg_cur' in df.columns:
            valid_points = df[(df['duration_sec'] > 0) & (df['avg_cur'].notna())].shape[0]
            print(f"有效数据点数量: {valid_points}")
            print(f"=== 有效数据点计算完成 ===")
            return valid_points
        
        # 如果只有部分列存在，返回非空行数
        result = df.dropna(subset=available_columns).shape[0]
        print(f"部分列有效数据点数量: {result}")
        print(f"=== 有效数据点计算完成 ===")
        return result
    
    def analyze_high_power_scenario(self):
        """执行完整的高功耗场景分析"""
        # 验证文件夹
        validation = self.validate_folders()
        if not validation['success']:
            return validation
        
        # 查找Excel文件
        file_path_1 = self.find_test_report(self.scene1_folder)
        file_path_2 = self.find_test_report(self.scene2_folder)
        
        if not file_path_1:
            return {'success': False, 'message': f'在版本1文件夹中未找到testReport.xlsx文件: {self.scene1_folder}'}
        
        if not file_path_2:
            return {'success': False, 'message': f'在版本2文件夹中未找到testReport.xlsx文件: {self.scene2_folder}'}
        
        # 执行高功耗分析
        return self.analyze_high_power(file_path_1, file_path_2)
    
    def analyze_high_power(self, file_path_1, file_path_2):
        """执行高功耗分析 - 从PowerAnalyzer类复制的方法"""
        print(f"=== 开始高功耗分析 ===")
        print(f"文件1路径: {file_path_1}")
        print(f"文件2路径: {file_path_2}")
        
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path_1):
                print(f"文件1不存在: {file_path_1}")
                return {'success': False, 'message': f'文件不存在: {file_path_1}'}
            if not os.path.exists(file_path_2):
                print(f"文件2不存在: {file_path_2}")
                return {'success': False, 'message': f'文件不存在: {file_path_2}'}
            
            # 读取两个版本的Excel文件
            print("正在读取Excel文件...")
            df1_report = pd.read_excel(file_path_1, sheet_name="report")
            df2_report = pd.read_excel(file_path_2, sheet_name="report")
            
            df1_current = pd.read_excel(file_path_1, sheet_name="current")
            df2_current = pd.read_excel(file_path_2, sheet_name="current")
            
            # 调试信息：打印数据框的列名和形状
            print(f"=== 数据框信息 ===")
            print(f"版本1 current 列名: {list(df1_current.columns)}")
            print(f"版本1 current 形状: {df1_current.shape}")
            print(f"版本1 current 前3行数据:")
            print(df1_current.head(3))
            
            print(f"版本1 report 列名: {list(df1_report.columns)}")
            print(f"版本1 report 形状: {df1_report.shape}")
            
            print(f"版本2 current 列名: {list(df2_current.columns)}")
            print(f"版本2 current 形状: {df2_current.shape}")
            print(f"版本2 current 前3行数据:")
            print(df2_current.head(3))
            
            print(f"版本2 report 列名: {list(df2_report.columns)}")
            print(f"版本2 report 形状: {df2_report.shape}")
            
            # 检查数据有效性
            if df1_current.empty or df2_current.empty:
                print("current工作表为空")
                return {
                    'success': False,
                    'message': 'current工作表为空，请检查Excel文件格式'
                }
            
            # 转换数据类型 - 更详细的数据类型转换
            numeric_columns = ['duration_sec', 'avg_cur', 'avg_vol', 'avg_cur_4v']
            time_columns = ['starttime', 'endtime']
            screen_columns = ['screen_state', 'screen', 'E']
            
            print(f"=== 数据类型转换 ===")
            # 处理每个数据框
            for i, df in enumerate([df1_current, df2_current], 1):
                print(f"处理版本 {i} 数据框")
                
                # 处理数值列 - 确保正确转换为数字
                for col in numeric_columns:
                    if col in df.columns:
                        print(f"  转换列 {col}:")
                        print(f"    前类型: {df[col].dtype}")
                        print(f"    前5个值: {df[col].head().tolist()}")
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                        print(f"    后类型: {df[col].dtype}")
                        print(f"    后5个值: {df[col].head().tolist()}")
                        # 检查转换结果
                        non_numeric_count = df[col].isna().sum()
                        print(f"    非数值数量: {non_numeric_count}/{len(df)}")
                
                # 处理时间列 - 保持原始格式
                for col in time_columns:
                    if col in df.columns:
                        print(f"  时间列 {col} 类型: {df[col].dtype}")
                        print(f"  时间列 {col} 前3个值: {df[col].head(3).tolist()}")
                
                # 处理屏幕状态列
                for col in screen_columns:
                    if col in df.columns:
                        print(f"  屏幕状态列 {col}:")
                        print(f"    前类型: {df[col].dtype}")
                        print(f"    前5个值: {df[col].head().tolist()}")
                        df[col] = df[col].astype(str)
                        print(f"    后类型: {df[col].dtype}")
                        print(f"    唯一值: {df[col].unique()}")
                        break
            
            # 检查有效数据点
            print(f"=== 有效数据点检查 ===")
            valid_data_points_1 = self._count_valid_data_points(df1_current)
            valid_data_points_2 = self._count_valid_data_points(df2_current)
            
            print(f"版本1有效数据点: {valid_data_points_1}")
            print(f"版本2有效数据点: {valid_data_points_2}")
            
            if valid_data_points_1 == 0 or valid_data_points_2 == 0:
                print("有效数据点不足，分析终止")
                return {
                    'success': False,
                    'message': f'找到 {valid_data_points_1} 个有效数据点（版本1）和 {valid_data_points_2} 个有效数据点（版本2），请检查数据格式'
                }
            
            print("=== 开始计算功耗 ===")
            # 计算Wi-Fi和Modem功耗
            result1 = calculate_power_consumption(df1_report, df1_current)
            result2 = calculate_power_consumption(df2_report, df2_current)
            
            # 对比分析
            comparison_result = compare_power_consumption(result1, result2)
            
            print(f"=== 高功耗分析完成 ===")
            return {
                'success': True,
                'data': {
                    'version1': result1,
                    'version2': result2,
                    'comparison': comparison_result,
                    'valid_data_points': {
                        'version1': valid_data_points_1,
                        'version2': valid_data_points_2
                    }
                }
            }
            
        except Exception as e:
            print(f"高功耗分析异常: {str(e)}")
            return {
                'success': False,
                'message': f'高功耗分析失败: {str(e)}'
            }


class PowerAnalyzer:
    """功耗分析器类"""
    
    def __init__(self):
        """初始化功耗分析器"""
        pass
    
    def _count_valid_data_points(self, df):
        """计算有效数据点数量"""
        print(f"=== 开始计算有效数据点 ===")
        print(f"数据框形状: {df.shape}")
        
        if df.empty:
            print("数据框为空")
            return 0
        
        # 检查关键列是否存在
        required_columns = ['duration_sec', 'avg_cur']
        available_columns = [col for col in required_columns if col in df.columns]
        
        print(f"需要的列: {required_columns}")
        print(f"可用的列: {available_columns}")
        
        if not available_columns:
            print("没有找到需要的列")
            return 0
        
        # 确保数据类型正确转换
        if 'duration_sec' in df.columns:
            print(f"duration_sec 列前5个值: {df['duration_sec'].head().tolist()}")
            df['duration_sec'] = pd.to_numeric(df['duration_sec'], errors='coerce')
            print(f"duration_sec 列转换后前5个值: {df['duration_sec'].head().tolist()}")
            print(f"duration_sec 列非空值数量: {df['duration_sec'].notna().sum()}")
            print(f"duration_sec > 0 的数量: {(df['duration_sec'] > 0).sum()}")
        
        if 'avg_cur' in df.columns:
            print(f"avg_cur 列前5个值: {df['avg_cur'].head().tolist()}")
            df['avg_cur'] = pd.to_numeric(df['avg_cur'], errors='coerce')
            print(f"avg_cur 列转换后前5个值: {df['avg_cur'].head().tolist()}")
            print(f"avg_cur 列非空值数量: {df['avg_cur'].notna().sum()}")
        
        # 计算有效数据点（duration_sec > 0 且 avg_cur 不为空）
        if 'duration_sec' in df.columns and 'avg_cur' in df.columns:
            valid_points = df[(df['duration_sec'] > 0) & (df['avg_cur'].notna())].shape[0]
            print(f"有效数据点数量: {valid_points}")
            print(f"=== 有效数据点计算完成 ===")
            return valid_points
        
        # 如果只有部分列存在，返回非空行数
        result = df.dropna(subset=available_columns).shape[0]
        print(f"部分列有效数据点数量: {result}")
        print(f"=== 有效数据点计算完成 ===")
        return result
    
    def analyze_high_power(self, file_path_1, file_path_2):
        """执行高功耗分析"""
        print(f"=== 开始高功耗分析 ===")
        print(f"文件1路径: {file_path_1}")
        print(f"文件2路径: {file_path_2}")
        
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path_1):
                print(f"文件1不存在: {file_path_1}")
                return {'success': False, 'message': f'文件不存在: {file_path_1}'}
            if not os.path.exists(file_path_2):
                print(f"文件2不存在: {file_path_2}")
                return {'success': False, 'message': f'文件不存在: {file_path_2}'}
            
            # 读取两个版本的Excel文件
            print("正在读取Excel文件...")
            df1_report = pd.read_excel(file_path_1, sheet_name="report")
            df2_report = pd.read_excel(file_path_2, sheet_name="report")
            
            df1_current = pd.read_excel(file_path_1, sheet_name="current")
            df2_current = pd.read_excel(file_path_2, sheet_name="current")
            
            # 调试信息：打印数据框的列名和形状
            print(f"=== 数据框信息 ===")
            print(f"版本1 current 列名: {list(df1_current.columns)}")
            print(f"版本1 current 形状: {df1_current.shape}")
            print(f"版本1 current 前3行数据:")
            print(df1_current.head(3))
            
            print(f"版本1 report 列名: {list(df1_report.columns)}")
            print(f"版本1 report 形状: {df1_report.shape}")
            
            print(f"版本2 current 列名: {list(df2_current.columns)}")
            print(f"版本2 current 形状: {df2_current.shape}")
            print(f"版本2 current 前3行数据:")
            print(df2_current.head(3))
            
            print(f"版本2 report 列名: {list(df2_report.columns)}")
            print(f"版本2 report 形状: {df2_report.shape}")
            
            # 检查数据有效性
            if df1_current.empty or df2_current.empty:
                print("current工作表为空")
                return {
                    'success': False,
                    'message': 'current工作表为空，请检查Excel文件格式'
                }
            
            # 转换数据类型 - 更详细的数据类型转换
            numeric_columns = ['duration_sec', 'avg_cur', 'avg_vol', 'avg_cur_4v']
            time_columns = ['starttime', 'endtime']
            screen_columns = ['screen_state', 'screen', 'E']
            
            print(f"=== 数据类型转换 ===")
            # 处理每个数据框
            for i, df in enumerate([df1_current, df2_current], 1):
                print(f"处理版本 {i} 数据框")
                
                # 处理数值列 - 确保正确转换为数字
                for col in numeric_columns:
                    if col in df.columns:
                        print(f"  转换列 {col}:")
                        print(f"    前类型: {df[col].dtype}")
                        print(f"    前5个值: {df[col].head().tolist()}")
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                        print(f"    后类型: {df[col].dtype}")
                        print(f"    后5个值: {df[col].head().tolist()}")
                        # 检查转换结果
                        non_numeric_count = df[col].isna().sum()
                        print(f"    非数值数量: {non_numeric_count}/{len(df)}")
                
                # 处理时间列 - 保持原始格式
                for col in time_columns:
                    if col in df.columns:
                        print(f"  时间列 {col} 类型: {df[col].dtype}")
                        print(f"  时间列 {col} 前3个值: {df[col].head(3).tolist()}")
                
                # 处理屏幕状态列
                for col in screen_columns:
                    if col in df.columns:
                        print(f"  屏幕状态列 {col}:")
                        print(f"    前类型: {df[col].dtype}")
                        print(f"    前5个值: {df[col].head().tolist()}")
                        df[col] = df[col].astype(str)
                        print(f"    后类型: {df[col].dtype}")
                        print(f"    唯一值: {df[col].unique()}")
                        break
            
            # 检查有效数据点
            print(f"=== 有效数据点检查 ===")
            valid_data_points_1 = self._count_valid_data_points(df1_current)
            valid_data_points_2 = self._count_valid_data_points(df2_current)
            
            print(f"版本1有效数据点: {valid_data_points_1}")
            print(f"版本2有效数据点: {valid_data_points_2}")
            
            if valid_data_points_1 == 0 or valid_data_points_2 == 0:
                print("有效数据点不足，分析终止")
                return {
                    'success': False,
                    'message': f'找到 {valid_data_points_1} 个有效数据点（版本1）和 {valid_data_points_2} 个有效数据点（版本2），请检查数据格式'
                }
            
            print("=== 开始计算功耗 ===")
            # 计算Wi-Fi和Modem功耗
            result1 = calculate_power_consumption(df1_report, df1_current)
            result2 = calculate_power_consumption(df2_report, df2_current)
            
            # 对比分析
            comparison_result = compare_power_consumption(result1, result2)
            
            print(f"=== 高功耗分析完成 ===")
            return {
                'success': True,
                'data': {
                    'version1': result1,
                    'version2': result2,
                    'comparison': comparison_result,
                    'valid_data_points': {
                        'version1': valid_data_points_1,
                        'version2': valid_data_points_2
                    }
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'高功耗分析失败: {str(e)}'
            }