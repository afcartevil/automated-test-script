# app_provider.py
from __future__ import annotations
import asyncio
import hashlib
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, TypeVar, Generic, Union, Any, Dict

# 添加项目根目录到 sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, project_root)

T = TypeVar('T')
PathLike = Union[str, Path]


# --------- Response / Codes ---------
class AppProviderCodes:
    SUCCESS = 0
    NOT_FOUND = 1
    NETWORK_ERROR = 2
    AUTH_ERROR = 3
    DOWNLOAD_ERROR = 4
    PARSE_ERROR = 5
    VALIDATION_ERROR = 6
    ALREADY_EXISTS = 7
    NOT_NEEDED = 8
    UNKNOWN = 99


@dataclass
class ProviderAppMeta:
    package: str = ''
    version_name: str = ''
    version_code: str = ''
    md5: str = ''
    file_size: int = 0
    package_type: str = ''  # 'apk' or 'xapk'


@dataclass
class ProviderAppMetaRemote(ProviderAppMeta):
    # token identifies remote downloadable object, or download url
    token: str = ''
    source_manifest: Optional[dict] = None


@dataclass
class ProviderAppMetaLocal(ProviderAppMeta):
    filepath: PathLike = ''

    @classmethod
    async def create_from_local_async(cls, apk_xapk_filepath: PathLike) -> "ProviderAppMetaLocal":
        """
        异步包装：在异步上下文中使用（内部调用同步实现到线程池）
        """
        return await asyncio.to_thread(cls._create_from_local_blocking, apk_xapk_filepath)

    @classmethod
    def create_from_local(cls, apk_xapk_filepath: PathLike) -> "ProviderAppMetaLocal":
        """
        同步阻塞接口：从本地 apk/xapk 文件创建 ProviderAppMetaLocal。
        """
        return cls._create_from_local_blocking(apk_xapk_filepath)

    @staticmethod
    def _create_from_local_blocking(apk_xapk_filepath: PathLike) -> "ProviderAppMetaLocal":
        from pathlib import Path
        import zipfile

        p = Path(apk_xapk_filepath)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {p}")

        inst = ProviderAppMetaLocal()
        inst.filepath = str(p)
        inst.file_size = int(p.stat().st_size)
        inst.md5 = _compute_md5_file(p)

        suffix = p.suffix.lower()
        if suffix == ".apk":
            inst.package_type = "apk"
            # try to parse manifest via apkutils2 (preferable)
            try:
                # import local to avoid hard dependency unless used
                from apkutils2 import APK
                try:
                    # 执行apkutils2的猴子补丁，防止manifest解不出的情况
                    from powertrde.utils.apkutils2_extends import apkutils2_patcher
                    apkutils2_patcher.patch()
                except Exception as e:
                    print(f'执行apkutils2猴子补丁失败，将使用默认行为，原因：{e}')
            except Exception as e:
                raise RuntimeError(
                    "apkutils2 is required to parse APK manifest. Install with `pip install apkutils2`. "
                    f"Underlying error: {e}"
                )
            try:
                a = APK(str(p))
                manifest = a.get_manifest()  # returns dict
                inst.package = manifest.get("@package", "") or manifest.get("package", "")
                inst.version_code = manifest.get("@android:versionCode", "") or manifest.get("@versionCode", "")
                inst.version_name = manifest.get("@android:versionName", "") or manifest.get("@versionName", "")
                # normalize None -> ''
                if inst.version_code is None:
                    inst.version_code = ""
                if inst.version_name is None:
                    inst.version_name = ""
            except Exception as e:
                # parsing failed -> still return md5/size but raise parse error to alert integrator
                raise RuntimeError(f"Failed to parse APK manifest for {p}: {e}")
            return inst

        elif suffix == ".xapk" or suffix == ".zip":
            # treat xapk as zip; preserve all files but try to parse first contained apk for package metadata
            inst.package_type = "xapk"
            try:
                from apkutils2 import APK
                try:
                    # 执行apkutils2的猴子补丁，防止manifest解不出的情况
                    from powertrde.utils.apkutils2_extends import apkutils2_patcher
                    apkutils2_patcher.patch()
                except Exception as e:
                    print(f'执行apkutils2猴子补丁失败，将使用默认行为，原因：{e}')
            except Exception:
                # Without apkutils2 we still return md5/size and type
                return inst

            try:
                with zipfile.ZipFile(str(p), "r") as z:
                    # find first .apk entry
                    apk_entries = [n for n in z.namelist() if n.lower().endswith(".apk")]
                    if apk_entries:
                        # extract first apk to temp file for parsing
                        with tempfile.NamedTemporaryFile(suffix=".apk", delete=False) as tmpf:
                            tmp_name = tmpf.name
                            with z.open(apk_entries[0]) as src:
                                shutil.copyfileobj(src, tmpf)
                        try:
                            a = APK(tmp_name)
                            manifest = a.get_manifest()
                            inst.package = manifest.get("@package", "") or manifest.get("package", "")
                            inst.version_code = manifest.get("@android:versionCode", "") or manifest.get("@versionCode", "")
                            inst.version_name = manifest.get("@android:versionName", "") or manifest.get("@versionName", "")
                        finally:
                            try:
                                os.remove(tmp_name)
                            except Exception:
                                pass
            except Exception:
                # ignore contained apk parse errors; still return md5/size
                pass
            return inst

        else:
            # unknown extension: still fill md5 & size and mark type by extension
            inst.package_type = suffix.lstrip(".") or "bin"
            return inst


