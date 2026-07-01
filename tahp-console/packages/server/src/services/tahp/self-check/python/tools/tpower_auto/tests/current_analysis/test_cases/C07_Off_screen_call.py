from tests.current_analysis.phoneconfig import PhoneConfig
from time import sleep
from powertrde.utils.trde import adb
import time
import re
import datetime
def get_sim_operator_from_settings(phone: PhoneConfig):
    """通过设置界面获取SIM卡运营商信息"""
    d = phone.u2d
    try:
        # 确保屏幕已解锁
        phone.u2d_helper.screen_on_and_unlock()
        sleep(2)
        
        # 打开设置应用
        d.app_stop("com.android.settings")
        sleep(2)
        d.app_start("com.android.settings")
        sleep(2)
        
        # 查找并点击SIM卡设置
        try:
            d(textContains="SIM").click(timeout=2)
        except:
            d.app_stop("com.android.settings")
            sleep(2)
            d.app_start("com.android.settings")
            sleep(2)
            d(textContains="SIM").click(timeout=2)
        sleep(2)
        
        # 直接查找包含"CU"的文本元素
        # 优先检查联通运营商（CU）
        try:
            cu_element = d(textContains="CU")
            if cu_element.exists(timeout=3):
                cu_text = cu_element.get_text(timeout=2)
                return "联通"
        except Exception as e:
            phone.logwarning(f"直接查找CU元素失败: {str(e)}")
        
        # 直接查找包含"CM"的文本元素
        # 检查移动运营商（CM）
        try:
            cm_element = d(textContains="CM")
            if cm_element.exists(timeout=3):
                cm_text = cm_element.get_text(timeout=2)
                return "移动"
        except Exception as e:
            phone.logwarning(f"直接查找CM元素失败: {str(e)}")
        
        # 直接查找包含"CC"的文本元素
        # 检查电信运营商（CC）
        try:
            cc_element = d(textContains="CC")
            if cc_element.exists(timeout=3):
                cc_text = cc_element.get_text(timeout=2)
                return "电信"
        except Exception as e:
            phone.logwarning(f"直接查找CC元素失败: {str(e)}")
        
        # 如果直接查找都失败，抛出异常
        raise Exception("未找到有效的运营商信息")
        
    except Exception as e:
        phone.logerror(f"获取SIM卡运营商信息失败: {str(e)}")
        raise Exception(f"SIM卡识别失败: {str(e)}")
    finally:
        # 关闭设置应用
        try:
            d.app_stop("com.android.settings")
        except:
            pass

def get_phone_number_by_operator(operator: str):
    """根据运营商获取对应的客服电话号码"""
    operator_map = {
        "移动": "10086",
        "联通": "10010", 
        "电信": "10000"
    }
    
    if operator not in operator_map:
        raise Exception(f"不支持的运营商: {operator}")
    
    return operator_map[operator]

def MakeEmergencyCall(phone: PhoneConfig):
    """拨打紧急电话 - 根据SIM卡运营商动态选择号码"""
    d = phone.u2d
    try:
        serial = phone.serial
        
        # 获取SIM卡运营商信息
        operator = get_sim_operator_from_settings(phone)
        phone_number = get_phone_number_by_operator(operator)
        
        # 确保屏幕已解锁
        phone.u2d_helper.screen_on_and_unlock()
        sleep(2)
        adb.exec_cmd(serial, f"am start -a android.intent.action.DIAL -d tel:{phone_number}")
        sleep(5)

        # 检查拨号界面是否成功打开
        if not (d(resourceIdMatches=".*dialpad.*").exists or 
                d(textMatches=".*拨号.*").exists or
                d(descriptionMatches=".*dial.*").exists):
            raise Exception("拨号界面未成功打开")

        d(resourceId="com.sh.smart.caller:id/dialpad_floating_action_button").click() # 点击拨号按钮
        sleep(5)
        # 检查是否成功拨号
        call_connected = False
        for i in range(15):
            # 检查通话界面是否出现
            if (d(resourceIdMatches=".*incall.*").exists or 
                d(descriptionMatches=".*end.*call.*").exists or
                d(textMatches=".*通话中.*").exists or
                d(textMatches=".*Calling.*").exists or
                d(resourceIdMatches=".*incall_end_call.*").exists):
                call_connected = True
                break
            sleep(1)
        
        if call_connected:
            phone.loginfo(f"拨号[{phone_number}]成功")
            return True
        else:
            raise Exception(f"拨号[{phone_number}]失败")
        
    except Exception as e:
        phone.loginfo(f"拨打电话出错: {str(e)}")
        return False

def C07_Off_screen_call(phone: PhoneConfig):
    """灭屏通话功耗测试主函数"""
    device = phone.device
    pmsn = phone.pmsn
    serial = phone.serial
    
    if not MakeEmergencyCall(phone):
        return None
    
    # 添加功耗测试前截图
    current_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    phone.screenshot(f"{current_time}.png")

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
    device.set_filterperiod(pmsn, 30)
    # 断开USB连接
    device.usb_disconnect(pmsn)
    sleep(20)  # 等待脚本执行和系统稳定
    
    phone.loginfo("---开始功耗测量（通话中灭屏状态）")
    device.start_measure(pmsn)
    sleep(120)  # 测量2分钟
    result = device.stop_measure(pmsn)
    
    if result is None:
        phone.logerror("---功耗测量失败")
    else:
        phone.loginfo("---功耗测量成功")
        device.set_keyvalue(pmsn, "current", result["avgcurrent_mA"])

    # 重新连接USB
    device.usb_connect(pmsn)
    # 添加功耗测试后截图
    current_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    phone.screenshot(f"{current_time}.png")
    
    # 先亮屏再挂断电话
    try:
        phone.u2d_helper.screen_on_and_unlock()
        sleep(2) 
        adb.exec_cmd(phone.serial, "input keyevent KEYCODE_ENDCALL")
        sleep(1)
    except Exception as e:
        phone.logwarning(f"挂断电话时出现异常: {str(e)}")
    # 获取测试后板温
    board_temp_after = phone.get_board_temperature()
    if board_temp_after is not None:
        device.set_keyvalue(pmsn, "ntc_end", board_temp_after)
    # 保存日志
    phone.phone_log_stop_save()

    return result