import datetime
import time

from powertrde.utils.u2_extends import u2utils
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase
from powertrde.utils.trde import adb


class DesimuLocator(U2SelectorLocator):
    ...


class AwAppDesimu(DesimuLocator, AwAppBase):
    aw_name = 'desimu'
    app_package = 'com.transsion.desimu'
    def enter_app(self):
        self.grant_all_runtime_permissions()
        self.u2d_helper.grant_all_useful_permissions(self.app_package)
        self.u2d_helper.restart_app(self.app_package)
        time.sleep(3)
        self.u2d.xpath('//*[@resource-id="android:id/switch_widget"]').click_exists()
        self.u2d_helper.restart_app(self.app_package)
        time.sleep(3)
        if self.u2d(text="Set Desimu as your default SMS app?").wait(timeout=5):
            self.u2d(text = "Desimu").click()
            time.sleep(2)
            self.u2d(text = "Set as default").click()
            time.sleep(3)
            assert self.u2d(text="START").exists
        self.u2d.xpath('//*[@resource-id="com.transsion.desimu:id/navigation_rom"]').click_exists(timeout=3)

    def set_user_data(self, contact_count=1, call_count=1, message_count=1):
       self.u2d(resourceId = "com.transsion.desimu:id/ll_content").scroll.to(text='user data')
       time.sleep(2)
       self.u2d(resourceId="com.transsion.desimu:id/aet_contact_count").click_exists(timeout=3)
       self.u2d(resourceId="com.transsion.desimu:id/aet_contact_count").clear_text(timeout=3)
       self.u2d(resourceId="com.transsion.desimu:id/aet_contact_count").set_text(contact_count)
       self.u2d_helper.press_back_key()
       self.u2d(resourceId="com.transsion.desimu:id/aet_call_count").click_exists(timeout=3)
       self.u2d(resourceId="com.transsion.desimu:id/aet_call_count").clear_text(timeout=3)
       self.u2d(resourceId="com.transsion.desimu:id/aet_call_count").set_text(call_count)
       self.u2d_helper.press_back_key()
       self.u2d(resourceId="com.transsion.desimu:id/aet_message_count").click_exists(timeout=3)
       self.u2d(resourceId="com.transsion.desimu:id/aet_message_count").clear_text(timeout=3)
       self.u2d(resourceId="com.transsion.desimu:id/aet_message_count").set_text(message_count)
       self.u2d_helper.press_back_key()
       time.sleep(3)
       self.u2d(scrollable=True).scroll.to(text="media resource fill")
       check_box_element = self.u2d(text="media resource fill").sibling(resourceId="com.transsion.desimu:id/cb_resouse")
       check_box = check_box_element.info.get("checked", None)
       if check_box:
           check_box_element.click(timeout=3)
       time.sleep(3)
       self.u2d(scrollable=True).scroll.to(text="total storage")
       check_box_element = self.u2d(text="file fragmentation").sibling(resourceId="com.transsion.desimu:id/cb_pieces")
       check_box = check_box_element.info.get("checked", None)
       if check_box:
           check_box_element.click(timeout=3)
       time.sleep(3)

       self.u2d(scrollable=True).scroll.to(text="filled with large files")
       check_box_element = self.u2d(text="cache export").sibling(resourceId="com.transsion.desimu:id/cb_cache_export")
       check_box = check_box_element.info.get("checked", None)
       if check_box:
           check_box_element.click(timeout=3)
       time.sleep(3)
       self.u2d(scrollable=True).scroll.to(text="cache generation")
       time.sleep(3)
       check_box_element = self.u2d(text="cache generation").sibling(resourceId="com.transsion.desimu:id/cb_cache")
       check_box = check_box_element.info.get("checked", None)
       if check_box:
           check_box_element.click(timeout=3)
       time.sleep(3)
       self.u2d(scrollable=True).scroll.to(text="filled with large files")
       time.sleep(3)
       check_box_element = self.u2d(text="filled with large files").sibling(
           resourceId="com.transsion.desimu:id/cb_fill")
       check_box = check_box_element.info.get("checked", None)
       if check_box:
           check_box_element.click(timeout=3)
       time.sleep(3)
       self.u2d(scrollable=True).scroll.to(text="monkey automation")
       check_box_element = self.u2d(text="monkey automation").sibling(
           resourceId="com.transsion.desimu:id/cb_monkey")
       check_box = check_box_element.info.get("checked", None)
       if check_box:
           check_box_element.click(timeout=3)
       self.u2d(scrollable=True).scroll.to(text="START")
       time.sleep(5)
       self.u2d(text="START").click_exists(timeout=3)
       after_minute = datetime.datetime.now() + datetime.timedelta(minutes=20)
       while datetime.datetime.now() < after_minute:
           if self.u2d.xpath('//*[@resource-id="com.transsion.desimu:id/rv_schedule_detail"]').wait_gone():
               break
           time.sleep(10)


