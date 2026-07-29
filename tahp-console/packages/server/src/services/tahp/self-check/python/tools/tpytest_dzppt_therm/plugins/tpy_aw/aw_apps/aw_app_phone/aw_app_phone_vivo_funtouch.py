import time

from uiautomator2 import XPathElementNotFoundError

from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_apps.aw_app_phone.aw_app_phone_vivo import AwAppPhoneVivo


class PhoneVivoFuntouchLocator(U2SelectorLocator):
    btn_go_to_settings = U2Selector().xpath('//android.widget.TextView[@text="Go to Settings"]').bind()
    btn_param_text = U2Selector().xpath_text('{param_text}').bind()
    number_one_button = U2Selector().xpath('//*[@text="1"]').bind()


class AwAppPhoneVivoFuntouch(PhoneVivoFuntouchLocator, AwAppPhoneVivo):
    aw_nickname = 'VivoFuntouchPhone'
    variant_key = 'vivo_funtouch'
    default_app_package = 'com.android.dialer'

    def switch_to_recents_page(self):
        """
        跳转到dialer界面
        """
        dialer_btn = self.u2d.xpath('//*[@text="Dial"]')
        if dialer_btn.exists:
            dialer_btn.click(timeout=5)
        else:
            raise Exception("跳转到dialer界面失败！")

    def expand_dial_pad(self):
        result, dial_pad = self.u2d_helper.assert_icon_exist('xpath',
                                                             '//*[@resource-id="com.android.dialer:id/fab"]')
        if result:
            dial_pad.click()
        time.sleep(1)

    def make_a_call(self, phone_number):
        """
        打电话
        """
        for i in phone_number:
            print(i)
            self.u2d_helper.assert_icon_exist('text', i, click=True)
            time.sleep(0.5)
        self.u2d_helper.click_wait('//*[@resource-id="com.android.dialer:id/dialButton"]', no_raise=True)
        time.sleep(2)
        result, _ = self.u2d_helper.assert_icon_exist('xpath',
                                                      '//*[@resource-id="com.android.incallui:id/end_button"]')
        if not result:
            raise XPathElementNotFoundError('找不到结束通话按钮')

    def end_call(self):
        result, end_call = self.u2d_helper.assert_icon_exist('xpath',
                                                             '//*[@resource-id="com.android.incallui:id/end_button"]')
        if result:
            end_call.click()

    def click_speaker(self):
        """
        通话中点击外放
        """
        self.u2d_helper.click_wait('//*[@resource-id="com.android.incallui:id/audio_dtmf_button"]',
                                   timeout=5, post_wait=1)
