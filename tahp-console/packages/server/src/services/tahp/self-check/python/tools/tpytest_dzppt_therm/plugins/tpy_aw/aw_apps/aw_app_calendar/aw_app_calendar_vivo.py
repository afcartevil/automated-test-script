from tpy_aw.aw_apps.aw_app_calendar.aw_app_calendar import AwAppCalendar
import time


class AwAppCalendarVivo(AwAppCalendar):
    aw_nickname = "VivoCalendar"
    variant_key = 'Vivo'
    default_app_package = "com.google.android.calendar"

    def click_calendar_tab(self):
        self.u2d.xpath('//*[@content-desc="Show Calendar List and Settings drawer"]').click()
        time.sleep(2)
        self.u2d.xpath('//*[@text="Month"]').click()
        time.sleep(2)

    def click_important_days_tab(self):
        self.u2d.xpath('//*[@content-desc="Show Calendar List and Settings drawer"]').click()
        time.sleep(2)
        self.u2d.xpath('//*[@text="Schedule"]').click()
        time.sleep(2)

    def create_event(self):
        """
        创建事件(右上角+号)
        """
        self.u2d.xpath('//*[@content-desc="Create new event or other calendar entries"]').click()
        time.sleep(2)
        self.u2d.xpath('//*[@resource-id="com.google.android.calendar:id/speed_dial_event_container"]').click()
        time.sleep(2)

    def click_more_options(self):
        ...