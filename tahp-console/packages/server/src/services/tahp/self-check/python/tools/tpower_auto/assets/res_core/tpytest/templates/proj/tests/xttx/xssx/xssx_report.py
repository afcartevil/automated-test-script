from dataclasses import dataclass, field
from tpytest.case_test_report import CaseTestReport


@dataclass
class XssxReportData:
    mock_value: int = 0
    ...


@dataclass
class XssxReport(CaseTestReport):
    data: XssxReportData = field(default_factory=XssxReportData)
    ...


if __name__ == '__main__':
    ...
