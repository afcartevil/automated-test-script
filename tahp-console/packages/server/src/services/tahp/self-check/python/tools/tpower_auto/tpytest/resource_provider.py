import os
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Tuple, Union

from powertrde.framework.logs_protocol import logs_p
from powertrde.utils.feishu.feishu_api_helper import FeishuApiHelper


# -------------------- 异常体系 --------------------
class ResourceProviderError(Exception):
    """资源提供器基础异常"""
    pass


class PathResolutionError(ResourceProviderError):
    """路径解析异常"""


class ProviderConnectionError(ResourceProviderError):
    """连接相关异常"""


class TransferError(ResourceProviderError):
    """传输过程异常"""


class PathWriteError(ResourceProviderError):
    """路径写入异常"""


# -------------------- 基类实现 --------------------
class BaseResourceProvider(ABC):
    TEMP_SUFFIX = ".download"

    def __init__(self):
        self._temp_manager = TempFileManager()

    @abstractmethod
    def _raw_download(self, full_remote_path: str, local_path: str):
        """子类实现具体下载逻辑（接收完整路径）"""
        pass

    @abstractmethod
    def _raw_upload(self, local_path: str, full_remote_path: str):
        """子类实现具体上传逻辑（接收完整路径）"""
        pass

    @abstractmethod
    def _raw_delete(self, full_remote_path: str):
        """子类实现具体删除逻辑"""
        pass

    @abstractmethod
    def list_contents(self, remote_path: str) -> List[Tuple[str, bool]]:
        """列出目录内容"""

    @abstractmethod
    def resolve_remote_path(self, remote_path: str) -> str:
        """解析完整的远程路径"""

    @abstractmethod
    def is_directory(self, remote_path: str) -> bool:
        """判断路径是否为文件夹"""
        pass

    def is_exists(self, remote_path: str) -> bool:
        """判断路径是否存在"""
        try:
            self.is_directory(remote_path)
            return True
        except Exception:
            return False

    def get_path_type(self, remote_path: str):
        """
        获取路径类型（‘文件夹’或‘文件’或‘路径不存在’）
        :return: 'dir' | 'file' | 'not_exists'
        """
        try:
            if self.is_directory(remote_path):
                return 'dir'
            return 'file'
        except PathResolutionError:
            return 'not_exists'

    @abstractmethod
    def create_directory(self, remote_path: str):
        """创建远程目录（包含父目录）"""
        pass

    def download(self,
                 remote_path: str,
                 local_path: Union[str, Path],
                 overwrite: bool = True) -> str:
        """
        安全下载主入口
        :param remote_path: 远程资源路径（相对路径）
        :param local_path: 本地目标路径（文件或目录）
        :param overwrite: 是否覆盖现有文件
        :return: 实际保存路径
        """
        final_path = self._resolve_local_path(local_path, remote_path)

        if self.is_directory(remote_path):
            if not final_path.exists():
                final_path.mkdir(parents=True, exist_ok=True)

            for entry, is_dir in self.list_contents(remote_path):
                sub_remote_path = f"{remote_path}/{entry}"
                sub_local_path = final_path / entry
                if is_dir:
                    self.download(sub_remote_path, sub_local_path, overwrite)
                else:
                    self._download_file(sub_remote_path, sub_local_path, overwrite)
            return str(final_path)
        else:
            return self._download_file(remote_path, final_path, overwrite)

    def _download_file(self, remote_path: str, local_path: Path, overwrite: bool) -> str:
        if local_path.exists() and not overwrite:
            return str(local_path)

        with self._temp_manager.create_temp_dir() as temp_dir:
            temp_file = Path(temp_dir) / "download.tmp"
            remote_full = self.resolve_remote_path(remote_path)

            try:
                self._raw_download(remote_full, str(temp_file))
                self._verify_download(temp_file, remote_full)
                return self._atomic_save(temp_file, local_path)
            except Exception as e:
                self._cleanup_failed_download(temp_file, local_path)
                raise ResourceProviderError(f"下载失败: {str(e)}")

    def upload(self,
               local_path: Union[str, Path],
               remote_path: str,
               overwrite: bool = True) -> str:
        """
        安全上传主入口
        :param local_path: 本地源路径（文件或目录）
        :param remote_path: 远程目标路径（相对路径）
        :param overwrite: 是否覆盖现有文件
        :return: 实际保存路径
        """
        local_path_resolved = Path(local_path).resolve()
        if not local_path_resolved.exists():
            raise FileNotFoundError(f"本地路径不存在: {local_path_resolved}")

        final_remote_path = self.resolve_remote_path(remote_path)
        if remote_path.endswith(('/', '\\')) and not local_path.endswith(('/', '\\')):
            final_remote_path = os.path.join(final_remote_path, os.path.basename(local_path_resolved))

        if local_path_resolved.is_dir():
            self._upload_directory(local_path_resolved, final_remote_path, overwrite)
            return final_remote_path
        else:
            return self._upload_file(local_path_resolved, final_remote_path, overwrite)

    def _upload_directory(self, local_dir: Path, remote_path: str, overwrite: bool):
        """递归上传目录（自动创建路径）"""
        try:
            # 先尝试创建目标目录
            self.create_directory(remote_path)
        except Exception as e:
            raise TransferError(f"创建远程目录失败: {remote_path}") from e

        # 原有递归上传逻辑保持不变
        for item in local_dir.iterdir():
            remote_item_path = f"{remote_path}/{item.name}"
            if item.is_dir():
                self._upload_directory(item, remote_item_path, overwrite)
            else:
                self._upload_file(item, remote_item_path, overwrite)

    def _upload_file(self, local_file: Path, remote_path: str, overwrite: bool) -> str:
        _path_type = self.get_path_type(remote_path)
        if _path_type == 'dir':
            self._raw_delete(remote_path)
            # raise PathWriteError(f"不能覆盖目录: {remote_path}")

        if not overwrite and _path_type == 'file':
            return remote_path

        try:
            self._raw_upload(str(local_file), remote_path)
            return remote_path
        except Exception as e:
            self._cleanup_failed_upload(remote_path)
            raise TransferError(f"上传失败: {str(e)}")

    def _verify_upload(self, temp_file: Path, original_file: Path):
        """上传前校验"""
        if temp_file.stat().st_size != original_file.stat().st_size:
            raise TransferError("临时文件大小不匹配")
        # 可扩展添加哈希校验

    def _cleanup_failed_upload(self, remote_path: str):
        """清理失败上传"""
        try:
            if self.is_exists(remote_path):
                # 子类需实现具体删除逻辑
                self._raw_delete(remote_path)
        except Exception:
            pass

    def push_to_device(self,
                       remote_path: str,
                       device_id: str,
                       device_path: str,
                       retries: int = 0,
                       overwrite_exists: bool = True):
        """一站式推送到设备"""
        with self._temp_manager.create_temp_dir() as temp_dir:
            downloaded_path = self.download(remote_path, temp_dir)
            self._adb_push_with_retry(downloaded_path, device_id, device_path, retries, overwrite_exists)

    def _resolve_local_path(self, user_path: Union[str, Path], remote_path: str) -> Path:
        """智能解析本地路径"""
        user_path_is_dir = False
        if isinstance(user_path, str) and user_path.endswith(('/', '\\')):
            user_path_is_dir = True
        target = Path(user_path).resolve()
        remote_name = Path(remote_path).name

        # 处理目录路径
        if target.exists() and target.is_dir():
            return target / remote_name

        # 处理不存在的路径
        if not target.exists():
            # 以分隔符结尾视为目录
            if user_path_is_dir:
                target.mkdir(parents=True, exist_ok=True)
                return target / remote_name
            # 确保父目录存在
            target.parent.mkdir(parents=True, exist_ok=True)

        return target

    def _atomic_save(self, temp_file: Path, final_path: Path) -> str:
        """原子保存文件"""
        if final_path.exists():
            final_path.unlink()
        shutil.move(str(temp_file), str(final_path))
        return str(final_path)

    def _adb_push_with_retry(self,
                             local_path: str,
                             device_id: str,
                             device_path: str,
                             max_retries: int,
                             overwrite_exists: bool):
        """带重试的ADB推送"""
        for attempt in range(max_retries + 1):
            try:
                # subprocess.check_call([ADB_EXE, "-s", device_id, "push", local_path, device_path])
                self.local_adb_push(device_id, local_path, device_path, overwrite_exists)
            except Exception as e:
                if attempt == max_retries:
                    raise
                time.sleep(2 ** attempt)

    def _verify_download(self, temp_file: Path, remote_path: str):
        """下载校验（可扩展）"""
        if not temp_file.exists():
            raise TransferError("临时文件未生成")
        if temp_file.stat().st_size == 0:
            raise TransferError("下载文件内容为空")

    def _cleanup_failed_download(self, temp_file: Path, final_path: Path):
        """清理失败下载"""
        if temp_file.exists():
            temp_file.unlink()
        if final_path.exists() and final_path.stat().st_size == 0:
            final_path.unlink()

    def test_connection(self):
        """连接检测"""

    @staticmethod
    def local_adb_push(device_id: str, src_path: Union[str, os.PathLike], target_path: Union[str, os.PathLike],
                       overwrite=True):
        """
        将文件或文件夹推送到Android设备的指定路径。

        :param device_id: 设备的唯一标识符（SN）
        :param src_path: 源文件或文件夹路径
        :param target_path: 目标路径
        :param overwrite: 如果为True，允许覆盖已存在的文件；否则跳过
        """
        from powertrde.utils.trde import adb
        adb.push_file_ext(device_id, src_path, target_path, overwrite)

    def open_in_explorer(self, path: Union[str, os.PathLike]):
        """在浏览器打开"""


