import os
import time
from typing import Optional, List

from powertrde import env
from powertrde.framework.defines import HasHandledException
from powertrde.utils.trde import adb
from tpytest_extends.utils.tests_utils import read_latest_changelogs_version
from powertrde.utils import misc_utils
from tpytest.tpypre.pretest_collectors.app_pretest_collector import AppPretestCollector
from tpytest.tpypre.pretest_collectors.link_pretest_collector import LinkPretestCollector
from tpytest.tpypre.pretest_collectors.pretest_collector import PretestCollector
from tpytest.tpypre.pretest_runtime import PretestRuntime
from tpytest_extends.scheme.apps_static_info import AppsStaticInfo


class PretestEntry:
    _instance = None
    pretest_runtime_class = PretestRuntime

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._env_kwargs = None
        self.pretest_runtime: Optional[PretestRuntime] = None
        self.current_pretest_step = ''
        self.env_pc_pretest_collector: Optional[PretestCollector] = None
        self.env_phone_pretest_collector: Optional[PretestCollector] = None
        self.env_copilot_pretest_collector: Optional[PretestCollector] = None
        self.link_pretest_collector: Optional[LinkPretestCollector] = None
        self.app_pretest_collector: Optional[AppPretestCollector] = None
        self.env_post_phone_pretest_collector: Optional[PretestCollector] = None

    def with_scheme_env_kwargs(self, **kwargs):
        self._env_kwargs = kwargs
        return self

    @property
    def scheme_name(self):
        return self.pretest_runtime.scheme_env.scheme_name

    def start(self):
        self.on_process_start()
        try:
            self.pretest_runtime.scheme_env.try_start_txn_status_dispatcher()
            self.pretest_runtime.scheme_env.runtime_phase = 'checking'
            self.current_pretest_step = self.step_1_init_devices_env.__name__
            self.on_pretest_start()
            self.on_step_start(self.current_pretest_step)
            self.step_1_init_devices_env()
            self.on_step_pass(self.current_pretest_step)

            self.current_pretest_step = self.step_2_collect_cases.__name__
            self.on_step_start(self.current_pretest_step)
            self.step_2_collect_cases()
            self.on_step_pass(self.current_pretest_step)

            self.pretest_runtime.scheme_env.runtime_phase = 'pretest'
            self.current_pretest_step = self.step_3_run_pretest_cases.__name__
            self.on_step_start(self.current_pretest_step)
            self.step_3_run_pretest_cases()
            self.on_step_pass(self.current_pretest_step)
            self.on_pretest_pass()

            if not self.pretest_runtime.scheme_config.is_run_mode_pretest_by_cases:
                self.pretest_runtime.scheme_env.runtime_phase = 'case'
                self.current_pretest_step = self.step_4_run_test_cases.__name__
                self.on_case_test_start()
                self.on_step_start(self.current_pretest_step)
                self.step_4_run_test_cases()
                self.on_step_pass(self.current_pretest_step)
                self.on_case_test_pass()

            self.pretest_runtime.scheme_env.runtime_phase = 'case_phase_end'
            time.sleep(1)
        except Exception as e:
            print(flush=True)
            if isinstance(e, HasHandledException):
                self.pretest_runtime.logger.warning(str(e), ext_event=True)
            else:
                self.pretest_runtime.logger.exception(str(e))
                self.pretest_runtime.logger.error_with_tag(str(e), ext_event=True)
            self.on_step_error(self.current_pretest_step, e)
            if self.current_pretest_step != 'step_4_run_test_cases':
                self.on_pretest_error(e)
            else:
                self.on_case_test_error(e)
            self.on_process_end(e)
        else:
            self.on_process_end(None)

    def on_process_start(self):
        if self._env_kwargs:
            env.get_scheme_shared_kwargs().update(self._env_kwargs)
        self.pretest_runtime = self.pretest_runtime_class.get_instance()
        self.pretest_runtime.scheme_env.send_vm_event('session_log_dir', self.pretest_runtime.logger.base_log_dir)
        self.current_pretest_step = ''
        if not self.pretest_runtime.scheme_env.user_config.is_skip_pretest:
            self.env_pc_pretest_collector = PretestCollector('env.pc.collector', self.pretest_runtime, ['env.pc'])
            self.env_phone_pretest_collector = PretestCollector('env.phone.collector', self.pretest_runtime,
                                                                ['env.phone'])
            self.env_copilot_pretest_collector = PretestCollector('env.copilot.collector', self.pretest_runtime,
                                                                  ['env.copilot'])
            self.link_pretest_collector = LinkPretestCollector('link.collector', self.pretest_runtime, [])
            self.app_pretest_collector = AppPretestCollector('apps.phone.collector', self.pretest_runtime, [])
            self.env_post_phone_pretest_collector = PretestCollector('env.post.phone.collector', self.pretest_runtime, ['env.post.phone'])
            self.pretest_runtime.logger.info(f'※ --------- [{self.scheme_name.upper()} BEGIN] Pretest start! ---------',
                                             ext_event=True)
        self.pretest_runtime.scheme_env.print_log_dir()

    def on_process_end(self, last_exc: Optional[Exception]):
        self.pretest_runtime.scheme_env.print_log_dir()
        if last_exc or self.pretest_runtime.scheme_env.has_error_logs:
            if self.pretest_runtime.scheme_env.runtime_phase.startswith('case'):
                self.pretest_runtime.logger.info(
                    f'※ --------- [{self.scheme_name.upper()} END] Pretests and Tests finished with FAIL. ---------',
                    ext_event=True)
            else:
                self.pretest_runtime.logger.info(
                    f'※ --------- [{self.scheme_name.upper()} END] Pretest result FAIL. ---------',
                    ext_event=True)
        else:
            self.pretest_runtime.logger.info(
                f'※ --------- [{self.scheme_name.upper()} END] Test result PASS. ---------',
                ext_event=True)
        if last_exc:
            self.pretest_runtime.scheme_env.runtime_phase = 'exception_' + self.pretest_runtime.scheme_env.runtime_phase
        self.pretest_runtime.scheme_env.try_stop_txn_status_dispatcher()
        self.stop_usage_stats_sdk()

    def try_start_video_monitor(self):
        if not self.pretest_runtime.scheme_env.has_trunk_flag('auto_start_video_monitor'):
            return
        try:
            self.pretest_runtime.scheme_env.start_video_monitor()
        except Exception:
            pass
        _save_dir = getattr(self.pretest_runtime.scheme_env, '_video_monitor_save_dir', None)
        if not _save_dir:
            self.pretest_runtime.logger.warning('Can not start video monitor, please check the recent warning messages to determine the cause.', ext_event=True)

    def start_usage_stats_sdk(self):
        # 统计sdk开始
        try:
            if not self.pretest_runtime.scheme_config.scheme_release_version == '0.0.0':  # 如果是剪枝后的发布版本
                from usagestats import usage_stats
                tool_key = self.pretest_runtime.scheme_env.nickname
                tool_version = read_latest_changelogs_version(self.pretest_runtime.scheme_env.scheme_name,
                                                              self.pretest_runtime.scheme_env.team_name)
                mobile_model = adb.device_model(self.pretest_runtime.scheme_env.device_id)
                if not (tool_version and tool_key and mobile_model):
                    self.pretest_runtime.logger.warning(
                        f'Usage Stats SDK sending failed; test data was not collected. Current tool_key:{tool_key}, tool_version:{tool_version}, mobile_model:{mobile_model}',
                        ext_event=True)
                else:
                    self.pretest_runtime.logger.info(
                        f'Usage Stats SDK send [tool_key:{tool_key}, tool_version:{tool_version}, mobile_model:{mobile_model}]',
                        ext_event=True)
                    usage_stats.start(tool_key, tool_version, mobile_model)
            else:
                self.pretest_runtime.logger.info(f'should not send data through the Usage Stats SDK', ext_event=True)
        except Exception as e:
            self.pretest_runtime.logger.warning(f'Usage Stats SDK encountered an exception while sending: {str(e)}',
                                                ext_event=True)

    def stop_usage_stats_sdk(self):
        # 统计sdk结束
        try:
            from usagestats import usage_stats
            usage_stats.stop()
        except Exception:
            pass

    def on_step_start(self, step_name: str):
        ...

    def on_step_pass(self, step_name: str):
        ...

    def on_step_error(self, step_name: str, exc: Exception):
        ...

    def on_pretest_start(self):
        ...

    def on_pretest_pass(self):
        ...

    def on_pretest_error(self, exc: Exception):
        ...

    def on_case_test_start(self):
        ...

    def on_case_test_pass(self):
        ...

    def on_case_test_error(self, exc: Exception):
        ...

    

    def check_phone_apps_install(self, test_app_list: List[AppsStaticInfo], back_app_list: List[AppsStaticInfo]):
        self.pretest_runtime.check_installed_apps_and_grant_permissions(False, test_app_list, back_app_list)

    def check_copilot_apps_install(self, app_list: List[AppsStaticInfo]):
        self.pretest_runtime.check_installed_apps_and_grant_permissions(True, app_list, None)

    def check_any_error_tag_log_to_raise(self):
        if self.pretest_runtime.scheme_env.error_tag_logs:
            if self.pretest_runtime.scheme_config.is_run_mode_utp:
                con = self.pretest_runtime.scheme_config
                minimal_reports = []
                json_path = con.utp_report_file
                json_dir = os.path.dirname(json_path)

                # utp 流水线在预测试失败后需要一个报告 full mode
                if con.is_run_mode_utp_full:
                    for i, case in enumerate(con.cases):
                        tcid = case.case_id
                        minimal_reports.append({
                            'tcid': tcid,
                            'testCaseName': "unknown",
                            'result': 'Fail',
                            'sn': con.device_id,
                            'testDate': "unknown",
                            'startTime': "unknown",
                            'endTime': "unknown",
                            'description': f"异常问题导致未正常执行：{self.pretest_runtime.scheme_env.error_tag_logs}",
                        })
                elif con.is_run_mode_utp_single:
                    utp_report_dict = {
                        'tcid': con.utp_single_tcid,
                        'testCaseName': con.smart_single_case_path,
                        'result': 'Fail',
                        'description': f"异常问题导致未正常执行：{self.pretest_runtime.scheme_env.error_tag_logs}"
                    }
                    minimal_reports.append(utp_report_dict)

                if json_dir:
                    os.makedirs(json_dir, exist_ok=True)

                    if minimal_reports:
                        with open(json_path, 'w', encoding='utf-8') as fp:
                            import json
                            json.dump(minimal_reports, fp, ensure_ascii=False, indent=None, default=str)
                        self.pretest_runtime.logger.info(f'[{self.__class__.__name__}] JSON report generated: {json_path}')

                    # 把日志拷贝到UTP路径，方便UTP进行展示
                    target_log_path = os.path.join(str(json_dir), 'app.log')
                    try:
                        misc_utils.copy_logger_log_file(self.pretest_runtime.logger.classical_logger, target_log_path)
                    except Exception as e:
                        self.pretest_runtime.logger.warning(f"Copy current log to '{target_log_path}' failed, details: {e}")

            raise HasHandledException(
                'Due to the aforementioned errors, the pre-test has to be terminated. Please fix these issues first.')

    def step_1_init_devices_env(self):
        self.pretest_runtime.logger.info(
            f'※ --------- [{self.scheme_name.upper()} STEP 1] Now check and prepare pc and devices! ---------',
            ext_event=True)

    def step_2_collect_cases(self):
        if self.pretest_runtime.scheme_env.user_config.is_run_mode_single:
            # 单用例模式
            self.pretest_runtime.logger.info(
                f'※ --------- [{self.scheme_name.upper()} STEP 2] Now collect Single Case! ---------',
                ext_event=True)

            assert self.pretest_runtime.scheme_env.user_config.smart_single_case_path, "Cannot get config 'single_case_path' for single case run mode"
            full_single_path = f'{self.pretest_runtime.scheme_env.scheme_request.scheme_env_class_name_parent_path}/{self.pretest_runtime.scheme_env.user_config.smart_single_case_path}'
            self.pretest_runtime.pre_collect_single_case(full_single_path)
            self.pretest_runtime.collect_single_test_case()
        else:
            self.pretest_runtime.logger.info(
                f'※ --------- [{self.scheme_name.upper()} STEP 2] Now collect Cases and Apps! ---------',
                ext_event=True)
            self.pretest_runtime.pre_collect_all_cases()

            self.pretest_runtime.collect_test_cases_and_apps()
            self.pretest_runtime.collect_back_apps()

            if not self.pretest_runtime.scheme_env.user_config.is_skip_pretest:
                if self.pretest_runtime.scheme_config.run_pc_pretests:
                    self.env_pc_pretest_collector.collect()
                else:
                    self.pretest_runtime.logger.info(
                        f"Will skip collecting PC Pretest Cases because of the run_pc_pretests configuration item has been set to 0.",
                        ext_event=True)

                self.env_phone_pretest_collector.collect()

                if self.pretest_runtime.scheme_env.has_copilot_case:
                    self.env_copilot_pretest_collector.collect()
                else:
                    self.pretest_runtime.logger.info(
                        f'Will skip collecting Copilot Pretest Cases due to NOT COPILOT APP found in TEST CASES.',
                        ext_event=True)

                self.link_pretest_collector.collect()

                if self.pretest_runtime.is_enable_app_pretest:
                    self.app_pretest_collector.collect()
                else:
                    self.pretest_runtime.logger.warning(
                        'The auto collection of app pretest will be skipped because your pretest level is less than 2 or you have forcibly turned off app pretest.',
                        ext_event=True)

                self.env_post_phone_pretest_collector.collect()

    def step_3_run_pretest_cases(self):
        # 启动视频监控
        self.try_start_video_monitor()

        # 启动统计SDK
        self.start_usage_stats_sdk()

        if self.pretest_runtime.scheme_env.user_config.is_skip_pretest:
            self.pretest_runtime.logger.info(
                f'※ --------- [{self.scheme_name.upper()} STEP 3] PRETEST will be skipped due to single case mode or pretest level lower than 0! ---------', ext_event=True)
        else:
            self.pretest_runtime.logger.info(
                f'※ --------- [{self.scheme_name.upper()} STEP 3] Now start PRETEST! ---------', ext_event=True)

            if self.pretest_runtime.scheme_config.run_pc_pretests:
                self.env_pc_pretest_collector.execute()

            self.pretest_runtime.logger.info(f'Now check phone TEST APPS and BACK APPS installation...', ext_event=True)
            self.check_phone_apps_install(self.pretest_runtime.scheme_env.test_apps, self.pretest_runtime.scheme_env.back_apps)

            if self.pretest_runtime.scheme_env.has_copilot_case:
                self.pretest_runtime.logger.info(f'Now check COPILOT phone TEST APPS installation...', ext_event=True)
                assert self.pretest_runtime.scheme_env.c_device_id, f'The COPILOT PHONE requires the case set, but no connected COPILOT was found!'
                self.check_copilot_apps_install(self.pretest_runtime.scheme_env.copilot_apps)

            self.env_phone_pretest_collector.execute()
            if self.pretest_runtime.scheme_env.has_copilot_case:
                self.env_copilot_pretest_collector.execute()
            self.check_any_error_tag_log_to_raise()
            self.link_pretest_collector.execute()
            if self.pretest_runtime.is_enable_app_pretest:
                self.app_pretest_collector.execute()
            self.check_any_error_tag_log_to_raise()
            self.env_post_phone_pretest_collector.execute()
            self.check_any_error_tag_log_to_raise()

    def step_4_run_test_cases(self):
        self.pretest_runtime.logger.info(
            f'※ --------- [{self.scheme_name.upper()} STEP 4] Good! We will start CASE TEST! ---------', ext_event=True)
        # 直接在收集阶段置入 big loop 的设定，这里移除逻辑
        # if self.pretest_runtime.scheme_config.test_loop > 1:
        #     self.pretest_runtime.test_scheduler.apply_scheduled_items_loop(self.pretest_runtime.scheme_config.test_loop)
        _pass_to_pytest_config = {}
        if 'config' in self.pretest_runtime.scheme_env.sys_kwargs:
            _pass_to_pytest_config['config'] = self.pretest_runtime.scheme_env.sys_kwargs['config']
        if 'extra_args' in self.pretest_runtime.scheme_env.sys_kwargs:
            _pass_to_pytest_config['extra_args'] = self.pretest_runtime.scheme_env.sys_kwargs['extra_args']
        self.pretest_runtime.test_scheduler.start(**_pass_to_pytest_config)
