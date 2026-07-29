import glob
import json
import os.path
from dataclasses import field, dataclass
from datetime import timedelta, datetime
from functools import cached_property
from typing import List, Any, Optional

from powertrde import env
from powertrde.framework.tran_logger import t_log
from powertrde.utils import yaml_utils, misc_utils
from powertrde.utils.excel_report_writer import ExcelTableUnit, title_meta, ExcelTableWriter
from powertrde.utils.feishu.utp_api_helper import UTPApiHelper
from powertrde.utils.window_utils import UnclosableWindow
from tpytest_extends.utils import tests_utils
from tpytest_extends.utils.tests_utils import get_last_runtime_log_dir


@dataclass
class CaseStepReporterUnit(ExcelTableUnit):
    test_id: str = title_meta(default='', display_name='Test ID', width=19)
    case_id: str = title_meta(default='', display_name='Case ID', width=28)
    case_name: str = title_meta(default='', display_name='Case Name', width=20)
    case_desc: str = title_meta(default='', display_name='Case Desc', width=36)
    step_name: str = title_meta(default='', display_name='Step Name', width=20)
    step_depth: int = title_meta(default=0, display_name='Step Depth', width=4)
    start_time: str = title_meta(default='', display_name='Start Time', width=28)
    end_time: str = title_meta(default='', display_name='End Time', width=28)
    duration: float = title_meta(default=0.0, display_name='Duration', width=9)
    result: str = title_meta(default='', display_name='Result', width=7)
    error_msg: str = title_meta(default='', display_name='Error Msg', width=10)

    def _on_parse_finished(self, final_source: dict):
        self.result = final_source.get('test_result', '')
        self.start_time = self.start_time.replace('T', ' ')
        self.end_time = self.end_time.replace('T', ' ')


@dataclass
class CaseReporterUnit(ExcelTableUnit):
    case_step_report_class: type = CaseStepReporterUnit

    test_id: str = title_meta(default='', display_name='Test ID', width=19)
    case_id: str = title_meta(default='', display_name='Case ID', width=28)
    case_name: str = title_meta(default='', display_name='Case Name', width=20)
    case_desc: str = title_meta(default='', display_name='Case Desc', width=36)
    start_time: str = title_meta(default='', display_name='Start Time', width=28)
    end_time: str = title_meta(default='', display_name='End Time', width=28)
    duration: str = title_meta(default='', display_name='Duration', width=9)
    result: str = title_meta(default='', display_name='Result', width=7)
    source: int = title_meta(default=0, display_name='Source', width=7)
    retry_index: int = title_meta(default=0, display_name='Retry Index', width=11)
    last_retry: int = title_meta(default=0, display_name='Last Retry', width=10)
    error_msg: str = title_meta(default='', display_name='Error Msg', width=10)

    case_id_no_retry: str = ''
    filepath: str = ''
    step_report_units: List[CaseStepReporterUnit] = field(default_factory=list)

    def _on_parse_finished(self, final_source: dict):
        if not self.case_id_no_retry:
            self.case_id_no_retry = self.case_id

        self.result = final_source.get('test_result', '')
        self.last_retry = 1 if final_source.get('is_last_retry', True) else 0
        self.start_time = self.start_time.replace('T', ' ')
        self.end_time = self.end_time.replace('T', ' ')

        self.step_report_units.clear()
        if not self.case_step_report_class:
            return

        monitor_data = final_source.get('data', {}).get('monitor_step_datas')
        if not monitor_data:
            return
        temp_dict = dict(final_source)
        temp_dict['step_name'] = ''
        temp_dict['step_depth'] = 0
        root_step = dict(temp_dict)

        for m in monitor_data:
            temp_dict.update(m)
            temp_dict['step_depth'] = m.get('step_name', '').count('/') + 1
            temp_dict['error_msg'] = m.get('error_message', '')
            temp_dict['duration'] = misc_utils.format_seconds_to_time(m.get('duration', 0.0))
            self.step_report_units.append(self.case_step_report_class.parse_from(temp_dict))

        self.step_report_units.append(self.case_step_report_class.parse_from(root_step))


