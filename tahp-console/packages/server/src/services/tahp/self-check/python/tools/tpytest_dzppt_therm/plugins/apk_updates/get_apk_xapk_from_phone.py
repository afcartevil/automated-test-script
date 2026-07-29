# -*- coding: utf-8 -*-
"""
智能APK更新拉取工具 - 独立版本

基于global_index.json版本索引智能拉取手机上的更新版本APK/XAPK包。
该工具会比较本地索引文件中记录的版本与手机上实际安装的版本，
仅拉取版本号更高的应用，避免重复下载相同版本的应用。

主要功能:
    - 读取和解析global_index.json版本索引文件
    - 获取手机上已安装应用的版本信息
    - 智能版本比较，仅拉取更新版本
    - 支持单个APK和Split APK的XAPK打包
    - 自动处理未记录的应用下载
    - 详细的更新日志和处理报告

技术特性:
    - 支持多种版本比较策略（数字版本码优先）
    - Windows路径格式优化
    - 简洁的实现方式，避免复杂的防御性编程
    - 外部调用接口支持，便于集成到其他系统
    - 完整的错误处理和日志记录
    - 独立运行，无需外部模块依赖

依赖要求:
    - Python 3.7+
    - ADB工具（Android Debug Bridge）
    - aapt工具（用于版本信息提取，可选）
    - Android设备已连接并授权ADB调试
    - global_index.json版本索引文件
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple

# 导入adb工具中的版本获取方法
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, project_root)
from powertrde.utils.trde.adb import get_installed_package_version, get_installed_package_version_code


# ==================== 核心ADB和设备管理函数 ====================

def run_adb(cmd: List[str], device: Optional[str] = None, check: bool = True) -> Tuple[int, str]:
    """执行ADB命令并返回结果"""
    base = ["adb"]
    if device:
        base += ["-s", device]
    full = base + cmd
    try:
        out = subprocess.check_output(full, stderr=subprocess.STDOUT)
        return 0, out.decode('utf-8', errors='ignore')
    except subprocess.CalledProcessError as e:
        return e.returncode, (e.output.decode('utf-8', errors='ignore') if e.output else str(e))
    except FileNotFoundError:
        print("[ERROR] adb not found. Make sure adb is installed and in PATH.")
        sys.exit(2)


def list_devices() -> List[str]:
    """获取当前连接的Android设备列表"""
    rc, out = run_adb(["devices"])
    if rc != 0:
        raise RuntimeError(f"adb devices failed: {out}")
    lines = [l.strip() for l in out.splitlines()]
    serials = []
    for l in lines[1:]:
        if not l:
            continue
        parts = l.split()
        if len(parts) >= 2 and parts[1] == 'device':
            serials.append(parts[0])
    return serials


def pm_list_packages(device: str, flag: Optional[str] = None) -> List[str]:
    """获取设备上已安装的应用包列表"""
    cmd = ["shell", "pm", "list", "packages"]
    if flag:
        cmd = ["shell", "pm", "list", "packages", flag]
    rc, out = run_adb(cmd, device)
    if rc != 0:
        raise RuntimeError(f"pm list packages failed: {out}")
    packages = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('package:'):
            packages.append(line[len('package:'):])
    return packages


def pm_path(device: str, package: str) -> List[str]:
    """获取指定包在设备上的APK文件路径列表"""
    rc, out = run_adb(["shell", "pm", "path", package], device)
    if rc != 0:
        return []
    paths = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.search(r'package:(\S+)', line)
        if m:
            paths.append(m.group(1))
    return paths


def get_package_info(device: str, package: str) -> Dict:
    """获取应用包的详细元数据信息"""
    info = {}

    # 使用 adb.py 中的方法获取版本信息（自动处理 stub 版本）
    try:
        version_code = get_installed_package_version_code(device, package)
        if version_code > 0:
            info['version_code'] = str(version_code)
        
        version_name = get_installed_package_version(device, package)
        if version_name:
            info['version_name'] = version_name
    except Exception as e:
        print(f"[DEBUG] 使用 adb.py 方法获取 {package} 信息失败: {e}")

    # 备用方法: 使用 dumpsys package
    if not info.get('version_code'):
        try:
            rc, out = run_adb(["shell", "dumpsys", "package", package], device)
            if rc == 0:
                lines = out.splitlines()
                in_package_section = False
                permissions = []

                for line in lines:
                    line = line.strip()

                    if f"Package [{package}]" in line or f"pkg={package}" in line:
                        in_package_section = True
                        continue

                    if in_package_section:
                        if line.startswith("Package [") and package not in line:
                            break

                        if "versionCode=" in line:
                            match = re.search(r'versionCode=(\d+)', line)
                            if match:
                                info['version_code'] = match.group(1)

                        if "versionName=" in line:
                            match = re.search(r'versionName=([^\s]+)', line)
                            if match:
                                info['version_name'] = match.group(1)

                        if "minSdk=" in line:
                            match = re.search(r'minSdk=(\d+)', line)
                            if match:
                                info['min_sdk_version'] = match.group(1)

                        if "targetSdk=" in line:
                            match = re.search(r'targetSdk=(\d+)', line)
                            if match:
                                info['target_sdk_version'] = match.group(1)

                        if (line.startswith("android.") or line.startswith("com.") or
                                line.startswith("huawei.") or line.startswith("org.")):
                            if line not in permissions:
                                permissions.append(line)

                if permissions:
                    info['permissions'] = permissions
        except Exception as e:
            print(f"[DEBUG] dumpsys 方法获取 {package} 信息失败: {e}")

    return info


def get_app_name(device: str, package: str) -> Tuple[Optional[str], Optional[str]]:
    """获取应用的用户友好显示名称和图标路径"""
    app_name = None
    icon_path = None

    try:
        rc, out = run_adb(["shell", "pm", "dump", package], device)
        if rc == 0:
            for line in out.splitlines():
                line = line.strip()
                if "applicationLabel=" in line:
                    match = re.search(r'applicationLabel=(.+)', line)
                    if match:
                        app_name = match.group(1).strip()
                elif "applicationIcon=" in line:
                    match = re.search(r'applicationIcon=(.+)', line)
                    if match:
                        icon_path = match.group(1).strip()
    except Exception as e:
        print(f"[DEBUG] pm dump 获取应用名称失败: {e}")

    if not app_name:
        try:
            rc, out = run_adb(["shell", "pm", "list", "packages", "-f", package], device)
            if rc == 0 and package in out:
                app_name = package.split('.')[-1].replace('_', ' ').title()
        except Exception as e:
            print(f"[DEBUG] pm list packages 获取应用名称失败: {e}")

    return app_name, icon_path


def adb_pull_file(device: str, remote_path: str, local_path: str) -> bool:
    """从Android设备拉取文件到本地"""
    rc, out = run_adb(["pull", remote_path, local_path], device)
    if rc != 0:
        print(f"[WARN] pull failed for {remote_path}: {out}")
        return False
    return True


# ==================== 文件处理和XAPK打包函数 ====================

def sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    return re.sub(r'[\\/*?:<>|"\n\r\t]+', '_', name)


def get_apk_size(apk_path: Path) -> int:
    """获取APK文件的字节大小"""
    try:
        return apk_path.stat().st_size
    except:
        return 0


def extract_icon_from_apk(apk_path: Path, output_dir: Path) -> Optional[str]:
    """从APK文件中提取应用图标"""
    try:
        import zipfile
        with zipfile.ZipFile(apk_path, 'r') as apk_zip:
            icon_candidates = []
            for file_info in apk_zip.filelist:
                if (file_info.filename.startswith('res/drawable') or
                    file_info.filename.startswith('res/mipmap')) and \
                        (file_info.filename.endswith('.png') or
                         file_info.filename.endswith('.xml')):
                    icon_candidates.append(file_info.filename)

            best_icon = None
            for candidate in icon_candidates:
                if 'xxxhdpi' in candidate or 'xxhdpi' in candidate:
                    best_icon = candidate
                    break

            if not best_icon and icon_candidates:
                best_icon = icon_candidates[0]

            if best_icon:
                icon_data = apk_zip.read(best_icon)
                icon_filename = "icon.png"
                icon_path = output_dir / icon_filename
                with open(icon_path, 'wb') as f:
                    f.write(icon_data)
                return icon_filename
    except Exception as e:
        print(f"[WARN] 提取图标失败: {e}")
    return None


def package_to_xapk_with_path(xapk_path: Path, package: str, apk_files: List[Path], device: str) -> Path:
    """将APK文件列表打包为指定路径的XAPK格式文件"""
    import zipfile

    print(f"[DEBUG] 开始为 {package} 获取详细信息...")

    package_info = get_package_info(device, package)
    app_name, icon_path = get_app_name(device, package)

    total_size = sum(get_apk_size(apk) for apk in apk_files)

    split_apks = []
    for apk_file in apk_files:
        apk_info = {
            "file": apk_file.name,
            "id": "base" if "base" in apk_file.name.lower() else apk_file.name.replace(".apk", "")
        }
        split_apks.append(apk_info)

    icon_filename = None
    base_apk = None
    for apk_file in apk_files:
        if "base" in apk_file.name.lower() or package in apk_file.name:
            base_apk = apk_file
            break
    if not base_apk and apk_files:
        base_apk = apk_files[0]

    if base_apk:
        temp_dir = Path(tempfile.mkdtemp())
        try:
            icon_filename = extract_icon_from_apk(base_apk, temp_dir)
        except Exception as e:
            print(f"[DEBUG] 提取图标失败: {e}")

    manifest = {
        "xapk_version": "2",
        "package_name": package,
        "name": app_name or package,
        "locales_name": {
            "en": app_name or package
        },
        "version_code": package_info.get('version_code', '1'),
        "version_name": package_info.get('version_name', '1.0'),
        "min_sdk_version": package_info.get('min_sdk_version', '21'),
        "target_sdk_version": package_info.get('target_sdk_version', '33'),
        "permissions": package_info.get('permissions', []),
        "total_size": total_size,
        "icon": icon_filename or "icon.png",
        "split_apks": split_apks
    }

    with zipfile.ZipFile(xapk_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for p in apk_files:
            zf.write(p, arcname=p.name)

        if icon_filename and base_apk:
            temp_dir = Path(tempfile.mkdtemp())
            try:
                extracted_icon = extract_icon_from_apk(base_apk, temp_dir)
                if extracted_icon:
                    icon_path = temp_dir / extracted_icon
                    if icon_path.exists():
                        zf.write(icon_path, arcname=icon_filename)
            except Exception as e:
                print(f"[DEBUG] 写入图标失败: {e}")
            finally:
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass

        zf.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))

    return xapk_path


# ==================== 版本比较和文件冲突处理函数 ====================

def find_aapt_executable() -> Optional[str]:
    """查找系统中可用的aapt工具可执行文件"""
    import subprocess
    import glob
    from pathlib import Path

    script_dir = Path(__file__).parent
    project_aapt = script_dir.parent.parent / "assets" / "res_plugins" / "aapt.exe"

    potential_paths = [
        str(project_aapt),
        'aapt',
        'aapt.exe',
        r'C:\tools\android-tools\aapt.exe',
    ]

    def tess_aapt(cmd):
        try:
            result = subprocess.run([cmd, 'version'], capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except:
            return False

    for path in potential_paths:
        if Path(path).exists() and tess_aapt(path):
            print(f"[DEBUG] 使用aapt工具: {path}")
            return path

    sdk_patterns = [
        r'C:\android-sdk\build-tools\*\aapt.exe',
        r'C:\Users\*\AppData\Local\Android\Sdk\build-tools\*\aapt.exe',
    ]

    for pattern in sdk_patterns:
        try:
            for path in glob.glob(pattern):
                if Path(path).exists() and tess_aapt(path):
                    print(f"[DEBUG] 在SDK中找到aapt工具: {path}")
                    return path
        except:
            continue

    return None


def get_version_from_apk(apk_path: Path, device: Optional[str] = None, package_name: Optional[str] = None) -> Tuple[
    Optional[str], Optional[str]]:
    """从APK文件中提取版本信息"""
    import subprocess
    import re

    aapt_cmd = find_aapt_executable()
    if not aapt_cmd:
        print(f"[WARN] 未找到aapt工具，无法从 {apk_path.name} 提取版本信息")
        return None, None

    try:
        result = subprocess.run(
            [aapt_cmd, 'dump', 'badging', str(apk_path)],
            capture_output=True, text=True, timeout=30, encoding='utf-8', errors='ignore'
        )

        if result.returncode == 0 and result.stdout:
            for line in result.stdout.split('\n'):
                if line.startswith('package:'):
                    version_code_match = re.search(r"versionCode='([^']+)'", line)
                    version_name_match = re.search(r"versionName='([^']+)'", line)

                    if version_code_match and version_name_match:
                        version_code = version_code_match.group(1)
                        version_name = version_name_match.group(1)
                        return version_code, version_name
    except Exception as e:
        print(f"[DEBUG] aapt命令执行异常: {e}")

    return None, None


def get_version_from_xapk(xapk_path: Path) -> Tuple[Optional[str], Optional[str]]:
    """从XAPK文件中提取版本信息"""
    try:
        import zipfile
        with zipfile.ZipFile(xapk_path, 'r') as xapk_zip:
            if 'manifest.json' in xapk_zip.namelist():
                manifest_data = xapk_zip.read('manifest.json')
                manifest = json.loads(manifest_data.decode('utf-8'))

                version_code = manifest.get('version_code')
                version_name = manifest.get('version_name')

                return version_code, version_name
    except Exception as e:
        print(f"[DEBUG] 从XAPK {xapk_path} 提取版本信息失败: {e}")

    return None, None


def compare_versions(current_version_code: str, current_version_name: str,
                     existing_version_code: Optional[str], existing_version_name: Optional[str]) -> bool:
    """比较应用版本号，判断是否应该覆盖现有文件"""
    if existing_version_code is None:
        return True

    try:
        current_code = int(current_version_code)
        existing_code = int(existing_version_code)

        if current_code > existing_code:
            print(
                f"[INFO] 版本更新：{existing_version_code}({existing_version_name}) -> {current_version_code}({current_version_name})")
            return True
        elif current_code == existing_code:
            print(f"[INFO] 版本相同：{current_version_code}({current_version_name})，跳过")
            return False
        else:
            print(
                f"[INFO] 版本较旧：{current_version_code}({current_version_name}) < {existing_version_code}({existing_version_name})，跳过")
            return False
    except (ValueError, TypeError):
        print(f"[DEBUG] 版本号格式特殊，使用字符串比较")
        if current_version_code > (existing_version_code or ''):
            return True
        else:
            return False


def handle_file_conflict(target_path: Path, overwrite_mode: str, current_version_code: Optional[str] = None,
                         current_version_name: Optional[str] = None) -> Optional[Path]:
    """处理文件冲突的核心逻辑函数"""
    if not target_path.exists():
        return target_path

    print(f"[WARN] 文件已存在: {target_path}")

    if overwrite_mode == 'overwrite':
        print(f"[INFO] 强制覆盖模式，覆盖文件: {target_path}")
        return target_path
    elif overwrite_mode == 'skip':
        print(f"[INFO] 跳过模式，跳过文件: {target_path}")
        return None
    elif overwrite_mode == 'version':
        if current_version_code is None:
            print(f"[WARN] 无法获取当前版本信息，默认跳过以保证安全")
            return None

        existing_version_code, existing_version_name = None, None

        if target_path.suffix.lower() == '.apk':
            existing_version_code, existing_version_name = get_version_from_apk(target_path, None, target_path.stem)
        elif target_path.suffix.lower() == '.xapk':
            existing_version_code, existing_version_name = get_version_from_xapk(target_path)

        if existing_version_code is None:
            print(f"[WARN] 无法获取现有文件版本信息，默认覆盖")
            return target_path

        should_overwrite = compare_versions(current_version_code, current_version_name or '',
                                            existing_version_code, existing_version_name)

        if should_overwrite:
            return target_path
        else:
            return None
    elif overwrite_mode == 'rename':
        stem = target_path.stem
        suffix = target_path.suffix
        parent = target_path.parent

        counter = 1
        while True:
            new_name = f"{stem}_{counter}{suffix}"
            new_path = parent / new_name
            if not new_path.exists():
                print(f"[INFO] 自动重命名为: {new_path}")
                return new_path
            counter += 1
            if counter > 1000:
                print(f"[ERROR] 无法找到合适的重命名，跳过")
                return None

    return target_path


def ensure_outdir(path: str) -> Path:
    """确保输出目录存在"""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


# ==================== 核心拉取处理函数 ====================

def pull_packages(device: str, package_list: List[str], outdir: Path, keep_temp: bool = False,
                  overwrite_mode: str = 'ask') -> Dict[str, Dict]:
    """APK拉取和XAPK打包的核心批量处理函数"""
    res = {}
    tmpdir = Path(tempfile.mkdtemp(prefix='adb_pull_apks_'))
    try:
        for pkg in package_list:
            print(f"-> 处理包: {pkg}")

            package_info = get_package_info(device, pkg)
            current_version_code = package_info.get('version_code')
            current_version_name = package_info.get('version_name')

            paths = pm_path(device, pkg)
            if not paths:
                print(f"   [WARN] 无法获取 {pkg} 的 apk 路径，跳过")
                res[pkg] = {'ok': False, 'reason': 'no_paths'}
                continue

            apk_local_paths: List[Path] = []
            for remote in paths:
                base_name = os.path.basename(remote)
                candidate = tmpdir / f"{pkg}__{base_name}"
                idx = 1
                while candidate.exists():
                    candidate = tmpdir / f"{pkg}__{idx}__{base_name}"
                    idx += 1
                success = adb_pull_file(device, remote, str(candidate))
                if success:
                    apk_local_paths.append(candidate)

            if not apk_local_paths:
                print(f"   [WARN] {pkg} 未成功下载任何 apk")
                res[pkg] = {'ok': False, 'reason': 'pull_failed'}
                continue

            if len(apk_local_paths) == 1:
                dest_name = sanitize_filename(f"{pkg}.apk")
                target_path = outdir / dest_name

                final_path = handle_file_conflict(target_path, overwrite_mode, current_version_code,
                                                  current_version_name)
                if final_path is None:
                    print(f"   [SKIP] 跳过已存在的单个 apk: {pkg}")
                    res[pkg] = {'ok': False, 'reason': 'skipped_existing'}
                    continue

                shutil.move(str(apk_local_paths[0]), final_path)
                print(f"   [OK] 单个 apk：{final_path}")
                res[pkg] = {'ok': True, 'type': 'apk', 'path': str(final_path)}
            else:
                prepared: List[Path] = []
                for i, p in enumerate(apk_local_paths, start=1):
                    original_name = os.path.basename(paths[i - 1]) if i - 1 < len(paths) else f"part{i}.apk"
                    if "base" in original_name:
                        friendly_name = f"{pkg}.apk"
                    elif "config" in original_name:
                        friendly_name = original_name
                    else:
                        friendly_name = f"{pkg}__part{i}.apk"

                    friendly = tmpdir / sanitize_filename(friendly_name)
                    shutil.move(str(p), friendly)
                    prepared.append(friendly)

                xapk_name = sanitize_filename(f"{pkg}.xapk")
                target_xapk_path = outdir / xapk_name
                final_xapk_path = handle_file_conflict(target_xapk_path, overwrite_mode, current_version_code,
                                                       current_version_name)

                if final_xapk_path is None:
                    print(f"   [SKIP] 跳过已存在的 xapk: {pkg}")
                    res[pkg] = {'ok': False, 'reason': 'skipped_existing'}
                    continue

                xapk_path = package_to_xapk_with_path(final_xapk_path, pkg, prepared, device)
                print(f"   [OK] 多 apk -> xapk: {xapk_path}")
                res[pkg] = {'ok': True, 'type': 'xapk', 'path': str(xapk_path), 'parts': [str(p) for p in prepared]}

                if not keep_temp:
                    for p in prepared:
                        try:
                            p.unlink()
                        except Exception:
                            pass

        return res
    finally:
        if keep_temp:
            print(f"临时目录保留: {tmpdir}")
        else:
            try:
                shutil.rmtree(tmpdir)
            except Exception:
                pass


# ==================== 智能更新器核心类 ====================

class GlobalIndexManager:
    """全局索引管理器 - 处理版本索引文件的读取和更新"""

    def __init__(self, index_file_path: str):
        """
        初始化索引管理器

        参数:
            index_file_path (str): global_index.json文件路径
        """
        self.index_file_path = Path(index_file_path)
        self.index_data = {}
        self.package_versions = {}

    def load_index(self) -> bool:
        """
        加载全局索引文件

        返回值:
            bool: 加载是否成功
        """
        try:
            if not self.index_file_path.exists():
                print(f"[WARN] 索引文件不存在: {self.index_file_path}")
                return False

            with open(self.index_file_path, 'r', encoding='utf-8') as f:
                self.index_data = json.load(f)

            # 构建包名到版本的映射
            if 'apps' in self.index_data:
                for app in self.index_data['apps']:
                    package_name = app.get('package_name')
                    version_code = app.get('latest_version_code')
                    version_name = app.get('version_name')

                    if package_name and version_code:
                        self.package_versions[package_name] = {
                            'version_code': str(version_code),
                            'version_name': version_name or 'unknown',
                            'meta_url': app.get('meta_url', '')
                        }

            print(f"[INFO] 成功加载索引文件，包含 {len(self.package_versions)} 个应用记录")
            return True

        except Exception as e:
            print(f"[ERROR] 加载索引文件失败: {e}")
            return False

    def get_package_version(self, package_name: str) -> Optional[Dict[str, str]]:
        """
        获取指定包的版本信息

        参数:
            package_name (str): 应用包名

        返回值:
            Optional[Dict]: 版本信息字典或None
        """
        return self.package_versions.get(package_name)

    def get_all_packages(self) -> List[str]:
        """
        获取索引中所有的包名列表

        返回值:
            List[str]: 包名列表
        """
        return list(self.package_versions.keys())


class SmartAPKUpdater:
    """智能APK更新器 - 核心更新逻辑处理"""

    def __init__(self, device_id: Optional[str] = None,
                 output_dir: str = r'E:\Desktop\local_app_repo',
                 index_file: str = r'E:\Desktop\project\dz_auto_env\zxc\copy2\global_index.json'):
        """
        初始化更新器

        参数:
            device_id (Optional[str]): 设备序列号
            output_dir (str): 输出目录
            index_file (str): 全局索引文件路径
        """
        self.device_id = device_id
        self.output_dir = Path(output_dir)
        self.index_manager = GlobalIndexManager(index_file)
        self.update_candidates = []
        self.unrecorded_candidates = []
        self.processing_results = {}

    def initialize(self) -> bool:
        """
        初始化更新器，检查工具和设备

        返回值:
            bool: 初始化是否成功
        """
        print("=== 智能APK更新拉取工具 ===")

        # 检查aapt工具
        aapt_path = find_aapt_executable()
        if aapt_path:
            print(f"[INFO] aapt工具已就绪: {aapt_path}")
        else:
            print(f"[WARN] 未找到aapt工具，版本比较功能可能受限")

        # 加载索引文件
        if not self.index_manager.load_index():
            return False

        # 检查设备连接
        devices = list_devices()
        if not devices:
            print('[ERROR] 没有发现任何 adb 设备，请确保设备已连接并已授权 adb 调试')
            return False

        # 选择设备
        if not self.device_id:
            if len(devices) == 1:
                self.device_id = devices[0]
                print(f"自动选择唯一设备: {self.device_id}")
            else:
                print('可用设备:')
                for i, d in enumerate(devices, start=1):
                    print(f"  {i}: {d}")
                print('请指定device_id参数或使用命令行--device参数')
                return False
        else:
            if self.device_id not in devices:
                print(f"[ERROR] 指定设备 {self.device_id} 未在可用设备列表中")
                return False

        # 确保输出目录存在
        ensure_outdir(str(self.output_dir))

        return True

    def scan_for_updates(self) -> Tuple[List[str], List[str]]:
        """
        扫描需要更新的应用包和未记录的应用包

        返回值:
            Tuple[List[str], List[str]]: (需要更新的包名列表, 未记录的包名列表)
        """
        if not self.device_id:
            print("[ERROR] 设备ID未设置")
            return [], []

        print("\n[INFO] 开始扫描设备上的应用版本...")

        # 获取设备上的所有应用列表
        all_packages = pm_list_packages(self.device_id, None)
        
        # 定义系统应用前缀黑名单（这些前缀的应用通常是系统组件）
        system_prefixes = (
            'android.',
            'com.android.',
            'com.google.android.',
            'com.google.mainline.',
            'com.qualcomm.',
            'com.qti.',
            'vendor.',
            'com.mediatek.',
            'com.miui.',  # 小米系统应用
            'com.xiaomi.xmsf',  # 小米推送
            'com.coloros.',  # OPPO系统应用
            'com.oplus.',  # OPPO系统应用
            'com.heytap.',  # OPPO系统应用
            'com.oneplus.',  # 一加系统应用
            'com.samsung.',  # 三星系统应用
            'com.sec.',  # 三星系统应用
            'com.huawei.',  # 华为系统应用
            'com.hihonor.',  # 荣耀系统应用
            'com.vivo.',  # vivo系统应用
        )
        
        # 定义系统应用完整包名黑名单（精确匹配）
        system_packages_blacklist = {
            # Google 系统服务
            'com.google.android.gms',
            'com.google.android.gsf',
            'com.google.android.ext.services',
            'com.google.android.ext.shared',
            'com.google.android.webview',
            'com.google.android.trichromelibrary',
            'com.google.android.overlay',
            'com.google.android.permissioncontroller',
            'com.google.android.packageinstaller',
            'com.google.android.safetycenter.resources',
            'com.google.android.networkstack',
            'com.google.android.modulemetadata',
            'com.google.android.cellbroadcastreceiver',
            'com.google.android.configupdater',
            'com.google.android.providers.media.module',
            
            # 设备制造商系统应用（示例）
            'com.miui.securitycenter',
            'com.miui.analytics',
            'com.xiaomi.account',
            'com.coloros.safecenter',
            'com.oplus.safecenter',
            'com.heytap.cloud',
            'com.samsung.android.app.settings.bixby',
            'com.huawei.hwid',
            
            # 禁止更新的应用
            'com.android.chrome',  # Chrome浏览器（禁止更新）
        }
        
        # 定义白名单：这些应用即使匹配系统前缀也要保留
        whitelist_packages = {
            # 'com.android.vending',  # Google Play商店
            'com.google.android.youtube',  # YouTube
            # 'com.google.android.apps.maps',  # Google地图
            # 'com.google.android.gm',  # Gmail
            # 'com.google.android.apps.docs',  # Google文档
            # 'com.google.android.apps.photos',  # Google相册
        }
        
        # 过滤逻辑
        def is_valid_package(pkg):
            # 白名单直接通过
            if pkg in whitelist_packages:
                return True
            
            # 黑名单直接过滤
            if pkg in system_packages_blacklist:
                return False
            
            # 检查系统前缀
            for prefix in system_prefixes:
                if pkg.startswith(prefix):
                    return False
            
            # 其他应用保留
            return True
        
        installed_packages = [pkg for pkg in all_packages if is_valid_package(pkg)]
        
        print(f"[INFO] 设备上发现 {len(installed_packages)} 个第三方应用（已过滤 {len(all_packages) - len(installed_packages)} 个系统应用）")

        # 获取索引中的包列表
        indexed_packages = self.index_manager.get_all_packages()
        print(f"[INFO] 索引文件中包含 {len(indexed_packages)} 个应用记录")

        # 找出需要检查的交集和未记录的应用
        common_packages = set(installed_packages) & set(indexed_packages)
        unrecorded_packages = set(installed_packages) - set(indexed_packages)

        print(f"[INFO] 需要检查版本的应用: {len(common_packages)} 个")
        print(f"[INFO] 未记录的新应用: {len(unrecorded_packages)} 个")

        update_candidates = []
        unrecorded_candidates = list(unrecorded_packages)

        # 检查已记录应用的版本更新
        for package in common_packages:
            print(f"-> 检查包: {package}")

            # 获取设备上的版本信息
            device_info = get_package_info(self.device_id, package)
            device_version_code = device_info.get('version_code')
            device_version_name = device_info.get('version_name', 'unknown')

            if not device_version_code:
                print(f"   [WARN] 无法获取设备上 {package} 的版本信息，跳过")
                continue

            # 获取索引中的版本信息
            index_info = self.index_manager.get_package_version(package)
            if not index_info:
                print(f"   [WARN] 索引中未找到 {package} 的信息，跳过")
                continue

            index_version_code = index_info['version_code']
            index_version_name = index_info['version_name']

            # 打印版本对比信息
            print(f"   [VERSION] 设备版本: {device_version_code}({device_version_name})")
            print(f"   [VERSION] 索引版本: {index_version_code}({index_version_name})")

            # 比较版本
            needs_update = self.compare_versions(
                device_version_code, device_version_name,
                index_version_code, index_version_name
            )

            if needs_update:
                update_candidates.append(package)
                print(
                    f"   [UPDATE] 设备版本更新，将拉取: {device_version_code}({device_version_name}) > {index_version_code}({index_version_name})")
            else:
                print(f"   [SKIP] 设备版本不比索引新，跳过拉取")

        # 输出未记录的应用信息
        if unrecorded_candidates:
            print(f"\n[INFO] 未记录的应用将被下载:")
            for package in unrecorded_candidates:
                device_info = get_package_info(self.device_id, package)
                version_code = device_info.get('version_code', 'unknown')
                version_name = device_info.get('version_name', 'unknown')
                print(f"   -> {package} ({version_code}/{version_name})")

        self.update_candidates = update_candidates
        self.unrecorded_candidates = unrecorded_candidates

        print(f"\n[INFO] 发现 {len(update_candidates)} 个应用需要更新")
        print(f"[INFO] 发现 {len(unrecorded_candidates)} 个未记录应用需要下载")

        return update_candidates, unrecorded_candidates

    def compare_versions(self, device_version_code: str, device_version_name: str,
                         index_version_code: str, index_version_name: str) -> bool:
        """
        比较版本号，判断是否需要拉取

        参数:
            device_version_code (str): 设备上的版本代码
            device_version_name (str): 设备上的版本名称
            index_version_code (str): 索引中的版本代码
            index_version_name (str): 索引中的版本名称

        返回值:
            bool: 是否需要拉取（设备版本比索引版本新）
        """
        try:
            device_code = int(device_version_code)
            index_code = int(index_version_code)

            # 数字版本码比较（主要策略）：设备版本大于索引版本时拉取
            result = device_code > index_code
            print(f"   [DEBUG] 版本码比较: {device_code} > {index_code} = {result}")
            return result

        except (ValueError, TypeError):
            # 版本码无法转换为数字时，使用字符串比较
            result = device_version_code > index_version_code
            print(f"   [DEBUG] 字符串版本比较: {device_version_code} > {index_version_code} = {result}")
            return result

    def pull_updates(self, overwrite_mode: str = 'overwrite') -> Dict[str, Any]:
        """
        拉取需要更新的应用和未记录的应用

        参数:
            overwrite_mode (str): 文件覆盖模式

        返回值:
            Dict[str, Any]: 处理结果
        """
        if not self.device_id:
            print("[ERROR] 设备ID未设置")
            return {
                'success': False,
                'total_count': 0,
                'success_count': 0,
                'failed_count': 0,
                'update_count': 0,
                'new_count': 0,
                'results': {},
                'error': 'device_id_not_set'
            }

        all_candidates = self.update_candidates + self.unrecorded_candidates

        if not all_candidates:
            print("[INFO] 没有需要处理的应用")
            return {
                'success': True,
                'total_count': 0,
                'success_count': 0,
                'failed_count': 0,
                'update_count': 0,
                'new_count': 0,
                'results': {}
            }

        print(f"\n[INFO] 开始拉取应用...")
        if self.update_candidates:
            print(f"   - 更新应用: {len(self.update_candidates)} 个")
        if self.unrecorded_candidates:
            print(f"   - 新应用: {len(self.unrecorded_candidates)} 个")

        # 使用现有的pull_packages函数进行批量拉取
        detailed_results = pull_packages(
            self.device_id,
            all_candidates,
            self.output_dir,
            keep_temp=False,
            overwrite_mode=overwrite_mode
        )

        # 统计结果
        success_count = sum(1 for v in detailed_results.values() if v.get('ok'))
        failed_count = len(all_candidates) - success_count

        self.processing_results = {
            'success': success_count > 0,
            'total_count': len(all_candidates),
            'success_count': success_count,
            'failed_count': failed_count,
            'update_count': len(self.update_candidates),
            'new_count': len(self.unrecorded_candidates),
            'results': detailed_results
        }

        return self.processing_results

    def generate_update_report(self) -> Tuple[str, List[str]]:
        """
        生成更新报告并返回成功处理的包名列表

        返回值:
            Tuple[str, List[str]]: (报告文件路径, 成功更新的包名列表)
        """
        if not self.processing_results:
            return "", []

        # 收集成功处理的包名列表
        updated_packages_list = []

        # 准备报告数据
        report_data = {
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'device_id': self.device_id,
            'output_directory': str(self.output_dir),
            'index_file': str(self.index_manager.index_file_path),
            'scan_summary': {
                'update_candidates_found': len(self.update_candidates),
                'new_apps_found': len(self.unrecorded_candidates),
                'total_processed': self.processing_results['total_count'],
                'successful_downloads': self.processing_results['success_count'],
                'failed_downloads': self.processing_results['failed_count']
            },
            'update_details': self.processing_results['results'],
            'updated_packages': []
        }

        # 收集成功下载的包信息
        for package, result in self.processing_results['results'].items():
            if result.get('ok'):
                # 添加到成功处理的文件名列表（包含扩展名）
                output_file_path = result.get('path', '')
                if output_file_path:
                    # 提取文件名（包含扩展名）
                    filename = os.path.basename(output_file_path)
                    updated_packages_list.append(filename)

                # 区分更新应用和新应用
                is_update = package in self.update_candidates
                package_info = {
                    'package_name': package,
                    'output_file': result.get('path', ''),
                    'file_type': result.get('type', ''),
                    'is_update': is_update
                }

                if is_update:
                    # 更新应用，获取索引中的版本信息
                    index_info = self.index_manager.get_package_version(package)
                    if index_info:
                        package_info.update({
                            'target_version_code': index_info['version_code'],
                            'target_version_name': index_info['version_name']
                        })
                else:
                    # 新应用，获取设备上的版本信息
                    if self.device_id:
                        device_info = get_package_info(self.device_id, package)
                        package_info.update({
                            'device_version_code': device_info.get('version_code', 'unknown'),
                            'device_version_name': device_info.get('version_name', 'unknown')
                        })

                report_data['updated_packages'].append(package_info)

        # 保存报告
        report_file = self.output_dir / 'update_report.json'
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        return str(report_file), updated_packages_list


def smart_update_external(device_serial: Optional[str] = None,
                          output_dir: str = r'',
                          index_file: str = r'',
                          overwrite_mode: str = 'overwrite',
                          scan_only: bool = False) -> Dict[str, Any]:
    """
    外部调用接口 - 智能APK更新拉取

    根据global_index.json文件智能拉取手机上版本更新的应用包

    参数:
        device_serial (Optional[str]): 设备序列号
        output_dir (str): 输出目录路径
        index_file (str): global_index.json文件路径
        overwrite_mode (str): 文件覆盖模式
        scan_only (bool): 仅扫描不拉取，用于检查更新

    返回值:
        Dict[str, Any]: 处理结果字典，包含updated_packages_list字段
    """
    result = {
        'success': False,
        'scan_completed': False,
        'updates_available': 0,
        'new_apps_available': 0,
        'updates_processed': 0,
        'updates_successful': 0,
        'updates_failed': 0,
        'update_apps_count': 0,
        'new_apps_count': 0,
        'device_used': '',
        'output_directory': '',
        'report_file': '',
        'update_candidates': [],
        'unrecorded_candidates': [],
        'detailed_results': {},
        'updated_packages_list': [],
        'error_message': None
    }

    try:
        # 初始化更新器
        updater = SmartAPKUpdater(device_serial, output_dir, index_file)

        if not updater.initialize():
            result['error_message'] = '更新器初始化失败'
            return result

        result['device_used'] = updater.device_id
        result['output_directory'] = str(updater.output_dir)

        # 扫描更新和未记录应用
        update_candidates, unrecorded_candidates = updater.scan_for_updates()
        result['scan_completed'] = True
        result['updates_available'] = len(update_candidates)
        result['new_apps_available'] = len(unrecorded_candidates)
        result['update_candidates'] = update_candidates
        result['unrecorded_candidates'] = unrecorded_candidates

        total_candidates = len(update_candidates) + len(unrecorded_candidates)
        if not total_candidates:
            result['success'] = True
            result['error_message'] = '没有发现需要处理的应用'
            return result

        if scan_only:
            result['success'] = True
            print(f"[INFO] 仅扫描模式：")
            print(f"   - 可更新应用: {len(update_candidates)} 个")
            print(f"   - 未记录应用: {len(unrecorded_candidates)} 个")
            return result

        # 执行更新拉取
        pull_results = updater.pull_updates(overwrite_mode)

        result['updates_processed'] = pull_results['total_count']
        result['updates_successful'] = pull_results['success_count']
        result['updates_failed'] = pull_results['failed_count']
        result['update_apps_count'] = pull_results['update_count']
        result['new_apps_count'] = pull_results['new_count']
        result['detailed_results'] = pull_results['results']
        result['success'] = pull_results['success']

        # 生成报告并获取成功处理的包名列表
        report_file, updated_packages_list = updater.generate_update_report()
        result['report_file'] = report_file
        result['updated_packages_list'] = updated_packages_list

        print(f"\n=== 处理完成 ===")
        print(f"发现更新: {result['updates_available']} 个")
        print(f"发现新应用: {result['new_apps_available']} 个")
        print(f"处理成功: {result['updates_successful']}/{result['updates_processed']}")
        print(f"成功处理的包: {updated_packages_list}")
        if report_file:
            print(f"详细报告: {report_file}")

        return result

    except Exception as e:
        result['error_message'] = f'执行过程中发生异常: {str(e)}'
        print(f"[ERROR] {result['error_message']}")
        return result


def main():
    """主函数 - 命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description='智能APK更新拉取工具')
    parser.add_argument('--device', '-d', help='设备序列号')
    parser.add_argument('--output', '-o', default=r'E:\Desktop\local_app_repo', help='输出目录')
    parser.add_argument('--index', '-i', default=r'E:\Desktop\global_index_remote.json', help='全局索引文件路径')
    parser.add_argument('--overwrite', choices=['overwrite', 'skip', 'rename'], default='overwrite',
                        help='文件冲突处理方式')
    parser.add_argument('--scan-only', action='store_true', help='仅扫描可更新应用，不执行拉取')

    args = parser.parse_args()

    # 执行更新
    result = smart_update_external(
        device_serial=args.device,
        output_dir=args.output,
        index_file=args.index,
        overwrite_mode=args.overwrite,
        scan_only=args.scan_only
    )

    # 输出成功处理的包名列表
    if result.get('updated_packages_list'):
        print(f"\n成功处理的包名列表: {result['updated_packages_list']}")

    # 根据结果设置退出码
    if result['success']:
        sys.exit(0)
    else:
        print(f"执行失败: {result.get('error_message', '未知错误')}")
        sys.exit(1)


