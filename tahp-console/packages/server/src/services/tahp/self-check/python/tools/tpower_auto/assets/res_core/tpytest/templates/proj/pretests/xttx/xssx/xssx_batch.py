import os.path

from powertrde.env import PROJ_DIR
from pretests.xttx.xssx.xssx_pretest_runtime import XssxPretestRuntime
from tpytest.tpypre.batch_entry import BatchEntry


class XssxBatch(BatchEntry):
    pretest_runtime_class = XssxPretestRuntime
    pretest_exe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'xssx_pretest_launcher.py')
    detach_run_executors = True


if __name__ == '__main__':
    os.chdir(PROJ_DIR)
    XssxBatch.get_instance().start()
