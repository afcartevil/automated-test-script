#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 Gerrit 或 MTK 版本服务器获取 MDDB 符号表文件

优先使用 Gerrit REST API 下载（快速、稳定），失败时回退到版本服务器。
"""

import argparse
import base64
import fnmatch
import json
import logging
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


DEFAULT_MANIFEST = {
    "issue_key": "",
    "workspace_root": "",
    "jira": {
        "affected_versions": [],
    },
    "extraction": {
        "filter_results": [],
    },
    "mddb_fetch": {
        "results": [],
    },
}

VERSION_SERVER_ROOTS = [
    r"\\10.150.98.24\sw_ver_sh",
    r"\\10.150.98.24\sw_ver",
]

BRANDS = ["INFINIX", "TECNO", "itel"]


def configure_stdio():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


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
        raise ValueError(f"manifest 格式错误: {path}")
    return merge_defaults(data, deepcopy(DEFAULT_MANIFEST))


def save_manifest(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    data = merge_defaults(data, deepcopy(DEFAULT_MANIFEST))
    data["_meta"] = {"updated_at": datetime.now().isoformat(timespec="seconds")}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_env(env_path=None):
    """从 .env 文件加载环境变量"""
    if env_path is None:
        project_root = Path(__file__).parent.parent
        env_path = project_root / ".env"
    
    env = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env[key.strip()] = value.strip()
    return env


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
    project_name = extract_project_name(version_string)
    version_number = extract_version_number(version_string)
    
    if not project_name or not version_number:
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
    if not releasenote:
        return None
    
    component_info = releasenote.get("component_info", {})
    odm_info = component_info.get("odm", {})
    snapshot = odm_info.get("snapshot")
    
    if snapshot and logger:
        logger.info("ODM snapshot: %s", snapshot)
    
    return snapshot


def read_snapshot_file(version_dir, snapshot_name, logger=None):
    snapshot_path = version_dir / snapshot_name
    
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
    
    return None


def get_modem_info_from_version(version_string, logger=None):
    version_dir, brand = find_version_directory(version_string, logger)
    
    if not version_dir:
        if logger:
            logger.error("未找到版本目录: %s", version_string)
        return None
    
    releasenote = read_releasenote(version_dir, logger)
    snapshot_name = get_odm_snapshot_from_releasenote(releasenote, logger)
    
    if not snapshot_name:
        if logger:
            logger.error("无法获取 ODM snapshot 名称")
        return None
    
    snapshot_content = read_snapshot_file(version_dir, snapshot_name, logger)
    
    if not snapshot_content:
        if logger:
            logger.error("无法读取 snapshot 文件")
        return None
    
    return parse_modem_info_from_snapshot(snapshot_content, logger)


class GerritClient:
    """Gerrit REST API 客户端"""
    
    def __init__(self, url, username, password):
        self.url = url.rstrip('/')
        self.username = username
        self.password = password
        self._rest = None
        self.logger = logging.getLogger("mddb-fetcher.gerrit")
    
    @property
    def rest(self):
        if self._rest is None:
            try:
                from pygerrit2 import GerritRestAPI, HTTPBasicAuth
                self._rest = GerritRestAPI(
                    url=self.url,
                    auth=HTTPBasicAuth(self.username, self.password)
                )
            except ImportError:
                self.logger.error("请安装 pygerrit2: pip install pygerrit2")
                raise
        return self._rest
    
    def get_commit_info(self, project, commit):
        encoded_project = quote(project, safe='')
        endpoint = f'/projects/{encoded_project}/commits/{commit}'
        return self.rest.get(endpoint)
    
    def get_parent_commit(self, project, commit):
        try:
            commit_info = self.get_commit_info(project, commit)
            parents = commit_info.get('parents', [])
            if parents:
                return parents[0].get('commit')
        except Exception as e:
            self.logger.debug("获取 parent commit 失败: %s", e)
        return None
    
    def get_file_from_commit(self, project, commit, file_path):
        encoded_project = quote(project, safe='')
        encoded_file = quote(file_path, safe='')
        endpoint = f'/projects/{encoded_project}/commits/{commit}/files/{encoded_file}/content'
        return self.rest.get(endpoint)
    
    def list_files_in_commit(self, project, commit):
        encoded_project = quote(project, safe='')
        endpoint = f'/projects/{encoded_project}/commits/{commit}/files/'
        return self.rest.get(endpoint)
    
    def download_file_from_commit(self, project, commit, file_path, output_path):
        try:
            content = self.get_file_from_commit(project, commit, file_path)
            if content:
                if isinstance(content, str):
                    data = content.encode('latin-1')
                else:
                    data = content
                os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(data)
                return len(data)
        except Exception as e:
            self.logger.error("下载文件失败 %s: %s", file_path, e)
        return 0


class GerritMddbFetcher:
    """从 Gerrit 仓库获取 MDDB 符号表（优先方式）"""
    
    def __init__(self, version_string, env=None):
        self.version_string = version_string.strip()
        self.project_name = extract_project_name(version_string)
        self.env = env or load_env()
        self.logger = logging.getLogger("mddb-fetcher.gerrit")
        
        self.gerrit_url = self.env.get("GERRIT_URL", "https://gerrit.transsion.com")
        self.gerrit_username = self.env.get("GERRIT_USERNAME", "")
        self.gerrit_password = self.env.get("GERRIT_PASSWORD", "")
        
        self.modem_info = None
    
    def _get_modem_info(self):
        if self.modem_info is None:
            self.modem_info = get_modem_info_from_version(self.version_string, self.logger)
        return self.modem_info
    
    def fetch_to_dir(self, output_dir):
        if not self.project_name:
            self.logger.warning("无法从版本号提取项目名称: %s", self.version_string)
            return []
        
        if not self.gerrit_username or not self.gerrit_password:
            self.logger.warning("未配置 Gerrit 凭据，跳过 Gerrit 获取")
            return []
        
        modem_info = self._get_modem_info()
        if not modem_info:
            self.logger.warning("无法从编译快照获取 modem 信息")
            return []
        
        project = modem_info.get("project")
        start_commit = modem_info.get("commit")
        
        if not project or not start_commit:
            self.logger.warning("modem 信息缺少 project 或 commit")
            return []
        
        self.logger.info("从 Gerrit 获取 MDDB: project=%s, start_commit=%s", project, start_commit[:8])
        
        file_patterns = [
            f"{self.project_name.lower()}*/*.EDB",
            f"{self.project_name.lower()}*/*.edb",
            f"{self.project_name}*/*.EDB",
            f"{self.project_name}*/*.edb",
        ]
        
        try:
            client = GerritClient(self.gerrit_url, self.gerrit_username, self.gerrit_password)
            
            current_commit = start_commit
            visited = set()
            found_files = {}
            depth = 0
            max_depth = 100
            
            self.logger.info("开始遍历 commit 历史查找 MDDB 文件...")
            
            while current_commit and current_commit not in visited and depth < max_depth:
                visited.add(current_commit)
                depth += 1
                
                self.logger.info("[%d] 检查 commit: %s", depth, current_commit[:8])
                
                files = client.list_files_in_commit(project, current_commit)
                if not files:
                    self.logger.debug("commit 下没有文件")
                    parent = client.get_parent_commit(project, current_commit)
                    if parent:
                        self.logger.debug("继续向上 (parent: %s)", parent[:8])
                        current_commit = parent
                    else:
                        self.logger.info("已到达根 commit，停止遍历")
                        break
                    continue
                
                matched = []
                for file_path in files.keys():
                    if file_path == '/COMMIT_MSG':
                        continue
                    for pattern in file_patterns:
                        if fnmatch.fnmatch(file_path, pattern):
                            matched.append(file_path)
                            break
                
                if matched:
                    self.logger.info("找到 %d 个匹配文件!", len(matched))
                    for f in matched:
                        if f not in found_files:
                            found_files[f] = current_commit
                            self.logger.info("  - %s", f)
                    break
                
                parent = client.get_parent_commit(project, current_commit)
                if parent:
                    self.logger.debug("继续向上 (parent: %s)", parent[:8])
                    current_commit = parent
                else:
                    self.logger.info("已到达根 commit，停止遍历")
                    break
            
            self.logger.info("遍历完成! 共检查 %d 个 commit", depth)
            
            if not found_files:
                self.logger.warning("未找到匹配的 MDDB 文件: %s", file_patterns)
                return []
            
            os.makedirs(output_dir, exist_ok=True)
            extracted_files = []
            
            for file_path, commit_hash in found_files.items():
                filename = os.path.basename(file_path)
                dst_path = os.path.join(output_dir, filename)
                
                self.logger.info("下载: %s (from %s)", file_path, commit_hash[:8])
                size = client.download_file_from_commit(project, commit_hash, file_path, dst_path)
                
                if size > 0:
                    size_mb = size / (1024 * 1024)
                    self.logger.info("下载成功: %s (%.2f MB)", filename, size_mb)
                    extracted_files.append(filename)
                else:
                    self.logger.warning("下载失败: %s", file_path)
            
            return extracted_files
        
        except Exception as e:
            self.logger.error("Gerrit 获取失败: %s", e)
            return []


class VersionMddbFetcher:
    """从版本服务器获取 MDDB 符号表（回退方式）"""
    
    def __init__(self, version_string):
        self.version_string = version_string.strip()
        self.normalized_version = normalize_version(version_string)
        self.project_name = extract_project_name(version_string)
        self.found_zip = None
        self.logger = logging.getLogger("mddb-fetcher.version-server")
    
    def _find_project_folders_fast(self, brand_path):
        found = []
        exact = brand_path / self.project_name
        if exact.exists() and exact.is_dir():
            found.append(exact)
        try:
            for d in brand_path.glob(self.project_name + "-*"):
                if d.is_dir() and d not in found:
                    found.append(d)
        except Exception as e:
            self.logger.debug("glob 搜索出错 %s: %s", brand_path, e)
        return found

    def _search_zip_in_type_path(self, type_path):
        if not type_path.exists():
            return None
        try:
            for version_dir in type_path.iterdir():
                if not version_dir.is_dir():
                    continue
                for search_dir in [version_dir / "Open", version_dir]:
                    if not search_dir.exists():
                        continue
                    for zip_file in search_dir.glob("*.zip"):
                        zip_name = zip_file.name
                        if any(s in zip_name for s in ['_user_fans', '_user', '_debug']):
                            continue
                        if self.normalized_version in zip_name:
                            self.found_zip = zip_file
                            size_gb = zip_file.stat().st_size / (1024**3)
                            self.logger.info("找到版本 ZIP: %s (%.2f GB) 路径: %s",
                                           zip_file.name, size_gb, zip_file.parent)
                            return zip_file
        except Exception as e:
            self.logger.debug("搜索路径出错 %s: %s", type_path, e)
        return None

    def find_version_zip(self):
        if not self.project_name:
            self.logger.warning("无法从版本号中提取项目名称: %s", self.version_string)
            return None
        
        self.logger.info("搜索版本 ZIP 文件: %s (标准化: %s, 项目前缀: %s)",
                        self.version_string, self.normalized_version, self.project_name)
        
        search_types = ["FANS", "TEST"]
        
        candidates = []
        for server_root in VERSION_SERVER_ROOTS:
            server_path = Path(server_root)
            if not server_path.exists():
                continue
            for brand in BRANDS:
                brand_path = server_path / brand
                if not brand_path.exists():
                    continue
                folders = self._find_project_folders_fast(brand_path)
                if folders:
                    self.logger.info("在 %s/%s 下找到 %d 个项目文件夹: %s",
                                   server_root, brand, len(folders),
                                   [f.name for f in folders])
                    candidates.extend(folders)
        
        if not candidates:
            self.logger.warning("未找到项目文件夹: %s", self.project_name)
            return None
        
        for project_folder in candidates:
            for search_type in search_types:
                result = self._search_zip_in_type_path(project_folder / search_type)
                if result:
                    return result
        
        self.logger.warning("未找到版本 ZIP 文件: %s (标准化: %s)", self.version_string, self.normalized_version)
        return None
    
    def extract_mddb_to_dir(self, output_dir):
        if not self.found_zip:
            self.logger.error("未找到 ZIP 文件，请先调用 find_version_zip()")
            return []
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        try:
            with zipfile.ZipFile(self.found_zip, 'r') as zf:
                all_files = zf.namelist()
                
                mddb_files = []
                for file_path in all_files:
                    filename = os.path.basename(file_path)
                    if filename.startswith('MDDB_InfoCustom') and filename.lower().endswith('.edb'):
                        mddb_files.append(file_path)
                
                if not mddb_files:
                    self.logger.warning("ZIP 中未找到 MDDB_InfoCustom*.EDB 文件")
                    return []
                
                extracted_files = []
                for file_path in mddb_files:
                    filename = os.path.basename(file_path)
                    output_file = output_path / filename
                    
                    with zf.open(file_path) as source:
                        with open(output_file, 'wb') as target:
                            shutil.copyfileobj(source, target)
                    
                    size_mb = output_file.stat().st_size / (1024 * 1024)
                    self.logger.info("提取 MDDB 文件: %s (%.2f MB) -> %s", filename, size_mb, output_dir)
                    extracted_files.append(filename)
                
                return extracted_files
        
        except Exception as e:
            self.logger.error("提取 MDDB 文件失败: %s", e)
            return []
    
    def fetch_to_dir(self, output_dir):
        zip_path = self.find_version_zip()
        if not zip_path:
            return []
        
        return self.extract_mddb_to_dir(output_dir)


def has_edb_files(directory):
    """检查目录及其父目录中是否已存在 EDB 文件"""
    try:
        # 检查当前目录
        for name in os.listdir(directory):
            if name.lower().endswith('.edb'):
                return True
        
        # 检查父目录（EDB 文件可能在 mdlog1 父目录中）
        parent_dir = os.path.dirname(directory)
        if parent_dir and os.path.isdir(parent_dir):
            for name in os.listdir(parent_dir):
                if name.lower().endswith('.edb'):
                    return True
    except OSError:
        pass
    return False


def find_muxz_dirs(mdlog_dir):
    """在 mdlog1 目录中查找包含 .muxz 文件的子目录"""
    muxz_dirs = []
    
    # 检查当前目录
    try:
        has_muxz = any(name.lower().endswith(('.mux', '.muxz', '.muxraw')) 
                      for name in os.listdir(mdlog_dir))
        if has_muxz:
            muxz_dirs.append(mdlog_dir)
    except OSError:
        pass
    
    # 检查子目录
    try:
        for entry in os.scandir(mdlog_dir):
            if entry.is_dir():
                try:
                    has_muxz = any(name.lower().endswith(('.mux', '.muxz', '.muxraw')) 
                                  for name in os.listdir(entry.path))
                    if has_muxz:
                        muxz_dirs.append(entry.path)
                except OSError:
                    pass
    except OSError:
        pass
    
    return muxz_dirs


def fetch_mddb_for_all_logs(manifest_path):
    logger = logging.getLogger("mddb-fetcher")
    manifest = load_manifest(manifest_path)
    
    affected_versions = manifest.get("jira", {}).get("affected_versions", [])
    if not affected_versions:
        logger.info("未找到影响版本，跳过 MDDB 获取")
        manifest["mddb_fetch"] = {"results": []}
        save_manifest(manifest_path, manifest)
        return 0
    
    version = affected_versions[0]
    logger.info("使用影响版本: %s", version)
    
    filter_results = manifest.get("extraction", {}).get("filter_results", [])
    mdlog_dirs = []
    for result in filter_results:
        mdlog_dirs.extend(result.get("found", {}).get("mdlog1_dirs", []))
    
    if not mdlog_dirs:
        logger.info("未找到 MDLog 目录，跳过 MDDB 获取")
        manifest["mddb_fetch"] = {"results": []}
        save_manifest(manifest_path, manifest)
        return 0
    
    # 去重并找到实际包含 .muxz 文件的目录
    unique_mdlog_dirs = list(dict.fromkeys(mdlog_dirs))
    target_dirs = []
    for mdlog_dir in unique_mdlog_dirs:
        muxz_dirs = find_muxz_dirs(mdlog_dir)
        target_dirs.extend(muxz_dirs)
    
    # 去重
    target_dirs = list(dict.fromkeys(target_dirs))
    
    if not target_dirs:
        logger.info("未找到包含 trace 文件的目录，跳过 MDDB 获取")
        manifest["mddb_fetch"] = {"results": []}
        save_manifest(manifest_path, manifest)
        return 0
    
    logger.info("找到 %d 个包含 trace 文件的目录", len(target_dirs))
    
    env = load_env()
    gerrit_fetcher = GerritMddbFetcher(version, env)
    version_fetcher = VersionMddbFetcher(version)
    
    results = []
    for target_dir in target_dirs:
        logger.info("处理目录: %s", target_dir)
        
        # 检查是否已存在 EDB 文件（检查当前目录和父目录）
        if has_edb_files(target_dir):
            logger.info("目录或其父目录中已存在 EDB 文件，跳过获取")
            results.append({
                "mdlog_dir": os.path.abspath(target_dir),
                "version": version,
                "mddb_files": [],
                "fetch_method": "skip",
                "success": True,
                "error": None,
                "skipped": True,
                "skip_reason": "EDB 文件已存在",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            })
            continue
        
        mddb_files = []
        fetch_method = None
        error = None
        
        mddb_files = gerrit_fetcher.fetch_to_dir(target_dir)
        if mddb_files:
            fetch_method = "gerrit"
            logger.info("Gerrit 获取成功: %d 个文件", len(mddb_files))
        
        if not mddb_files:
            logger.info("Gerrit 获取失败，回退到版本服务器...")
            mddb_files = version_fetcher.fetch_to_dir(target_dir)
            if mddb_files:
                fetch_method = "version-server"
                logger.info("版本服务器获取成功: %d 个文件", len(mddb_files))
        
        if not mddb_files:
            error = "Gerrit 和版本服务器均未找到 MDDB 文件"
        
        results.append({
            "mdlog_dir": os.path.abspath(target_dir),
            "version": version,
            "mddb_files": mddb_files,
            "fetch_method": fetch_method,
            "success": bool(mddb_files),
            "error": error,
            "skipped": False,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        })
    
    manifest["mddb_fetch"] = {"results": results}
    save_manifest(manifest_path, manifest)
    
    success_count = sum(1 for r in results if r["success"])
    skipped_count = sum(1 for r in results if r.get("skipped", False))
    gerrit_count = sum(1 for r in results if r.get("fetch_method") == "gerrit")
    version_count = sum(1 for r in results if r.get("fetch_method") == "version-server")
    
    logger.info("MDDB 获取完成: 成功 %d/%d (跳过: %d, Gerrit: %d, 版本服务器: %d)",
                success_count, len(results), skipped_count, gerrit_count, version_count)
    
    return 0


def parse_args():
    parser = argparse.ArgumentParser(description="从 Gerrit 或 MTK 版本服务器获取 MDDB 符号表文件")
    parser.add_argument("--manifest", required=True, help="manifest 文件路径")
    parser.add_argument("--output", help="结果 JSON 输出路径（可选）")
    return parser.parse_args()


def main():
    configure_stdio()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    
    try:
        return fetch_mddb_for_all_logs(args.manifest)
    except Exception as e:
        logger = logging.getLogger("mddb-fetcher")
        logger.error("MDDB 获取失败: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
