import copy
import os.path
import shutil
from typing import List, cast

from powertrde import env
from powertrde.env import RES_CORE_DIR
from powertrde.utils import yaml_utils
from tpytest.scheme import scheme_template_creator


class SchemePublisher:
    def __init__(self, scheme_team: str, scheme_name: str, publish_version: str):
        env.try_init_scheme(f'{scheme_team}/{scheme_name}')
        self.publish_version = publish_version
        self.scheme = copy.deepcopy(env.scheme)
        self.scheme.config_dict.setdefault('plugins', [])
        self.scheme.config_dict.setdefault('assets', [])
        self.root_dir = env.PROJ_DIR
        self._merge_assets()

    @property
    def team_name(self) -> str:
        return self.scheme.team

    @property
    def scheme_name(self) -> str:
        return self.scheme.name

    @property
    def pack_path(self):
        return os.path.join(self.root_dir, f'tpytest_{self.scheme.team}_{self.scheme.name}')

    @property
    def plugins(self):
        return self.scheme.config_dict['plugins']

    @property
    def assets(self):
        return self.scheme.config_dict['assets']

    @property
    def assets_paths(self) -> List[str]:
        return cast(List[str], [pt for pt in [os.path.normpath(os.path.join(self.root_dir, p)) for p in self.assets] if
                                os.path.exists(pt)])

    @property
    def plugin_paths(self) -> List[str]:
        return cast(List[str], [pt for pt in [os.path.join(self.root_dir, 'plugins', p) for p in self.plugins] if
                                os.path.exists(pt)])

    def _merge_assets(self):
        for plugin_path in self.plugin_paths:
            plugin_yaml = os.path.join(plugin_path, 'plugin.yaml')
            if os.path.exists(plugin_yaml):
                plugin_yaml_dict = yaml_utils.read_yaml(plugin_yaml)
                if plugin_yaml_dict:
                    for a in plugin_yaml_dict.get('assets', []):
                        plugin_a = f'assets/res_plugins/{a}'
                        if plugin_a not in self.assets:
                            self.assets.append(plugin_a)

    @staticmethod
    def copy2(src, dst):
        """
        复制单个文件（使用 self.copy2），如果目标路径的上级目录不存在，则自动创建。

        :param src: 源文件路径
        :param dst: 目标文件路径（含文件名）
        """
        if not os.path.isfile(src):
            raise FileNotFoundError(f"源文件不存在: {src}")

        dst_dir = os.path.dirname(dst)
        if dst_dir and not os.path.exists(dst_dir):
            os.makedirs(dst_dir)

        shutil.copy2(src, dst)

    @staticmethod
    def copy_all_files(src_dir: str, dst_dir: str):
        """
        将 src_dir 下所有非目录文件拷贝到 dst_dir 下。
        - 如果 dst_dir 不存在，则自动创建；
        - 若遇同名文件，直接覆盖。
        """
        if not os.path.isdir(src_dir):
            return

        os.makedirs(dst_dir, exist_ok=True)

        for item in os.listdir(src_dir):
            src_path = os.path.join(src_dir, item)
            dst_path = os.path.join(dst_dir, item)
            if os.path.isfile(src_path):  # 只处理文件，忽略目录
                shutil.copy2(src_path, dst_path)

    def _process_scheme_struct_folder(self, folder_name: str):
        pack_path = self.pack_path
        folder_path = os.path.join(self.root_dir, folder_name)
        self.copy_all_files(folder_path, pack_path + folder_path[len(self.root_dir):])
        team_folder_path = os.path.join(folder_path, self.team_name)
        self.copy_all_files(team_folder_path, pack_path + team_folder_path[len(self.root_dir):])
        scheme_folder_path = os.path.join(team_folder_path, self.scheme_name)
        shutil.copytree(scheme_folder_path, pack_path + scheme_folder_path[len(self.root_dir):],
                        ignore=shutil.ignore_patterns('__pycache__'))

    def process(self):
        pack_path = self.pack_path
        if os.path.exists(pack_path):
            shutil.rmtree(pack_path)
        # os.makedirs(pack_path)

        # 处理root launchers
        src_launchers = os.path.join(RES_CORE_DIR, 'tpytest', 'templates', 'root_launchers')
        pairs = [('xttx', self.team_name), ('xssx', self.scheme_name)]
        scheme_template_creator.directly_main(src_launchers, self.pack_path, pairs)

        if not os.path.exists(os.path.join(self.root_dir, 'launchers', self.team_name, self.scheme_name, f'start_{self.scheme_name}_gui_python.py')):
            os.remove(os.path.join(self.pack_path, f'start_env_{self.scheme_name}_gui.bat'))
            os.remove(os.path.join(self.pack_path, f'start_embed_{self.scheme_name}_gui.bat'))

        # 写入version
        if self.publish_version:
            with open(os.path.join(self.pack_path, f'{self.scheme_name}_version.txt'), 'w') as f:
                f.write(self.publish_version)

        # 处理 基础框架
        shutil.copytree(os.path.join(self.root_dir, 'tpytest'), os.path.join(pack_path, 'tpytest'),
                        ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(os.path.join(self.root_dir, 'powertrde'), os.path.join(pack_path, 'powertrde'),
                        ignore=shutil.ignore_patterns('__pycache__'))
        self.copy2(os.path.join(self.root_dir, 'requirements.txt'), os.path.join(pack_path, 'requirements.txt'))
        self.copy2(os.path.join(self.root_dir, 'requirements-win.txt'),
                     os.path.join(pack_path, 'requirements-win.txt'))
        self.copy2(os.path.join(self.root_dir, 'setup_tpytest.py'), os.path.join(pack_path, 'setup_tpytest.py'))
        self.copy2(os.path.join(self.root_dir, '.gitignore'), os.path.join(pack_path, '.gitignore'))
        self.copy2(os.path.join(self.root_dir, '.gitmodules'), os.path.join(pack_path, '.gitmodules'))

        # 处理 config
        self._process_scheme_struct_folder('config')

        # 处理 assets
        shutil.copytree(os.path.join(self.root_dir, 'assets', 'res_core'),
                        os.path.join(pack_path, 'assets', 'res_core'))

        scheme_assets_dir = os.path.join(self.root_dir, 'assets', self.team_name, self.scheme_name)
        if os.path.exists(scheme_assets_dir):
            shutil.copytree(scheme_assets_dir, pack_path + scheme_assets_dir[len(self.root_dir):])

        team_tables_dir = os.path.join(self.root_dir, 'assets', self.team_name, 'tables')
        if os.path.exists(team_tables_dir):
            shutil.copytree(team_tables_dir, pack_path + team_tables_dir[len(self.root_dir):])

        team_records_dir = os.path.join(self.root_dir, 'assets', self.team_name, 'pre_records')
        if os.path.exists(team_records_dir):
            shutil.copytree(team_records_dir, pack_path + team_records_dir[len(self.root_dir):])

        team_shared_dir = os.path.join(self.root_dir, 'assets', self.team_name, 'shared')
        if os.path.exists(team_shared_dir):
            shutil.copytree(team_shared_dir, pack_path + team_shared_dir[len(self.root_dir):])

        # 处理 launchers
        self._process_scheme_struct_folder('launchers')

        # 处理 plugins
        for p in self.plugin_paths:
            shutil.copytree(p, pack_path + p[len(self.root_dir):], ignore=shutil.ignore_patterns('__pycache__'))

        # 处理 tests
        self._process_scheme_struct_folder('tests')
        team_aw_dir = os.path.join(self.root_dir, 'tests', self.team_name, 'aw')
        if os.path.exists(team_aw_dir):
            shutil.copytree(team_aw_dir, pack_path + team_aw_dir[len(self.root_dir):], ignore=shutil.ignore_patterns('__pycache__'))

        # 处理 pretests
        self._process_scheme_struct_folder('pretests')

        # 处理 方案指定 assets
        for a in self.assets_paths:
            if os.path.isdir(a):
                shutil.copytree(a, pack_path + a[len(self.root_dir):], dirs_exist_ok=True)
            else:
                self.copy2(a, pack_path + a[len(self.root_dir):])


if __name__ == '__main__':
    _team = input('input team name: ')
    _scheme = input('input scheme name: ')
    _version = input('input version: ')
    print('Publishing...')
    _publisher = SchemePublisher(_team, _scheme, _version)
    _publisher.process()
    print(f'Successfully publish to {_publisher.pack_path}')
