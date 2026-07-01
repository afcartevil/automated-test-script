from typing import Optional, List

from powertrde import env
from powertrde.framework.defines import HasHandledException
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

            self.pretest_runtime.scheme_env.runtime_phase = 'case'
            self.current_pretest_step = self.step_4_run_test_cases.__name__
            self.on_case_test_start()
            self.on_step_start(self.current_pretest_step)
            self.step_4_run_test_cases()
            self.on_step_pass(self.current_pretest_step)
            self.on_case_test_pass()
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
            if self.pretest_runtime.scheme_env.runtime_phase == 'case':
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
        self.pretest_runtime.check_installed_apps_and_grant_permissions()

    def check_copilot_apps_install(self, app_list: List[AppsStaticInfo]):
        self.pretest_runtime.check_installed_apps_and_grant_permissions_copilot()

    def check_any_error_tag_log_to_raise(self):
        if self.pretest_runtime.scheme_env.error_tag_logs:
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
            # 普通模式
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

                if self.pretest_runtime.pretest_level >= 2:
                    self.app_pretest_collector.collect()
                else:
                    self.pretest_runtime.logger.warning(
                        f'Will skip collecting App Pretest Cases due to your pretest level {self.pretest_runtime.pretest_level} less than 2',
                        ext_event=True)

                self.env_post_phone_pretest_collector.collect()

    def step_3_run_pretest_cases(self):
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
                self.check_copilot_apps_install(self.pretest_runtime.scheme_env.copilot_apps)

            self.env_phone_pretest_collector.execute()
            if self.pretest_runtime.scheme_env.has_copilot_case:
                self.env_copilot_pretest_collector.execute()
            self.check_any_error_tag_log_to_raise()
            self.link_pretest_collector.execute()
            if self.pretest_runtime.pretest_level >= 2:
                self.app_pretest_collector.execute()
            self.check_any_error_tag_log_to_raise()
            self.env_post_phone_pretest_collector.execute()
            self.check_any_error_tag_log_to_raise()

    def step_4_run_test_cases(self):
        self.pretest_runtime.logger.info(
            f'※ --------- [{self.scheme_name.upper()} STEP 4] Good! We will start CASE TEST! ---------', ext_event=True)
        if self.pretest_runtime.scheme_config.test_loop > 1:
            self.pretest_runtime.test_scheduler.apply_scheduled_items_loop(self.pretest_runtime.scheme_config.test_loop)
        self.pretest_runtime.test_scheduler.start(**self.pretest_runtime.scheme_env.sys_kwargs)
