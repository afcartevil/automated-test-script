# -*- coding: utf-8 -*-
# @Time     : 2025/5/14 15:12
# @Author   : kaiyuan.xie
# @Email    : kaiyuan.xie@transsion.com
# @File     : aw_app_launcher.py
import time

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from tpy_aw.aw_app_base import AwAppBase


class AwAppTranssioner(AwAppBase):
    aw_name = 'Transsioner'
    default_app_package = 'com.ss.android.lark.transsion'

    def click_docs_tab(self):
        """
        点击文档tab
        """
        self.u2d.xpath('//*[@text="Docs"] | //*[@text="云文档"]').click(timeout=1)
        time.sleep(2)

    def click_message_tab(self):
        """
        点击消息tab
        """
        self.u2d.xpath('//*[@text="Messenger"] | //*[@text="消息"]').click(timeout=1)
        time.sleep(2)
