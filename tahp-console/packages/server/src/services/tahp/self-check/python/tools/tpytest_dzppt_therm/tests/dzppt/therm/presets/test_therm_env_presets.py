import pytest

from tests.dzppt.therm.presets.cases_therm_env_presets import CasesThermEnvPresets
from tests.dzppt.therm.presets.test_therm_presets import TestThermPresets


class TestThermEnvPresets(TestThermPresets):
    # 设定该测试类绑定的测试用例设计类，该类必须继承自CasesSteps类，用以绑定测试用例步骤
    option_bind_cs_class: type = CasesThermEnvPresets

    @property
    def cs(self) -> CasesThermEnvPresets:
        return self.get_bound_cs()

    @pytest.mark.pretest_config(target='phone', category='mock', level=0, order=0.0, expiration=None)
    def test_pre_mock_1(self):
        self.cs.pre_therm_mock_1()

    @pytest.mark.pretest_config(target='phone', category='mock', level=0, order=0.0, expiration=None)
    def test_pre_mock_2(self):
        self.cs.pre_therm_mock_2()

    @pytest.mark.pretest_config(target='phone', category='env.phone', level=0, order=0.0, expiration=None)
    def test_pre_therm_powerhal_encrypt(self):
        self.cs.pre_therm_powerhal_encrypt()

    @pytest.mark.pretest_config(target='phone', category='env.phone', level=0, order=0.0, expiration=None)
    def test_pre_therm_policy_encrypt(self):
        self.cs.pre_therm_policy_encrypt()


