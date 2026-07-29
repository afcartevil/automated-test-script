import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional

from powertrde import env
from powertrde.framework.interfaces.i_has_device_id import PhoneDeviceInfo
from powertrde.utils import misc_utils, yaml_utils
from tpytest.case_original_request import CaseOriginalRequest


@dataclass
class CaseTestReport:
    case_ori_request: Optional[CaseOriginalRequest] = None
    retry_index: int = 0
    device_info: PhoneDeviceInfo = field(default_factory=PhoneDeviceInfo)
    test_id: str = ''
    case_id: str = ''
    case_id_no_retry: str = ''
    case_name: str = ''
    case_desc: str = ''
    test_result: str = ''
    is_skip: bool = False
    is_xfail: bool = False
    skip_reason: str = ''
    start_time_through_retry: Optional[datetime] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    call_start_time: Optional[datetime] = None
    call_end_time: Optional[datetime] = None
    error_msg: str = ''
    data = None
    meta_data = None
    error_phase: str = ''
    extra_msg: str = ''
    _case_request = None

    def __str__(self) -> str:
        report = [f"Test ID: {self.test_id}", f"Case ID: {self.case_id}", f"Case Name: {self.case_name}",
                  f"Case Description: {self.case_desc}", f"Device Info: {self.device_info}", f"Retry Index: {self.retry_index}",
                  f"Test Result: {self.test_result}", f"Start Time: {self.start_time}", f"End Time: {self.end_time}",
                  f"Error Message: {self.error_msg}", f"Data: {self.data}", f"Meta Data: {self.meta_data}",
                  f"Extra Message: {self.extra_msg}"]
        return "\n".join(report)

    def __getstate__(self):
        """
        返回一个 dict，作为 pickle 的“状态”。
        在这里把 _case_request 字段剔除，就不会尝试序列化它。
        """
        state = self.__dict__.copy()
        # 跳过不可序列化字段
        if "_case_request" in state:
            del state["_case_request"]
        return state

    @property
    def case_short_id(self):
        return self.case_id[5:]

    @property
    def is_pass(self):
        return self.test_result == 'pass'

    @property
    def is_error_or_fail(self):
        return not self.is_pass

    @property
    def case_request(self):
        return self._case_request

    @case_request.setter
    def case_request(self, value):
        self._case_request = value

    def start_report(self):
        self.start_time = datetime.now()
        if self.start_time_through_retry is None:
            self.start_time_through_retry = self.start_time

    def start_phase_call(self):
        self.call_start_time = datetime.now()

    def end_phase_call(self):
        self.call_end_time = datetime.now()

    def end_report(self):
        self.end_time = datetime.now()

    def append_error_message(self, error_phase: str, msg: str):
        if not self.error_phase:
            self.error_phase = error_phase
        else:
            self.error_phase += ','
            self.error_phase += error_phase

        if not self.error_msg:
            self.error_msg = msg
        else:
            self.error_msg += '|||'
            self.error_msg += msg

    @property
    def test_duration(self):
        if not self.start_time:
            return 0.0
        if not self.end_time:
            return (datetime.now() - self.start_time).total_seconds()
        return (self.end_time - self.start_time).total_seconds()

    @property
    def test_duration_through_retry(self):
        if not self.start_time_through_retry:
            return 0.0
        if not self.end_time:
            return (datetime.now() - self.start_time_through_retry).total_seconds()
        return (self.end_time - self.start_time_through_retry).total_seconds()

    def to_json_dict(self):
        # 将dataclass对象转换为字典
        data_dict = asdict(self)
        # 处理datetime类型为可序列化格式
        if self.start_time:
            data_dict['start_time'] = self.start_time.isoformat()
        if self.end_time:
            data_dict['end_time'] = self.end_time.isoformat()
        if self.call_start_time:
            data_dict['call_start_time'] = self.call_start_time.isoformat()
        if self.call_end_time:
            data_dict['call_end_time'] = self.call_end_time.isoformat()
        if self.start_time_through_retry:
            data_dict['start_time_through_retry'] = self.start_time_through_retry.isoformat()
        if self.end_time and self.start_time:
            data_dict['duration'] = misc_utils.format_seconds_to_time((self.end_time - self.start_time).total_seconds())
        data_dict['is_last_retry'] = self.is_last_retry
        return data_dict

    @property
    def display_id(self):
        return f'{misc_utils.get_digit_time_str(True, self.start_time)}_{self.test_result}_{self.case_id[5:]}'

    @property
    def is_retry_test(self):
        return self.retry_index > 0

    @property
    def is_last_retry(self):
        return self.retry_index >= self.case_ori_request.retry or self.is_skip or self.is_xfail or self.is_pass

    @property
    def is_first_small_loop(self):
        return self.case_ori_request.is_first_small_loop

    @property
    def is_last_small_loop(self):
        return self.case_ori_request.is_last_small_loop

    @property
    def is_first_big_loop(self):
        return self.case_ori_request.is_first_big_loop

    @property
    def is_last_big_loop(self):
        return self.case_ori_request.is_last_big_loop

    @property
    def has_remaining_retry_count(self):
        return self.retry_index < self.case_ori_request.retry

    def get_meta_report_file_path(self, session_life):
        return os.path.join(session_life.get_meta_report_dir(), f'{self.display_id}.yaml')

    def save_unit_report(self, session_life):
        self.save_unit_report_as(self.get_meta_report_file_path(session_life))

    def save_unit_report_as(self, target_path: str):
        units_report_dir = os.path.dirname(target_path)
        if not os.path.exists(units_report_dir):
            os.makedirs(units_report_dir)
        yaml_utils.write_yaml(self.to_json_dict(), target_path, confuse_file=env.is_publish_mode_odm())
