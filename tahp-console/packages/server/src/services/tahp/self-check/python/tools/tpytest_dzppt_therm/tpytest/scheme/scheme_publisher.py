import hashlib
import json
import os.path
import shutil
import subprocess
import sys
from datetime import datetime
from typing import Optional

from powertrde import env
from powertrde.env import RES_CORE_DIR
from powertrde.utils import yaml_utils, confuse_utils, path_utils
from tpytest.scheme import scheme_template_creator
from tpytest.scheme.scheme_requirements import SchemeRequirements


def apply_publish_mode(pack_path, publish_mode: str, team_name: str):
    _env_file = os.path.join(pack_path, 'powertrde', 'env.py')
    _env_file_content = None
    with open(_env_file, 'r', encoding='utf-8') as f:
        _env_file_content = f.read()

    with open(_env_file, 'w', encoding='utf-8') as f:
        if f"PUBLISH_MODE = '{publish_mode}'" in _env_file_content:
            return
        _env_file_content = _env_file_content.replace("PUBLISH_MODE = ''", f"PUBLISH_MODE = '{publish_mode}'")
        # _text_confused_key = str(uuid.uuid4())
        # _env_file_content = _env_file_content.replace("TEXT_CONFUSED_KEY = '_$E$C$IG'",
        #                                               f"TEXT_CONFUSED_KEY = '{_text_confused_key}'")
        f.write(_env_file_content)

    _config_dir = os.path.join(pack_path, 'config', team_name)

    # 获取所有yaml文件进行混淆（海外版本除外）
    if publish_mode != 'overseas':
        _files = path_utils.search_paths(_config_dir, '*.yaml', include_dirs=False)
        for _file in _files:
            _full_path = _file['path']
            if not _full_path.endswith('scheme.yaml') or not _full_path.endswith('proj.yaml'):
                confuse_utils.confuse_file(_full_path, passphrase=env.TEXT_CONFUSED_KEY)


