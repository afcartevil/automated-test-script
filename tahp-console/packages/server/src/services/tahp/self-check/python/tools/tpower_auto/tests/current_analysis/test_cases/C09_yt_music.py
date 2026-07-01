from time import sleep
from powertrde.utils.trde import adb
from tests.current_analysis.phoneconfig import PhoneConfig
import datetime

def yt_start(phone :PhoneConfig, file="Lonely"):
    serial = phone.serial
    #断网，保持离线模式
    phone.u2d_helper.open_close_wifi(False)
    phone.u2d_helper.open_close_mobile_data(False)
    phone.u2d.app_stop("com.google.android.apps.youtube.music")
    sleep(1)
    adb.exec_cmd(phone.serial, "pm clear com.google.android.apps.youtube.music")
    phone.u2d_helper.grant_all_useful_permissions("com.google.android.apps.youtube.music")
    phone.u2d.app_start("com.google.android.apps.youtube.music")
    sleep(5)
    if(phone.u2d(resourceId="com.google.android.apps.youtube.music:id/title",text="Accounts").exists()):
        phone.u2d_helper.press_back_key()
    if (phone.u2d(text="Device files only").exists()):
        phone.u2d_helper.click_wait(phone.u2d(text="Device files only"), pre_wait=1, timeout=3)
        phone.u2d(text="Dismiss").click_exists(timeout=3)
        phone.u2d(text="Allow").click_exists(timeout=3)
    else :
        phone.u2d_helper.click_wait(phone.u2d(resourceId="com.google.android.apps.youtube.music:id/text1",text="Home"), pre_wait=1, timeout=3)
        phone.u2d_helper.click_wait(phone.u2d(resourceId="com.google.android.apps.youtube.music:id/text1",text="Library"), pre_wait=1, timeout=3)
        phone.u2d_helper.click_wait(phone.u2d(resourceId="com.google.android.apps.youtube.music:id/text1",text="Library"), pre_wait=1, timeout=3)
        phone.u2d_helper.click_wait(phone.u2d(resourceId="com.google.android.apps.youtube.music:id/text",text="Device files"), pre_wait=1, timeout=3)
    
    try:
        phone.u2d(resourceId="com.google.android.apps.youtube.music:id/title", textContains=f"{file}").click()
    except:
        phone.logerror(f"点击播放{file}失败")
        return False
    return True

def C09_yt_music(phone :PhoneConfig, file="Lonely"):
    pmsn = phone.pmsn
    device = phone.device
    serial = phone.serial
    if not yt_start(phone, file):
        return None
    # 添加功耗测试前截图
    current_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    phone.screenshot(f"{current_time}.png")
    adb.poweroff_phone_screen(serial)
    device.usb_disconnect(pmsn)
    sleep(30)
    device.set_filterperiod(pmsn, 120)
    phone.loginfo(f"---开始测量")
    # 3. 功耗测试
    device.start_measure(pmsn)
    sleep(300)
    result = device.stop_measure(pmsn)
    if result is None:
        phone.logerror(f"---测量失败")
    else:
        phone.loginfo(f"---测量成功")
        device.set_keyvalue(pmsn, "current", result["avgcurrent_mA"])
    device.usb_connect(pmsn)   
    # 获取测试后板温
    board_temp_after = phone.get_board_temperature()
    if board_temp_after is not None:
        device.set_keyvalue(pmsn, "ntc_end", board_temp_after)
    # 保存日志
    phone.phone_log_stop_save()

    return result
