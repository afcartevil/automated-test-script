#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@Project ：dz_auto_env 
@File    ：aw_app_messages
@Author  ：kai.zhao
@Date    ：2025/8/20 19:56 
"""
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase

class MessagesLocator(U2SelectorLocator):
    start_chat_btn = U2Selector().xpath('//*[@resource-id="com.transsion.smartmessage:id/start_new_conversation_button"]').bind()


class AwAppMessages(MessagesLocator, AwAppBase):
    aw_name = 'Messages'
    default_app_package = 'com.transsion.smartmessage'


