import time

from powertrde.framework.tran_logger import t_log
from tpy_aw.aw_app_base import AwAppBase


class AwAppFileManager(AwAppBase):
    aw_name = 'FileManager'
    default_app_package = 'com.transsion.filemanagerx'

    def change_to_recents(self):
        self.u2d_helper.click_wait('//*[@resource-id="com.transsion.filemanagerx:id/os_foot_opt_bar_item_root_layout"]', timeout=10, post_wait=1)

    def flush_the_resource(self, need_start_app:bool=True):
        if need_start_app:
            self.restart_launcher_activity()
            self.u2d.sleep(1)
        self.u2d(text="Browse", resourceId="com.transsion.filemanagerx:id/os_foot_opt_bar_item_text").click()
        self.u2d.sleep(1)
        self.u2d(text="My Phone").click()
        self.u2d.sleep(1)
        self.u2d.swipe(0.5, 0.3, 0.5, 0.7)
        self.stop_app()