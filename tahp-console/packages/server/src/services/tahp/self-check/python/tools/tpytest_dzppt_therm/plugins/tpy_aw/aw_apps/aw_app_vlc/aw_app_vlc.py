#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@Project ：dz_auto_env 
@File    ：aw_app_vlc
@Author  ：xingzhi.chen
@Date    ：2025/8/5 13:49 
"""
import time

from powertrde.framework.tran_logger import t_log
from tpy_aw.aw_app_base import AwAppBase

class AwAppVLC(AwAppBase):
    aw_name = 'VLC'
    default_app_package = 'org.videolan.vlc'

    def click_video_tab(self):
        """
        点击视频tab
        """
        self.u2d.xpath('//*[@resource-id="org.videolan.vlc:id/nav_video"]').click()
        time.sleep(2)

    def play_video(self):
        """
        播放视频，前提再Video tab页
        """
        # 查找并点击Video文件夹
        self.u2d.xpath('//*[@text="VIDEOS"]').click()
        time.sleep(1)
        self.u2d.xpath('//*[@resource-id="org.videolan.vlc:id/ml_item_title" or contains(@content-desc, "Video:")]').click()
        time.sleep(1)
