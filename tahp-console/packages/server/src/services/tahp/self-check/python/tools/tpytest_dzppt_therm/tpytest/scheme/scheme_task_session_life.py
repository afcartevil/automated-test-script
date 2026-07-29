import json
import os
import shutil
from datetime import datetime
from typing import Optional, Dict, Any

from powertrde import env
from powertrde.framework.i18n import I18n
from powertrde.utils import json_utils, misc_utils
from tpytest.task_session_life import TaskSessionLife
from tpytest.test_case_counter import CaseTestInfo


class SchemeTaskSessionLife(TaskSessionLife):
    option_auto_append_cases_to_env_test_counter = True

    def init(self):
        super().init()
        self._session_report.scheme = self.scheme_env.scheme_name

    @property
    def scheme_env(self):
        from tpytest.scheme.scheme_test_env import get_scheme_env
        return get_scheme_env()

    def get_log_dir(self):
        """
        如果重测，都获取的是重测的根目录
        """
        return self.scheme_env.get_log_root_dir()

    def get_log_dir_retest_root(self):
        """
        无论是否重测，都获取最根源的目录
        """
        return self.scheme_env.get_log_root_dir_retest_root()

    def on_session_start(self):
        try:
            if hasattr(self.scheme_env, 'is_short_test_debug') and self.scheme_env.is_short_test_debug:
                warning_msg = (
                    "⚠️  警告：当前正在使用 SHORT_TEST 模式！\n"
                    "   - 测试时长将被大幅缩短\n"
                    "   - 循环次数将被减少\n"
                    "   - 并不能作为正式数据\n"
                    "   - 请确认这是您期望的测试模式"
                )
                warning_msg_en = (
                    "⚠️  Warning: SHORT_TEST mode is currently enabled!\n"
                    "   - The test duration will be significantly shortened\n"
                    "   - The number of loops will be reduced\n"
                    "   - The results should NOT be used as official data\n"
                    "   - Please confirm that this is the test mode you intend to use"
                )
                self.logger.warning(I18n.gen_str(warning_msg_en, warning_msg), ext_event=True)
        except Exception as e:
            self.logger.debug(f"检查 short_test 模式时出现异常: {e}")

        self.session_config.save_last_session_log_root_dir(self.get_log_dir())
        super().on_session_start()

    def on_session_end(self):
        if self.scheme_env.runtime_phase == 'case':
            self.scheme_env.runtime_phase = 'case_phase_teardown'
        super().on_session_end()

    def on_session_report_start(self, start_time: datetime):
        super().on_session_report_start(start_time)
        if self.option_auto_append_cases_to_env_test_counter:
            if (not self.is_bound_cs_class_pretest or self.session_config.is_run_mode_pretest) and self.pytest_session:
                for item in self.pytest_session.items:
                    self.scheme_env.test_counter.case_test_infos.append(CaseTestInfo.from_test_item(item))
                self.scheme_env.test_counter.total_count += len(self.pytest_session.items)

    def run_collector_for_session(self, data_collector, suffix: str, override_params: Optional[Dict[str, Any]] = None):
        self.scheme_env.run_collector_for_session(data_collector, suffix, override_params)

    def gen_node_collect_label_name_for_session(self, suffix: str):
        return self.scheme_env.gen_node_collect_label_name_for_session(suffix)

    def try_write_utp_report_for_end_session(self) -> bool:
        if not super().try_write_utp_report_for_end_session():
            return False

        if not self.is_case_phase_or_task_debugging and not (((self.scheme_env.is_debug_setup_task and not self.scheme_env.runtime_phase.startswith('pretest')) or self.scheme_env.runtime_phase.startswith('case')) and self.session_config.is_run_mode_pretest and self.is_bound_cs_class_pretest):
            return False

        if self.session_config.is_run_mode_single:
            self.write_utp_single_report()
        return True

    def write_utp_single_report(self):
        utp_report_file = self.session_config.utp_report_file
        assert utp_report_file, 'utp_report_file config is empty'
        os.makedirs(os.path.dirname(utp_report_file), exist_ok=True)
        utp_report_dict = {
            'tcid': self.session_config.utp_single_tcid,
            'testCaseName': self.session_config.smart_single_case_path,
            'result': 'Pass' if self.session_report.test_case_counter.pass_rate >= 1 else 'Fail',
            'description': self._gen_utp_single_description()
        }
        json_utils.write_json_file(utp_report_file, [utp_report_dict], indent=None)
        self.logger.info(f'Successfully wrote UTP report to {utp_report_file}')

        # # 把日志拷贝到初始WorkSpace和UTP报告目录，方便UTP进行展示
        # workspace_log_file = os.path.normpath(os.path.join(env.INITIAL_WORKSPACE, 'app.log'))
        #
        # utp_report_file = self.session_config.utp_report_file
        # utp_log_file = None
        # if utp_report_file:
        #     utp_log_file = os.path.normpath(os.path.join(os.path.dirname(utp_report_file), 'app.log'))
        #     if workspace_log_file == utp_log_file:
        #         utp_log_file = None

        utp_log_file = os.path.normpath(os.path.join(os.path.dirname(utp_report_file), 'app.log'))

        try:
            misc_utils.copy_logger_log_file(self.logger.classical_logger, utp_log_file)
        except Exception as e:
            self.logger.error_with_tag(f"Copy current log to UTP PATH '{utp_log_file}' failed, details: {e}")
        else:
            self.logger.info(f'Successfully wrote test log to {utp_log_file}')

        # else:
        #     try:
        #         if utp_log_file and os.path.exists(workspace_log_file):
        #             shutil.copy(workspace_log_file, utp_log_file)
        #     except Exception as e:
        #         self.logger.error_with_tag(f"Copy current log to '{utp_log_file}' failed, details: {e}")

    def _gen_utp_single_description(self):
        desc_dict = {'log_dir': self.get_log_dir()}
        report_dict_array = []
        for report in self._test_reports.values():
            j = report.to_json_dict()
            del j['case_ori_request']
            report_dict_array.append(j)
        desc_dict['case_reports'] = report_dict_array
        return json.dumps(desc_dict)

    def try_export_phone_logs(self, export_bugreports_mode='full'):
        if self.get_phone_logs_zips():
            return
        try:
            self.scheme_env.u2d_helper.export_logs(self.get_phone_logs_dir(), export_bugreports_mode=export_bugreports_mode)
        except Exception as e:
            self.logger.exception(f'try_export_phone_logs error: {e}')
            self.logger.error_with_tag(f'try_export_phone_logs error: {e}', ext_event=True)

    @property
    def is_case_phase_or_task_debugging(self):
        """
        是否正处于正式用例测试阶段或者打开了 'setup_task' debug 模式
        """
        return bool(not self.is_bound_cs_class_pretest and self.scheme_env.is_case_phase_or_debug_setup_task)
