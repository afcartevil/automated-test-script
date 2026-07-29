import time

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_apps.aw_app_phone.aw_app_phone_vivo import AwAppPhoneVivo


class PhoneSamsungLocator(U2SelectorLocator):
    btn_go_to_settings = U2Selector().xpath('//android.widget.TextView[@text="Go to Settings"]').bind()
    btn_param_text = U2Selector().xpath_text('{param_text}').bind()
    number_one_button = U2Selector().xpath('//*[@text="1"]').bind()


class AwAppPhoneSamsung(PhoneSamsungLocator, AwAppPhoneVivo):
    variant_key = 'Samsung'
    default_app_package = 'com.google.android.dialer'


    def go_to_settings_set_as_default_dialer(self):
        """
        如果此时默认电话是其他电话app，进入phone时会提示go to settings。 可以点击且跳转至settings做选择
        """
        self.btn_go_to_settings.click_wait()

    def check_at_homepage(self):
        if self.u2d.xpath('//*[@content-desc="Call" or @resource-id="com.samsung.android.dialer:id/dialButtonImage"]').exists:
            t_log.debug('已在Phone主页')
        else:
            raise XPathElementNotFoundError('未在Phone主页')
        time.sleep(2)

    def set_as_default_phone(self):
        """
        设置为默认app
        """
        self.u2d_helper.set_default_browser(self.default_app_package)

    def switch_to_recents_page(self):
        """
        跳转到dialer界面
        """
        if self.u2d.xpath('//*[@text="Keypad"]').exists:
            self.u2d.xpath('//*[@text="Keypad"]').click()
        else:
            raise XPathElementNotFoundError('找不到Recents页')
        time.sleep(2)

    def hide_dial_pad(self):
        """
        隐藏拨号盘  暂时无法隐藏
        """
        ...

    def expand_dial_pad(self):
        """
        展开拨号盘  暂时无法展开
        """
        ...

    def make_a_call(self, phone_number):
        """
        打电话
        """
        self.u2d_helper.click_wait('//*[@text="Keypad"]', pre_wait=1, timeout=5, post_wait=1)
        for i in phone_number:
            print(i)
            self.u2d_helper.assert_icon_exist('text', i, click=True)
            time.sleep(0.5)
        self.u2d_helper.assert_icon_exist('xpath', '//*[@content-desc="Call" or @resource-id="com.samsung.android.dialer:id/dialButtonImage"]', click=True)
        time.sleep(2)
        result, _ = self.u2d_helper.assert_icon_exist('xpath','//*[@resource-id="com.samsung.android.incallui:id/voice_disconnect_button" or @content-desc="End call"]')
        if not result:
            raise XPathElementNotFoundError('找不到结束通话按钮')

    def end_call(self):
        result, end_call = self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.samsung.android.incallui:id/voice_disconnect_button" or @content-desc="End call"]')
        if result:
            end_call.click()

    def click_speaker(self):
        """
        通话中点击外放
        """
        self.u2d_helper.click_wait('//*[@text="Speaker"]', timeout=5, post_wait=1)
