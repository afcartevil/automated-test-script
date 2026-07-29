#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@Project ：dz_auto_env 
@File    ：aw_app_googlemessages
@Author  ：xingzhi.chen
@Date    ：2025/8/20 19:56 
"""
import time

from powertrde.framework.tran_logger import t_log
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase

class GoogleMessagesLocator(U2SelectorLocator):
    start_chat_btn = U2Selector().xpath('//*[@resource-id="com.google.android.apps.messaging:id/start_chat_fab"]').bind()


class AwAppGoogleMessages(GoogleMessagesLocator, AwAppBase):
    aw_name = 'GoogleMessages'
    default_app_package = 'com.google.android.apps.messaging'

    def start_chat(self):
        self.start_chat_btn.click()
        time.sleep(2)


