import glob
import os.path
import re
from dataclasses import field, dataclass
from datetime import timedelta, datetime
from functools import cached_property
from typing import List, Any

from powertrde.framework.tran_logger import t_log
from powertrde.utils import yaml_utils, misc_utils
from powertrde.utils.excel_report_writer import ExcelTableUnit, title_meta, ExcelTableWriter
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
    error_msg: str = title_meta(default='', display_name='Error Msg', width=10)

    filepath: str = ''
    step_report_units: List[CaseStepReporterUnit] = field(default_factory=list)

    def _on_parse_finished(self, final_source: dict):
        self.result = final_source.get('test_result', '')
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
    sn: str = title_meta(default='', display_name='SN', width=18)
    brand: str = title_meta(default='', display_name='Brand', width=7)
    model: str = title_meta(default='', display_name='Model', width=7)
    rom: str = title_meta(default='', display_name='ROM', width=35)
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

    def _on_parse_field(self, filed_name: str, source_value: Any) -> bool:
        if filed_name == 'timezone_delta':
            self.timezone_delta = timedelta(seconds=source_value)
            return True
        elif filed_name == 'duration':
            self.duration = misc_utils.format_seconds_to_time(source_value)
            return True
        return False

    def _on_parse_finished(self, final_source: dict):
        self.start_time = self.start_time.replace('T', ' ')
        self.end_time = self.end_time.replace('T', ' ')

        device_info = final_source.get('device_info', {})
        self.sn = device_info.get('device_sn', '')
        self.brand = device_info.get('device_brand', '')
        self.model = device_info.get('device_model', '')
        self.rom = device_info.get('device_rom_version', '')
        if not self.end_time or self.end_time == 'null':
            self.end_time = device_info.get('last_update_time', '')

    def update_from_case_reports(self, case_reports: List[CaseReporterUnit]):
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

    def __init__(self, scheme_runtime_log_dir: str):
        super().__init__()
        assert self.target_scheme, 'Target Scheme must be set in your own TestReporter class!'
        self.scheme_runtime_log_dir = scheme_runtime_log_dir
        self.case_meta_reports_files: List[str] = []
        self.case_meta_reports_dicts: List[dict] = []
        self.session_total_report_dict = None
        self.session_runtime_config_dict = None
        self.session_process_report_dict = None
        self.case_meta_reporter_units: List[CaseReporterUnit] = []
        self.summary_reporter_unit = None
        self._try_load_session_summary_reports()
        self._collect_case_meta_reports_files()

    @classmethod
    def get_scheme_last_log_dir(cls):
        return get_last_runtime_log_dir(cls.target_scheme)

    @property
    def is_session_completed(self):
        return bool(self.session_total_report_dict)

    @cached_property
    def meta_report_dir(self):
        return os.path.join(self.scheme_runtime_log_dir, 'meta_report')

    @cached_property
    def session_logs_dir(self):
        return os.path.join(self.scheme_runtime_log_dir, 'session_logs')

    @cached_property
    def excel_report_filepath(self):
        return os.path.join(self.meta_report_dir, self.excel_report_filename)

    def parse_reporter_units(self):
        """
        开始解析汇报者
        """
        self._parse_case_report_units()
        self._parse_summary_report_unit()

    @property
    def has_monitor_steps(self):
        try:
            return bool(self.case_meta_reports_dicts[0]['data']['monitor_step_datas'])
        except Exception:
            return False

    def _on_write_reporter_excel(self, reporter_writer: ExcelTableWriter):
        if self.summary_reporter_unit:
            reporter_writer.write_sheet('Summary', [self.summary_reporter_unit], save_workbook=False)

        reporter_writer.write_sheet('Cases', self.case_meta_reporter_units, save_workbook=False)
        if self.has_monitor_steps:
            step_units = []
            for u in self.case_meta_reporter_units:
                step_units.extend(u.step_report_units)
            reporter_writer.write_sheet('Steps', step_units, save_workbook=False)

    def write_reporter_excel(self):
        assert self.case_meta_reporter_units, 'Can not write excel report when there is not any case meta report.'
        reporter_writer = ExcelTableWriter(self.excel_report_filepath)
        self._on_write_reporter_excel(reporter_writer)
        reporter_writer.save()

    def _collect_case_meta_reports_files(self):
        self.case_meta_reports_files.clear()
        search_pattern = os.path.join(self.meta_report_dir, f'*_{self.target_scheme}_*.yaml')
        for file_path in glob.glob(search_pattern):
            d = yaml_utils.read_yaml(file_path)
            if d:
                d['filepath'] = file_path
            else:
                t_log.error(f'Meta report file "{os.path.basename(file_path)}" load failed!')
                continue

            if self.only_collect_last_retry_cases:
                if not d.get('is_last_retry', True):
                    continue
            self.case_meta_reports_files.append(file_path)
            self.case_meta_reports_dicts.append(d)
        self.case_meta_reports_files.sort(key=lambda x: os.path.basename(x))
        self.case_meta_reports_dicts.sort(key=lambda x: os.path.basename(x['filepath']))

    def _try_load_session_summary_reports(self):
        self.session_total_report_dict = yaml_utils.read_yaml(
            os.path.join(self.meta_report_dir, 'session_total_report.yaml'))
        self.session_runtime_config_dict = yaml_utils.read_yaml(
            os.path.join(self.meta_report_dir, 'session_runtime_config.yaml'))
        self.session_process_report_dict = yaml_utils.read_yaml(
            os.path.join(self.meta_report_dir, 'session_process_report.yaml'))

    def _parse_case_report_units(self):
        self.case_meta_reporter_units.clear()
        if not self.case_reporter_class or not self.case_meta_reports_dicts:
            return
        for d in self.case_meta_reports_dicts:
            self.case_meta_reporter_units.append(self.case_reporter_class.parse_from(d))

    def _parse_summary_report_unit(self):
        self.summary_reporter_unit = None
        if not self.summary_reporter_class:
            return
        report_dict = self.session_total_report_dict or self.session_process_report_dict
        assert report_dict, 'Can not load any of total report or process report file!'
        self.summary_reporter_unit = self.summary_reporter_class.parse_from(report_dict)
        self.summary_reporter_unit.update_from_case_reports(self.case_meta_reporter_units)
