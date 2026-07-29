# -*- coding: utf-8 -*-
# @Time     : 2025/8/25 16:39
# @Author   : kaiyuan.xie
# @Email    : kaiyuan.xie@transsion.com
# @File     : aw_app_gallerygo.py
import time

from powertrde.framework.tran_logger import t_log
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase


class AwAppGalleryGo(AwAppBase):
    aw_name = 'GalleryGo'
    default_app_package = 'com.google.android.apps.photosgo'
