from time import sleep
from powertrde.utils.trde import adb
from tests.current_analysis.phoneconfig import PhoneConfig
import datetime

def candycrash_start(phone :PhoneConfig):
    d = phone.u2d
    phone.u2d_helper.stop_app("com.king.candycrushsaga")
    sleep(1)
    adb.exec_cmd(phone.serial, "pm clear com.king.candycrushsaga")
    sleep(1)
    phone.u2d_helper.grant_all_useful_permissions("com.king.candycrushsaga")
    phone.u2d_helper.start_app("com.king.candycrushsaga")
    # 游戏界面无法识别控件，先盲点，图像识别后续调研
    d.sleep(10)
    d.click(0.5, 0.72) # ACCEPT
    d.sleep(1)
    d.click(0.5, 0.485) # PLAY
    d.sleep(3)
    d.click(0.5, 0.9) # Don't allow
    d.sleep(15)
    d.click(0.5, 0.95)

def candycrash_stop(phone :PhoneConfig):
    adb.double_press_back_key(phone.serial)
    adb.stop_app(phone.serial, "com.king.candycrushsaga")
    
def candycrash_check(phone :PhoneConfig, delay: float = 10):
    candycrash_start(phone)
    sleep(delay)
    candycrash_stop(phone)
    return True

def C16_candycrash(phone :PhoneConfig):
    device = phone.device
    candycrash_start(phone)
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
    candycrash_stop(phone)
    device.usb_connect(phone.pmsn)
    # 获取测试后板温
    board_temp_after = phone.get_board_temperature()
    if board_temp_after is not None:
        device.set_keyvalue(phone.pmsn, "ntc_end", board_temp_after)
    # 保存日志
    phone.phone_log_stop_save()

    return result
