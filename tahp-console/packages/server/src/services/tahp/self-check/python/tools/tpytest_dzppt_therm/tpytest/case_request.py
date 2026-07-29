from datetime import datetime
from functools import cached_property
from typing import Optional

from _pytest.fixtures import FixtureRequest

from powertrde import env
from tpytest.case_original_request import CaseOriginalRequest
from tpytest.case_test_report import CaseTestReport
from tpytest.tpypre.pretest_config_helper import PretestConfigHelper
from tpytest.tpytest_exceptions import CombinedTestException
from tpytest_extends.scheme.apps_static_info import AppsStaticInfo


class CaseRequest:
    def __init__(self, fixture_request: FixtureRequest, case_report: CaseTestReport, retry_index: int):
        self.fixture_request = fixture_request
        self.fixture_request.case_request = self
        self.report = case_report
        self.report.case_request = self
        self.current_phase = 'pre_setup'
        self.current_sub_phase = ''
        self.exception: Optional[Exception] = None
        self.error_phase = ''
        self.error_sub_phase = ''
        self.post_exception: Optional[Exception] = None
        self.post_error_phase = ''
        self._case_config: Optional[dict] = None
        self._pretest_config_helper: Optional[PretestConfigHelper] = None
        self._case_test_apps: Optional[list] = None
        self._case_copilot_apps: Optional[list] = None
        self._case_test_apps_infos: Optional[AppsStaticInfo] = None
        self._case_copilot_apps_infos: Optional[AppsStaticInfo] = None
        self._original_request: Optional[CaseOriginalRequest] = None

        self.report.retry_index = retry_index
        self.report.case_id_no_retry = self.fixture_request.node.nodeid.rsplit("::", 1)[-1]
        self.report.case_id = self.report.case_id_no_retry
        if retry_index > 0:
            if self.original_request.loop_index > 1 or self.original_request.big_loop_index > 1 or self.original_request.dup_index > 1 or self.original_request.group_loop_index > 1:
                self.report.case_id += f'_r{retry_index}'
            else:
                self.report.case_id += f'__r{retry_index}'
        self.report.case_name = self.fixture_request.node.name[5:]

        doc = self.fixture_request.function.__doc__
        if doc:
            self.report.case_desc = doc.strip()
        else:
            self.report.case_desc = ''

    @property
    def test_class_instance(self):
        return self.fixture_request.node.instance

    @property
    def case_class_instance(self):
        return self.test_class_instance.cs

    @property
    def session_life(self):
        return self.case_class_instance.session_life

    def start_report(self):
        self.report.test_id = datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3]
        env_device_info = env.get_user_env_arg('device_info')
        if env_device_info:
            self.report.device_info = env_device_info
        self.report.case_ori_request = self.original_request
        self.report.start_report()

    def end_report(self):
        self.report.end_report()

    def start_test_call(self):
        self.report.start_phase_call()

    def end_test_call(self):
        self.report.end_phase_call()

    @property
    def case_base_node_id(self):
        return self.report.case_id

    @property
    def case_base_node_id_no_retry(self):
        return self.report.case_id_no_retry

    @property
    def case_short_node_id(self):
        return self.case_base_node_id[5:]

    @property
    def case_config(self) -> dict:
        if self._case_config is None:
            m = self.fixture_request.node.get_closest_marker('case_config')
            if m:
                d = m.kwargs
                if d is None:
                    self._case_config = {}
                else:
                    self._case_config = dict(d)
            else:
                self._case_config = {}
        return self._case_config

    @property
    def pretest_config_helper(self) -> PretestConfigHelper:
        if self._pretest_config_helper is None:
            self._pretest_config_helper = PretestConfigHelper(self.fixture_request.node)
        return self._pretest_config_helper

    @property
    def original_request(self) -> Optional[CaseOriginalRequest]:
        if self._original_request is None:
            m = getattr(self.fixture_request.node, 'original_request', None)
            if m:
                self._original_request = m
            else:
                self._original_request = CaseOriginalRequest()
        return self._original_request if self._original_request != 0 else None

    @property
    def case_test_apps(self) -> list:
        if self._case_test_apps is None:
            m = self.fixture_request.node.get_closest_marker('test_app')
            if m:
                self._case_test_apps = m.args
                if self._case_test_apps is None:
                    self._case_test_apps = []
            else:
                self._case_test_apps = []
        return self._case_test_apps

    @property
    def case_test_apps_infos(self):
        if self._case_test_apps_infos is None:
            self._case_test_apps_infos = [AppsStaticInfo.get_app_info(app_name) for app_name in self.case_test_apps]
        return self._case_test_apps_infos

    @property
    def first_test_app(self):
        return self.case_test_apps[0]

    @property
    def first_test_app_info(self):
        return self.case_test_apps_infos[0]

    @property
    def case_copilot_apps(self) -> list:
        if self._case_copilot_apps is None:
            m = self.fixture_request.node.get_closest_marker('copilot_app')
            if m:
                self._case_copilot_apps = m.args
                if self._case_copilot_apps is None:
                    self._case_copilot_apps = []
            else:
                self._case_copilot_apps = []
        return self._case_copilot_apps

    @property
    def case_copilot_apps_infos(self):
        if self._case_copilot_apps_infos is None:
            c_device_sn = env.get_user_env_arg('c_device_sn', '')
            self._case_copilot_apps_infos = [AppsStaticInfo.get_app_info(app_name, variant_device_sn=c_device_sn) for app_name in self.case_copilot_apps]
        return self._case_copilot_apps_infos

    @property
    def first_copilot_app(self):
        return self.case_copilot_apps[0]

    @property
    def first_copilot_app_info(self):
        return self.case_copilot_apps_infos[0]

    @cached_property
    def is_need_copilot(self):
        """
        该用例是否需要辅助机
        """
        return bool(self.case_copilot_apps) or bool(self.fixture_request.node.get_closest_marker('need_copilot')) or self.pretest_config_helper.target == 'copilot'

    @cached_property
    def is_need_observe(self):
        """
        该用例是否需要观测机
        """
        return bool(self.fixture_request.node.get_closest_marker('need_observe'))

    @property
    def is_pass(self):
        return self.report.is_pass

    @property
    def is_skip(self):
        return self.report.is_skip

    @is_skip.setter
    def is_skip(self, value: bool):
        self.report.is_skip = value

    @property
    def is_xfail(self):
        return self.report.is_xfail

    @is_xfail.setter
    def is_xfail(self, value: bool):
        self.report.is_xfail = value

    @property
    def skip_reason(self):
        return self.report.skip_reason

    @skip_reason.setter
    def skip_reason(self, value: str):
        self.report.skip_reason = value

    @property
    def result(self):
        return self.report.test_result

    @result.setter
    def result(self, value: str):
        self.report.test_result = value

    @property
    def case_name(self):
        return self.report.case_name

    @property
    def case_desc(self):
        return self.report.case_desc

    @cached_property
    def case_desc_one_line_with_bracket(self):
        if not self.case_desc:
            return ''
        else:
            return '(' + '; '.join(
                strip_line for strip_line in (line.strip() for line in self.case_desc.split('\n')) if strip_line) + ')'

    @property
    def loop_index(self):
        return self.original_request.loop_index

    @property
    def big_loop_index(self):
        return self.original_request.big_loop_index

    @property
    def group_loop_index(self):
        return self.original_request.group_loop_index

    @property
    def dup_index(self):
        return self.original_request.dup_index

    @property
    def test_id(self):
        return self.report.test_id

    @property
    def retry_index(self):
        return self.report.retry_index

    @property
    def is_retry_test(self):
        return self.report.is_retry_test

    @property
    def is_last_retry(self):
        return self.report.is_last_retry

    @property
    def is_last_small_loop(self):
        return self.report.is_last_small_loop

    @property
    def need_retry_next(self):
        if self.report.test_result != 'fail' and self.report.test_result != 'error':
            return False
        if self.report.is_last_retry:
            return False
        from _pytest.outcomes import XFailed, Skipped
        if isinstance(self.exception, (XFailed, Skipped)):
            return False
        if isinstance(self.exception, CombinedTestException):
            if self.exception.has_exception_type((XFailed, Skipped)):
                return False
        return True

    @property
    def has_remaining_retry_count(self):
        return self.report.has_remaining_retry_count

    @property
    def start_test_time(self):
        return self.report.start_time

    @property
    def end_test_time(self):
        return self.report.end_time