class SchemePublisher(SchemeRequirements):
    def __init__(self, scheme_team: str, scheme_name: str, publish_version: str, update_level: int = 0,choice:int = 0,
                 compiled_root: str = None):
        super().__init__(scheme_team, scheme_name)
        self.publish_version = publish_version
        self.update_level = update_level
        support_mode_idx = 0 if choice < 2 else 1
        is_patch = 1 if choice % 2 == 0 else 0
        self.is_patch = is_patch
        self.support_mode_idx = support_mode_idx
        # 外接编译工程根目录（可选）
        if compiled_root and os.path.isdir(compiled_root):
            self.compiled_root = os.path.normpath(compiled_root)
        else:
            self.compiled_root = None
        self.merge_assets()

    @property
    def pack_path(self):
        # 当提供 compiled_root 时，发布输出也放在该外部工程下，避免与当前项目混杂
        base_root = self.compiled_root or self.root_dir
        return os.path.join(base_root, f'tpytest_{self.scheme.team}_{self.scheme.name}')

    def merge_assets(self, base_root: Optional[str] = None):
        base = base_root or self.root_dir
        for p in self.plugins:
            plugin_path = os.path.join(base, 'plugins', p)
            plugin_yaml = os.path.join(str(plugin_path), 'plugin.yaml')
            if os.path.exists(plugin_yaml):
                plugin_yaml_dict = yaml_utils.read_yaml(plugin_yaml)
                if plugin_yaml_dict:
                    for a in plugin_yaml_dict.get('assets', []):
                        plugin_a = f'assets/{a}'
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

    def copy_tree(self, folder_name: str, base_root: str):
        pack_path = self.pack_path
        folder_path = os.path.join(base_root, folder_name)
        if os.path.exists(folder_path):
            shutil.copytree(folder_path, pack_path + folder_path[len(base_root):],
                            ignore=shutil.ignore_patterns('__pycache__', '.*'))

    def process_scheme_struct_folder(self, folder_name: str, base_root: Optional[str] = None):
        base = base_root or self.root_dir
        pack_path = self.pack_path
        folder_path = os.path.join(base, folder_name)
        if os.path.isdir(folder_path):
            self.copy_all_files(folder_path, pack_path + folder_path[len(base):])
        team_folder_path = os.path.join(folder_path, self.team_name)
        if os.path.isdir(team_folder_path):
            self.copy_all_files(team_folder_path, pack_path + team_folder_path[len(base):])
        scheme_folder_path = os.path.join(team_folder_path, self.scheme_name)
        if os.path.isdir(scheme_folder_path):
            shutil.copytree(scheme_folder_path, pack_path + scheme_folder_path[len(base):],
                            ignore=shutil.ignore_patterns('__pycache__'))

    def _process_scheme_struct_folder_from(self, base_root: str, folder_name: str):
        # 保持兼容：转调到统一实现
        return self.process_scheme_struct_folder(folder_name, base_root)

    def process(self):
        # 如果提供了 compiled_root，则仅以 compiled_root 为源进行剪枝打包，避免与当前项目源代码混淆
        src_root = self.compiled_root or self.root_dir

        pack_path = self.pack_path

        # 检查 pack root 下是否有adb被占用，如果是，则先进行adb kill-server
        _exists_packed_adb = os.path.join(pack_path, 'assets', 'res_core', 'adb', 'adb.exe')
        if os.path.exists(_exists_packed_adb):
            try:
                os.remove(_exists_packed_adb)
            except Exception:
                subprocess.run([_exists_packed_adb, 'kill-server'])

        if os.path.exists(pack_path):
            shutil.rmtree(pack_path)

        # 处理root launchers（从模板生成启动脚本）
        src_launchers = os.path.join(RES_CORE_DIR, 'tpytest', 'templates', 'root_launchers')
        pairs = [('xttx', self.team_name), ('xssx', self.scheme_name)]
        scheme_template_creator.directly_main(src_launchers, self.pack_path, pairs)

        # 如果源工程没有方案专属 Python 启动器，则删除相关 bat
        if not os.path.exists(os.path.join(src_root, 'launchers', self.team_name, self.scheme_name,
                                           f'start_{self.scheme_name}_gui_python.py')):
            os.remove(os.path.join(self.pack_path, f'start_env_{self.scheme_name}_gui.bat'))
            os.remove(os.path.join(self.pack_path, f'start_embed_{self.scheme_name}_gui.bat'))
        update_info = {}
        # 写入version
        if self.publish_version:
            update_info['version'] = self.publish_version
            # with open(os.path.join(self.pack_path, f'{self.scheme_name}_version.yaml'), 'w') as f:
            #     f.write(self.publish_version)
        update_info['force_update'] = True if self.update_level >= 2 else False
        update_info['update_level'] = self.update_level
        update_info["is_patch"] = True if bool(self.is_patch) else False
        update_info["support_mode_idx"] = self.support_mode_idx
        update_info['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        yaml_utils.write_yaml(update_info, os.path.join(self.pack_path, f'{self.scheme_name}_version.yaml'))

        # 处理 基础框架（tpytest, powertrde）
        tpytest_src = os.path.join(src_root, 'tpytest')
        if os.path.isdir(tpytest_src):
            shutil.copytree(tpytest_src, os.path.join(pack_path, 'tpytest'),
                            ignore=shutil.ignore_patterns('__pycache__'))
        powertrde_src = os.path.join(src_root, 'powertrde')
        if os.path.isdir(powertrde_src):
            shutil.copytree(powertrde_src, os.path.join(pack_path, 'powertrde'),
                            ignore=shutil.ignore_patterns('__pycache__'))
        if os.path.exists(os.path.join(src_root, 'requirements.txt')):
            self.copy2(os.path.join(src_root, 'requirements.txt'), os.path.join(pack_path, 'requirements.txt'))
        if os.path.exists(os.path.join(src_root, 'requirements-win.txt')):
            self.copy2(os.path.join(src_root, 'requirements-win.txt'), os.path.join(pack_path, 'requirements-win.txt'))
        if os.path.exists(os.path.join(src_root, 'setup_tpytest.py')):
            self.copy2(os.path.join(src_root, 'setup_tpytest.py'), os.path.join(pack_path, 'setup_tpytest.py'))
        if os.path.exists(os.path.join(src_root, '.gitignore')):
            self.copy2(os.path.join(src_root, '.gitignore'), os.path.join(pack_path, '.gitignore'))
        if os.path.exists(os.path.join(src_root, '.gitmodules')):
            self.copy2(os.path.join(src_root, '.gitmodules'), os.path.join(pack_path, '.gitmodules'))

        # 处理 config
        self.process_scheme_struct_folder('config', src_root)

        # 处理 assets（res_core + 方案/团队目录 + shared/tables/pre_records）
        res_core_src = os.path.join(src_root, 'assets', 'res_core')
        if os.path.isdir(res_core_src):
            shutil.copytree(res_core_src, os.path.join(pack_path, 'assets', 'res_core'))

        scheme_assets_dir = os.path.join(src_root, 'assets', self.team_name, self.scheme_name)
        if os.path.exists(scheme_assets_dir):
            shutil.copytree(scheme_assets_dir, pack_path + scheme_assets_dir[len(src_root):])

        team_tables_dir = os.path.join(src_root, 'assets', self.team_name, 'tables')
        if os.path.exists(team_tables_dir):
            shutil.copytree(team_tables_dir, pack_path + team_tables_dir[len(src_root):])

        team_records_dir = os.path.join(src_root, 'assets', self.team_name, 'pre_records')
        if os.path.exists(team_records_dir):
            shutil.copytree(team_records_dir, pack_path + team_records_dir[len(src_root):])

        team_shared_dir = os.path.join(src_root, 'assets', self.team_name, 'shared')
        if os.path.exists(team_shared_dir):
            shutil.copytree(team_shared_dir, pack_path + team_shared_dir[len(src_root):])

        # 处理 launchers
        self.process_scheme_struct_folder('launchers', src_root)

        # 处理 plugins（仅剪枝所需插件）
        plugin_paths_src = []
        for p in self.plugins:
            pp = os.path.join(src_root, 'plugins', p)
            if os.path.exists(pp):
                plugin_paths_src.append(pp)
        for p in plugin_paths_src:
            _str_p = str(p)
            shutil.copytree(_str_p, pack_path + _str_p[len(src_root):], ignore=shutil.ignore_patterns('__pycache__'))

        # 处理 tests
        self.process_scheme_struct_folder('tests', src_root)
        team_aw_dir = os.path.join(src_root, 'tests', self.team_name, 'aw')
        if os.path.exists(team_aw_dir):
            shutil.copytree(team_aw_dir, pack_path + team_aw_dir[len(src_root):],
                            ignore=shutil.ignore_patterns('__pycache__'))

        # 处理 pretests
        self.process_scheme_struct_folder('pretests', src_root)

        # 处理 TAEP
        _deal_taep = False
        try:
            if 'use_taep' not in self.base_config_dict['trunk_flags']:
                raise Exception()
            _deal_taep = True
        except Exception:
            pass

        if _deal_taep:
            self.copy_tree(os.path.join('taep', 'aw'), src_root)
            self.copy_tree(os.path.join('taep', 'page'), src_root)
            self.copy_tree(os.path.join('taep', 'resource'), src_root)
            self.copy_tree(os.path.join('taep', 'TCoreCapaLib'), src_root)
            self.process_scheme_struct_folder(os.path.join('taep', 'testcase'), src_root)

        # 收集插件声明的 assets（针对 compiled_root 也做一次合并），并复制方案指定 assets
        if self.compiled_root:
            self.merge_assets(src_root)
        # 将 assets 中的相对路径映射到 src_root 下复制
        for a in self.assets:
            full_a = os.path.normpath(os.path.join(src_root, a))
            if os.path.isdir(full_a):
                shutil.copytree(full_a, pack_path + full_a[len(src_root):], dirs_exist_ok=True)
            elif os.path.isfile(full_a):
                self.copy2(full_a, pack_path + full_a[len(src_root):])

        # 生成合并后的 requirements
        print('Now merging scheme requirements...')
        _m = self.gen_merged_requirements(include_win_requirements=False)
        with open(os.path.join(pack_path, 'requirements-merged.txt'), 'w') as f:
            f.write('\n'.join(_m['merged']))
        with open(os.path.join(pack_path, 'install-requirements-merged-env.bat'), 'w') as f:
            f.write(
                '@echo off\ncd /d %~dp0\npip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements-merged.txt\necho.\npause')
        with open(os.path.join(pack_path, 'install-requirements-merged-embed.bat'), 'w') as f:
            f.write(
                '@echo off\ncd /d %~dp0\n..\\tpytest-python-embed\\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements-merged.txt\necho.\npause')

        # 删除不需要的模板
        _template_tpytest_dir = os.path.join(self.pack_path, 'assets', 'res_core', 'tpytest')
        if os.path.exists(_template_tpytest_dir):
            shutil.rmtree(_template_tpytest_dir)

        # 计算整个目录的MD5值并保存到manifest.json
        self._generate_md5_checksum(pack_path)

    def _generate_md5_checksum(self, directory_path):
        """
        计算指定目录下所有文件的MD5值，并保存到manifest.json文件中
        """
        md5_dict = {}
        
        for root, dirs, files in os.walk(directory_path):
            # 跳过__pycache__目录
            dirs[:] = [d for d in dirs if d != '__pycache__']
            
            for file in files:
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, directory_path)
                
                # 计算文件的MD5值
                md5_hash = hashlib.md5()
                try:
                    with open(file_path, "rb") as f:
                        # 分块读取文件以处理大文件
                        for chunk in iter(lambda: f.read(4096), b""):
                            md5_hash.update(chunk)
                    md5_dict[relative_path] = md5_hash.hexdigest()
                except Exception as e:
                    print(f"Warning: Could not calculate MD5 for {file_path}: {e}")
        
        # 保存到manifest.json
        manifest_path = os.path.join(directory_path, 'manifest.json')
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(md5_dict, f, indent=2, ensure_ascii=False)



    def apply_publish_mode(self, publish_mode: str):
        apply_publish_mode(self.pack_path, publish_mode, self.team_name)


