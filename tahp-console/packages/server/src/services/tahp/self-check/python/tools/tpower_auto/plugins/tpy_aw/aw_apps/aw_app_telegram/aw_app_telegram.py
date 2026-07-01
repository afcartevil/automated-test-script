import time
import random

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from tpy_aw.aw_app_base import AwAppBase


class AwAppTelegram(AwAppBase):
    aw_name = 'Telegram'
    default_app_package = 'org.telegram.messenger'

    def delete_friend(self, contact_name):
        """
        删除好友
        """
        self.u2d.xpath(f'//android.widget.TextView[@text="{contact_name}"]').click_exists()
        time.sleep(1)
        self.u2d.xpath('//*[@content-desc="More options"]').click()
        time.sleep(1)
        self.u2d.xpath('//android.widget.TextView[@text="Delete contact"]').click()
        time.sleep(1)
        self.u2d.xpath('//android.widget.TextView[@text="Delete"]').click()
        self.und_u2.click_back(2)

    def add_new_contact(self, name, country_code, phone_number):
        """
        新增好友
        """
        self.u2d.xpath('//android.widget.TextView[@text="New Contact"]').click()
        time.sleep(1)
        self.u2d.xpath('//android.widget.EditText').all()[0].click()
        time.sleep(1)
        for i in range(5):
            adb.exec_cmd(self.device_id, 'input keyevent 67')
        u2utils.input_text(self.u2d, name)
        self.u2d.xpath('//android.widget.EditText').all()[2].click()
        u2utils.input_text(self.u2d, country_code)
        self.u2d.xpath('//android.widget.EditText').all()[3].click()
        u2utils.input_text(self.u2d, phone_number)
        time.sleep(2)
        self.u2d.xpath('//android.widget.TextView[@text="Create Contact"]').click()
        self.u2d_helper.wait_ui_obj(f'//android.widget.TextView[@text="{name}"]', post_wait=1)

    def add_only_one_contact(self, name, country_code, phone_number):
        """
        新增一个唯一名字的好友，会删除其他同名的
        """
        friend = self.u2d.xpath(f'//android.widget.TextView[@text="{name}"]')
        if friend.exists:
            if len(friend.all()) == 1:
                friend.click()
                self.u2d_helper.click_wait(f'//android.widget.TextView[@text="{name}"]', post_wait=1, timeout=4)
                time.sleep(1)
                # 获取联系人号码
                if self.u2d(textContains='+').exists:
                    contact_text2 = self.u2d(textContains='+').get_text()
                    country_code2, phone_number2 = self.u2d_helper.get_phone_number_and_countrycode(contact_text2)

                    # 是否为相同联系人
                    if phone_number2 == phone_number:
                        self.und_u2.click_back(2)
                    else:
                        self.delete_friend(name)

                        self.add_new_contact(name, country_code, phone_number)
            # 多个好友的情况, 全删
            else:
                for i in range(len(friend.all())):
                    self.delete_friend(name)

        else:
            self.add_new_contact(name, country_code, phone_number)
