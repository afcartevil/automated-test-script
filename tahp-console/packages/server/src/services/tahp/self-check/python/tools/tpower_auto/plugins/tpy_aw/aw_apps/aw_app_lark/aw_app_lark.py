# -*- coding: utf-8 -*-
# @Time     : 2025/5/14 15:12
# @Author   : kaiyuan.xie
# @Email    : kaiyuan.xie@transsion.com
# @File     : aw_app_launcher.py
import time

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from tpy_aw.aw_app_base import AwAppBase


class AwAppLark(AwAppBase):
    aw_name = 'Lark'
    default_app_package = 'com.larksuite.suite'
