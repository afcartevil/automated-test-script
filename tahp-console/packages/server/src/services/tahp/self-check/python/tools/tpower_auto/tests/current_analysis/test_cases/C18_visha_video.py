from time import sleep
from powertrde.utils.trde import adb
from tests.current_analysis.phoneconfig import PhoneConfig
import datetime

def visha_start(phone :PhoneConfig, file="1080.mp4"):
    d = phone.u2d
    phone.u2d_helper.stop_app("com.transsion.magicshow")
    sleep(1)
    phone.u2d_helper.grant_all_useful_permissions("com.transsion.magicshow")
    sleep(1)
    adb.exec_cmd(phone.serial, f"am start -a android.intent.action.VIEW \
        -n com.transsion.magicshow/com.transsion.magicvideo.activities.VideoPlayerActivity \
        -d \"file:///sdcard/MyAlbums/naxienian/{file}\" \
        -t \"video/mp4\" \
        --ez android.intent.extra.user_rotation 1")
    sleep(3)
    while phone.u2d(text="Agree").exists():
        phone.u2d.swipe(0.5, 0.7, 0.5, 0.5)
        phone.u2d(text="Agree").click()
        sleep(1)
    if phone.u2d(resourceId="com.transsion.magicshow:id/tv_skip").exists():
        phone.u2d(resourceId="com.transsion.magicshow:id/tv_skip").click()
    sleep(3)
    phone.u2d.click(0.5, 0.5)
    phone.u2d_helper.click_wait(phone.u2d(resourceId="com.transsion.magicshow:id/iv_video_play_rotate",description="Full Screen"), timeout=2)
    #phone.u2d.screenshot("visha_fullscreen.png")


def visha_stop(phone :PhoneConfig):
    phone.u2d_helper.press_home_key()
    phone.u2d_helper.stop_app("com.transsion.magicshow")
    
def visha_check(phone :PhoneConfig, delay: float = 10):
    visha_start(phone)
    sleep(delay)
    visha_stop(phone)
    return True

def C18_visha_video(phone :PhoneConfig, file="1080.mp4"):
    device = phone.device
    visha_start(phone, file)
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
    phone.device.set_filterperiod(phone.pmsn, 120)
    phone.loginfo(f"---开始测量")
    # 3. 功耗测试
    device.start_measure(phone.pmsn)
    sleep(300)
    result = device.stop_measure(phone.pmsn)
    if result is None:
        phone.logerror(f"---测量失败")
    else:
        phone.loginfo(f"---测量成功")
        device.set_keyvalue(phone.pmsn, "current", result["avgcurrent_mA"])
    sleep(3)
    visha_stop(phone)
    device.usb_connect(phone.pmsn)
    # 获取测试后板温
    board_temp_after = phone.get_board_temperature()
    if board_temp_after is not None:
        device.set_keyvalue(phone.pmsn, "ntc_end", board_temp_after)
    # 保存日志
    phone.phone_log_stop_save()

    return result