class AppProviderResponse(Generic[T]):
    def __init__(self):
        super().__init__()
        self.code: int = AppProviderCodes.UNKNOWN
        self.message: str = ''
        self.data: Optional[T] = None

    def set_success(self, data: Optional[T] = None, message: str = '') -> None:
        self.code = AppProviderCodes.SUCCESS
        self.message = message
        self.data = data

    def set_error(self, error_code: int, error_message: str) -> None:
        self.code = error_code
        self.message = error_message
        self.data = None

    def __bool__(self) -> bool:
        return self.code == AppProviderCodes.SUCCESS

    def as_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "message": self.message, "data": getattr(self.data, "__dict__", self.data)}


class AppProvider:
    """
    基类：合作方应继承并实现（同步方法，便于无 async 能力的工程师）：
      - def fetch_app_latest_meta(self, package: str) -> AppProviderResponse[ProviderAppMetaRemote]
      - def _raw_download_app(self, package: str, tmp_save_path: str) -> AppProviderResponse[ProviderAppMetaLocal]

    说明：
      - download_app: 负责创建临时路径并调用 _raw_download_app，然后做原子移动与校验。
      - check_version_code_download_app: 基于 fetch_app_latest_meta 判定是否需要下载（latest.version_code > arg）
      - 另外为每个同步方法提供了对应的异步 wrapper（*_async），以便在 asyncio 场景中复用。
    """

    # ---------- 可重用工具函数给子类/外部使用 ----------
    @staticmethod
    def compute_md5(path: PathLike) -> str:
        return _compute_md5_file(Path(path))

    @staticmethod
    async def compute_md5_async(path: PathLike) -> str:
        return await asyncio.to_thread(lambda: _compute_md5_file(Path(path)))

    # ---------- 子类必须实现的接口（同步） ----------
    def fetch_app_latest_meta(self, package: str) -> AppProviderResponse[ProviderAppMetaRemote]:
        """
        子类实现（同步）：
          通过 package 查询远端最新 meta（versionCode/versionName/md5/filesize/token等）
          返回 AppProviderResponse[ProviderAppMetaRemote]
        """
        raise NotImplementedError('Subclass must implement fetch_app_latest_meta')

    def _raw_download_app(self, package: str, tmp_save_path: str) -> AppProviderResponse[ProviderAppMetaLocal]:
        """
        子类实现（同步）：
          将远端资源下载到 tmp_save_path（完整文件路径，包含文件名）
          约定：子类应把实际下载好的本地文件路径填入返回的 ProviderAppMetaLocal.filepath（可与 tmp_save_path 相同）
          返回 AppProviderResponse[ProviderAppMetaLocal]
        """
        raise NotImplementedError('Subclass must implement _raw_download_app')

    # ---------- 异步包装（供需要 async 的调用方使用） ----------
    async def fetch_app_latest_meta_async(self, package: str) -> AppProviderResponse[ProviderAppMetaRemote]:
        return await asyncio.to_thread(self.fetch_app_latest_meta, package)

    async def _raw_download_app_async(self, package: str, tmp_save_path: str) -> AppProviderResponse[ProviderAppMetaLocal]:
        return await asyncio.to_thread(self._raw_download_app, package, tmp_save_path)

    async def download_app_async(self, package: str, save_path: PathLike) -> AppProviderResponse[ProviderAppMetaLocal]:
        return await asyncio.to_thread(self.download_app, package, save_path)

    async def check_version_code_download_app_async(self, package: str, version_code_greater_than: int) -> AppProviderResponse[ProviderAppMetaLocal]:
        return await asyncio.to_thread(self.check_version_code_download_app, package, version_code_greater_than)

    # ---------- 公共实现部分（同步） ----------
    def download_app(self, package: str, save_path: PathLike) -> AppProviderResponse[ProviderAppMetaLocal]:
        """
        对外下载接口（同步）改良版：
         - 修复当 save_path 为目录且临时文件名被误用为最终文件名导致最终文件被 finally 删除的问题；
         - 优先使用子类返回的 local_meta（package/version/package_type）来归一化目标文件名；
         - 保持原子移动与 md5 比对，保证幂等与安全。
        """
        resp = AppProviderResponse[ProviderAppMetaLocal]()

        # Normalize save_path
        target = Path(save_path)
        is_dir = False
        if target.exists() and target.is_dir():
            is_dir = True

        # create parent dir if needed
        target_parent = target if target.is_dir() else target.parent
        try:
            target_parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        # create unique tmp filename in same directory to allow atomic replace
        tmp_fd, tmp_path = tempfile.mkstemp(prefix=f"approvdl_{package}_", dir=str(target_parent))
        os.close(tmp_fd)

        final_path: Optional[Path] = None
        downloaded_path: Optional[Path] = None

        def _safe_name(s: str) -> str:
            # simple safe filename: replace unsafe chars with underscore, keep reasonable length
            s = (s or "").strip()
            if not s:
                return "unknown"
            import re
            safe = re.sub(r'[^A-Za-z0-9._+-]', '_', s)
            if len(safe) > 200:
                safe = safe[:200]
            return safe

        try:
            # Let subclass perform actual download into tmp_path
            raw_resp = self._raw_download_app(package, tmp_path)
            if not raw_resp:
                resp.set_error(
                    raw_resp.code if getattr(raw_resp, "code", None) is not None else AppProviderCodes.DOWNLOAD_ERROR,
                    raw_resp.message or "raw download failed")
                # cleanup tmp if exists
                try:
                    if Path(tmp_path).exists():
                        Path(tmp_path).unlink()
                except Exception:
                    pass
                return resp

            # raw_resp.data should contain ProviderAppMetaLocal and filepath
            local_meta = raw_resp.data
            if local_meta is None or not getattr(local_meta, "filepath", None):
                # If subclass didn't populate filepath, assume tmp_path
                local_meta = local_meta or ProviderAppMetaLocal()
                local_meta.filepath = tmp_path

            downloaded_path = Path(local_meta.filepath)
            if not downloaded_path.exists():
                # maybe subclass wrote to tmp_path, try that
                if Path(tmp_path).exists():
                    downloaded_path = Path(tmp_path)
                else:
                    resp.set_error(AppProviderCodes.DOWNLOAD_ERROR, "Downloaded file not found after raw download")
                    return resp

            # determine final_path
            if is_dir:
                # Prefer structured name from meta: package + version + ext inferred from package_type or downloaded file
                pkg_name = getattr(local_meta, "package", "") or package or ""
                ver = getattr(local_meta, "version_code", "") or getattr(local_meta, "version_name", "") or ""
                ptype = getattr(local_meta, "package_type", "") or ""
                # infer extension
                ext = ""
                try:
                    # if declared type known
                    if str(ptype).lower() == "apk":
                        ext = ".apk"
                    elif str(ptype).lower() == "xapk":
                        ext = ".xapk"
                except Exception:
                    ext = ""
                if not ext:
                    ext = downloaded_path.suffix or ""
                # Build candidate name; avoid using tmp-like names
                candidate_basename = ""
                if pkg_name and ver:
                    candidate_basename = f"{_safe_name(pkg_name)}_{_safe_name(str(ver))}{ext}"
                else:
                    # fallback: use downloaded filename unless it looks like our tmp prefix
                    dname = downloaded_path.name
                    if dname.startswith(f"approvdl_{package}_"):
                        # avoid tmp-like name: generate generic name
                        candidate_basename = f"{_safe_name(package)}_{_safe_name(str(getattr(local_meta, 'version_code', '')))}{ext}"
                    else:
                        candidate_basename = dname
                final_path = target_parent / candidate_basename
            else:
                final_path = target

            # If final exists and identical (md5) -> skip replacing
            try:
                if final_path.exists():
                    try:
                        existing_md5 = _compute_md5_file(final_path)
                    except Exception:
                        existing_md5 = None
                    try:
                        new_md5 = _compute_md5_file(downloaded_path)
                    except Exception:
                        new_md5 = None

                    if existing_md5 is not None and new_md5 is not None and existing_md5 == new_md5:
                        # remove tmp if it's separate from final
                        if downloaded_path.exists() and str(downloaded_path) != str(final_path):
                            try:
                                downloaded_path.unlink()
                            except Exception:
                                pass
                        # prepare response meta from existing file
                        try:
                            final_meta_inst = ProviderAppMetaLocal.create_from_local(final_path)
                            resp.set_success(final_meta_inst, message="already_exists_and_identical")
                            return resp
                        except Exception:
                            # fallback to minimal response
                            inst = ProviderAppMetaLocal()
                            inst.filepath = str(final_path)
                            inst.file_size = int(final_path.stat().st_size)
                            try:
                                inst.md5 = _compute_md5_file(final_path)
                            except Exception:
                                inst.md5 = ""
                            resp.set_success(inst, message="already_exists_and_identical")
                            return resp

                # if downloaded_path and final_path are the same path, consider it already in place
                same_path = False
                try:
                    same_path = downloaded_path.resolve() == final_path.resolve()
                except Exception:
                    same_path = str(downloaded_path) == str(final_path)

                if not same_path:
                    # ensure parent
                    final_path.parent.mkdir(parents=True, exist_ok=True)
                    # Move (atomic on same filesystem)
                    shutil.move(str(downloaded_path), str(final_path))
                # else no move needed

            except Exception as e:
                # try copy fallback
                try:
                    shutil.copy2(str(downloaded_path), str(final_path))
                    try:
                        if downloaded_path.exists() and str(downloaded_path) != str(final_path):
                            downloaded_path.unlink()
                    except Exception:
                        pass
                except Exception as e2:
                    resp.set_error(AppProviderCodes.DOWNLOAD_ERROR,
                                   f"Failed to move/copy downloaded file into place: {e2}")
                    return resp

            # Build final ProviderAppMetaLocal (fill missing fields)
            try:
                final_meta = ProviderAppMetaLocal.create_from_local(final_path)
            except Exception as e:
                # parsing failed but file exists; still return success with minimal meta
                inst = ProviderAppMetaLocal()
                inst.filepath = str(final_path)
                inst.file_size = int(final_path.stat().st_size)
                try:
                    inst.md5 = _compute_md5_file(final_path)
                except Exception:
                    inst.md5 = ""
                resp.set_success(inst, message=f"downloaded_but_parse_failed:{e}")
                return resp

            resp.set_success(final_meta, message="downloaded")
            return resp

        finally:
            # cleanup any stray tmp file if still exists AND is NOT the same as final_path
            try:
                tmp_p = Path(tmp_path)
                if tmp_p.exists():
                    try:
                        if final_path is None or tmp_p.resolve() != Path(final_path).resolve():
                            tmp_p.unlink()
                    except Exception:
                        # best-effort: if resolve() fails, fallback to string compare
                        try:
                            if final_path is None or str(tmp_p) != str(final_path):
                                tmp_p.unlink()
                        except Exception:
                            pass
            except Exception:
                pass

    def check_version_code_download_app(self, package: str, version_code_greater_than: int) -> AppProviderResponse[ProviderAppMetaLocal]:
        """
        同步版本：
        检查合作方站点上最新版本是否 > version_code_greater_than：
          - 若 latest_version_code > version_code_greater_than，则自动下载最新版本到临时目录并返回 ProviderAppMetaLocal
          - 否则返回 code = NOT_NEEDED
        返回 AppProviderResponse[ProviderAppMetaLocal]
        """
        resp = AppProviderResponse[ProviderAppMetaLocal]()
        # fetch latest meta
        try:
            latest_resp = self.fetch_app_latest_meta(package)
        except Exception as e:
            resp.set_error(AppProviderCodes.NETWORK_ERROR, f"fetch_latest_meta_failed:{e}")
            return resp

        if not latest_resp:
            # propagate remote error
            resp.set_error(latest_resp.code or AppProviderCodes.UNKNOWN, latest_resp.message or "fetch_latest_meta_failed")
            return resp

        remote: ProviderAppMetaRemote = latest_resp.data
        # Attempt numeric comparison; treat missing or non-int as not decidable (assume need)
        try:
            remote_v = int(remote.version_code)
        except Exception:
            # cannot parse: consider it as newer -> attempt download
            remote_v = None

        if remote_v is not None and remote_v <= int(version_code_greater_than):
            resp.set_error(AppProviderCodes.NOT_NEEDED, "remote_not_newer")
            return resp

        # remote is newer (or cannot parse) -> download to temp dir
        tmp_dir = Path(tempfile.gettempdir()) / "appprov_downloads"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        # prefer token/filename if provided in remote meta to name file, else use package+version
        suggested_name = None
        try:
            if getattr(remote, "token", None):
                # use token as name safe fallback
                suggested_name = f"{package}_{remote.version_code}"
            else:
                suggested_name = f"{package}_{remote.version_code}"
        except Exception:
            suggested_name = f"{package}_{remote.version_code}"

        save_path = tmp_dir / suggested_name
        try:
            dl_resp = self.download_app(package, str(save_path))
        except Exception as e:
            resp.set_error(AppProviderCodes.DOWNLOAD_ERROR, f"download_failed:{e}")
            return resp

        if not dl_resp:
            resp.set_error(dl_resp.code or AppProviderCodes.DOWNLOAD_ERROR, dl_resp.message or "download failed")
            return resp

        # success
        resp.set_success(dl_resp.data, message="downloaded_newer")
        return resp


# ---------- Helper functions ----------
def _compute_md5_file(p: Path) -> str:
    h = hashlib.md5()
    with open(str(p), "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
