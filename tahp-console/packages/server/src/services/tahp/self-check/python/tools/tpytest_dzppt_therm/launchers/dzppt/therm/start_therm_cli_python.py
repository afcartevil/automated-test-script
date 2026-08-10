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


def _pick_test_device(devices, preferred_device_id=None):
    from powertrde.utils.trde import adb

    if preferred_device_id:
        if preferred_device_id not in devices:
            raise RuntimeError(f"Device '{preferred_device_id}' not found in adb devices: {devices}")
        return preferred_device_id

    for device_id in devices:
        if not adb.is_pointer_location_on(device_id):
            return device_id
    return devices[0]


def _detect_case_set(device_id):
    from powertrde.utils.trde import adb

    if adb.is_mtk(device_id):
        return 'mtk'
    if adb.is_qcom(device_id):
        return 'qcom'
    if adb.is_sprd(device_id):
        return 'sqrt'
    return 'mtk'


def _parse_cli_args():
    case_set = None
    device_id = None
    log_parent_dir = None
    passthrough = []
    args = sys.argv[1:]
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in ('--mock',):
            case_set = 'mock'
        elif arg.startswith('--case-set='):
            case_set = arg.split('=', 1)[1].strip()
        elif arg == '--case-set' and index + 1 < len(args):
            case_set = args[index + 1].strip()
            index += 1
        elif arg.startswith('--device-id='):
            device_id = arg.split('=', 1)[1].strip()
        elif arg == '--device-id' and index + 1 < len(args):
            device_id = args[index + 1].strip()
            index += 1
        elif arg.startswith('--log-parent-dir='):
            log_parent_dir = arg.split('=', 1)[1].strip()
        elif arg == '--log-parent-dir' and index + 1 < len(args):
            log_parent_dir = args[index + 1].strip()
            index += 1
        elif arg.startswith('--config='):
            passthrough.extend([arg])
        elif arg == '--config' and index + 1 < len(args):
            passthrough.extend([arg, args[index + 1]])
            index += 1
        else:
            passthrough.append(arg)
        index += 1
    return case_set, device_id, log_parent_dir, passthrough


def _count_case_set_cases(case_set_name: str) -> int:
    config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                              'config', 'dzppt', 'therm')
    case_set_file = os.path.join(config_dir, f'case_set_{case_set_name}.yaml')
    if not os.path.exists(case_set_file):
        return 0
    count = 0
    with open(case_set_file, encoding='utf-8') as file:
        for line in file:
            stripped = line.strip()
            if stripped.startswith('- test_') or stripped.startswith('- Test'):
                count += 1
    return count


if __name__ == '__main__':
    add_path_to_python_env()
    check_to_install_requirements('dzppt', 'therm')

    from powertrde.utils.trde import adb
    from powertrde.env import PROJ_DIR
    from pretests.dzppt.therm.therm_pretest import ThermPretest

    case_set_override, device_id_override, log_parent_dir, passthrough_args = _parse_cli_args()
    sys.argv = [sys.argv[0], *passthrough_args]

    devices = adb.adb_devices()
    if not devices:
        print('Error: No ADB device found. Please connect a phone and enable USB debugging.', flush=True)
        sys.exit(1)

    device_id = _pick_test_device(devices, device_id_override)
    case_set = case_set_override or _detect_case_set(device_id)
    case_count = _count_case_set_cases(case_set)
    if log_parent_dir:
        os.makedirs(log_parent_dir, exist_ok=True)

    print('=' * 48, flush=True)
    print('  THERM CLI One-Click Test', flush=True)
    print(f'  Device   : {device_id}', flush=True)
    print(f'  Platform : {case_set}', flush=True)
    print(f'  Cases    : {case_count}', flush=True)
    if log_parent_dir:
        print(f'  Log dir  : {log_parent_dir}', flush=True)
    print('=' * 48, flush=True)
    print(flush=True)

    os.chdir(PROJ_DIR)
    env_kwargs = {
        'case_set': case_set,
        'device_id': device_id,
    }
    if log_parent_dir:
        env_kwargs['log_parent_dir'] = log_parent_dir
    ThermPretest.get_instance().with_scheme_env_kwargs(**env_kwargs).start()
