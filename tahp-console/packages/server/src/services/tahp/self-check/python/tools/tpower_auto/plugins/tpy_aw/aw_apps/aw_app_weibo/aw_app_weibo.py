# -*- coding: utf-8 -*-
# @Time     : 2025/7/3 14:35
# @Author   : kaiyuan.xie
# @Email    : kaiyuan.xie@transsion.com
# @File     : aw_app_weibo.py
import time

from powertrde.framework.tran_logger import t_log
from tpy_aw.aw_app_base import AwAppBase


class AwAppWeibo(AwAppBase):
    aw_name = 'Weibo'
    default_app_package = 'com.sina.weibo'

    def click_home_tab(self):
        """
        点击首页tab
        """
        home = self.u2d.xpath('//*[@content-desc="HOME"]').wait(timeout=2)
        if not home:
            self.u2d_helper.press_back_key()
            time.sleep(2)
        self.u2d.xpath('//*[@content-desc="HOME"]').click(timeout=1)
        time.sleep(2)

    def click_a_weibo(self):
        """
        点击一条微博
        """
        self.u2d.xpath('//*[@resource-id="com.sina.weibo:id/contentTextView"]').click(timeout=1)
        time.sleep(1)

    def click_message_tab(self):
        """
        点击消息tab
        """
        self.u2d.xpath('//*[@content-desc="Message"]').click(timeout=1)
        time.sleep(2)
