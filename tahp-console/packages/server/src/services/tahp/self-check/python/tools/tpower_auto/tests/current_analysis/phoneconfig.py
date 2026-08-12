import asyncio
import threading
import time
import concurrent.futures
import re
import os

from plugins.tpy_aw.u2d_test_helper import U2DTestHelper
from powertrde.utils.trde import adb
from powertrde.framework.logs_protocol import logs_p
from powertrde.utils.wifiadb.wifi_adb_utils import check_device_to_link_wifi
from tests.current_analysis.device import Device
from tests.current_analysis.gobalconfig import GlobalConfig
from plugins.tpytest_extends.utils.app_installer import AppInstallerForProvider
from tests.current_analysis.tran_ai import TranAi
from powertrde.env import PROJ_DIR

class PhoneConfig():
    def __init__(self, pmsn: str):
        self.pmsn = pmsn
        self.logrootdir = os.path.join(PROJ_DIR, "output")
        self.logsubdir = ""
        self.taskid = ""
        self.device = Device()
        self.serial = self.device.get_serial(pmsn)
        assert self.serial is not None, f"[{pmsn}] - serial is None"
        self.model  = self.device.get_model(pmsn)
        assert self.model is not None, f"[{pmsn}] - model is None"
        self.version = self.device.get_version(pmsn)
        assert self.version is not None, f"[{pmsn}] - version is None"
        self.dict_task = self.device.pmsn_deviceid_dict[pmsn]
        self.dict_excel = self.device.pmsn_deviceid_dict[pmsn]['excel']
        self.u2d_helper = U2DTestHelper(self.serial)
        self.u2d = self.u2d_helper.u2d
        self.global_config = GlobalConfig()
        self.powerref = {}
        self.platform = self.u2d_helper.tran_cpu_platform
        self.debug = False
        self.tran_ai = TranAi()
        self._mylog = logs_p()
        self.option_app_installer_class = AppInstallerForProvider
        self.u2d_helper.kill_monkey_process()

    def loginfo(self, text: str):
        self._mylog.log(f"[{self.pmsn}][{self.model}] - {text}")
    
    def logdebug(self, text: str):
        self._mylog.log_debug(f"[{self.pmsn}][{self.model}] - {text}")
    
    def logwarning(self, text: str):
        self._mylog.log_warning(f"[{self.pmsn}][{self.model}] - {text}")
    
    def logerror(self, text: str):
        self._mylog.log_error(f"[{self.pmsn}][{self.model}] - {text}")

    def check_installed_apps_and_grant_permissions(self, installbackapp = False):
        try:
            # 把待测手机加入adb线程忽略池子（用于并发）
            adb.ignored_thread_lock_devices.add(self.serial)
            # 用于存放 test_apps 中检测到未安装的 app，后续在 back_apps 中排重使用
            already_not_installed_app_package_set = set()
            # 锁，用于在多线程环境下安全更新集合
            lock = threading.Lock()
            device_id = self.serial
            self.install_status = True
            # 尝试安装
            async def try_install(app: dict, tips: str) -> bool:
                res_provider = self.global_config.res_provider
                app_install_provider = self.option_app_installer_class(
                    res_provider,
                    self.u2d_helper.u2d,
                    app['id'],
                    app['package'])
                try:
                    return await app_install_provider.install()
                except Exception:
                    with lock:
                        self.logerror(f"{tips} install failed: {app['package']}")
                    self.install_status = False
                    return False

            def process_test_app(app: dict):
                package = app['package']
                if not adb.package_is_installed(device_id, package):
                    install_flag = asyncio.run(try_install(app, "Test App"))
                    if not install_flag:
                        already_not_installed_app_package_set.add(package)
                else:
                    self.u2d_helper.grant_all_useful_permissions(package)
                    self.u2d_helper.deny_pip_permission(package)# 禁用画中画权限

            def process_back_app(app: dict):
                package = app['package']
                if not adb.package_is_installed(device_id, package):
                    with lock:
                        need_install_back_app = (package not in already_not_installed_app_package_set)
                    if need_install_back_app:
                        install_flag = asyncio.run(try_install(app, "Back App"))
    
            # 并行处理 test_apps：将每个 app 的检测和权限赋予任务提交到线程池
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
                futures_test = [executor.submit(process_test_app, app) for app in self.global_config.test_apps.values()]
                # 等待所有 test_apps 任务完成
                concurrent.futures.wait(futures_test)

            # 并行处理 back_apps：将每个 app 的检测任务提交到线程池
            if installbackapp:
                with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
                    futures_back = [executor.submit(process_back_app, app) for app in self.global_config.back_apps.values()]
                    concurrent.futures.wait(futures_back)
        except Exception:
            self.logerror(f"check_installed_apps_and_grant_permissions failed, serial: {self.serial}")
            self.install_status = False
        finally:
            # 把待测手机从并发adb线程忽略池子中移除
            adb.ignored_thread_lock_devices.remove(self.serial)
        
        assert self.install_status, "check_installed_apps_and_grant_permissions failed"
        return self.install_status
    
    def stop_pip_apps(self):
        stopped_packages = set()  # 使用集合避免重复停止同一应用
        try:
            output_lines  = adb.exec_cmd(self.serial, "dumpsys activity activities")
            if not output_lines:
                return
            output = "\n".join(output_lines)
            # 找到 pictureInPicture=true 的 Activity
            for section in output.split("ActivityRecord"):
                if "InPicture=true" in section and "state=PAUSED" in section:
                    while True:
                        match = re.search(r'packageName=(\S+)', section)
                        pkg = None
                        if match:
                            pkg = match.group(1).strip()
                            break
                        match = re.search(r'cmp=(\S+)/', section)
                        if match:
                            pkg = match.group(1).split('/')[0]
                            break
                        break

                    if pkg and pkg not in stopped_packages:
                        try:
                            self.u2d_helper.stop_app(pkg)
                            stopped_packages.add(pkg)
                            self.logdebug(f"已停止画中画应用: {pkg}")
                        except Exception as e:
                            self.logerror(f"停止画中画应用 {pkg} 失败: {str(e)}")
        except Exception as e:
            self.logerror(f"获取画中画应用信息失败: {str(e)}")
            
        return

    def stop_music_or_video_playing_apps(self):
        stopped_packages = set()
        try:
            output_lines  = adb.exec_cmd(self.serial, "dumpsys media_session")
            if not output_lines:
                return
            output = "\n".join(output_lines)
                
            # 匹配 PlaybackState=STATE_PLAYING 的会话
            for section in output.split("Sessions Stack"):
                if "state=PlaybackState {state=3" in section or "state=PLAYING" in section:
                    pkg = None
                    match =  re.search(r"package=([^\s]+)", section)
                    if match:
                        pkg = match.group(1).strip()                 
                    if pkg and pkg not in stopped_packages:
                        try:
                            self.u2d_helper.stop_app(pkg)
                            stopped_packages.add(pkg)
                            self.logdebug(f"已停止正在播放媒体的应用: {pkg}")
                        except Exception as e:
                            self.logerror(f"停止正在播放的媒体应用 {pkg} 失败: {str(e)}")
        except Exception as e:
            self.logerror(f"获取媒体会话信息失败: {str(e)}")
        return

    def standby_monkey(self):
        adb.exec_cmd_no_nohup(self.serial, f"monkey \
                              --ignore-crashes \
                              --ignore-timeouts \
                              --ignore-security-exceptions \
                              --kill-process-after-error \
                              --pct-trackball 0 \
                              --pct-nav 0 \
                              --pct-majornav 0 \
                              --pct-anyevent 0 \
                              -v -v \
                              --throttle 800 21600 > NUL 2>&1")
    
    def env_init(self):
        adb.poweron_screen_and_unlock(self.serial)
        time.sleep(1)
        self.u2d_helper.press_home_key()
        time.sleep(0.5)
        self.stop_pip_apps()
        self.u2d_helper.set_all_volume_level(5)
        self.u2d_helper.set_brightness_and_close_auto_bright(102)
        self.loginfo(f"pre_phone_copilot_switch_language_en")
        self.pre_phone_copilot_switch_language_en()
        self.loginfo(f"pre_phone_developer")
        self.pre_phone_developer()
        self.loginfo(f"pre_phone_copilot_restore_control_center_status")
        self.pre_phone_copilot_restore_control_center_status()
        self.loginfo(f"pre_phone_switch_keyboard_default")
        self.pre_phone_switch_keyboard_default()
        self.loginfo(f"pre_phone_switch_navi_mode_3_buttons")
        self.pre_phone_switch_navi_mode_3_buttons()
        self.loginfo(f"pre_phone_close_non_disturb_mode")
        self.pre_phone_close_non_disturb_mode()
        self.loginfo(f"pre_phone_close_clock")
        self.pre_phone_close_clock()
        self.loginfo(f"pre_phone_copilot_switch_dialer_default")
        self.pre_phone_copilot_switch_dialer_default()
        self.loginfo(f"pre_phone_clean_and_push_necessary_files")
        self.pre_phone_clean_and_push_necessary_files()
        self.loginfo(f"pre_phone_close_sidebar")
        self.pre_phone_close_sidebar()
        self.loginfo(f"pre_phone_copilot_close_google_protect")
        self.pre_phone_copilot_close_google_protect()
        self.loginfo(f"pre_phone_check_wifi_connection")
        self.pre_phone_check_wifi_connection()
        self.loginfo(f"pre_check_installed_apps_and_grant_permissions")
        self.check_installed_apps_and_grant_permissions()
        self.loginfo(f"pre_app_google_play_update")
        for cnt in range(5):
            try:
                self.pre_app_google_play_update()
                break
            except Exception as e:
                self.logerror(f"pre_app_google_play_update 失败: {str(e)}")
                if cnt == 4:
                    raise e
        try:
            self.loginfo(f"pre_phone_check_time")
            self.pre_phone_check_time()
        except Exception as e:
            self.logerror(f"pre_phone_check_time 失败: {str(e)}")
        self.loginfo(f"pre_phone_close_auto_update")
        self.pre_phone_close_auto_update()
        self.loginfo(f"pre_app_visha_video")
        self.pre_app_visha()
        self.loginfo(f"pre_app_mxplayer")
        self.pre_app_mxplayer()
        self.loginfo(f"pre_app_youtube")
        self.pre_app_youtube()
        #self.loginfo(f"pre_app_tiktok")
        #self.pre_app_tiktok()
        self.loginfo(f"pre_app_instagram")
        self.pre_app_instagram()
        self.loginfo(f"pre_app_gallery")
        self.pre_app_gallery()
        #断网测试
        self.loginfo(f"pre_app_YTMusic")
        self.pre_app_YTMusic()
        self.loginfo(f"pre_app_candycrash")
        self.pre_app_candycrash()
        
    def resourceid_click(self, idname: str, delay: float = 1) -> bool:
        for i in range(2):
            try:
                exists = self.u2d(resourceId=idname).exists(timeout=delay)
            except TypeError:
                time.sleep(delay)
                exists = self.u2d(resourceId=idname).exists
            if(exists):
                time.sleep(0.5)
                self.u2d(resourceId=idname).click()
                time.sleep(0.2)
                return True

        #print(f"[{pmsn}] - {idname} 不存在")
        return False
    
    #高通平台日志操作指导 https://transsioner.feishu.cn/docx/ALo5dVn4PoiqPMxiHhhccwAonw5
    def _tran_log_start(self):
        self._tran_log_stop()
        time.sleep(3)
        #删除debuglogger 目录下的所有文件
        adb.exec_cmd(self.serial, "find /data/debuglogger/ -type f -delete")
        #启动日志记录
        adb.exec_cmd(self.serial, "setprop debug.logd.applogcat 1")
        adb.exec_cmd(self.serial, "setprop debug.logd.mainlogcat 1")
        adb.exec_cmd(self.serial, "setprop debug.logd.systemlogcat 1")
        adb.exec_cmd(self.serial, "setprop debug.logd.eventslogcat 1")
        adb.exec_cmd(self.serial, "setprop debug.logd.radiologcat 1")
        adb.exec_cmd(self.serial, "setprop debug.logd.crashlogcat 1")
        adb.exec_cmd(self.serial, "setprop debug.logd.kernellogcat 1")
        adb.exec_cmd(self.serial, "setprop debug.logd.securitylogcat 1")
    
    def _tran_log_stop(self):
        adb.exec_cmd(self.serial, "setprop debug.logd.applogcat 0")
        adb.exec_cmd(self.serial, "setprop debug.logd.mainlogcat 0")
        adb.exec_cmd(self.serial, "setprop debug.logd.systemlogcat 0")
        adb.exec_cmd(self.serial, "setprop debug.logd.eventslogcat 0")
        adb.exec_cmd(self.serial, "setprop debug.logd.radiologcat 0")
        adb.exec_cmd(self.serial, "setprop debug.logd.crashlogcat 0")
        adb.exec_cmd(self.serial, "setprop debug.logd.kernellogcat 0")
        adb.exec_cmd(self.serial, "setprop debug.logd.securitylogcat 0")
        time.sleep(3)
    
    def _tran_log_get(self, logfile):
        #判断mobilelog 目录是否存在    
        for i in range(10):
            adb.exec_cmd(self.serial, "sync")
            mobilelog_dir_exists = adb.exec_cmd(self.serial, "ls /data/debuglogger/")
            if "mobilelog" in mobilelog_dir_exists:
                break
            time.sleep(1)
        if "mobilelog" not in mobilelog_dir_exists:
            self.logwarning(f"mobilelog 目录不存在")
            return
        time.sleep(5)
        adb.pull_file(self.serial, "/data/debuglogger", logfile)
        
    def _mtk_log_start(self):
        adb.exec_cmd(self.serial, "am broadcast -a com.debug.loggerui.ADB_CMD -e cmd_name stop --ei cmd_target 23 -n com.debug.loggerui/.framework.LogReceiver")
        time.sleep(3)
        #清除所有日志
        adb.exec_cmd(self.serial, "am broadcast -a com.debug.loggerui.ADB_CMD -e cmd_name clear_logs_all --ei cmd_target 0 -n com.debug.loggerui/.framework.LogReceiver")
        #启动日志记录 23可改为1/2/4/16，分别代表MobileLog/ModemLog/NetworkLog/GPSLog
        adb.exec_cmd(self.serial, "am broadcast -a com.debug.loggerui.ADB_CMD -e cmd_name start --ei cmd_target 5 -n com.debug.loggerui/.framework.LogReceiver")

    def _mtk_log_stop(self):
        adb.exec_cmd(self.serial, "am broadcast -a com.debug.loggerui.ADB_CMD -e cmd_name stop --ei cmd_target 23 -n com.debug.loggerui/.framework.LogReceiver")
        
    def _mtk_log_get(self, logfile):
        self._tran_log_get(logfile)
        
    def phone_log_start(self):
        if self.platform == "mtk":
            self._mtk_log_start()
        elif self.platform == "qcom":
            self._tran_log_start()
        else :
            self._tran_log_start()
    
    def phone_log_stop(self):
        if self.platform == "mtk":
            self._mtk_log_stop()
        elif self.platform == "qcom":
            self._tran_log_stop()
        else :
            self._tran_log_stop()

    def phone_log_get(self, logfile):
        if self.platform == "mtk":
            self._mtk_log_get(logfile)
        elif self.platform == "qcom":
            self._tran_log_get(logfile)
        else :
            self._tran_log_get(logfile)
    
    def phone_log_stop_save(self) -> str:
        self.phone_log_stop()
        time.sleep(20)
        logdir = f"{self.logrootdir}/{self.logsubdir}/{self.taskid}"
        self.phone_log_get(logdir)
        return logdir

    def clean_backapp(self) -> bool:
        adb.press_back_key(self.serial)
        time.sleep(0.5)
        adb.press_back_key(self.serial)
        time.sleep(0.5)
        adb.press_home_key(self.serial)
        time.sleep(0.5)
        adb.press_app_switch_key(self.serial)
        time.sleep(0.5)
        # 增加等待时间和调试信息
        element1 = self.u2d(resourceId="com.transsion.hilauncher:id/recents_memory_container")
        element2 = self.u2d(resourceId="com.transsion.launcher3:id/recents_memory_container")
        if element1.exists(timeout=1):
            element1.click()
        elif element2.exists(timeout=1):
            element2.click()
        else:
            adb.press_back_key(self.serial)
            return False
        adb.press_back_key(self.serial)
        return True
    
    
    # ---------------------------- Phone/Copilot 测试机/辅助机环境预测试 开始 -------------------------------------

    def pre_phone_close_sidebar(self):
        """
        关闭侧边栏
        """
        self.u2d_helper.close_sidebar()
        time.sleep(1)

    def pre_phone_close_data_warn(self):
        """
        关闭数据警告
        """
        self.u2d_helper.close_data_warn()

    def pre_phone_copilot_switch_language_en(self):
        """
        切换到英文语言
        """
        self.u2d_helper.check_switch_language_en()

    def pre_phone_copilot_ai_net_control_disable(self):
        """
        关闭AI网络控制
        """
        if not self.u2d_helper.get_ai_net_control_enable():
            self.u2d_helper.disable_ai_net_control_enable()
            self.u2d_helper.reboot_and_wait_complete()
            self.u2d_helper.screen_on_and_unlock()


    def pre_phone_check_time(self):
        """
        检查PC和Android手机的时间差
        """
        self.u2d_helper.assert_time_with_pc(10)

    def pre_phone_switch_keyboard_default(self):
        """
        切换到默认键盘
        """
        self.u2d_helper.switch_keyboard_default()

    def pre_phone_settle_settings_down(self):
        """
        确保Settings应用在底部
        """
        if not self.u2d_helper.check_app_position('Settings', 3):
            self.u2d_helper.search_and_move_app_to_home('Settings', 3)

    def pre_phone_copilot_restore_control_center_status(self, mode_dou=True):
        """
        恢复控制中心状态
        """
        self.u2d_helper.assert_swipe_unlock_mode()
        self.u2d_helper.set_aod_enabled(False)
        self.u2d_helper.set_dynamic_island_open_close(True)
        self.u2d_helper.set_inadvertently_mode_open_close(False)
        self.u2d_helper.assert_hotspot_closed()
        self.u2d_helper.set_heads_up_notify_enabled(False)
        self.u2d_helper.open_close_auto_brightness(False)
        self.u2d_helper.open_close_auto_rotate(False)
        self.u2d_helper.set_screen_fps_auto()
        self.u2d_helper.close_sleep_mode()
        self.u2d_helper.set_long_screen_sleep_time()
        self.u2d_helper.close_low_battery_remainder()
        if mode_dou: # 仅对DOU测试有效
            self.u2d_helper.open_close_airplane_mode(False)
            self.u2d_helper.open_close_wifi(True)
            self.u2d_helper.open_close_bluetooth(True)
            self.u2d_helper.open_close_location_service(True)
            self.u2d_helper.open_close_nfc(True)
            self.u2d_helper.open_close_mobile_data(True)

    def pre_phone_copilot_close_google_protect(self):
        """
        关闭Google Protect
        """
        self.u2d_helper.close_google_protect()
        
    def pre_phone_model_set_brightness_with_area_set(self):
        """
        设置手机亮度
        """
        info = self.global_config.phone_infos[self.model]
        area_set = self.global_config.user_config.case_area_or_set
        self.u2d_helper.set_brightness_and_close_auto_bright(info[f"{area_set}_bl"])
        return info[f"{area_set}_bl"]
        
    def pre_phone_model_set_volume_with_area_set(self):
        """
        设置手机音量
        """
        info = self.global_config.phone_infos[self.model]
        area_set = self.global_config.user_config.case_area_or_set
        self.u2d_helper.set_all_volume_level(info[f"{area_set}_vol"])
        return info[f"{area_set}_vol"]

    def pre_phone_switch_navi_mode_3_buttons(self):
        """
        切换导航模式为3个按钮
        """
        self.u2d_helper.set_navi_mode_3_buttons()

    def pre_phone_assert_double_click_wake(self):
        assert not self.u2d_helper.is_double_tap_screen_wake_open, 'Main Test Phone MUST NOT enable Double-Tap wake feature! Please close it.'

    def pre_phone_check_auto_network(self):
        self.u2d_helper.close_wifi_auto_switch()

    def pre_phone_check_wifi_connection(self):
        # 不要自动打开wifi
        check_device_to_link_wifi(self.u2d, "power_cloud", "1234567809")
        try:
            self.u2d_helper.check_network_connections(True)
        except Exception:
            raise Exception("Phone wifi connection failed")

    def pre_phone_check_mobile_data_connection(self):
        if adb.is_wifi_open(self.serial):
            self.u2d_helper.open_close_wifi(False)
            time.sleep(5)
        if not adb.is_mobile_data_open(self.serial):
            self.u2d_helper.open_close_mobile_data(True)
            time.sleep(5)
        try:
            if not self.is_overseas:
                # 如果是国内，需要提前打开VPN
                self.u2d_helper.press_home_key(times=3)
                self.u2d_helper.open_close_linsoc_vpn(True,True)
                try:
                    time.sleep(2)
                    self.u2d_helper.check_network_connections(True)
                finally:
                    self.u2d_helper.und_u2.click(0.82, 0.60)
                    self.u2d_helper.open_close_linsoc_vpn(True,True)
            else:
                import locale
                if '_CN' in locale.getdefaultlocale()[0]:
                    self.u2d_helper.check_network_connections(False)
                else:
                    self.u2d_helper.check_network_connections(True)
        except Exception:
            self.u2d_helper.open_close_wifi(True)
            raise Exception("Phone mobile data connection failed")
        self.u2d_helper.open_close_wifi(True)

    def pre_phone_close_non_disturb_mode(self):
        self.u2d_helper.assert_non_disturb_mode_close()# 关闭勿扰模式
        
    def pre_phone_close_clock(self):
        app_package = 'com.transsion.deskclock'
        self.u2d_helper.stop_app(app_package)
        self.u2d.sleep(1)
        self.u2d_helper.start_app(app_package)
        self.u2d.sleep(2)
        #关闭所有闹钟
        if self.u2d(resourceId="com.transsion.deskclock:id/os_foot_opt_bar_item_text", text="Alarm").exists():
            self.u2d(resourceId="com.transsion.deskclock:id/os_foot_opt_bar_item_text", text="Alarm").click()
        else :
            self.u2d(text="Alarm").click()
        self.u2d.sleep(1)
        alarm_count = self.u2d(resourceId="com.transsion.deskclock:id/onoff").count
        if alarm_count > 0:
            for i in range(alarm_count):
                switch = self.u2d.xpath(
                    f'//*[@resource-id="com.transsion.deskclock:id/alarms_recycler_view"]'
                    f'/android.view.ViewGroup[{i + 1}]/android.view.ViewGroup[1]/android.widget.Switch[1]'
                )
                if switch.info['checked']:
                    switch.click()
        self.u2d.sleep(1)
        #复位倒计时
        if self.u2d(resourceId="com.transsion.deskclock:id/os_foot_opt_bar_item_text", text="Timer").exists():
            self.u2d(resourceId="com.transsion.deskclock:id/os_foot_opt_bar_item_text", text="Timer").click()
        else:
            self.u2d(text="Timer").click()
        self.u2d.sleep(1)
        if self.u2d(resourceId="com.transsion.deskclock:id/left_button").info['enabled']:
            self.u2d(resourceId="com.transsion.deskclock:id/left_button").click()
        self.u2d.sleep(1)
        #关闭秒表
        if self.u2d(resourceId="com.transsion.deskclock:id/os_foot_opt_bar_item_text", text="Stopwatch").exists():
            self.u2d(resourceId="com.transsion.deskclock:id/os_foot_opt_bar_item_text", text="Stopwatch").click()
        else:
            self.u2d(text="Stopwatch").click()
        self.u2d.sleep(1)
        if self.u2d(resourceId="com.transsion.deskclock:id/right_button").info['enabled']:
            self.u2d(resourceId="com.transsion.deskclock:id/fab").click()
            self.u2d.sleep(1)
        if self.u2d(resourceId="com.transsion.deskclock:id/left_button").info['enabled']:
            self.u2d(resourceId="com.transsion.deskclock:id/left_button").click()
        self.u2d.sleep(1)
        self.u2d_helper.press_home_key()
    '''
    def pre_phone_record_phone_number_and_cn_sim_index(self):
        if self.is_overseas:
            if self.userconfig.test_region == 'KE':
                ke_number = self.u2d_helper.get_phone_number_ke()
            else:
                # 获取现有电话号码
                now_number = self.dou3_env.get_test_phone_number(True)
                # 其他国家使用手动输入电话号码
                overseas_number = self.u2d_helper.get_phone_number_manual_window(tips='Enter [TEST PHONE] number:',
                                                                                 default_number=now_number)
                assert len(overseas_number) > 3, 'The length of the phone number must be greater than 3.'
                # raise Exception(f'Can not get test phone number for area {self.dou3_env.case_area_set}')
        else:
            cn_index, cn_number = self.u2d_helper.get_cn_sim_index_and_number()
    '''
    def pre_phone_close_desktop_auto_align(self):
        self.u2d_helper.close_desktop_auto_align()

    def pre_phone_close_auto_update(self):
        self.u2d_helper.close_auto_update()

    def pre_phone_copilot_switch_dialer_default(self):
        self.u2d_helper.set_dialer_default()

    def pre_phone_developer(self):
        adb.stop_settings_activity(self.serial)
        adb.open_settings_activity(self.serial)
        if self.u2d(textMatches=".*Search.*").exists(timeout=5):
            search_box = self.u2d(textMatches=".*Search.*")
        else:
            assert False, 'search box not found'
        search_box.click(timeout=5)
        self.u2d.sleep(1)
        self.u2d.send_keys('Developer O')
        self.u2d.sleep(1)
        if self.u2d(textContains="Developer Options").exists(timeout=5):
            return True
        adb.stop_settings_activity(self.serial)
        adb.open_settings_activity(self.serial)
        if self.u2d(textMatches=".*Search.*").exists(timeout=5):
            self.u2d(textMatches=".*Search.*").click(timeout=5)
        else:
            assert False, 'search box not found'
        self.u2d.sleep(1)
        self.u2d.send_keys('build N')
        if self.u2d(textContains="Build Number").exists(timeout=10):
            self.u2d(textContains="Build Number").click(timeout=5)
            self.u2d.sleep(1)
        else:
            assert False, 'Build Number not found'
        for i in range(7):
            self.u2d.sleep(0.5)
            self.u2d(textMatches=".*uild .*umber").click(timeout=1)
        '''
        adb.stop_settings_activity(self.serial)
        adb.open_settings_activity(self.serial)
        if self.u2d(textMatches=".*Search.*").exists(timeout=5):
            self.u2d(textMatches=".*Search.*").click(timeout=5)
        else:
            assert False, 'search box not found'
        self.u2d.sleep(1)
        self.u2d.send_keys('USB D')
        if self.u2d(textContains="USB Ddebugging").exists(timeout=10):
            self.u2d(textContains="USB Ddebugging").click(timeout=5)
            self.u2d.sleep(1)
        else:
            assert False, 'USB Ddebugging not found'
        '''

    def pre_phone_clean_and_push_necessary_files(self):
        if not adb.package_is_installed(self.serial, 'com.transsion.filemanagerx'):
            if not self.u2d_helper.check_file_exists('/data/local/tmp/FileManager_com.transsion.filemanagerx.apk'):
                self.global_config.res_provider.push_to_device('apk_res/FileManager_com.transsion.filemanagerx.apk', self.serial,
                                                 '/data/local/tmp/', overwrite_exists=True)
            adb.exec_cmd(self.serial, 'pm install /data/local/tmp/FileManager_com.transsion.filemanagerx.apk')
            self.u2d_helper.grant_file_management_permissions('com.transsion.filemanagerx')

        # 删除googlefiles复制的文件
        self.u2d_helper.delete_except('/sdcard/AAA', [])
        adb.make_dirs(self.serial, '/sdcard/AAA')
        # 推资源
        if (
        not self.u2d_helper.check_file_exists('/sdcard/500Mfile.zip')) and self.global_config.user_config.case_area_or_set == 'africa':
            self.global_config.res_provider.push_to_device('dou3/500Mfile.zip', self.serial, '/sdcard/', overwrite_exists=True)

        # 删除MyAlbums除了彩色图片和那些年的其他资源（For Ai gallery）
        self.u2d_helper.delete_except('/sdcard/DCIM', [])

        adb.uninstall_apk(self.serial, 'com.rovio.abcasual')

        # 在drive文件里找，不需要更新
        if not self.u2d_helper.check_file_exists('/sdcard/CM5-STR5.pdf'):
            self.global_config.res_provider.push_to_device('dou3/CM5-STR5.pdf', self.serial, '/sdcard/', overwrite_exists=True)

        # 不需要更新
        self.u2d_helper.delete_except('/sdcard/Music', ['lonely'])
        if not self.u2d_helper.check_file_exists('/sdcard/Music/lonely.mp3'):
            self.global_config.res_provider.push_to_device('dou3/lonely.mp3', self.serial, '/sdcard/Music/', overwrite_exists=True)

        self.u2d_helper.delete_except('/sdcard/MyAlbums', ['^colorful$', '^naxienian$'])
        if not self.u2d_helper.check_file_exists('/sdcard/MyAlbums/colorful/wp_power.jpg'):
            self.global_config.res_provider.push_to_device('dou3/colorful', self.serial, '/sdcard/MyAlbums/',
                                             overwrite_exists=True)
        if not self.u2d_helper.check_file_exists('/sdcard/MyAlbums/naxienian/1080.mp4'):
            self.global_config.res_provider.push_to_device('dou3/1080.mp4', self.serial, '/sdcard/MyAlbums/naxienian/',
                                             overwrite_exists=True)
        # if not self.u2d_helper.check_file_exists('/sdcard/MyAlbums/filter'):
            self.global_config.res_provider.push_to_device('dou3/filter_picture.jpg', self.serial, '/sdcard/MyAlbums/filter/',
                                         overwrite_exists=True)
        adb.poweron_screen_and_unlock(self.serial)
        # if adb.is_mtk(self.serial):
        self.u2d.app_stop("com.transsion.filemanagerx")
        self.u2d.sleep(1)
        self.u2d.app_start("com.transsion.filemanagerx")
        self.u2d.sleep(3)
        # self.u2d.xpath('//*[@resource-id="com.transsion.filemanagerx:id/mbtnOk"]').click(timeout=2)
        self.u2d.xpath('//*[@resource-id="com.transsion.filemanagerx:id/mbtnOk"]').click_exists(timeout=2)
        self.u2d(text="Browse").click()
        self.u2d.sleep(1)
        self.u2d(text="My Phone").click()
        self.u2d.sleep(1)
        self.u2d.swipe(0.5, 0.3, 0.5, 0.7)
        self.u2d.app_stop("com.transsion.filemanagerx")

        # # 重启更新资源
        # self.u2d_helper.reboot_and_wait_complete()
        # time.sleep(10)
        # self.u2d_helper.screen_on_and_unlock()
        
    def pre_app_google_play_update(self):
        app_name = 'GooglePlay'
        app_info = self.global_config.table_apps[app_name]
        self.u2d.app_stop(app_info['package'])
        time.sleep(2)
        self.u2d.app_start(app_info['package'])
        time.sleep(5)
        # 如果没登录, 自动登录某个账号
        if self.u2d.xpath('//*[@text="Sign in"]').exists:
            time.sleep(1)
            self.u2d.xpath('//*[@text="Sign in"]').click()
            self.u2d_helper.click_wait('//android.widget.EditText', pre_wait=10, timeout=40, post_wait=5)
            self.u2d_helper.input_text(self.global_config.user_config.config_dict['accounts']['google_email'])
            time.sleep(1)
            self.u2d.xpath('//*[@text="Next"]').click()
            self.u2d_helper.click_wait('//android.widget.EditText', pre_wait=10, timeout=40, post_wait=5)
            self.u2d_helper.input_text(self.global_config.user_config.config_dict['accounts']['google_password'])
            time.sleep(1)
            self.u2d.xpath('//*[@text="Next"]').click()
            time.sleep(30)
            self.u2d.xpath('//*[@text="Next"]').click_exists(timeout=5)
            self.u2d_helper.click_wait('//*[@text="I agree"]', pre_wait=10, timeout=10, post_wait=5)
            self.u2d.swipe(0.5, 0.7, 0.5, 0.2)
            self.u2d_helper.click_wait('//android.widget.Button[@text="Accept"]', pre_wait=10, timeout=40, post_wait=5, no_raise=True)
            time.sleep(10)
        # 第一次进入的弹窗
        if self.u2d.xpath('//*[@content-desc="Not now"]').exists:
            self.u2d.xpath('//*[@content-desc="Not now"]').click()
            time.sleep(2)
        if self.u2d.xpath('//*[@text="No thanks"]').exists:
            self.u2d.xpath('//*[@text="No thanks"]').click()
            time.sleep(2)
        if self.u2d.xpath('//*[@text="Meet the Search tab"]').exists:
            self.u2d.xpath('//*[@text="Meet the Search tab"]').click()
            time.sleep(2)
        
        self.u2d_helper.click_wait(self.u2d(resourceId="com.android.vending:id/0_resource_name_obfuscated"), pre_wait=1, timeout=5)
        self.u2d_helper.click_wait(self.u2d(textMatches=".*Manage apps.*"), pre_wait=1, timeout=5)
        time.sleep(5)
        if(self.u2d(textMatches=".*Updat.*").exists(timeout= 5)):
            self.u2d(textMatches=".*Updat.*").click()
            time.sleep(5)
            if self.u2d.xpath('//*[@text="Cancel all"]').exists:
                self.u2d.xpath('//*[@text="Cancel all"]').click()
                time.sleep(3)
            if self.u2d.xpath('//*[@text="Update all"]').exists:
                self.u2d.xpath('//*[@text="Update all"]').click()
                self.u2d.xpath('//*[@text="Continue"]').click_exists(timeout=2)
                while True:
                    time.sleep(1)
                    if self.u2d.xpath('//*[@text="OK"]').exists:
                        self.u2d.xpath('//*[@text="OK"]').click()
                    else:
                        break
            while True:
                time.sleep(1)
                self.u2d.swipe(0.5, 0.3, 0.5, 0.7)
                if self.u2d.xpath('//*[@text="Cancel all"]').exists:
                    continue
                break
        self.u2d.app_stop(app_info['package'])

    def pre_app_mxplayer(self):
        from tests.current_analysis.test_cases.C17_mxplayer import mxplayer_check
        mxplayer_check(self)

    def pre_app_youtube(self):
        from tests.current_analysis.test_cases.C19_youtube import youtube_check
        youtube_check(self)

    def pre_app_tiktok(self):
        from tests.current_analysis.test_cases.C20_tiktok import tiktok_check
        tiktok_check(self)

    def pre_app_instagram(self):
        from tests.current_analysis.test_cases.C22_instagram import instagram_check
        instagram_check(self)

    def pre_app_gallery(self):
        from tests.current_analysis.test_cases.C03_gallery import Gallery_start
        if not Gallery_start(self):
            raise Exception('Gallery start failed')
        time.sleep(10)
        self.clean_backapp()
        
    def pre_app_YTMusic(self):
        from tests.current_analysis.test_cases.C09_yt_music import yt_start
        if not yt_start(self):
            raise Exception('Youtube music play failed')
        time.sleep(10)
        self.clean_backapp()
    
    def pre_app_visha(self):
        from tests.current_analysis.test_cases.C18_visha_video import visha_check
        if not visha_check(self, 10):
            raise Exception('Visha video play failed')

    def pre_app_candycrash(self):
        from tests.current_analysis.test_cases.C16_candycrash import candycrash_check
        if not candycrash_check(self, 10):
            raise Exception('Candy crash play failed')

    def get_refresh_rate(self):
        try:
            # 方法1: 使用dumpsys display命令查找当前刷新率
            output_lines = adb.exec_cmd(self.serial, "dumpsys SurfaceFlinger")
            if output_lines:
                for line in output_lines:
                    # 查找当前刷新率信息
                    if "refresh" in line.lower() and "rate" in line.lower():
                        # 尝试多种格式匹配
                        patterns = [
                            r'peak-refresh-rate.*?(\d+(\.\d+)?)', 
                        ]
                        for pattern in patterns:
                            match = re.search(pattern, line, re.IGNORECASE)
                            if match:
                                refresh_rate = float(match.group(1))
                                self.loginfo(f"获取到当前刷新率: {refresh_rate}Hz")
                                return refresh_rate
            
            self.logwarning("无法获取到当前屏幕刷新率信息")
            return None
            
        except Exception as e:
            self.logerror(f"获取当前刷新率时出错: {str(e)}")
            return None

    def get_screen_brightness(self):
        try:
            # 使用settings命令获取亮度值
            settings_output = adb.exec_cmd(self.serial, "settings get system screen_brightness")
            
            if not settings_output or len(settings_output) == 0:
                self.logwarning("settings命令未返回任何结果")
                return None
            
            # 处理返回值
            brightness_str = settings_output[0].strip()
            
            # 检查是否为有效的数字字符串
            if not brightness_str.isdigit():
                self.logwarning(f"settings命令返回非数字值: {brightness_str}")
                return None
            
            # 转换为整数并验证范围
            brightness = int(brightness_str)
            
            # 亮度值通常在0-255或0-1023范围内
            if 0 <= brightness <= 1023:
                self.loginfo(f"获取到当前屏幕亮度: {brightness}")
                return brightness
            else:
                self.logwarning(f"settings命令返回亮度值超出有效范围: {brightness}")
                return None
                
        except Exception as e:
            self.logerror(f"获取当前屏幕亮度时出错: {str(e)}")
            return None
            
    def screenshot(self, filename=None):
        try:
            if filename is None:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{timestamp}.png"
            if not filename.lower().endswith('.png'):
                filename += '.png'
            base_dir = os.path.abspath(f"{self.logrootdir}/{self.logsubdir}/{self.taskid}")
            screenshot_dir = os.path.join(base_dir, "screenshot")  # 创建screenshot子文件夹
            # 确保screenshot文件夹存在
            os.makedirs(screenshot_dir, exist_ok=True)
            local_path = os.path.join(screenshot_dir, filename)
            # 截图保存路径（手机端）
            phone_path = f"/sdcard/Pictures/{filename}"
            # 执行截图命令（需要在shell中执行）
            adb.exec_cmd(self.serial, f"screencap -p {phone_path}")
            # 验证截图是否成功保存到手机
            result = adb.exec_cmd(self.serial, f"ls -la {phone_path}")
            if result and len(result) > 0:
                # 使用正确的adb_pull函数，避免将pull命令放在shell中执行
                adb.pull_file(self.serial, phone_path, local_path)
                # 验证本地文件是否存在
                if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                    self.loginfo(f"截图成功")
                    return local_path
                else:
                    self.logwarning(f"截图已保存到手机，但拉取到本地失败: {local_path}")
                    return None
            else:
                self.logwarning(f"截图命令执行成功，但无法验证手机文件是否存在: {phone_path}")
                return None
                
        except Exception as e:
            self.logerror(f"截图失败: {str(e)}")

    def get_board_temperature(self):
        try:
            # 使用dumpsys thermalservice命令获取温度信息
            thermalservice_output = adb.exec_cmd(self.serial, "dumpsys thermalservice")
            if thermalservice_output and len(thermalservice_output) > 0:
                # 标记是否进入Current temperatures from HAL部分
                in_current_temperatures_section = False
                # 遍历输出行，先定位到Current temperatures from HAL部分
                for line in thermalservice_output:
                    # 检查是否到达Current temperatures from HAL部分的起始行
                    if "Current temperatures from HAL:" in line:
                        in_current_temperatures_section = True
                        continue
                    # 检查是否到达下一个部分的起始行（以大写字母开头的行）
                    # 例如"Current cooling devices from HAL:"或"Temperature static thresholds from HAL:"等
                    if in_current_temperatures_section and line.strip() and line.strip()[0].isupper() and ":" in line.strip():
                        break
                    # 只在Current temperatures from HAL部分中查找SOC温度
                    if in_current_temperatures_section and "mType=3" in line and ("mName=SKIN" in line or "mName=skin" in line):
                        try:
                            value_str = line.split("mValue=")[1].split(",")[0]
                            temp_celsius = float(value_str)
                            # 验证温度值的合理性（20-100℃范围）
                            if 20 <= temp_celsius <= 100:
                                self.loginfo(f"获取到当前SKIN温度: {temp_celsius:.2f}°C")
                                return temp_celsius
                            else:
                                self.logwarning(f"SKIN温度值不合理: {temp_celsius}°C")
                        except (IndexError, ValueError) as e:
                            self.logwarning(f"解析SKIN温度值失败: {str(e)}")
                # 如果没有在Current temperatures from HAL部分找到SKIN温度信息
                self.logwarning("未在Current temperatures from HAL部分找到SKIN温度信息")
            else:
                self.logwarning("执行thermalservice命令失败，无返回内容")
            return None
        except Exception as e:
            self.logerror(f"获取当前SOC温度时出错: {str(e)}")
            return None