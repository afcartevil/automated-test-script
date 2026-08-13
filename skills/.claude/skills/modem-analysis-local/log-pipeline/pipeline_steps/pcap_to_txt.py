#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import json
import logging
import os
import subprocess
import sys
import winreg
from copy import deepcopy
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


DEFAULT_MANIFEST = {
    "issue_key": "",
    "workspace_root": "",
    "extraction": {
        "normalized_log_roots": [],
    },
    "pcap_exports": {
        "results": [],
    },
}


def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )


def merge_defaults(target, defaults):
    for key, value in defaults.items():
        if key not in target:
            target[key] = deepcopy(value)
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            merge_defaults(target[key], value)
    return target


def load_manifest(path):
    if not path or not os.path.exists(path):
        return deepcopy(DEFAULT_MANIFEST)
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"manifest format is invalid: {path}")
    return merge_defaults(data, deepcopy(DEFAULT_MANIFEST))


def save_manifest(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    data = merge_defaults(data, deepcopy(DEFAULT_MANIFEST))
    data["_meta"] = {"updated_at": datetime.now().isoformat(timespec="seconds")}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_wireshark_path():
    """从注册表或环境变量获取 Wireshark 路径"""
    # 优先使用环境变量
    env_path = os.environ.get("WIRESHARK_PATH")
    if env_path and os.path.isdir(env_path):
        tshark = os.path.join(env_path, "tshark.exe")
        if os.path.isfile(tshark):
            return env_path
    
    # 搜索注册表
    reg_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r'Software\Wireshark'),
        (winreg.HKEY_LOCAL_MACHINE, r'Software\WOW6432Node\Wireshark'),
        (winreg.HKEY_CURRENT_USER, r'Software\Wireshark'),
    ]
    
    for hkey, subpath in reg_paths:
        try:
            key = winreg.OpenKey(hkey, subpath, 0, winreg.KEY_READ)
            try:
                path, _ = winreg.QueryValueEx(key, 'Path')
            except:
                path, _ = winreg.QueryValueEx(key, 'InstallLocation')
            winreg.CloseKey(key)
            if path and os.path.isdir(path):
                return path
        except:
            continue
    
    return None


def find_pcap_files(input_path):
    """递归查找所有 pcap/pcapng/cap 文件"""
    pcap_files = []
    if not os.path.exists(input_path):
        return pcap_files
    
    for root, _, files in os.walk(input_path):
        for file in files:
            if file.lower().endswith(('.pcap', '.pcapng', '.cap')):
                pcap_files.append(os.path.join(root, file))
    
    return pcap_files


def convert_pcap_to_txt(pcap_file, tshark_path, logger):
    """将单个 pcap 文件转换为 txt，每个数据包一行，包含详细协议信息"""
    # 生成输出 txt 文件路径
    base_name = os.path.basename(pcap_file)
    name_without_ext, ext = os.path.splitext(base_name)
    new_base_name = f"{name_without_ext}{ext.replace('.', '_')}.txt"
    txt_file = os.path.join(os.path.dirname(pcap_file), new_base_name)
    
    # 构建 tshark 命令
    # 过滤器：排除 SLL，只保留关键协议用于网络性能分析
    display_filter = (
        "tcp or udp or icmp or "
        "nas-eps or nas-5gs or "
        "rrc or pdcp-lte or pdcp-nr or rlc-lte or rlc-nr or "
        "gtp or gtpv2 or "
        "dns or http or http2 or quic"
    )
    
    # 使用 -V 输出详细协议树，然后通过 Python 处理合并成一行
    # -t ad: 显示绝对日期和时间
    # -P: 即使使用 -V 也打印摘要行
    # -V: 显示详细的协议树
    command = [
        tshark_path, '-r', pcap_file, 
        '-Y', display_filter, 
        '-t', 'ad', 
        '-P', '-V'
    ]
    
    logger.info(f"Converting: {os.path.basename(pcap_file)} -> {os.path.basename(txt_file)}")
    
    try:
        # 执行命令并将输出重定向到 txt 文件
        with open(txt_file, 'w', encoding='utf-8') as f:
            result = subprocess.run(
                command, 
                stdout=f, 
                stderr=subprocess.PIPE, 
                check=True,
                timeout=300  # 5 分钟超时
            )
        
        file_size = os.path.getsize(txt_file) if os.path.exists(txt_file) else 0
        logger.info(f"Conversion succeeded: {txt_file} ({file_size} bytes)")
        
        return {
            "pcap_file": pcap_file,
            "txt_file": txt_file,
            "status": "success",
            "file_size": file_size
        }
    
    except subprocess.TimeoutExpired:
        logger.error(f"Conversion timeout: {pcap_file}")
        return {
            "pcap_file": pcap_file,
            "txt_file": txt_file,
            "status": "timeout",
            "error": "Conversion timeout after 5 minutes"
        }
    
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        logger.error(f"Conversion failed: {pcap_file}, error: {error_msg}")
        return {
            "pcap_file": pcap_file,
            "txt_file": txt_file,
            "status": "failed",
            "error": error_msg
        }
    
    except Exception as e:
        logger.error(f"Conversion failed: {pcap_file}, error: {e}")
        return {
            "pcap_file": pcap_file,
            "txt_file": txt_file,
            "status": "failed",
            "error": str(e)
        }


