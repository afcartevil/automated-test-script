from tpy_aw.aw_apps.aw_app_calendar.aw_app_calendar import AwAppCalendar
import time


class AwAppCalendarXiaomi(AwAppCalendar):
    aw_nickname = "XiaomiCalendar"
    variant_key = 'Xiaomi'
    default_app_package = "com.xiaomi.calendar"

    def click_calendar_tab(self):
        """
        点击日历tab（小米没有日历tab）
        """
        ...

    def click_important_days_tab(self):
        """
        点击重要日期tab（小米没有日历tab）
        """
        ...

    def create_event(self):
        """
        创建事件(右上角+号)
        """
        self.u2d.xpath('//*[@resource-id="com.xiaomi.calendar:id/new_event_button" or @content-desc="New"]').click()
        time.sleep(2)
