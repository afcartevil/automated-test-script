import json
import os
from datetime import datetime
from typing import Optional, Dict, Any

from powertrde import env
from powertrde.utils import json_utils, misc_utils
from tpytest.task_session_life import TaskSessionLife
from tpytest.test_case_counter import CaseTestInfo


class SchemeTaskSessionLife(TaskSessionLife):
    @property
    def scheme_env(self):
        from tpytest.scheme.scheme_test_env import get_scheme_env
        return get_scheme_env()

    def on_session_report_start(self, start_time: datetime):
        super().on_session_report_start(start_time)
        if not self.is_bound_cs_class_pretest and self.pytest_session:
            for item in self.pytest_session.items:
                self.scheme_env.test_counter.case_test_infos.append(CaseTestInfo.from_test_item(item))
            self.scheme_env.test_counter.total_count += len(self.pytest_session.items)

    def run_collector_for_session(self, data_collector, suffix: str, override_params: Optional[Dict[str, Any]] = None):
        self.scheme_env.run_collector_for_session(data_collector, suffix, override_params)

    def gen_node_collect_label_name_for_session(self, suffix: str):
        return self.scheme_env.gen_node_collect_label_name_for_session(suffix)

    def write_session_report_for_end_session(self, update_time: Optional[datetime] = None):
        super().write_session_report_for_end_session(update_time)
        if self.session_config.is_run_mode_utp:
            if self.session_config.is_run_mode_single:
                self.write_utp_single_report()

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

        # 把日志拷贝到初始WorkSpace，方便UTP进行展示
        target_log_path = os.path.join(env.INITIAL_WORKSPACE, 'app.log')
        try:
            misc_utils.copy_logger_log_file(self.logger.classical_logger, target_log_path)
        except Exception as e:
            self.logger.error_with_tag(f"Copy current log to '{target_log_path}' failed, details: {e}")

    def _gen_utp_single_description(self):
        report_dict_array = []
        for report in self._test_reports.values():
            j = report.to_json_dict()
            del j['case_ori_request']
            report_dict_array.append(j)
        return json.dumps(report_dict_array)