# -------------------- NAS提供器（下载速度慢，不再使用） --------------------
# class NASProvider(BaseResourceProvider):
#     """
#     基于 smbclient 的 NAS 资源提供器，实现 SMB 文件共享的访问。
#     支持文件/目录的创建、上传、下载、删除及内容列举。
#
#     :param server: NAS 服务器地址（IP 或主机名）
#     :param share: 共享名称
#     :param base_path: 共享内基础子路径，如 'folder/sub'
#     :param username: 登录用户名
#     :param password: 登录密码
#     """
#     def __init__(
#         self,
#         server: str,
#         share: str,
#         base_path: str = '',
#         username: str = '',
#         password: str = ''
#     ):
#         super().__init__()
#         self.server = server.strip('/\\')
#         self.share = share.strip('/\\')
#         self.base_path = base_path.strip('/\\')
#         self.username = username
#         self.password = password
#         self._session_registered = False
#
#     def _connect_smb(self):
#         if not self._session_registered:
#             try:
#                 smbclient.register_session(
#                     server=self.server,
#                     username=self.username,
#                     password=self.password,
#                     port=445,
#                     connection_timeout=5
#                 )
#                 self._session_registered = True
#             except Exception as e:
#                 raise ProviderConnectionError(f"SMB 连接失败: {e}")
#
#     def _get_unc_path(self, remote_path: str) -> str:
#         parts = [self.base_path] if self.base_path else []
#         parts += [seg for seg in remote_path.strip('/\\').split('/') if seg]
#         p = PureWindowsPath('\\', self.server, self.share, *parts)
#         return str(p)
#
#     def resolve_remote_path(self, relative_path: str) -> str:
#         # 基类逻辑：将相对路径解析为 UNC 完整路径
#         return self._get_unc_path(relative_path)
#
#     def create_directory(self, remote_path: str):
#         self._connect_smb()
#         unc = self.resolve_remote_path(remote_path)
#         segments = PureWindowsPath(unc).parts[3:]
#         base = PureWindowsPath('\\', self.server, self.share)
#         for seg in segments:
#             base = PureWindowsPath(base, seg)
#             try:
#                 smbclient.mkdir(str(base))
#             except SMBException as e:
#                 if 'STATUS_OBJECT_NAME_COLLISION' in str(e) or 'File exists' in str(e):
#                     continue
#                 raise TransferError(f"创建目录失败: {base}: {e}")
#
#     def is_directory(self, remote_path: str) -> bool:
#         self._connect_smb()
#         unc = self.resolve_remote_path(remote_path)
#         try:
#             return smbclient.path.isdir(unc)
#         except SMBException as e:
#             raise PathResolutionError(f"判断目录失败: {unc}: {e}")
#
#     def list_contents(self, remote_path: str) -> List[Tuple[str, bool]]:
#         self._connect_smb()
#         unc = self.resolve_remote_path(remote_path)
#         try:
#             entries = smbclient.scandir(unc)
#         except SMBException as e:
#             raise PathResolutionError(f"列举目录失败: {unc}: {e}")
#         result = []
#         for entry in entries:
#             is_dir = False
#             try:
#                 is_dir = entry.is_dir()
#             except Exception:
#                 pass
#             result.append((entry.name, is_dir))
#         return result
#
#     def _raw_download(self, full_unc_path: str, local_path: str):
#         """full_unc_path 已为 UNC 完整路径"""
#         self._connect_smb()
#         try:
#             if not smbclient.path.exists(full_unc_path):
#                 raise FileNotFoundError(f"远程文件不存在: {full_unc_path}")
#             with smbclient.open_file(full_unc_path, mode='rb') as remote_file, \
#                  open(local_path, 'wb') as local_file:
#                 shutil.copyfileobj(remote_file, local_file, length=65535)
#         except SMBException as e:
#             raise TransferError(f"下载失败: {full_unc_path}: {e}")
#
#     def _raw_upload(self, local_path: str, full_unc_path: str):
#         """full_unc_path 已为 UNC 完整路径"""
#         self._connect_smb()
#         try:
#             with open(local_path, 'rb') as local_file, \
#                  smbclient.open_file(full_unc_path, mode='wb') as remote_file:
#                 shutil.copyfileobj(local_file, remote_file, length=65535)
#         except SMBException as e:
#             raise TransferError(f"上传失败: {full_unc_path}: {e}")
#
#     def _raw_delete(self, full_unc_path: str):
#         """full_unc_path 已为 UNC 完整路径"""
#         self._connect_smb()
#         try:
#             if smbclient.path.isdir(full_unc_path):
#                 smbclient.rmdir(full_unc_path)
#             else:
#                 smbclient.remove(full_unc_path)
#         except SMBException as e:
#             raise TransferError(f"删除失败: {full_unc_path}: {e}")
#
#     def test_connection(self) -> bool:
#         try:
#             _ = self.list_contents('')
#             return True
#         except Exception as e:
#             t_log.warning(f"连接测试失败: {e}")
#             return False


