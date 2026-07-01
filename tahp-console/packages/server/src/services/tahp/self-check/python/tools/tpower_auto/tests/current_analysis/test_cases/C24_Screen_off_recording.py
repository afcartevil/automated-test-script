from tests.current_analysis.phoneconfig import PhoneConfig
from time import sleep
from powertrde.utils.trde import adb
import datetime

def OpenSoundRecorder(phone: PhoneConfig):
    """打开录音应用并准备录音"""
    serial = phone.serial
    try:
        phone.u2d_helper.screen_on_and_unlock()
        phone.u2d_helper.stop_app("com.transsion.soundrecorder")
        sleep(1)
        phone.u2d_helper.clear_app_data("com.transsion.soundrecorder")  # 初始化录音应用
        sleep(1)
        phone.u2d_helper.grant_all_useful_permissions("com.transsion.soundrecorder")  # 授予所有必要权限
        sleep(1)
        phone.u2d_helper.start_app("com.transsion.soundrecorder")
        d = phone.u2d
        d(text="Agree").click_exists(timeout=3)
        d(text="Got It").click_exists(timeout=3)
        sleep(5)
        phone.loginfo("录音应用已成功打开")
        return True
        
    except Exception as e:
        phone.logerror(f"打开录音应用失败: {str(e)}")
        return False

def C24_Screen_off_recording(phone: PhoneConfig):
    """飞行模式下录音功耗测试主函数"""
    device = phone.device
    pmsn = phone.pmsn
    serial = phone.serial

    phone.u2d_helper.screen_on_and_unlock()
    sleep(2)
    
    if not OpenSoundRecorder(phone):
        return None
    
    # 开始录音
    phone.loginfo("---开始录音")
    # 点击录音按钮（使用resource-id）
    d = phone.u2d
    record_button = d(resourceId="com.transsion.soundrecorder:id/btn_record_container")
    if record_button.exists(timeout=10):
        record_button.click()
        phone.loginfo("---成功点击录音按钮")
    else:
        phone.logerror("---录音按钮未找到，使用坐标点击")
        adb.tap(serial, 500, 1000)  # 备用方案：使用坐标点击
    sleep(2)  # 等待2秒内
    
    # 创建后台灭屏脚本
    script_lines = [
        "# 等待USB断开后执行灭屏操作",
        "sleep 5",
        "input keyevent KEYCODE_POWER",
        "sleep 2",
        "input keyevent KEYCODE_POWER"
    ]
    
    # 先删除可能存在的旧文件
    adb.exec_cmd(serial, "rm -f /data/local/tmp/screen_off.sh")
    sleep(1)
    
    # 逐行写入脚本内容
    for line in script_lines:
        adb.exec_cmd(serial, f"echo '{line}' >> /data/local/tmp/screen_off.sh")
        sleep(0.2)
    
    sleep(2)
    
    # 验证文件是否创建成功
    adb.exec_cmd(serial, "ls -l /data/local/tmp/screen_off.sh")
    sleep(1)
    
    adb.exec_cmd(serial, "chmod 777 /data/local/tmp/screen_off.sh")
    sleep(1)
    
    # 在USB断开前启动后台灭屏脚本
    adb.exec_cmd(serial, "nohup /data/local/tmp/screen_off.sh > /dev/null 2>&1 &")
    
    # 获取测试前刷新率
    refresh_rate_before = phone.get_refresh_rate()
    if refresh_rate_before is not None:
        device.set_keyvalue(pmsn, "refresh_min", refresh_rate_before)
    
    # 获取测试前亮度
    brightness_before = phone.get_screen_brightness()
    if brightness_before is not None:
        device.set_keyvalue(pmsn, "brightness_actual", brightness_before)
    
    # 获取测试前刷新率
    refresh_rate_before1 = phone.get_refresh_rate()
    if refresh_rate_before1 is not None:
        device.set_keyvalue(pmsn, "refresh_max", refresh_rate_before1)
    
    # 添加功耗测试前截图
    current_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    phone.screenshot(f"{current_time}.png")
    
    # 设置滤波周期
    device.set_filterperiod(pmsn, 30)
    device.usb_disconnect(pmsn)
    # 等待脚本执行和系统稳定
    sleep(20)
    # 功耗测量记录
    device.start_measure(pmsn)
    phone.loginfo("---开始测量")
    sleep(120)  # 测量2分钟
    result = device.stop_measure(pmsn)

    if result is None:
        phone.logerror("---功耗测量失败")
    else:
        phone.loginfo("---功耗测量成功")
        device.set_keyvalue(pmsn, "current", result["avgcurrent_mA"])
    
    # 连接ADB，抓取日志
    device.usb_connect(pmsn)
    
    # 清理灭屏脚本进程
    adb.exec_cmd(serial, "pkill -f screen_off.sh")
    
    # 获取测试后板温
    board_temp_after = phone.get_board_temperature()
    if board_temp_after is not None:
        device.set_keyvalue(pmsn, "ntc_end", board_temp_after)
    # 先解锁屏幕
    phone.u2d_helper.screen_on_and_unlock()
    # 停止录音
    phone.loginfo("---停止录音")
    sleep(2)
    # 点击停止录音按钮（使用resource-id）
    d = phone.u2d
    stop_button = d(resourceId="com.transsion.soundrecorder:id/btn_record_container")
    if stop_button.exists(timeout=10):
        stop_button.click()
        phone.loginfo("---成功点击停止录音按钮")
    else:
        phone.logerror("---停止录音按钮未找到，使用坐标点击")
        adb.tap(serial, 500, 1000)  # 备用方案：使用坐标点击
    sleep(2)
    d(text="close").click_exists(timeout=3)
    sleep(2)
  # 点击Delete控件（使用坐标点击）
    phone.loginfo("---点击Delete控件")
    # delete控件的bounds=[558,2032][960,2164]，计算中心点坐标
    delete_x = (558 + 960) // 2
    delete_y = (2032 + 2164) // 2
    # 使用input tap命令点击指定坐标
    adb.exec_cmd(serial, f"input tap {delete_x} {delete_y}")
    phone.loginfo(f"---成功点击Delete控件，坐标: ({delete_x}, {delete_y})")
    sleep(2)

    # 保存日志
    phone.phone_log_stop_save()
    phone.u2d_helper.stop_app("com.transsion.soundrecorder")
    sleep(2)
    return result