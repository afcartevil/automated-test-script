#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@Project : dz_auto_env 
@File    : local_to_feishu_sync
@Author  : xingzhi.chen
@Date    : 2025-10-29
@Description : 将本地 Windows 文件夹同步到飞书云盘文件夹
"""
import os
import sys
import logging
from pathlib import Path
from datetime import datetime

# 添加父目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
grandparent_dir = os.path.dirname(parent_dir)
sys.path.append(grandparent_dir)

from powertrde.utils.feishu.feishu_api_helper import FeishuApiHelper


class LocalToFeishuSync:
    """将本地 Windows 文件夹同步到飞书云盘文件夹"""
    
    # 特殊文件列表：需要在最后同步的文件
    SPECIAL_FILES = ['global_index.json']
    
    def __init__(self, app_id: str, app_secret: str, root_folder_name: str, root_folder_token: str):
        """
        初始化飞书同步助手
        
        :param app_id: 飞书应用 ID
        :param app_secret: 飞书应用密钥
        :param root_folder_name: 根文件夹名称（用于标识）
        :param root_folder_token: 飞书中的根文件夹 token
        """
        self.feishu = FeishuApiHelper(app_id, app_secret)
        self.feishu.register_root_folder_token(root_folder_name, root_folder_token)
        self.root_folder_name = root_folder_name
        self.root_folder_token = root_folder_token
        
    def _get_or_create_folder(self, folder_name: str, parent_token: str) -> str:
        """
        获取文件夹 token，如果不存在则创建（带重试机制）
        
        :param folder_name: 文件夹名称
        :param parent_token: 父文件夹 token
        :return: 文件夹 token
        """
        import time
        
        max_retries = 5  # 增加重试次数
        retry_delay = 3  # 增加初始延迟（秒）
        
        for attempt in range(max_retries):
            try:
                # 搜索已存在的文件夹
                existing = self.feishu.search_folder(parent_token, folder_name=folder_name)
                if existing:
                    logging.info(f"找到已存在的文件夹: {folder_name}")
                    return existing["token"]
                
                # 如果不存在则创建新文件夹
                logging.info(f"创建新文件夹: {folder_name} (attempt {attempt + 1}/{max_retries})")
                
                # 在第3次重试时，尝试刷新 token
                if attempt == 2:
                    logging.info("尝试刷新 access token...")
                    try:
                        self.feishu.refresh_access_token()
                        logging.info("Access token 刷新成功")
                    except Exception as e:
                        logging.warning(f"刷新 token 失败: {e}")
                
                result = self.feishu.create_folder(folder_name, parent_token)
                
                # 创建成功后稍等片刻，避免过快的后续请求
                time.sleep(1)
                return result["data"]["token"]
                
            except Exception as e:
                error_msg = str(e)
                
                # 如果是"unknown error"或资源竞争错误且还有重试机会
                should_retry = (
                    ("unknown error" in error_msg or "resource contention" in error_msg) 
                    and attempt < max_retries - 1
                )
                
                if should_retry:
                    logging.warning(f"创建失败 ({error_msg})，{retry_delay}秒后重试... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, 10)  # 指数退避，最多10秒
                    continue
                
                # 其他错误或最后一次重试失败
                logging.error(f"获取或创建文件夹 '{folder_name}' 时出错: {e}")
                
                # 最后一次尝试：再次搜索（可能已经被其他请求创建或实际已存在）
                if attempt == max_retries - 1:
                    try:
                        logging.info("最后一次尝试：重新搜索文件夹...")
                        time.sleep(2)
                        existing = self.feishu.search_folder(parent_token, folder_name=folder_name)
                        if existing:
                            logging.info(f"重试搜索成功，找到文件夹: {folder_name}")
                            return existing["token"]
                    except Exception as search_e:
                        logging.error(f"最后搜索也失败: {search_e}")
                
                raise
    
    def _delete_if_exists(self, file_name: str, parent_token: str):
        """
        如果文件或文件夹存在于父文件夹中，则删除它
        
        :param file_name: 要删除的文件或文件夹名称
        :param parent_token: 父文件夹 token
        """
        try:
            existing = self.feishu.search_folder(parent_token, folder_name=file_name)
            if existing:
                logging.info(f"删除已存在的项目: {file_name} (类型: {existing['type']})")
                self.feishu.delete_file_or_folder(existing["token"], existing["type"])
                logging.info(f"成功删除: {file_name}")
        except Exception as e:
            logging.warning(f"删除 '{file_name}' 时出错: {e}")
    
    def _get_feishu_folder_items(self, folder_token: str) -> dict:
        """
        获取飞书文件夹中的所有项目
        
        :param folder_token: 文件夹 token
        :return: {文件名/文件夹名: {"token": xxx, "type": "file"/"folder"}}
        """
        try:
            items = self.feishu.search_folder(folder_token, only_first_file=False)
            if not items:
                return {}
            
            result = {}
            for item in items:
                result[item['name']] = {
                    'token': item['token'],
                    'type': item['type']
                }
            return result
        except Exception as e:
            logging.warning(f"获取飞书文件夹内容时出错: {e}")
            return {}
    
    def _file_needs_upload(self, file_name: str, parent_token: str) -> bool:
        """
        检查文件是否需要上传（根据文件名判断是否存在）
        
        :param file_name: 文件名
        :param parent_token: 飞书中的父文件夹 token
        :return: True 需要上传，False 不需要上传
        """
        try:
            # 搜索飞书上的文件
            existing = self.feishu.search_folder(parent_token, folder_name=file_name)
            if not existing or existing['type'] != 'file':
                logging.info(f"文件不存在，需要上传: {file_name}")
                return True  # 文件不存在或类型不匹配，需要上传
            
            # 文件已存在，跳过上传
            logging.info(f"文件已存在，跳过上传: {file_name}")
            return False
            
        except Exception as e:
            logging.warning(f"检查文件 '{file_name}' 时出错: {e}，将重新上传")
            return True
    
    def _upload_file(self, local_file_path: str, file_name: str, parent_token: str, force: bool = False):
        """
        上传单个文件到飞书
        
        :param local_file_path: 本地文件路径
        :param file_name: 文件名
        :param parent_token: 飞书中的父文件夹 token
        :param force: 是否强制上传（忽略文件比较）
        """
        try:
            # 检查是否需要上传（除非强制上传）
            if not force and not self._file_needs_upload(file_name, parent_token):
                return
            
            # 如果存在则删除已有文件
            self._delete_if_exists(file_name, parent_token)
            
            # 上传新文件
            file_size = os.path.getsize(local_file_path)
            if file_size > 20 * 1024 * 1024:  # > 20MB
                logging.info(f"上传大文件: {file_name} ({file_size / (1024*1024):.2f} MB)")
                self.feishu._upload_large_file(parent_token, local_file_path, file_name)
            else:
                logging.info(f"上传文件: {file_name} ({file_size / 1024:.2f} KB)")
                self.feishu._upload_file(parent_token, local_file_path, file_name)
            
            logging.info(f"成功上传: {file_name}")
        except Exception as e:
            logging.error(f"上传文件 '{file_name}' 时出错: {e}")
            raise
    
    def _sync_folder_recursive(self, local_folder: Path, feishu_parent_token: str, relative_path: str = "", special_files_queue: list = None):
        """
        递归同步本地文件夹到飞书
        
        :param local_folder: 本地文件夹路径
        :param feishu_parent_token: 飞书中的父文件夹 token
        :param relative_path: 相对路径（用于日志）
        :param special_files_queue: 特殊文件队列（用于延迟上传）
        """
        try:
            # 获取飞书文件夹中的现有项目
            feishu_items = self._get_feishu_folder_items(feishu_parent_token)
            
            # 列出本地文件夹中的所有项目
            items = list(local_folder.iterdir())
            logging.info(f"同步文件夹: {relative_path or '根目录'} ({len(items)} 个项目)")
            
            # 记录本地存在的项目名称
            local_item_names = set()
            
            for item in items:
                local_item_names.add(item.name)
                item_relative_path = f"{relative_path}/{item.name}" if relative_path else item.name
                
                if item.is_dir():
                    # 处理目录
                    logging.info(f"处理目录: {item_relative_path}")
                    folder_token = self._get_or_create_folder(item.name, feishu_parent_token)
                    # 递归同步子目录
                    self._sync_folder_recursive(item, folder_token, item_relative_path, special_files_queue)
                else:
                    # 处理文件
                    # 检查是否是特殊文件（需要最后上传）
                    if item.name in self.SPECIAL_FILES and special_files_queue is not None:
                        logging.info(f"特殊文件，加入延迟队列: {item_relative_path}")
                        special_files_queue.append({
                            'local_path': str(item),
                            'file_name': item.name,
                            'parent_token': feishu_parent_token,
                            'relative_path': item_relative_path
                        })
                    else:
                        logging.info(f"处理文件: {item_relative_path}")
                        self._upload_file(str(item), item.name, feishu_parent_token)
            
            # # 删除飞书上存在但本地不存在的项目
            # for feishu_item_name, feishu_item_info in feishu_items.items():
            #     if feishu_item_name not in local_item_names:
            #         logging.info(f"本地已删除，同步删除飞书上的项目: {feishu_item_name} (类型: {feishu_item_info['type']})")
            #         try:
            #             self.feishu.delete_file_or_folder(feishu_item_info['token'], feishu_item_info['type'])
            #             logging.info(f"成功删除: {feishu_item_name}")
            #         except Exception as e:
            #             logging.error(f"删除 '{feishu_item_name}' 时出错: {e}")
            
            logging.info(f"完成同步文件夹: {relative_path or '根目录'}")
        except Exception as e:
            logging.error(f"同步文件夹 '{relative_path}' 时出错: {e}")
            raise
    
    def sync_local_to_feishu(self, local_folder_path: str, feishu_remote_path: str):
        """
        将整个本地文件夹同步到飞书云盘文件夹
        
        :param local_folder_path: 要同步的本地文件夹路径
        :param feishu_remote_path: 飞书中的远程路径（相对于根文件夹）
        """
        try:
            local_folder = Path(local_folder_path)
            
            # 验证本地文件夹
            if not local_folder.exists():
                raise FileNotFoundError(f"本地文件夹不存在: {local_folder_path}")
            if not local_folder.is_dir():
                raise ValueError(f"路径不是一个目录: {local_folder_path}")
            
            logging.info(f"=== 开始同步 ===")
            logging.info(f"本地文件夹: {local_folder_path}")
            logging.info(f"飞书路径: {feishu_remote_path}")
            
            # 获取或创建飞书中的目标文件夹
            if feishu_remote_path:
                # 导航到目标文件夹（如需要则创建）
                folders = feishu_remote_path.strip('/').split('/')
                current_token = self.root_folder_token
                
                for folder_name in folders:
                    current_token = self._get_or_create_folder(folder_name, current_token)
                
                target_token = current_token
            else:
                # 直接使用根文件夹
                target_token = self.root_folder_token
            
            # 创建特殊文件队列
            special_files_queue = []
            
            # 开始递归同步（普通文件和文件夹）
            self._sync_folder_recursive(local_folder, target_token, special_files_queue=special_files_queue)
            
            # 最后处理特殊文件（如 global_index.json）
            if special_files_queue:
                logging.info(f"\n=== 开始同步特殊文件 ({len(special_files_queue)} 个) ===")
                for special_file in special_files_queue:
                    logging.info(f"处理特殊文件: {special_file['relative_path']}")
                    # 强制上传特殊文件（总是删除旧的并上传新的）
                    self._upload_file(
                        special_file['local_path'],
                        special_file['file_name'],
                        special_file['parent_token'],
                        force=True
                    )
            
            logging.info("\n=== 同步成功完成 ===")
            
        except Exception as e:
            logging.error(f"同步失败: {e}")
            raise


def setup_logger():
    """配置日志系统"""
    log_dir = r"..\..\\.runtime\\feishu_sync_logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{datetime.now().strftime('%Y-%m-%d')}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

def _demo():
    FEISHU_APP_ID = 'cli_a88b4d15dc70100b'
    FEISHU_APP_SECRET = 'nTOW0ZolI9RssVN8gact5eVcLVtljJC2'
    FEISHU_ROOT_FOLDER_TOKEN = 'RvJ2f0723lX8lCdgR0UckPAhnZc'

    from tpytest.resource_provider import FeishuProvider
    _feishu_api_helper = FeishuApiHelper(FEISHU_APP_ID, FEISHU_APP_SECRET)
    _feishu_api_helper.register_root_folder_token('app_repo', FEISHU_ROOT_FOLDER_TOKEN)
    _feishu_provider = FeishuProvider(_feishu_api_helper, 'app_repo')
    print(_feishu_provider.list_contents('packages'))

if __name__ == '__main__':
    # _demo()


    # 初始化日志系统
    setup_logger()

    try:
        # 配置信息
        FEISHU_APP_ID = 'cli_a88b4d15dc70100b'
        FEISHU_APP_SECRET = 'nTOW0ZolI9RssVN8gact5eVcLVtljJC2'
        FEISHU_ROOT_FOLDER_NAME = '快温省_PPT'
        FEISHU_ROOT_FOLDER_TOKEN = 'FcFefmW17lcqGjd9KnUcj9oynUf'

        # 要同步的本地文件夹
        LOCAL_FOLDER = r'D:\tpytest_local_app_repo'

        # 飞书目标路径（相对于根文件夹）
        FEISHU_PATH = 'app_repo'

        # 创建同步助手
        sync_helper = LocalToFeishuSync(
            app_id=FEISHU_APP_ID,
            app_secret=FEISHU_APP_SECRET,
            root_folder_name=FEISHU_ROOT_FOLDER_NAME,
            root_folder_token=FEISHU_ROOT_FOLDER_TOKEN
        )

        # 开始同步
        sync_helper.sync_local_to_feishu(LOCAL_FOLDER, FEISHU_PATH)

        logging.info("程序执行完成")

    except Exception as e:
        logging.error(f"程序执行失败: {e}")
        raise
