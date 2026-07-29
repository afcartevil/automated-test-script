import concurrent.futures
import sys
import threading
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any, Union

import pytest

from powertrde.utils import algorithm_utils
from powertrde.utils.trde import adb
from tpytest.case_original_request import CaseOriginalRequest
from tpytest.scheme.scheme_test_env import get_scheme_env
from tpytest.scheme.scheme_user_config import SchemeUserConfig
from tpytest.tpypre.link_pretest_helper import LinkPretestHelper
from tpytest_extends.scheme.apps_static_info import AppsStaticInfo
from tpytest.preset_recorder import PresetRecorder
from tpytest.tpytest_scheduler import TPytestTestScheduler, ScheduledOrderItem


class PretestRuntime:
    _instance = None

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

        self.test_scheduler = TPytestTestScheduler([], [test_range], request_group_query_pool=self._gen_request_group_query_pool(), default_small_loop=self.scheme_config.small_test_loop, default_retry=self.scheme_config.retry, default_timeout=self.scheme_config.test_case_timeout)
        self._pretest_pre_collected_items = None
        self._pc_pretest_pass_recorder = None
        self._pc_pretest_pass_node = None
        self._phone_pretest_pass_recorder = None
        self._phone_pretest_pass_node = None
        self._copilot_pretest_pass_recorder = None
        self._copilot_pretest_pass_node = None

    def _gen_request_group_query_pool(self) -> Dict[str, List[str]]:
        _ret = {}
        for k, v in self.scheme_config.configured_config_dict.items():
            if k.startswith('case_group_'):
                _ret[k] = v
        return _ret

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
                record_method(case_name.lower())

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

    @property
    def is_enable_app_pretest(self):
        return self.scheme_config.is_enable_app_pretest

    def record_search_box_pos_y(self, pos_y: float):
        self.scheme_env.create_main_recorder_node().record('search_box_pos_y', pos_y / self.scheme_env.u2d.window_size()[1])

    def record_az_pos(self, pos:tuple[float,float]):
        self.scheme_env.create_main_recorder_node().record("az_pos",(pos[0]/self.scheme_env.u2d.window_size()[0],pos[1] / self.scheme_env.u2d.window_size()[1]))

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
        case_ori_request.parse_from('*', self.scheme_config.small_test_loop, self.scheme_config.retry, self.scheme_config.test_case_timeout)
        self.test_scheduler.case_ori_requests.append(case_ori_request)
        self.test_scheduler.generate_schedule()
        self.scheme_env.test_cases = list(self.test_scheduler.scheduled_order_items)

    def collect_test_cases_and_apps(self):
        """
        收集测试用例
        """
        self.test_scheduler.case_ori_requests.clear()
        self.test_scheduler.clear_scheduled_items()
        if self.scheme_config.is_run_mode_utp_full:
            self.test_scheduler.case_ori_requests.extend(self.scheme_config.smart_utp_full_case_paths)
        else:
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

        # 如果是复测模式，从收集到的用例中删除之前已经测试通过的用例
        _no_big_loop_cases_dict: Optional[Dict[str, ScheduledOrderItem]] = None
        _no_big_loop_cases: Optional[List[ScheduledOrderItem]] = None

        if self.scheme_env.retests_combiner:
            if self.scheme_config.test_loop > 1:
                self.test_scheduler.apply_scheduled_items_loop(self.scheme_config.test_loop)

            new_items = []
            all_ids, pass_ids, fail_ids = self.scheme_env.retests_combiner.get_all_pass_fail_case_ids()
            for i in self.test_scheduler.scheduled_order_items:
                if i.case_id in fail_ids or i.case_id not in all_ids:
                    new_items.append(i)
            self.test_scheduler.scheduled_order_items.clear()
            self.test_scheduler.scheduled_order_items.extend(new_items)

            if not self.test_scheduler.scheduled_order_items:
                raise Exception('No test cases requiring retesting were found, testing will be skipped!\n没有发现任何需要复测的用例，将跳过测试！')

            _no_big_loop_cases_dict = {}
            for _tc in self.test_scheduler.scheduled_order_items:
                _no_big_loop_cases_dict.setdefault(_tc.full_case_id_no_big_loop, _tc)
        else:
            _no_big_loop_cases = list(self.test_scheduler.scheduled_order_items)
            if self.scheme_config.test_loop > 1:
                self.test_scheduler.apply_scheduled_items_loop(self.scheme_config.test_loop)

        self.scheme_env.test_cases = self.test_scheduler.scheduled_order_items

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

        for v in (_no_big_loop_cases or _no_big_loop_cases_dict.values()):
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

    def collect_back_apps(self):
        """
        收集背景App
        """
        apps_table = AppsStaticInfo.get_default_table()
        self.scheme_env.back_apps = [apps_table.get_info(app_name) for app_name in self.scheme_config.back_apps]

    def check_installed_apps_and_grant_permissions(self, target_on_copilot: bool, test_apps: Union[None, List[AppsStaticInfo]], back_apps: Union[None, List[AppsStaticInfo]]):
        device_id = self.scheme_env.c_device_id if target_on_copilot else self.scheme_env.device_id
        _u2d_helper = self.c_u2d_helper if target_on_copilot else self.u2d_helper
        device_marker_store = self.scheme_env.c_device_marker_store if target_on_copilot else self.scheme_env.device_marker_store
        try:
            # 把待测手机加入adb线程忽略池子（用于并发）
            adb.ignored_thread_lock_devices.add(device_id)
            # 用于存放 test_apps 中检测到未安装的 app，后续在 back_apps 中排重使用
            already_not_installed_app_package_set = set()
            # 锁，用于在多线程环境下安全更新集合
            lock = threading.Lock()

            user_config: SchemeUserConfig = self.scheme_env.user_config

            need_app_pretest = user_config.is_enable_app_pretest
            pretest_level = user_config.pretest_level

            if need_app_pretest:
                exclude_flag = 0
            else:
                if pretest_level >= 2:
                    exclude_flag = 0
                elif pretest_level >= 1:
                    exclude_flag = 4
                else:
                    exclude_flag = 6

            test_app_install_configs = {
                'is_check_app_install': user_config.is_check_apps_install(is_copilot=target_on_copilot, is_background_app=False, exclude_flag=exclude_flag),
                'is_install_app': user_config.is_check_to_install_apps(is_copilot=target_on_copilot, is_background_app=False, exclude_flag=exclude_flag),
                'is_update_app_version': user_config.is_check_to_update_apps(is_copilot=target_on_copilot, is_background_app=False, exclude_flag=exclude_flag),
                'is_grant_useful_permissions': user_config.is_check_to_grant_apps_all_permissions(is_copilot=target_on_copilot, is_background_app=False, exclude_flag=exclude_flag),
                'install_options': ('-r', '-g', '-t')
            }

            back_app_install_configs = {
                'is_check_app_install': user_config.is_check_apps_install(is_copilot=target_on_copilot, is_background_app=True, exclude_flag=exclude_flag),
                'is_install_app': user_config.is_check_to_install_apps(is_copilot=target_on_copilot, is_background_app=True, exclude_flag=exclude_flag),
                'is_update_app_version': user_config.is_check_to_update_apps(is_copilot=target_on_copilot, is_background_app=True, exclude_flag=exclude_flag),
                'is_grant_useful_permissions': user_config.is_check_to_grant_apps_all_permissions(is_copilot=target_on_copilot, is_background_app=True, exclude_flag=exclude_flag),
                'install_options': ('-r', '-g', '-t')
            }

            app_install_configs = {
                'Test': test_app_install_configs,
                'Background': back_app_install_configs
            }

            _device_nickname = 'Copilot Phone' if target_on_copilot else 'Test Phone'

            def _grant_permissions_and_mark_login_suggest(package: str):
                try:
                    _result = _u2d_helper.grant_all_runtime_permissions(package)
                    _total = _result.get('total_runtime_permissions', 0)
                    _granted = _result.get('granted_count', 0)
                    _granted_rate = 0.0
                    if _total > 0:
                        _granted_rate = _granted / _total
                    if _granted_rate > 0.5:
                        with lock:
                            device_marker_store.upgrade_login_suggest_level(package, 1)
                            device_marker_store.clear_login_mark(package)

                except Exception as e:
                    self.logger.warning(f'{_device_nickname} grant permissions error: {e}')

            # 尝试安装
            def try_install(app: AppsStaticInfo, app_type_nickname: str) -> Tuple[bool, int, Any]:
                app_type_config = app_install_configs[app_type_nickname]

                if not app_type_config['is_install_app']:
                    return False, -1, 'User configure as not require install'

                _is_update_app = app_type_config['is_update_app_version'] and not app.no_update
                _text_update_or_install = 'update' if _is_update_app else 'install'

                app_install_provider = None
                app_install_provider_fail_reason = ''
                try:
                    app_install_provider = self.scheme_env.create_app_installer(device_id, app, _is_update_app, install_options=app_type_config['install_options'])
                except Exception as e:
                    app_install_provider_fail_reason = str(e)

                if app_install_provider is None:
                    return False, -2, f'Apk install provider instantiation failed: {app_install_provider_fail_reason}'

                with lock:
                    self.logger.info(f'{_device_nickname} try {_text_update_or_install} {app_type_nickname} App: {app.ori_id} {app.package}', tag=device_id, ext_event=True)
                try:
                    _result_msg = app_install_provider.install()
                    _notes = ''
                    _result = ''
                    _is_skipped = False
                    _is_updated = False
                    if isinstance(_result_msg, dict):
                        _is_skipped = _result_msg.get('action') == 'skipped'
                        _is_installed = _result_msg.get('action') == 'installed'
                        try:
                            _version_before = int(_result_msg['device_before']['version_code'])
                            assert _version_before > 0
                            _version_after = int(_result_msg['device_after']['version_code'])
                            _is_updated = _is_installed and _version_before < _version_after
                        except Exception:
                            pass
                        _result_bool = _is_skipped or _is_installed
                        _result_code = (-3 if _is_skipped else 0) if _result_bool else 1

                        _notes = _result_msg.get('notes', 'null')
                        _notes = f' | Details: {_notes}'
                    else:
                        _result_bool = bool(_result_msg)
                        _result_code = 0 if _result_bool else 1

                        if _result_bool:
                            _result = 'SUCCESSFULLY'

                    if _is_skipped:
                        _result = 'SKIP'
                        _log_func = self.logger.info
                    elif _result_bool:
                        _result = 'SUCCESSFULLY'
                        _log_func = self.logger.info
                    else:
                        _result = 'FAILED'
                        _log_func = self.logger.error_with_tag

                    with lock:
                        _log_func(
                            f'{_device_nickname} {_result} {_text_update_or_install} {app_type_nickname} App: {app.ori_id} {app.package}{_notes}',
                            tag=device_id, ext_event=True)
                        # 如果安装成功（并且不是升级或跳过），则推荐后续执行登录（写入标签）
                        if _result_bool and not _is_updated and not _is_skipped:
                            device_marker_store.upgrade_login_suggest_level(app.package, 2)
                            device_marker_store.clear_login_mark(app.package)

                    return _result_bool, _result_code, _result_msg
                except Exception as e:
                    with lock:
                        self.logger.error_with_tag(f'{_device_nickname} occurs error on install: {app.ori_id} {app.package}', tag=device_id, ext_event=True)
                    return False, 2, e

            def process_app(app: AppsStaticInfo, app_type_nickname: str):
                if app.id == 'launcher':
                    return

                app_type_config = app_install_configs[app_type_nickname]
                _is_update_app = app_type_config['is_update_app_version'] and not app.no_update

                package = app.package
                _ori_installed = adb.package_is_installed(device_id, package)
                if _is_update_app or not _ori_installed:
                    _result_bool, _result_code, _result_msg = try_install(app, app_type_nickname)
                    if not _result_bool:
                        with lock:
                            # 判断是否为 Google 应用
                            _is_google_app = package.startswith('com.google.android.') or package.startswith('com.android.vending') or package.startswith('com.android.chrome')

                            if _result_code < 0:
                                if _is_google_app:
                                    self.logger.warning(
                                        f'{_device_nickname} {app_type_nickname} App failed (Google App): {app.ori_id} {package}, reason: {_result_msg}. Please try to install/update manually from Google Play Store.',
                                        tag=device_id, ext_event=True
                                    )
                                else:
                                    self.logger.error_with_tag(
                                        f'{_device_nickname} not installed {app_type_nickname} App: {app.ori_id} {package}, will not install this app with reason: {_result_msg}', tag=device_id, ext_event=True
                                    )
                            else:
                                if _ori_installed:
                                    _t_install_or_update = 'UPDATE'
                                else:
                                    _t_install_or_update = 'INSTALL'

                                # Google 应用安装/更新失败时使用警告,非 Google 应用使用错误
                                if _is_google_app:
                                    self.logger.warning(
                                        f'{_device_nickname} {_t_install_or_update} {app_type_nickname} App failed (Google App): {app.ori_id} {package}, reason: {_result_msg}. Please try to install/update manually from Google Play Store.',
                                        tag=device_id, ext_event=True
                                    )
                                else:
                                    self.logger.error_with_tag(
                                        f'{_device_nickname} {_t_install_or_update} {app_type_nickname} App failed: {app.ori_id} {package}, reason: {_result_msg}', tag=device_id, ext_event=True
                                    )
                            already_not_installed_app_package_set.add(package)
                    else:
                        if app_type_config['is_grant_useful_permissions']:
                            if _result_code < 0:
                                # 跳过的情况下，需要重新赋予所有权限
                                _grant_permissions_and_mark_login_suggest(package)
                                _u2d_helper.grant_common_high_level_permissions(package)
                            else:
                                # 非跳过的情况下，仅需要赋权高级权限
                                _u2d_helper.grant_common_high_level_permissions(package)
                            # 禁用画中画权限
                            _u2d_helper.deny_pip_permission(package)
                elif _ori_installed:
                    if app_type_config['is_grant_useful_permissions']:
                        # 重新赋予所有权限
                        _grant_permissions_and_mark_login_suggest(package)
                        _u2d_helper.grant_common_high_level_permissions(package)
                        # 禁用画中画权限
                        _u2d_helper.deny_pip_permission(package)

            def process_task(apps: list, app_type_nickname: str):
                app_type_config = app_install_configs[app_type_nickname]
                if apps and (app_type_config['is_check_app_install'] or app_type_config['is_grant_useful_permissions']):
                    if app_type_config['is_update_app_version']:
                        self.logger.info(f'Now will check and UPDATE all {app_type_nickname} Apps: {apps}', tag=device_id, ext_event=True)
                    elif app_type_config['is_install_app']:
                        self.logger.info(f'Now will check and INSTALL all {app_type_nickname} Apps: {apps}', tag=device_id, ext_event=True)
                    elif app_type_config['is_check_app_install']:
                        self.logger.info(f'Now will check all {app_type_nickname} Apps installation: {apps}', tag=device_id, ext_event=True)

                    if app_type_config['is_grant_useful_permissions']:
                        self.logger.info(f'Now also will grant all {app_type_nickname} Apps permissions...', tag=device_id, ext_event=True)

                    # 并行处理 test_apps：将每个 app 的检测和权限赋予任务提交到线程池
                    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
                        futures_test = [executor.submit(process_app, app, app_type_nickname) for app in apps]
                        # 等待所有 test_apps 任务完成
                        concurrent.futures.wait(futures_test)

            # 发起并发检测前，首先更新global_index，利用缓存机制，防止并发多次下载该文件
            self.scheme_env.try_update_app_repo_index()
            process_task(test_apps, 'Test')
            process_task(back_apps, 'Background')

        finally:
            # 把待测手机从并发adb线程忽略池子中移除
            adb.ignored_thread_lock_devices.remove(device_id)

    def _grant_all_permissions(self, is_copilot: bool, package: str):
        if is_copilot:
            helper = self.c_u2d_helper
        else:
            helper = self.u2d_helper
        helper.grant_all_useful_permissions(package)

    # --------------------------------- Legacy Methods --------------------------------

    def legacy_check_installed_apps_and_grant_permissions(self):
        from tpytest_extends.utils.app_installer import AppInstallerForProvider
        import asyncio

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
                app_install_provider = AppInstallerForProvider(res_provider, device_id, app.ori_id, app.package)
                with lock:
                    self.logger.info(f'Try install {tips}: {app.ori_id} {app.package}', ext_event=True)
                try:
                    return await app_install_provider.install()
                except Exception:
                    with lock:
                        self.logger.error_with_tag(f'Error on install: {app.ori_id} {app.package}', ext_event=True)
                    return False

            def process_test_app(app: AppsStaticInfo):
                if app.id == 'launcher':
                    return

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
                if app.id == 'launcher':
                    return

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

    def legacy_check_installed_apps_and_grant_permissions_copilot(self):
        for app in self.scheme_env.copilot_apps:
            package = app.package
            if not adb.package_is_installed(self.scheme_env.c_device_id, package):
                self.logger.error_with_tag(f'Copilot phone app not installed: {app.ori_id} {package}', ext_event=True)
            else:
                self._grant_all_permissions(True, package)
