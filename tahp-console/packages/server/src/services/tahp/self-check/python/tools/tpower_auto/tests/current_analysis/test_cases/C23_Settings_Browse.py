from tests.current_analysis.phoneconfig import PhoneConfig
from time import sleep
from powertrde.utils.trde import adb
import time
import subprocess  # 添加subprocess模块用于执行批处理文件
import datetime

def OpenSettingsAndBrowse(phone: PhoneConfig):
    """打开设置应用并准备浏览"""
    d = phone.u2d
    serial = phone.serial
    try:
        phone.u2d_helper.screen_on_and_unlock()
        phone.u2d_helper.stop_app("com.android.settings")
        sleep(1)
        phone.u2d_helper.clear_app_data("com.android.settings")  # 初始化设置应用
        sleep(1)
        phone.u2d_helper.grant_all_useful_permissions("com.android.settings")  # 授予所有必要权限
        sleep(1)
        phone.u2d_helper.start_app("com.android.settings")

        sleep(5)
        # 检查设置应用是否成功打开
        if not (d(packageName="com.android.settings").exists or 
                d(textMatches=".*Settings.*").exists or
                d(textMatches=".*设置.*").exists):
            raise Exception("设置应用未成功打开")

        phone.loginfo("设置应用已成功打开")
        return True
        
    except Exception as e:
        phone.logerror(f"打开设置应用失败: {str(e)}")
        return False

def C23_Settings_Browse(phone: PhoneConfig):
    """设置应用浏览功耗测试主函数"""
    device = phone.device
    pmsn = phone.pmsn
    serial = phone.serial

    phone.u2d_helper.screen_on_and_unlock()
    sleep(2)
    if not OpenSettingsAndBrowse(phone):
        return None
    
    # 创建自动滑动脚本
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
    device.set_filterperiod(pmsn, 90)
    device.usb_disconnect(pmsn)
    # 测量前静置等待
    sleep(20)
    # 功耗测量记录
    device.start_measure(pmsn)
    phone.loginfo("---开始测量")
    sleep(180)
    result = device.stop_measure(pmsn)

    if result is None:
        phone.logerror("---功耗测量失败")
    else:
        phone.loginfo("---功耗测量成功")
        device.set_keyvalue(pmsn, "current", result["avgcurrent_mA"])
    
    # 连接ADB，抓取日志
    device.usb_connect(pmsn)
    # 获取测试后板温
    board_temp_after = phone.get_board_temperature()
    if board_temp_after is not None:
        device.set_keyvalue(pmsn, "ntc_end", board_temp_after)
    # 保存日志
    phone.phone_log_stop_save()
    # 关闭自动滑动脚本进程
    adb.exec_cmd(serial, "pkill -f auto_scroll.sh")
    phone.u2d_helper.stop_app("com.android.settings")
    sleep(2)
    return result