# -*- coding: utf-8 -*-
# @Time     : 2025/7/1 21:11
# @Author   : kaiyuan.xie
# @Email    : kaiyuan.xie@transsion.com
# @File     : aw_app_meituan.py
import time

from tpy_aw.aw_app_base import AwAppBase


class AwAppMeituan(AwAppBase):
    aw_name = 'Meituan'
    default_app_package = 'com.sankuai.meituan'

    def tt(self, template_key: str, debug_fallback_value=None):
        """
        同 get_typed_template
        从类级别的“模板录制”中获取录制记录
        """
        return self.get_typed_template(template_key, debug_fallback_value)

    def click_message_tab(self):
        """
        点击消息tab
        """
        self.u2d(descriptionContains='消息').click(timeout=1)
        time.sleep(1)

    def click_me_tab(self):
        """
        点击我的tab
        """
        self.u2d.xpath('//*[@content-desc="我的"]').click(timeout=1)
        time.sleep(2)

    def click_home_tab(self):
        """
        点击首页tab
        """
        self.u2d_helper.und_u2.click_match_template(self.tt('home_icon'), target_score=0.9, limit_area=(0, 0.85, 0.5, 1))
        time.sleep(2)
