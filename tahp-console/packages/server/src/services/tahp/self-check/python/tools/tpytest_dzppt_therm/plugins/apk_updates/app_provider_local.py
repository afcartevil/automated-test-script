# AppProviderLocal implementation for local filesystem repo
import os
import shutil
from pathlib import Path
from typing import List, Optional, Union

from apk_updates.apk_xapk_repo_builder import load_json, save_json_atomic
from apk_updates.app_provider import AppProviderCodes, ProviderAppMetaLocal, _compute_md5_file, AppProviderResponse, \
    ProviderAppMetaRemote, PathLike, AppProvider

import hashlib


class AppProviderLocal(AppProvider):
    """
    Local AppProvider that serves apps from a repo on local filesystem.

    repo_root layout expected:
      <repo_root>/global_index.json
      <repo_root>/packages/<package>/<version>/meta.json
      <repo_root>/packages/<package>/<version>/<artifact files>
    """

    def __init__(self, repo_root: PathLike):
        super().__init__()
        self.repo_root = Path(repo_root).expanduser().resolve()
        if not self.repo_root.exists():
            raise FileNotFoundError(f"repo_root not found: {self.repo_root}")
        # verify minimal layout
        if not (self.repo_root / "global_index.json").exists():
            idx = {"generated_at": None, "apps": []}
            try:
                save_json_atomic(self.repo_root / "global_index.json", idx)
            except Exception:
                pass

    # ---------- helpers ----------
    def _load_global_index(self) -> dict:
        idx_path = self.repo_root / "global_index.json"
        idx = load_json(idx_path)
        return idx or {"generated_at": None, "apps": []}

    def list_packages(self) -> List[str]:
        idx = self._load_global_index()
        return [a.get("package_name") for a in idx.get("apps", [])]

    def get_global_entry(self, package: str) -> Optional[dict]:
        idx = self._load_global_index()
        for a in idx.get("apps", []):
            if a.get("package_name") == package:
                return a
        return None

    def get_meta_path(self, package: str, version: Optional[Union[int, str]] = None) -> Optional[Path]:
        if version is None or str(version).lower() == "latest":
            entry = self.get_global_entry(package)
            if not entry:
                return None
            meta_rel = entry.get("meta_url")
            if not meta_rel:
                return None
            meta_rel = meta_rel.lstrip("/\\")
            return self.repo_root / meta_rel
        else:
            return self.repo_root / "packages" / package / str(version) / "meta.json"

    def load_meta(self, package: str, version: Optional[Union[int, str]] = None) -> Optional[dict]:
        path = self.get_meta_path(package, version)
        if path is None:
            return None
        try:
            m = load_json(path)
            return m
        except Exception:
            return None

    def list_versions(self, package: str) -> List[int]:
        pkg_dir = self.repo_root / "packages" / package
        if not pkg_dir.exists() or not pkg_dir.is_dir():
            return []
        vers = []
        for child in pkg_dir.iterdir():
            if child.is_dir():
                try:
                    vers.append(int(child.name))
                except Exception:
                    pass
        return sorted(vers)

    def resolve_artifact_path(self, package: str, version: Union[int, str], filename: str) -> Optional[Path]:
        candidate = self.repo_root / "packages" / package / str(version) / filename
        if candidate.exists():
            return candidate
        pkg_dir = self.repo_root / "packages" / package / str(version)
        if pkg_dir.exists() and pkg_dir.is_dir():
            for f in pkg_dir.iterdir():
                if f.name == filename:
                    return f
        return None

    def _find_artifact_by_md5(self, package: str, version: Union[int, str], md5_hex: str) -> Optional[Path]:
        """
        Search package/version directory for a file with matching md5.
        Returns first match Path or None.
        """
        if not md5_hex:
            return None
        pkg_dir = self.repo_root / "packages" / package / str(version)
        if not pkg_dir.exists() or not pkg_dir.is_dir():
            return None
        for f in pkg_dir.iterdir():
            if f.is_file():
                try:
                    if _compute_md5_file(f) == md5_hex:
                        return f
                except Exception:
                    # skip unreadable files
                    continue
        return None

    def _compute_sha256(self, path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    # ---------- required AppProvider methods (synchronous) ----------
    def fetch_app_latest_meta(self, package: str) -> AppProviderResponse[ProviderAppMetaRemote]:
        """
        Return ProviderAppMetaRemote for latest version published in global_index.json.
        md5 field is filled from meta.file.content_md5 if present, otherwise fall back to content_sha256.
        """
        resp = AppProviderResponse[ProviderAppMetaRemote]()
        entry = self.get_global_entry(package)
        if not entry:
            resp.set_error(AppProviderCodes.NOT_FOUND, f"package not found in global_index: {package}")
            return resp

        meta_path = self.get_meta_path(package, entry.get("latest_version_code"))
        if meta_path is None or not meta_path.exists():
            resp.set_error(AppProviderCodes.NOT_FOUND, f"meta not found for package {package} (entry exists but meta missing)")
            return resp

        meta = load_json(meta_path)
        if not meta or not isinstance(meta, dict):
            resp.set_error(AppProviderCodes.PARSE_ERROR, f"meta.json parse error: {meta_path}")
            return resp

        file_info = meta.get("file", {}) or {}
        pmeta = ProviderAppMetaRemote()
        pmeta.package = meta.get("package_name") or meta.get("package") or package
        try:
            pmeta.version_code = str(int(meta.get("version_code") if meta.get("version_code") is not None else entry.get("latest_version_code")))
        except Exception:
            pmeta.version_code = str(meta.get("version_code") or entry.get("latest_version_code"))
        pmeta.version_name = str(meta.get("version_name") or "")

        # **Prefer content_md5** when available; fall back to sha256 for legacy compatibility
        pmeta.md5 = file_info.get("content_md5") or file_info.get("content_sha256") or ""
        pmeta.file_size = int(file_info.get("size") or 0)
        pmeta.package_type = file_info.get("type") or ""
        artifact_filename = file_info.get("filename") or ""
        token_rel = f"packages/{pmeta.package}/{pmeta.version_code}/{artifact_filename}"
        pmeta.token = token_rel
        pmeta.source_manifest = meta
        resp.set_success(pmeta, message="ok")
        return resp

    def _raw_download_app(self, package: str, tmp_save_path: str) -> AppProviderResponse[ProviderAppMetaLocal]:
        """
        Copy the artifact file into tmp_save_path. Validates against content_md5/content_sha256 if provided.
        If meta.file.filename missing, attempt to find artifact by content_md5 in the package/version dir.
        """
        resp = AppProviderResponse[ProviderAppMetaLocal]()
        entry = self.get_global_entry(package)
        if not entry:
            resp.set_error(AppProviderCodes.NOT_FOUND, f"package not found: {package}")
            return resp

        meta = self.load_meta(package, entry.get("latest_version_code"))
        if not meta:
            resp.set_error(AppProviderCodes.NOT_FOUND, f"meta.json missing for {package}/{entry.get('latest_version_code')}")
            return resp

        file_info = meta.get("file", {}) or {}
        fname = file_info.get("filename")
        version_in_meta = meta.get("version_code") or entry.get("latest_version_code")

        artifact_path = None
        if fname:
            artifact_path = self.resolve_artifact_path(package, version_in_meta, fname)

        # If filename not found, but content_md5 present, try search by md5
        expected_md5 = file_info.get("content_md5")
        expected_sha256 = file_info.get("content_sha256")
        if artifact_path is None and expected_md5:
            # try find file by md5
            candidate = self._find_artifact_by_md5(package, version_in_meta, expected_md5)
            if candidate:
                artifact_path = candidate

        if artifact_path is None or not artifact_path.exists():
            resp.set_error(AppProviderCodes.NOT_FOUND, f"artifact file missing for {package}: {fname or '<unknown>'}")
            return resp

        tmp_path_obj = Path(tmp_save_path)
        tmp_path_obj.parent.mkdir(parents=True, exist_ok=True)

        try:
            # copy file to tmp_save_path
            shutil.copy2(str(artifact_path), str(tmp_save_path))
        except Exception as e:
            resp.set_error(AppProviderCodes.DOWNLOAD_ERROR, f"copy_failed:{e}")
            return resp

        # perform validation using md5/sha256 if available
        try:
            actual_md5 = _compute_md5_file(Path(tmp_save_path))
        except Exception:
            actual_md5 = None
        actual_sha256 = None
        try:
            actual_sha256 = self._compute_sha256(Path(tmp_save_path))
        except Exception:
            actual_sha256 = None

        # If expected md5 exists, it must match
        if expected_md5 and actual_md5:
            if expected_md5 != actual_md5:
                # cleanup corrupted tmp
                try:
                    Path(tmp_save_path).unlink()
                except Exception:
                    pass
                resp.set_error(AppProviderCodes.VALIDATION_ERROR, f"md5_mismatch: expected={expected_md5} actual={actual_md5}")
                return resp

        # If expected sha256 exists, check it as well (optional additional safety)
        if expected_sha256 and actual_sha256:
            if expected_sha256 != actual_sha256:
                try:
                    Path(tmp_save_path).unlink()
                except Exception:
                    pass
                resp.set_error(AppProviderCodes.VALIDATION_ERROR, f"sha256_mismatch: expected={expected_sha256} actual={actual_sha256}")
                return resp

        # try to build ProviderAppMetaLocal from meta and local file to avoid reparsing where possible
        try:
            local_meta = ProviderAppMetaLocal()
            local_meta.filepath = str(tmp_save_path)
            local_meta.file_size = int(os.path.getsize(tmp_save_path))
            # prefer the md5 computed from file (true md5)
            local_meta.md5 = actual_md5 or ""
            local_meta.package_type = file_info.get("type") or ""
            local_meta.package = meta.get("package_name") or package
            local_meta.version_code = str(meta.get("version_code") or entry.get("latest_version_code"))
            local_meta.version_name = str(meta.get("version_name") or "")
            resp.set_success(local_meta, message="downloaded")
            return resp
        except Exception:
            # fallback: attempt to parse file to fill manifest info (may require apkutils2)
            try:
                parsed = ProviderAppMetaLocal.create_from_local(tmp_save_path)
                resp.set_success(parsed, message="downloaded_and_parsed")
                return resp
            except Exception as e:
                fallback = ProviderAppMetaLocal()
                fallback.filepath = str(tmp_save_path)
                fallback.file_size = int(os.path.getsize(tmp_save_path))
                fallback.md5 = actual_md5 or ""
                resp.set_success(fallback, message=f"downloaded_but_parse_failed:{e}")
                return resp

    # ---------- convenience: download a specific version (synchronous) ----------
    def download_version(self, package: str, version: Union[int, str], tmp_save_path: str) -> AppProviderResponse[ProviderAppMetaLocal]:
        """
        Explicitly download a given package/version artifact into tmp_save_path.
        Also validates using content_md5/content_sha256 when available.
        """
        resp = AppProviderResponse[ProviderAppMetaLocal]()
        meta = self.load_meta(package, version)
        if not meta:
            resp.set_error(AppProviderCodes.NOT_FOUND, f"meta.json missing for {package}/{version}")
            return resp

        file_info = meta.get("file", {}) or {}
        fname = file_info.get("filename")
        artifact_path = None
        if fname:
            artifact_path = self.resolve_artifact_path(package, meta.get("version_code") or version, fname)

        expected_md5 = file_info.get("content_md5")
        expected_sha256 = file_info.get("content_sha256")
        if artifact_path is None and expected_md5:
            artifact_path = self._find_artifact_by_md5(package, version, expected_md5)

        if not artifact_path or not artifact_path.exists():
            resp.set_error(AppProviderCodes.NOT_FOUND, f"artifact file missing for {package}/{version}: {fname or '<unknown>'}")
            return resp

        tmp_path_obj = Path(tmp_save_path)
        tmp_path_obj.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(str(artifact_path), str(tmp_save_path))
        except Exception as e:
            resp.set_error(AppProviderCodes.DOWNLOAD_ERROR, f"copy_failed:{e}")
            return resp

        # validate
        try:
            actual_md5 = _compute_md5_file(Path(tmp_save_path))
        except Exception:
            actual_md5 = None
        actual_sha256 = None
        try:
            actual_sha256 = self._compute_sha256(Path(tmp_save_path))
        except Exception:
            actual_sha256 = None

        if expected_md5 and actual_md5 and expected_md5 != actual_md5:
            try:
                Path(tmp_save_path).unlink()
            except Exception:
                pass
            resp.set_error(AppProviderCodes.VALIDATION_ERROR, f"md5_mismatch: expected={expected_md5} actual={actual_md5}")
            return resp

        if expected_sha256 and actual_sha256 and expected_sha256 != actual_sha256:
            try:
                Path(tmp_save_path).unlink()
            except Exception:
                pass
            resp.set_error(AppProviderCodes.VALIDATION_ERROR, f"sha256_mismatch: expected={expected_sha256} actual={actual_sha256}")
            return resp

        # parse to meta
        try:
            parsed = ProviderAppMetaLocal.create_from_local(tmp_save_path)
            resp.set_success(parsed, message="downloaded")
            return resp
        except Exception as e:
            fallback = ProviderAppMetaLocal()
            fallback.filepath = str(tmp_save_path)
            fallback.file_size = int(os.path.getsize(tmp_save_path))
            fallback.md5 = actual_md5 or ""
            resp.set_success(fallback, message=f"downloaded_but_parse_failed:{e}")
            return resp


if __name__ == '__main__':
    apl = AppProviderLocal(r'D:\apks\repo')
    a = apl.download_app('com.transsion.emmctest', r'D:\apks\downloads')
    print(a.code, a.message, getattr(a.data, "filepath", None))
