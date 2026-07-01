from time import sleep
from powertrde.utils.trde import adb
from tests.current_analysis.phoneconfig import PhoneConfig
import datetime

def tiktok_start(phone :PhoneConfig):
    app_info = phone.global_config.table_apps['TikTok']
    phone.u2d.app_stop(app_info['package'])
    sleep(2)
    # 启动App
    phone.u2d.app_start(app_info['package'])
    sleep(4)
    # 要登录账号才能看直播，所以不能清除data
    agree = phone.u2d.xpath('//*[@text="Agree and continue"]')
    if agree.exists:
        agree.click()
        sleep(2)
    skip = phone.u2d.xpath('//*[@text="Skip"]')
    if skip.exists:
        skip.click()
        sleep(2)
    start_watching = phone.u2d.xpath('//*[@text="Start watching"]')
    if start_watching.exists:
        start_watching.click()
        sleep(2)
    agree = phone.u2d.xpath('//android.widget.TextView[@text="Agree and continue"]')
    if agree.exists:
        agree.click()
        sleep(2)
    swip_text = phone.u2d.xpath('//android.widget.TextView[@text="Swipe up for more"]')
    if swip_text.exists:
        phone.u2d.swipe(0.5, 0.8, 0.5, 0.2)
        sleep(2)
    phone.u2d.click(0.92, 0.07) #search
    sleep(1)
    phone.u2d.click(0.50, 0.07) #input
    phone.u2d_helper.input_text('chuanguiyuan')
    sleep(2)
    phone.u2d_helper.press_enter_key()
    sleep(3)
    phone.u2d.click(0.2, 0.35) #first video
    sleep(5)
    if not phone.u2d.xpath('//*[@text="· 2024-04-24"]').exists:
        raise Exception("视频播放错误")

def tiktok_stop(phone :PhoneConfig):
    app_info = phone.global_config.table_apps['TikTok']
    phone.u2d_helper.press_home_key()
    sleep(1)
    phone.u2d.app_stop(app_info['package'])
    
def tiktok_check(phone :PhoneConfig, delay: float = 10):
    for i in range(3):
        try:
            tiktok_start(phone)
            break
        except Exception as e:
            phone.logerror(f"---第{i+1}次启动失败: {e}")
            tiktok_stop(phone)
            if i == 2:
                raise Exception(f"{e}")
        sleep(5)
    sleep(delay)
    tiktok_stop(phone)
    return True

def C20_tiktok_video(phone :PhoneConfig):
    device = phone.device
    tiktok_start(phone)
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
    tiktok_stop(phone)
    device.usb_connect(phone.pmsn)
    # 获取测试后板温
    board_temp_after = phone.get_board_temperature()
    if board_temp_after is not None:
        device.set_keyvalue(phone.pmsn, "ntc_end", board_temp_after)
    # 保存日志
    phone.phone_log_stop_save()

    return result