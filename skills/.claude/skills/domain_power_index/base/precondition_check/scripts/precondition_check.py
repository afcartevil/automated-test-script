#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检测设备状态的工具脚本
从 mainlog 中检测飞行模式、NFC、GPS、蓝牙和自动旋转屏幕的开关状态
"""

import re
import os
import sys
import argparse

def _setup_utf8_stdio() -> None:
    """统一脚本标准输入输出编码为 UTF-8，减少 Windows 终端乱码。"""
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
for _ in range(5):
    _BASE_DIR = os.path.dirname(_BASE_DIR)
_BASE_DIR = os.path.join(_BASE_DIR, "base", "lib")
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)
from repo_paths import resolve_workspace_dir, workspace_analysis, workspace_downloads


def detect_flight_mode(log_content):
    """检测飞行模式状态"""
    # 匹配 mIsAirplaneMode=false 或 mIsAirplaneMode=true
    pattern = r"mIsAirplaneMode=(true|false)"
    matches = re.findall(pattern, log_content, re.IGNORECASE)
    
    if matches:
        status = matches[-1].lower()
        if status == 'true':
            return "开启"
        elif status == 'false':
            return "关闭"
    return "未检测到"


def detect_nfc_status(log_content):
    """检测NFC状态
    
    以最后一次打印的状态为准
    """
    # 匹配新的NFC状态关键字
    pattern = r"TranNfcAllowCardReadController:  setPreferenceEnabled  isEnabled = (true|false)"
    matches = re.findall(pattern, log_content)
    
    if matches:
        # 以最后一次打印的状态为准
        status = matches[-1].lower()
        if status == 'true':
            return "开启"
        elif status == 'false':
            return "关闭"
    return "未检测到"


def detect_gps_status(log_content):
    """检测GPS状态"""
    # 匹配 GpsNetInitiatedHandler: location enabled :false 或 true
    pattern = r"GpsNetInitiatedHandler: location enabled :(true|false)"
    matches = re.findall(pattern, log_content)
    
    if matches:
        status = matches[-1].lower()
        if status == 'true':
            return "开启"
        elif status == 'false':
            return "关闭"
    return "未检测到"


def detect_bluetooth_status(log_content):
    """检测蓝牙状态"""
    # 匹配 BluetoothAdapter: isLeEnabled(): OFF 或 ON
    pattern = r"BluetoothAdapter: isLeEnabled\(\):\s*(ON|OFF)"
    matches = re.findall(pattern, log_content)
    
    if matches:
        status = matches[-1].upper()
        if status == 'ON':
            return "开启"
        elif status == 'OFF':
            return "关闭"
    return "未检测到"


def detect_data_connection_status(log_content):
    """检测数据流量状态
    
    以最后一次打印的状态为准
    """
    # 匹配新的蜂窝网络状态关键字
    pattern = r"TranMccSar: updateStateForDataConnectionChanged: (true|false)"
    matches = re.findall(pattern, log_content)
    
    if matches:
        # 以最后一次打印的状态为准
        status = matches[-1].lower()
        if status == 'true':
            return "开启"
        elif status == 'false':
            return "关闭"
    return "未检测到"


def detect_sim_status(log_content):
    """检测SIM卡状态
    
    以最后一次打印的状态为准
    """
    # 匹配SIM卡状态关键字
    # 收集所有状态变化记录
    status_records = []
    
    # 检查插入状态
    inserted_pattern = r"FIND_SimStateReceiver: SIM inserted"
    inserted_matches = re.findall(inserted_pattern, log_content)
    for match in inserted_matches:
        status_records.append('已插入')
    
    # 检查拔出状态
    unplugged_pattern = r"FIND_SimStateReceiver: SIM unplugged"
    unplugged_matches = re.findall(unplugged_pattern, log_content)
    for match in unplugged_matches:
        status_records.append('未插入')
    
    # 以最后一次状态为准
    if status_records:
        return status_records[-1]
    return "未检测到"


def detect_wifi_status(log_content):
    """检测WIFI状态
    
    以最后一次打印的状态为准
    """
    # 匹配新的WIFI状态关键字
    # 收集所有状态变化记录
    status_records = []
    
    # 检查开启状态
    enable_pattern = r"WifiController: EnabledState.enter()"
    enable_matches = re.findall(enable_pattern, log_content)
    for match in enable_matches:
        status_records.append('开启')
    
    # 检查关闭状态
    disable_pattern = r"WifiController: DisabledState.exit()"
    disable_matches = re.findall(disable_pattern, log_content)
    for match in disable_matches:
        status_records.append('关闭')
    
    # 以最后一次状态为准
    if status_records:
        return status_records[-1]
    return "未检测到"


def detect_auto_rotate_status(log_content):
    """检测自动旋转屏幕状态"""
    # 匹配 Tile.TrRotationLockTile: click rotation, current mState.value=true
    # 注意：关闭是true，打开是false
    pattern = r"Tile\.TrRotationLockTile: click rotation, current mState\.value=(true|false)"
    matches = re.findall(pattern, log_content)
    
    if matches:
        status = matches[-1].lower()
        if status == 'true':
            return "关闭"  # 关闭是true
        elif status == 'false':
            return "开启"  # 打开是false
    return "未检测到"


def detect_brightness(log_content):
    """检测亮度值"""
    # 匹配 TAB.BrightnessCollector: brightness: 255
    pattern = r"TAB\.BrightnessCollector: brightness: (\d+)"
    matches = re.findall(pattern, log_content)
    
    if matches:
        return matches[-1]
    return "未检测到"


def detect_volume_index(log_content):
    """检测音量格数"""
    # 匹配 AudioPolicyInterfaceImpl: setStreamVolumeIndex(), stream 3, index 12, device 0x2
    pattern = r"AudioPolicyInterfaceImpl: setStreamVolumeIndex\(\), stream \d+, index (\d+), device 0x[0-9a-fA-F]+"
    matches = re.findall(pattern, log_content)
    
    if matches:
        return matches[-1]
    return "未检测到"


def extract_preconditions(description):
    """从JIRA描述中提取前置条件
    
    Args:
        description: JIRA单的描述信息
    
    Returns:
        dict: 包含前置条件的字典
    """
    preconditions = {
        "飞行模式": "未检测到",
        "数据流量": "未检测到",
        "WIFI": "未检测到",
        "蓝牙": "未检测到",
        "GPS": "未检测到",
        "NFC": "未检测到",
        "SIM卡": "未检测到",
        "自动旋转屏幕": "未检测到",
        "亮度等级": "未检测到",
        "音量等级": "未检测到"
    }
    
    # 提取A)Preconditions部分
    precondition_pattern = r"A\)Preconditions：(.*?)(B\)|$)"
    matches = re.search(precondition_pattern, description, re.DOTALL)
    
    if matches:
        precondition_text = matches.group(1)
        print(f"提取到前置条件文本: {precondition_text}")
        
        # 解析各项设置
        if "数据流量（默认设定开）" in precondition_text or "数据（开）" in precondition_text:
            preconditions["数据流量"] = "开启"
        elif "数据流量（默认设定关）" in precondition_text or "数据（关）" in precondition_text:
            preconditions["数据流量"] = "关闭"
        
        if "WIFI(开启并连接AP)" in precondition_text or "WIFI（开）" in precondition_text:
            preconditions["WIFI"] = "开启"
        elif "WIFI（关）" in precondition_text:
            preconditions["WIFI"] = "关闭"
        
        if "蓝牙（开启并连接蓝牙耳机）" in precondition_text or "蓝牙（开）" in precondition_text:
            preconditions["蓝牙"] = "开启"
        elif "蓝牙（关）" in precondition_text:
            preconditions["蓝牙"] = "关闭"
        
        if "GPS(默认设定开)" in precondition_text or "GPS（开）" in precondition_text:
            preconditions["GPS"] = "开启"
        elif "GPS（关）" in precondition_text:
            preconditions["GPS"] = "关闭"
        
        if "NFC (默认设定开)" in precondition_text or "NFC（开）" in precondition_text:
            preconditions["NFC"] = "开启"
        elif "NFC（关）" in precondition_text:
            preconditions["NFC"] = "关闭"
        
        if "飞行模式（默认设定开）" in precondition_text or "飞行模式（开）" in precondition_text:
            preconditions["飞行模式"] = "开启"
        elif "飞行模式（默认设定关）" in precondition_text or "飞行模式（关）" in precondition_text:
            preconditions["飞行模式"] = "关闭"
        
        if "插入一张SIM卡" in precondition_text or "插USIM卡" in precondition_text:
            preconditions["SIM卡"] = "已插入"
        
        if "自动旋转屏幕（默认设定自动）" in precondition_text or "自动旋转（开）" in precondition_text:
            preconditions["自动旋转屏幕"] = "开启"
        elif "自动旋转（关）" in precondition_text:
            preconditions["自动旋转屏幕"] = "关闭"
        elif "关闭双击亮屏和AOD" in precondition_text:
            # 这里可能需要更具体的解析，暂时标记为未检测到
            pass
    
    return preconditions


def compare_preconditions(actual_status, expected_preconditions):
    """比较实际检测结果与预期前置条件
    
    Args:
        actual_status: 实际检测到的设备状态
        expected_preconditions: 从JIRA中提取的预期前置条件
    
    Returns:
        tuple: (是否满足前置条件, 不满足的项列表)
    """
    not_matching = []
    
    for key in expected_preconditions:
        expected = expected_preconditions[key]
        actual = actual_status[key]
        
        # 只比较有明确预期的项
        if expected != "未检测到":
            # 对于亮度和音量，可能需要特殊处理
            if key in ["亮度等级", "音量等级"]:
                # 暂时只检查是否检测到，不做具体值的比较
                if actual == "未检测到":
                    not_matching.append(f"{key}: 预期={expected}, 实际={actual}")
            else:
                if actual != expected:
                    not_matching.append(f"{key}: 预期={expected}, 实际={actual}")
    
    return len(not_matching) == 0, not_matching


def save_result(workspace_dir, result, actual_status, expected_preconditions, not_matching):
    """保存前置条件检查结果到文件
    
    Args:
        workspace_dir: temp 工作区根目录（temp/<DATE>/<KEY>）
        result: 检查结果（True/False）
        actual_status: 实际检测到的设备状态
        expected_preconditions: 从JIRA中提取的预期前置条件
        not_matching: 不满足的项列表
    
    Returns:
        str: 保存的文件路径
    """
    analysis_dir = workspace_analysis(workspace_dir)
    report_file = os.path.join(analysis_dir, "precondition_check_result.txt")
    
    # 生成报告内容
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("=== 前置条件检查报告 ===\n")
        f.write(f"检查结果: {'前置条件满足' if result else '前置条件不满足'}\n\n")
        
        f.write("=== 预期前置条件 ===\n")
        for key, value in expected_preconditions.items():
            if value != "未检测到":
                f.write(f"{key}: {value}\n")
        f.write("\n")
        
        f.write("=== 实际检测结果 ===\n")
        # 只显示预期前置条件中提到的项目
        for key, value in expected_preconditions.items():
            if value != "未检测到":
                f.write(f"{key}: {actual_status.get(key, '未检测到')}\n")
        f.write("\n")
        
        if not_matching:
            f.write("=== 不满足的项 ===\n")
            for item in not_matching:
                f.write(f"{item}\n")
        else:
            f.write("=== 所有项均满足 ===\n")
    
    print(f"报告已保存到: {report_file}")
    return report_file


def merge_mainlog_files(mainlog_files):
    """合并多个mainlog文件的内容，按文件修改时间排序
    
    Args:
        mainlog_files: mainlog 文件路径列表
    
    Returns:
        str: 合并后的日志内容
    """
    # 按文件修改时间排序，最新的文件在最后
    mainlog_files.sort(key=lambda x: os.path.getmtime(x))
    
    merged_content = ""
    for file_path in mainlog_files:
        try:
            # 尝试以不同编码读取文件
            encodings = ['utf-8', 'utf-16', 'gbk', 'ansi']
            content = ""
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                        content = f.read()
                    # 如果成功读取且内容不为空，就使用这个编码
                    if content:
                        break
                except:
                    continue
            
            # 如果所有编码都失败，尝试以二进制模式读取并转换
            if not content:
                with open(file_path, 'rb') as f:
                    binary_content = f.read()
                # 尝试解码，忽略错误
                content = binary_content.decode('utf-8', errors='ignore')
            
            merged_content += content
            merged_content += "\n"  # 添加分隔符
        except Exception as e:
            print(f"读取 mainlog 文件 {file_path} 时出错: {e}")
    
    # 清理内容，移除空字节和多余的空白字符
    merged_content = merged_content.replace('\x00', '')
    
    # 保存合并后的内容到文件
    if merged_content and mainlog_files:
        merged_file_path = os.path.join(os.path.dirname(mainlog_files[0]), "merged_mainlog.txt")
        try:
            with open(merged_file_path, 'w', encoding='utf-8') as f:
                f.write(merged_content)
            print(f"合并后的日志已保存到: {merged_file_path}")
        except Exception as e:
            print(f"保存合并日志文件时出错: {e}")
    
    return merged_content


def detect_device_status(mainlog_path_or_content):
    """检测设备状态
    
    Args:
        mainlog_path_or_content: mainlog 文件的路径或合并后的日志内容
    
    Returns:
        dict: 包含各状态检测结果的字典
    """
    log_content = ""
    
    # 检查输入是文件路径还是直接的内容
    if isinstance(mainlog_path_or_content, str):
        if os.path.exists(mainlog_path_or_content):
            # 是文件路径
            try:
                with open(mainlog_path_or_content, 'r', encoding='utf-8', errors='ignore') as f:
                    log_content = f.read()
            except Exception as e:
                print(f"读取 mainlog 文件时出错: {e}")
                return {
                    "飞行模式": "未检测到",
                    "数据流量": "未检测到",
                    "WIFI": "未检测到",
                    "蓝牙": "未检测到",
                    "GPS": "未检测到",
                    "NFC": "未检测到",
                    "SIM卡": "未检测到",
                    "自动旋转屏幕": "未检测到",
                    "亮度等级": "未检测到",
                    "音量等级": "未检测到"
                }
        else:
            # 是直接的内容
            log_content = mainlog_path_or_content
    
    if not log_content:
        return {
            "飞行模式": "未检测到",
            "数据流量": "未检测到",
            "WIFI": "未检测到",
            "蓝牙": "未检测到",
            "GPS": "未检测到",
            "NFC": "未检测到",
            "SIM卡": "未检测到",
            "自动旋转屏幕": "未检测到",
            "亮度等级": "未检测到",
            "音量等级": "未检测到"
        }
    
    brightness = detect_brightness(log_content)
    volume = detect_volume_index(log_content)
    
    return {
        "飞行模式": detect_flight_mode(log_content),
        "数据流量": detect_data_connection_status(log_content),
        "WIFI": detect_wifi_status(log_content),
        "蓝牙": detect_bluetooth_status(log_content),
        "GPS": detect_gps_status(log_content),
        "NFC": detect_nfc_status(log_content),
        "SIM卡": detect_sim_status(log_content),
        "自动旋转屏幕": detect_auto_rotate_status(log_content),
        "亮度等级": f"brightnrss={brightness}" if brightness != "未检测到" else "未检测到",
        "音量等级": f"index={volume}" if volume != "未检测到" else "未检测到"
    }


def find_and_detect_mainlog(folder_path, scenario='system_baseline'):
    """在文件夹中递归查找 mainlog 文件并检测设备状态
    
    Args:
        folder_path: 要搜索的文件夹路径
        scenario: 测试场景，可选值：system_baseline（系统基础功耗）、basic_experience（基础体验场景）、nps_bad（NPS差评模式）
    
    Returns:
        dict: 包含检测结果和找到的 mainlog 文件路径
    """
    # 递归查找 mainlog 文件
    mainlog_files = []
    
    try:
        print(f"开始搜索 mainlog 文件，搜索路径: {folder_path}")
        print(f"路径是否存在: {os.path.exists(folder_path)}")
        print(f"是否是文件夹: {os.path.isdir(folder_path)}")
        print(f"测试场景: {scenario}")
        
        for root, dirs, files in os.walk(folder_path):
            print(f"搜索目录: {root}")
            print(f"找到文件: {files}")
            for file in files:
                if 'mainlog' in file.lower() or 'main_log' in file.lower():
                    mainlog_files.append(os.path.join(root, file))
                    print(f"找到匹配文件: {os.path.join(root, file)}")
        
        print(f"搜索完成，找到 {len(mainlog_files)} 个匹配文件")
    except Exception as e:
        print(f"搜索 mainlog 文件时出错: {e}")
        return {
            "success": False,
            "message": f"搜索 mainlog 文件时出错: {e}",
            "mainlog_path": None,
            "status": {
                "飞行模式": "未检测到",
                "数据流量": "未检测到",
                "WIFI": "未检测到",
                "蓝牙": "未检测到",
                "GPS": "未检测到",
                "NFC": "未检测到",
                "自动旋转屏幕": "未检测到",
                "亮度等级": "未检测到",
                "音量等级": "未检测到"
            }
        }
    
    if not mainlog_files:
        return {
            "success": False,
            "message": "未找到 mainlog 文件",
            "mainlog_path": None,
            "status": {
                "飞行模式": "未检测到",
                "数据流量": "未检测到",
                "WIFI": "未检测到",
                "蓝牙": "未检测到",
                "GPS": "未检测到",
                "NFC": "未检测到",
                "自动旋转屏幕": "未检测到",
                "亮度等级": "未检测到",
                "音量等级": "未检测到"
            }
        }
    
    # 处理多个mainlog文件的情况
    if len(mainlog_files) > 1:
        print(f"找到 {len(mainlog_files)} 个 mainlog 文件，按时间顺序合并后检测")
        # 合并多个mainlog文件
        merged_content = merge_mainlog_files(mainlog_files)
        status = detect_device_status(merged_content)
        mainlog_path = f"多个文件合并 ({len(mainlog_files)} 个)"
    else:
        # 只有一个mainlog文件的情况
        mainlog_path = mainlog_files[0]
        status = detect_device_status(mainlog_path)
    
    # 根据场景添加特定的检测逻辑（如果需要）
    if scenario == 'system_baseline':
        print("执行系统基础功耗场景检测")
    elif scenario == 'basic_experience':
        print("执行基础体验场景检测")
    elif scenario == 'nps_bad':
        print("执行NPS差评模式检测")
    
    return {
        "success": True,
        "message": f"找到 {len(mainlog_files)} 个 mainlog 文件: {mainlog_path}",
        "mainlog_path": mainlog_path,
        "status": status
    }


def main():
    """主函数"""
    _setup_utf8_stdio()
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="检测设备状态并与JIRA前置条件对比")
    parser.add_argument("description", help="JIRA单的描述信息")
    parser.add_argument("save_dir", help="保存目录")
    args = parser.parse_args()
    
    description = args.description
    save_dir = args.save_dir
    
    print(f"开始前置条件检查，保存目录: {save_dir}")
    
    # 1. 提取JIRA前置条件
    expected_preconditions = extract_preconditions(description)
    print("\n=== 预期前置条件 ===")
    for key, value in expected_preconditions.items():
        if value != "未检测到":
            print(f"{key}: {value}")
    
    # 2. 查找并检测mainlog文件（默认在 temp/.../downloads/）
    workspace_dir = resolve_workspace_dir(save_dir)
    resources_path = workspace_downloads(workspace_dir)
    detection_result = find_and_detect_mainlog(resources_path)
    
    if not detection_result["success"]:
        print(f"错误: {detection_result['message']}")
        # 即使找不到mainlog文件，也保存结果
        actual_status = detection_result["status"]
        result = False
        not_matching = ["未找到mainlog文件，无法检测设备状态"]
    else:
        actual_status = detection_result["status"]
        print("\n=== 实际检测结果 ===")
        # 只显示预期前置条件中提到的项目
        for key, value in expected_preconditions.items():
            if value != "未检测到":
                print(f"{key}: {actual_status.get(key, '未检测到')}")
        
        # 3. 比较实际状态与预期前置条件
        result, not_matching = compare_preconditions(actual_status, expected_preconditions)
    
    # 4. 保存结果
    save_result(workspace_dir, result, actual_status, expected_preconditions, not_matching)
    
    # 5. 输出检查结果
    print("\n=== 前置条件检查结果 ===")
    if result:
        print("前置条件满足")
    else:
        print("前置条件不满足")
        if not_matching:
            print("不满足的项:")
            for item in not_matching:
                print(f"- {item}")
    print("=======================")


if __name__ == "__main__":
    main()