import pytest

from tests.xttx.xssx.presets.cases_xssx_presets import CasesXssxPresets
from tests.xttx.xssx.test_xssx import TestXssx
from tpytest.pretest_mix_in import TestPretestMixIn


class TestXssxPresets(TestXssx, TestPretestMixIn):
    # 设定该测试类绑定的测试用例设计类，该类必须继承自CasesSteps类，用以绑定测试用例步骤
    option_bind_cs_class: type = CasesXssxPresets
    # 设定该类的测试用例运行时打出的Log的前缀
    option_test_log_header: str = 'Pretest'
    # 设定该类是否自动写入测试报告文件
    option_auto_write_report_file: bool = False
    # 设定该测试类绑定的测试用例报告类，该类必须继承自CaseTestReport类，用以绑定测试用例报告
    option_bind_report_class: type = None

    @property
    def cs(self) -> CasesXssxPresets:
        return self.get_bound_cs()

    @pytest.mark.pretest_config(target='phone', category='mock', level=0, order=0.0, expiration=None)
    def test_pre_xssx_mock_1(self):
        self.cs.pre_xssx_mock_1()

    @pytest.mark.pretest_config(target='phone', category='mock', level=0, order=0.0, expiration=None)
    def test_pre_xssx_mock_2(self):
        self.cs.pre_xssx_mock_2()
