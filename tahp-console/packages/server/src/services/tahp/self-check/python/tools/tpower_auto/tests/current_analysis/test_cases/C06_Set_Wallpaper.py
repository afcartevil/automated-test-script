from powertrde.utils.trde import adb
from tests.current_analysis.phoneconfig import PhoneConfig
from time import sleep
import time
import datetime
def WallpaperSetting(phone: PhoneConfig, file):
    d = phone.u2d
    try:
        if not phone.u2d_helper.check_file_exists(f'/sdcard/MyAlbums/colorful/{file}'):
            phone.logerror(f"wallpaper file {file} not exists")
            return False

        # 停止并重新启动文件管理器，确保从初始状态开始
        phone.u2d_helper.restart_app("com.transsion.filemanagerx")
        sleep(3)
        # 点击确认按钮（如果有）
        d.xpath('//*[@resource-id="com.transsion.filemanagerx:id/mbtnOk"]').click_exists(timeout=2)
        # 点击浏览选项
        d(text="Browse").click()
        sleep(1)
        # 点击"My Phone"
        d(text="My Phone").click()
        sleep(1)
        # 滑动查找"MyAlbums"文件夹
        album_found = False
        for _ in range(5):  # 最多滑动5次
            sleep(1)
            if d(text="MyAlbums").exists:
                d(text="MyAlbums").click()
                sleep(5)
                album_found = True
                break
            d.swipe(0.5, 0.7, 0.5, 0.3, 0.2)  # 向上滑动
            sleep(1)
        
        if not album_found:
            raise Exception("unable to find MyAlbums folder")
        
        # 滑动查找"colorful"文件夹
        colorful_found = False
        for _ in range(3):  # 最多滑动3次
            if d(text="colorful").exists:
                d(text="colorful").click()
                sleep(1)
                colorful_found = True
                break
            d.swipe(0.5, 0.7, 0.5, 0.3, 0.2)  # 向上滑动
            sleep(0.5)
        
        if not colorful_found:
            raise Exception("unable to find colorful folder")
        
        # 在colorful文件夹中查找壁纸文件
        file_found = False
        for _ in range(3):  # 最多滑动3次
            if d(text=file).exists:
                d(text=file).click()
                sleep(2)
                file_found = True
                break
            d.swipe(0.5, 0.7, 0.5, 0.3, 0.2)  # 向上滑动
            sleep(0.5)
        
        if not file_found:
            raise Exception(f"unable to find wallpaper file: {file}")
        
        # 查找并点击"Use as Wallpaper"选项
        use_as_wallpaper_found = False
        for _ in range(2):  # 最多尝试两次
            if d(text="Use as Wallpaper").exists:
                d(text="Use as Wallpaper").click()
                sleep(1)
                use_as_wallpaper_found = True
                break
            elif d(text="Set as Wallpaper").exists:
                d(text="Set as Wallpaper").click()
                sleep(1)
                use_as_wallpaper_found = True
                break
            # 添加对resourceId=com.gallery20:id/os_fob_layout的检查
            elif d.xpath('(//*[@resource-id="com.gallery20:id/os_fob_layout"])[2]').exists:
                d.xpath('(//*[@resource-id="com.gallery20:id/os_fob_layout"])[2]').click()
                sleep(1)
                use_as_wallpaper_found = True
                break
            # 如果没有直接找到，尝试点击更多选项或菜单按钮
            elif d(resourceId="com.transsion.filemanagerx:id/more").exists:
                d(resourceId="com.transsion.filemanagerx:id/more").click()
                sleep(1)
            sleep(1)
        
        if not use_as_wallpaper_found:
            raise Exception("unable to find Use as Wallpaper or Set as Wallpaper option")
        
        # 处理Apply选项或设置壁纸按钮（如果有）
        if d(text="Apply").exists(timeout=2):
            d(text="Apply").click()
            sleep(1)
        # 检查是否有设置壁纸按钮
        elif d(resourceId="com.transsion.livewallpaper.page:id/set_wallpaper_btn").exists(timeout=2):
            d(resourceId="com.transsion.livewallpaper.page:id/set_wallpaper_btn").click()
            sleep(1)
        
        # 选择设置为"Home screen and lock screen"
        if d(text="Home screen and lock screen").exists(timeout=3):
            d(text="Home screen and lock screen").click()
            sleep(2)
        elif d(text="Home and lock screens").exists(timeout=3):
            d(text="Home and lock screens").click()
            sleep(2)
        elif d(text="Both").exists(timeout=3):
            d(text="Both").click()
            sleep(2)
        else:
            # 如果没有同时设置的选项，尝试先设置主屏幕再设置锁屏
            if d(text="Home screen").exists:
                d(text="Home screen").click()
                sleep(2)
                # 等待回到设置壁纸界面
                sleep(2)
                # 再次打开壁纸设置选项
                if d(text="Use as Wallpaper").exists:
                    d(text="Use as Wallpaper").click()
                    sleep(1)
                elif d(text="Set as Wallpaper").exists:
                    d(text="Set as Wallpaper").click()
                    sleep(1)
                # 设置锁屏
                if d(text="Lock screen").exists:
                    d(text="Lock screen").click()
                    sleep(2)
            else:
                raise Exception("unable to find Home screen or Lock screen option")
        # 停止文件管理器
        d.app_stop("com.transsion.filemanagerx")
        sleep(1)
        phone.u2d_helper.press_home_key() # 返回桌面
        sleep(1)
    except Exception as e:
        phone.logerror(f"Wallpaper setting failed: {str(e)}")

