import pytest

from tests.dzppt.therm.therm_report import ThermReport
from tests.dzppt.therm.scenes.cases_therm_scenes import CasesThermScenes
from tests.dzppt.therm.test_therm import TestTherm


class TestThermScenes(TestTherm):
    # 设定该测试类绑定的测试用例设计类，该类必须继承自CasesSteps类，用以绑定测试用例步骤
    option_bind_cs_class: type = CasesThermScenes
    # 设定该类的测试用例运行时打出的Log的前缀
    option_test_log_header: str = 'Test'
    # 设定该类是否自动写入测试报告文件
    option_auto_write_report_file: bool = True
    # 设定该测试类绑定的测试用例报告类，该类必须继承自CaseTestReport类，用以绑定测试用例报告
    option_bind_report_class: type = ThermReport

    @property
    def cs(self) -> CasesThermScenes:
        return self.get_bound_cs()

    @pytest.mark.test_app('Settings')
    def test_therm_mock_1(self):
        self.cs.case_therm_mock_1()

    def test_therm_mock_2(self):
        self.cs.case_therm_mock_2()

    # def test_therm_powerhal_encrypt(self):
    #     """power_app_cfg.xml解密方法"""
    #     return self.cs.case_therm_powerhal_encrypt()
    #
    # def test_therm_policy_encrypt(self):
    #     """policy解密方法 """
    #     return self.cs.case_therm_policy_encrypt()

    # ----------------------------------------- Q平台 -------------------------------------------------
    def test_therm_generated_platform_thermal_qcom(self):
        """thermal zone,cooling device是否正常生成"""
        return self.cs.case_therm_generated_platform_thermal_qcom()

    def test_therm_read_ntc_temp_qcom(self):
        """NTC温度是否能否正常读取"""
        return self.cs.case_therm_read_ntc_temp_qcom()

    def test_therm_working_thermal_framework_qcom(self):
        """Thermal框架工作是否正常"""
        return self.cs.case_therm_working_thermal_framework_qcom()

    def test_therm_working_qt_service_qcom(self):
        """qt-setvice是否工作正常"""
        return self.cs.case_therm_working_qt_service_qcom()

    def test_therm_step_freq_cpu_qthermal_cfg_qcom(self):
        """阶梯控频_CPU多阶调频_高通thermal通用配置"""
        return self.cs.case_therm_step_freq_cpu_qthermal_cfg_qcom()

    def test_therm_step_freq_cpu_camera_qcom(self):
        """阶梯控频_CPU多阶调频_高通thermal_客制化_相机"""
        return self.cs.case_therm_step_freq_cpu_camera_qcom()

    def test_therm_step_freq_cpu_video_qcom(self):
        """阶梯控频_CPU多阶调频_高通thermal_客制化_视频"""
        return self.cs.case_therm_step_freq_cpu_video_qcom()

    def test_therm_step_freq_cpu_video_call_qcom(self):
        """阶梯控频_CPU多阶调频_高通thermal_客制化_视频通话"""
        return self.cs.case_therm_step_freq_cpu_video_call_qcom()

    def test_therm_step_freq_cpu_game_qcom(self):
        """阶梯控频_CPU多阶调频_高通thermal_客制化_游戏"""
        return self.cs.case_therm_step_freq_cpu_game_qcom()

    def test_therm_step_freq_benchmark_score_qcom(self):
        """阶梯控频_CPU多阶调频_高通thermal_客制化_跑分"""
        return self.cs.case_therm_step_freq_benchmark_score_qcom()

    def test_therm_core_iso_cpu_mtkthermal_cfg_qcom(self):
        """核心隔离_CPU核心隔离_高通thermal通用配置"""
        return self.cs.case_therm_core_iso_cpu_mtkthermal_cfg_qcom()

    def test_therm_high_temp_backlight_disp_all_qcom(self):
        """高温背光_display_all"""
        return self.cs.case_therm_high_temp_backlight_disp_all_qcom()

    def test_therm_hbm_high_temp_ctrl_disp_outdoor_high_qcom(self):
        """HBM高温控制_display_户外高亮"""
        return self.cs.case_therm_hbm_high_temp_ctrl_disp_outdoor_high_qcom()

    def test_therm_screen_brightness_limit_disp_mtk_cfg_qcom(self):
        """屏幕亮度限制_display_高通thermal通用配置"""
        return self.cs.case_therm_screen_brightness_limit_disp_mtk_cfg_qcom()

    def test_therm_smart_temp_rise_dyn_limit_charging_qcom(self):
        """智能温升动态限流_充电_充电"""
        return self.cs.case_therm_smart_temp_rise_dyn_limit_charging_qcom()

    def test_therm_three_level_charging_qcom(self):
        """三档充电"""
        return self.cs.case_therm_three_level_charging_qcom()

    def test_therm_charging_temp_limit_charging_camera_qcom(self):
        """高通thermal充电限流_相机"""
        return self.cs.case_therm_charging_temp_limit_charging_camera_qcom()

    def test_therm_charging_temp_limit_charging_video_qcom(self):
        """高通thermal充电限流_视频"""
        return self.cs.case_therm_charging_temp_limit_charging_video_qcom()

    def test_therm_charging_temp_limit_charging_video_call_qcom(self):
        """高通thermal充电限流_视频通话"""
        return self.cs.case_therm_charging_temp_limit_charging_video_call_qcom()

    def test_therm_charging_temp_limit_charging_game_qcom(self):
        """高通thermal充电限流_游戏"""
        return self.cs.case_therm_charging_temp_limit_charging_game_qcom()

    def test_therm_game_thermal_ctrl_engine_1_0_game_qcom(self):
        """游戏温控引擎1.0_游戏_游戏"""
        return self.cs.case_therm_game_thermal_ctrl_engine_1_0_game_qcom()

    def test_therm_game_QFPS_game_qcom(self):
        """QFPS_游戏"""
        return self.cs.case_therm_game_QFPS_game_qcom()

    def test_therm_camera_high_temp_protection_sys_camera_qcom(self):
        """Camera高温保护策略_camera_系统相机"""
        return self.cs.case_therm_camera_high_temp_protection_sys_camera_qcom()

    def test_therm_video_power_saving_mode_v1_0_sys_camera_qcom(self):
        """Video省电模式V1.0_camera_系统相机"""
        return self.cs.case_therm_video_power_saving_mode_v1_0_sys_camera_qcom()

    def test_therm_image_smart_temp_ctrl_v1_0_sys_camera_qcom(self):
        """影像智能温控V1.0_camera_系统相机"""
        return self.cs.case_therm_image_smart_temp_ctrl_v1_0_sys_camera_qcom()

    def test_therm_smart_flash_ctrl_v1_0_sys_camera_qcom(self):
        """智能闪光灯控制V1.0_camera_系统相机"""
        return self.cs.case_therm_smart_flash_ctrl_v1_0_sys_camera_qcom()

    def test_therm_video_chat_third_party_camera_qcom(self):
        """视频畅聊_camera_三方相机"""
        return self.cs.case_therm_video_chat_third_party_camera_qcom()

    # ----------------------------------------- Q平台 -------------------------------------------------

    # ----------------------------------------- MTK平台 -------------------------------------------------
    def test_therm_generated_platform_thermal_mtk(self):
        """thermal zone, cooling device是否正常生成"""
        return self.cs.case_therm_generated_platform_thermal_mtk()

    def test_therm_read_ntc_temp_mtk(self):
        """NTC温度是否正常读取"""
        return self.cs.case_therm_read_ntc_temp_mtk()

    def test_therm_working_thermal_framework_mtk(self):
        """Thermal框架是否正常工作"""
        return self.cs.case_therm_working_thermal_framework_mtk()

    def test_therm_customize_starup_thermal_policy_mtk(self):
        """开机定制thermal policy"""
        return self.cs.case_therm_customize_starup_thermal_policy_mtk()

    def test_therm_kswapd_bind_small_cpu_all_mtk(self):
        """Kswapd绑小核_CPU_all"""
        return self.cs.case_therm_kswapd_bind_small_cpu_all_mtk()

    def test_therm_short_video_bind_cpu_feat_mtk(self):
        """短视频绑核方案_CPU_feature"""
        return self.cs.case_therm_short_video_bind_cpu_feat_mtk()

    def test_therm_high_temperature_transient_mtk(self):
        """高温瞬态"""
        return self.cs.case_therm_high_temperature_transient_mtk()

    def test_therm_dyn_freq_cpu_mtkthermal_cfg_mtk(self):
        """动态调频_CPU动态调频_MTKthermal通用配置"""
        return self.cs.case_therm_dyn_freq_cpu_mtkthermal_cfg_mtk()

    def test_therm_dyn_freq_cpu_policy01_camera_60fps_mtk(self):
        """动态调频_CPU动态调频_Policy01-Camera场景（60fps）"""
        return self.cs.case_therm_dyn_freq_cpu_policy01_camera_60fps_mtk()

    def test_therm_dyn_freq_cpu_policy02_camera_mtk(self):
        """动态调频_CPU动态调频_Policy02-Camera场景"""
        return self.cs.case_therm_dyn_freq_cpu_policy02_camera_mtk()

    def test_therm_dyn_freq_cpu_policy03_benchmark_mtk(self):
        """动态调频_CPU动态调频_Policy03-跑分"""
        return self.cs.case_therm_dyn_freq_cpu_policy03_benchmark_mtk()

    def test_therm_dyn_freq_cpu_policy04_video_conf_call_mtk(self):
        """动态调频_CPU动态调频_Policy04-视频会议/通话"""
        return self.cs.case_therm_dyn_freq_cpu_policy04_video_conf_call_mtk()

    def test_therm_dyn_freq_cpu_policy05_browser_mtk(self):
        """动态调频_CPU动态调频_Policy05-浏览器"""
        return self.cs.case_therm_dyn_freq_cpu_policy05_browser_mtk()

    def test_therm_dyn_freq_cpu_policy06_game_mtk(self):
        """动态调频_CPU动态调频_Policy06-游戏"""
        return self.cs.case_therm_dyn_freq_cpu_policy06_game_mtk()

    def test_therm_dyn_freq_cpu_policy07_game_a_mtk(self):
        """动态调频_CPU动态调频_Policy07-游戏A"""
        return self.cs.case_therm_dyn_freq_cpu_policy07_game_a_mtk()

    def test_therm_dyn_freq_cpu_policy09_game_b_mtk(self):
        """动态调频_CPU动态调频_Policy09-游戏B"""
        return self.cs.case_therm_dyn_freq_cpu_policy09_game_b_mtk()

    def test_therm_dyn_freq_cpu_policy10_social_app_mtk(self):
        """动态调频_CPU动态调频_Policy10-社交应用"""
        return self.cs.case_therm_dyn_freq_cpu_policy10_social_app_mtk()

    def test_therm_dyn_freq_cpu_policy11_video_play_mtk(self):
        """动态调频_CPU动态调频_Policy11-视频播放"""
        return self.cs.case_therm_dyn_freq_cpu_policy11_video_play_mtk()

    def test_therm_dyn_freq_cpu_policy12_map_nav_mtk(self):
        """动态调频_CPU动态调频_Policy12-地图导航"""
        return self.cs.case_therm_dyn_freq_cpu_policy12_map_nav_mtk()

    def test_therm_dyn_freq_cpu_policy13_game_c_genshin_mtk(self):
        """动态调频_CPU动态调频_Policy13-游戏C（原神等）"""
        return self.cs.case_therm_dyn_freq_cpu_policy13_game_c_genshin_mtk()

    def test_therm_dyn_freq_cpu_policy14_one_key_migrate_mtk(self):
        """动态调频_CPU动态调频_Policy14-一键换机"""
        return self.cs.case_therm_dyn_freq_cpu_policy14_one_key_migrate_mtk()

    def test_therm_dyn_freq_cpu_policy15_game_d_football_mtk(self):
        """动态调频_CPU动态调频_Policy15-游戏D（足球）"""
        return self.cs.case_therm_dyn_freq_cpu_policy15_game_d_football_mtk()

    def test_therm_step_freq_cpu_mtkthermal_cfg_mtk(self):
        """阶梯控频_CPU多阶调频_MTKthermal通用配置"""
        return self.cs.case_therm_step_freq_cpu_mtkthermal_cfg_mtk()

    def test_therm_step_freq_cpu_policy01_camera_60fps_mtk(self):
        """阶梯控频_CPU多阶调频_Policy01-Camera场景（60fps）"""
        return self.cs.case_therm_step_freq_cpu_policy01_camera_60fps_mtk()

    def test_therm_step_freq_cpu_policy02_camera_mtk(self):
        """阶梯控频_CPU多阶调频_Policy02-Camera场景"""
        return self.cs.case_therm_step_freq_cpu_policy02_camera_mtk()

    def test_therm_step_freq_cpu_policy03_benchmark_mtk(self):
        """阶梯控频_CPU多阶调频_Policy03-跑分"""
        return self.cs.case_therm_step_freq_cpu_policy03_benchmark_mtk()

    def test_therm_step_freq_cpu_policy04_video_conf_call_mtk(self):
        """阶梯控频_CPU多阶调频_Policy04-视频会议/通话"""
        return self.cs.case_therm_step_freq_cpu_policy04_video_conf_call_mtk()

    def test_therm_step_freq_cpu_policy05_browser_mtk(self):
        """阶梯控频_CPU多阶调频_Policy05-浏览器"""
        return self.cs.case_therm_step_freq_cpu_policy05_browser_mtk()

    def test_therm_step_freq_cpu_policy06_game_mtk(self):
        """阶梯控频_CPU多阶调频_Policy06-游戏"""
        return self.cs.case_therm_step_freq_cpu_policy06_game_mtk()

    def test_therm_step_freq_cpu_policy07_game_a_mtk(self):
        """阶梯控频_CPU多阶调频_Policy07-游戏A"""
        return self.cs.case_therm_step_freq_cpu_policy07_game_a_mtk()

    def test_therm_step_freq_cpu_policy09_game_b_mtk(self):
        """阶梯控频_CPU多阶调频_Policy09-游戏B"""
        return self.cs.case_therm_step_freq_cpu_policy09_game_b_mtk()

    def test_therm_step_freq_cpu_policy10_social_app_mtk(self):
        """阶梯控频_CPU多阶调频_Policy10-社交应用"""
        return self.cs.case_therm_step_freq_cpu_policy10_social_app_mtk()

    def test_therm_step_freq_cpu_policy11_video_play_mtk(self):
        """阶梯控频_CPU多阶调频_Policy11-视频播放"""
        return self.cs.case_therm_step_freq_cpu_policy11_video_play_mtk()

    def test_therm_step_freq_cpu_policy12_map_nav_mtk(self):
        """阶梯控频_CPU多阶调频_Policy12-地图导航"""
        return self.cs.case_therm_step_freq_cpu_policy12_map_nav_mtk()

    def test_therm_step_freq_cpu_policy13_game_c_genshin_mtk(self):
        """阶梯控频_CPU多阶调频_Policy13-游戏C（原神等）"""
        return self.cs.case_therm_step_freq_cpu_policy13_game_c_genshin_mtk()

    def test_therm_step_freq_cpu_policy14_one_key_migrate_mtk(self):
        """阶梯控频_CPU多阶调频_Policy14-一键换机"""
        return self.cs.case_therm_step_freq_cpu_policy14_one_key_migrate_mtk()

    def test_therm_step_freq_cpu_policy15_game_d_football_mtk(self):
        """阶梯控频_CPU多阶调频_Policy15-游戏D（足球）"""
        return self.cs.case_therm_step_freq_cpu_policy15_game_d_football_mtk()

    def test_therm_core_iso_cpu_mtkthermal_cfg_mtk(self):
        """核心隔离_CPU核心隔离_MTKthermal通用配置"""
        return self.cs.case_therm_core_iso_cpu_mtkthermal_cfg_mtk()

    def test_therm_core_iso_cpu_policy01_camera_60fps_mtk(self):
        """核心隔离_CPU核心隔离_Policy01-Camera场景（60fps）"""
        return self.cs.case_therm_core_iso_cpu_policy01_camera_60fps_mtk()

    def test_therm_core_iso_cpu_policy02_camera_mtk(self):
        """核心隔离_CPU核心隔离_Policy02-Camera场景"""
        return self.cs.case_therm_core_iso_cpu_policy02_camera_mtk()

    def test_therm_core_iso_cpu_policy03_benchmark_mtk(self):
        """核心隔离_CPU核心隔离_Policy03-跑分"""
        return self.cs.case_therm_core_iso_cpu_policy03_benchmark_mtk()

    def test_therm_core_iso_cpu_policy04_video_conf_call_mtk(self):
        """核心隔离_CPU核心隔离_Policy04-视频会议/通话"""
        return self.cs.case_therm_core_iso_cpu_policy04_video_conf_call_mtk()

    def test_therm_core_iso_cpu_policy05_browser_mtk(self):
        """核心隔离_CPU核心隔离_Policy05-浏览器"""
        return self.cs.case_therm_core_iso_cpu_policy05_browser_mtk()

    def test_therm_core_iso_cpu_policy06_game_mtk(self):
        """核心隔离_CPU核心隔离_Policy06-游戏"""
        return self.cs.case_therm_core_iso_cpu_policy06_game_mtk()

    def test_therm_core_iso_cpu_policy07_game_a_mtk(self):
        """核心隔离_CPU核心隔离_Policy07-游戏A"""
        return self.cs.case_therm_core_iso_cpu_policy07_game_a_mtk()

    def test_therm_core_iso_cpu_policy09_game_b_mtk(self):
        """核心隔离_CPU核心隔离_Policy09-游戏B"""
        return self.cs.case_therm_core_iso_cpu_policy09_game_b_mtk()

    def test_therm_core_iso_cpu_policy10_social_app_mtk(self):
        """核心隔离_CPU核心隔离_Policy10-社交应用"""
        return self.cs.case_therm_core_iso_cpu_policy10_social_app_mtk()

    def test_therm_core_iso_cpu_policy11_video_play_mtk(self):
        """核心隔离_CPU核心隔离_Policy11-视频播放"""
        return self.cs.case_therm_core_iso_cpu_policy11_video_play_mtk()

    def test_therm_core_iso_cpu_policy12_map_nav_mtk(self):
        """核心隔离_CPU核心隔离_Policy12-地图导航"""
        return self.cs.case_therm_core_iso_cpu_policy12_map_nav_mtk()

    def test_therm_core_iso_cpu_policy13_game_c_genshin_mtk(self):
        """核心隔离_CPU核心隔离_Policy13-游戏C（原神等）"""
        return self.cs.case_therm_core_iso_cpu_policy13_game_c_genshin_mtk()

    def test_therm_core_iso_cpu_policy14_one_key_migrate_mtk(self):
        """核心隔离_CPU核心隔离_Policy14-一键换机"""
        return self.cs.case_therm_core_iso_cpu_policy14_one_key_migrate_mtk()

    def test_therm_core_iso_cpu_policy15_game_d_football_mtk(self):
        """核心隔离_CPU核心隔离_Policy15-游戏D（足球）"""
        return self.cs.case_therm_core_iso_cpu_policy15_game_d_football_mtk()

    def test_therm_high_temp_backlight_disp_all_mtk(self):
        """高温背光_display_all"""
        return self.cs.case_therm_high_temp_backlight_disp_all_mtk()

    def test_therm_hbm_high_temp_ctrl_disp_outdoor_high_mtk(self):
        """HBM高温控制_display_户外高亮"""
        return self.cs.case_therm_hbm_high_temp_ctrl_disp_outdoor_high_mtk()

    def test_therm_smart_temp_rise_dyn_limit_charging_mtk(self):
        """智能温升动态限流_充电_充电"""
        return self.cs.case_therm_smart_temp_rise_dyn_limit_charging_mtk()

    def test_therm_three_level_charging_mtk(self):
        """三档充电"""
        return self.cs.case_therm_three_level_charging_mtk()

    def test_therm_wifi_high_temp_speed_limit_wifi_all_mtk(self):
        """WiFi高温限速_wifi_all"""
        return self.cs.case_therm_wifi_high_temp_speed_limit_wifi_all_mtk()

    def test_therm_step_limit_modem_behavior_modem_all_mtk(self):
        """阶梯限制modem的行为_Modem_all"""
        return self.cs.case_therm_step_limit_modem_behavior_modem_all_mtk()

    def test_therm_game_thermal_ctrl_engine_1_0_game_mtk(self):
        """游戏温控引擎1.0_游戏_游戏"""
        return self.cs.case_therm_game_thermal_ctrl_engine_1_0_game_mtk()

    def test_therm_drt_game_whitelist_game_mtk(self):
        """DRT_游戏_白名单游戏"""
        return self.cs.case_therm_drt_game_whitelist_game_mtk()

    def test_therm_frs_stable_frame_game_mtk(self):
        """FRS稳帧_游戏_游戏"""
        return self.cs.case_therm_frs_stable_frame_game_mtk()

    def test_therm_camera_high_temp_protection_sys_camera_mtk(self):
        """Camera高温保护策略_camera_系统相机"""
        return self.cs.case_therm_camera_high_temp_protection_sys_camera_mtk()

    def test_therm_video_power_saving_mode_v1_0_sys_camera_mtk(self):
        """Video省电模式V1.0_camera_系统相机"""
        return self.cs.case_therm_video_power_saving_mode_v1_0_sys_camera_mtk()

    def test_therm_image_smart_temp_ctrl_v1_0_sys_camera_mtk(self):
        """影像智能温控V1.0_camera_系统相机"""
        return self.cs.case_therm_image_smart_temp_ctrl_v1_0_sys_camera_mtk()

    def test_therm_smart_flash_ctrl_v1_0_sys_camera_mtk(self):
        """智能闪光灯控制V1.0_camera_系统相机"""
        return self.cs.case_therm_smart_flash_ctrl_v1_0_sys_camera_mtk()

    def test_therm_video_chat_third_party_camera_mtk(self):
        """视频畅聊_camera_三方相机"""
        return self.cs.case_therm_video_chat_third_party_camera_mtk()

    # ----------------------------------------- MTK平台 -------------------------------------------------

    # ---------------------------------------- sqrt ----------------------------------------------
    def test_therm_generated_platform_thermal_sqrt(self):
        """thermal zone, cooling device是否正常生成"""
        return self.cs.case_therm_generated_platform_thermal_sqrt()

    def test_therm_read_ntc_temp_sqrt(self):
        """NTC温度是否正常读取"""
        return self.cs.case_therm_read_ntc_temp_sqrt()

    def test_therm_working_thermal_framework_sqrt(self):
        """Thermal框架是否正常工作"""
        return self.cs.case_therm_working_thermal_framework_sqrt()

    def test_therm_kswapd_bind_small_cpu_all_sqrt(self):
        """Kswapd绑小核_CPU_all"""
        return self.cs.case_therm_kswapd_bind_small_cpu_all_sqrt()

    def test_therm_short_video_bind_cpu_feat_sqrt(self):
        """短视频绑核方案_CPU_feature"""
        return self.cs.case_therm_short_video_bind_cpu_feat_sqrt()

    def test_therm_step_freq_cpu_qthermal_cfg_sqrt(self):
        """阶梯控频_CPU多阶调频_展锐thermal通用配置"""
        return self.cs.case_therm_step_freq_cpu_qthermal_cfg_sqrt()

    def test_therm_step_freq_cpu_camera_sqrt(self):
        """阶梯控频_CPU多阶调频_展锐thermal_场景识别_相机"""
        return self.cs.case_therm_step_freq_cpu_camera_sqrt()

    def test_therm_step_freq_cpu_video_sqrt(self):
        """阶梯控频_CPU多阶调频_展锐thermal_场景识别_视频"""
        return self.cs.case_therm_step_freq_cpu_video_sqrt()

    def test_therm_step_freq_cpu_video_call_sqrt(self):
        """阶梯控频_CPU多阶调频_展锐thermal_场景识别_视频通话"""
        return self.cs.case_therm_step_freq_cpu_video_call_sqrt()

    def test_therm_step_freq_cpu_game_sqrt(self):
        """阶梯控频_CPU多阶调频_展锐thermal_场景识别_游戏"""
        return self.cs.case_therm_step_freq_cpu_game_sqrt()

    def test_therm_core_iso_cpu_thermal_cfg_sqrt(self):
        """核心隔离_CPU核心隔离_thermal通用配置"""
        return self.cs.case_therm_core_iso_cpu_thermal_cfg_sqrt()

    def test_therm_high_temp_backlight_disp_all_sqrt(self):
        """高温背光_display_all"""
        return self.cs.case_therm_high_temp_backlight_disp_all_sqrt()

    def test_therm_hbm_high_temp_ctrl_disp_outdoor_high_sqrt(self):
        """HBM高温控制_display_户外高亮"""
        return self.cs.case_therm_hbm_high_temp_ctrl_disp_outdoor_high_sqrt()

    def test_therm_screen_brightness_limit_disp_sqrt_cfg_sqrt(self):
        """屏幕亮度限制_display_展锐thermal通用配置"""
        return self.cs.case_therm_screen_brightness_limit_disp_sqrt_cfg_sqrt()

    def test_therm_smart_temp_rise_dyn_limit_charging_sqrt(self):
        """智能温升动态限流_充电_充电"""
        return self.cs.case_therm_smart_temp_rise_dyn_limit_charging_sqrt()

    def test_therm_three_level_charging_sqrt(self):
        """三档充电"""
        return self.cs.case_therm_three_level_charging_sqrt()

    def test_therm_charging_temp_limit_charging_camera_sqrt(self):
        """展锐thermal充电限流_相机"""
        return self.cs.case_therm_charging_temp_limit_charging_camera_sqrt()

    def test_therm_charging_temp_limit_charging_video_sqrt(self):
        """展锐thermal充电限流_视频"""
        return self.cs.case_therm_charging_temp_limit_charging_video_sqrt()

    def test_therm_charging_temp_limit_charging_video_call_sqrt(self):
        """展锐thermal充电限流_视频通话"""
        return self.cs.case_therm_charging_temp_limit_charging_video_call_sqrt()

    def test_therm_charging_temp_limit_charging_game_sqrt(self):
        """展锐thermal充电限流_游戏"""
        return self.cs.case_therm_charging_temp_limit_charging_game_sqrt()

    def test_therm_wifi_high_temp_speed_limit_wifi_all_sqrt(self):
        """WiFi高温限速_wifi_all"""
        return self.cs.case_therm_wifi_high_temp_speed_limit_wifi_all_sqrt()

    def test_therm_game_thermal_ctrl_engine_1_0_game_sqrt(self):
        """游戏温控引擎1.0_游戏_游戏"""
        return self.cs.case_therm_game_thermal_ctrl_engine_1_0_game_sqrt()

    def test_therm_drt_game_whitelist_game_sqrt(self):
        """DRT_游戏_白名单游戏"""
        return self.cs.case_therm_drt_game_whitelist_game_sqrt()

    def test_therm_frs_stable_frame_game_sqrt(self):
        """FRS稳帧_游戏_游戏"""
        return self.cs.case_therm_frs_stable_frame_game_sqrt()

    def test_therm_camera_high_temp_protection_sys_camera_sqrt(self):
        """Camera高温保护策略_camera_系统相机"""
        return self.cs.case_therm_camera_high_temp_protection_sys_camera_sqrt()

    def test_therm_video_power_saving_mode_v1_0_sys_camera_sqrt(self):
        """Video省电模式V1.0_camera_系统相机"""
        return self.cs.case_therm_video_power_saving_mode_v1_0_sys_camera_sqrt()

    def test_therm_image_smart_temp_ctrl_v1_0_sys_camera_sqrt(self):
        """影像智能温控V1.0_camera_系统相机"""
        return self.cs.case_therm_image_smart_temp_ctrl_v1_0_sys_camera_sqrt()

    def test_therm_smart_flash_ctrl_v1_0_sys_camera_sqrt(self):
        """智能闪光灯控制V1.0_camera_系统相机"""
        return self.cs.case_therm_smart_flash_ctrl_v1_0_sys_camera_sqrt()

    def test_therm_video_chat_third_party_camera_sqrt(self):
        """视频畅聊_camera_三方相机"""
        return self.cs.case_therm_video_chat_third_party_camera_sqrt()

    # ------------------------------------------- sqrt ----------------------------------------------
