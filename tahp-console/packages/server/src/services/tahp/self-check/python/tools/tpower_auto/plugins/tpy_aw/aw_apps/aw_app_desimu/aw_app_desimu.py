import datetime
import time

from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase
from powertrde.utils.trde import adb


class DesimuLocator(U2SelectorLocator):
    contact_count = U2Selector().resource_id("com.transsion.desimu:id/aet_contact_count").bind()
    call_count = U2Selector().resource_id("com.transsion.desimu:id/aet_call_count").bind()
    message_count = U2Selector().resource_id("com.transsion.desimu:id/aet_message_count").bind()
    picture_count = U2Selector().resource_id("com.transsion.desimu:id/aet_picture_count").bind()
    music_count = U2Selector().resource_id("com.transsion.desimu:id/aet_music_count").bind()
    video_count = U2Selector().resource_id("com.transsion.desimu:id/aet_video_count").bind()
    sound_count = U2Selector().resource_id("com.transsion.desimu:id/aet_sound_count").bind()
    document_count = U2Selector().resource_id("document_count").bind()
    document_text = U2Selector().text("document").bind()
    file_fragmentation = U2Selector().text("file fragmentation").bind()
    desimu_text = U2Selector().text("Desimu").bind()
    schedule_detail = U2Selector().xpath('//*[@resource-id="com.transsion.desimu:id/rv_schedule_detail"]').bind()


class AwAppDesimu(DesimuLocator, AwAppBase):
    aw_name = 'desimu'
    app_package = 'com.transsion.desimu'

    def set_as_default_desimu(self):
        adb.set_dialer(self.device_id, self.app_package)

    def grant_permissions(self):
        self.u2d_helper.grant_all_useful_permissions(self.app_package)

    def enter_app(self):
        self.set_as_default_desimu()
        self.grant_permissions()
        self.u2d_helper.restart_app(self.app_package)
        self.desimu_text.click_wait(timeout=3)

    def set_user_data(self, contact_count, call_count, message_count):
        self.contact_count.click_wait(timeout=3)
        self.u2d_helper.click_wait(self.contact_count).clear_text()
        self.u2d(self.contact_count).set_text(contact_count)

        self.call_count.click_wait(timeout=3)
        self.u2d_helper.click_wait(self.call_count).clear_text()
        self.u2d(self.call_count).set_text(call_count)

        self.message_count.click_wait(timeout=3)
        self.u2d_helper.click_wait(self.message_count).clear_text()
        self.u2d(self.message_count).set_text(message_count)

        self.u2d_helper.press_back_key(times=1, interval=0.5)

    def set_media_data(self, picture_count, music_count, video_count, sound_count, document_count):
        self.u2d_helper.press_back_key()
        self.contact_count.click_wait(timeout=3)
        self.u2d_helper.click_wait(self.contact_count).clear_text()
        self.u2d(self.contact_count).set_text(picture_count)
        self.u2d_helper.press_back_key()

        self.music_count.click_wait(timeout=3)
        self.u2d(scrollable=True).scroll.to(text="file fragmentation")
        self.u2d_helper.click_wait(self.music_count).clear_text()
        self.u2d(self.music_count).set_text(music_count)

        self.u2d_helper.press_back_key()
        self.video_count.click_wait(timeout=3)
        self.u2d(scrollable=True).scroll.to(text="file fragmentation")
        self.u2d_helper.click_wait(self.video_count).clear_text()
        self.u2d(self.video_count).set_text(video_count)

        self.u2d_helper.press_back_key()
        self.sound_count.click_wait(timeout=3)
        self.u2d(scrollable=True).scroll.to(text="file fragmentation")
        self.u2d_helper.click_wait(self.sound_count).clear_text()
        self.u2d(self.sound_count).set_text(sound_count)

        self.u2d_helper.press_back_key()
        self.document_count.click_wait(timeout=3)
        self.u2d(scrollable=True).scroll.to(text="aging model")
        self.u2d_helper.click_wait(self.document_count).clear_text()
        self.u2d(self.document_count).set_text(document_count)

    def reset_other_data(self):
        self.u2d(scrollable=True).scroll.to(text="file fragmentation")

        check_box_element = self.u2d(text="file fragmentation").sibling(resourceId="com.transsion.desimu:id/cb_pieces")
        check_box = check_box_element.info.get("checked", None)
        if check_box:
            check_box_element.click(timeout=3)
        self.u2d(scrollable=True).scroll.to(text="cache export")
        check_box_element = self.u2d(text="cache export").sibling(resourceId="com.transsion.desimu:id/cb_cache_export")
        check_box = check_box_element.info.get("checked", None)
        if check_box:
            check_box_element.click(timeout=3)
        self.u2d(scrollable=True).scroll.to(text="cache generation")
        check_box_element = self.u2d(text="cache generation").sibling(resourceId="com.transsion.desimu:id/cb_cache")
        check_box = check_box_element.info.get("checked", None)
        if check_box:
            check_box_element.click(timeout=3)

        self.u2d(scrollable=True).scroll.to(text="filled with large files")
        check_box_element = self.u2d(text="filled with large files").sibling(
            resourceId="com.transsion.desimu:id/cb_fill")
        check_box = check_box_element.info.get("checked", None)
        if check_box:
            check_box_element.click(timeout=3)

        self.u2d(scrollable=True).scroll.to(text="monkey automation")
        check_box_element = self.u2d(text="monkey automation").sibling(
            resourceId="com.transsion.desimu:id/cb_monkey")
        check_box = check_box_element.info.get("checked", None)
        if check_box:
            check_box_element.click(timeout=3)
        self.u2d(scrollable=True).scroll.to(text="START")
        self.u2d(text="START").click_exists(timeout=3)
        if not self.u2d(text="进行中").exists:
            raise Exception("enter fill data page fail")

    def check_is_fill_done(self):
        after_minute = datetime.datetime.now() + datetime.timedelta(minutes=10)
        while datetime.datetime.now() < after_minute:
            self.schedule_detail.wait_gone()
            time.sleep(10)
