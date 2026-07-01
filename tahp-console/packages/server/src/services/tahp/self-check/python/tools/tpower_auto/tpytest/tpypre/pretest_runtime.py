import asyncio
import concurrent.futures
import sys
import threading
from datetime import datetime
from typing import List

import pytest

from powertrde.utils import algorithm_utils
from powertrde.utils.trde import adb
from tpytest.case_original_request import CaseOriginalRequest
from tpytest.scheme.scheme_test_env import get_scheme_env
from tpytest.tpypre.link_pretest_helper import LinkPretestHelper
from tpytest_extends.scheme.apps_static_info import AppsStaticInfo
from tpytest_extends.utils.app_installer import AppInstallerForProvider
from tpytest.preset_recorder import PresetRecorder
from tpytest.tpytest_scheduler import TPytestTestScheduler


class PretestRuntime:
    _instance = None
    option_app_installer_class = AppInstallerForProvider

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.scheme_env = get_scheme_env()
        self.scheme_config = self.scheme_env.user_config
        self.sys_args = sys.argv

        test_range = self.scheme_env.scheme_request.scheme_env_class_name_parent_path
        if not test_range:
            if self.scheme_env.scheme_name:
                test_range = 'test/' + self.scheme_env.scheme_name
            else:
                test_range = 'test'

        self.test_scheduler = TPytestTestScheduler([], [test_range])
        self._pretest_pre_collected_items = None
        self._pc_pretest_pass_recorder = None
        self._pc_pretest_pass_node = None
        self._phone_pretest_pass_recorder = None
        self._phone_pretest_pass_node = None
        self._copilot_pretest_pass_recorder = None
        self._copilot_pretest_pass_node = None

    @property
    def pre_collected_pretest_items(self):
        if self._pretest_pre_collected_items is None:
            self._pretest_pre_collected_items = []
            for item in self.test_scheduler.pre_collected_items:
                # 检查是否是pretest类
                if item.parent:
                    parent_cls = getattr(item.parent, 'cls', None)
                    if not parent_cls:
                        continue
                    is_pretest_class = getattr(parent_cls, 'is_pretest_class', None)
                    if is_pretest_class:
                        self._pretest_pre_collected_items.append(item)
        return self._pretest_pre_collected_items

    @property
    def pc_pretest_pass_recorder(self):
        if not self._pc_pretest_pass_recorder:
            self._pc_pretest_pass_recorder = PresetRecorder.create_recorder_node('pc', 'pc', 'pretest_pass')
        return self._pc_pretest_pass_recorder

    @property
    def pc_pretest_pass_node(self):
        if not self._pc_pretest_pass_node:
            self._pc_pretest_pass_node = PresetRecorder.load_record_groups('pc', 'pc', True, False).get('pretest_pass')
        return self._pc_pretest_pass_node

    @property
    def phone_pretest_pass_recorder(self):
        if not self._phone_pretest_pass_recorder:
            assert self.scheme_env.device_model and self.scheme_env.device_sn, 'The user env must have both device_model and device_sn present.'
            self._phone_pretest_pass_recorder = PresetRecorder.create_recorder_node(self.scheme_env.device_model, self.scheme_env.device_sn, 'pretest_pass')
        return self._phone_pretest_pass_recorder

    @property
    def phone_pretest_pass_node(self):
        if not self._phone_pretest_pass_node:
            self._phone_pretest_pass_node = self.scheme_env.preset_record_groups.get('pretest_pass')
        return self._phone_pretest_pass_node

    @property
    def copilot_pretest_pass_recorder(self):
        if not self._copilot_pretest_pass_recorder:
            assert self.scheme_env.c_device_id, 'The user env must have c_device_id present.'
            assert adb.is_adb_connected(self.scheme_env.c_device_id), 'The copilot phone must connect to PC via adb.'
            c_model = adb.device_model_simple(self.scheme_env.c_device_id)
            self._copilot_pretest_pass_recorder = PresetRecorder.create_recorder_node(c_model, self.scheme_env.c_device_id, 'pretest_pass')
        return self._copilot_pretest_pass_recorder

    @property
    def copilot_pretest_pass_node(self):
        if not self._copilot_pretest_pass_node:
            assert self.scheme_env.c_device_id, 'The user env must have c_device_id present.'
            assert adb.is_adb_connected(self.scheme_env.c_device_id), 'The copilot phone must connect to PC via adb.'
            c_model = adb.device_model_simple(self.scheme_env.c_device_id)
            self._copilot_pretest_pass_node = PresetRecorder.load_record_groups(c_model, self.scheme_env.c_device_id, True, False).get('pretest_pass')
        return self._copilot_pretest_pass_node

    def record_pc_pretest_none(self, pretest_case_id: str):
        self.pc_pretest_pass_node.update(pretest_case_id, 0)
        self.pc_pretest_pass_recorder.record(pretest_case_id, 0)

    def record_pc_pretest_pass(self, pretest_case_id: str):
        v = datetime.now().isoformat()
        self.pc_pretest_pass_node.update(pretest_case_id, v)
        self.pc_pretest_pass_recorder.record(pretest_case_id, v)

    def is_pc_pretest_pass(self, pretest_case_id: str, expiration_duration=-1.0):
        pass_time_str = self.pc_pretest_pass_node.get_with_fallback(pretest_case_id)
        if pass_time_str:
            elapse_duration = (datetime.now() - datetime.fromisoformat(pass_time_str)).total_seconds()
            ed = self.scheme_config.pretest_skip_pass_hours * 3600.0
            if expiration_duration < 0:
                expiration_duration = ed
            else:
                expiration_duration = min(expiration_duration, ed)
            return elapse_duration < expiration_duration
        return False

    def record_copilot_pretest_none(self, pretest_case_id: str):
        self.copilot_pretest_pass_node.update(pretest_case_id, 0)
        self.copilot_pretest_pass_recorder.record(pretest_case_id, 0)

    def record_copilot_pretest_pass(self, pretest_case_id: str):
        v = datetime.now().isoformat()
        self.copilot_pretest_pass_node.update(pretest_case_id, v)
        self.copilot_pretest_pass_recorder.record(pretest_case_id, v)

    def is_copilot_pretest_pass(self, pretest_case_id: str, expiration_duration=-1.0):
        try:
            pass_time_str = self.copilot_pretest_pass_node.get_with_fallback(pretest_case_id)
            if pass_time_str:
                elapse_duration = (datetime.now() - datetime.fromisoformat(pass_time_str)).total_seconds()
                ed = self.scheme_config.pretest_skip_pass_hours * 3600.0
                if expiration_duration < 0:
                    expiration_duration = ed
                else:
                    expiration_duration = min(expiration_duration, ed)
                return elapse_duration < expiration_duration
        except Exception:
            pass
        return False

    def record_phone_pretest_none(self, pretest_case_id: str):
        self.phone_pretest_pass_node.update(pretest_case_id, 0)
        self.phone_pretest_pass_recorder.record(pretest_case_id, 0)

    def record_phone_pretest_pass(self, pretest_case_id: str):
        v = datetime.now().isoformat()
        self.phone_pretest_pass_node.update(pretest_case_id, v)
        self.phone_pretest_pass_recorder.record(pretest_case_id, v)

    def is_phone_pretest_pass(self, pretest_case_id: str, expiration_duration=-1.0):
        pass_time_str = self.phone_pretest_pass_node.get_with_fallback(pretest_case_id)
        if pass_time_str:
            elapse_duration = (datetime.now() - datetime.fromisoformat(pass_time_str)).total_seconds()
            ed = self.scheme_config.pretest_skip_pass_hours * 3600.0
            if expiration_duration < 0:
                expiration_duration = ed
            else:
                expiration_duration = min(expiration_duration, ed)
            return elapse_duration < expiration_duration
        return False

    def record_pretest_result(self, target: str, case_name: str, is_pass_or_none: bool):
        if target:
            ext = ('pass' if is_pass_or_none else 'none')
            record_method = getattr(self, f'record_{target}_pretest_{ext}')
            if record_method:
                record_method(case_name)

    def is_target_pretest_pass(self, target: str, pretest_case_id: str, expiration_duration=-1.0):
        if not target:
            return False
        _method = getattr(self, f'is_{target}_pretest_pass')
        if _method:
            return _method(pretest_case_id, expiration_duration)
        return False

    @property
    def u2d_helper(self):
        return self.scheme_env.u2d_helper

    @property
    def c_u2d_helper(self):
        return self.scheme_env.c_u2d_helper

    @property
    def logger(self):
        return self.scheme_env.logger

    @property
    def pretest_level(self):
        return self.scheme_config.pretest_level

    def record_cn_sim_index(self, index: int):
        self.scheme_env.create_main_recorder_node().record('cn_sim_index', index)

    def record_sim_count(self, count: int):
        self.scheme_env.create_main_recorder_node().record('sim_count', count)

    def record_copilot_phone_number(self, number: str):
        self.scheme_env.create_main_recorder_node().record('copilot_phone_number', number)

    def record_test_phone_number(self, number: str):
        self.scheme_env.create_main_recorder_node().record('test_phone_number', number)

    def pre_collect_all_cases(self):
        """
        预收集所有测试用例
        """
        self.test_scheduler.clear_pre_collected_items()
        self.test_scheduler.pre_collect_tests(disable_output=True)

    def pre_collect_single_case(self, case_path: str):
        """
        预收集所有测试用例
        """
        self.test_scheduler.clear_pre_collected_items()
        self.test_scheduler.test_ranges = [case_path]
        self.test_scheduler.pre_collect_tests(disable_output=True)
        # self.test_scheduler.pre_collect_single_test(case_path, disable_output=True)

    def collect_single_test_case(self):
        self.test_scheduler.case_ori_requests.clear()
        self.test_scheduler.clear_scheduled_items()
        case_ori_request = CaseOriginalRequest()
        case_ori_request.parse_from('*', self.scheme_config.small_test_loop, self.scheme_config.retry)
        self.test_scheduler.case_ori_requests.append(case_ori_request)
        self.test_scheduler.generate_schedule()
        self.scheme_env.test_cases = list(self.test_scheduler.scheduled_order_items)

    def collect_test_cases_and_apps(self):
        """
        收集测试用例
        """
        self.test_scheduler.case_ori_requests.clear()
        self.test_scheduler.clear_scheduled_items()
        self.test_scheduler.case_ori_requests.extend(self.scheme_config.cases)
        self.test_scheduler.generate_schedule()

        # 检查用例负载均衡
        if self.scheme_config.case_loading_balance:
            # 计算负载区间
            work_interval = algorithm_utils.get_unit_work_interval(len(self.test_scheduler.scheduled_order_items), self.scheme_config.total_devices, self.scheme_config.device_index)
            if work_interval:
                self.test_scheduler.clip_scheduled_items_interval(work_interval[0], work_interval[1])
            else:
                self.test_scheduler.clear_scheduled_items()

        self.scheme_env.test_cases = list(self.test_scheduler.scheduled_order_items)

        self.scheme_env.test_apps.clear()
        self.scheme_env.copilot_apps.clear()
        self.scheme_env.collected_pretest_names.clear()
        self.scheme_env.collected_pretest_flags.clear()
        test_apps_list = list()
        test_apps_set = set()
        copilot_apps_set = set()

        def _dict_deep_get(d, path):
            for key in path.split('/'):
                d = d[key]
            return d

        for v in self.scheme_env.test_cases:
            item = v.test_item
            m: pytest.Mark = item.get_closest_marker('test_app')
            cm: pytest.Mark = item.get_closest_marker('copilot_app')
            m_x: pytest.Mark = item.get_closest_marker('test_app_from_config')
            cm_x: pytest.Mark = item.get_closest_marker('copilot_app_from_config')
            need_copilot = bool(item.get_closest_marker('need_copilot'))
            need_observe = bool(item.get_closest_marker('need_observe'))
            if need_copilot:
                self.scheme_env.has_any_need_copilot_mark = True
            if need_observe:
                self.scheme_env.has_any_need_observe_mark = True
            lp_helper = LinkPretestHelper(item)
            if m:
                test_apps_list.extend(m.args)
            if m_x:
                for a in m_x.args:
                    try:
                        app_or_apps = _dict_deep_get(self.scheme_config.configured_config_dict, a)
                    except KeyError:
                        continue
                    # app_or_apps = self.scheme_config.configured_config_dict.get(a)
                    if isinstance(app_or_apps, list):
                        test_apps_list.extend(app_or_apps)
                    elif isinstance(app_or_apps, str):
                        test_apps_list.append(app_or_apps)
            if cm:
                copilot_apps_set.update(cm.args)
            if cm_x:
                for a in cm_x.args:
                    app_or_apps = self.scheme_config.configured_config_dict.get(a)
                    if isinstance(app_or_apps, list):
                        copilot_apps_set.update(app_or_apps)
                    elif isinstance(app_or_apps, str):
                        copilot_apps_set.add(app_or_apps)
            self.scheme_env.collected_pretest_names.update(lp_helper.names)
            self.scheme_env.collected_pretest_flags.update(lp_helper.flags)
        test_apps_set.update(test_apps_list)
        for app_name in test_apps_set:
            app_info = AppsStaticInfo.get_app_info(app_name)
            app_info.user_args['use_count'] = test_apps_list.count(app_name)
            self.scheme_env.test_apps.append(app_info)
        for app_name in copilot_apps_set:
            self.scheme_env.copilot_apps.append(AppsStaticInfo.get_app_info(app_name))
        if copilot_apps_set:
            if not self.scheme_env.is_copilot_connected:
                self.logger.error_with_tag(
                    f'Found app(s) need to be installed on copilot phone, but NO COPILOT PHONE were found, copilot app list: {copilot_apps_set}',
                    ext_event=True)
        if self.scheme_env.test_apps:
            self.logger.info(f'Pretest Runtime collects these test apps: {self.scheme_env.test_apps}')

    def async_install_apps(self, apps: List[AppsStaticInfo], limit_max_installed_count=0):
        try:
            # 把待测手机加入adb线程忽略池子（用于并发）
            adb.ignored_thread_lock_devices.add(self.scheme_env.device_id)
            # 用于存放 test_apps 中检测到未安装的 app
            failed_installed_app_set = set()
            installed_app_set = set()
            skipped_installed_app_set = set()
            # 锁，用于在多线程环境下安全更新集合
            lock = threading.Lock()
            device_id = self.scheme_env.device_id

            # 尝试安装
            async def try_install(app: AppsStaticInfo, tips: str) -> bool:
                res_provider = self.scheme_env.res_provider
                app_install_provider = self.option_app_installer_class(res_provider, self.u2d_helper.u2d, app.ori_id,
                                                                       app.package)
                with lock:
                    self.logger.info(f'Try install {tips}: {app.ori_id} {app.package}', ext_event=True)
                try:
                    return await app_install_provider.install()
                except Exception:
                    with lock:
                        self.logger.error_with_tag(f'Error on install: {app.ori_id} {app.package}', ext_event=True)
                    return False

            def process_test_app(app: AppsStaticInfo):
                package = app.package

                if 0 < limit_max_installed_count <= len(installed_app_set):
                    skipped_installed_app_set.add(app)
                    return

                if not adb.package_is_installed(device_id, package):
                    install_flag = asyncio.run(try_install(app, "Test App"))
                    if not install_flag:
                        with lock:
                            self.logger.error_with_tag(
                                f'Test App not installed: {app.ori_id} {package}', ext_event=True
                            )
                            failed_installed_app_set.add(app)
                    else:
                        installed_app_set.add(app)
                else:
                    self._grant_all_permissions(False, package)
                    skipped_installed_app_set.add(app)

            # 并行处理 test_apps：将每个 app 的检测和权限赋予任务提交到线程池
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
                futures_test = [executor.submit(process_test_app, app) for app in apps]
                # 等待所有 test_apps 任务完成
                concurrent.futures.wait(futures_test)
            return installed_app_set, failed_installed_app_set, skipped_installed_app_set
        finally:
            # 把待测手机从并发adb线程忽略池子中移除
            adb.ignored_thread_lock_devices.remove(self.scheme_env.device_id)

    def collect_back_apps(self):
        """
        收集背景App
        """
        apps_table = AppsStaticInfo.get_default_table()
        self.scheme_env.back_apps = [apps_table.get_info(app_name) for app_name in self.scheme_config.back_apps]

    def check_installed_apps_and_grant_permissions(self):
        try:
            # 把待测手机加入adb线程忽略池子（用于并发）
            adb.ignored_thread_lock_devices.add(self.scheme_env.device_id)
            # 用于存放 test_apps 中检测到未安装的 app，后续在 back_apps 中排重使用
            already_not_installed_app_package_set = set()
            # 锁，用于在多线程环境下安全更新集合
            lock = threading.Lock()
            device_id = self.scheme_env.device_id

            # 尝试安装
            async def try_install(app: AppsStaticInfo, tips: str) -> bool:
                res_provider = self.scheme_env.res_provider
                app_install_provider = self.option_app_installer_class(res_provider, self.u2d_helper.u2d, app.ori_id, app.package)
                with lock:
                    self.logger.info(f'Try install {tips}: {app.ori_id} {app.package}', ext_event=True)
                try:
                    return await app_install_provider.install()
                except Exception:
                    with lock:
                        self.logger.error_with_tag(f'Error on install: {app.ori_id} {app.package}', ext_event=True)
                    return False

            def process_test_app(app: AppsStaticInfo):
                package = app.package
                if not adb.package_is_installed(device_id, package):
                    install_flag = asyncio.run(try_install(app, "Test App"))
                    if not install_flag:
                        with lock:
                            self.logger.error_with_tag(
                                f'Test App not installed: {app.ori_id} {package}', ext_event=True
                            )
                            already_not_installed_app_package_set.add(package)
                else:
                    self._grant_all_permissions(False, package)
                    # 禁用画中画权限
                    self.u2d_helper.deny_pip_permission(package)

            def process_back_app(app: AppsStaticInfo):
                package = app.package
                if not adb.package_is_installed(device_id, package):
                    with lock:
                        need_install_back_app = (app.package not in already_not_installed_app_package_set)
                    if need_install_back_app:
                        install_flag = asyncio.run(try_install(app, "Back App"))
                        if not install_flag:
                            with lock:
                                self.logger.error_with_tag(
                                    f'Background App not installed: {app.ori_id} {package}', ext_event=True
                                )
    
            # 并行处理 test_apps：将每个 app 的检测和权限赋予任务提交到线程池
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
                futures_test = [executor.submit(process_test_app, app) for app in self.scheme_env.test_apps]
                # 等待所有 test_apps 任务完成
                concurrent.futures.wait(futures_test)

            # 并行处理 back_apps：将每个 app 的检测任务提交到线程池
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
                futures_back = [executor.submit(process_back_app, app) for app in self.scheme_env.back_apps]
                concurrent.futures.wait(futures_back)
        finally:
            # 把待测手机从并发adb线程忽略池子中移除
            adb.ignored_thread_lock_devices.remove(self.scheme_env.device_id)

    def check_installed_apps_and_grant_permissions_copilot(self):
        for app in self.scheme_env.copilot_apps:
            package = app.package
            if not adb.package_is_installed(self.scheme_env.c_device_id, package):
                self.logger.error_with_tag(f'Copilot phone app not installed: {app.ori_id} {package}', ext_event=True)
            else:
                self._grant_all_permissions(True, package)

    def _grant_all_permissions(self, is_copilot: bool, package: str):
        if is_copilot:
            helper = self.c_u2d_helper
        else:
            helper = self.u2d_helper
        helper.grant_all_useful_permissions(package)
