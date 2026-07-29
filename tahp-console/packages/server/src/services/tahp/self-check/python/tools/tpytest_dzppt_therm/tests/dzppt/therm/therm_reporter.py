import glob
import os.path
from dataclasses import dataclass
from typing import List
import re
from powertrde.utils.excel_report_writer import ExcelTableUnit, title_meta, ExcelTableWriter
from tpytest.test_reporter import TestReporter


@dataclass
class ThermReportUnit(ExcelTableUnit):
    case_name: str = title_meta(default='/', display_name='测试名称', width=64, data_align=('center', 'center'))
    case_data: str = title_meta(default='/', display_name='测试数据', width=64, data_align=('center', 'center'))
    case_result: str = title_meta(default='/', display_name='测试结果', width=12, data_align=('center', 'center'))

    def _on_parse_finished(self, final_source: dict):
        self.case_name = final_source['测试名称']
        self.case_data = final_source['测试数据']
        self.case_result = final_source['测试结果']

class ThermReporter(TestReporter):
    target_scheme = 'therm'
    excel_report_filename: str = 'testReport.xlsx'

    def __init__(self, scheme_runtime_log_dir: str, check_retest_to_merge=False, **kwargs):
        super().__init__(scheme_runtime_log_dir, check_retest_to_merge, **kwargs)
        self.therm_report_units: List[ThermReportUnit] = []

    def remove_illegal_characters(self, data):
        # 过滤掉非法的控制字符（ASCII 范围 0x00-0x1F 除 \t, \n, \r）
        return ''.join(c for c in data if c.isprintable() or c in '\t\n\r')

    def _parse_case_report_units(self):
        super()._parse_case_report_units()
        result_path = glob.glob(os.path.join(self.session_logs_dir, '20*.log'))[0]
        print(result_path)
        with open(result_path, "r", encoding="utf-8") as file:
            log = file.read()

        pattern = re.compile(
            r"===.*?Start.*?(?<=\*\*\*)(.*?)\*\*\*(.*?) - - result：【(.*?)】",
            re.S
        )
        matches = pattern.findall(log)

        source_datas = []
        for match in matches:
            test_result = match[2].strip()
            if test_result.lower() == "true":
                test_result = "pass"
            elif test_result.lower() == "false":
                test_result = "fail"
            source_datas.append({"测试名称": match[0].strip(), "测试数据": match[1].strip() if match[1].strip() else None,
                            "测试结果": test_result})

        for source_data in source_datas:
            unit = ThermReportUnit.parse_from(source_data)
            unit.case_data = self.remove_illegal_characters(unit.case_data)
            self.therm_report_units.append(unit)

    def _on_write_reporter_excel(self, reporter_writer: ExcelTableWriter):
        # 更改保存路径
        reporter_writer.excel_filepath = os.path.join(self.scheme_runtime_log_dir, self.excel_report_filename)
        if os.path.exists(reporter_writer.excel_filepath):
            os.remove(reporter_writer.excel_filepath)

        if self.therm_report_units:
            reporter_writer.write_sheet('report', self.therm_report_units, save_workbook=True)

        super()._on_write_reporter_excel(reporter_writer)


if __name__ == '__main__':
    reporter = ThermReporter(r'D:\dz_auto_env\.runtime\log\20251014_171631_therm_S688LN_153772557A000258')
    reporter.parse_reporter_units()
    reporter.write_reporter_excel()