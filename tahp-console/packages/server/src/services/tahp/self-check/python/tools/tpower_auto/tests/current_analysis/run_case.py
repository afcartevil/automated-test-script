import os
from time import sleep
from powertrde.utils.trde import adb
from tests.current_analysis.phoneconfig import PhoneConfig
from tests.current_analysis.test_cases.C01_sleep  import C01_Sleep, C01_Sleep_KeyLogs
from tests.current_analysis.test_cases.C02_sleep import C02_ComplexStandby_Init, C02_ComplexStandby

def set_gesture(phone : PhoneConfig):
    pmsn = phone.pmsn
    serial = phone.serial
    d = phone.u2d
    gesture = phone.dict_excel['gesture']
    adb.stop_settings_activity(serial)
    adb.open_settings_activity(serial)
    if d(textMatches=".*Search.*").exists:
        search_box = d(textMatches=".*Search.*")
    else:
        assert False, 'search box not found'
    search_box.click(timeout=5)
    d.sleep(1)
    d.send_keys('Actions and Gestures')
    d.sleep(1)
    menu = d(resourceId="android:id/title", textContains="Actions And Gestures")
    if menu.exists(timeout=1):
        menu.click()
    else:
        phone.logerror(f"Actions and Gestures menu not found")
        return False
    d.sleep(1)
    
    menu = d(textContains="Quickly enable")
    if menu.exists(timeout=1):
        menu.click()
    else:
        phone.logerror(f"Quick Start menu not found")
        return False
    d.sleep(1)
    switch_xpath = d.xpath('//android.widget.Switch[1]')
    if switch_xpath.wait(timeout=1): 
        state = switch_xpath.info['checked']
    else:
        phone.logerror(f"Switch not found")
        return False
    if gesture == 'off':
        if state:
            switch_xpath.click()
    else:
        if not state:
            switch_xpath.click()
    adb.exec_cmd(serial, "input keyevent KEYCODE_BACK")
    
    d.sleep(1)
    menu = d(textContains="Double-Tap")
    if menu.wait(timeout=1):
        menu.click()
    else:
        phone.logerror(f"Double-Tap menu not found")
        return False
    d.sleep(1)
    switch_xpath = d.xpath('//android.widget.Switch[1]')
    if switch_xpath.wait(timeout=1):
        state = switch_xpath.info['checked']
    else:
        phone.logerror(f"Switch not found")
        return False
    if gesture == 'off':
        if state:
            switch_xpath.click()
    else:
        if not state:
            switch_xpath.click()
    adb.exec_cmd(serial, "input keyevent KEYCODE_BACK")
    
    d.sleep(1)
    menu = d(textContains="Quickly manage")
    if menu.wait(timeout=1):
        menu.click()
    else:
        phone.logerror(f"Music menu not found")
        return False
    d.sleep(1)
    switch_xpath = d.xpath('//android.widget.Switch[1]')
    if switch_xpath.wait(timeout=1):
        state = switch_xpath.info['checked']
    else:
        phone.logerror(f"Switch not found")
        return False
    if gesture == 'on':
        if not state:
            switch_xpath.click()
    else:
        if state:
            switch_xpath.click()
    adb.exec_cmd(serial, "input keyevent KEYCODE_BACK")    
    
    d.sleep(1)
    menu = d(textContains="Flip phone")
    if menu.wait(timeout=1):
        menu.click()
        d.sleep(1)
        switch_xpath = d.xpath('//android.widget.Switch[1]')
        if switch_xpath.wait(timeout=1):
            state = switch_xpath.info['checked']
        else:
            phone.logerror(f"Switch not found")
            return False
        if gesture == 'on':
            if not state:
                switch_xpath.click()
        else:
            if state:
                switch_xpath.click()
        adb.exec_cmd(serial, "input keyevent KEYCODE_BACK")
    else:
        phone.logerror(f"Flip to Mute menu not found")
        
    d.sleep(1)
    menu = d(textContains="Just raise")
    if menu.wait(timeout=1):
        menu.click()
        d.sleep(1)
        switch_xpath = d.xpath('//android.widget.Switch[1]')
        if switch_xpath.wait(timeout=1):
            state = switch_xpath.info['checked']
        else:
            phone.logerror(f"Switch not found")
            return False
        if gesture == 'on':
            if not state:
                switch_xpath.click()
        else:
            if state:
                switch_xpath.click()
        adb.exec_cmd(serial, "input keyevent KEYCODE_BACK")
    else:
        phone.logerror(f"Raise to Ear menu not found")
     
    d.swipe_ext("up", 0.5)

    d.sleep(1)
    menu = d(textContains="Raise your phone")
    if menu.wait(timeout=1):
        menu.click()
        d.sleep(1)
        switch_xpath = d.xpath('//android.widget.Switch[1]')
        if switch_xpath.wait(timeout=1):
            state = switch_xpath.info['checked']
        else:
            phone.logerror(f"Switch not found")
            return False
        if gesture == 'on':
            if not state:
                switch_xpath.click()
        else:
            if state:
                switch_xpath.click()
        adb.exec_cmd(serial, "input keyevent KEYCODE_BACK")
    else:
        phone.logerror(f"Raise to Wake menu not found")
    
    d.sleep(1)
    menu = d(textContains="Use different gestures")
    if menu.wait(timeout=1):
        menu.click()
        d.sleep(1)
        switch_xpath = d.xpath('//android.widget.Switch[1]')
        if switch_xpath.wait(timeout=1):
            state = switch_xpath.info['checked']
        else:
            phone.logerror(f"Switch not found")
            return False
        if gesture == 'on':
            if not state:
                switch_xpath.click()
        else:
            if state:
                switch_xpath.click()
        adb.exec_cmd(serial, "input keyevent KEYCODE_BACK")
    else:
        phone.logerror(f"Answwer Calls with gestures menu not found")

    return True