def process_pcap_exports(manifest_path):
    """处理 PCAP 导出的主函数"""
    logger = logging.getLogger("pcap-export")
    
    # 加载 manifest
    manifest = load_manifest(manifest_path)
    normalized_roots = manifest.get("extraction", {}).get("normalized_log_roots", [])
    
    if not normalized_roots:
        logger.warning("No normalized_log_roots found in manifest, skipping pcap export")
        manifest["pcap_exports"]["results"] = []
        save_manifest(manifest_path, manifest)
        return 0
    
    # 获取 Wireshark 路径
    wireshark_path = get_wireshark_path()
    if not wireshark_path:
        logger.warning("Wireshark not found, skipping pcap export")
        manifest["pcap_exports"]["results"] = []
        save_manifest(manifest_path, manifest)
        return 0
    
    tshark_path = os.path.join(wireshark_path, 'tshark.exe')
    if not os.path.isfile(tshark_path):
        logger.warning(f"tshark.exe not found at: {tshark_path}, skipping pcap export")
        manifest["pcap_exports"]["results"] = []
        save_manifest(manifest_path, manifest)
        return 0
    
    logger.info(f"Using tshark: {tshark_path}")
    
    # 查找所有 pcap 文件
    all_pcap_files = []
    for root_dir in normalized_roots:
        if not os.path.exists(root_dir):
            logger.warning(f"Root directory not found: {root_dir}")
            continue
        pcap_files = find_pcap_files(root_dir)
        all_pcap_files.extend(pcap_files)
        logger.info(f"Found {len(pcap_files)} pcap files in {root_dir}")
    
    if not all_pcap_files:
        logger.warning("No pcap files found in any normalized_log_roots")
        manifest["pcap_exports"]["results"] = []
        save_manifest(manifest_path, manifest)
        return 0
    
    logger.info(f"Total pcap files to convert: {len(all_pcap_files)}")
    
    # 转换所有 pcap 文件
    results = []
    for pcap_file in all_pcap_files:
        result = convert_pcap_to_txt(pcap_file, tshark_path, logger)
        results.append(result)
    
    # 更新 manifest
    manifest["pcap_exports"]["results"] = results
    save_manifest(manifest_path, manifest)
    
    # 统计结果
    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = len(results) - success_count
    
    logger.info(f"PCAP export completed: {success_count} succeeded, {failed_count} failed")
    
    return 0


def export_pcap_to_txt(manifest_path):
    """
    导出 PCAP 文件为 TXT 格式（供 pipeline 调用）
    
    Args:
        manifest_path: manifest 文件路径
    
    Returns:
        dict: 导出结果
    """
    configure_logging()
    return process_pcap_exports(manifest_path)


def main():
    configure_logging()
    logger = logging.getLogger("pcap-export")
    
    parser = argparse.ArgumentParser(description="Export PCAP files to TXT format")
    parser.add_argument("--manifest", required=True, help="Path to manifest JSON file")
    args = parser.parse_args()
    
    try:
        return process_pcap_exports(args.manifest)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
