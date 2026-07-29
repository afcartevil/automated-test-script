#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@Project ：dz_auto_env 
@File    ：AwAppGooglePhotos
@Author  ：kai.zhao
@Date    ：2025/8/21 10:57 
"""
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase


class GooglePhotosLocator(U2SelectorLocator):
    ...


class AwAppGooglePhotos(GooglePhotosLocator, AwAppBase):
    aw_name = 'GooglePhotos'
    default_app_package = 'com.google.android.apps.photos'


