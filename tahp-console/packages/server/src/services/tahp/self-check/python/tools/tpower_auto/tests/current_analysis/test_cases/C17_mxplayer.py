from time import sleep
from powertrde.utils.trde import adb
from tests.current_analysis.phoneconfig import PhoneConfig
import datetime

def mxplayer_start(phone :PhoneConfig):
    phone.u2d_helper.stop_app("com.mxtech.videoplayer.ad")
    sleep(2)
    phone.u2d_helper.start_app("com.mxtech.videoplayer.ad")
    phone.u2d_helper.wait_ui_obj('//*[@resource-id="com.mxtech.videoplayer.ad:id/music_tab"]', timeout=10,
                                post_wait=2)
    sleep(0.5)
    phone.u2d(resourceId="com.mxtech.videoplayer.ad:id/local_tab").click()
    sleep(2)
    titles_res = phone.u2d(resourceId="com.mxtech.videoplayer.ad:id/title")
    titles = []
    flag = False
    for title in titles_res:
        titles.append(title.get_text())
    for title in titles:
        if title == "Naxienian":
            flag = True
        else:
            phone.u2d(text=title, resourceId='com.mxtech.videoplayer.ad:id/title').long_click(duration=2)
            phone.u2d(resourceId="com.mxtech.videoplayer.ad:id/delete").click()
            phone.u2d.xpath('//*[@resource-id="com.mxtech.videoplayer.ad:id/tv_ok"]').click_exists(timeout=2)
            phone.u2d.xpath('//*[@resource-id="com.mxtech.videoplayer.ad:id/tv_delete"]').click_exists(timeout=2)
            sleep(1)
    if flag is False:
        raise Exception("Naxienian folder not found")
    btn_movies = phone.u2d.xpath('//android.widget.TextView[@text="Naxienian"]')
    # 1080.mp4进度条拖至最开始
    btn_movies.click()
    sleep(1)
    btn_1080 = phone.u2d.xpath('//android.widget.TextView[@text="1080"]')
    btn_1080.click()
    sleep(3)
    for i in range(2):
        phone.u2d.swipe(0.9, 0.5, 0.1, 0.5)
        sleep(1)

def mxplayer_stop(phone :PhoneConfig):
    phone.u2d_helper.press_home_key()
    phone.u2d_helper.stop_app("com.mxtech.videoplayer.ad")
    
def mxplayer_check(phone :PhoneConfig, delay: float = 10):
    mxplayer_start(phone)
    sleep(delay)
    mxplayer_stop(phone)
    return True

def C17_mxplayer_video(phone :PhoneConfig):
    device = phone.device
    mxplayer_start(phone)
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
    sleep(20)
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
    mxplayer_stop(phone)
    device.usb_connect(phone.pmsn)
    # 获取测试后板温
    board_temp_after = phone.get_board_temperature()
    if board_temp_after is not None:
        device.set_keyvalue(phone.pmsn, "ntc_end", board_temp_after)
    # 保存日志
    phone.phone_log_stop_save()

    return result