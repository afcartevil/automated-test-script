import os

from powertrde.env import PROJ_DIR
from pretests.xttx.xssx.xssx_pretest_runtime import XssxPretestRuntime
from tpytest.tpypre.pretest_entry import PretestEntry


class XssxPretest(PretestEntry):
    pretest_runtime_class = XssxPretestRuntime

    def step_1_init_devices_env(self):
        super().step_1_init_devices_env()
        ...

    def step_2_collect_cases(self):
        super().step_2_collect_cases()
        ...

    def step_3_run_pretest_cases(self):
        super().step_3_run_pretest_cases()
        ...

    def step_4_run_test_cases(self):
        super().step_4_run_test_cases()
        ...


if __name__ == '__main__':
    os.chdir(PROJ_DIR)
    XssxPretest.get_instance().start()
