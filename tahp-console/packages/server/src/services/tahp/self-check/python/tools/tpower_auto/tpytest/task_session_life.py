import glob
import os
from datetime import datetime
from typing import Optional, Callable, Dict, List

import uiautomator2

from powertrde.env import RUNTIME_LOG_DIR
from powertrde.framework.interfaces.i_has_device_id import PhoneDeviceInfo
from powertrde.framework.tran_logger.device_logger import DeviceLogger
from powertrde.framework.tran_logger.log_device import LocalLogDevice, AdbLogDevice, MultiLogDevice
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from powertrde.utils import misc_utils, yaml_utils, host_utils
from tpytest.case_request import CaseRequest
from tpytest.case_test_report import CaseTestReport
from tpytest.task_session_config import TaskSessionConfig
from tpytest.task_session_report import TaskSessionReport
from tpytest.test_case_counter import CaseTestInfo
from tpytest.tpytest_runtime import TPytestRuntime
from tpytest.u2_serial_provider_factory import U2SerialProviderFactory, CopilotU2SerialProviderFactory


class TaskSessionLife:
    on_instance_init: Optional[Callable[['TaskSessionLife'], None]] = None
    _last_known_instance: Optional['TaskSessionLife'] = None

    @classmethod
    def get_last_known_instance(cls):
        return cls._last_known_instance

    def __init__(self):
        super().__init__()
        self.pytest_session = None
        self.setup_case_request: Optional[CaseRequest] = None
        self.session_id_log_report_group_name = ''
        self.session_id_visible_flags = []

        self.has_init_test_classes = {}

        self.bound_test_class: Optional[type] = None
        self.bound_cs_class: Optional[type] = None
        self.enable_auto_write_report_file = False

        self._session_id = ''

        self._session_report = TaskSessionReport()

        self._device_id: Optional[str] = None
        self._device_info: Optional[PhoneDeviceInfo] = None
        self._c_device_id: Optional[str] = None
        self._u2d: Optional[uiautomator2.Device] = None
        self._c_u2d: Optional[uiautomator2.Device] = None
        self.user_obj = {}
        self._session_config: Optional[TaskSessionConfig] = None
        self._logger: Optional[DeviceLogger] = None

        self._test_reports: Dict[str, CaseTestReport] = {}
        self.last_case_request: Optional[CaseRequest] = None

    @property
    def next_case_info(self):
        cur_idx = self.current_case_index
        if cur_idx < len(self.test_case_counter.case_test_infos) - 1:
            return self.test_case_counter.case_test_infos[cur_idx + 1]
        return None

    @property
    def session_config(self):
        if self.tpytest_runtime.current_scheme_env.option_fully_take_over_task_session_life_properties:
            return self.tpytest_runtime.current_scheme_env.user_config

        if self._session_config is None:
            if isinstance(self.tpytest_runtime.current_scheme_env.user_config, TaskSessionConfig):
                self._session_config = self.tpytest_runtime.current_scheme_env.user_config
            else:
                self._session_config = TaskSessionConfig()
        return self._session_config

    @property
    def is_bound_cs_class_pretest(self):
        return bool(self.bound_cs_class and getattr(self.bound_cs_class, 'is_pretest_class', None))

    @property
    def session_start_time(self):
        return self._session_report.start_time

    @property
    def session_end_time(self):
        return self._session_report.end_time

    @session_end_time.setter
    def session_end_time(self, value: datetime):
        self._session_report.end_time = value

    def setup_test_class_if_needed(self, case_request: CaseRequest):
        test_class = type(case_request.test_class_instance)
        if test_class in self.has_init_test_classes:
            return
        cs_class = type(case_request.case_class_instance)
        self.has_init_test_classes[test_class] = cs_class
        cs_class.on_setup_class(self, test_class)

    def update_report(self, report: CaseTestReport):
        self._test_reports[report.case_id] = report

    @property
    def test_case_counter(self):
        return self._session_report.test_case_counter

    @property
    def current_case_index(self):
        return self.test_case_counter.finished_count

    @property
    def test_reports(self):
        return self._test_reports

    @property
    def session_test_duration(self):
        return self._session_report.duration().total_seconds()

    def init(self):
        self._last_known_instance = self
        if self.on_instance_init:
            self.on_instance_init(self)

        self._gen_session_id()

    @property
    def has_init(self):
        return bool(self._session_id)

    @property
    def session_id(self):
        if not self._session_id:
            self._gen_session_id()
        return self._session_id

    def _gen_session_id(self):
        if self.session_config.session_id:
            self._session_id = self.session_config.session_id
        elif TPytestRuntime.get_instance().task_session_id:
            self._session_id = TPytestRuntime.get_instance().task_session_id
        else:
            time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._session_id = time_str
            if self.session_id_log_report_group_name:
                self._session_id += f'_{self.session_id_log_report_group_name}'
            if self.session_id_visible_flags:
                flags_link = '_'.join(self.session_id_visible_flags)
                self._session_id += f'_{flags_link}'
            try:
                if self.device_info.device_model:
                    self._session_id += f'_{self.device_info.device_model}'
            except Exception:
                pass
        return self._session_id

    @property
    def logger(self):
        if self.tpytest_runtime.current_scheme_env.option_fully_take_over_task_session_life_properties:
            return self.tpytest_runtime.current_scheme_env.logger

        if not self._logger:
            if TPytestRuntime.get_instance().task_session_logger:
                self._logger = TPytestRuntime.get_instance().task_session_logger
            else:
                pc_logger = LocalLogDevice(device_name='pc')
                device_logger = AdbLogDevice(device_name='main', device_id=lambda: U2SerialProviderFactory(self))
                c_device_logger = AdbLogDevice(device_name='copilot', device_id=lambda: CopilotU2SerialProviderFactory(self))
                multi_logger = MultiLogDevice(main_device=pc_logger, devices=[device_logger, c_device_logger])
                self._logger = DeviceLogger(log_device=multi_logger,
                                            base_log_dir=self.get_log_dir(),
                                            log_session_id='session_logs')
        return self._logger

    def get_log_dir(self):
        return os.path.join(RUNTIME_LOG_DIR, self.session_id)

    def get_phone_logs_dir(self):
        return os.path.join(self.get_log_dir(), 'phone_logs')

    def get_phone_logs_zips(self) -> List[str]:
        files = glob.glob(os.path.join(self.get_phone_logs_dir(), 'mobile_log*.zip'))
        return files

    def get_session_logs_dir(self):
        return os.path.join(self.get_log_dir(), 'session_logs')

    def get_meta_report_dir(self):
        return os.path.join(self.get_log_dir(), 'meta_report')

    def get_collects_report_dir(self):
        return os.path.join(self.get_meta_report_dir(), 'collects')

    def get_or_gen_meta_report_dir(self):
        return self.try_make_meta_report_dir()

    def try_make_meta_report_dir(self):
        meta_report_dir = self.get_meta_report_dir()
        if not os.path.exists(meta_report_dir):
            os.makedirs(meta_report_dir)
        return meta_report_dir

    @property
    def session_report(self):
        return self._session_report

    def write_session_report_for_in_process(self, update_time: Optional[datetime] = None,
                                            copy_user_config: bool = False):
        meta_report_dir = self.get_meta_report_dir()
        if not os.path.exists(meta_report_dir):
            os.makedirs(meta_report_dir)
        in_process_report_file = os.path.join(meta_report_dir, 'session_process_report.yaml')
        data = self._session_report.to_dict(update_time)
        yaml_utils.write_yaml(data, in_process_report_file)
        if copy_user_config:
            self.tpytest_runtime.current_scheme_env.user_config.write_config_dict_to_file(
                os.path.join(meta_report_dir, 'session_runtime_config.yaml'))

    def write_session_report_for_end_session(self, update_time: Optional[datetime] = None):
        meta_report_dir = self.get_meta_report_dir()
        if not os.path.exists(meta_report_dir):
            os.makedirs(meta_report_dir)
        total_report_file = os.path.join(meta_report_dir, 'session_total_report.yaml')
        data = self._session_report.to_dict(update_time)
        yaml_utils.write_yaml(data, total_report_file)

    def on_session_report_start(self, start_time: datetime):
        self._session_report.start_time = start_time
        self._session_report.host_info = host_utils.get_host_info()
        self._session_report.timezone_delta = misc_utils.get_timezone_delta()
        if self.pytest_session:
            for item in self.pytest_session.items:
                self._session_report.test_case_counter.case_test_infos.append(CaseTestInfo.from_test_item(item))
            self._session_report.test_case_counter.total_count = len(self.pytest_session.items)
        if self.device_info:
            self._session_report.device_info = self.device_info

    def on_session_start(self):
        # sn_log_tag = self.tpytest_runtime.current_scheme_env.sn_log_tag
        # if sn_log_tag:
        #     sn_log_tag = f' with device: {sn_log_tag}'
        self.logger.info(f'※-SESSION-S- [{self.bound_cs_class.__name__}] Test session start',
                         ext_event=True, tag=self.tpytest_runtime.current_scheme_env.sn_log_tag)
        self.on_session_report_start(datetime.now())
        if self.setup_case_request.test_class_instance and self.setup_case_request.test_class_instance.option_auto_write_report_file:
            self.write_session_report_for_in_process(copy_user_config=True)

    def on_session_end(self):
        # sn_log_tag = self.tpytest_runtime.current_scheme_env.sn_log_tag
        # if sn_log_tag:
        #     sn_log_tag = f' with device: {sn_log_tag}'
        self.logger.info(f'※-SESSION-E- [{self.bound_cs_class.__name__}] Test session end',
                         ext_event=True, tag=self.tpytest_runtime.current_scheme_env.sn_log_tag)
        if self.setup_case_request.test_class_instance and self.setup_case_request.test_class_instance.option_auto_write_report_file:
            self.write_session_report_for_end_session()

    @property
    def tpytest_runtime(self):
        return TPytestRuntime.get_instance()

    @property
    def u2d(self):
        if self.tpytest_runtime.current_scheme_env.option_fully_take_over_task_session_life_properties:
            return self.tpytest_runtime.current_scheme_env.u2d

        if self._u2d is not None:
            return self._u2d
        if self.tpytest_runtime.current_scheme_env.device_id == self.device_id:
            self._u2d = self.tpytest_runtime.current_scheme_env.u2d
            if self._u2d:
                return self._u2d
        device_id = self.device_id
        self._u2d = u2utils.connect_u2_device(device_id)
        return self._u2d

    @property
    def c_u2d(self):
        if self.tpytest_runtime.current_scheme_env.option_fully_take_over_task_session_life_properties:
            return self.tpytest_runtime.current_scheme_env.c_u2d

        if self._c_u2d is not None:
            return self._c_u2d
        if self.tpytest_runtime.current_scheme_env.c_device_id == self.c_device_id:
            self._c_u2d = self.tpytest_runtime.current_scheme_env.c_u2d
            if self._c_u2d:
                return self._c_u2d
        c_device_id = self.c_device_id
        self._c_u2d = u2utils.connect_u2_device(c_device_id)
        return self._c_u2d

    @property
    def device_id(self):
        """
        获取测试机的SN或ID。如果没有指定，则尝试获取第一个连接的测试机。
        """
        if self.tpytest_runtime.current_scheme_env.option_fully_take_over_task_session_life_properties:
            return self.tpytest_runtime.current_scheme_env.device_id

        if self._device_id is not None:
            return self._device_id

        sn = self.session_config.device_id

        if not sn:
            sn = self.tpytest_runtime.current_scheme_env.device_id

        # 如果没有传入参数，使用 ADB 获取第一个连接的设备 SN
        if sn is None:
            devices = adb.adb_devices()
            if devices:
                # 如果只有一台那么执行无论是否打开pointer_location都是测试机
                if len(devices) == 1:
                    sn = devices[0]
                else:
                    # 获取第一个没有打开pointer location的机器
                    sn = adb.first_device_isopen_pointer_location(0)
            if not sn:
                raise RuntimeError("No connected test machine detected.")
        self._device_id = sn
        return sn

    @property
    def device_info(self):
        if self.tpytest_runtime.current_scheme_env.option_fully_take_over_task_session_life_properties:
            return self.tpytest_runtime.current_scheme_env.device_info

        if self._device_info:
            return self._device_info
        if not self.device_id:
            return None
        if self.tpytest_runtime.current_scheme_env.device_id == self.device_id:
            try:
                self._device_info = self.tpytest_runtime.current_scheme_env.device_info
            except Exception:
                pass
        if not self._device_info:
            self._device_info = PhoneDeviceInfo(device_id=self.device_id)
        return self._device_info

    @property
    def c_device_id(self):
        """
        获取辅助机的SN或ID。如果没有指定，则尝试获取第一个连接的辅助机。
        """
        if self.tpytest_runtime.current_scheme_env.option_fully_take_over_task_session_life_properties:
            return self.tpytest_runtime.current_scheme_env.c_device_id

        if self._c_device_id is not None:
            return self._c_device_id

        sn = self.session_config.c_device_id

        if not sn:
            sn = self.tpytest_runtime.current_scheme_env.c_device_id

        # 如果没有传入参数，使用 ADB 获取第一个连接的设备 SN
        if sn is None:
            devices = adb.adb_devices()
            if devices:
                # 获取第一个没有打开pointer location的机器
                sn = adb.first_device_isopen_pointer_location(1)
        self._c_device_id = sn
        return sn
