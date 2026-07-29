import time

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from tpy_aw.aw_apps.aw_app_phone.aw_app_phone import AwAppPhone


class AwAppPhoneOppo(AwAppPhone):
    variant_key = 'oppo'
    default_app_package = 'com.google.android.dialer'

    def go_to_settings_set_as_default_dialer(self):
        """
        如果此时默认电话是其他电话app，进入phone时会提示go to settings。 可以点击且跳转至settings做选择
        """
        self.btn_go_to_settings.click_wait()

    def check_at_homepage(self):
        if self.u2d.xpath('//*[@text="All" or text="Add" or @content-desc="key pad"]').exists:
            t_log.debug('已在Phone主页')
        else:
            raise XPathElementNotFoundError('未在Phone主页')
        time.sleep(2)

    def set_as_default_phone(self):
        """
        设置为默认app
        """
        # TODO
        self.u2d_helper.set_default_browser(self.default_app_package)

    def switch_to_contacts_page(self):
        """
        跳转到联系人界面
        """
        if self.u2d.xpath('//*[@text="Contacts"]').exists:
            self.u2d.xpath('//*[@text="Contacts"]').click()
        else:
            raise XPathElementNotFoundError('找不到Contacts页')
        time.sleep(2)

    def switch_to_recents_page(self):
        """
        跳转到dialer界面
        """
        if self.u2d.xpath('//*[@text="Home" or @text="Recents"]').exists:
            self.u2d.xpath('//*[@text="Home" or @text="Recents"]').click()
        else:
            raise XPathElementNotFoundError('找不到Recents页')
        time.sleep(2)

    def hide_dial_pad(self):
        """
        隐藏拨号盘  暂时无法隐藏
        """
        dial_pad = self.u2d.xpath('//*[@resource-id="com.android.contacts:id/close_dialpad" or @content-desc="Close dial pad"]').wait(timeout=1)
        if dial_pad:
            self.u2d.xpath('//*[@resource-id="com.android.contacts:id/close_dialpad" or @content-desc="Close dial pad"]').click()
            time.sleep(1)

    def expand_dial_pad(self):
        """
        展开拨号盘  暂时无法展开
        """
        self.u2d_helper.click_wait('//*[@text="All" or text="Add" or @content-desc="key pad"]', pre_wait=1, post_wait=1, wait_after_click=3)

    def make_a_call(self, phone_number):
        """
        打电话
        """
        self.u2d_helper.click_wait('//*[@text="Keypad" or @content-desc="key pad"]', pre_wait=1, timeout=5, post_wait=1, wait_after_click=1, no_raise=True)
        eng_number = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine']
        for i in phone_number:
            print(i)
            print(eng_number[int(i)])
            if self.u2d.xpath(f'//*[@resource-id="com.android.contacts:id/{eng_number[int(i)]}"]').exists:
                self.u2d.xpath(f'//*[@resource-id="com.android.contacts:id/{eng_number[int(i)]}"]').click()
                continue
            if len(self.u2d.xpath(f'//*[@text="{i}"]').all()) > 1:
                self.u2d.xpath(f'//*[@text="{i}"]').all()[-1].click()
            else:
                self.u2d_helper.assert_icon_exist('text', i, click=True)
            time.sleep(0.5)
        self.u2d_helper.assert_icon_exist('xpath', '//*[@text="Call" or @content-desc="dial" or @resource-id="com.android.contacts:id/single_call_button"]', click=True)
        time.sleep(2)
        result, _ = self.u2d_helper.assert_icon_exist('xpath','//*[@resource-id="end_call_fab_test_tag" or @content-desc="End call" or @content-desc="End"]')
        if not result:
            raise XPathElementNotFoundError('找不到结束通话按钮')

    def end_call(self):
        result, end_call = self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="end_call_fab_test_tag" or @content-desc="End call" or @content-desc="End"]')
        if result:
            end_call.click()

    def click_speaker(self):
        """
        通话中点击外放
        """
        self.u2d_helper.click_wait('//*[@content-desc="Speaker"]', timeout=5, post_wait=1)

