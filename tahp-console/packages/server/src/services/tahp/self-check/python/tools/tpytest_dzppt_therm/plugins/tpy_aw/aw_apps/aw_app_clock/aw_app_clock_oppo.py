# -*- coding: utf-8 -*-
# @Time     : 2025/5/14 15:12
# @Author   : kaiyuan.xie
# @Email    : kaiyuan.xie@transsion.com
# @File     : aw_app_chrome.py

from tpy_aw.aw_app_base import AwAppBase
class ClockOppoLocator:
    pass

class AwAppClock(ClockOppoLocator,AwAppBase):
    aw_nickname = 'OppoClock'
    variant_key = 'oppo'
    aw_name = 'clock'
    default_app_package = 'com.coloros.alarmclock'

