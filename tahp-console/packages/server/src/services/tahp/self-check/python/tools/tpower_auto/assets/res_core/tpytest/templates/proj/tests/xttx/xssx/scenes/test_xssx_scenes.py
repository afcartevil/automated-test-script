import pytest

from tests.xttx.xssx.xssx_report import XssxReport
from tests.xttx.xssx.scenes.cases_xssx_scenes import CasesXssxScenes
from tests.xttx.xssx.test_xssx import TestXssx


class TestXssxScenes(TestXssx):
    # 设定该测试类绑定的测试用例设计类，该类必须继承自CasesSteps类，用以绑定测试用例步骤
    option_bind_cs_class: type = CasesXssxScenes
    # 设定该类的测试用例运行时打出的Log的前缀
    option_test_log_header: str = 'Test'
    # 设定该类是否自动写入测试报告文件
    option_auto_write_report_file: bool = True
    # 设定该测试类绑定的测试用例报告类，该类必须继承自CaseTestReport类，用以绑定测试用例报告
    option_bind_report_class: type = XssxReport

    @property
    def cs(self) -> CasesXssxScenes:
        return self.get_bound_cs()

    @pytest.mark.test_app('Settings')
    def test_xssx_mock_1(self):
        self.cs.case_xssx_mock_1()

    def test_xssx_mock_2(self):
        self.cs.case_xssx_mock_2()
