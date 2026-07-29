from dataclasses import dataclass, field, asdict
from datetime import timedelta, datetime
from typing import Optional

from powertrde.framework.interfaces.i_has_device_id import PhoneDeviceInfo
from powertrde.utils.host_utils import HostInfo
from tpytest.test_case_counter import TestCaseCounter


@dataclass
class TaskSessionReport:
    session_id: str = ''
    scheme: str = ''
    host_info: Optional[HostInfo] = None
    timezone_delta: timedelta = field(default_factory=timedelta)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    device_info: PhoneDeviceInfo = field(default_factory=PhoneDeviceInfo)
    test_case_counter: TestCaseCounter = field(default_factory=TestCaseCounter)
    user_data: dict = field(default_factory=dict)
    last_run_case_id: str = ''

    def duration(self, update_time: Optional[datetime] = None):
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        if self.start_time:
            if not update_time:
                update_time = datetime.now()
            return update_time - self.start_time
        return timedelta()

    def to_dict(self, update_time: Optional[datetime] = None):
        if not update_time:
            update_time = datetime.now()
        d = asdict(self)
        d.pop('test_case_counter')
        d['last_update_time'] = update_time.isoformat()
        d['timezone_delta'] = self.timezone_delta.total_seconds()
        if self.start_time:
            d['start_time'] = self.start_time.isoformat()
        if self.end_time:
            d['end_time'] = self.end_time.isoformat()
        d['duration'] = self.duration(update_time).total_seconds()

        d['total_count'] = self.test_case_counter.total_count
        d['finish_count'] = self.test_case_counter.finished_count
        d['pass_count'] = self.test_case_counter.pass_count
        d['fail_count'] = self.test_case_counter.fail_count
        d['finish_rate'] = self.test_case_counter.finished_rate
        d['pass_rate'] = self.test_case_counter.pass_rate
        d['fail_rate'] = self.test_case_counter.fail_rate
        return d
