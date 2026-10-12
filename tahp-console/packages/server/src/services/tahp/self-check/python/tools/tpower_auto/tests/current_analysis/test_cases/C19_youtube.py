from time import sleep
from powertrde.utils.trde import adb
from tests.current_analysis.phoneconfig import PhoneConfig
import datetime

def youtube_start(phone :PhoneConfig):
    phone.u2d.app_stop('com.google.android.gms')
    phone.u2d.app_stop('com.google.android.youtube')
    sleep(3)
    # 启动App
    phone.u2d.app_start('com.google.android.youtube')
    phone.u2d.xpath('//*[@resource-id="com.android.permissioncontroller:id/permission_allow_button"]').click_exists(timeout=5)
    phone.u2d.xpath('//*[@text="No subscribers"]').click_exists(timeout=5)
    phone.u2d.xpath('//*[@resource-id="com.android.vending:id/0_resource_name_obfuscated"]').click_exists(timeout=1)
    phone.u2d_helper.wait_ui_obj('//*[@text="Home"]', timeout=20, post_wait=1)
    phone.u2d.xpath('//*[@text="Home"]').click(timeout=5)
    btn_short = phone.u2d.xpath('//*[@text="Shorts"]')
    phone.u2d_helper.wait_ui_obj('//*[@resource-id="com.google.android.youtube:id/menu_item_1"]', timeout=30,
                                pre_wait=1)
    btn_search = phone.u2d.xpath('//*[@resource-id="com.google.android.youtube:id/menu_item_1"]')
    btn_search.click()
    sleep(1)
    phone.u2d.xpath('//*[@resource-id="com.google.android.youtube:id/search_edit_text"]').click()
    sleep(3)
    phone.u2d.send_keys("keepon动漫社")
    sleep(1)
    phone.u2d_helper.press_enter_key()
    sleep(5)
    phone.u2d.xpath('//*[@content-desc="View Channel"]').click()
    sleep(5)
    phone.u2d.swipe(0.5, 0.9, 0.5, 0.1)
    sleep(1)
    phone.u2d(descriptionContains='Avatar EP01').click()
    for _ in range(20):  # 最多等待60秒（20次*3秒）
        sleep(3)
        phone.u2d.xpath('//*[@resource-id="com.google.android.youtube:id/skip_ad_button_text"]').click_exists(timeout=5)
        if phone.u2d(descriptionContains='seconds of 25 minutes').exists():
            break
    else:
        phone.logerror("YouTube视频加载超时，跳过广告跳过步骤")
    phone.u2d.click(0.5, 0.1)
    btn_fullscreen = phone.u2d.xpath('//*[@resource-id="com.google.android.youtube:id/fullscreen_button"]')
    btn_fullscreen.click()
    sleep(2)
    phone.u2d.click(0.5, 0.5)
    btn_settings = phone.u2d.xpath('//*[@resource-id="com.google.android.youtube:id/player_overflow_button"]')
    btn_settings.click()
    sleep(1)
    #Quality
    phone.u2d.xpath('//android.support.v7.widget.RecyclerView/android.view.ViewGroup[1]').click()
    sleep(1)
    #Advanced
    phone.u2d.xpath('//*[@resource-id="com.google.android.youtube:id/bottom_sheet_list"]/android.view.ViewGroup[1]/android.view.ViewGroup[4]').click()
    sleep(1)
    #1080p
    phone.u2d.xpath('//*[@resource-id="com.google.android.youtube:id/bottom_sheet_list"]/android.view.ViewGroup[1]/android.view.ViewGroup[1]').click()
    sleep(1)
    phone.u2d.click(0.5, 0.5)
    sleep(0.2)
    for i in range(2):
        phone.u2d.swipe(0.9, 0.8, 0.1, 0.8)
        sleep(0.5)

def youtube_stop(phone :PhoneConfig):
    phone.u2d_helper.press_home_key()
    sleep(1)
    phone.stop_pip_apps()
    phone.u2d.app_stop('com.google.android.youtube')
    
def youtube_check(phone :PhoneConfig, delay: float = 10):
    for i in range(3):
        try:
            youtube_start(phone)
            break
        except Exception as e:
            phone.logerror(f"---第{i+1}次启动失败: {e}")
            youtube_stop(phone)
            if i == 2:
                raise Exception(f"{e}")
        sleep(5)
    sleep(delay)
    youtube_stop(phone)
    return True

def C19_youtube_video(phone :PhoneConfig):
    device = phone.device
    youtube_start(phone)
    refresh_rate_before1 = phone.get_refresh_rate()
    if refresh_rate_before1 is not None:
        device.set_keyvalue(phone.pmsn, "refresh_max", refresh_rate_before1)
    sleep(5)
    # 获取测试前亮度（使用PhoneConfig类的get_screen_brightness方法）
    brightness_before = phone.get_screen_brightness()
    if brightness_before is not None:
        device.set_keyvalue(phone.pmsn, "brightness_actual", brightness_before)
    
    # 获取测试前刷新率（使用PhoneConfig类的get_refresh_rate方法）
    refresh_rate_before = phone.get_refresh_rate()
    if refresh_rate_before is not None:
        device.set_keyvalue(phone.pmsn, "refresh_min", refresh_rate_before)
    # 添加功耗测试前截图
    current_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    phone.screenshot(f"{current_time}.png")
    device.usb_disconnect(phone.pmsn)
    sleep(60)
    phone.device.set_filterperiod(phone.pmsn, 90)
    phone.loginfo(f"---开始测量")
    # 3. 功耗测试
    device.start_measure(phone.pmsn)
    sleep(180)
    result = device.stop_measure(phone.pmsn)
    if result is None:
        phone.logerror(f"---测量失败")
    else:
        phone.loginfo(f"---测量成功")
        device.set_keyvalue(phone.pmsn, "current", result["avgcurrent_mA"])
    sleep(3)
    youtube_stop(phone)
    device.usb_connect(phone.pmsn)
    # 获取测试后板温
    board_temp_after = phone.get_board_temperature()
    if board_temp_after is not None:
        device.set_keyvalue(phone.pmsn, "ntc_end", board_temp_after)
    # 保存日志
    phone.phone_log_stop_save()

    return result