def phone_env_config(phone:PhoneConfig):
    device = phone.device
    pmsn = phone.pmsn
    serial = phone.serial
    dict_excel = phone.dict_excel
    # 关闭自动旋转
    adb.open_close_auto_rotate(serial, False)
    # 设置亮度
    if 'brightness' in dict_excel and dict_excel['brightness'].strip() != '':
        bl = int(dict_excel['brightness'].strip())
        if bl < 0:
            try:
                bl = phone.global_config.get_brightness_with_area_set(dict_excel['model'])
                phone.loginfo(f"获取DOU亮度: {bl}")
            except Exception as e:
                phone.loginfo(f"获取DOU亮度失败，改为默认亮度: {e}")
                bl = 102
            finally:
                dict_excel['brightness'] = str(bl)
        phone.u2d_helper.set_brightness_and_close_auto_bright(bl)
        
    # 设置音量
    if 'volume' in dict_excel and dict_excel['volume'].strip() != '':
        #把str转为int
        vl = int(dict_excel['volume'].strip())
        if vl < 0:
            try:
                vl = phone.global_config.get_volume_with_area_set(dict_excel['model'])
                phone.loginfo(f"获取DOU音量: {vl}")
            except Exception as e:
                phone.loginfo(f"获取DOU音量失败，改为默认音量: {e}")
                vl = 13
            finally:
                dict_excel['volume'] = str(vl)
        phone.u2d_helper.set_all_volume_level(vl)
    
        from datetime import datetime, time
        current_time = datetime.now().time()
        if vl > 0 and (current_time >= time(12,30) and current_time <= time(13,30)):  # 午休期间，保持安静
            phone.loginfo(f"当前时间为 {current_time}, 音量较大，13:30之后继续测量")
            while True:
                current_time = datetime.now().time()
                if current_time >= time(12,30) and current_time <= time(13,30):
                    sleep(60)
                else:
                    phone.u2d_helper.screen_on_and_unlock()
                    sleep(5)
                    break
    
    # 设置刷新率
    if 'refresh_rate' in dict_excel:
        if dict_excel['refresh_rate'] == 'min':
            adb.set_settings_screen_fps(serial,0)
            phone.loginfo(f"设置刷新率为 min")
        elif dict_excel['refresh_rate'] == 'max':
            adb.set_settings_screen_fps(serial,1)
            phone.loginfo(f"设置刷新率为 max")
        else:
            adb.set_settings_screen_fps(serial,2)
            phone.loginfo(f"设置刷新率为 Auto")

    # 设置手势
    if phone.debug is False:
        if 'gesture' in dict_excel:
            if(dict_excel['gesture'].strip() == ''):
                dict_excel['gesture'] = 'off'
            phone.loginfo(f"设置手势: {dict_excel['gesture']}")
            while True:
                if dict_excel['gesture'] == device.get_keyvalue(pmsn, 'last_gesture'):
                    phone.loginfo(f"手势已设置为 {dict_excel['gesture']}")
                    break
                ret = set_gesture(phone)
                if ret:
                    device.set_keyvalue(pmsn, 'last_gesture', dict_excel['gesture'])
                    break
    
    # 设置是否开启后台应用
    if 'background' in dict_excel:
        if dict_excel['background'] == True:
            phone.loginfo(f"安装后台应用")
            for i in range(3):
                try:
                    phone.check_installed_apps_and_grant_permissions(True)
                except Exception as e:
                    phone.logerror(f"安装后台应用失败: {e}")
                break
        else:
            phone.clean_backapp()

    # 设置飞行模式
    if 'airplane_mode' in dict_excel:
        #print(f"[{pmsn}] - 设置飞行模式为 {data_dict['airplane_mode']}")
        airmode = adb.is_airplane_mode_on(serial)
        if dict_excel['airplane_mode']:
            if not airmode:
                adb.press_home_key(serial)
                sleep(0.2)
                phone.u2d.swipe(0.8, 1, 0.8, 0.5, 0.1)
                element = phone.u2d(description="Airplane Mode")
                if element.exists(timeout=1):
                    element.click()
                adb.press_back_key(serial)
        else:
            if airmode:
                adb.press_home_key(serial)
                sleep(0.2)
                phone.u2d.swipe(0.8, 1, 0.8, 0.5, 0.1)
                element = phone.u2d(description="Airplane Mode")
                if element.exists(timeout=1):
                    element.click()
                adb.press_back_key(serial)
    
    # 设置wifi
    if 'wifi' in dict_excel:
        if dict_excel['wifi'] != True:
            dict_excel['wifi'] = False
        adb.open_close_wifi(serial, dict_excel['wifi'])
        #print(f"[{pmsn}] - 设置wifi为 {dict_excel['wifi']}")
    
    # 设置data
    if 'data' in dict_excel: 
        if dict_excel['data'] != True:
            dict_excel['data'] = False
        adb.open_close_mobile_data(serial, dict_excel['data'])
        #print(f"[{pmsn}] - 设置data为 {dict_excel['data']}")
    
    # 设置蓝牙
    if 'bt' in dict_excel:
        if dict_excel['bt'] != True:
            dict_excel['bt'] = False
        adb.open_close_bluetooth(serial, dict_excel['bt'])
        #print(f"[{pmsn}] - 设置bt为 {dict_excel['bt']}")
    
    # 设置gps
    if 'gps' in dict_excel:
        if dict_excel['gps'] != True:
            dict_excel['gps'] = False
        adb.open_close_location_service(serial, dict_excel['gps'])
        phone.u2d_helper.press_back_key()
        #print(f"[{pmsn}] - 设置位置服务为 {dict_excel['gps']}")
    
    # 设置nfc
    if 'nfc' in dict_excel:
        if dict_excel['nfc'] != True:
            dict_excel['nfc'] = False
        adb.open_close_nfc(serial, dict_excel['nfc'])
        #print(f"[{pmsn}] - 设置nfc为 {dict_excel['nfc']}")
    return True


