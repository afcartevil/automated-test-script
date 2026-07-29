import os.path
import threading
from datetime import datetime
from typing import cast

from dz_remote.dz_api_error import TestExecutionFailed
from phone_dispatcher.phone_dispatcher_mix_in import PhoneDispatcherMixIn
from powertrde import env
from dz_remote.uni_device_dz_seat import UniDeviceDzSeat
from powertrde.utils.simple_event_center import SimpleEventCenter
from tests.dzppt.aw.dzppt_u2d_helper import DzpptU2DTestHelper
from tpy_aw.uni_device_u2d import UniDeviceU2D
from powertrde.framework.uni_device import UniDevice
from powertrde.utils import misc_utils, path_utils
import shutil
import concurrent.futures
from pathlib import Path
import time
from powertrde.utils.trde import adb
from tpytest.scheme.scheme_task_session_life import SchemeTaskSessionLife
from tpytest.task_session_life import TaskSessionLife
from tpytest_extends.scheme.cases_scheme import CasesScheme
from typing import Optional


class CasesDzPpt(CasesScheme, PhoneDispatcherMixIn):
    def __init__(self):
        super().__init__()
        self._trace_monitor_step_handler = None

    @property
    def u2d_helper(self) -> DzpptU2DTestHelper:
        return super().u2d_helper

    @property
    def c_u2d_helper(self) -> DzpptU2DTestHelper:
        return super().c_u2d_helper

    @property
    def o_u2d_helper(self) -> DzpptU2DTestHelper:
        return super().o_u2d_helper

    @property
    def has_caller_sensor_for_dz(self):
        return self.dzppt_env.has_caller_sensor and not self.dzppt_env.is_u2d_debug_mode

    @property
    def dz_client(self):
        return self.dzppt_env.dz_client

    @property
    def dz_seat(self):
        return self.dz_client.seat

    @classmethod
    def get_dz_client(cls):
        return cls.get_dzppt_env().dz_client

    @classmethod
    def get_dz_seat(cls):
        return cls.get_dz_client().seat

    @property
    def und(self) -> UniDevice:
        return self.dzppt_env.uni_device

    @property
    def und_u2(self) -> UniDeviceU2D:
        return self.dzppt_env.uni_device_u2

    @property
    def und_dz(self) -> UniDeviceDzSeat:
        return self.dzppt_env.uni_device_dz

    @classmethod
    def get_und(cls) -> UniDevice:
        return cls.get_dzppt_env().uni_device

    @classmethod
    def get_und_u2(cls) -> UniDeviceU2D:
        return cls.get_dzppt_env().uni_device_u2

    @classmethod
    def get_und_dz(cls) -> UniDeviceDzSeat:
        return cls.get_dzppt_env().uni_device_dz

    @property
    def dzppt_env(self):
        return self.get_dzppt_env()

    @classmethod
    def get_dzppt_env(cls):
        from tests.dzppt.dzppt_env import get_dzppt_env
        return get_dzppt_env()

    def dz_run_case(self, case_path: str, timeout: float = 1200, copy_dz_log: bool = False):
        self.logger.info("DZ case start", tag=f'DZ Case {case_path}')
        dz_log_path = ''
        try:
            def _internal_copy_dz_case_result_log(task_id, result_json, exc):
                nonlocal dz_log_path
                dz_log_path = self._copy_dz_case_result_log(result_json, copy_dz_log)

            result = self.dz_seat.execute_test_case(case_path, timeout, on_task_end=_internal_copy_dz_case_result_log)
            self.logger.info(f"DZ case passed: [dz log: {dz_log_path}]\n{result}", tag=f'DZ Case {case_path}')
        except TestExecutionFailed as tef:
            result = tef.response
            self.logger.error_with_tag(f"DZ case failed: [dz log: {dz_log_path}]\n{tef}", tag=f'DZ Case {case_path}',
                                       ext_event=True)
            raise
        except TimeoutError as te:
            self.logger.warning(f"DZ case timeout: {te}", tag=f'DZ Case {case_path}', ext_event=True)
            raise
        except Exception as e:
            self.logger.error_with_tag(f"DZ case error: {e}", tag=f'DZ Case {case_path}', ext_event=True)
            raise

    def _copy_dz_case_result_log(self, dz_result: dict, copy_dz_log: bool):
        case_name = dz_result['CaseName']
        workFolder = dz_result['WorkFolder']
        folderName = os.path.basename(workFolder)
        pass_or_fail = 'pass' if dz_result['ExeResult'] else 'fail'
        folderName = f'dz_{folderName}_{pass_or_fail}_{case_name}'
        folderPath = os.path.join(self.session_logs_dir, folderName)
        folderPath = path_utils.get_unique_path(folderPath)
        os.makedirs(folderPath)
        misc_utils.write_all_text(os.path.join(folderPath, 'dz_result.txt'), str(dz_result))
        # 复制东舟Log
        if copy_dz_log:
            self._copy_logs_async_background(workFolder, folderPath)
        return folderPath

    @staticmethod
    def copy_file(src: Path, dst: Path):
        """ 复制单个文件 """
        os.makedirs(os.path.dirname(str(dst)), exist_ok=True)
        shutil.copy2(src, dst)

    @staticmethod
    def get_optimal_workers():
        """ 根据 CPU 核心数，自动计算合适的并行线程/进程数 """
        cpu_cores = os.cpu_count() or 4  # 获取 CPU 核心数，默认至少 4
        return min(8, max(2, cpu_cores))  # 限制最大 8 个并行任务

    def _copy_logs_async(self, src_log_dir: str, dst_log_dir: str, use_multiprocessing=True):
        """
        自适应多线程/多进程复制日志文件，避免同时打开过多并行任务。

        :param src_log_dir: 源日志文件夹路径
        :param dst_log_dir: 目标日志文件夹路径
        :param use_multiprocessing: 是否使用多进程（适用于大文件），否则使用多线程（适用于小文件）
        """
        src_path = Path(src_log_dir)
        dst_path = Path(dst_log_dir)

        if not src_path.exists() or not src_path.is_dir():
            self.logger.warning(f"源日志文件夹不存在: {src_path}", ext_event=True)
            return

        dst_path.mkdir(parents=True, exist_ok=True)

        file_list = [f for f in src_path.rglob("*") if f.is_file()]
        num_workers = self.get_optimal_workers()  # 自动计算最佳并行数

        self.logger.debug(
            f"发现 {len(file_list)} 个文件，使用 {num_workers} 个 {'进程' if use_multiprocessing else '线程'} 进行复制")

        Executor = concurrent.futures.ProcessPoolExecutor if use_multiprocessing else concurrent.futures.ThreadPoolExecutor

        with Executor(max_workers=num_workers) as executor:
            future_to_file = {executor.submit(self.copy_file, file, dst_path / file.relative_to(src_path)): file for
                              file in
                              file_list}

            for future in concurrent.futures.as_completed(future_to_file):
                try:
                    future.result()  # 捕获可能的异常
                except Exception as e:
                    self.logger.error_with_tag(f"[ERROR] 复制 {future_to_file[future]} 失败: {e}", ext_event=True)

        # print(f"[INFO] 日志文件夹复制完成: {src_path} -> {dst_path}")

    def _copy_logs_async_background(self, src_log_dir: str, dst_log_dir: str):
        """
        启动一个后台线程异步复制日志文件夹，复制任务在后台运行，
        不会阻塞 pytest 测试用例执行，也不会引发僵尸进程问题。
        """
        thread = threading.Thread(
            target=self._copy_logs_async,
            args=(src_log_dir, dst_log_dir),
            daemon=True  # daemon 线程会在主线程退出时自动终止
        )
        thread.start()
        thread.join()

    @staticmethod
    def get_dz_res(base_res_path: str, res_name: str):
        return base_res_path + res_name

    @classmethod
    def dz_kill_last_task(cls, task_number=1, swipe_bottom_edge_first=False):
        cls.dz_return_home_first_page(swipe_bottom_edge_first)
        und = cls.get_und()
        und.click_menu()
        time.sleep(1)
        for i in range(task_number):
            if i > 0:
                time.sleep(0.3)
            und.swipe_direction('up', speed=200)
        time.sleep(0.2)
        und.click_home()
        time.sleep(0.5)

    @classmethod
    def dz_return_home(cls, swipe_bottom_edge_first=False):
        und = cls.get_und()
        if swipe_bottom_edge_first:
            und.edge_swipe('bottom', speed=200)
            time.sleep(0.25)
        und.click_home(2, interval=0.2)
        time.sleep(1)

    @classmethod
    def dz_return_home_first_page(cls, swipe_bottom_edge_first=False):
        und = cls.get_und()
        if swipe_bottom_edge_first:
            und.edge_swipe('bottom', speed=200)
            time.sleep(0.25)
        und.click_back(2, interval=0.2)
        time.sleep(1)
        und.click_home(2, interval=0.2)
        time.sleep(1)
        und.click_home(1)
        time.sleep(0.5)

    @classmethod
    def dz_open_airplane_mode(cls):
        """开启飞行模式"""

        def _try_func():
            cls.dz_open_control_center()
            time.sleep(1)
            cls.get_und().click_match_template(
                cls.get_dzppt_env().preset_record_groups.get_static('Settings').get('airplane_mode'), target_score=0.6)

        misc_utils.retry_func(_try_func, attempts=2)
        time.sleep(1)
        cls.get_und().click_home()
        cls.get_dzppt_env().selected_dz_seat_phone_state_cache.is_airplane_mode_on = True

    @classmethod
    def dz_close_airplane_mode(cls):
        """关闭飞行模式"""

        def _try_func():
            cls.dz_open_control_center()
            time.sleep(1)
            cls.get_und().click_match_template(
                cls.get_dzppt_env().preset_record_groups.get_static('Settings').get('airplane_mode'), target_score=0.6)

        misc_utils.retry_func(_try_func, attempts=2)
        time.sleep(1)
        cls.get_und().click_home()
        cls.get_dzppt_env().selected_dz_seat_phone_state_cache.is_airplane_mode_on = False

    @classmethod
    def dz_open_settings(cls):
        """打开第三个app, 需要提前设置setting在桌面第三个app位置上"""

        def _try_func():
            cls.get_und().click_home(2)
            cls.get_und().click_tuple((0.617, 0.133))
            # cls.dz_open_control_center()
            # time.sleep(1)
            # cls.get_und().click_match_template(
            #     cls.get_dzppt_env().preset_record_groups.get_static('Settings').get('settings'),
            #     limit_area=(0, 0, 1, 0.4),
            #     target_score=0.6)
            time.sleep(1)
            cls.get_und().assert_match_text("Settings", limit_area=(0, 0, 1, 0.4), target_score=0.6, match_times=3)

        misc_utils.retry_func(_try_func, attempts=2)
        time.sleep(2)

    @classmethod
    def dz_open_settings_via_control_center(cls):
        """通过下拉控制中心打开设置界面"""
        def _try_func():
            cls.dz_open_control_center()
            time.sleep(1)
            cls.get_und().click_match_template(
                cls.get_dzppt_env().preset_record_groups.get_static('Settings').get('settings'),
                limit_area=(0, 0, 1, 0.4),
                target_score=0.6)
            time.sleep(1)
            cls.get_und().assert_match_text("Settings", limit_area=(0, 0, 1, 0.4), target_score=0.6, match_times=3)

        misc_utils.retry_func(_try_func, attempts=2)
        time.sleep(2)
    @classmethod
    def _dz_open_wifi(cls):
        def _try_func():
            cls.get_und().click_match_template(
                cls.get_dzppt_env().preset_record_groups.get_static('Settings').get('wifi'),
                limit_area=(0, 0, 0.95, 0.4),
                target_score=0.80)

        misc_utils.retry_func(_try_func, attempts=2)
        time.sleep(1)
        cls.get_und().click_home()
        if cls.get_dzppt_env().is_tran_cpu_sprd:
            time.sleep(3)
        cls.get_dzppt_env().selected_dz_seat_phone_state_cache.is_wifi_on = True
    @classmethod
    def dz_open_wifi(cls):
        """通过下拉控制中心打开Wifi开关"""

        def _try_func():
            cls.dz_open_control_center()
            time.sleep(1)
            if cls.get_dou3_env().has_env_key('TRAN_XOS_TOS16'):
                return cls._dz_close_wifi()
            if "TRAN" in cls.get_dzppt_env().app_multi_package_keys:
                cls.get_und().click_match_template(
                    cls.get_dzppt_env().preset_record_groups.get_static('Settings').get('wifi'),
                    limit_area=(0, 0, 0.95, 0.4),
                    target_score=0.80)
            else:
                cls.get_und().click_match_template(
                    cls.get_dzppt_env().preset_record_groups.get_static('Settings').get('wifi_vivo'),
                    limit_area=(0, 0, 0.95, 0.4),
                    target_score=0.80)

        misc_utils.retry_func(_try_func, attempts=2)
        time.sleep(1)
        cls.get_und().click_home()
        if cls.get_dzppt_env().is_tran_cpu_sprd:
            time.sleep(3)
        cls.get_dzppt_env().selected_dz_seat_phone_state_cache.is_wifi_on = True

    @classmethod
    def dz_open_control_center(cls):
        cls.get_und().edge_swipe('top_right', 1 if cls.get_dzppt_env().is_tran_cpu_sprd else 0.5)

    @classmethod
    def _dz_close_wifi(cls):
        def _try_func():
            cls.get_und().click_match_template(
                cls.get_dzppt_env().preset_record_groups.get_static('Settings').get('wifi'),
                limit_area=(0, 0.13, 1, 0.23),
                target_score=0.80)
        misc_utils.retry_func(_try_func, attempts=2)
        time.sleep(1)
        cls.get_und().click_home()
        cls.get_dzppt_env().selected_dz_seat_phone_state_cache.is_wifi_on = False


    @classmethod
    def dz_close_wifi(cls):
        """通过下拉控制中心关闭Wifi开关"""

        def _try_func():
            cls.dz_open_control_center()
            time.sleep(1)
            if cls.get_dou3_env().has_env_key('TRAN_XOS_TOS16'):
                return cls._dz_close_wifi()
            if "TRAN" in cls.get_dzppt_env().app_multi_package_keys:
                cls.get_und().click_match_template(
                    cls.get_dzppt_env().preset_record_groups.get_static('Settings').get('wifi'),
                    limit_area=(0, 0, 1, 0.3),
                    target_score=0.6)
            else:
                cls.get_und().click_match_template(
                    cls.get_dzppt_env().preset_record_groups.get_static('Settings').get('wifi_vivo_close'),
                    limit_area=(0.05, 0.15, 0.18, 0.21),
                    target_score=0.8)


        misc_utils.retry_func(_try_func, attempts=2)
        time.sleep(1)
        cls.get_und().click_home()
        cls.get_dzppt_env().selected_dz_seat_phone_state_cache.is_wifi_on = False

    @classmethod
    def dz_click_power_and_swipe_up(cls):
        cls.get_und().click_power()
        if cls.get_dzppt_env().is_u2d_debug_mode:
            time.sleep(0.3)
        cls.get_und().swipe_direction('up', 0.6, speed=250)

    @classmethod
    def dz_open_mobile_data(cls):
        """通过下拉控制中心打开MobileData开关"""
        cls.get_dzppt_env().selected_dz_seat_phone_state_cache.is_mobile_data_on = True
        raise NotImplementedError('暂未实现，也暂时不需要实现东舟改这个')

    @classmethod
    def dz_close_mobile_data(cls):
        """通过下拉控制中心关闭MobileData开关"""
        cls.get_dzppt_env().selected_dz_seat_phone_state_cache.is_mobile_data_on = False
        raise NotImplementedError('暂未实现，也暂时不需要实现东舟改这个')

    @classmethod
    def dz_open_hotspot(cls, forced_u2d=False):
        """通过下拉控制中心打开热点开关"""
        cls.get_dzppt_env().selected_dz_seat_phone_state_cache.is_hotspot_on = True
        und = cls.get_und()
        if forced_u2d:
            und = cls.get_und_u2()

        def _try_func():
            cls.dz_open_control_center()
            time.sleep(1)
            if "TRAN" in cls.get_dzppt_env().app_multi_package_keys:
                und.click_match_template(cls.get_dzppt_env().preset_record_groups.get_static('Settings').get('hotspot_open'),
                                         target_score=0.6)
            else:
                und.click_match_template(cls.get_dzppt_env().preset_record_groups.get_static('Settings').get('hotspot_vivo'),
                                         target_score=0.6)


        misc_utils.retry_func(_try_func, attempts=2)
        time.sleep(1)
        und.click_home()

    @classmethod
    def dz_close_hotspot(cls, forced_u2d=False):
        """通过下拉控制中心关闭热点开关"""
        cls.get_dzppt_env().selected_dz_seat_phone_state_cache.is_hotspot_off = False
        und = cls.get_und()
        if forced_u2d:
            und = cls.get_und_u2()

        def _try_func():
            cls.dz_open_control_center()
            time.sleep(1)
            if "TRAN" in cls.get_dzppt_env().app_multi_package_keys:
               if cls.get_dzppt_env().has_env_key('TOS16'):
                    und.click_match_template(
                        cls.get_dzppt_env().preset_record_groups.get_static('Settings').get('hotspot_close'),
                        target_score=0.75)
               else:
                    und.click_match_template(cls.get_dzppt_env().preset_record_groups.get_static('Settings').get('hotspot_close'),
                                         target_score=0.6)
            else:
                und.click_match_template(
                    cls.get_dzppt_env().preset_record_groups.get_static('Settings').get('hotspot_vivo_close'),limit_area=(0.8,0.2,1,0.3),
                    target_score=0.8)


        misc_utils.retry_func(_try_func, attempts=2)
        time.sleep(1)
        und.click_home()

    @classmethod
    def dz_camera_start_record(cls, save_path: str):
        """开启东舟摄像头录像"""
        # 启动东舟摄像头会导致东舟用例执行异常，暂时屏蔽，而使用自己的摄像头系统
        # os.makedirs(os.path.dirname(save_path), exist_ok=True)
        # cls.get_dz_client().start_image_grab(0, save_path)

    @classmethod
    def dz_camera_stop_record(cls):
        """停止东舟摄像头录像"""
        # 启动东舟摄像头会导致东舟用例执行异常，暂时屏蔽，而使用自己的摄像头系统
        # cls.get_dz_client().stop_image_grab(0)

    @classmethod
    def _dz_vpn_on_internal_banana(cls, und: UniDevice, no_return_home: bool):
        if isinstance(und, UniDeviceU2D):
            adb.stop_app(cls.get_dzppt_env().device_id, 'com.bananago.speed')
        und.click_home(times=2, interval=0.2)
        time.sleep(0.5)

        # 以前通过搜索打开VPN，速度太慢，需要改进
        # cls.dz_search_open_app('Bana', forced_u2d)
        und.click(0.14, 0.14)

        banana_vpn_group = cls.get_dzppt_env().preset_record_groups.get_static('BananaVpn')
        und.assert_match_template(banana_vpn_group.get('assert_home'), match_times=10, match_interval=1,
                                  target_score=0.55)
        if und.match_template(banana_vpn_group.get('ad')):
            und.click(0.5, 0.82)
            time.sleep(1)

        if und.match_template(banana_vpn_group.get('connected')):
            if not no_return_home:
                und.click_home()
            cls.get_dzppt_env().selected_dz_seat_phone_state_cache.is_vpn_on = True
            return

        # Assert 新加坡节点
        und.assert_match_template(banana_vpn_group.get('Singapore'), match_times=7, match_interval=1,
                                  target_score=0.55)
        und.click(0.828, 0.576)
        time.sleep(0.5)

        if not und.match_template(banana_vpn_group.get('connected'), target_score=0.50):
            und.click(0.828, 0.576)
            time.sleep(0.5)
            und.assert_match_template(banana_vpn_group.get('connected'), target_score=0.50)

        if not no_return_home:
            und.click_home()
        cls.get_dzppt_env().selected_dz_seat_phone_state_cache.is_vpn_on = True

    @classmethod
    def _dz_vpn_on_internal(cls, und: UniDevice, no_return_home: bool):
        if isinstance(und, UniDeviceU2D):
            adb.stop_app(cls.get_dzppt_env().device_id, 'com.linsoc.android')
        und.click_home(times=2, interval=0.2)
        time.sleep(0.5)

        und.click(0.14, 0.14)

        vpn_group = cls.get_dzppt_env().preset_record_groups.get_static('Linsoc')
        und.assert_match_template(vpn_group.get('assert_home'), match_times=10, match_interval=1,
                                  limit_area=(0, 0, 0.5, 0.3))

        if und.match_text('Connected', limit_area=(0.1, 0.1, 0.7, 0.26), match_times=5):
            if not no_return_home:
                und.click_home()
            cls.get_dzppt_env().selected_dz_seat_phone_state_cache.is_vpn_on = True
            return

        for i in range(5):
            mangu = und.match_text('曼谷1', limit_area=(0, 0.1, 0.4, 1), target_score=0.85)
            if mangu:
                und.click_tuple(mangu.center)
                break
            und.swipe(0.5, 0.8, 0.5, 0.2)
            time.sleep(0.5)

        time.sleep(1)

        und.assert_match_text('Connected', limit_area=(0.1, 0.1, 0.7, 0.26), match_times=2)

        if not no_return_home:
            und.click_home()
        cls.get_dzppt_env().selected_dz_seat_phone_state_cache.is_vpn_on = True

    @classmethod
    def dz_vpn_on(cls, forced_u2d=False, no_return_home=False):
        """通过东舟机械手打开VPN"""
        und = cls.get_und_u2() if forced_u2d else cls.get_und()
        try_count = 3
        for i in range(try_count):
            try:
                cls._dz_vpn_on_internal(und, no_return_home)
                break
            except Exception:
                if i < try_count - 1:
                    cls.dz_kill_last_task()
                else:
                    raise

    @classmethod
    def _dz_vpn_off_internal_banana(cls, und: UniDevice):
        if isinstance(und, UniDeviceU2D):
            adb.stop_app(cls.get_dzppt_env().device_id, 'com.bananago.speed')
        und.click_home()
        time.sleep(0.5)

        # 以前通过搜索打开VPN，速度太慢，需要改进
        # cls.dz_search_open_app('Bana', forced_u2d)
        und.click(0.14, 0.14)

        banana_vpn_group = cls.get_dzppt_env().preset_record_groups.get_static('BananaVpn')
        und.assert_match_template(banana_vpn_group.get('assert_home'), match_times=10, match_interval=1,
                                  target_score=0.55)
        if und.match_template(banana_vpn_group.get('ad')):
            und.click(0.5, 0.82)
            time.sleep(1)

        if und.match_template(banana_vpn_group.get('not_connect')):
            cls.get_dzppt_env().selected_dz_seat_phone_state_cache.is_vpn_on = False
            und.click_home()
            return

        und.click(0.828, 0.576)
        time.sleep(0.5)

        if not und.match_template(banana_vpn_group.get('not_connect'), target_score=0.50):
            und.click(0.828, 0.576)
            time.sleep(0.5)
            und.assert_match_template(banana_vpn_group.get('not_connect'), target_score=0.50)

        und.click_home()
        cls.get_dzppt_env().selected_dz_seat_phone_state_cache.is_vpn_on = False

    @classmethod
    def _dz_vpn_off_internal(cls, und: UniDevice):
        if isinstance(und, UniDeviceU2D):
            adb.stop_app(cls.get_dzppt_env().device_id, 'com.linsoc.android')
        und.click_home(times=2, interval=0.2)
        time.sleep(0.5)

        und.click(0.14, 0.14)

        vpn_group = cls.get_dzppt_env().preset_record_groups.get_static('Linsoc')
        und.assert_match_template(vpn_group.get('assert_home'), match_times=4, match_interval=1, limit_area=(0, 0, 0.5, 0.3))

        if not und.match_text('Connected', limit_area=(0.1, 0.1, 0.7, 0.26), match_times=4):
            cls.get_dzppt_env().selected_dz_seat_phone_state_cache.is_vpn_on = False
            und.click_home()
            return

        # und.click_tuple((0.5, 0.29))
        time.sleep(1)


        disconnect = und.match_text('DISCONNECT', limit_area=(0.06, 0.26, 0.95, 0.37), match_times=4)
        if disconnect:
            und.click_tuple(disconnect.center)
            time.sleep(1)
            und.assert_match_text('DISCONNECT', limit_area=(0.06, 0.26, 0.95, 0.37), match_times=4)

        und.click_home()
        time.sleep(5)
        cls.get_dzppt_env().selected_dz_seat_phone_state_cache.is_vpn_on = False

    @classmethod
    def dz_vpn_off(cls, forced_u2d=False):
        """通过东舟机械手关闭VPN"""
        und = cls.get_und_u2() if forced_u2d else cls.get_und()
        try_count = 2
        for i in range(try_count):
            try:
                cls._dz_vpn_off_internal(und)
                break
            except Exception:
                if i < try_count - 1:
                    cls.dz_kill_last_task()
                else:
                    raise

    @classmethod
    def dz_open_bugreport(cls, forced_u2d=False):
        """通过东舟机械手打开bugreport"""
        from powertrde.framework.tran_logger import t_log
        und = cls.get_und_u2() if forced_u2d else cls.get_und()
        from tpytest_extends.scheme.scheme_extend_test_env import get_scheme_extend_env
        app_name = 'SimUnplugTool'
        pr_static = get_scheme_extend_env().preset_record_groups.get_static(app_name)
        und.click_home()
        time.sleep(1)
        und.click(0.38, 0.14)
        time.sleep(3)
        # und.click_tuple(pr_static.get('btn_bugreport'))
        und.click_match_template(pr_static.get('pic_bugreport'), match_times=3, match_interval=1)
        time.sleep(3)
        result = und.match_template(pr_static.get('pic_bugreport'), match_times=3, match_interval=1)
        if result.score < 0.85:  # 点击后会回到做桌面，故不用assert_match_template
            return
        else:
            t_log.error_with_tag("Bugreport not open !!!!!!!!!!!!!!!!!!!", ext_event=True)
            # raise Exception('bugreport not open')

    @classmethod
    def get_app_search_box_pos_y(cls) -> float:
        pos_y_record = cls.get_dzppt_env().recorded_search_box_pos_y_or_none
        if pos_y_record is not None:
            return pos_y_record
        return cls.get_u2d_helper().get_search_postion(str(cls.get_dzppt_env().os_version))

    @classmethod
    def get_app_az_pos(cls) -> tuple[float, float]:
        pos_y_record = cls.get_dzppt_env().recorded_az_pos
        return pos_y_record


    @classmethod
    def _do_az_action(cls,und,duration=0.2,start=(0.5,0.8),end=(0.5,0.01),speed=200):
        """
         根据 a_z_mode 执行 swipe 或 click
         env.get_user_env_arg("a_z_mode") 为 None / {} / 非法时使用默认值
         """
        action_mode = env.get_user_env_arg("a_z_mode")
        if not isinstance(action_mode, dict) or not action_mode:
            time.sleep(duration)
            if isinstance(und, UniDeviceU2D):
                time.sleep(0.3)
            az_pos = cls.get_app_az_pos()
            # und.click(0.85, 0.15)
            und.click_tuple(az_pos)
            return
        _duration = action_mode.get("duration", duration)
        swipe_speed = action_mode.get("swipe_speed", speed)
        time.sleep(_duration)
        if isinstance(und, UniDeviceU2D):
            time.sleep(0.3)
        und.swipe(
            start[0], start[1],
            end[0], end[1],
            speed=swipe_speed
        )


    @classmethod
    def dz_search_open_app(cls, search_name: str, forced_u2d=False, search_index: int = 0):
        """
        通过手机桌面上滑后出现的搜索框打字搜索打开一个应用
        :param dispatch_search_event: 打开后，会派发 dz_search_open_app 事件，用于接管搜索的实现
        """
        und = cls.get_und_u2() if forced_u2d else cls.get_und()
        und.click_home()
        # action_mode = env.get_user_env_arg("a_z_mode")
        # time.sleep(0.2)
        # if isinstance(und, UniDeviceU2D):
        #     time.sleep(0.3)
        # und.swipe(0.5, 0.8, 0.5, 0.01, speed=200)  # 上滑搜索框
        cls._do_az_action(und)
        time.sleep(0.6)

        other_pos = cls.get_u2d_helper().get_search_postion('other_pos')
        if other_pos:
            und.click_tuple(other_pos)
            time.sleep(0.5)

        y_postion = cls.get_app_search_box_pos_y()
        # und.click(0.50, y_postion-0.01, times=1, interval=0.3)
        und.click(0.50, y_postion, times=1, interval=0.3)
        time.sleep(1)
        if isinstance(und, UniDeviceU2D):
            time.sleep(0.5)
        cls.dz_click_keyboard_string(search_name, forced_u2d)
        time.sleep(0.3)
        e = SimpleEventCenter.get_instance().dispatch_event('dz_search_open_app', search_name=search_name, search_index=search_index, und=und)
        if not e.return_arg:
            if search_index <= 0:
                search_index = 1
            if cls.get_dzppt_env().is_tran_cpu_sprd:
                time.sleep(1)
            if other_pos:
                und.click(0.02 + (0.24 * search_index) - 0.12, 0.24)
            else:
                und.click(0.02 + (0.24 * search_index) - 0.12, 0.16)  # 第一个应用坐标

    @classmethod
    def dz_click_keyboard_char(cls, char: str, forced_u2d=False):
        """使用机械臂点击手机虚拟键盘上的一个字符"""
        und = cls.get_und_u2() if forced_u2d else cls.get_und()
        pos = cls.get_u2d_helper().get_phone_keyboard_pos_map()[char.lower() if char.isalpha() else char]
        # pos = get_phone_keyboard_pos_map()[char.lower()]
        und.click(pos[0], pos[1])

    @classmethod
    def dz_click_keyboard_string(cls, string: str, forced_u2d=False):
        """通过组合机械臂点击手机虚拟键盘上的多个字符，输入字符串"""
        # 打字场景 暂不需要判断展锐平台
        # if cls.get_dzppt_env().is_tran_cpu_sprd:
        #     time.sleep(1)
        for char in string:
            cls.dz_click_keyboard_char(char, forced_u2d)
            time.sleep(0.5)

    @classmethod
    def dz_click_callboard_char(cls, char: str, forced_u2d=False):
        und = cls.get_und_u2() if forced_u2d else cls.get_und()
        """使用机械臂点击手机虚拟键盘上的一个数字"""
        pos = cls.get_u2d_helper().get_phone_callboard_pos_map()[char.lower() if char.isalpha() else char]
        und.click(pos[0], pos[1])

    @classmethod
    def dz_click_callboard_string(cls, string: str, forced_u2d=False):
        """通过组合机械臂点击手机虚拟键盘上的多个数字，输入电话号码"""
        for char in string:
            cls.dz_click_callboard_char(char, forced_u2d)




    @classmethod
    def dz_click_offsetcallboard_char(cls, char: str, forced_u2d=False, offset=0):
        und = cls.get_und_u2() if forced_u2d else cls.get_und()
        """使用机械臂点击手机虚拟键盘上的一个数字"""
        if char == '+':
            pos = cls.get_u2d_helper().get_phone_callboard_pos_map()['0']
            und.long_press(pos[0], pos[1]+ offset, 1)
        else:
            pos = cls.get_u2d_helper().get_phone_callboard_pos_map()[char.lower() if char.isalpha() else char]
            und.click(pos[0], pos[1] + offset)

    @classmethod
    def dz_click_offsetcallboard_string(cls, string: str, forced_u2d=False, offset=0):
        """通过组合机械臂点击手机虚拟键盘上的多个数字，输入电话号码"""
        for char in string:
            cls.dz_click_offsetcallboard_char(char, forced_u2d, offset)

    @classmethod
    def dz_click_googlecallboard_char(cls, char: str, forced_u2d=False):
        und = cls.get_und_u2() if forced_u2d else cls.get_und()
        if char == '+':
            pos = cls.get_u2d_helper().get_phone_callboard_pos_map()['0']
            und.long_press(pos[0], pos[1]+ 0.06, 1)
        else:
            pos = cls.get_u2d_helper().get_phone_callboard_pos_map()[char.lower() if char.isalpha() else char]
            und.click(pos[0], pos[1] + 0.06)

    @classmethod
    def dz_click_truecallerboard_char(cls, char: str, forced_u2d=False):
        und = cls.get_und_u2() if forced_u2d else cls.get_und()
        if char == '+':
            pos = cls.get_u2d_helper().get_phone_callboard_pos_map()['0']
            und.long_press(pos[0], pos[1] + 0.015, 1)
        else:
            pos = cls.get_u2d_helper().get_phone_callboard_pos_map()[char.lower() if char.isalpha() else char]
            und.click(pos[0], pos[1] + 0.015)

    @classmethod
    def dz_click_truecallerboard_string(cls, string: str, forced_u2d=False):
        """通过组合机械臂点击手机虚拟键盘上的多个数字，输入电话号码"""
        for char in string:
            cls.dz_click_truecallerboard_char(char, forced_u2d)

    @classmethod
    def dz_click_googlecallboard_string(cls, string: str, forced_u2d=False):
        """通过组合机械臂点击手机虚拟键盘上的多个数字，输入电话号码"""
        for char in string:
            cls.dz_click_googlecallboard_char(char, forced_u2d)

    @classmethod
    def dz_led_on(cls):
        if cls.get_dzppt_env().is_u2d_debug_mode:
            return
        case_path = '【模型通用】/通用基础操作/开灯'
        cls.get_dz_seat().execute_test_case(case_path, timeout_seconds=5, delete_task_on_finish=True)

    @classmethod
    def dz_led_off(cls):
        if cls.get_dzppt_env().is_u2d_debug_mode:
            return
        case_path = '【模型通用】/通用基础操作/关灯'
        cls.get_dz_seat().execute_test_case(case_path, timeout_seconds=5, delete_task_on_finish=True)

    @classmethod
    def dz_detect_black_screen(cls):
        if 'u2d' in env.get_user_env_debug_modes():
            return not adb.is_screen_on(cls.get_dzppt_env().device_id)
        else:
            cls.dz_led_off()
            try:
                und = cls.get_und_dz()
                return und.detect_black_screen()
            finally:
                cls.dz_led_on()

    @classmethod
    def dz_toggle_debug_logger(cls, is_mtk, forced_u2d=False):
        und = cls.get_und_u2() if forced_u2d else cls.get_und()
        cls.dz_check_to_unlock_screen()
        cls.dz_return_home(True)
        cls.dz_search_open_app('contacts')
        time.sleep(2)
        und.click(0.24, 0.90, times=2)
        time.sleep(1)
        cls.dz_click_callboard_string("*#9646633#")
        time.sleep(2)
        if is_mtk:
            for i in range(6):
                und.swipe_direction('left', distance_ratio=0.8, speed=250)
                time.sleep(0.5)
            und.swipe_direction('right', distance_ratio=0.8, speed=250)
            time.sleep(0.5)
            # und.click(0.5, 0.24)
            und.click_match_text('DebugLoggerUI', target_score=0.6, match_times=3, match_interval=1)
            time.sleep(4)
            und.click(0.5, 0.92)
        else:
            und.swipe_direction('left', distance_ratio=0.8, speed=250)
            time.sleep(1)
            und.click(0.5, 0.428)
            time.sleep(4)
            und.click(0.5, 0.92)

    @classmethod
    def dz_capture_bugreport(cls, forced_u2d=False):
        und = cls.get_und_u2() if forced_u2d else cls.get_und()
        cls.dz_check_to_unlock_screen()
        cls.dz_return_home_first_page(swipe_bottom_edge_first=True)
        cls.dz_open_settings()
        und.click(0.50, 0.20)
        time.sleep(3)
        cls.dz_click_keyboard_string('developer o', forced_u2d=forced_u2d)
        time.sleep(2)
        cls.dz_click_keyboard_char('p')
        time.sleep(3)
        und.click(0.50, 0.16)
        time.sleep(2)
        und.click(0.50, 0.34)
        time.sleep(2)
        und.click(0.50, 0.89)
        time.sleep(7 * 60)
        und.click_home()

    @classmethod
    def dz_check_to_unlock_screen(cls):
        """如果识别黑屏并成功解锁，则返回True，否则False"""
        if 'u2d' in env.get_user_env_debug_modes():
            if not adb.is_screen_on(cls.get_dzppt_env().device_id):
                adb.press_key(cls.get_dzppt_env().device_id, 'KEYCODE_POWER')
                time.sleep(0.5)
                cls.get_und().swipe_direction('up')
                return True
            return False
        else:
            case_path = '【模型通用】/通用基础操作/识别黑屏上滑解锁'
            # cls.get_dz_seat().home_axes(True)
            try:
                cls.get_dz_seat().execute_test_case(case_path, timeout_seconds=20, delete_task_on_finish=True)
            except TestExecutionFailed:
                return False
            return True
            # self.dz_led_off()
            # if self.und.detect_black_screen():
            #     self.und.click_power()
            #     time.sleep(0.5)
            #     self.und.swipe_direction('up')

    @classmethod
    def dz_check_to_unlock_screen_accurate(cls, exposure_time):
        """如果识别黑屏并成功解锁，则返回True，否则False"""
        if 'u2d' in env.get_user_env_debug_modes():
            if not adb.is_screen_on(cls.get_dzppt_env().device_id):
                adb.press_key(cls.get_dzppt_env().device_id, 'KEYCODE_POWER')
                time.sleep(0.5)
                cls.get_und().swipe_direction('up')
                return True
            return False
        else:
            case_path = '【模型通用】/通用基础操作/按Power后上滑解锁'
            cls.get_dz_seat().home_axes(True)
            try:
                cls.get_dz_seat().set_exposure_time(100000)
                cls.dz_led_off()
                if cls.get_und_dz().detect_black_screen():
                    cls.get_dz_seat().execute_test_case(case_path, timeout_seconds=20, delete_task_on_finish=True)
                cls.get_dz_seat().set_exposure_time(exposure_time)
                cls.dz_led_on()
            except TestExecutionFailed:
                return False
            return True

    def get_pt5_filepath(self):
        m = self.session_life.get_meta_report_dir()
        if not os.path.exists(m):
            os.makedirs(m)
        return os.path.join(m, f'{self.case_report.display_id}.pt5')

    @property
    def trace_monitor_step_handler(self):
        if self._trace_monitor_step_handler is None:
            from tests.dzppt.aw.trace_monitor_step_handler import TraceMonitorStepHandler
            self._trace_monitor_step_handler = TraceMonitorStepHandler()
        return self._trace_monitor_step_handler

    @property
    def current_session_tracer(self):
        return self.trace_monitor_step_handler.get_exist_tracer(cast(SchemeTaskSessionLife, self.session_life))

    @property
    def session_tracer(self):
        return self.trace_monitor_step_handler.get_tracer_by_session_life(cast(SchemeTaskSessionLife, self.session_life))

    @classmethod
    def get_trace_dir(cls, session_life: TaskSessionLife):
        return os.path.join(session_life.get_session_logs_dir(), 'trace')

    @property
    def trace_dir(self):
        return self.get_trace_dir(self.session_life)

    def wait_for_trace_pulls(self):
        if self.current_session_tracer:
            self.current_session_tracer.wait_for_all_pulls()

    def pull_all_pending_traces(self, raise_on_error=True):
        if self.current_session_tracer:
            return self.current_session_tracer.pull_all_pending_traces(raise_on_error=raise_on_error)
        return None

    def on_post_call(self, exception: Optional[Exception]):
        super().on_post_call(exception)

        if exception is not None and (self.scheme_env.user_config.notify_group_name or self.scheme_env.user_config.notify_user_email):
            try:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                utp_mode = ("full" if self.user_config.is_run_mode_utp_full else
                            "single" if self.user_config.is_run_mode_utp_single else
                            "manual")
                # 发送飞书通知
                er = (f"用例名：{self.case_name}\n"
                      f"用例描述：{self.case_request.case_desc}\n"
                      f"utp模式：{utp_mode}\n"
                      f"详细信息：{exception}\n"
                      f"时间：{current_time}\n"
                      f"测试手机：{self.scheme_env.device_model}\n"
                      f"sn号：{self.scheme_env.device_id}\n"
                      f"主机地址：{self.session_life.session_report.host_info.host_ip}\n"
                      f"主机用户：{self.session_life.session_report.host_info.user_name}"
                      )
                if self.scheme_env.user_config.notify_group_name:
                    self.scheme_env.feishu_helper.send_text_to_group(self.scheme_env.user_config.notify_group_name, er)
                if self.scheme_env.user_config.notify_user_email:
                    self.scheme_env.feishu_helper.send_text_to_user(self.scheme_env.user_config.notify_user_email, er)
                self.logger.info(f"已发送用例错误飞书通知")
            except Exception as e:
                self.logger.warning(f"发送用例飞书通知失败: {str(e)}")

    @classmethod
    def restore_power(cls, target_vout=4.0, target_battery_level=90, retries=3, delay=7.5, recovery_attempts=3):
        from pypowertool.powertool_utils import PowerToolManager
        from powertrde.framework.tran_logger import t_log

        power_tool = PowerToolManager.get_default_instance()
        success = False  # 用于标记恢复是否成功

        # 外部循环：如果电池电量不足，则重试恢复操作
        for _ in range(retries):
            power_tool.set_vout(2.0, usb_link=False)
            power_tool.set_vout(4.4, usb_link=True)

            is_connected = cls.get_scheme_env().u2d_helper.wait_device_connection(timeout=60, interval=5)
            if is_connected:
                t_log.info('手机已连接到usb,无需手动重启', ext_event=True)
                power_tool.set_vout(target_vout, usb_link=True)
                return

            # 尝试恢复设备，最多重试 'recovery_attempts' 次
            for attempt in range(recovery_attempts):
                hold_time = delay + attempt
                t_log.info('长按power重启', ext_event=True)
                cls.get_und().long_press_power(hold_time=hold_time)
                time.sleep(30)

                # 检查设备是否通过 ADB 连接
                is_connected = cls.get_scheme_env().u2d_helper.wait_device_connection(timeout=90, interval=5)
                if is_connected is None:
                    t_log.debug('设备没有连接，再次长按power', ext_event=True)
                    continue  # 如果设备没有连接，重试
                else:
                    # 检查电池电量是否足够
                    battery_level = cls.get_scheme_env().u2d_helper.get_battery_level()
                    if battery_level >= target_battery_level:
                        t_log.info('电量恢复成功，跳出循环', ext_event=True)
                        success = True  # 标记恢复成功
                        break  # 退出恢复尝试循环
                    else:
                        # 如果电池电量不足，重新开始外部循环
                        break
            if success:
                break  # 如果恢复成功，退出外部循环

        if not success:
            raise Exception("在多次尝试后无法恢复电源。")

        power_tool.set_vout(target_vout, usb_link=True)
