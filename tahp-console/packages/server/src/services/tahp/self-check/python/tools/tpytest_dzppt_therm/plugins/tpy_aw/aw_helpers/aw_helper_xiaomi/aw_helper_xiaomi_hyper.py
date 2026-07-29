from powertrde.framework.logs_protocol import logs_p
from powertrde.utils.trde import adb
from tpy_aw.aw_apps.aw_app_desimu.aw_app_desimu import AwAppDesimu
from tpy_aw.aw_apps.aw_app_googlemessages.aw_app_googlemessages import AwAppGoogleMessages
from tpy_aw.aw_helpers.aw_helper_xiaomi.aw_helper_xiaomi import AwHelperXiaomi


class AwHelperXiaomiHyper(AwHelperXiaomi):
    variant_key = 'hyper'


    def check_switch_language_en(self):
        """
        Set the system language to English
        """
        if 'en' not in adb.exec_cmd(self.device_id, 'getprop persist.sys.locale')[0].strip():
            logs_p().log('The phone system language is not set to English, try setting it to English.')
            adb.exec_cmd(self.u2d.serial, 'am start -a android.settings.LOCALE_SETTINGS')
            self.u2d.swipe(0.5, 0.6, 0.5, 0.2)
            eng = self.u2d(textContains='English (United States)').wait(timeout=2)
            if eng:
                self.u2d(textContains='English (United States)').click()
                self.u2d.sleep(1)
                self.u2d(resourceId='com.android.settings:id/btn_positive').click_exists()
                self.u2d(resourceId='android:id/button1').click_exists()
            else:
                self.u2d(resourceId='com.android.settings:id/add_language').click()
                self.u2d.sleep(1)
                self.u2d(textContains='English (United States)').click()
                self.u2d.sleep(1)
                self.u2d(resourceId='com.android.settings:id/btn_positive').click_exists()
                self.u2d(resourceId='android:id/button1').click_exists()

            self.u2d.sleep(1)
            if 'en' not in adb.exec_cmd(self.device_id, 'getprop persist.sys.locale')[0].strip():
                raise Exception("set system language to English！")
            else:
                logs_p().log('set system language to English successfully！')


    def insert_sms(self, count=1):
        aw_google_messages: AwAppGoogleMessages = self.get_casted_app_aw(AwAppGoogleMessages)
        adb.set_message(aw_google_messages.app_package)
        aw_desimu: AwAppDesimu = self.get_casted_app_aw(AwAppDesimu)
        aw_desimu.enter_app()
        aw_desimu.set_user_data(message_count=count)
        aw_desimu.stop_app()
        self.u2d.press("back")
        if self.u2d(text="Set as default").wait(timeout=5):
            el_info = self.u2d(text="Set as default").info
            if not bool(el_info.get('enabled', False)):
                self.u2d(text="Cancel").click()

