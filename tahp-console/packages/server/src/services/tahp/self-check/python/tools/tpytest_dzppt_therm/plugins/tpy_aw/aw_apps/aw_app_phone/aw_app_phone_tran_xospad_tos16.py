
from tpy_aw.aw_apps.aw_app_phone.aw_app_phone import AwAppPhone


class AwAppPhoneTranssionXospadTos16(AwAppPhone):
    aw_name = 'Phone'
    default_app_package = 'com.sh.smart.caller'

    def click_search_btn(self):
        self.u2d_helper.click_wait('//*[@resource-id="com.sh.smart.caller:id/enter_search"]', timeout=5, post_wait=1)
