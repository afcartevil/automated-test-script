from tests.dzppt.therm.presets.cases_therm_presets import CasesThermPresets


class CasesThermEnvPresets(CasesThermPresets):
    # ------------------------------------- Below is mock ----------------------------------------

    def pre_therm_mock_1(self):
        ...

    def pre_therm_mock_2(self):
        ...

    def pre_therm_powerhal_encrypt(self):
        """解密power_app_cfg.xml至power_app_cfg_decoded.xml"""
        if self.u2d_helper.tran_cpu_platform == 'mtk':
            self.powerhal_encrypt()

    def pre_therm_policy_encrypt(self):
        """policy策略解密方法"""
        if self.u2d_helper.tran_cpu_platform == 'mtk':
            self.policy_encrypt()