def MoveSettingToNewDesktop(phone: PhoneConfig):
    d = phone.u2d
    for i in range(8):
        d.swipe(0.7, 0.5, 0.3, 0.5, 0.2)
        sleep(0.5)
    
    if d(text="Settings").exists:
        d(text="Settings").long_click(2)
        if d(text="Remove").exists:
            d(text="Remove").click()
            sleep(1)
    try:
        app_name = "Settings"
        width, height = d.window_size()
        d.swipe(0.5, 0.7, 0.5, 0.3, 0.2)
        sleep(1)
        search_box = d(textMatches=".*Search.*")
        if d(textMatches=".*Search.*").exists:
            search_box.click(timeout=5)
            sleep(1)
            phone.u2d_helper.input_text(app_name[:-1])
            sleep(1)
        else:
            assert False, 'search box not found!'
        b = d.xpath(f'//*[@text="{app_name}"]').all()[0].info['bounds']
        start_position = [(b['left'] + b['right']) / 2, (b['top'] + b['bottom']) / 2]
        time.sleep(0.5)
        d.touch.down(start_position[0], start_position[1])
        sleep(0.5)
        for i in range(5):
            d.touch.move((0.9 + i * 0.02) * width, 0.5 * height)
            sleep(0.2)
        sleep(2)
        d.touch.up(0.5, 0.5)
    except Exception as e:
        phone.logerror(f"将设置移动到空白桌面过程出错: {str(e)}")

def C06_Set_Wallpaper(phone: PhoneConfig, file="wp_power.jpg"):
    device = phone.device
    pmsn = phone.pmsn
    
    WallpaperSetting(phone, file)
    MoveSettingToNewDesktop(phone)
    sleep(10)
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
    # 添加功耗测试前截图
    current_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    phone.screenshot(f"{current_time}.png")
    
    # 3. 设置滤波周期
    device.set_filterperiod(pmsn, 30)
    phone.loginfo(f"设置滤波周期为30秒")
    # 4. 测量前静置等待
    device.usb_disconnect(pmsn)
    sleep(60)
    
    # 5. 功耗测量记录
    phone.loginfo(f"---开始功耗测量")
    device.start_measure(pmsn)
    sleep(120)  # 测量2分钟
    result = device.stop_measure(pmsn)
    
    if result is None:
        phone.logerror(f"---功耗测量失败")
    else:
        phone.loginfo(f"---功耗测量成功")
        device.set_keyvalue(pmsn, "current", result["avgcurrent_mA"])
    device.usb_connect(pmsn)       
    # 获取测试后板温
    board_temp_after = phone.get_board_temperature()
    if board_temp_after is not None:
        device.set_keyvalue(pmsn, "ntc_end", board_temp_after)
    # 保存日志
    phone.phone_log_stop_save()

    return result
