#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : dz_auto_env 
@File    : app_repo_checker
@Author  : xingzhi.chen
@Date    : 2025-11-21
@Description :
"""
import json
import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

# 添加父目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
grandparent_dir = os.path.dirname(parent_dir)
sys.path.append(grandparent_dir)

from tpytest.resource_provider import BaseResourceProvider, ResourceProviderFactory


class AppRepoChecker:
    """APK 仓库检查器 - 检查远端仓库中应用包是否存在"""
    
    GLOBAL_INDEX_FILENAME = "global_index.json"
    
    # 默认配置
    DEFAULT_CONFIG = {
        'remote_repo_path': r'\\10.205.101.200\nas2\resource\ppt_test_resources\app_repo',
        'username': 'monkeytest',
        'password': 'Monkey123',
        'cache_dir': r'D:\tpytest_app_updates\.app_repo_cache'
    }
    
    def __init__(self, provider: BaseResourceProvider, cache_dir: Optional[str] = None):
        """
        初始化仓库检查器
        
        :param provider: 资源提供器实例（用于访问远端仓库）
        :param cache_dir: 本地缓存目录（可选，用于缓存 global_index.json）
        """
        self.provider = provider
        self.cache_dir = Path(cache_dir) if cache_dir else Path(os.getcwd()) / ".app_repo_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self._index_cache_path = self.cache_dir / self.GLOBAL_INDEX_FILENAME
        self._index_data: Optional[Dict[str, Any]] = None
    
    def fetch_global_index(self, force: bool = False) -> Dict[str, Any]:
        """
        从远端 NAS 拉取 global_index.json 文件
        
        :param force: 是否强制从远端拉取（忽略本地缓存）
        :return: global_index.json 的字典数据
        :raises: FileNotFoundError 如果远端文件不存在
        :raises: json.JSONDecodeError 如果文件格式不正确
        """
        # 如果不强制更新且内存中已有缓存，直接返回
        if not force and self._index_data is not None:
            print(f"[INFO] 使用内存缓存的 global_index.json")
            return self._index_data
        
        # 如果不强制更新且本地文件缓存存在，优先使用本地缓存
        if not force and self._index_cache_path.exists():
            try:
                print(f"[INFO] 使用本地缓存文件: {self._index_cache_path}")
                with open(self._index_cache_path, 'r', encoding='utf-8') as f:
                    self._index_data = json.load(f)
                return self._index_data
            except Exception as e:
                print(f"[WARN] 读取本地缓存失败: {e}，将从远端拉取")
        
        # 从远端下载 global_index.json
        print(f"[INFO] 从远端拉取 {self.GLOBAL_INDEX_FILENAME}")
        try:
            downloaded_path = self.provider.download(
                self.GLOBAL_INDEX_FILENAME,
                str(self._index_cache_path),
                overwrite=True
            )
            print(f"[INFO] 下载成功: {downloaded_path}")
            
            # 读取并缓存到内存
            with open(self._index_cache_path, 'r', encoding='utf-8') as f:
                self._index_data = json.load(f)
            
            return self._index_data
            
        except Exception as e:
            raise FileNotFoundError(f"无法从远端拉取 {self.GLOBAL_INDEX_FILENAME}: {e}")
    
    def check_package_exists(self, package_name: str, force_refresh: bool = False) -> bool:
        """
        检查远端仓库中是否有指定的应用包
        
        :param package_name: 应用包名（如 com.example.app）
        :param force_refresh: 是否强制刷新 global_index（默认使用缓存）
        :return: True 如果包存在，False 如果不存在
        """
        # 确保已加载索引数据
        if self._index_data is None or force_refresh:
            try:
                self.fetch_global_index(force=force_refresh)
            except Exception as e:
                print(f"[ERROR] 获取 global_index 失败: {e}")
                return False
        
        # 在 apps 列表中查找包名
        apps = self._index_data.get("apps", [])
        for app in apps:
            if app.get("package_name") == package_name:
                print(f"[INFO] 找到包: {package_name}")
                return True
        
        print(f"[INFO] 未找到包: {package_name}")
        return False
    
    def check_packages_batch(self, package_names: List[str], force_refresh: bool = False) -> Dict[str, bool]:
        """
        批量检查多个应用包是否存在于远端仓库
        
        :param package_names: 应用包名列表
        :param force_refresh: 是否强制刷新 global_index
        :return: 字典，key 为包名，value 为是否存在
        """
        # 确保已加载索引数据
        if self._index_data is None or force_refresh:
            try:
                self.fetch_global_index(force=force_refresh)
            except Exception as e:
                print(f"[ERROR] 获取 global_index 失败: {e}")
                return {pkg: False for pkg in package_names}
        
        # 构建包名集合以加速查询
        apps = self._index_data.get("apps", [])
        existing_packages = {app.get("package_name") for app in apps if app.get("package_name")}
        
        # 批量检查
        results = {}
        for package_name in package_names:
            exists = package_name in existing_packages
            results[package_name] = exists
            status = "存在" if exists else "不存在"
            print(f"[INFO] {package_name}: {status}")
        
        return results
    
    def get_package_info(self, package_name: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        获取指定包的详细信息
        
        :param package_name: 应用包名
        :param force_refresh: 是否强制刷新 global_index
        :return: 包信息字典，如果不存在则返回 None
        """
        # 确保已加载索引数据
        if self._index_data is None or force_refresh:
            try:
                self.fetch_global_index(force=force_refresh)
            except Exception as e:
                print(f"[ERROR] 获取 global_index 失败: {e}")
                return None
        
        # 查找包信息
        apps = self._index_data.get("apps", [])
        for app in apps:
            if app.get("package_name") == package_name:
                return app
        
        return None
    
    def list_all_packages(self, force_refresh: bool = False) -> List[str]:
        """
        列出远端仓库中所有应用包名
        
        :param force_refresh: 是否强制刷新 global_index
        :return: 包名列表
        """
        # 确保已加载索引数据
        if self._index_data is None or force_refresh:
            try:
                self.fetch_global_index(force=force_refresh)
            except Exception as e:
                print(f"[ERROR] 获取 global_index 失败: {e}")
                return []
        
        apps = self._index_data.get("apps", [])
        packages = [app.get("package_name") for app in apps if app.get("package_name")]
        
        print(f"[INFO] 仓库中共有 {len(packages)} 个应用包")
        return packages
    
    def get_missing_packages(self, package_names: List[str], force_refresh: bool = False) -> List[str]:
        """
        获取缺失的应用包列表（不在远端仓库中的包）
        
        :param package_names: 待检查的包名列表
        :param force_refresh: 是否强制刷新 global_index
        :return: 缺失的包名列表
        """
        results = self.check_packages_batch(package_names, force_refresh)
        missing = [pkg for pkg, exists in results.items() if not exists]
        
        if missing:
            print(f"[WARN] 以下 {len(missing)} 个包不在远端仓库中:")
            for pkg in missing:
                print(f"  - {pkg}")
        else:
            print(f"[INFO] 所有包都存在于远端仓库")
        
        return missing
    
    @classmethod
    def create_default(cls, cache_dir: Optional[str] = None) -> 'AppRepoChecker':
        """
        使用默认配置创建仓库检查器实例
        
        :param cache_dir: 本地缓存目录（可选，不指定则使用默认配置）
        :return: AppRepoChecker 实例
        """
        config = cls.DEFAULT_CONFIG
        
        # 创建资源提供器
        provider = ResourceProviderFactory.create(
            config['remote_repo_path'],
            username=config['username'],
            password=config['password']
        )
        
        # 使用指定的缓存目录或默认缓存目录
        final_cache_dir = cache_dir if cache_dir else config['cache_dir']
        
        return cls(provider=provider, cache_dir=final_cache_dir)


