from datetime import datetime

from powertrde.utils.log import mobilelog
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends.base_u2d_test_helper import BaseU2DTestHelper


class U2DHelperMobileLog(BaseU2DTestHelper):
    def reset_bugreport(self):
        """
        重置手机的Bugreports时间，使得手机的Bugreports时间与当前时间一致
        """
        adb.reset_batterystats_for_bugreport(self.device_id)

    def clear_bugreports(self, reset_bugreport_also=False):
        """
        清除手机的Bugreports
        reset_bugreport_time_also：是否同时重置bugreport的时间，默认为False
        """
        mobilelog.clear_bugreports(self.device_id, reset_bugreport_time_also=reset_bugreport_also)

    def find_next_closest_bugreport(self, target_datetime: datetime):
        """
        找到手机里某个时间点之后的最近的一个bugreport文件
        """
        return mobilelog.find_next_closest_bugreport(self.device_id, target_datetime)

    def find_previous_closest_bugreport(self, target_datetime: datetime):
        """
        找到手机里某个时间点之前的最近的一个bugreport文件
        """
        return mobilelog.find_previous_closest_bugreport(self.device_id, target_datetime)

    def clear_and_start_mobile_log(self, start_log_flag=5, wait_duration_after_log_start=15, set_log_size=10000, include_bug_report_clear_reset=True):
        """
        清除手机日志并重新开始记录日志
        start_log_flag：日志开始记录的标志（位运算），默认为5。可选位：# 127-all, 1-MobileLog, 2-ModemLog, 4-NetworkLog, 8-METlog, 16-GPSLog, 32-ConnsysFWLog, 64-BTHostLog
        wait_duration_after_log_start：日志开始后，为了正确记录日志，需要等待一段时间，默认为15秒
        set_log_size：同时调整日志储存文件大小，默认为10000MB
        include_bug_report_clear_reset：是否包含bugreport的清理和重置，默认为True
        """
        import time
        for retry in range(3):
            try:
                mobilelog.clear_and_start_mobile_log(self.device_id, self.u2d, start_log_flag, wait_duration_after_log_start, set_log_size, include_bug_report_clear_reset)
                break
            except Exception as e:
                if retry < 2:
                    error_type = type(e).__name__
                    print(f"[WARNING] 操作失败，等待2秒后重试 ({retry + 1}/3): {error_type} - {e}")
                    time.sleep(2)
                    continue
                # 最后一次重试失败，直接抛出
                raise

    def export_logs(self, export_log_dir, export_bugreports_mode='none'):
        """
        导出手机日志（如果export_bugreports_mode参数不为none，则同时导出bugreports）
        export_bugreports_mode == 'full'：重新生成bugreport，并将所有bugreports拉出
        export_bugreports_mode == 'full_exist'：不重新生成bugreport，直接将所有已经存在的bugreports拉出
        export_bugreports_mode == 'single'：重新生成bugreport，并仅拉出这个文件
        """
        mobilelog.export_logs(self.device_id, export_log_dir, export_bugreports_mode)

    def export_bugreports(self, export_bugreports_dir, export_mode='full'):
        """
        导出手机的Bugreports压缩文件
        export_mode == 'full'：重新生成bugreport，并将所有bugreports拉出
        export_mode == 'full_exist'：不重新生成bugreport，直接将所有已经存在的bugreports拉出
        export_mode == 'single'：重新生成bugreport，并仅拉出这个文件
        """
        mobilelog.export_bugreports(export_bugreports_dir, export_mode)

    # ============= Qualcomm platform diag log management methods =============

    def get_qcom_log_service_status(self):
        """
        获取高通平台各项diag日志服务的状态
        返回包含各日志服务状态的字典 (1=运行中, 0=已停止)
        """
        return mobilelog.get_qcom_log_service_status(self.device_id)

    def list_qcom_diag_log_files(self):
        """
        列出高通平台日志目录下的所有diag日志文件
        返回包含各日志目录文件列表的字典
        """
        return mobilelog.list_qcom_diag_log_files(self.device_id)

    def export_qcom_all_vendor_logs(self, export_dir):
        """
        导出高通平台所有vendor日志
        """
        mobilelog.export_qcom_all_vendor_logs(self.device_id, export_dir)

    def export_qcom_cellular_logs(self, export_dir):
        """
        导出高通平台蜂窝通信日志 (mdlog)
        """
        mobilelog.export_qcom_cellular_logs(self.device_id, export_dir)

    def export_qcom_wifi_logs(self, export_dir):
        """
        导出高通平台WiFi相关日志
        """
        mobilelog.export_qcom_wifi_logs(self.device_id, export_dir)

    def export_qcom_bluetooth_logs(self, export_dir):
        """
        导出高通平台蓝牙相关日志
        """
        mobilelog.export_qcom_bluetooth_logs(self.device_id, export_dir)

    def export_qcom_audio_logs(self, export_dir):
        """
        导出高通平台audio相关日志
        """
        mobilelog.export_qcom_audio_logs(self.device_id, export_dir)

    def export_qcom_sensor_logs(self, export_dir):
        """
        导出高通平台sensor相关日志
        """
        mobilelog.export_qcom_sensor_logs(self.device_id, export_dir)

    def export_qcom_charger_logs(self, export_dir):
        """
        导出高通平台charger相关日志
        """
        mobilelog.export_qcom_charger_logs(self.device_id, export_dir)

    def stop_all_qcom_diag_services(self, wait_seconds=10):
        """
        关闭高通平台所有diag日志服务
        wait_seconds: 关闭服务后等待时间，确保进程已终止
        """
        mobilelog.stop_all_qcom_diag_services(self.device_id, wait_seconds)

    def start_qcom_diag_service(self, service_type, stop_all_first=True, wait_seconds=10):
        """
        开启高通平台特定的diag日志服务
        
        service_type: 要启动的服务类型，可选项：
            - 'modem': 蜂窝通信日志
            - 'wifi': WiFi日志
            - 'bluetooth': 蓝牙日志
            - 'sensor': 传感器日志
            - 'audio': 音频日志
            - 'charger': 充电日志
        stop_all_first: 启动前是否先关闭所有服务 (默认: True)
        wait_seconds: 关闭服务后等待时间
        """
        mobilelog.start_qcom_diag_service(self.device_id, service_type, stop_all_first, wait_seconds)

    def clear_all_qcom_log_files(self):
        """
        清空高通平台所有日志文件
        注意: 此操作会删除所有文件，但保留文件夹结构
        """
        mobilelog.clear_all_qcom_log_files(self.device_id)

    def clear_qcom_log_folder(self, folder_type):
        """
        清空高通平台指定日志文件夹的内容
        
        folder_type: 要清空的文件夹类型，可选项：
            - 'mobilelog': /data/debuglogger/mobilelog
            - 'mdlog': /data/vendor/debuglogger/mdlog (蜂窝通信日志)
            - 'netlog': /data/vendor/debuglogger/netlog (网络相关日志)
            - 'bthci': /data/vendor/debuglogger/connsyslog/bthci (蓝牙日志)
            - 'fw': /data/vendor/debuglogger/connsyslog/fw (WiFi日志)
            - 'sensor': /data/vendor/debuglogger/adsp/sensor (传感器日志)
            - 'audio': /data/vendor/debuglogger/adsp/audio (音频日志)
            - 'charger': /data/vendor/debuglogger/adsp/charger (充电日志)
        """
        mobilelog.clear_qcom_log_folder(self.device_id, folder_type)

    def export_qcom_today_logs(self, export_dir, target_date=None):  # type: ignore
        """
        导出高通平台指定日期的日志
        
        export_dir: 导出目录
        target_date: 目标日期，格式为 'YYYY-MM-DD'，如果不提供则默认为今天
        """
        mobilelog.export_qcom_today_logs(self.device_id, export_dir, target_date)  # type: ignore

    def check_qcom_logd_services_status(self):
        """
        检查高通平台核心 logd 服务的状态 (debug.logd.*)
        返回包含各 logd 服务状态的字典 (1=运行中, 0=已停止)
        """
        return mobilelog.check_qcom_logd_services_status(self.device_id)

    def list_mobilelog_files(self):
        """
        列出 mobilelog 目录下的所有日志文件
        返回文件列表字符串
        """
        return mobilelog.list_mobilelog_files(self.device_id)

    def export_all_mobilelog(self, export_dir):
        """
        导出 mobilelog 目录下的所有文件
        """
        mobilelog.export_all_mobilelog(self.device_id, export_dir)

    def export_crash_logs(self, export_dir):
        """
        导出崩溃日志
        导出主崩溃日志文件和所有压缩归档文件
        """
        mobilelog.export_crash_logs(self.device_id, export_dir)

    def start_all_qcom_logd_services(self):
        """
        启动高通平台所有核心 logd 服务
        """
        mobilelog.start_all_qcom_logd_services(self.device_id)

    def get_all_qcom_log_services_status(self):
        """
        获取高通平台所有日志服务的状态（包括 diag_mdlog 和 logd 服务）
        返回包含所有服务状态的组合字典
        """
        return mobilelog.get_all_qcom_log_services_status(self.device_id)