@dataclass
class CaseSummaryReporter(ExcelTableUnit):
    source: str = title_meta(default='Merged', display_name='Source', width=7)
    session_id: str = title_meta(default='', display_name='ID', width=7)
    scheme: str = title_meta(default='', display_name='Scheme', width=8)
    sn: str = title_meta(default='', display_name='SN', width=18)
    brand: str = title_meta(default='', display_name='Brand', width=8)
    model: str = title_meta(default='', display_name='Model', width=8)
    rom: str = title_meta(default='', display_name='ROM', width=46)
    start_time: str = title_meta(default='', display_name='Start Time', width=28)
    end_time: str = title_meta(default='', display_name='End Time', width=28)
    duration: str = title_meta(default='', display_name='Duration', width=9)
    total_count: int = title_meta(default=0, display_name='Total Count', width=12)
    finish_count: int = title_meta(default=0, display_name='Finish Count', width=13)
    finish_rate: float = title_meta(default=0.0, display_name='Finish Rate', width=12)
    pass_count: int = title_meta(default=0, display_name='Pass Count', width=12)
    fail_count: int = title_meta(default=0, display_name='Fail Count', width=11)
    pass_rate: float = title_meta(default=0.0, display_name='Pass Rate', width=10)

    timezone_delta: timedelta = field(default_factory=timedelta)
    gap_time_to_pc: float = 0.0
    filepath: str = ''

    def _on_parse_field(self, filed_name: str, source_value: Any) -> bool:
        if filed_name == 'timezone_delta':
            self.timezone_delta = timedelta(seconds=source_value)
            return True
        elif filed_name == 'duration':
            self.duration = misc_utils.format_seconds_to_time(source_value)
            return True
        return False

    @staticmethod
    def starts_with_timestamp_strict(s: Any) -> bool:
        """
        严格检测：先按格式截取前 16 字符（YYYYMMDD_HHMMSS_），
        再用 datetime.strptime 验证年月日时分秒是否合法（例如不允许 20250230）。
        """
        if not isinstance(s, str):
            return False
        # 必须至少 16 个字符：YYYYMMDD_HHMMSS_
        if len(s) < 16:
            return False
        # 前 15 个字符用来做 datetime 解析： "YYYYMMDD_HHMMSS"
        dt_part = s[:15]  # 索引 0..14，共 15 个字符
        sep_char = s[15]  # 第 16 个字符，应当是 '_'
        if sep_char != '_':
            return False
        try:
            datetime.strptime(dt_part, "%Y%m%d_%H%M%S")
            return True
        except ValueError:
            return False

    def _on_parse_finished(self, final_source: dict):
        if not self.session_id and self.filepath:
            try:
                dir_base_name = os.path.basename(os.path.dirname(os.path.dirname(self.filepath)))
                if self.starts_with_timestamp_strict(dir_base_name):
                    self.session_id = dir_base_name
            except Exception:
                pass

        if not self.scheme and self.filepath:
            try:
                dir_base_name = os.path.basename(os.path.dirname(os.path.dirname(self.filepath)))
                if self.starts_with_timestamp_strict(dir_base_name):
                    _ss = dir_base_name.split('_', maxsplit=4)
                    if len(_ss) >= 3:
                        self.scheme = _ss[2]
            except Exception:
                pass

        # 首先检查并设置end_time
        device_info = final_source.get('device_info', {})
        if not self.end_time or self.end_time == 'null':
            self.end_time = device_info.get('last_update_time', '')

        # 确保end_time不为None后再调用replace
        self.start_time = self.start_time.replace('T', ' ')
        if self.end_time:
            self.end_time = self.end_time.replace('T', ' ')

        self.sn = device_info.get('device_sn', '')
        self.brand = device_info.get('device_brand', '')
        self.model = device_info.get('device_model', '')
        self.rom = device_info.get('device_rom_version', '')

    def update_from_case_reports(self, case_reports: List[CaseReporterUnit]):
        if case_reports:
            self.start_time = case_reports[0].start_time
            self.end_time = case_reports[-1].end_time
            self.duration = misc_utils.format_seconds_to_time(
                (datetime.fromisoformat(self.end_time.replace(' ', 'T')) - datetime.fromisoformat(
                    self.start_time.replace(' ', 'T'))).total_seconds())