def pull_specific_packages(device_serial=None, package_names=None, output_dir=None):
    """
    从手机拉取指定包名的 APK/XAPK
    
    参数:
        device_serial (str, optional): 设备序列号，不指定则自动选择唯一设备
        package_names (list, optional): 要拉取的包名列表
        output_dir (str, optional): 输出目录路径
    
    返回:
        dict: 拉取结果
    """
    # 默认参数
    if package_names is None:
        package_names = ['com.android.chrome']  # 默认拉取 Chrome
    
    if output_dir is None:
        output_dir = r'D:\pulled_apks'  # 默认输出目录
    
    # 确保输出目录存在
    outdir = ensure_outdir(output_dir)
    print(f"[INFO] 输出目录: {outdir}")
    
    # 检查设备
    devices = list_devices()
    if not devices:
        print('[ERROR] 没有发现任何 ADB 设备，请确保设备已连接并授权 ADB 调试')
        return {'success': False, 'error': 'no_devices'}
    
    # 选择设备
    if not device_serial:
        if len(devices) == 1:
            device_serial = devices[0]
            print(f"[INFO] 自动选择唯一设备: {device_serial}")
        else:
            print('[ERROR] 发现多个设备，请指定 device_serial 参数:')
            for i, d in enumerate(devices, start=1):
                print(f"  {i}: {d}")
            return {'success': False, 'error': 'multiple_devices'}
    else:
        if device_serial not in devices:
            print(f"[ERROR] 指定设备 {device_serial} 未在可用设备列表中")
            return {'success': False, 'error': 'device_not_found'}
    
    print(f"[INFO] 使用设备: {device_serial}")
    print(f"[INFO] 要拉取的包: {package_names}")
    
    # 执行拉取
    print("\n" + "="*60)
    print("开始拉取应用...")
    print("="*60 + "\n")
    
    results = pull_packages(
        device=device_serial,
        package_list=package_names,
        outdir=outdir,
        keep_temp=False,
        overwrite_mode='overwrite'  # 覆盖已存在的文件
    )
    
    # 输出结果
    print("\n" + "="*60)
    print("拉取完成！")
    print("="*60 + "\n")
    
    success_count = 0
    failed_count = 0
    
    for pkg, result in results.items():
        if result.get('ok'):
            success_count += 1
            print(f"✓ {pkg}")
            print(f"  类型: {result.get('type', 'unknown')}")
            print(f"  路径: {result.get('path', 'unknown')}")
            if result.get('parts'):
                print(f"  包含文件数: {len(result['parts'])}")
        else:
            failed_count += 1
            print(f"✗ {pkg}")
            print(f"  失败原因: {result.get('reason', 'unknown')}")
        print()
    
    print(f"成功: {success_count}/{len(package_names)}")
    print(f"失败: {failed_count}/{len(package_names)}")
    
    return {
        'success': success_count > 0,
        'total': len(package_names),
        'success_count': success_count,
        'failed_count': failed_count,
        'results': results,
        'output_dir': str(outdir)
    }


