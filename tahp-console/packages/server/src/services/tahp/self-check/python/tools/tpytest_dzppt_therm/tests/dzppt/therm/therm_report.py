from dataclasses import dataclass, field
from tpytest.case_test_report import CaseTestReport


@dataclass
class ThermReportData:
    front_side_tmp: float = 0.0
    back_side_tmp: float = 0.0
    slide_side_tmp: float = 0.0


@dataclass
class ThermReport(CaseTestReport):
    data: ThermReportData = field(default_factory=ThermReportData)
    ...


if __name__ == '__main__':
    ...
