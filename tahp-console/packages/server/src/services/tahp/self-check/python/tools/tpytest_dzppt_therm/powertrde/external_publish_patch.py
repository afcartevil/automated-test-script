"""
***************************************************************
临时补丁文件，等加密流程搞完之后，要删除的文件，
***************************************************************
"""

import os
import shutil

from powertrde import env
from powertrde.utils import path_utils, confuse_utils

proj_dir = input("请输入已加密和剪枝后的项目根路径（Please enter the root path of the project after encryption and pruning）:")
team = input('Input team name: ')
scheme = input('Input scheme name: ')


def _encrypt_config():
    ...
    # todo 待确定加密代码位置
    EXCLUDE_FILES = {
        'scheme.yaml',
        'proj.yaml',
        'external_overwrite.yaml',
        'case_set_recent_trace_analyse.yaml',
        'case_set_launch_trace_analyse.yaml',
        'case_set_D7300_D8300_8G.yaml',
        'case_set_D7300_D8300_12G.yaml',
        'case_set_G100_D6300_6G.yaml',
        'case_set_G100_D6300_8G.yaml',
        'case_set_T615_G81_4G.yaml',
        'case_set_T615_G81_6G.yaml',
        'case_set_response_consistency.yaml'
    }
    _config_dir = os.path.join(proj_dir, 'config')
    _files = path_utils.search_paths(_config_dir, '*.yaml', include_dirs=False)
    for _file in _files:
        _full_path = _file['path']
        # if not (_full_path.endswith('scheme.yaml') or _full_path.endswith('proj.yaml') or _full_path.endswith('external_overwrite.yaml') ):
        #     confuse_utils.confuse_file(_full_path, passphrase=env.TEXT_CONFUSED_KEY)
        filename = os.path.basename(_full_path)
        if filename in EXCLUDE_FILES:
            continue
        confuse_utils.confuse_file(_full_path, passphrase=env.TEXT_CONFUSED_KEY)

def _remove_env(publish_mode: str):
    # ... existing code ...
    base_dir = proj_dir.strip().strip('"').strip("'")
    powertrde_dir = os.path.join(base_dir, 'powertrde')
    odm_dir = os.path.join(powertrde_dir, 'odm')
    overseas_dir = os.path.join(powertrde_dir, 'overseas')

    env_name = 'env.cp311-win_amd64.pyd'

    if publish_mode == 'odm':
        src_dir = odm_dir
        mode_label = 'odm'
    elif publish_mode == 'overseas':
        src_dir = overseas_dir
        mode_label = 'overseas'
    else:
        print(f'发布模式必须为 "odm" 或 "overseas"，当前：{publish_mode}')
        return

    src_path = os.path.join(src_dir, env_name)
    dst_path = os.path.join(powertrde_dir, env_name)

    if not os.path.exists(src_path):
        print(f'源文件不存在：{src_path}，无法复制到上一层 {dst_path}')
        return

    try:
        # 覆盖复制到上一层（powertrde）
        shutil.copy2(src_path, dst_path)
        print(f'[{mode_label}] 已复制并覆盖到上一层：{src_path} -> {dst_path}')
    except Exception as e:
        print(f'复制失败：{src_path} -> {dst_path}，原因：{e}')
        return

    # 递归删除 odm 与 overseas 文件夹
    for d in [odm_dir, overseas_dir]:
        if os.path.exists(d):
            try:
                shutil.rmtree(d)
                print(f'已递归删除目录：{d}')
            except Exception as e:
                print(f'删除目录失败：{d}，原因：{e}')
        else:
            print(f'目录不存在：{d}，跳过')
    # ... existing code ...
    
def _remove_phoneMonitor():
    base_dir = proj_dir.strip().strip('"').strip("'")
    pm_dir = os.path.join(base_dir, 'assets', 'res_plugins', 'phonemonitor')

    if not os.path.isdir(pm_dir):
        print(f'未找到目录：{pm_dir}，跳过删除 phoneMonitor apk')
        return

    try:
        entries = os.listdir(pm_dir)
    except Exception as e:
        print(f'无法列出目录：{pm_dir}，原因：{e}')
        return

    apk_files = [f for f in entries if f.lower().endswith('.apk') and os.path.isfile(os.path.join(pm_dir, f))]
    if not apk_files:
        print('没有国内的phoneMonitor apk，无需删除')
        return

    for fname in apk_files:
        fpath = os.path.join(pm_dir, fname)
        try:
            os.remove(fpath)
            print(f'已删除：{fpath}')
        except Exception as e:
            print(f'删除失败：{fpath}，原因：{e}')

def apply_publish_mode(publish_mode: str):
    _remove_phoneMonitor()
    _remove_env(publish_mode)
    if publish_mode == 'odm':
        _encrypt_config()

if __name__ == '__main__':
    apply_publish_mode('odm')
    # apply_publish_mode('overseas')