class TestReporter:
    target_scheme: str = ''
    excel_report_filename: str = 'testReport.xlsx'
    case_reporter_class: type = CaseReporterUnit
    summary_reporter_class: type = CaseSummaryReporter
    only_collect_last_retry_cases: bool = False
    _in_parsing_reporters: list = []

    @staticmethod
    def get_current_parsing_reporter() -> 'TestReporter':
        if not TestReporter._in_parsing_reporters:
            raise Exception('No TestReporter is performing parsing!')
        return TestReporter._in_parsing_reporters[-1]

    def __init__(self, scheme_runtime_log_dir: str, check_retest_to_merge=False, **kwargs):
        super().__init__()

        if not self.target_scheme:
            overwrite_target_scheme = kwargs.get('target_scheme')
            if overwrite_target_scheme:
                self.target_scheme = overwrite_target_scheme

        assert self.target_scheme, 'Target Scheme must be set in your own TestReporter class!'

        self.scheme_runtime_log_dir = scheme_runtime_log_dir
        self.need_merge_retest = False
        if check_retest_to_merge:
            self._check_to_correct_retest_root_dir()

        self._meta_report_dir = None
        self._try_overwrite_meta_report_dir_name = kwargs.get('try_overwrite_meta_report_dir_name')
        self.case_meta_reports_files: List[str] = []
        self.case_meta_reports_dicts: List[dict] = []
        self.session_total_report_path = None
        self.session_runtime_config_path = None
        self.session_process_report_path = None
        self.session_total_report_dict = None
        self.session_runtime_config_dict = None
        self.session_process_report_dict = None
        self.case_meta_reporter_units: List[CaseReporterUnit] = []
        self.summary_reporter_unit = None
        self.summary_reporter_units = []
        self._reports_combiner = None
        self._temp_scheme_env = None
        self._runtime_config = None

    @classmethod
    def get_runtime_config_type(cls):
        raise NotImplementedError(
            'Please implement this method in the subclass (returns your scheme config class type)')

    @classmethod
    def get_scheme_env_type(cls):
        raise NotImplementedError('Please implement this method in the subclass (returns your scheme env class type)')

    @property
    def runtime_config(self):
        if self.session_runtime_config_path is None:
            raise Exception('Please call "parse_reporter_units" first!')
        if self._runtime_config is None:
            scheme_request = env.Scheme()
            scheme_request.try_init(f'{env.DEFAULT_TEAM_NAME}/{self.target_scheme}')
            self._runtime_config = self.get_runtime_config_type().create(config_path=self.session_runtime_config_path, scheme_request=scheme_request)
        return self._runtime_config

    @property
    def temp_scheme_env(self):
        if self._temp_scheme_env is None:
            self._temp_scheme_env = self.get_scheme_env_type().create(specific_user_config=self.runtime_config)
        return self._temp_scheme_env

    def _check_to_correct_retest_root_dir(self):
        _new_dir, _dir_changed, _has_retests = tests_utils.check_to_correct_retest_root_dir(self.scheme_runtime_log_dir)
        self.need_merge_retest = _has_retests
        if _dir_changed:
            t_log.info(
                f'[{self.__class__.__name__}] Detected that the target folder "{self.scheme_runtime_log_dir}" you passed in is a RETEST or SUB REPORT folder, it will be automatically converted to the report root folder "{_new_dir}".',
                ext_event=True)
            self.scheme_runtime_log_dir = _new_dir

    def merge_retests(self):
        t_log.info(f'[{self.__class__.__name__}] Merging retest reports from root: {self.scheme_runtime_log_dir}',
                   ext_event=True)
        from tpytest.reports_combiner import ReportsCombiner, ReportMergeMode
        self._reports_combiner = ReportsCombiner(self.target_scheme, self.scheme_runtime_log_dir,
                                                 merge_mode=ReportMergeMode.PassRelace, search_retests=True,
                                                 test_reporter_class=self.__class__)
        self._reports_combiner.parse_report_processors()
        self._reports_combiner.merge_reports()
        self._reports_combiner.merge_write_files()

    @staticmethod
    def is_report_dir_available(report_dir: str):
        a = os.path.join(report_dir, 'meta_report', 'session_process_report.yaml')
        if os.path.exists(a):
            return True
        b = os.path.join(report_dir, 'session_process_report.yaml')
        if os.path.exists(b):
            return True
        return False

    @staticmethod
    def resolve_meta_report_dir(root_path: str, try_overwrite_meta_report_dir_name: Optional[str] = None):
        if try_overwrite_meta_report_dir_name:
            _m = os.path.join(root_path, try_overwrite_meta_report_dir_name)
            if os.path.isdir(_m):
                _meta_report_dir = _m
                return _meta_report_dir

        _m = os.path.join(root_path, 'meta_report')
        if os.path.isdir(_m):
            _meta_report_dir = _m
        else:
            _meta_report_dir = root_path
        return _meta_report_dir

    @classmethod
    def get_scheme_last_log_dir(cls):
        return get_last_runtime_log_dir(cls.target_scheme)

    @property
    def is_session_completed(self):
        return bool(self.session_total_report_dict)

    @cached_property
    def meta_report_dir(self):
        if self._meta_report_dir is None:
            self._meta_report_dir = self.resolve_meta_report_dir(self.scheme_runtime_log_dir,
                                                                 self._try_overwrite_meta_report_dir_name)
        return self._meta_report_dir

    @cached_property
    def session_logs_dir(self):
        return os.path.join(self.scheme_runtime_log_dir, 'session_logs')

    @cached_property
    def get_log_dir_retest_root(self):
        """
        无论是否重测，都获取最根源的目录,返回的是20251014_202637_psm2_CN5C_1571225581000199结尾的目录
        """
        runtime_log_dir, _dir_changed, _has_retests = tests_utils.check_to_correct_retest_root_dir(self.scheme_runtime_log_dir)
        return runtime_log_dir

    @cached_property
    def excel_report_filepath(self):
        return os.path.join(self.meta_report_dir, self.excel_report_filename)

    def parse_reporter_units(self):
        """
        开始解析汇报者
        """
        self._runtime_config = None
        self._temp_scheme_env = None

        try:
            TestReporter._in_parsing_reporters.append(self)

            if self.need_merge_retest:
                self.merge_retests()

            self._try_load_session_summary_reports()
            self._collect_case_meta_reports_files()
            self._parse_case_report_units()
            self._parse_summary_report_unit()
        finally:
            TestReporter._in_parsing_reporters.pop()

    @property
    def has_monitor_steps(self):
        try:
            return bool(self.case_meta_reports_dicts[0]['data']['monitor_step_datas'])
        except Exception:
            return False

    def _on_write_reporter_excel(self, reporter_writer: ExcelTableWriter):
        """当写入报告时"""
        if self.summary_reporter_units:
            reporter_writer.write_sheet('Summary', self.summary_reporter_units, save_workbook=False)

        reporter_writer.write_sheet('Cases', self.case_meta_reporter_units, save_workbook=False)
        if self.has_monitor_steps:
            step_units = []
            for u in self.case_meta_reporter_units:
                step_units.extend(u.step_report_units)
            reporter_writer.write_sheet('Steps', step_units, save_workbook=False)

    def _on_save_reporter_excel(self, reporter_writer: ExcelTableWriter):
        reporter_writer.save()

    def write_reporter_excel(self):
        assert self.case_meta_reporter_units, 'Can not write excel report when there is not any case meta report.'

        reporter_writer = ExcelTableWriter(self.excel_report_filepath)

        try:
            TestReporter._in_parsing_reporters.append(self)
            self._on_write_reporter_excel(reporter_writer)
            self._on_save_reporter_excel(reporter_writer)
        finally:
            TestReporter._in_parsing_reporters.pop()

        try:
            self._after_write_reporter_excel()
        finally:
            t_log.info(f'[{self.__class__.__name__}] Successfully write excel report to: {reporter_writer.excel_filepath}',
                       ext_event=True)

    def _after_write_reporter_excel(self):
        pass

    def generate_utp_data_local(self, json_path):
        """
        生成 放到本地文件夹下的json文件, utp自取， 流水线可用。要在excel报告生成（write_reporter_excel）后调用
        """
        try:
            utp_data_items = self._build_utp_local_data()

            json_dir = os.path.dirname(json_path) if json_path else self.excel_report_filepath + '\\report.json'
            if json_dir:
                os.makedirs(json_dir, exist_ok=True)

            with open(json_path, 'w', encoding='utf-8') as fp:
                json.dump(utp_data_items, fp, ensure_ascii=False, indent=None, default=str)

            t_log.info(f'[{self.__class__.__name__}] JSON report generated: {json_path}')
        except Exception as e:
            t_log.error(f'[{self.__class__.__name__}] JSON report generation failed: {e}')

    def _build_utp_local_data(self):
        """
        构建 UTP 数据项的抽象方法，子类必须实现此方法。
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _build_utp_data_items() method"
        )

    def generate_utp_data_upload(self):
        """
        生成需要上传的 UTP 格式的数据， 手动上传可用，要在excel报告生成（write_reporter_excel）后调用
        """
        utp = UTPApiHelper('679d854d', 'e521b58beebf4f509a847c151a0b9a79')
        # task_id = get_utp_taskid_manual_window()
        task_id = self.session_runtime_config_dict.get("task_id", "")
        if not task_id:
            return
        run_mode = self.session_runtime_config_dict.get("run_mode", "")
        # tcids, project这两个参数可以做校验
        if run_mode == 'utp/full':
            tcids, project = '', 'utp/full'
        else:
            tcids, project = utp._get_tcids_and_project(task_id)
        # bizno是唯一的批次号，为了避免同一个数据重复上传。如果有多轮，则需要多个批次号。
        bizno, _utp_data_power, _utp_data_perf = self._build_utp_data_items(task_id, tcids, project)
        if bizno:
            with UnclosableWindow("Upload Reports Logs",
                                  f"There are/is {len(bizno)} round of data. Uploading reports to UTP, please wait...\n当前有{len(bizno)}轮数据，正在上传UTP，请等待..."):
                for i in range(len(bizno)):
                    try:
                        utp._upload_utp(bizno[i] + self.target_scheme + 'power', _utp_data_power[i])
                    except Exception as e:
                        t_log.info(
                            f'power数据没有上传成功，可能是任务下发没有Power任务。与测试无关，测试人员可以不关注:{e}')
                    try:
                        utp._upload_utp(bizno[i] + self.target_scheme + 'perf', _utp_data_perf[i])
                    except Exception as e:
                        t_log.info(
                            f'perf数据没有上传成功，可能是任务下发没有Perf任务。与测试无关，测试人员可以不关注:{e}')

    def _build_utp_data_items(self, task_id, tcids, project):
        """
        构建 UTP 数据项的抽象方法，子类必须实现此方法。
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _build_utp_data_items() method"
        )

    def _collect_case_meta_reports_files(self):
        self.case_meta_reports_files.clear()
        test_id_to_d = {}
        search_pattern = os.path.join(self.meta_report_dir, f'*_{self.target_scheme}_*.yaml')
        for file_path in glob.glob(search_pattern):
            d = yaml_utils.read_yaml(file_path)
            if d:
                _dk = (d['test_id'], d['retry_index'])
                if _dk in test_id_to_d:
                    continue

                d['filepath'] = file_path
                test_id_to_d[_dk] = d
            else:
                t_log.error(f'Meta report file "{os.path.basename(file_path)}" load failed!')
                continue

            if self.only_collect_last_retry_cases:
                if not d.get('is_last_retry', True):
                    continue

        for d in test_id_to_d.values():
            self.case_meta_reports_files.append(d['filepath'])
            self.case_meta_reports_dicts.append(d)

        self.case_meta_reports_files.sort(key=lambda x: os.path.basename(x))
        self.case_meta_reports_dicts.sort(key=lambda x: os.path.basename(x['filepath']))

    def _try_load_session_summary_reports(self):
        self.session_total_report_path = os.path.join(self.meta_report_dir, 'session_total_report.yaml')
        self.session_total_report_dict = yaml_utils.read_yaml(self.session_total_report_path)
        if self.session_total_report_dict:
            self.session_total_report_dict['filepath'] = self.session_total_report_path

        self.session_process_report_path = os.path.join(self.meta_report_dir, 'session_process_report.yaml')
        self.session_process_report_dict = yaml_utils.read_yaml(self.session_process_report_path)
        if self.session_process_report_dict:
            self.session_process_report_dict['filepath'] = self.session_process_report_path

        self.session_runtime_config_path = os.path.join(self.meta_report_dir, 'session_runtime_config.yaml')
        self.session_runtime_config_dict = yaml_utils.read_yaml(self.session_runtime_config_path)

    def _parse_case_report_units(self):
        """当解析所有收集到的报告单元时（多个）"""
        self.case_meta_reporter_units.clear()
        if not self.case_reporter_class or not self.case_meta_reports_dicts:
            return
        for d in self.case_meta_reports_dicts:
            self.case_meta_reporter_units.append(self.case_reporter_class.parse_from(d))

    @property
    def summary_report_dict(self) -> Optional[dict]:
        return self.session_total_report_dict or self.session_process_report_dict

    def _parse_summary_report_unit(self):
        """当解析汇总报告单元时（单个）"""
        self.summary_reporter_unit = None
        self.summary_reporter_units.clear()
        if not self.summary_reporter_class:
            return
        report_dict = self.summary_report_dict
        assert report_dict, 'Can not load any of total report or process report file!'

        self.summary_reporter_unit = self.summary_reporter_class.parse_from(report_dict)
        self.summary_reporter_unit.update_from_case_reports(self.case_meta_reporter_units)
        self.summary_reporter_units.append(self.summary_reporter_unit)

        if self._reports_combiner:
            for _rp in self._reports_combiner.report_processors:
                self.summary_reporter_units.extend(_rp.test_reporter.summary_reporter_units)
