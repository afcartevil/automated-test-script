import os.path

from powertrde.utils.trde import adb
import time
import re
from tests.dzppt.therm.scenes.life_therm_scenes_mix_in import LifethermScenesMixIn


class CasesThermScenes(LifethermScenesMixIn):
    def case_therm_mock_1(self):
        ...

    def case_therm_mock_2(self):
        print('正在测试用例2')

    # ----------------------------------------- Q平台 -------------------------------------------------
    def case_therm_generated_platform_thermal_qcom(self):
        """thermal zone,cooling device是否正常生成"""
        data = adb.exec_cmd(self.device_id,
                            "i=0; while [[ $i -lt 80 ]] ;do (type=`cat /sys/class/thermal/thermal_zone$i/type`;"
                            "temp=`cat /sys/class/thermal/thermal_zone$i/temp`; echo "'$i $type : $temp'"); i=$((i+1));done")
        ntc_temp_result = 'True'
        ntc_temp_list = []
        for item in data:
            if "sys-therm-" in item:
                ntc_temp_list.append(item)
                parts = item.split(":")
                if len(parts) > 1:
                    ntc_temp = int(parts[1].strip())
                    if "sys-therm-8" in item and (not 50 > ntc_temp / 10 > 20):
                        ntc_temp_result = 'False'
                        continue
                    if not 50000 > ntc_temp > 20000:
                        ntc_temp_result = 'False'
        self.logger.info("\n*** thermal zone,cooling device是否正常生成 ***\n" + "- " + "\n".join(ntc_temp_list) + "\n", ext_event=True)
        self.log_result(bool(ntc_temp_result and ntc_temp_list))

    def case_therm_read_ntc_temp_qcom(self):
        """NTC温度是否能否正常读取"""
        data = adb.exec_cmd(self.device_id,
                            "i=0; while [[ $i -lt 80 ]] ;do (type=`cat /sys/class/thermal/thermal_zone$i/type`;"
                            "temp=`cat /sys/class/thermal/thermal_zone$i/temp`; echo "'$i $type : $temp'"); i=$((i+1));done")
        ntc_temp_result, ntc_temp = 'True', 0
        ntc_temp_list = []
        for item in data:
            if "sys-therm-" in item:
                ntc_temp_list.append(item)
                parts = item.split(":")
                if len(parts) > 1:
                    ntc_temp = int(parts[1].strip())
                    if "sys-therm-8" in item and (not 50 > ntc_temp / 10 > 20):
                        ntc_temp_result = 'False'
                        continue
                    if not 50000 > ntc_temp > 20000:
                        ntc_temp_result = 'False'
        self.logger.info("\n- thermal zone,cooling, device是否正常生成：\n" + "- " + "\n".join(ntc_temp_list) + "\n", ext_event=True)
        self.logger.info(f"\n*** NTC温度是否能否正常读取 ***\n {ntc_temp}", ext_event=True)
        self.log_result(bool(ntc_temp_result and ntc_temp_list))

    def case_therm_working_thermal_framework_qcom(self):
        """Thermal框架工作是否正常"""
        data = adb.exec_cmd(self.device_id, 'ps -A | grep thermal-engine')
        self.logger.info("\n*** Thermal框架工作是否正常 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool('thermal-engine' in str(data)))

    def case_therm_working_qt_service_qcom(self):
        """qt-setvice是否工作正常"""
        data = adb.exec_cmd(self.device_id, 'ps -A | grep qt-service')
        self.logger.info("\n*** qt-service是否工作正常 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool('qt-service' in str(data)))

    def case_therm_step_freq_cpu_qthermal_cfg_qcom(self):
        """阶梯控频_CPU多阶调频_高通thermal通用配置"""
        if not os.path.exists(os.path.join(self.runtime_dir, 'thermal-engine.conf')):
            adb.pull_file(self.device_id, "vendor/etc/thermal-engine.conf", self.runtime_dir)
        data1 = adb.exec_cmd(self.device_id, "cat vendor/etc/thermal-engine.conf")
        result1 = bool('DEFAULT_STEP_CPU' in str(data1))
        self.logger.info(
            "\n*** 阶梯控频_CPU多阶调频_高通thermal通用配置 thermal-engine.conf ***\n" + "- " + "\n".join(data1) + "\n",
            ext_event=True)
        if not os.path.exists(os.path.join(self.runtime_dir, 'qt-service_config.xml')):
            adb.pull_file(self.device_id, "vendor/etc/qt-service_config.xml", self.runtime_dir)
        data2 = adb.exec_cmd(self.device_id, "cat vendor/etc/qt-service_config.xml")
        result2 = bool('DEFAULT_CONF' in str(data2))
        self.logger.info(
            "\n- 阶梯控频_CPU多阶调频_高通thermal通用配置 qt-service_config.xml ：\n" + "- " + "\n".join(data2) + "\n",
            ext_event=True)
        data = [data1, data2]
        self.log_result(result1 and result2)

    def case_therm_step_freq_cpu_camera_qcom(self):
        """阶梯控频_CPU多阶调频_高通thermal_客制化_相机"""
        data1 = adb.exec_cmd(self.device_id, "cat vendor/etc/thermal-engine.conf")
        result1 = bool('CAMERA_STEP_CPU' in str(data1))
        self.logger.info(
            "\n*** 阶梯控频_CPU多阶调频_高通thermal_客制化_相机 thermal-engine.conf ***\n" + "- " + "\n".join(data1) + "\n",
            ext_event=True)

        data2 = adb.exec_cmd(self.device_id, "cat vendor/etc/qt-service_config.xml")
        result2 = bool('CAMERA_CONF' in str(data2))
        self.logger.info(
            "\n- 阶梯控频_CPU多阶调频_高通thermal_客制化_相机 qt-service_config.xml ：\n" + "- " + "\n".join(data2) + "\n",
            ext_event=True)
        data = [data1, data2]
        self.log_result(result1 and result2)

    def case_therm_step_freq_cpu_video_qcom(self):
        """阶梯控频_CPU多阶调频_高通thermal_客制化_视频"""
        data1 = adb.exec_cmd(self.device_id, "cat vendor/etc/thermal-engine.conf")
        result1 = bool('VIDEO_STEP_CPU' in str(data1))
        self.logger.info(
            "\n*** 阶梯控频_CPU多阶调频_高通thermal_客制化_视频 thermal-engine.conf ***\n" + "- " + "\n".join(data1) + "\n",
            ext_event=True)

        data2 = adb.exec_cmd(self.device_id, "cat vendor/etc/qt-service_config.xml")
        result2 = bool('VIDEO_CONF' in str(data2))
        self.logger.info(
            "\n- 阶梯控频_CPU多阶调频_高通thermal_客制化_视频 qt-service_config.xml：\n" + "- " + "\n".join(
                data2) + "\n",
            ext_event=True)
        data = [data1, data2]
        self.log_result(result1 and result2)

    def case_therm_step_freq_cpu_video_call_qcom(self):
        """阶梯控频_CPU多阶调频_高通thermal_客制化_视频通话"""
        data1 = adb.exec_cmd(self.device_id, "cat vendor/etc/thermal-engine.conf")
        result1 = bool('VIDEOCALL_STEP_CPU' in str(data1))
        self.logger.info(
            "\n*** 阶梯控频_CPU多阶调频_高通thermal_客制化_视频通话 thermal-engine.conf ***\n" + "- " + "\n".join(data1) + "\n",
            ext_event=True)

        data2 = adb.exec_cmd(self.device_id, "cat vendor/etc/qt-service_config.xml")
        result2 = bool('VIDEOCALL_CONF' in str(data2))
        self.logger.info(
            "\n- 阶梯控频_CPU多阶调频_高通thermal_客制化_视频通话 qt-service_config.xml：\n" + "- " + "\n".join(data2) + "\n",
            ext_event=True)
        data = [data1, data2]
        self.log_result(result1 and result2)

    def case_therm_step_freq_cpu_game_qcom(self):
        """阶梯控频_CPU多阶调频_高通thermal_客制化_游戏"""
        data1 = adb.exec_cmd(self.device_id, "cat vendor/etc/thermal-engine.conf")
        result1 = bool('GAME_STEP_CPU' in str(data1))
        self.logger.info(
            "\n*** 阶梯控频_CPU多阶调频_高通thermal_客制化_游戏 thermal-engine.conf ***\n" + "- " + "\n".join(
                data1) + "\n",
            ext_event=True)

        data2 = adb.exec_cmd(self.device_id, "cat vendor/etc/qt-service_config.xml")
        result2 = bool('GAME_CONF' in str(data2))
        self.logger.info(
            "\n- 阶梯控频_CPU多阶调频_高通thermal_客制化_游戏 qt-service_config.xml：\n" + "- " + "\n".join(
                data2) + "\n",
            ext_event=True)
        data = [data1, data2]
        self.log_result(result1 and result2)

    def case_therm_step_freq_benchmark_score_qcom(self):
        """阶梯控频_CPU多阶调频_高通thermal_客制化_跑分"""
        data2 = adb.exec_cmd(self.device_id, "cat vendor/etc/qt-service_config.xml")
        result2 = bool('ANTUTU_CONF' in str(data2))
        self.logger.info(
            "\n*** 阶梯控频_CPU多阶调频_高通thermal_客制化_跑分 qt-service_config.xml ***\n" + "- " + "\n".join(
                data2) + "\n",
            ext_event=True)
        data = [data2]
        self.log_result(result2)

    def case_therm_core_iso_cpu_mtkthermal_cfg_qcom(self):
        """核心隔离_CPU核心隔离_高通thermal通用配置"""
        adb.exec_cmd(self.device_id, "touch /tmp/thermal-conf-verify.txt")
        adb.exec_cmd(self.device_id, "thermal-engine-v2 -o > /tmp/thermal-conf-verify.txt")
        adb.pull_file(self.device_id, "/tmp/thermal-conf-verify.txt", self.runtime_dir)
        data = adb.exec_cmd(self.device_id, "cat /tmp/thermal-conf-verify.txt")
        self.logger.info("\n*** 核心隔离_CPU核心隔离_高通thermal通用配置 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool('FAIL-SAFE-SKIN-MONITOR' in data))

    def case_therm_high_temp_backlight_disp_all_qcom(self):
        """高温背光_display_all"""
        self.u2d_helper.screen_on_and_unlock()
        time.sleep(10)
        data = adb.exec_cmd(self.device_id, "dumpsys activity thermal_backlight thermal_back_state")
        self.logger.info("\n*** 高温背光_display_all ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool('Enable = true' in str(data)))

    def case_therm_hbm_high_temp_ctrl_disp_outdoor_high_qcom(self):
        """HBM高温控制_display_户外高亮"""
        data = adb.exec_cmd(self.device_id, "getprop | grep -iE hbm.thermal")
        self.logger.info("\n*** HBM高温控制_display_户外高 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_screen_brightness_limit_disp_mtk_cfg_qcom(self):
        """屏幕亮度限制_display_高通thermal通用配置"""
        data = "暂不实现"
        self.logger.info("\n*** 屏幕亮度限制_display_高通thermal通用配置 ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_smart_temp_rise_dyn_limit_charging_qcom(self):
        """智能温升动态限流_充电_充电"""
        data = "暂不实现"
        self.logger.info("\n*** 智能温升动态限流_充电_充电 ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_three_level_charging_qcom(self):
        """三档充电"""
        data = "暂不实现"
        self.logger.info("\n*** 三档充电 ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_charging_temp_limit_charging_camera_qcom(self):
        """高通thermal充电限流_相机"""
        data = "暂不实现"
        self.logger.info("\n*** 高通thermal充电限流_相机 ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_charging_temp_limit_charging_video_qcom(self):
        """高通thermal充电限流_视频"""
        data = "暂不实现"
        self.logger.info("\n*** 高通thermal充电限流_视频 ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_charging_temp_limit_charging_video_call_qcom(self):
        """高通thermal充电限流_视频通话"""
        data = "暂不实现"
        self.logger.info("\n*** 高通thermal充电限流_视频通话 ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_charging_temp_limit_charging_game_qcom(self):
        """高通thermal充电限流_游戏"""
        data = "暂不实现"
        self.logger.info("\n*** 高通thermal充电限流_游戏 ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_game_thermal_ctrl_engine_1_0_game_qcom(self):
        """游戏温控引擎1.0_游戏_游戏"""
        data = adb.exec_cmd(self.device_id, "getprop | grep ro.tr_esports.thermal_config.feature.support")
        self.logger.info("\n*** 游戏温控引擎1.0_游戏_游戏 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool('[ro.tr_esports.thermal_config.feature.support]: [1]' in data))

    def case_therm_game_QFPS_game_qcom(self):
        """QFPS_游戏"""
        data = "暂不实现"
        self.logger.info("\n*** QFPS_游戏 ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_camera_high_temp_protection_sys_camera_qcom(self):
        """Camera高温保护策略_camera_系统相机"""
        data = "暂不实现"
        self.logger.info("\n*** Camera高温保护策略_camera_系统相机 ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_video_power_saving_mode_v1_0_sys_camera_qcom(self):
        """Video省电模式V1.0_camera_系统相机"""
        try:
            adb.stop_app(self.device_id, 'com.transsion.camera')
            time.sleep(1)
            adb.poweron_screen_and_unlock(self.device_id)
            time.sleep(2)
            adb.start_launcher_activity(self.device_id, 'com.transsion.camera')
            time.sleep(2)
            self.u2d_helper.click_wait('//*[@content-desc="Video" or @text="Video"]')
            time.sleep(1)
            five_min_before_bri = adb.exec_cmd(self.device_id, 'settings get system screen_brightness')
            self.u2d_helper.click_wait('//*[@content-desc="Shutter" or @resource-id="com.transsion.camera:id/shutter_button"]')
            time.sleep(5 * 60)
            five_min_after_bri = adb.exec_cmd(self.device_id, 'settings get system screen_brightness')
            first = "有" if five_min_before_bri > five_min_after_bri else "没有"
            self.click_screen_by_percentage(self.device_id, 50, 50)
            time.sleep(30)
            last_bri = adb.exec_cmd(self.device_id, 'settings get system screen_brightness')
            second = "有" if five_min_after_bri > last_bri else "没有"
            data = [five_min_before_bri, five_min_after_bri, last_bri]
            self.logger.info(f"\n- 5分钟前后以及30s最后的亮度分别为：{data}", ext_event=True)
            self.logger.info(
                "\n*** Video省电模式V1.0_camera_系统相机 ***\n" + "- 5分钟后确认屏幕" + first + "降低亮度" + "\n" + "- 30s后确认屏幕" + second + "降低亮度" + "\n",
                ext_event=True)
            self.u2d_helper.click_wait('//*[@content-desc="Shutter" or @resource-id="com.transsion.camera:id/shutter_button"]', post_wait=1)
            self.log_result(bool(first == "没有" and second == "没有"))
        finally:
            adb.stop_app(self.device_id, 'com.transsion.camera')

    def case_therm_image_smart_temp_ctrl_v1_0_sys_camera_qcom(self):
        """影像智能温控V1.0_camera_系统相机"""
        data1 = adb.exec_cmd(self.device_id, "getprop | grep vendor.debug.tran_cam_dynamic_fps")
        data2 = adb.exec_cmd(self.device_id, "getprop | grep vendor.debug.tran_camera_hq_mode")
        self.logger.info(
            "\n*** 影像智能温控V1.0_camera_系统相机 ***\n" + "- " + "getprop | grep vendor.debug.tran_cam_dynamic_fps \n" + "\n".join(
                data1) + "\n"
            + "- " + "getprop | grep vendor.debug.tran_camera_hq_mode \n" + "\n".join(data2) + "\n", ext_event=True)
        data = [data1, data2]
        self.log_result(bool(data == [[], []]) or bool(data == [[0], [1]]))

    def case_therm_smart_flash_ctrl_v1_0_sys_camera_qcom(self):
        """智能闪光灯控制V1.0_camera_系统相机"""
        data = "暂不实现"
        self.logger.info("\n*** 智能闪光灯控制V1.0_camera_系统相机 ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_video_chat_third_party_camera_qcom(self):
        """视频畅聊_camera_三方相机"""
        data = adb.exec_cmd(self.device_id, "dumpsys activity service com.transsion.usf.UsfMainService -dump_config -videocallsave")
        self.logger.info("\n*** 视频畅聊_camera_三方相机 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    # ----------------------- MTK平台 ------------------------------------
    def case_therm_generated_platform_thermal_mtk(self):
        """thermal zone,cooling device是否正常生成"""
        data = adb.exec_cmd(self.device_id,
                            "i=0; while [[ $i -lt 80 ]] ;do (type=`cat /sys/class/thermal/thermal_zone$i/type`;"
                            "temp=`cat /sys/class/thermal/thermal_zone$i/temp`; echo "'$i $type : $temp'"); i=$((i+1));done")
        ntc_temp_result = 'True'
        ntc_temp_list = []
        for item in data:
            if "ntc" in item:
                ntc_temp_list.append(item)
                parts = item.split(":")
                if len(parts) > 1:
                    ntc_temp = int(parts[1].strip())
                    if not 60000 > ntc_temp > 20000:
                        ntc_temp_result = 'False'
        self.logger.info("\n*** thermal zone,cooling device是否正常生成 ***\n" + "- " + "\n".join(ntc_temp_list) + "\n", ext_event=True)
        self.log_result(bool(ntc_temp_result and ntc_temp_list))

    def case_therm_read_ntc_temp_mtk(self):
        """NTC温度是否能否正常读取"""
        data = adb.exec_cmd(self.device_id,
                            "i=0; while [[ $i -lt 80 ]] ;do (type=`cat /sys/class/thermal/thermal_zone$i/type`;"
                            "temp=`cat /sys/class/thermal/thermal_zone$i/temp`; echo "'$i $type : $temp'"); i=$((i+1));done")
        ntc_temp_result, ntc_temp = 'True', 0
        ntc_temp_list = []
        for item in data:
            if "ntc" in item:
                ntc_temp_list.append(item)
                parts = item.split(":")
                if len(parts) > 1:
                    ntc_temp = int(parts[1].strip())
                    if not 60000 > ntc_temp > 20000:
                        ntc_temp_result = 'False'
        self.logger.info("\n thermal zone,cooling, device是否正常生成：\n" + "- " + "\n".join(ntc_temp_list) + "\n", ext_event=True)
        self.logger.info(f"\n*** NTC温度是否能否正常读取 ***\n {ntc_temp}", ext_event=True)
        self.log_result(bool(ntc_temp_result and ntc_temp_list))

    def case_therm_working_thermal_framework_mtk(self):
        """Thermal框架工作是否正常"""
        data = adb.exec_cmd(self.device_id, 'ps -A | grep thermal_core')
        self.logger.info("\n*** Thermal框架工作是否正常 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool('thermal_core' in str(data)))

    def case_therm_customize_starup_thermal_policy_mtk(self):
        """开机定制thermal policy"""
        data = adb.exec_cmd(self.device_id, 'ls -la vendor/etc/.tp')
        self.logger.info("\n*** 开机定制thermal policy ***\n" + "- " + str(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_kswapd_bind_small_cpu_all_mtk(self):
        """Kswapd绑小核_CPU_all"""
        lines = adb.exec_cmd(self.device_id, "top -b -n 1 | grep 'kswapd0'")
        pattern = re.compile(r'^\s*(\d+)\s.*\[kswapd0\]')
        pid = ''
        for line in lines:
            match = pattern.search(line)
            if match:
                pid = match.group(1)
        data = adb.exec_cmd(self.device_id, "taskset -p " + pid)[0].split(' ')[-1]
        data = bin(int(data, 16))[2:].zfill(8)
        self.logger.info("\n*** Kswapd绑小核_CPU_all ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(bool('1' in data[-2:]))

    def case_therm_short_video_bind_cpu_feat_mtk(self):
        """短视频绑核方案_CPU_feature"""
        data = adb.exec_cmd(self.device_id, 'cat /dev/cpuset/top-app/cpus')[0]
        if '4-6' in data:
            result = '正常'
        else:
            result = '高温'
        self.logger.info("\n*** 短视频绑核方案_CPU_feature ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(result)

    def case_therm_high_temperature_transient_mtk(self):
        """高温瞬态检测"""
        result = 'False'
        android_version = int(adb.device_android_version(self.device_id))

        if android_version >= 16:
            # Android 版本 >= 16 时的逻辑
            data = adb.exec_cmd(self.device_id, "dumpsys activity service com.transsion.usf.UsfMainService -thermal thermal_engine config | grep 'ThermalUx'")
            print(data)
            if data and 'null' not in str(data):  # 检查返回数据是否有效
                result = 'True'
        else:
            commands = [
                'getprop ro.vendor.powerhal.thermal_ux_support',
                'getprop persist.vendor.powerhal.thermal_ux_temp_max',
                'getprop persist.vendor.powerhal.thermal_ux_temp_min'
            ]
            data = [adb.exec_cmd(self.device_id, cmd) for cmd in commands]
            if all(data):
                result = 'True'

        self.logger.info(f"\n*** 高温瞬态 ***\n- {str(data)}\n", ext_event=True)
        self.log_result(result)

    def case_therm_dyn_freq_cpu_mtkthermal_cfg_mtk(self):
        """动态调频_CPU动态调频_MTKthermal通用配置"""
        data = self.find_mtk_feature("", "")
        self.logger.info("\n*** 动态调频_CPU动态调频_MTKthermal通用配置 thermal.conf ***\n" + "- " + str(data) + "\n", ext_event=True)
        data = adb.exec_cmd(self.device_id, 'cat /data/vendor/thermal/.current_tp')[0]
        self.logger.info("\n- 动态调频_CPU动态调频_MTKthermal通用配置 当前：\n" + "- " + data + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_dyn_freq_cpu_policy01_camera_60fps_mtk(self):
        """动态调频_CPU动态调频_Policy01-Camera场景（60fps）"""
        data = self.find_mtk_skin_control("01")
        self.logger.info(
            "\n*** 动态调频_CPU动态调频_Policy01-Camera场景（60fps） ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_dyn_freq_cpu_policy02_camera_mtk(self):
        """动态调频_CPU动态调频_Policy02-Camera场景"""
        data = self.find_mtk_skin_control("02")
        self.logger.info("\n*** 动态调频_CPU动态调频_Policy02-Camera场景 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_dyn_freq_cpu_policy03_benchmark_mtk(self):
        """动态调频_CPU动态调频_Policy03-跑分"""
        data = self.find_mtk_skin_control("03")
        self.logger.info("\n*** 动态调频_CPU动态调频_Policy03-跑分 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_dyn_freq_cpu_policy04_video_conf_call_mtk(self):
        """动态调频_CPU动态调频_Policy04-视频会议/通话"""
        data = self.find_mtk_skin_control("04")
        self.logger.info("\n*** 动态调频_CPU动态调频_Policy04-视频会议/通话 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_dyn_freq_cpu_policy05_browser_mtk(self):
        """动态调频_CPU动态调频_Policy05-浏览器"""
        data = self.find_mtk_skin_control("05")
        self.logger.info("\n*** 动态调频_CPU动态调频_Policy05-浏览器 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_dyn_freq_cpu_policy06_game_mtk(self):
        """动态调频_CPU动态调频_Policy06-游戏"""
        data = self.find_mtk_skin_control("06")
        self.logger.info("\n*** 动态调频_CPU动态调频_Policy06-游戏 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_dyn_freq_cpu_policy07_game_a_mtk(self):
        """动态调频_CPU动态调频_Policy07-游戏A"""
        data = self.find_mtk_skin_control("07")
        self.logger.info("\n*** 动态调频_CPU动态调频_Policy07-游戏A ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_dyn_freq_cpu_policy09_game_b_mtk(self):
        """动态调频_CPU动态调频_Policy09-游戏B"""
        data = self.find_mtk_skin_control("09")
        self.logger.info("\n*** 动态调频_CPU动态调频_Policy09-游戏B ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_dyn_freq_cpu_policy10_social_app_mtk(self):
        """动态调频_CPU动态调频_Policy10-社交应用"""
        data = self.find_mtk_skin_control("10")
        self.logger.info("\n*** 动态调频_CPU动态调频_Policy10-社交应用 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_dyn_freq_cpu_policy11_video_play_mtk(self):
        """动态调频_CPU动态调频_Policy11-视频播放"""
        data = self.find_mtk_skin_control("11")
        self.logger.info("\n*** 动态调频_CPU动态调频_Policy11-视频播放 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_dyn_freq_cpu_policy12_map_nav_mtk(self):
        """动态调频_CPU动态调频_Policy12-地图导航"""
        data = self.find_mtk_skin_control("12")
        self.logger.info("\n*** 动态调频_CPU动态调频_Policy12-地图导航 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_dyn_freq_cpu_policy13_game_c_genshin_mtk(self):
        """动态调频_CPU动态调频_Policy13-游戏C（原神等）"""
        data = self.find_mtk_skin_control("13")
        self.logger.info("\n*** 动态调频_CPU动态调频_Policy13-游戏C（原神等） ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_dyn_freq_cpu_policy14_one_key_migrate_mtk(self):
        """动态调频_CPU动态调频_Policy14-一键换机"""
        data = self.find_mtk_skin_control("14")
        self.logger.info("\n*** 动态调频_CPU动态调频_Policy14-一键换机 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_dyn_freq_cpu_policy15_game_d_football_mtk(self):
        """动态调频_CPU动态调频_Policy15-游戏D（足球）"""
        data = self.find_mtk_skin_control("15")
        self.logger.info("\n*** 动态调频_CPU动态调频_Policy15-游戏D（足球） ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_step_freq_cpu_mtkthermal_cfg_mtk(self):
        """阶梯控频_CPU多阶调频_MTKthermal通用配置"""
        data = self.find_mtk_cpu_table_mapping("")
        self.logger.info("\n*** 阶梯控频_CPU多阶调频_MTKthermal通用配置 ***\n" + "- " + str(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_step_freq_cpu_policy01_camera_60fps_mtk(self):
        """阶梯控频_CPU多阶调频_Policy01-Camera场景（60fps）"""
        data = self.find_mtk_cpu_table_mapping("01")
        self.logger.info("\n*** 阶梯控频_CPU多阶调频_Policy01-Camera场景（60fps） ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_step_freq_cpu_policy02_camera_mtk(self):
        """阶梯控频_CPU多阶调频_Policy02-Camera场景"""
        data = self.find_mtk_cpu_table_mapping("02")
        self.logger.info("\n*** 阶梯控频_CPU多阶调频_Policy02-Camera场景 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_step_freq_cpu_policy03_benchmark_mtk(self):
        """阶梯控频_CPU多阶调频_Policy03-跑分"""
        data = self.find_mtk_cpu_table_mapping("03")
        self.logger.info("\n*** 阶梯控频_CPU多阶调频_Policy03-跑分 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_step_freq_cpu_policy04_video_conf_call_mtk(self):
        """阶梯控频_CPU多阶调频_Policy04-视频会议/通话"""
        data = self.find_mtk_cpu_table_mapping("04")
        self.logger.info("\n*** 阶梯控频_CPU多阶调频_Policy04-视频会议/通话 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_step_freq_cpu_policy05_browser_mtk(self):
        """阶梯控频_CPU多阶调频_Policy05-浏览器"""
        data = self.find_mtk_cpu_table_mapping("05")
        self.logger.info("\n*** 阶梯控频_CPU多阶调频_Policy05-浏览器 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_step_freq_cpu_policy06_game_mtk(self):
        """阶梯控频_CPU多阶调频_Policy06-游戏"""
        data = self.find_mtk_cpu_table_mapping("06")
        self.logger.info("\n*** 阶梯控频_CPU多阶调频_Policy06-游戏 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_step_freq_cpu_policy07_game_a_mtk(self):
        """阶梯控频_CPU多阶调频_Policy07-游戏A"""
        data = self.find_mtk_cpu_table_mapping("07")
        self.logger.info("\n*** 阶梯控频_CPU多阶调频_Policy07-游戏A ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_step_freq_cpu_policy09_game_b_mtk(self):
        """阶梯控频_CPU多阶调频_Policy09-游戏B"""
        data = self.find_mtk_cpu_table_mapping("09")
        self.logger.info("\n*** 阶梯控频_CPU多阶调频_Policy09-游戏B ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_step_freq_cpu_policy10_social_app_mtk(self):
        """阶梯控频_CPU多阶调频_Policy10-社交应用"""
        data = self.find_mtk_cpu_table_mapping("10")
        self.logger.info("\n*** 阶梯控频_CPU多阶调频_Policy10-社交应用 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_step_freq_cpu_policy11_video_play_mtk(self):
        """阶梯控频_CPU多阶调频_Policy11-视频播放"""
        data = self.find_mtk_cpu_table_mapping("11")
        self.logger.info("\n*** 阶梯控频_CPU多阶调频_Policy11-视频播放 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_step_freq_cpu_policy12_map_nav_mtk(self):
        """阶梯控频_CPU多阶调频_Policy12-地图导航"""
        data = self.find_mtk_cpu_table_mapping("12")
        self.logger.info("\n*** 阶梯控频_CPU多阶调频_Policy12-地图导航 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_step_freq_cpu_policy13_game_c_genshin_mtk(self):
        """阶梯控频_CPU多阶调频_Policy13-游戏C（原神等）"""
        data = self.find_mtk_cpu_table_mapping("13")
        self.logger.info("\n*** 阶梯控频_CPU多阶调频_Policy13-游戏C（原神等） ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_step_freq_cpu_policy14_one_key_migrate_mtk(self):
        """阶梯控频_CPU多阶调频_Policy14-一键换机"""
        data = self.find_mtk_cpu_table_mapping("14")
        self.logger.info("\n*** 阶梯控频_CPU多阶调频_Policy14-一键换机 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_step_freq_cpu_policy15_game_d_football_mtk(self):
        """阶梯控频_CPU多阶调频_Policy15-游戏D（足球）"""
        data = self.find_mtk_cpu_table_mapping("15")
        self.logger.info("\n*** 阶梯控频_CPU多阶调频_Policy15-游戏D（足球） ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_core_iso_cpu_mtkthermal_cfg_mtk(self):
        """核心隔离_CPU核心隔离_MTKthermal通用配置"""
        data = self.find_mtk_cpu_isolate("")
        self.logger.info("\n*** 核心隔离_CPU核心隔离_MTKthermal通用配置 ***\n" + "- " + str(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_core_iso_cpu_policy01_camera_60fps_mtk(self):
        """核心隔离_CPU核心隔离_Policy01-Camera场景（60fps）"""
        data = self.find_mtk_cpu_isolate("01")
        self.logger.info("\n*** 核心隔离_CPU核心隔离_Policy01-Camera场景（60fps） ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_core_iso_cpu_policy02_camera_mtk(self):
        """核心隔离_CPU核心隔离_Policy02-Camera场景"""
        data = self.find_mtk_cpu_isolate("02")
        self.logger.info("\n*** 核心隔离_CPU核心隔离_Policy02-Camera场景 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_core_iso_cpu_policy03_benchmark_mtk(self):
        """核心隔离_CPU核心隔离_Policy03-跑分"""
        data = self.find_mtk_cpu_isolate("03")
        self.logger.info("\n*** 核心隔离_CPU核心隔离_Policy03-跑分 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_core_iso_cpu_policy04_video_conf_call_mtk(self):
        """核心隔离_CPU核心隔离_Policy04-视频会议/通话"""
        data = self.find_mtk_cpu_isolate("04")
        self.logger.info("\n*** 核心隔离_CPU核心隔离_Policy04-视频会议/通话 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_core_iso_cpu_policy05_browser_mtk(self):
        """核心隔离_CPU核心隔离_Policy05-浏览器"""
        data = self.find_mtk_cpu_isolate("05")
        self.logger.info("\n*** 核心隔离_CPU核心隔离_Policy05-浏览器 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_core_iso_cpu_policy06_game_mtk(self):
        """核心隔离_CPU核心隔离_Policy06-游戏"""
        data = self.find_mtk_cpu_isolate("06")
        self.logger.info("\n*** 核心隔离_CPU核心隔离_Policy06-游戏 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_core_iso_cpu_policy07_game_a_mtk(self):
        """核心隔离_CPU核心隔离_Policy07-游戏A"""
        data = self.find_mtk_cpu_isolate("07")
        self.logger.info("\n*** 核心隔离_CPU核心隔离_Policy07-游戏A ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_core_iso_cpu_policy09_game_b_mtk(self):
        """核心隔离_CPU核心隔离_Policy09-游戏B"""
        data = self.find_mtk_cpu_isolate("09")
        self.logger.info("\n*** 核心隔离_CPU核心隔离_Policy09-游戏B ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_core_iso_cpu_policy10_social_app_mtk(self):
        """核心隔离_CPU核心隔离_Policy10-社交应用"""
        data = self.find_mtk_cpu_isolate("10")
        self.logger.info("\n*** 核心隔离_CPU核心隔离_Policy10-社交应用 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_core_iso_cpu_policy11_video_play_mtk(self):
        """核心隔离_CPU核心隔离_Policy11-视频播放"""
        data = self.find_mtk_cpu_isolate("11")
        self.logger.info("\n*** 核心隔离_CPU核心隔离_Policy11-视频播放 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_core_iso_cpu_policy12_map_nav_mtk(self):
        """核心隔离_CPU核心隔离_Policy12-地图导航"""
        data = self.find_mtk_cpu_isolate("12")
        self.logger.info("\n*** 核心隔离_CPU核心隔离_Policy12-地图导航 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_core_iso_cpu_policy13_game_c_genshin_mtk(self):
        """核心隔离_CPU核心隔离_Policy13-游戏C（原神等）"""
        data = self.find_mtk_cpu_isolate("13")
        self.logger.info("\n*** 核心隔离_CPU核心隔离_Policy13-游戏C（原神等） ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_core_iso_cpu_policy14_one_key_migrate_mtk(self):
        """核心隔离_CPU核心隔离_Policy14-一键换机"""
        data = self.find_mtk_cpu_isolate("14")
        self.logger.info("\n*** 核心隔离_CPU核心隔离_Policy14-一键换机 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_core_iso_cpu_policy15_game_d_football_mtk(self):
        """核心隔离_CPU核心隔离_Policy15-游戏D（足球）"""
        data = self.find_mtk_cpu_isolate("15")
        self.logger.info("\n*** 核心隔离_CPU核心隔离_Policy15-游戏D（足球） ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_high_temp_backlight_disp_all_mtk(self):
        """高温背光_display_all"""
        self.u2d_helper.screen_on_and_unlock()
        time.sleep(10)
        data = adb.exec_cmd(self.device_id, "dumpsys activity thermal_backlight thermal_back_state")
        self.logger.info("\n*** 高温背光_display_all ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool('Enable = true' in data))

    def case_therm_hbm_high_temp_ctrl_disp_outdoor_high_mtk(self):
        """HBM高温控制_display_户外高亮"""
        data = adb.exec_cmd(self.device_id, "getprop | grep -iE hbm.thermal")
        self.logger.info("\n*** HBM高温控制_display_户外高亮 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_smart_temp_rise_dyn_limit_charging_mtk(self):
        """智能温升动态限流_充电_充电"""
        adb.adb_root(self.device_id)
        adb.exec_cmd(self.device_id, "echo [1] > /sys/devices/platform/pe5/pe50_debug")
        data = adb.exec_cmd(self.device_id, "dmesg | grep dump_pe50_thermal_para")
        self.logger.info("\n*** 智能温升动态限流_充电_充电 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_three_level_charging_mtk(self):
        """三档充电"""
        # 设置电池温度
        adb.exec_cmd(self.device_id, "echo [123,38,39,41,41,41,41,41,41,41,41,41,41,1000,1500,3001,3001,3001,3001,3001,3001,3001]"
                                     " >  /sys/devices/platform/pe5/pe50_debug")
        # 设置PCB温度
        adb.exec_cmd(self.device_id, "echo [124,38,39,41,41,41,41,41,41,41,41,41,41,1000,1500,3001,3001,3001,3001,3001,3001,3001]"
                                     " >  /sys/devices/platform/pe5/pe50_debug")
        # data = adb.exec_cmd(self.device_id, 'dmesg | grep dump_pe50_thermal_para')
        data = adb.exec_cmd(self.device_id, 'cat /sys/devices/platform/pe5/pe50_debug')
        self.logger.info("\n*** 三档充电 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_wifi_high_temp_speed_limit_wifi_all_mtk(self):
        """WiFi高温限速_wifi_all"""
        data = "暂不实现"
        self.logger.info("\n*** WiFi高温限速_wifi_all ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_step_limit_modem_behavior_modem_all_mtk(self):
        """阶梯限制modem的行为_Modem_all"""
        data = "暂不实现"
        self.logger.info("\n*** 阶梯限制modem的行为_Modem_all ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_game_thermal_ctrl_engine_1_0_game_mtk(self):
        """游戏温控引擎1.0_游戏_游戏"""
        # getprop ro.esports.thermal_config.support 直接获取值方便？
        data = adb.exec_cmd(self.device_id,
                            "getprop | grep ro.esports.thermal_config.support")
        self.logger.info("\n*** 游戏温控引擎1.0_游戏_游戏 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool('[ro.esports.thermal_config.support]: [1]' in data))

    def case_therm_drt_game_whitelist_game_mtk(self):
        """DRT_游戏_白名单游戏"""
        data1 = adb.exec_cmd(self.device_id, "getprop | grep ro.vendor.app_resolution_tuner")  # 1
        result1 = bool('[ro.vendor.app_resolution_tuner]: [1]' in data1)
        data2 = adb.exec_cmd(self.device_id, "getprop | grep ro.vendor.tgpa_resolution_tuner")  # 1
        result2 = bool('[ro.vendor.tgpa_resolution_tuner]: [1]' in data2)
        data = [data1, data2]
        self.logger.info(
            "\n*** DRT_游戏_白名单游戏 ***\n" + "- " + "getprop | grep ro.vendor.app_resolution_tuner \n" + "\n".join(
                data1) + "\n"
            + "- " + "getprop | grep ro.vendor.tgpa_resolution_tuner \n" + "\n".join(data2) + "\n", ext_event=True)
        self.log_result(bool(result1 and result2))

    def case_therm_frs_stable_frame_game_mtk(self):
        """FRS稳帧_游戏_游戏"""
        data = "暂不实现"
        self.logger.info("\n*** FRS稳帧_游戏_游戏 ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_camera_high_temp_protection_sys_camera_mtk(self):
        """Camera高温保护策略_camera_系统相机"""
        data = "暂不实现"
        self.logger.info("\n*** Camera高温保护策略_camera_系统相机 ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_video_power_saving_mode_v1_0_sys_camera_mtk(self):
        """Video省电模式V1.0_camera_系统相机"""
        try:
            adb.stop_app(self.device_id, 'com.transsion.camera')
            time.sleep(1)
            adb.poweron_screen_and_unlock(self.device_id)
            time.sleep(2)
            adb.start_launcher_activity(self.device_id, 'com.transsion.camera')
            time.sleep(2)
            self.u2d_helper.click_wait('//*[@content-desc="Video" or @text="Video"]')
            time.sleep(1)
            five_min_before_bri = adb.get_screen_brightness(self.device_id)
            self.u2d_helper.click_wait('//*[@content-desc="Shutter" or @resource-id="com.transsion.camera:id/shutter_button"]')
            time.sleep(5 * 60)
            five_min_after_bri = adb.get_screen_brightness(self.device_id)
            first = "有" if five_min_before_bri > five_min_after_bri else "没有"
            self.click_screen_by_percentage(self.device_id, 50, 50)
            time.sleep(30)
            last_bri = adb.get_screen_brightness(self.device_id)
            second = "有" if five_min_after_bri > last_bri else "没有"
            data = [five_min_before_bri, five_min_after_bri, last_bri]
            self.logger.info(f"\n- 5分钟前后以及30s最后的亮度分别为：{data}", ext_event=True)
            self.logger.info(
                "\n*** Video省电模式V1.0_camera_系统相机 ***\n" + "- 5分钟后确认屏幕" + first + "降低亮度" + "\n" + "- 30s后确认屏幕" + second + "降低亮度" + "\n",
                ext_event=True)
            self.u2d_helper.click_wait('//*[@content-desc="Shutter" or @resource-id="com.transsion.camera:id/shutter_button"]', post_wait=1)
            self.log_result(bool(first == "没有" and second == "没有"))
        finally:
            adb.stop_app(self.device_id, 'com.transsion.camera')

    def case_therm_image_smart_temp_ctrl_v1_0_sys_camera_mtk(self):
        """影像智能温控V1.0_camera_系统相机"""
        data1 = adb.exec_cmd(self.device_id, "getprop | grep vendor.debug.tran_cam_dynamic_fps")
        data2 = adb.exec_cmd(self.device_id, "getprop | grep vendor.debug.tran_camera_hq_mode")
        self.logger.info(
            "\n*** 影像智能温控V1.0_camera_系统相机 ***\n" + "- " + "getprop | grep vendor.debug.tran_cam_dynamic_fps \n" + "\n".join(
                data1) + "\n"
            + "- " + "getprop | grep vendor.debug.tran_camera_hq_mode \n" + "\n".join(data2) + "\n", ext_event=True)
        data = [data1, data2]
        self.log_result(bool(data == [[], []]) or bool(data == [[0], [1]]))

    def case_therm_smart_flash_ctrl_v1_0_sys_camera_mtk(self):
        """智能闪光灯控制V1.0_camera_系统相机"""
        data = "暂不实现"
        self.logger.info("\n*** 智能闪光灯控制V1.0_camera_系统相机 ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_video_chat_third_party_camera_mtk(self):
        """视频畅聊_camera_三方相机"""
        data = "暂不实现"
        self.logger.info("\n*** 视频畅聊_camera_三方相机 ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)

    # -------------------------------- mtk --------------------------------------

    # -------------------------------- sqrt -------------------------------------
    def case_therm_generated_platform_thermal_sqrt(self):
        """thermal zone,cooling device是否正常生成"""
        data = adb.exec_cmd(self.device_id,
                            "i=0; while [[ $i -lt 80 ]] ;do (type=`cat /sys/class/thermal/thermal_zone$i/type`;"
                            "temp=`cat /sys/class/thermal/thermal_zone$i/temp`; echo "'$i $type : $temp'"); i=$((i+1));done")
        ntc_temp_result = 'True'
        ntc_temp_list = []
        for item in data:
            if "ntc" in item:
                ntc_temp_list.append(item)
                parts = item.split(":")
                if len(parts) > 1:
                    ntc_temp = int(parts[1].strip())
                    if not 60000 > ntc_temp > 20000:
                        ntc_temp_result = 'False'
        self.logger.info("\n*** thermal zone,cooling device是否正常生成 ***\n" + "- " + "\n".join(ntc_temp_list) + "\n",
                         ext_event=True)
        self.log_result(bool(ntc_temp_result and ntc_temp_list))

    def case_therm_read_ntc_temp_sqrt(self):
        """NTC温度是否能否正常读取"""
        data = adb.exec_cmd(self.device_id,
                            "i=0; while [[ $i -lt 80 ]] ;do (type=`cat /sys/class/thermal/thermal_zone$i/type`;"
                            "temp=`cat /sys/class/thermal/thermal_zone$i/temp`; echo "'$i $type : $temp'"); i=$((i+1));done")
        ntc_temp_result, ntc_temp = 'True', 0
        ntc_temp_list = []
        for item in data:
            if "ntc" in item:
                ntc_temp_list.append(item)
                parts = item.split(":")
                if len(parts) > 1:
                    ntc_temp = int(parts[1].strip())
                    if not 60000 > ntc_temp > 20000:
                        ntc_temp_result = 'False'
        self.logger.info("\n- thermal zone,cooling, device是否正常生成：\n" + "- " + "\n".join(ntc_temp_list) + "\n", ext_event=True)
        self.logger.info(f"\n*** NTC温度是否能否正常读取 ***\n {ntc_temp}", ext_event=True)
        self.log_result(bool(ntc_temp_result and ntc_temp_list))

    def case_therm_working_thermal_framework_sqrt(self):
        """Thermal框架工作是否正常"""
        data = adb.exec_cmd(self.device_id, 'ps -A | grep thermal_core')
        self.logger.info("\n*** Thermal框架工作是否正常 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool('thermal_core' in str(data)))

    def case_therm_kswapd_bind_small_cpu_all_sqrt(self):
        """Kswapd绑小核_CPU_all"""
        lines = adb.exec_cmd(self.device_id, "top -b -n 1 | grep 'kswapd0'")
        pattern = re.compile(r'^\s*(\d+)\s.*\[kswapd0\]')
        pid = ''
        for line in lines:
            match = pattern.search(line)
            if match:
                pid = match.group(1)
                print(pid)
        data = adb.exec_cmd(self.device_id, "taskset -p " + pid)[0].split(' ')[-1]
        data = bin(int(data, 16))[2:].zfill(8)
        self.logger.info("\n*** Kswapd绑小核_CPU_all ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(bool('1' in data[-2:]))

    def case_therm_short_video_bind_cpu_feat_sqrt(self):
        """短视频绑核方案_CPU_feature"""
        data = adb.exec_cmd(self.device_id, 'cat /dev/cpuset/top-app/cpus')[0]
        if '4-6' in data:
            result = '正常'
        else:
            result = '高温'
        self.logger.info("\n*** 短视频绑核方案_CPU_feature ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(result)

    def case_therm_step_freq_cpu_qthermal_cfg_sqrt(self):
        """阶梯控频_CPU多阶调频_展锐thermal通用配置"""
        data = self.find_sqrt_feature()
        self.logger.info(
            "\n*** 阶梯控频_CPU多阶调频_展锐thermal通用配置 thermal.conf ***\n" + "- " + str(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_step_freq_cpu_camera_sqrt(self):
        """阶梯控频_CPU多阶调频_展锐thermal_场景识别_相机"""
        data = self.find_sqrt_feature()
        self.logger.info("\n*** 阶梯控频_CPU多阶调频_展锐thermal_场景识别_相机 ***\n" + "- " + str(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_step_freq_cpu_video_sqrt(self):
        """阶梯控频_CPU多阶调频_展锐thermal_场景识别_视频"""
        data = self.find_sqrt_feature()
        self.logger.info("\n*** 阶梯控频_CPU多阶调频_展锐thermal_场景识别_视频 ***\n" + "- " + str(data) + "\n",
                         ext_event=True)
        self.log_result(bool(data))

    def case_therm_step_freq_cpu_video_call_sqrt(self):
        """阶梯控频_CPU多阶调频_展锐thermal_场景识别_视频通话"""
        data = self.find_sqrt_feature()
        self.logger.info("\n*** 阶梯控频_CPU多阶调频_展锐thermal_场景识别_视频通话 ***\n" + "- " + str(data) + "\n",
                         ext_event=True)
        self.log_result(bool(data))

    def case_therm_step_freq_cpu_game_sqrt(self):
        """阶梯控频_CPU多阶调频_展锐thermal_场景识别_游戏"""
        data = self.find_sqrt_feature()
        self.logger.info("\n*** 阶梯控频_CPU多阶调频_展锐thermal_场景识别_游戏 ***\n" + "- " + str(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_core_iso_cpu_thermal_cfg_sqrt(self):
        """核心隔离_CPU核心隔离_thermal通用配置"""
        data = self.find_sqrt_feature()
        self.logger.info("\n*** 核心隔离_CPU核心隔离_thermal通用配置 ***\n" + "- " + str(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_high_temp_backlight_disp_all_sqrt(self):
        """高温背光_display_all"""
        self.u2d_helper.screen_on_and_unlock()
        time.sleep(10)
        data = adb.exec_cmd(self.device_id, "dumpsys activity thermal_backlight thermal_back_state")
        self.logger.info("\n*** 高温背光_display_all ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool('Enable = true' in data))

    def case_therm_hbm_high_temp_ctrl_disp_outdoor_high_sqrt(self):
        """HBM高温控制_display_户外高亮"""
        data = adb.exec_cmd(self.device_id, "getprop | grep -iE hbm.thermal")
        self.logger.info("\n*** HBM高温控制_display_户外高亮 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool(data))

    def case_therm_screen_brightness_limit_disp_sqrt_cfg_sqrt(self):
        """屏幕亮度限制_display_展锐thermal通用配置"""
        data = "暂不实现"
        self.logger.info("\n*** 屏幕亮度限制_display_MTKthermal通用配置 ***\n" + "- " + str(data) + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_smart_temp_rise_dyn_limit_charging_sqrt(self):
        """智能温升动态限流_充电_充电"""
        data = "暂不实现"
        self.logger.info("\n*** 智能温升动态限流_充电_充电 ***\n" + "- " + str(data) + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_three_level_charging_sqrt(self):
        """三档充电"""
        data = "暂不实现"
        self.logger.info("\n*** 三档充电 ***\n" + "- " + str(data) + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_charging_temp_limit_charging_camera_sqrt(self):
        """展锐thermal充电限流_相机"""
        data = "暂不实现"
        self.logger.info("\n*** 展锐thermal充电限流_相机 ***\n" + "- " + str(data) + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_charging_temp_limit_charging_video_sqrt(self):
        """展锐thermal充电限流_视频"""
        data = "暂不实现"
        self.logger.info("\n*** 展锐thermal充电限流_视频 ***\n" + "- " + str(data) + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_charging_temp_limit_charging_video_call_sqrt(self):
        """展锐thermal充电限流_视频通话"""
        data = "暂不实现"
        self.logger.info("\n*** 展锐thermal充电限流_视频通话 ***\n" + "- " + str(data) + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_charging_temp_limit_charging_game_sqrt(self):
        """展锐thermal充电限流_游戏"""
        data = "暂不实现"
        self.logger.info("\n*** 展锐thermal充电限流_游戏 ***\n" + "- " + str(data) + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_wifi_high_temp_speed_limit_wifi_all_sqrt(self):
        """WiFi高温限速_wifi_all"""
        data = "暂不实现"
        self.logger.info("\n*** WiFi高温限速_wifi_all ***\n" + "- " + str(data) + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_game_thermal_ctrl_engine_1_0_game_sqrt(self):
        """游戏温控引擎1.0_游戏_游戏"""
        # getprop ro.esports.thermal_config.support 直接获取值方便？
        data = adb.exec_cmd(self.device_id,
                            "getprop | grep ro.esports.thermal_config.support")
        self.logger.info("\n*** 游戏温控引擎1.0_游戏_游戏 ***\n" + "- " + "\n".join(data) + "\n", ext_event=True)
        self.log_result(bool('[ro.esports.thermal_config.support]: [1]' in data))

    def case_therm_drt_game_whitelist_game_sqrt(self):
        """DRT_游戏_白名单游戏"""
        data1 = adb.exec_cmd(self.device_id, "getprop | grep ro.vendor.app_resolution_tuner")  # 1
        result1 = bool('[ro.vendor.app_resolution_tuner]: [1]' in data1)
        data2 = adb.exec_cmd(self.device_id, "getprop | grep ro.vendor.tgpa_resolution_tuner")  # 1
        result2 = bool('[ro.vendor.tgpa_resolution_tuner]: [1]' in data2)
        data = [data1, data2]
        self.logger.info(
            "\n*** DRT_游戏_白名单游戏 ***\n" + "- " + "getprop | grep ro.vendor.app_resolution_tuner \n" + "\n".join(
                data1) + "\n"
            + "- " + "getprop | grep ro.vendor.tgpa_resolution_tuner \n" + "\n".join(data2) + "\n", ext_event=True)
        self.log_result(bool(result1 and result2))

    def case_therm_frs_stable_frame_game_sqrt(self):
        """FRS稳帧_游戏_游戏"""
        data = "暂不实现"
        self.logger.info("\n*** FRS稳帧_游戏_游戏 ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_camera_high_temp_protection_sys_camera_sqrt(self):
        """Camera高温保护策略_camera_系统相机"""
        data = "暂不实现"
        self.logger.info("\n*** Camera高温保护策略_camera_系统相机 ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_video_power_saving_mode_v1_0_sys_camera_sqrt(self):
        """Video省电模式V1.0_camera_系统相机"""
        try:
            adb.stop_app(self.device_id, 'com.transsion.camera')
            time.sleep(1)
            adb.poweron_screen_and_unlock(self.device_id)
            time.sleep(2)
            adb.start_launcher_activity(self.device_id, 'com.transsion.camera')
            time.sleep(2)
            self.u2d_helper.click_wait('//*[@content-desc="Video" or @text="Video"]')
            time.sleep(1)
            five_min_before_bri = adb.exec_cmd(self.device_id, 'settings get system screen_brightness')
            self.u2d_helper.click_wait('//*[@content-desc="Shutter" or @resource-id="com.transsion.camera:id/shutter_button"]')
            time.sleep(5 * 60)
            five_min_after_bri = adb.exec_cmd(self.device_id, 'settings get system screen_brightness')
            first = "有" if five_min_before_bri > five_min_after_bri else "没有"
            self.click_screen_by_percentage(self.device_id, 50, 50)
            time.sleep(30)
            last_bri = adb.exec_cmd(self.device_id, 'settings get system screen_brightness')
            second = "有" if five_min_after_bri > last_bri else "没有"
            data = [five_min_before_bri, five_min_after_bri, last_bri]
            self.logger.info(f"\n- 5分钟前后以及30s最后的亮度分别为：{data}", ext_event=True)
            self.logger.info(
                "\n*** Video省电模式V1.0_camera_系统相机 ***\n" + "- 5分钟后确认屏幕" + first + "降低亮度" + "\n" + "- 30s后确认屏幕" + second + "降低亮度" + "\n",
                ext_event=True)
            self.u2d_helper.click_wait('//*[@content-desc="Shutter" or @resource-id="com.transsion.camera:id/shutter_button"]', post_wait=1)
            self.log_result(bool(first == "没有" and second == "没有"))
        finally:
            adb.stop_app(self.device_id, 'com.transsion.camera')

    def case_therm_image_smart_temp_ctrl_v1_0_sys_camera_sqrt(self):
        """影像智能温控V1.0_camera_系统相机"""
        data1 = adb.exec_cmd(self.device_id, "getprop | grep vendor.debug.tran_cam_dynamic_fps")
        data2 = adb.exec_cmd(self.device_id, "getprop | grep vendor.debug.tran_camera_hq_mode")
        self.logger.info(
            "\n*** 影像智能温控V1.0_camera_系统相机 ***\n" + "- " + "getprop | grep vendor.debug.tran_cam_dynamic_fps \n" + "\n".join(
                data1) + "\n"
            + "- " + "getprop | grep vendor.debug.tran_camera_hq_mode \n" + "\n".join(data2) + "\n", ext_event=True)
        data = [data1, data2]
        self.log_result(bool(data == [[], []]) or bool(data == [[0], [1]]))

    def case_therm_smart_flash_ctrl_v1_0_sys_camera_sqrt(self):
        """智能闪光灯控制V1.0_camera_系统相机"""
        data = "暂不实现"
        self.logger.info("\n*** 智能闪光灯控制V1.0_camera_系统相机 ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)

    def case_therm_video_chat_third_party_camera_sqrt(self):
        """视频畅聊_camera_三方相机"""
        data = "暂不实现"
        self.logger.info("\n*** 视频畅聊_camera_三方相机 ***\n" + "- " + data + "\n", ext_event=True)
        self.log_result(data)
    # -------------------------------- sqrt -------------------------------------

