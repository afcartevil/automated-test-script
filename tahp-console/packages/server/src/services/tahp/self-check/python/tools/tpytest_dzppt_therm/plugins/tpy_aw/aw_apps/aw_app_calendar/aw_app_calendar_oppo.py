from tpy_aw.aw_apps.aw_app_calendar.aw_app_calendar import AwAppCalendar
import time


class AwAppCalendarOppo(AwAppCalendar):
    aw_nickname = "OppoCalendar"
    variant_key = 'Oppo'
    default_app_package = "com.oplus.calendar"

    def click_calendar_tab(self):
        self.u2d.xpath('//*[@resource-id="com.oplus.calendar:id/picker_view_wrapper"]').click()
        time.sleep(2)
        self.u2d.xpath('//*[@text="Month"]').click()
        time.sleep(2)

    def click_important_days_tab(self):
        self.u2d.xpath('//*[@text="Search events"]').click()
        time.sleep(2)
        for _ in range(2):
            self.u2d_helper.press_back_key()

    def create_event(self):
        """
        创建事件(右上角+号)
        """
        self.u2d.xpath('//*[@resource-id="com.oplus.calendar:id/fb_create_event"]').click()
        time.sleep(2)

    def click_more_options(self):
        self.u2d_helper.open_app(self.default_app_package)
        time.sleep(2)
        self.u2d.xpath('//*[@content-desc="More options"]').click()
        time.sleep(2)