def test_pull_examples():
    """测试示例函数"""
    # 示例 1: 拉取单个应用（Chrome，会自动拉取 trichrome 依赖）
    print("示例 1: 拉取 Chrome（自动包含依赖库）")
    print("-" * 60)
    result1 = pull_specific_packages(
        device_serial=None,  # 自动选择设备
        package_names=['com.android.chrome'],
        output_dir=r'D:\chrome_backup'
    )
    print("\n\n")
    
    # 示例 2: 拉取多个应用到指定目录
    print("示例 2: 拉取多个应用")
    print("-" * 60)
    result2 = pull_specific_packages(
        device_serial=None,
        package_names=[
            'com.whatsapp',
            'com.tencent.mm',  # 微信
            'com.ss.android.ugc.aweme',  # 抖音
        ],
        output_dir=r'D:\apps_backup'
    )
    print("\n\n")
    
    # 示例 3: 指定设备拉取
    print("示例 3: 从指定设备拉取")
    print("-" * 60)
    result3 = pull_specific_packages(
        device_serial='1410925519000179',  # 替换为你的设备序列号
        package_names=['com.android.vending'],  # Google Play
        output_dir=r'D:\play_store_backup'
    )
    
    print("\n所有示例执行完成！")


if __name__ == '__main__':
    # 默认执行命令行模式
    # 如果需要运行测试示例，可以注释下面一行，取消注释 test_pull_examples()
    main()
    
    # 运行测试示例（取消下面的注释可执行）
    # test_pull_examples()