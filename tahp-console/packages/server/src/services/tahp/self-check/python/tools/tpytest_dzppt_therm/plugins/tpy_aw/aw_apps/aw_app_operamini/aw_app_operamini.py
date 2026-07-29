#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@Project ：dz_auto_env 
@File    ：aw_app_operamini
@Author  ：xingzhi.chen
@Date    ：2025/8/1 14:43 
"""

import time
import random

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from tpy_aw.aw_app_base import AwAppBase


class AwAppOperaMini(AwAppBase):
    aw_name = 'OperaMini'

    def search_website(self, website):
        """
        搜索网站
        :param website: 要搜索的网站
        """
        self.u2d.xpath('//*[@resource-id="com.opera.mini.native:id/url_field"]').click()
        u2utils.input_text(self.u2d, website)
        time.sleep(2)
        adb.exec_cmd(self.device_id, 'input keyevent 66')
        time.sleep(10)
