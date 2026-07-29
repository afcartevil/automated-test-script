import os.path

from powertrde.env import PROJ_DIR
from pretests.dzppt.therm.therm_pretest_runtime import ThermPretestRuntime
from tpytest.tpypre.batch_entry import BatchEntry


class ThermBatch(BatchEntry):
    pretest_runtime_class = ThermPretestRuntime
    pretest_exe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'therm_pretest_launcher.py')
    detach_run_executors = True


if __name__ == '__main__':
    os.chdir(PROJ_DIR)
    ThermBatch.get_instance().start()
