import sys
import os


def add_path_to_python_env():
    if getattr(sys, 'frozen', False):
        return
    root_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    if root_path not in sys.path:
        sys.path.insert(0, root_path)
    plugins_path = os.path.join(root_path, 'plugins')
    if os.path.exists(plugins_path):
        sys.path.insert(0, plugins_path)


if __name__ == '__main__':
    add_path_to_python_env()
    from powertrde.env import PROJ_DIR
    from pretests.xttx.xssx.xssx_pretest import XssxPretest

    os.chdir(PROJ_DIR)
    XssxPretest.get_instance().start()
