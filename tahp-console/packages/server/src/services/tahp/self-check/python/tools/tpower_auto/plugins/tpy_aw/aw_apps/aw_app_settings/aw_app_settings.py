import time

from powertrde.utils.trde import adb


from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase


class SettingsLocator(U2SelectorLocator):
    text_default_phone_app_pop = U2Selector().xpath_text_contains('default phone app?').bind()
    btn_phone_app = U2Selector().xpath_text('Phone app').bind()
    btn_cancel = U2Selector().xpath('//android.widget.Button[@text="Cancel"]').bind()
    btn_param_text = U2Selector().xpath_text('{param_text}').bind()
    user_account = U2Selector().text("Users & Accounts").bind()
    google_account =  U2Selector().text("Google Account").bind()
class AwAppSettings(SettingsLocator, AwAppBase):
    aw_name = 'Settings'
    default_app_package = 'com.android.settings'

    def check_to_cancel_default_phone_app_settings_pop(self):
        """
        检查在点击切换电话app时，是否有弹窗。有弹窗则点击cancel，会自动跳转到系统内部选择。（没有从弹窗选择的需求建议直接调用adb命令设置）
        """
        if self.text_default_phone_app_pop.wait(timeout=2):
            self.btn_cancel.click_wait(timeout=1)

    def set_default_phone_app_in_default_apps_page(self, target_phone_app='(System default)'):
        """
        在跳转到系统设置之后，选择电话使用的默认的手机app
        """
        self.btn_phone_app.click_wait(timeout=4)
        self.btn_param_text.with_params(param_text=target_phone_app).click_wait(timeout=2)

    def enter_user_account(self):
        self.restart_app(self.default_app_package)
        self.u2d(resourceId ='com.android.settings:id/main_content').scroll.to(text="Users & Accounts")
        self.user_account.click_wait()
    def sing_in_google_account(self):
        self.u2d(text="Google").click()
        self.google_account.click_wait(timeout=5)
        self.u2d.xpath('(//android.widget.TextView)[5]').click()
        self.u2d.xpath('//android.widget.EditText').set_text("kelianglai001@gmail.com")
        self.u2d.xpath('//android.widget.EditText').wait(timeout=30)
        self.u2d.xpath('//android.widget.EditText').set_text("yslkl20170615")
        if self.u2d.xpath('Add phone number?').exists:
            self.u2d(resourceId = "view_container").scroll.to(text= "Yes, I’m in")
            self.u2d(text="Yes, I’m in").click_exists(timeout=5)
        self.u2d(text = "I agree").click_exists(timeout=10)
        self.u2d(description="Don't turn on").click_exists(timeout=15)
        self.u2d(text="Accept").click_exists(timeout=15)

    def check_is_login_success(self,username):
        if not self.u2d(text=username).exists:
            raise Exception("login google fail please check network")







    def set_hotspot_name_and_password(self, name, password):
        """
        设置热点的名字和密码
        """
        self.u2d.xpath('//android.widget.TextView[@text="Hotspot & Connections"]').click()
        time.sleep(1)
        self.u2d.xpath('//android.widget.TextView[@text="Personal Hotspot"]').click()
        time.sleep(1)
        self.u2d.xpath('//android.widget.TextView[@text="Hotspot Settings"]').click()
        time.sleep(1)

        self.u2d.xpath('//android.widget.EditText').all()[0].click()
        adb.exec_cmd(self.device_id, 'input keyevent KEYCODE_MOVE_END')
        for i in range(25):
            adb.exec_cmd(self.device_id, 'input keyevent KEYCODE_DEL')
        self.u2d_helper.input_text(self.u2d, f"{name}")
        time.sleep(1)
        self.u2d.xpath('//android.widget.EditText').all()[1].click()
        for i in range(20):
            adb.exec_cmd(self.device_id, 'input keyevent KEYCODE_DEL')
        self.u2d_helper.input_text(self.u2d, f"{password}")
        time.sleep(1)
        self.u2d.xpath('//*[@resource-id="com.transsion.settings.wifi:id/bt_save_hostap"]').click()

        return name