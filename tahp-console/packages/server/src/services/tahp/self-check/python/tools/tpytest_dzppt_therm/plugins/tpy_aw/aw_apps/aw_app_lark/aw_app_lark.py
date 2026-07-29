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

    def check_homepage(self):
        self.u2d_helper.click_wait('//*[@text="Accept"]', pre_wait=1, timeout=5, post_wait=1, no_raise=True)
        self.u2d_helper.click_wait('//*[@text="No, thanks"]', pre_wait=1, timeout=5, post_wait=1, no_raise=True)
        result = self.u2d_helper.wait_ui_obj('//*[@text="Messenger"]')
        if not result:
            raise Exception('The Feishu does not have a login account!')

    def create_meeting(self):
        self.u2d_helper.click_wait('//*[@text="Messenger"]', pre_wait=1, timeout=5, post_wait=1)
        self.u2d_helper.click_wait('//*[@resource-id="com.larksuite.suite:id/function_btn_2"]', pre_wait=1, timeout=5, post_wait=1)
        self.u2d_helper.click_wait('//*[@text="New Video Meeting"]', pre_wait=1, timeout=5, post_wait=1)
        self.u2d_helper.click_wait('//*[@text="Meet Now"]', pre_wait=1, timeout=3, post_wait=1)
        self.u2d_helper.click_wait('//*[@text="Confirm"]', pre_wait=1, timeout=3, post_wait=3, no_raise=True)
        self.u2d_helper.click_wait('//*[@text="Meeting Info"]', pre_wait=1, timeout=5, post_wait=3)
        element = self.u2d(resourceId="com.larksuite.suite:id/meeting_info_meetingid")
        if element.exists:
            meeting_id = element.info['text'].replace(" ", "")
            time.sleep(1)
            self.u2d_helper.press_back_key()
        else:
            raise Exception("Meeting ID not found")

        return meeting_id

    def join_meeting(self, meeting_id):
        self.u2d_helper.click_wait('//*[@text="Messenger"]', pre_wait=1, timeout=5, post_wait=1)
        self.u2d_helper.click_wait('//*[@resource-id="com.larksuite.suite:id/function_btn_2"]', pre_wait=1, timeout=5, post_wait=1)
        self.u2d_helper.click_wait('//*[@text="Join Video Meeting"]', pre_wait=1, timeout=5, post_wait=1)
        self.u2d_helper.click_wait('//*[@text="Meeting ID"]', pre_wait=1, timeout=5, post_wait=1)
        self.u2d_helper.input_text(meeting_id)
        self.u2d_helper.click_wait('//*[@text="Join Meeting"]', pre_wait=1, timeout=5, post_wait=1)
        self.u2d_helper.click_wait('//*[@resource-id="com.larksuite.suite:id/fv_orientation_switcher_folder_icon"]', pre_wait=1, timeout=5, post_wait=1)

    def leave_meeting(self):
        self.u2d_helper.click_wait('//*[@resource-id="com.larksuite.suite:id/image_mobile_hangup"]', pre_wait=1, timeout=5, post_wait=1)
        self.u2d_helper.click_wait('//*[@text="Leave Meeting"]', pre_wait=1, timeout=5, post_wait=1, no_raise=True)


    def share_doc(self):
        self.u2d_helper.click_wait('//*[@text="More"]', pre_wait=1, timeout=5, post_wait=1)
        self.u2d_helper.click_wait('//*[@text="Share"]', pre_wait=1, timeout=5, post_wait=1)
        time.sleep(3)
        btn_docs = self.u2d.xpath('//*[@resource-id="com.larksuite.suite:id/doc_type"]').all()
        if not btn_docs:
            raise Exception('There are no docs documents available for sharing!')
        self.u2d.xpath('//*[@resource-id="com.larksuite.suite:id/doc_type"]').all()[0].click()