if __name__ == '__main__':
    # print(yaml_utils.read_yaml(r'D:\Projects\dz_auto_env\tpytest_dzppt_perf\config\dzppt\perf\base_config.yaml'))
    if len(sys.argv) > 3:
        _team = sys.argv[1]
        _scheme = sys.argv[2]
        _version = sys.argv[3]
        _update_level = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        _publish_scope = int(sys.argv[5]) if len(sys.argv) > 5 else 0
        _compiled_root = sys.argv[6] if len(sys.argv) > 6 else ''
        # _support_mode_idx = sys.argv[7] if len(sys.argv) > 7 else ''
    else:
        _team = input('Input team name: ')
        _scheme = input('Input scheme name: ')
        _version = input('Input release version: ')
        # 0.普通更新 1.推荐更新 2.强制更新
        _update_level = input('Input version update level (0.Normal  1.Recommended  2.Must): ')
        try:
            _update_level = int(_update_level)
            if _update_level < 0:
                _update_level = 0
            elif _update_level > 2:
                _update_level = 2
        except Exception:
            _update_level = 0

        _publish_scope = input(
            "Select publish scope:\n"
            "0. China + Patch\n"
            "1. China + Full\n"
            "2. External + Patch\n"
            "3. External + Full\n"
            "Input: "
        ).strip()
        try:
            _publish_scope = int(_publish_scope)
        except:
            _publish_scope = 0

        # _is_patch = input('Select update type (0.Full update 1.Patch update): ')
        # _is_patch  = int(_is_patch)
        # try:
        #     if _is_patch < 0:
        #         _is_patch = 0
        # except Exception:
        #     _is_patch = 0
        _compiled_root = input('input external compiled project root (blank to skip): ')
        # _support_mode_idx = int(input('Input support mode (0.Default  1.Overseas ): ').strip())
        # _publish_mode_idx = input('Input publish mode (0.Default  1.Overseas  2.ODM 3.1|2): ').strip()
        # if _publish_mode_idx == '1':
        #     _publish_mode = 'overseas'
        # elif _publish_mode_idx == '2':
        #     _publish_mode = 'odm'

    print('Publishing...')
    _publisher = SchemePublisher(_team, _scheme, _version, _update_level,_publish_scope ,_compiled_root)
    _publisher.process()
    print(f'Successfully publish to {_publisher.pack_path}')
    # _publisher.apply_publish_mode('odm')


