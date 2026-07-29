# -*- coding: utf-8 -*-
# @Time     : 2025/6/23 16:39
# @Author   : kaiyuan.xie
# @Email    : kaiyuan.xie@transsion.com
# @File     : aw_app_filesbygoogle.py
import time

from powertrde.framework.tran_logger import t_log
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase

class FilesByGoogleLocator(U2SelectorLocator):
    search_btn = U2Selector().xpath('//android.support.v7.widget.LinearLayoutCompat').bind()


class AwAppFilesByGoogle(FilesByGoogleLocator, AwAppBase):
    aw_name = 'FilesByGoogle'
    default_app_package = 'com.google.android.apps.nbu.files'

    def home_page_continue(self):
        """
        最开始打开app时，偶尔提示Files app can help you quickly find your photos, videos, documents and more，需要点击继续
        """
        self.u2d_helper.xpath_click('//*[@resource-id="com.google.android.apps.nbu.files:id/agree_button"]', timeout=2, sleep_time=1)


    def swipe_quick_access_list(self):
        """
        滑动快速访问列表
        """
        width, height = self.u2d.window_size()
        recents_list = self.u2d.xpath('//*[contains(@resource-id, "quick_access_")]')
        bounds_y = (recents_list.info['bounds']['top'] + recents_list.info['bounds']['bottom']) / 2
        self.u2d.swipe(width*3/4, bounds_y, width/4, bounds_y, 0.2)
        time.sleep(0.5)
        self.u2d.swipe(width/4, bounds_y, width*3/4, bounds_y, 0.2)
        time.sleep(0.5)

    def open_file_from_quick_access_list(self):
        """
        打开快速访问列表中的文件
        """
        width, height = self.u2d.window_size()
        recents_list = self.u2d.xpath('//*[contains(@resource-id, "quick_access_")]')
        bounds_y = (recents_list.info['bounds']['top'] + recents_list.info['bounds']['bottom']) / 2
        self.u2d.click(width/4, bounds_y)
        time.sleep(0.5)

    def click_folder(self, folder_name='Videos'):
        """
        点击视频文件夹
        """
        self.u2d.xpath(f'//*[@text="{folder_name}"]').click(timeout=1)
        time.sleep(1)
