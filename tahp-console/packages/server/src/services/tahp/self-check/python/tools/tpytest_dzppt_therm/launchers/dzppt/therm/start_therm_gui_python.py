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


def check_to_install_requirements(team_name: str, scheme_name: str):
    from tpytest.scheme.scheme_requirements import SchemeRequirements
    from powertrde.utils.requirements_utils import InstallRequirementsOptions
    _sr = SchemeRequirements(team_name, scheme_name)
    _sr.check_to_install_scheme_requirements(InstallRequirementsOptions(index_url='https://pypi.tuna.tsinghua.edu.cn/simple'))


if __name__ == '__main__':
    add_path_to_python_env()
    check_to_install_requirements('dzppt', 'therm')
    from pretests.dzppt.therm.therm_gui import therm_gui_entry

    therm_gui_entry.main()
