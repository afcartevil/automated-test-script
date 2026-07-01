# -*- coding: utf-8 -*-
# @Time     : 2025/7/6 15:12
# @Author   : kaiyuan.xie
# @Email    : kaiyuan.xie@transsion.com
# @File     : aw_app_calendar.py
import time

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from tpy_aw.aw_app_base import AwAppBase


class AwAppCalendar(AwAppBase):
    aw_name = 'Calendar'
    default_app_package = 'com.transsion.calendar'

    def click_calendar_tab(self):
        """
        点击日历tab
        """
        self.u2d.xpath('//*[@text="Calendar"]').click()
        time.sleep(2)

    def click_important_days_tab(self):
        """
        点击重要日期tab
        """
        self.u2d.xpath('//*[@text="Important Days"]').click()
        time.sleep(2)

    def create_event(self):
        """
        创建事件(右上角+号)
        """
        self.u2d.xpath('//*[@resource-id="com.transsion.calendar:id/action_create_event" or @content-desc="Add schedule"]').click()
        time.sleep(2)
