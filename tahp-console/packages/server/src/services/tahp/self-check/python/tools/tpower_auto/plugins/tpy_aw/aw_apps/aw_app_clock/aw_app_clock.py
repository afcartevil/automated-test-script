# -*- coding: utf-8 -*-
# @Time     : 2025/5/14 15:12
# @Author   : kaiyuan.xie
# @Email    : kaiyuan.xie@transsion.com
# @File     : aw_app_chrome.py
import time

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from tpy_aw.aw_app_base import AwAppBase


class AwAppClock(AwAppBase):
    aw_name = 'clock'
    default_app_package = 'com.transsion.deskclock'

    def set_clock_in_2_min(self):
        self.u2d.xpath('//*[@resource-id="com.transsion.deskclock:id/os_fob_layout"]').all()[0].click()
        time.sleep(1)
        self.u2d.xpath('//*[@resource-id="com.transsion.deskclock:id/menu_item_add"]').click()
        time.sleep(2)
        screen_width, screen_height = self.u2d.window_size()
        min_pos = self.u2d.xpath('//*[@resource-id="com.transsion.deskclock:id/minWheel"]').center()
        hour_pos = self.u2d.xpath('//*[@resource-id="com.transsion.deskclock:id/hourWheel"]').center()
        offset_y = int(screen_height * 0.05)
        if self.u2d.xpath('//*[@resource-id="com.transsion.deskclock:id/minWheel" and (@content-desc="59" or @content-desc="58")]').exists:
            # 不需要滚动
            # offset_y = int(screen_height * 0.1)
            self.u2d.swipe(hour_pos[0], hour_pos[1], hour_pos[0], hour_pos[1] - offset_y)
            time.sleep(2)
            # if self.u2d.xpath('//*[@resource-id="com.transsion.deskclock:id/hourWheel" and @content-desc="23"]').exists:
            # for i in range(15):
            #     self.u2d.swipe(min_pos[0], min_pos[1], min_pos[0], min_pos[1] - offset_y)
            # time.sleep(2)
        # 2min比1min稳妥
        self.u2d.click(min_pos[0], min_pos[1] + offset_y)
        self.u2d.click(min_pos[0], min_pos[1] + offset_y)
        time.sleep(1)
        self.u2d.xpath('//*[@resource-id="com.transsion.deskclock:id/save_alarm"]').click()