import time

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase


class PhoneLocator(U2SelectorLocator):
    btn_go_to_settings = U2Selector().xpath('//android.widget.TextView[@text="Go to Settings"]').bind()
    btn_param_text = U2Selector().xpath_text('{param_text}').bind()
    number_one_button = U2Selector().xpath('//*[@text="1"]').bind()

class AwAppPhone(PhoneLocator, AwAppBase):
    aw_name = 'Phone'
    default_app_package = 'com.sh.smart.caller'

    def go_to_settings_set_as_default_dialer(self):
        """
        如果此时默认电话是其他电话app，进入phone时会提示go to settings。 可以点击且跳转至settings做选择
        """
        self.btn_go_to_settings.click_wait()

    def check_at_homepage(self):
        result, _ = self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.sh.smart.caller:id/os_foot_opt_bar_container"]')
        if result:
            t_log.debug('已在Phone主页')
        else:
            raise XPathElementNotFoundError('未在Phone主页')
        time.sleep(2)

    def set_as_default_phone(self):
        """
        设置为默认app
        """
        self.u2d_helper.set_default_browser(self.app_package)

    def switch_to_recents_page(self):
        """
        跳转到Recent界面
        """
        result, recents_page = self.u2d_helper.assert_icon_exist('xpath',
                                                                 '//*[@resource-id="com.sh.smart.caller:id/os_foot_opt_bar_container"]/android.widget.RelativeLayout[1]'
                                                                 ' | //*[@text="Recents"]')
        if result:
            recents_page.click()
        else:
            raise XPathElementNotFoundError('找不到Recents页')
        time.sleep(2)

    def switch_to_contacts_page(self):
        """
        跳转到联系人界面
        """
        result, contacts_page = self.u2d_helper.assert_icon_exist('xpath',
                                                                  '//*[@resource-id="com.sh.smart.caller:id/os_foot_opt_bar_container"]/android.widget.RelativeLayout[2]'
                                                                  ' | //*[@text="Contacts"]')
        if result:
            contacts_page.click()
        else:
            raise XPathElementNotFoundError('找不到Contacts页')
        time.sleep(2)

    def hide_dial_pad(self):
        """
        隐藏拨号盘
        """
        dial_pad = self.u2d.xpath('//*[@resource-id="com.sh.smart.caller:id/dialpad_hide" or @resource-id="com.sh.smart.caller:id/fab"]').wait(timeout=1)
        if dial_pad:
            self.u2d.xpath('//*[@resource-id="com.sh.smart.caller:id/dialpad_hide" or @resource-id="com.sh.smart.caller:id/fab"]').click()
            time.sleep(1)

    def expand_dial_pad(self):
        result, dial_pad = self.u2d_helper.assert_icon_exist('xpath', '//*[@content-desc="Expand dial pad"]')
        if result:
            dial_pad.click()
        time.sleep(1)

    def make_a_call_via_adb(self, phone_number):
        """
        adb打电话
        """
        self.u2d_helper.make_call(phone_number)

    def input_phone_number(self, phone_number):
        """
        输入电话号码
        """
        for i in phone_number:
            if i == "+":
                self.u2d.xpath('//*[@text="0"]').long_click()
                continue
            self.u2d_helper.assert_icon_exist('text', i, click=True)
            time.sleep(0.5)
        self.u2d_helper.assert_icon_exist('xpath',
                                          '//*[@resource-id="com.sh.smart.caller:id/dialpad_floating_action_button"] | //*[@resource-id="com.sh.smart.caller:id/elastic_duo_sim_card_panel"]',
                                          click=True)
        time.sleep(2)

    def make_a_call(self, phone_number):
        """
        打电话
        """
        self.input_phone_number(phone_number)
        result, _ = self.u2d_helper.assert_icon_exist('xpath',
                                                      '//*[@resource-id="com.sh.smart.caller:id/incall_end_call"]')
        if not result:
            raise XPathElementNotFoundError('找不到结束通话按钮')

    def end_call(self):
        if not adb.is_screen_on(self.u2d_helper.device_id):
            self.u2d_helper.screen_on_and_unlock()
            time.sleep(1)

        result, end_call = self.u2d_helper.assert_icon_exist('xpath',
                                                             '//*[@resource-id="com.sh.smart.caller:id/incall_end_call"]')
        if result:
            end_call.click()
        adb.press_end_call_key(self.device_id)
        self.u2d_helper.end_system_phone_call()

    def click_call_button(self, force_click=False):
        self.u2d_helper.click_wait('//*[@resource-id="com.sh.smart.caller:id/incall_end_call"]',
                                   no_raise=not force_click)

    def start_recording(self):
        """
        通话中点击录音
        """
        self.u2d_helper.click_wait(
            '//*[@content-desc="Start Recording"]',
            timeout=5, post_wait=1)

    def click_speaker(self):
        """
        通话中点击外放
        """
        self.u2d_helper.click_wait(
            '//*[@resource-id="com.sh.smart.caller:id/incall_speaker_button"] | //*[@content-desc="Speaker, is Off"]',
            timeout=5, post_wait=1)

    def click_mute(self):
        """
        通话中点击静音
        """
        self.u2d_helper.click_wait(
            '//*[@content-desc="Unmuted"] | //*[@resource-id="com.sh.smart.caller:id/two_button"]',
            timeout=5, post_wait=1)

    def click_contacts(self, index=-1, name=None):
        """
        从0开始，可以从index搜索和name搜索
        """
        if index < 0 and not name:
            raise Exception("Please input the index or name for contact")

        if index >= 0:
            self.u2d.xpath(f'//*[@resource-id="com.sh.smart.caller:id/click_target"] | '
                           f'//*[@resource-id="com.sh.smart.caller:id/contact_name"] | '
                           f'//*[@resource-id="com.sh.smart.caller:id/os_swipe_layout"] | '
                           f'//*[@text="Carlcare Service Hotline"]').all()[index].click()
        elif name:
            self.u2d_helper.click_wait(f'//*[@text="{name}"]', timeout=5, post_wait=1)

    def check_and_cancel_whatsapp_enhancement(self):
        """
        拨号盘键旁边有个whatsapp按钮，检查存在则取消
        """
        if self.u2d.xpath('//*[@content-desc="WhatsApp"]').exists:
            self.u2d_helper.click_wait('//*[@content-desc="Settings"]', post_wait=1)
            self.u2d_helper.click_wait('//*[@text="WhatsApp Enhancement"]', post_wait=1)
            self.u2d_helper.press_back_key()


    def add_a_new_contact(self, contact_name, country_code, phone_number):
        """
        增加一个新的联系人
        """
        try:
            self.switch_to_contacts_page()
            time.sleep(1)
            self.u2d.xpath('//*[@resource-id="com.sh.smart.caller:id/fab"]').click()
            time.sleep(1)

            self.check_complete_action()

            time.sleep(1)
            self.u2d.xpath('//android.widget.EditText[@text="First Name"]').click()
            self.u2d_helper.input_text(contact_name)
            time.sleep(1)
            self.und_u2.click_back()
            self.u2d_helper.click_wait('//android.widget.EditText[@text="Phone"]', post_wait=1)
            self.u2d.send_keys("+" + country_code + phone_number)
            time.sleep(1)
            self.u2d_helper.restore_keyboard_ime()
            time.sleep(1)
            if not self.u2d.xpath('//*[@resource-id="com.sh.smart.caller:id/menu_save_btn"]').exists:
                self.und_u2.click_back()
            self.u2d.xpath('//*[@resource-id="com.sh.smart.caller:id/menu_save_btn"]').click()
            time.sleep(1)
        except:
            raise Exception('Failed to add a new friends, you can add it manually(添加联系人失败，请手动添加)')

    def delete_contacts(self, contact_name):
        """
        删除所有指定名字的联系人
        """
        try:
            self.switch_to_contacts_page()
            self.u2d.xpath('//*[@resource-id="com.sh.smart.caller:id/text_click"]').click()

            self.u2d_helper.input_text(contact_name)
            time.sleep(1)
            con_num = self.u2d.xpath('//*[@resource-id="com.sh.smart.caller:id/primary"]').all()

            for i in range(len(con_num)):
                self.u2d.xpath('//*[@resource-id="com.sh.smart.caller:id/primary"]').click()
                self.u2d_helper.click_wait('//*[@content-desc="More options"]', post_wait=1)
                self.u2d_helper.click_wait('//android.widget.TextView[@text="Delete Contact"]', post_wait=1)
                time.sleep(1)
                self.u2d.xpath('//android.widget.Button[@text="Delete"]').click_exists(timeout=2)
                self.u2d.xpath('//android.widget.Button[@text="OK"]').click_exists(timeout=2)
                self.u2d.xpath('//android.widget.Button[@text="Hide Contact"]').click_exists(timeout=2)
        except Exception:
            raise Exception('Failed to delete a new friends, you can delete it manually(删除联系人失败，请手动删除)')

    def check_complete_action(self):
        """
        用launcher打开可能会有个弹窗，需要兼容
        """
        if self.u2d.xpath('//*[@text="Complete action using"]').exists:
            for i in range(3):
                if self.u2d.xpath('//*[@text="Phone"]').exists:
                    self.u2d.xpath('//*[@text="Phone"]').click()
                    time.sleep(1)
                    self.u2d.xpath('//*[@text="Always"]').click()
                    time.sleep(1)
                    return
                self.u2d.swipe(0.9, 0.7 ,0.2, 0.7)
                time.sleep(2)
            else:
                raise Exception('Failed to complete action')


    def answer_call(self):
        """
        接听电话
        """
        self.u2d.xpath('//*[@resource-id="com.transsion.dynamicbar:id/action2"]').click(timeout=30)

    def answer_call_full_screen(self):
        """
        锁屏时的电话
        """
        self.u2d_helper.wait_ui_obj('//*[@resource-id="com.sh.smart.caller:id/callControlView"]', timeout=10)
        center = self.u2d_helper.get_bounds_corner('//*[@resource-id="com.sh.smart.caller:id/callControlView"]', "center")
        self.u2d.drag(center[0]-50, center[1], center[0]+400, center[1])

    def click_search_btn(self):
        self.u2d_helper.click_wait('//android.widget.TextView[@text="Search"]', timeout=5, post_wait=1)
