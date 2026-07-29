#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@Project ：dz_auto_env 
@File    ：app_repo_updater
@Author  ：xingzhi.chen
@Date    ：2025/10/9 13:48 
"""
import json
import shutil

import os
import sys
import time
import schedule
import logging

import uiautomator2 as u2
from pathlib import Path
from apk_xapk_repo_builder import import_files
from get_apk_xapk_from_phone import smart_update_external
from local_to_feishu_sync import LocalToFeishuSync
from datetime import datetime
from typing import Union, List, Optional
from functools import partial

current_dir = os.path.dirname(os.path.abspath(__file__))  # 当前文件所在目录
parent_dir = os.path.dirname(current_dir)  # 上一级
grandparent_dir = os.path.dirname(parent_dir)  # 上两级
sys.path.append(grandparent_dir)
from tpytest.resource_provider import BaseResourceProvider, ResourceProviderFactory


class AppRepoUpdater:
    def __init__(self, provider: BaseResourceProvider):
        self.res_provider = provider

    @staticmethod
    def create_windows_nas_res_provider(
        remote_repo_path: str,
        nas_username: Optional[str] = None,
        nas_password: Optional[str] = None
    ) -> BaseResourceProvider:
        """创建Windows NAS资源提供器
        
        Args:
            remote_repo_path: NAS远程路径
            nas_username: NAS用户名(可选)
            nas_password: NAS密码(可选)
        """
        # 如果提供了认证信息,先连接NAS
        if nas_username and nas_password:
            nas_host = remote_repo_path.split('\\')[2] if '\\' in remote_repo_path else None
            if nas_host:
                import subprocess
                nas_share = f"\\\\{nas_host}"
                cmd = f'net use {nas_share} /user:{nas_username} {nas_password}'
                try:
                    subprocess.run(cmd, shell=True, check=False, capture_output=True)
                    logging.info(f"✓ NAS认证成功: {nas_share}")
                except Exception as e:
                    logging.warning(f"NAS认证失败: {e}")
        
        return ResourceProviderFactory.create(remote_repo_path)

    def download_global_index(self, remote_global_index_name: str, local_path: str) -> None:
        ret = self.res_provider.download(remote_global_index_name, local_path, True)
        assert ret

    def upload_global_index(self, from_path: str, to_file_name: str):
        self.res_provider.upload(from_path, to_file_name, True)

    def upload_local_repo_apks(self, from_path: str, to_file_name: str):
        self.res_provider.upload(from_path, to_file_name, True)


def ensure_empty_dir(dir_path):
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
        logging.info(f"📁 已创建新文件夹: {dir_path}")
    else:
        # 文件夹存在，清空内容
        for item in os.listdir(dir_path):
            item_path = os.path.join(dir_path, item)
            try:
                if os.path.isfile(item_path) or os.path.islink(item_path):
                    os.unlink(item_path)  # 删除文件或软链接
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)  # 删除子目录
            except Exception as e:
                logging.info(f"⚠️ 删除失败: {item_path}, 错误: {e}")
        logging.info(f"🧹 已清空文件夹内容: {dir_path}")


def merge_global_index(local_path, remote_path, output_path):
    def load_json(path):
        if not os.path.exists(path):
            logging.info(f"⚠️ 文件不存在: {path}")
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    local_data = load_json(local_path)
    remote_data = load_json(remote_path)

    local_apps = {app['package_name']: app for app in local_data.get('apps', [])}
    remote_apps = {app['package_name']: app for app in remote_data.get('apps', [])}

    # 合并逻辑：local 覆盖 remote
    merged_apps = dict(remote_apps)
    merged_apps.update(local_apps)

    # 保持结构一致
    merged_data = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "apps": list(merged_apps.values())
    }

    # 输出文件
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(merged_data, f, ensure_ascii=False, indent=4)


# ---------------------
# 日志配置函数
# ---------------------
def setup_logger():
    log_dir = r"..\..\.runtime\apk_update_logs"
    os.makedirs(log_dir, exist_ok=True)  # 确保日志目录存在
    log_file = os.path.join(log_dir, f"{datetime.now().strftime('%Y-%m-%d')}.log")

    # 配置日志格式
    logging.basicConfig(
        level=logging.INFO,  # 默认记录 INFO 及以上等级
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),  # 写入文件
            logging.StreamHandler()  # 输出到控制台
        ]
    )


# ---------------------
# 任务函数：同步本地仓库到飞书
# ---------------------
def sync_to_feishu(local_backup_repo_path: str, feishu_app_id: str, feishu_app_secret: str,
                   feishu_root_folder_name: str, feishu_root_folder_token: str, feishu_remote_path: str):
    try:
        logging.info("☁️ 开始同步本地仓库到飞书")

        # 创建飞书同步助手
        sync_helper = LocalToFeishuSync(
            app_id=feishu_app_id,
            app_secret=feishu_app_secret,
            root_folder_name=feishu_root_folder_name,
            root_folder_token=feishu_root_folder_token
        )

        # 开始同步
        sync_helper.sync_local_to_feishu(local_backup_repo_path, feishu_remote_path)

        logging.info("✅ 同步到飞书完成")

    except Exception as e:
        logging.error(f"❌ 同步到飞书失败：{e}")
        raise


# ---------------------
# 任务函数：更新应用仓库
# ---------------------
def update_app_repo(remote_app_repo_path: str, local_app_repo_path: str, local_apk_xapk_path: str,
                    local_backup_repo_path: str, device_serial: Optional[str] = None,
                    enable_feishu_sync: bool = False, feishu_config: Optional[dict] = None,
                    nas_username: Optional[str] = None, nas_password: Optional[str] = None):
    try:
        logging.info("🛠 开始更新应用仓库")

        ensure_empty_dir(local_app_repo_path)
        ensure_empty_dir(local_backup_repo_path)

        res_provider = AppRepoUpdater.create_windows_nas_res_provider(
            remote_repo_path=remote_app_repo_path,
            nas_username=nas_username,
            nas_password=nas_password
        )
        updater = AppRepoUpdater(res_provider)

        # 1. 下载 global_index
        updater.download_global_index(
            remote_global_index_name='global_index.json',
            local_path=os.path.join(local_app_repo_path, 'global_index_remote.json')
        )

        # 2. 根据索引更新 apk / xapk
        result = smart_update_external(
            device_serial=device_serial,
            output_dir=os.path.join(local_app_repo_path, 'new_apk_xapk_files'),
            index_file=os.path.join(local_app_repo_path, 'global_index_remote.json')
        )

        # 3. 将apk整理成仓库形式
        updated_packages = result['updated_packages_list']
        updated_packages_path: List[Union[str, Path]] = [
            Path(os.path.join(local_apk_xapk_path, pkg)) for pkg in updated_packages
        ]
        import_files(updated_packages_path, Path(local_app_repo_path), 'xingzhi.chen', False, False, 'A1')
        logging.info(f"📋 将apk整理成仓库形式")

        # 4. 上传apk到NAS
        logging.info(f"📋 开始上传apk包到nas")
        packages_dir = os.path.join(local_app_repo_path, 'packages')
        os.makedirs(packages_dir, exist_ok=True)
        updater.upload_local_repo_apks(
            from_path=packages_dir,
            to_file_name='packages'
        )
        logging.info(f"📋 已上传apk包到nas")

        # 4.1 同步复制到本地临时仓库
        logging.info(f"📋 开始同步复制到本地临时仓库")
        local_backup_packages_path = os.path.join(local_backup_repo_path, 'packages')
        os.makedirs(local_backup_packages_path, exist_ok=True)
        shutil.copytree(os.path.join(local_app_repo_path, 'packages'), local_backup_packages_path, dirs_exist_ok=True)
        logging.info(f"📋 已同步复制到本地临时仓库: {local_backup_packages_path}")

        # 5. 合并 global_index 文件
        merge_global_index(
            local_path=os.path.join(local_app_repo_path, 'global_index.json'),
            remote_path=os.path.join(local_app_repo_path, 'global_index_remote.json'),
            output_path=os.path.join(local_app_repo_path, 'global_index_new.json')
        )

        # 6. 上传新的 global_index 到nas
        logging.info(f"📋 开始上传新的 global_index到nas")
        updater.upload_global_index(
            from_path=os.path.join(local_app_repo_path, 'global_index_new.json'),
            to_file_name="global_index.json"
        )
        logging.info(f"📋 成功上传新的 global_index到nas")

        # 6.1 同步复制到本地临时仓库
        logging.info(f"📋 开始同步新的 global_index到本地临时仓库")
        local_backup_index_path = os.path.join(local_backup_repo_path, 'global_index.json')
        shutil.copy2(os.path.join(local_app_repo_path, 'global_index_new.json'), local_backup_index_path)
        logging.info(f"📋 已同步复制 global_index 到本地临时仓库: {local_backup_index_path}")

        logging.info("✅ 应用仓库更新完成")

        # 7. 同步到飞书（如果启用）
        if enable_feishu_sync and feishu_config:
            logging.info("开始同步到飞书云盘...")
            sync_to_feishu(
                local_backup_repo_path=local_backup_repo_path,
                feishu_app_id=feishu_config['app_id'],
                feishu_app_secret=feishu_config['app_secret'],
                feishu_root_folder_name=feishu_config['root_folder_name'],
                feishu_root_folder_token=feishu_config['root_folder_token'],
                feishu_remote_path=feishu_config['remote_path']
            )
        logging.info(f"📋 成功同步飞书云盘")

    except Exception as e:
        logging.error(f"❌ 更新应用仓库失败：{e}")
        raise


# ---------------------
# 任务函数：更新手机应用
# ---------------------
def update_phone_app_version(device_serial: str):
    try:
        logging.info("📱 开始更新手机应用版本")

        d = u2.connect(device_serial)

        d.screen_off()
        time.sleep(3)
        d.screen_on()
        time.sleep(3)

        w, h = d.window_size()
        d.swipe(w / 2, h * 0.9, w / 2, h * 0.1, 0.2)
        time.sleep(3)

        d.app_stop("com.android.vending")
        time.sleep(5)
        d.app_start("com.android.vending")
        time.sleep(5)

        # 点击进入 Google Play 更新页面
        if d.xpath('//*[contains(@content-desc, "Account and settings")]').exists:
            d.xpath('//*[contains(@content-desc, "Account and settings")]').click()
        time.sleep(5)

        if d.xpath('//*[@text="Manage apps & device"]').exists:
            d.xpath('//*[@text="Manage apps & device"]').click()
        time.sleep(5)

        if d.xpath('//*[@text="Update all"]').exists:
            d.xpath('//*[@text="Update all"]').click()
        time.sleep(5)

        logging.info("✅ 手机应用更新完成")

    except Exception as e:
        logging.error(f"❌ 更新手机应用失败：{e}")


# ---------------------
# 周期执行管理函数
# ---------------------
def cycle_execution(update_app_repo_task, update_phone_task):
    def job_update_utils():
        logging.info("🚀 执行更新应用仓库任务")
        update_app_repo_task()

    def job_update_googleplay():
        logging.info("🚀 执行更新手机应用任务")
        update_phone_task()

    # ✅ 启动时立即执行一次更新应用仓库
    job_update_utils()

    # ✅ 每天凌晨 2:00 执行更新应用仓库
    schedule.every(5).days.at("02:00").do(job_update_utils)

    # ✅ 每天凌晨 00:00 执行更新手机应用
    schedule.every().day.at("00:00").do(job_update_googleplay)

    logging.info("⏳ 定时任务启动，等待调度...")

    while True:
        schedule.run_pending()
        time.sleep(60)


# ---------------------
# 主程序入口
# ---------------------
if __name__ == '__main__':
    # 初始化日志系统
    setup_logger()

    # 飞书配置
    FEISHU_CONFIG = {
        'app_id': 'cli_a88b4d15dc70100b',
        'app_secret': 'nTOW0ZolI9RssVN8gact5eVcLVtljJC2',
        'root_folder_name': '快温省_PPT',
        'root_folder_token': 'FcFefmW17lcqGjd9KnUcj9oynUf',
        'remote_path': 'app_repo'
    }

    # NAS配置
    NAS_PATH = r'\\10.205.101.100\automation\dzppt\ppt_test_resources\app_repo'
    NAS_USERNAME = 'nasuser'
    NAS_PASSWORD = 'Tanssion123'
    
    cycle_execution(
        partial(update_app_repo,
                # 新的NAS路径
                remote_app_repo_path=NAS_PATH,
                local_app_repo_path=r'D:\tpytest_app_updates',
                local_apk_xapk_path=r'D:\tpytest_app_updates\new_apk_xapk_files',
                local_backup_repo_path=r'D:\tpytest_local_app_repo',
                device_serial='H933CK9N01234567',
                enable_feishu_sync=True,
                feishu_config=FEISHU_CONFIG,
                # NAS认证信息
                nas_username=NAS_USERNAME,
                nas_password=NAS_PASSWORD
                ),
        partial(update_phone_app_version,
                device_serial='H933CK9N01234567'
                )
    )

    # 手动测试示例:
    # update_app_repo(
    #     remote_app_repo_path=r'\\10.205.101.100\automation\dzppt\ppt_test_resources\app_repo',
    #     local_app_repo_path=r'D:\tpytest_app_updates',
    #     local_apk_xapk_path=r'D:\tpytest_app_updates\new_apk_xapk_files',
    #     local_backup_repo_path=r'D:\tpytest_local_app_repo',
    #     device_serial='H933CK9N01234567',
    #     enable_feishu_sync=True,
    #     feishu_config=FEISHU_CONFIG,
    #     nas_username='nasuser',
    #     nas_password='Tanssion123'
    # )