# -------------------- 本地提供器 --------------------
class LocalProvider(BaseResourceProvider):
    def __init__(self, base_path: str):
        super().__init__()
        self.base_path = self._resolve_base_path(base_path)

    def _raw_upload(self, local_path: str, full_remote_path: str):
        """本地文件上传实现"""
        remote_path = Path(full_remote_path)
        is_remote_exists = remote_path.exists()
        if is_remote_exists and remote_path.is_dir():
            raise TransferError("不能上传文件到已存在的目录路径")

        # 创建父目录
        remote_path.parent.mkdir(parents=True, exist_ok=True)

        temp_dst = Path(str(remote_path) + '.tmp')
        if temp_dst.exists():
            temp_dst.unlink()
        try:
            shutil.copy2(local_path, temp_dst)
            if is_remote_exists:
                os.remove(remote_path)
            os.rename(temp_dst, remote_path)
        finally:
            if temp_dst.exists():
                temp_dst.unlink()

    def _raw_delete(self, full_remote_path: str):
        """本地文件删除"""
        path = Path(full_remote_path)
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

    def is_exists(self, remote_path: str) -> bool:
        """优化存在性检查"""
        return (self.base_path / remote_path.lstrip('/\\')).exists()

    def _resolve_base_path(self, raw_path: str) -> Path:
        """解析并验证基础路径"""
        path = Path(raw_path).expanduser().resolve()

        if not path.exists():
            raise PathResolutionError(f"本地路径不存在: {raw_path}")
        if not path.is_dir():
            raise PathResolutionError(f"必须指定目录路径: {raw_path}")

        return path

    def create_directory(self, remote_path: str):
        full_path = Path(self.resolve_remote_path(remote_path))
        if not full_path.exists():
            full_path.mkdir(parents=True, exist_ok=True)

    def resolve_remote_path(self, relative_path: str) -> str:
        """解析完整本地路径"""
        return str(self.base_path / relative_path.lstrip('/\\'))

    def is_directory(self, remote_path: str) -> bool:
        full_path = self.base_path / remote_path.lstrip('/\\')
        if not full_path.exists():
            raise PathResolutionError(f"Path not exists: {full_path}")
        return full_path.is_dir()

    def list_contents(self, remote_path: str) -> List[Tuple[str, bool]]:
        full_path = self.base_path / remote_path.lstrip('/\\')

        if not full_path.exists():
            raise PathResolutionError(f"Path not exists: {full_path}")
        if not full_path.is_dir():
            raise PathResolutionError(f"Path not a dir: {full_path}")

        return [(child.name, child.is_dir()) for child in full_path.iterdir()]

    def _raw_download(self, full_remote_path: str, local_path: str):
        """本地文件复制"""
        source = Path(full_remote_path)

        if not source.exists():
            raise FileNotFoundError(f"源文件不存在: {source}")

        shutil.copy2(str(source), local_path)

    def test_connection(self):
        return os.path.exists(self.base_path)

    def push_to_device(self,
                       remote_path: str,
                       device_id: str,
                       device_path: str,
                       retries: int = 0,
                       overwrite_exists: bool = True):
        """一站式推送到设备"""
        self._adb_push_with_retry(self.resolve_remote_path(remote_path), device_id, device_path, retries,
                                  overwrite_exists)

    def open_in_explorer(self, path: Union[str, os.PathLike]):
        os.startfile(os.path.join(self.base_path, path))