def _demo_usage():
    """示例用法"""
    # 方式1: 使用默认配置快速创建
    print("\n=== 方式1: 使用默认配置创建 ===")
    checker = AppRepoChecker.create_default()
    
    # 方式2: 使用默认配置但自定义缓存目录
    # checker = AppRepoChecker.create_default(cache_dir=r'E:\custom_cache')
    
    # 方式3: 完全自定义（保留原有方式）
    # remote_repo_path = r'\\10.205.101.200\nas2\resource\ppt_test_resources\app_repo'
    # username = 'monkeytest'
    # password = 'Monkey123'
    # provider = ResourceProviderFactory.create(remote_repo_path, username=username, password=password)
    # checker = AppRepoChecker(provider=provider, cache_dir=r'D:\tpytest_app_updates\.app_repo_cache')
    
    # 示例1: 拉取 global_index.json
    print("\n=== 示例1: 拉取 global_index.json ===")
    try:
        index_data = checker.fetch_global_index(force=True)
        print(f"成功拉取，包含 {len(index_data.get('apps', []))} 个应用")
    except Exception as e:
        print(f"拉取失败: {e}")
    
    # 示例2: 检查单个包是否存在
    print("\n=== 示例2: 检查单个包 ===")
    test_package = "com.shopee.sg"
    exists = checker.check_package_exists(test_package, force_refresh=True)
    print(f"{test_package}: {'存在' if exists else '不存在'}")
    
    # 示例3: 批量检查多个包
    print("\n=== 示例3: 批量检查 ===")
    test_packages = [
        "com.facebook.orca",
        "org.videolan.vlc",
        "com.example.notexist"
    ]
    results = checker.check_packages_batch(test_packages, force_refresh=True)
    
    # 示例4: 获取包详细信息
    print("\n=== 示例4: 获取包详细信息 ===")
    package_info = checker.get_package_info("com.facebook.orca")
    if package_info:
        print(f"包名: {package_info.get('package_name')}")
        print(f"版本: {package_info.get('version_name')} ({package_info.get('latest_version_code')})")
        print(f"Meta URL: {package_info.get('meta_url')}")
    
    # 示例5: 获取缺失的包
    print("\n=== 示例5: 获取缺失的包 ===")
    missing = checker.get_missing_packages(test_packages, force_refresh=True)


if __name__ == '__main__':
    _demo_usage()
