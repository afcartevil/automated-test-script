#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从编译快照获取 Gerrit 项目信息

步骤：
1. 根据版本号在版本服务器上查找版本目录
2. 读取 releasenote.json 获取 odm snapshot
3. 读取 snapshot 文件获取 modem 项目的 project、branch、commit id
"""

import argparse
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path


VERSION_SERVER_ROOTS = [
    r"\\10.150.98.24\sw_ver_sh",
    r"\\10.150.98.24\sw_ver",
]

BRANDS = ["INFINIX", "TECNO", "itel"]


def normalize_version(version_string):
    version = version_string.strip()
    suffixes = ['FANS', '_user_fans', '_user', '_debug']
    for suffix in suffixes:
        if version.endswith(suffix):
            version = version[:-len(suffix)]
    return version


def extract_project_name(version_string):
    normalized = normalize_version(version_string)
    if '-' in normalized:
        return normalized.split('-')[0]
    return None


def extract_version_number(version_string):
    """
    从版本号中提取版本数字部分
    
    例如: X6891-16.1.0.115(OP001PF001AZ) -> 16.1.0.115
    """
    normalized = normalize_version(version_string)
    match = re.search(r'(\d+\.\d+\.\d+\.\d+)', normalized)
    if match:
        return match.group(1)
    return None


def find_project_folders_fast(brand_path, project_name):
    found = []
    exact = brand_path / project_name
    if exact.exists() and exact.is_dir():
        found.append(exact)
    try:
        for d in brand_path.glob(project_name + "-*"):
            if d.is_dir() and d not in found:
                found.append(d)
    except Exception:
        pass
    return found


def find_version_directory(version_string, logger=None):
    """
    根据版本号查找版本目录
    
    返回: (version_dir_path, brand) 或 (None, None)
    """
    project_name = extract_project_name(version_string)
    version_number = extract_version_number(version_string)
    
    if not project_name:
        if logger:
            logger.warning("无法从版本号提取项目名称: %s", version_string)
        return None, None
    
    if not version_number:
        if logger:
            logger.warning("无法从版本号提取版本数字: %s", version_string)
        return None, None
    
    if logger:
        logger.info("项目名称: %s, 版本数字: %s", project_name, version_number)
    
    for server_root in VERSION_SERVER_ROOTS:
        server_path = Path(server_root)
        if not server_path.exists():
            continue
        
        for brand in BRANDS:
            brand_path = server_path / brand
            if not brand_path.exists():
                continue
            
            project_folders = find_project_folders_fast(brand_path, project_name)
            for project_folder in project_folders:
                test_path = project_folder / "TEST"
                if not test_path.exists():
                    continue
                
                try:
                    for version_dir in test_path.iterdir():
                        if not version_dir.is_dir():
                            continue
                        
                        if version_number in version_dir.name:
                            if logger:
                                logger.info("找到版本目录: %s", version_dir)
                            return version_dir, brand
                except Exception as e:
                    if logger:
                        logger.debug("遍历目录出错 %s: %s", test_path, e)
    
    return None, None


def read_releasenote(version_dir, logger=None):
    """
    读取 releasenote.json 获取 odm snapshot 信息
    
    返回: dict 或 None
    """
    releasenote_path = version_dir / "releasenote.json"
    
    if not releasenote_path.exists():
        if logger:
            logger.warning("releasenote.json 不存在: %s", releasenote_path)
        return None
    
    try:
        with open(releasenote_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if logger:
            logger.info("读取 releasenote.json 成功")
        
        return data
    except Exception as e:
        if logger:
            logger.error("读取 releasenote.json 失败: %s", e)
        return None


def get_odm_snapshot_from_releasenote(releasenote, logger=None):
    """
    从 releasenote 中获取 odm snapshot 名称
    
    返回: snapshot 名称或 None
    """
    if not releasenote:
        return None
    
    component_info = releasenote.get("component_info", {})
    odm_info = component_info.get("odm", {})
    snapshot = odm_info.get("snapshot")
    
    if snapshot and logger:
        logger.info("ODM snapshot: %s", snapshot)
    
    return snapshot


def read_snapshot_file(version_dir, snapshot_name=None, logger=None):
    """
    读取 snapshot 文件
    
    返回: 文件内容或 None
    """
    if snapshot_name:
        snapshot_path = version_dir / snapshot_name
    else:
        snapshot_path = version_dir / "snapshot"
    
    if not snapshot_path.exists():
        if logger:
            logger.warning("snapshot 文件不存在: %s", snapshot_path)
        return None
    
    try:
        with open(snapshot_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if logger:
            logger.info("读取 snapshot 文件成功: %s", snapshot_path)
        
        return content
    except Exception as e:
        if logger:
            logger.error("读取 snapshot 文件失败: %s", e)
        return None


def parse_modem_info_from_snapshot(snapshot_content, logger=None):
    """
    从 snapshot 内容解析 modem 项目信息
    
    示例行：
    <project groups="transsion_vnd,transsion_vnd_codebase" 
            name="TRAN_V/vendor/mediatek/proprietary/modem" 
            path="vendor/mediatek/proprietary/modem" 
            revision="53d4ff6cde882c1a3b25897753e5af99c61912a4" 
            upstream="tOS16.2.0_mtk_A15_vnd_release"/>
    
    返回: dict {project, branch, commit} 或 None
    """
    if not snapshot_content:
        return None
    
    try:
        root = ET.fromstring(f"<root>{snapshot_content}</root>")
    except ET.ParseError:
        root = ET.fromstring(snapshot_content)
    
    for project in root.findall(".//project"):
        name = project.get("name", "")
        
        if "vendor/mediatek/proprietary/modem" in name:
            result = {
                "project": name,
                "branch": project.get("upstream"),
                "commit": project.get("revision"),
                "path": project.get("path", ""),
            }
            
            if logger:
                logger.info("找到 modem 项目信息:")
                logger.info("  project: %s", result["project"])
                logger.info("  branch: %s", result["branch"])
                logger.info("  commit: %s", result["commit"])
            
            return result
    
    if logger:
        logger.warning("未找到 modem 项目信息")
    
    return None


def get_modem_info_from_version(version_string, logger=None):
    """
    根据版本号获取 modem 项目信息
    
    返回: dict {project, branch, commit} 或 None
    """
    version_dir, brand = find_version_directory(version_string, logger)
    
    if not version_dir:
        if logger:
            logger.error("未找到版本目录: %s", version_string)
        return None
    
    releasenote = read_releasenote(version_dir, logger)
    snapshot_name = get_odm_snapshot_from_releasenote(releasenote, logger)
    
    snapshot_content = read_snapshot_file(version_dir, snapshot_name, logger)
    
    if not snapshot_content:
        if logger:
            logger.error("无法读取 snapshot 文件")
        return None
    
    return parse_modem_info_from_snapshot(snapshot_content, logger)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("snapshot-parser")
    
    parser = argparse.ArgumentParser(description="从编译快照获取 Gerrit 项目信息")
    parser.add_argument("--version", required=True, help="版本号，如 X6891-16.1.0.115(OP001PF001AZ)")
    parser.add_argument("--output", help="输出 JSON 文件路径（可选）")
    args = parser.parse_args()
    
    logger.info("版本号: %s", args.version)
    
    result = get_modem_info_from_version(args.version, logger)
    
    if result:
        output = {
            "version": args.version,
            "modem": result,
        }
        
        logger.info("\n结果:")
        logger.info(json.dumps(output, indent=2, ensure_ascii=False))
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            logger.info("结果已保存到: %s", args.output)
        
        return 0
    else:
        logger.error("获取 modem 信息失败")
        return 1


if __name__ == "__main__":
    exit(main())
