#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@Project ：dz_auto_env 
@File    ：demo
@Author  ：xingzhi.chen
@Date    ：2025/12/30 17:27 
"""
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from powertrde import env
from powertrde.utils.lazy_shared_pool import LazySharedPool
from plugins.video_recorder.camera_service_manager import ensure_camera_service

pool = LazySharedPool(r"D:\dz_auto_env_configs\shared\powertrde_shared_pool.db", '1')

params = {
    'user': 'tester1',
    'task': 'important_test1',
    'save_own_copy': True,  # 关键: 启用专属副本
    'copy_to_dir': r'E:\Desktop\camera_video_logs\tester1',  # 自定义文件夹名
    'save_dir': r'E:\Desktop\camera_video_logs',
    'db_path': r"D:\dz_auto_env_configs\shared\powertrde_shared_pool.db"
}
ensure_camera_service(params)
pool.join_shared_resource('摄像头', params)
time.sleep(1000)