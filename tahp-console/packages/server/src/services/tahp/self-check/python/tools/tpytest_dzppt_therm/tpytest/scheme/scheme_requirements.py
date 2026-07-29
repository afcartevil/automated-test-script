import copy
import os
from functools import cached_property
from typing import List, cast, Optional

from powertrde import env
from powertrde.framework.tran_logger import t_log
from powertrde.utils import requirements_utils, yaml_utils
from powertrde.utils.requirements_utils import InstallRequirementsOptions


class SchemeRequirements:
    def __init__(self, scheme_team: str, scheme_name: str):
        env.try_init_scheme(f'{scheme_team}/{scheme_name}')
        self.scheme = copy.deepcopy(env.scheme)
        self.scheme.config_dict.setdefault('plugins', [])
        self.scheme.config_dict.setdefault('assets', [])
        self.root_dir = env.PROJ_DIR
        self._requirements_paths = None

    @property
    def team_name(self) -> str:
        return self.scheme.team

    @property
    def scheme_name(self) -> str:
        return self.scheme.name

    @property
    def plugins(self):
        return self.scheme.config_dict['plugins']

    @property
    def assets(self):
        return self.scheme.config_dict['assets']

    @cached_property
    def base_config_dict(self):
        return yaml_utils.read_yaml(self.scheme_config_file_path)

    @property
    def assets_paths(self) -> List[str]:
        return cast(List[str], [pt for pt in [os.path.normpath(os.path.join(self.root_dir, p)) for p in self.assets] if
                                os.path.exists(pt)])

    @property
    def plugin_paths(self) -> List[str]:
        return cast(List[str], [pt for pt in [os.path.join(self.root_dir, 'plugins', p) for p in self.plugins] if
                                os.path.exists(pt)])

    @property
    def team_pretests_path(self):
        return os.path.join(self.root_dir, 'pretests', self.team_name)

    @property
    def scheme_pretests_path(self):
        return os.path.join(self.team_pretests_path, self.scheme_name)

    @property
    def team_tests_path(self):
        return os.path.join(self.root_dir, 'tests', self.team_name)

    @property
    def scheme_config_file_path(self):
        return os.path.join(self.root_dir, 'config', self.team_name, self.scheme_name, 'base_config.yaml')

    @property
    def scheme_tests_path(self):
        return os.path.join(self.team_tests_path, self.scheme_name)

    def get_requirements_paths(self, include_win_requirements=None) -> List[str]:
        if self._requirements_paths is not None:
            return self._requirements_paths

        self._requirements_paths = []

        _base_requirements = os.path.join(self.root_dir, 'requirements.txt')
        if os.path.exists(_base_requirements):
            self._requirements_paths.append(_base_requirements)

        _powertrde_requirements = os.path.join(self.root_dir, 'powertrde', 'requirements.txt')
        if os.path.exists(_powertrde_requirements):
            self._requirements_paths.append(_powertrde_requirements)

        if include_win_requirements or (include_win_requirements is None and os.name == 'nt'):
            _base_requirements_win = os.path.join(self.root_dir, 'requirements-win.txt')
            if os.path.exists(_base_requirements_win):
                self._requirements_paths.append(_base_requirements_win)
            _powertrde_requirements_win = os.path.join(self.root_dir, 'powertrde', 'requirements-win.txt')
            if os.path.exists(_powertrde_requirements_win):
                self._requirements_paths.append(_powertrde_requirements_win)

        _tpytest_requirements = os.path.join(self.root_dir, 'tpytest', 'requirements.txt')
        if os.path.exists(_tpytest_requirements):
            self._requirements_paths.append(_tpytest_requirements)

        _team_pretests_requirements = os.path.join(self.team_pretests_path, 'requirements.txt')
        if os.path.exists(_team_pretests_requirements):
            self._requirements_paths.append(_team_pretests_requirements)

        _team_tests_requirements = os.path.join(self.team_tests_path, 'requirements.txt')
        if os.path.exists(_team_tests_requirements):
            self._requirements_paths.append(_team_tests_requirements)

        if os.path.exists(self.scheme_pretests_path):
            self._requirements_paths.append(self.scheme_pretests_path)

        if os.path.exists(self.scheme_tests_path):
            self._requirements_paths.append(self.scheme_tests_path)

        self._requirements_paths.extend(self.plugin_paths)

        return self._requirements_paths

    def check_to_install_scheme_requirements(self, install_options: Optional[InstallRequirementsOptions] = None, raise_if_failed: bool = True):
        _missing_set = self.get_requirements_presence()[1]
        if _missing_set:
            t_log.info(f'Detected uninstalled requirements in the current scheme: {_missing_set}', tag='Requirements', ext_event=True)
            _s = requirements_utils.install_requirements(_missing_set, install_options)
            t_log.info(f'Requirements install finished with result: {_s}', tag='Requirements', ext_event=True)
            if raise_if_failed:
                _fails = _s['failed']
                if _fails:
                    raise Exception(f'Failed to pip install these packages: {_fails}')
            return _s
        return None

    def get_requirements_presence(self):
        return requirements_utils.check_requirements_presence(self.get_requirements_paths(), recursive=True)

    def gen_merged_requirements(self, include_win_requirements=None):
        return requirements_utils.smart_merge_requirements(self.get_requirements_paths(include_win_requirements))


if __name__ == '__main__':
    r = SchemeRequirements('dzppt', 'thm')
    # r.check_to_install_scheme_requirements()
    print(r.gen_merged_requirements(False))