def run_single_case(phone : PhoneConfig) -> bool:
    casename = phone.device.get_keyvalue(phone.pmsn, 'case_id')
    phone.taskid = phone.device.get_keyvalue(phone.pmsn, 'task_id')
    assert casename is not None, "case_id 不能为空"
    pmsn = phone.pmsn
    device = phone.device
    serial = phone.serial
    assert (True == device.usb_connect(pmsn))
    adb.poweron_screen_and_unlock(serial)
    
    if not phone_env_config(phone):
        return False
    
    # 提取casename _ 前的字符串
    caseid = casename.split('_')[0]
    logdir = os.path.abspath(f"{phone.logrootdir}/{phone.logsubdir}/{phone.taskid}")
    os.makedirs(os.path.dirname(f"{logdir}/"), exist_ok=True)
    phone.phone_log_start()
    if caseid == 'C01':
        result = C01_Sleep(phone)
    elif caseid == 'C02':
        C02_ComplexStandby_Init(phone)
        phone_env_config(phone)
        result = C02_ComplexStandby(phone)
    elif caseid == 'C03':
        from tests.current_analysis.test_cases.C03_gallery  import C03_Gallery
        result = C03_Gallery(phone, file="纯白.png")
    elif caseid == 'C04':
        from tests.current_analysis.test_cases.C03_gallery  import C03_Gallery
        result = C03_Gallery(phone, file="black.bmp")
    elif caseid == 'C06':
        from tests.current_analysis.test_cases.C06_Set_Wallpaper  import C06_Set_Wallpaper
        result = C06_Set_Wallpaper(phone)
    elif caseid == 'C07':    
        from tests.current_analysis.test_cases.C07_Off_screen_call  import C07_Off_screen_call
        result = C07_Off_screen_call(phone)
    elif caseid == 'C09':
        from tests.current_analysis.test_cases.C09_yt_music  import C09_yt_music
        result = C09_yt_music(phone, file="Lonely")
    elif caseid == 'C16':
        from tests.current_analysis.test_cases.C16_candycrash  import C16_candycrash
        result = C16_candycrash(phone)
    elif caseid == 'C17':
        from tests.current_analysis.test_cases.C17_mxplayer import C17_mxplayer_video
        result = C17_mxplayer_video(phone)
    elif caseid == 'C18':
        from tests.current_analysis.test_cases.C18_visha_video  import C18_visha_video
        result = C18_visha_video(phone, file="1080.mp4")
    elif caseid == 'C19':
        from tests.current_analysis.test_cases.C19_youtube  import C19_youtube_video
        result = C19_youtube_video(phone)
    elif caseid == 'C20':
        from tests.current_analysis.test_cases.C20_tiktok  import C20_tiktok_video
        result = C20_tiktok_video(phone)
    elif caseid == 'C21':
        from tests.current_analysis.test_cases.C21_Chrome_Browse  import C21_Chrome_Browse
        result = C21_Chrome_Browse(phone)
    elif caseid == 'C22':
        from tests.current_analysis.test_cases.C22_instagram  import C22_instagram_video
        result = C22_instagram_video(phone)
    elif caseid == 'C23':
        from tests.current_analysis.test_cases.C23_Settings_Browse  import C23_Settings_Browse
        result = C23_Settings_Browse(phone)
    elif caseid == 'C24':
        from tests.current_analysis.test_cases.C24_Screen_off_recording  import C24_Screen_off_recording
        result = C24_Screen_off_recording(phone)
    else:
        phone.logwarning(f"未实现的测试用例: {caseid}")
        return False
    adb.poweron_screen_and_unlock(serial)
    sleep(1)
    adb.double_press_back_key(serial)
    sleep(1)
    phone.u2d_helper.press_home_key()
    sleep(1)
    phone.clean_backapp()
    if result is None:
        phone.logerror(f"测试用例执行失败")
        return False
    else:
        for k,v in result.items():
            phone.dict_excel[k] = v
        device.savefile(pmsn, f"{logdir}\pt5file")
        phone.loginfo(f"测试成功,平均电流: {phone.dict_excel['current']} mA")
        return True