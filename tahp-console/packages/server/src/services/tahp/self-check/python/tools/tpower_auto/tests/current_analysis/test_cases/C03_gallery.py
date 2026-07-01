from time import sleep
from powertrde.utils.trde import adb

from tests.current_analysis.phoneconfig import PhoneConfig
import datetime

def Gallery_start(phone : PhoneConfig, file="纯白.png"):
    serial = phone.serial
    adb.exec_cmd(serial, f"am start -a android.intent.action.VIEW -d \"file:///sdcard/MyAlbums/colorful/{file}\" -t \"image/*\"")
    sleep(3)
    # 获取AI Gallery弹窗元素
    gallery_element = phone.u2d.xpath('//*[@text="AI Gallery"]')
    # 检查元素是否存在（使用try-except处理可能的API差异）
    try:
        exists = gallery_element.exists(timeout=2)
    except TypeError:
        exists = gallery_element.exists
        
    if exists:
        phone.loginfo(f"关闭AI Gallery 弹窗")
        gallery_element.click()
        phone.resourceid_click("android:id/button_always", 2)
        sleep(0.5)
    phone.u2d.click(0.5, 0.5)
    sleep(2)
    phone.u2d.double_click(0.5, 0.5, 0.01)
    return True
    

def C03_Gallery(phone : PhoneConfig, file="纯白.png"):
    pmsn = phone.pmsn
    device = phone.device
    Gallery_start(phone, file)

    refresh_rate_before1 = phone.get_refresh_rate()
    if refresh_rate_before1 is not None:
        device.set_keyvalue(pmsn, "refresh_max", refresh_rate_before1)
    sleep(5)
    
    # 获取测试前亮度（使用PhoneConfig类的get_screen_brightness方法）
    brightness_before = phone.get_screen_brightness()
    if brightness_before is not None:
        device.set_keyvalue(pmsn, "brightness_actual", brightness_before)
    
    # 获取测试前刷新率（使用PhoneConfig类的get_refresh_rate方法）
    refresh_rate_before = phone.get_refresh_rate()
    if refresh_rate_before is not None:
        device.set_keyvalue(pmsn, "refresh_min", refresh_rate_before)
    current_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    phone.screenshot(f"{current_time}.png")
    
    device.usb_disconnect(pmsn)
    sleep(60)
    device.set_filterperiod(pmsn, 30)
    phone.loginfo(f"---开始测量")
    
    # 3. 功耗测试
    device.start_measure(pmsn)
    sleep(120)
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