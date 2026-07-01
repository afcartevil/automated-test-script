from tests.current_analysis.phoneconfig import PhoneConfig
from time import sleep
from powertrde.utils.trde import adb
import time
import subprocess  # 添加subprocess模块用于执行批处理文件
import datetime

def OpenChromeAndBrowse(phone: PhoneConfig):
    """打开Chrome浏览器并浏览www.qq.com"""
    d = phone.u2d
    serial = phone.serial
    try:
        phone.u2d_helper.screen_on_and_unlock()
        phone.u2d_helper.stop_app("com.android.chrome")
        sleep(1)
        phone.u2d_helper.clear_app_data("com.android.chrome") # 初始化Chrome
        phone.u2d_helper.grant_all_useful_permissions("com.android.chrome") # 授予所有必要权限
        phone.u2d_helper.start_app("com.android.chrome")
        d(text="Stay signed out").click_exists(timeout=10)
        d(text="Use without an account").click_exists(timeout=3)
        d(text="No thanks").click_exists(timeout=5)
        d(text="Keep Google").click_exists(timeout=5)
        d(resourceId="com.android.chrome:id/more_button").click_exists(timeout=3)
        d(resourceId="com.android.chrome:id/ack_button").click_exists(timeout=3)
        d(text="OK").click_exists(timeout=3)
        # 检查Chrome是否成功打开
        if not (d(packageName="com.android.chrome").exists or 
                d(textMatches=".*Chrome.*").exists or
                d(descriptionMatches=".*chrome.*").exists):
            raise "Chrome未成功打开"
 
        d(resourceIdMatches=".*url_bar.*").click()
        sleep(2)
        # 使用ADB命令清除文本：先移动到末尾，然后删除所有字符
        adb.exec_cmd(serial, "input keyevent KEYCODE_MOVE_END")
        sleep(0.5)
        # 删除所有字符（假设最多50个字符）
        for i in range(50):
            adb.exec_cmd(serial, "input keyevent KEYCODE_FORWARD_DEL")
            sleep(0.05)
        sleep(1)
        phone.u2d_helper.input_text("www.qq.com")
        sleep(1)
        phone.u2d_helper.press_enter_key()
        sleep(5)
        # 检查页面是否成功加载
        page_loaded = False
        for i in range(10):
            if (d(textMatches=".*QQ.*").exists or 
                d(textMatches=".*腾讯.*").exists or
                d(descriptionMatches=".*qq.*").exists or
                d(textMatches=".*首页.*").exists or
                d(textMatches=".*Home.*").exists):
                page_loaded = True
                phone.loginfo("QQ页面已成功加载")
                break
            sleep(2)
        if not page_loaded:
            raise Exception("页面加载失败")

        return page_loaded
        
    except Exception as e:
        phone.logerror(f"打开Chrome失败: {str(e)}")
        return False

def C21_Chrome_Browse(phone: PhoneConfig):
    """Chrome浏览器浏览网页功耗测试主函数"""
    device = phone.device
    pmsn = phone.pmsn
    serial = phone.serial

    phone.u2d_helper.screen_on_and_unlock()
    sleep(2)
    if not OpenChromeAndBrowse(phone):
        return None
    
    script_lines = [
        "count=70",
        "interval=3", 
        "i=1",
        "while [ $i -le $count ]",
        "do",
        "    input swipe 500 1500 500 500 300",
        "    sleep $interval",
        "    i=$((i+1))",
        "done"
    ]
    
    # 先删除可能存在的旧文件
    adb.exec_cmd(serial, "rm -f /data/local/tmp/auto_scroll.sh")
    sleep(1)
    
    # 逐行写入脚本内容
    for line in script_lines:
        adb.exec_cmd(serial, f"echo '{line}' >> /data/local/tmp/auto_scroll.sh")
        sleep(0.2)
    
    sleep(5)
    refresh_rate_before = phone.get_refresh_rate()
    if refresh_rate_before is not None:
        device.set_keyvalue(pmsn, "refresh_min", refresh_rate_before)
    # 验证文件是否创建成功
    adb.exec_cmd(serial, "ls -l /data/local/tmp/auto_scroll.sh")
    sleep(1)
    
    adb.exec_cmd(serial, "chmod 777 /data/local/tmp/auto_scroll.sh")
    sleep(1)
    adb.exec_cmd(serial, "nohup /data/local/tmp/auto_scroll.sh > /dev/null 2>&1 &")
    sleep(5)
    
    # 获取测试前亮度（使用PhoneConfig类的get_screen_brightness方法）
    brightness_before = phone.get_screen_brightness()
    if brightness_before is not None:
        device.set_keyvalue(pmsn, "brightness_actual", brightness_before)
    
    # 获取测试前刷新率（使用PhoneConfig类的get_refresh_rate方法）
    refresh_rate_before1 = phone.get_refresh_rate()
    if refresh_rate_before1 is not None:
        device.set_keyvalue(pmsn, "refresh_max", refresh_rate_before1)
    # 添加功耗测试前截图
    current_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    phone.screenshot(f"{current_time}.png")
    
    device.set_filterperiod(pmsn, 90)
    device.usb_disconnect(pmsn)
    sleep(20)
    device.start_measure(pmsn)
    phone.logerror("---开始测量")
    sleep(180)
    result = device.stop_measure(pmsn)

    if result is None:
        phone.logerror("---功耗测量失败")
    else:
        phone.loginfo("---功耗测量成功")
        device.set_keyvalue(pmsn, "current", result["avgcurrent_mA"])
    
    device.usb_connect(pmsn)
    # 获取测试后板温
    board_temp_after = phone.get_board_temperature()
    if board_temp_after is not None:
        device.set_keyvalue(pmsn, "ntc_end", board_temp_after)
    # 保存日志
    phone.phone_log_stop_save()
    # 关闭自动滑动脚本进程
    adb.exec_cmd(serial, "pkill -f auto_scroll.sh")
    phone.u2d_helper.stop_app("com.android.chrome")
    sleep(2)
    return result