class WindowsUNCProvider(LocalProvider):
    """专用于 Windows UNC 路径的优化提供器"""

    def __init__(self, unc_path: str, username: str = '', password: str = ''):
        # 先保存凭据
        self._save_windows_credentials(unc_path, username, password)
        super().__init__(unc_path)

    def _save_windows_credentials(self, unc_path: str, username: str, password: str):
        """使用 Windows cmdkey 保存凭据"""
        try:
            # 提取服务器地址（如 \\10.205.101.200）
            server = unc_path.split('\\')[2]

            # 执行命令行保存凭据
            subprocess.run(
                f'cmdkey /add:{server} /user:{username} /pass:{password}',
                check=True,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            raise ProviderConnectionError(f"无法保存 Windows 凭据: {str(e)}")


# -----------------------------------------------

class LinuxNASProvider(LocalProvider):
    """
    Linux NAS 提供器，实现 CIFS/NFS 挂载并提供本地访问体验。
    支持自动回退挂载点到用户家目录下，避免权限问题。

    :param server: NAS 服务器地址（IP 或主机名）
    :param share: 共享名称
    :param mount_point: 本地挂载点（默认自动选择）
    :param fs_type: 文件系统类型，支持 'cifs' 或 'nfs'
    :param username: 用户名（仅 CIFS）
    :param password: 密码（仅 CIFS）
    :param options: 挂载选项（如 'rw,vers=3.0'）
    """

    def __init__(
            self,
            server: str,
            share: str,
            mount_point: Union[str, Path] = None,
            fs_type: str = 'cifs',
            username: str = '',
            password: str = '',
            options: str = 'vers=2.0',
            base_path: str = ''
    ):
        self.server = server
        self.share = share
        self.fs_type = fs_type.lower()
        self.username = username
        self.password = password
        self.options = options
        self.base_path = base_path

        # 选择挂载点，优先使用用户指定，否则自动生成
        name = ''
        if mount_point:
            mp = Path(mount_point)
        else:
            name = f"{self.server.replace('.', '_')}_{self.share.replace('/', '_')}"
            mp = Path('/mnt') / name

        # 创建挂载点，若无权限，则回退到用户家目录
        try:
            mp.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            fallback = Path.home() / '.cache' / 'nas_mounts'
            if name:
                fallback = fallback / name
            fallback.mkdir(parents=True, exist_ok=True)
            mp = fallback
        self.mount_point = mp.resolve()
        # print("确保已挂载，mount_point:", self.mount_point)
        # 确保已挂载
        self._ensure_mounted()
        # print("已挂载完成")
        super().__init__(base_path)

    def _ensure_mounted(self):
        # 已挂载检查
        try:
            subprocess.run(['mountpoint', '-q', str(self.mount_point)], check=True)
            # print("已挂载检查通过")
            return
        except subprocess.CalledProcessError:
            pass

        # 构建 mount 命令
        target = f"//{self.server}/{self.share}" if self.fs_type == 'cifs' else f"{self.server}:/{self.share}"
        cmd = ['sudo', 'mount', '-t', self.fs_type, target, str(self.mount_point)]
        opts = []
        if self.fs_type == 'cifs' and (self.username or self.password):
            if self.username:
                opts.append(f"username={self.username}")
            if self.password:
                opts.append(f"password={self.password}")
        if self.options:
            opts.append(self.options)

        if opts:
            # cmd.insert(-1, '-o')
            # cmd.insert(-1, ','.join(opts))
            cmd.append('-o')
            cmd.append(','.join(opts))
        try:
            # print("执行 mount 命令 cmd:", ' '.join(cmd))
            subprocess.run(cmd, check=True)
        except Exception as e:
            raise ProviderConnectionError(f"挂载 NAS 失败: {e}")


# -------------------- 工厂类 --------------------
class ResourceProviderFactory:
    @staticmethod
    def create(source: str, **kwargs) -> BaseResourceProvider:
        """
        智能创建资源提供器
        :param source: 支持格式：
            - smb://server/share/path
            - \\\\server\\share\\path (Windows网络路径)
            - /local/path
            - file:///local/path
        """
        # # 规范化路径处理
        # source = source.replace('\\', '/').strip()
        #
        # # 修复Windows路径处理
        # if source.startswith("//"):
        #     source = f"smb:{source}"

        # 临时强制将smb路径改为Windows映射实现，增加复制速度
        if source.startswith('smb://'):
            source = source.replace('smb://', '\\\\').replace('/', '\\')

        if source.startswith('smb://'):
            parsed = urllib.parse.urlparse(source)
            if not parsed.hostname:
                raise ValueError("无效SMB路径，缺少服务器地址")

            path_parts = parsed.path.strip('/').split('/')
            if len(path_parts) < 1:
                raise ValueError("SMB路径必须包含共享名称")

            # 关键修复：正确分离路径成分
            server = parsed.hostname
            share = path_parts[0]
            base_path = '/'.join(path_parts[1:]) if len(path_parts) > 1 else ''

            # logs_p().log_debug(f"创建NAS提供器: server={server}, share={share}, base_path={base_path}")
            # return NASProvider(
            #     server=server,
            #     share=share,
            #     base_path=base_path,
            #     **kwargs
            # )
            raise NotImplementedError('NAS提供器下载速度慢，暂不提供服务')
        elif source.startswith('\\\\'):
            if os.name == 'nt':
                return WindowsUNCProvider(source, **kwargs)
            else:
                def parse_path_windows_to_linux(path):
                    # 替换反斜杠为正斜杠
                    _linux_path = path.replace('\\', '/').strip('/')
                    # 使用正斜杠分割路径
                    _parts = _linux_path.split('/')
                    # 获取第一项、第二项和剩余部分
                    _server = _parts[0] if len(_parts) > 0 else None
                    _share = _parts[1] if len(_parts) > 1 else None
                    _remaining = '/'.join(_parts[2:]) if len(_parts) > 2 else None
                    return _linux_path, _server, _share, _remaining

                linux_path, server, share, remaining = parse_path_windows_to_linux(source)
                name = f"{server.replace('.', '_')}_{share.replace('/', '_')}"
                mp = Path('/mnt') / name
                mount_point = mp.resolve()
                base_path = os.path.join(str(mount_point), str(remaining))
                return LinuxNASProvider(server, share, base_path=base_path, mount_point=mount_point, **kwargs)
        else:
            return LocalProvider(source)


# -------------------- 工具类 --------------------
class TempFile:
    def __init__(self):
        self.file_descriptor = None
        self.path = None

    def __enter__(self):
        self.file_descriptor, self.path = tempfile.mkstemp()
        return self.path

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file_descriptor is not None:
            os.close(self.file_descriptor)
            self.file_descriptor = None  # 确保文件描述符被关闭
        try:
            os.remove(self.path)
        except PermissionError as e:
            logs_p().log_error(f"Error removing file {self.path}: {e}")


class TempFileManager:
    def create_temp_file(self):
        """返回一个支持上下文管理的临时文件"""
        return TempFile()

    def create_temp_dir(self) -> tempfile.TemporaryDirectory:
        """返回临时目录上下文"""
        return tempfile.TemporaryDirectory()


class FeishuProvider(BaseResourceProvider):
    def __init__(self, feishu_ins: FeishuApiHelper, root_folder_name: str):
        # 默认token文件夹是快温省_PPT
        super().__init__()
        self.feishu_ins = feishu_ins
        self.root_folder_name = root_folder_name

    def _raw_upload(self, local_path: str, full_remote_path: str = "功耗/DOU3测试数据"):
        """本地文件上传飞书实现"""
        try:
            file = self.feishu_ins.search_folder_recursive(self.feishu_ins.get_root_folder_token(self.root_folder_name),
                                                           full_remote_path)
            self.feishu_ins.upload_folder_auto(local_path, file["token"])
        except Exception as e:
            print(f"Error during upload: {e}")

    def _raw_download(self, full_remote_path: str, local_path: str):
        """子类实现具体下载逻辑（接收完整路径）"""
        try:
            file = self.feishu_ins.search_folder_recursive(self.feishu_ins.get_root_folder_token(self.root_folder_name),
                                                           full_remote_path)
            self.feishu_ins.download_file_auto(file["token"], os.path.dirname(local_path), os.path.basename(local_path))
        except Exception as e:
            print(f"Error during download: {e}")

    def _raw_delete(self, full_remote_path: str):
        """实现飞书文件或文件夹删除逻辑"""
        folder_or_file = self.feishu_ins.search_folder_recursive(
            self.feishu_ins.get_root_folder_token(self.root_folder_name), full_remote_path)
        if not folder_or_file:
            raise FileNotFoundError(f"Remote path not found: {full_remote_path}")
        self.feishu_ins.delete_file_or_folder(folder_or_file['token'], folder_or_file['type'])

    def list_contents(self, remote_path: str) -> List[Tuple[str, bool]]:
        """列出目录内容 (文件名, 是否是文件夹)"""
        folder = self.feishu_ins.search_folder_recursive(self.feishu_ins.get_root_folder_token(self.root_folder_name),
                                                         remote_path)
        if not folder:
            raise FileNotFoundError(f"Folder not found: {remote_path}")
        result = []
        children = self.feishu_ins.search_folder(folder["token"])
        for item in children:
            result.append((item["name"], item["type"] == "folder"))
        return result

    def resolve_remote_path(self, remote_path: str) -> str:
        """解析完整的远程路径"""
        # folder = self.feishu_ins.search_folder_recursive(self.feishu_ins.get_root_folder_token(self.root_folder_name), remote_path)
        # return folder["token"]
        return remote_path

    def is_directory(self, remote_path: str) -> bool:
        """判断路径是否为文件夹"""
        folder = self.feishu_ins.search_folder_recursive(self.feishu_ins.get_root_folder_token(self.root_folder_name),
                                                         remote_path)
        return folder is not None and folder["type"] == "folder"

    def create_directory(self, remote_path: str):
        """递归创建文件夹"""
        folders = remote_path.strip('/').split('/')
        current_token = self.feishu_ins.get_root_folder_token(self.root_folder_name)
        for folder in folders:
            current_token = self.feishu_ins.get_or_creat_folder_token(folder, current_token)

    def is_exists(self, remote_path: str) -> bool:
        """优化存在性检查"""
        return True if self.feishu_ins.search_folder(self.feishu_ins.get_root_folder_token(self.root_folder_name),
                                                     remote_path) else False


# -------------------- 使用示例 --------------------
if __name__ == '__main__':
    ...
