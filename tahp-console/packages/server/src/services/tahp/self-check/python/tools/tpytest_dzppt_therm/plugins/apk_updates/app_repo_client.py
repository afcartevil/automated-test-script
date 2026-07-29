# app_repo_client_locked.py
from __future__ import annotations
import json
import re
import shutil
import threading
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Union
from concurrent.futures import ThreadPoolExecutor, as_completed

from powertrde.framework.tran_logger import t_log
from powertrde.utils import misc_utils
from powertrde.utils.trde import adb


@dataclass
class DownloadResult:
    local_path: Path
    from_cache: bool
    content_sha256: Optional[str] = None


class AppRepoClient:
    """
    AppRepoClient with optional resource_lock_manager to avoid multi-process race conditions.

    resource_lock_manager: optional object that must implement:
        acquire_resource(key: str, timeout: float = 5.0, retry_delay: float = 0.1) -> bool
        release_resource(key: str) -> bool

    If resource_lock_manager is None, client uses in-process threading locks (not cross-process safe).
    """

    GLOBAL_INDEX_NAME = "global_index.json"

    def __init__(self,
                 provider,
                 cache_dir: Union[str, Path],
                 index_ttl_seconds: int = 300,
                 resource_lock_manager: Optional[Any] = None,
                 default_lock_timeout: float = 7200.0,
                 max_concurrent_downloads: int = 3):
        self.provider = provider
        self.cache_dir = Path(cache_dir).expanduser().resolve()
        self.index_ttl_seconds = int(index_ttl_seconds)
        self.lock_manager = resource_lock_manager  # may be None
        self.default_lock_timeout = float(default_lock_timeout)

        # throttle for provider downloads (useful for providers with limited parallelism, e.g. Feishu)
        self.max_concurrent_downloads = int(
            max_concurrent_downloads) if max_concurrent_downloads and max_concurrent_downloads > 0 else 3
        self._download_semaphore = threading.Semaphore(self.max_concurrent_downloads)

        # local cache paths
        self._index_cache_path = self.cache_dir / self.GLOBAL_INDEX_NAME
        self._packages_cache_dir = self.cache_dir / "packages"
        self._requests_local_dir = self.cache_dir / "requests_local"
        self._packages_cache_dir.mkdir(parents=True, exist_ok=True)
        self._requests_local_dir.mkdir(parents=True, exist_ok=True)
        self._local_lock_table: Dict[str, threading.Lock] = {}
        self._local_lock_table_guard = threading.Lock()
        if self.lock_manager is None:
            self.logger.warning(
                "No resource_lock_manager provided -> using in-process locks (NOT cross-process safe).")

    # ---------------- logger helpers ----------------

    @property
    def logger(self):
        return t_log.logger()

    # ---------------- lock helpers ----------------
    def _acquire(self, key: str, timeout: Optional[float] = None, retry_delay: float = 0.1) -> bool:
        """
        Acquire lock for key:
          - if external lock_manager provided -> call its acquire_resource
          - else use in-process threading.Lock (blocking)
        Returns True if acquired, False otherwise.
        """
        if timeout is None:
            timeout = self.default_lock_timeout

        def _in_process_lock():
            # in-process fallback
            with self._local_lock_table_guard:
                if key not in self._local_lock_table:
                    self._local_lock_table[key] = threading.Lock()
                lock = self._local_lock_table[key]
            # blocking acquire with timeout
            acquired = lock.acquire(timeout=timeout)
            if not acquired:
                self.logger.debug("In-process lock acquire timed out for key=%s", key)
            return acquired

        if self.lock_manager is not None:
            try:
                ok = self.lock_manager.acquire_resource(key, timeout, retry_delay) and _in_process_lock()
                if not ok:
                    self.logger.debug("Lock manager failed to acquire %s", key)
                return ok
            except Exception as e:
                self.logger.exception("External lock_manager.acquire_resource raised exception for key=%s: %s", key, e)
                return False

        return _in_process_lock()

    def _release(self, key: str) -> bool:
        """
        Release lock (external manager or in-process)
        """

        def _in_process_unlock():
            with self._local_lock_table_guard:
                l = self._local_lock_table.get(key)
            if l:
                try:
                    # threading.Lock.release may raise RuntimeError if not acquired
                    l.release()
                    return True
                except RuntimeError:
                    # already released or not owned
                    self.logger.debug("Attempted to release an in-process lock not owned for key=%s", key)
                    return False
            return False

        def _cross_process_unlock():
            if self.lock_manager is not None:
                try:
                    ok = self.lock_manager.release_resource(key)
                    if not ok:
                        self.logger.debug("Lock manager release_resource returned False for %s", key)
                    return ok
                except Exception as e:
                    self.logger.exception("External lock_manager.release_resource raised exception for key=%s: %s", key,
                                          e)
                    return False
            return True

        ret1 = _cross_process_unlock()
        ret2 = _in_process_unlock()

        return ret1 and ret2

    # ---------------- low-level file helpers ----------------
    def _write_json_atomic(self, path: Path, obj: Any):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def _read_json(self, path: Path) -> Optional[Dict[str, Any]]:
        try:
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    # ---------------- index helpers ----------------
    def fetch_global_index(self, force: bool = False) -> Dict[str, Any]:
        """
        Fetch global index, using local cache with TTL and provider as fallback.
        If force=True -> always fetch remote and refresh local cached copy.
        Returns the parsed index dict.
        """
        _fetch_time = datetime.utcnow()

        # if not forcing, try to use cached copy and TTL
        if not force:
            idx = self._read_json(self._index_cache_path)
            if idx:
                gen = idx.get("updated_at")
                if gen:
                    try:
                        # parse to timezone-aware UTC datetime
                        gen_dt_utc = misc_utils.parse_time_str_to_utc(gen, assume_naive_utc=True)
                        # use aware now in UTC
                        now_utc = datetime.now(timezone.utc)
                        age_seconds = (now_utc - gen_dt_utc).total_seconds()
                        if age_seconds < self.index_ttl_seconds:
                            self.logger.debug("Using cached global_index.json (fresh, age=%.1fs)", age_seconds)
                            return idx
                        else:
                            self.logger.debug("Cached global_index.json expired (age=%.1fs)", age_seconds)
                    except Exception as e:
                        # 不要在此直接抛出：解析失败则退到远程拉取（更稳健）
                        # self.logger.exception("Failed to parse cached generated_at (%r): %s", gen, e)
                        pass

        # Acquire index refresh lock to avoid stampede
        key = "global_index"
        got = self._acquire(key, timeout=30)
        if not got:
            # If fail to acquire, fallback to cached copy (if present), otherwise raise
            idx = self._read_json(self._index_cache_path)
            if idx:
                self.logger.info("Another worker refreshing global_index; falling back to cached copy")
                return idx
            raise RuntimeError("Failed to acquire global_index lock and no cache available")

        try:
            if not force:
                idx2 = self._read_json(self._index_cache_path)
                if idx2:
                    gen2 = idx2.get("updated_at")
                    if gen2:
                        try:
                            gen_dt_utc2 = misc_utils.parse_time_str_to_utc(gen2, assume_naive_utc=True)
                            now_utc2 = datetime.now(timezone.utc)
                            age_seconds2 = (now_utc2 - gen_dt_utc2).total_seconds()
                            if age_seconds2 < self.index_ttl_seconds:
                                self.logger.debug("Using cached global_index.json after lock (fresh, age=%.1fs)", age_seconds2)
                                return idx2
                        except Exception:
                            pass
            # attempt to download remote global_index.json into a tmp file
            tmp_local = self.cache_dir / f"tmp_global_index_{int(time.time())}.json"
            if tmp_local.exists():
                tmp_local.unlink()
            try:
                # provider.download may raise; let exceptions propagate so caller can handle
                saved = self.provider.download(self.GLOBAL_INDEX_NAME, str(tmp_local), overwrite=True)
                tmp_local = Path(saved)
                idx = json.loads(tmp_local.read_text(encoding="utf-8"))
                # atomic write to cache
                idx['updated_at'] = _fetch_time.isoformat() + "Z"
                self._write_json_atomic(self._index_cache_path, idx)
                # best-effort cleanup of temp file
                try:
                    if tmp_local.exists():
                        tmp_local.unlink(missing_ok=True)
                except Exception:
                    pass
                self.logger.info("global_index.json downloaded and cached (force=%s)", bool(force))
                return idx
            except Exception as e:
                self.logger.warning("Failed to download global_index.json: %s", e)
                # fallback to existing cache if available
                idx = self._read_json(self._index_cache_path)
                if idx is not None:
                    self.logger.info("Falling back to cached global_index.json")
                    return idx
                # no cache -> rethrow
                raise RuntimeError("Unable to obtain global_index.json from remote and no cache available") from e
        finally:
            self._release(key)

    def list_remote_apps(self) -> List[Dict[str, Any]]:
        idx = self.fetch_global_index()
        return idx.get("apps", [])

    def get_latest_version_from_index(self, package_name: str) -> Optional[Dict[str, Any]]:
        idx = self.fetch_global_index()
        for a in idx.get("apps", []):
            if a.get("package_name") == package_name:
                return a
        return None

    # ---------------- meta helpers (with meta-level lock) ----------------
    def _remote_meta_path(self, package_name: str, version_code: Union[int, str]) -> str:
        return f"packages/{package_name}/{version_code}/meta.json"

    def _local_meta_path(self, package_name: str, version_code: Union[int, str]) -> Path:
        return self._packages_cache_dir / package_name / str(version_code) / "meta.json"

    def get_remote_meta(self, package_name: str, version_code: Union[int, str], force: bool = False) -> Optional[Dict[str, Any]]:
        key = f"meta:{package_name}:{version_code}"
        got = self._acquire(key, timeout=self.default_lock_timeout)
        if not got:
            self.logger.warning("Could not acquire meta lock for %s/%s; attempting best-effort fetch via cache",
                                package_name, version_code)
            return self.get_cached_meta(package_name, version_code)

        try:
            remote = self._remote_meta_path(package_name, version_code)
            # quick existence check
            try:
                if not self.provider.is_exists(remote):
                    self.logger.debug("Remote meta not exists: %s", remote)
                    return None
            except Exception:
                self.logger.debug("Provider cannot resolve existence for %s - proceeding to attempt download", remote)

            tmp_local = self.cache_dir / f"tmp_meta_{package_name}_{version_code}.json"
            if tmp_local.exists():
                tmp_local.unlink()
            try:
                saved = self.provider.download(remote, str(tmp_local), overwrite=True)
                tmp_local = Path(saved)
                meta = json.loads(tmp_local.read_text(encoding="utf-8"))
                # save under cache
                local_meta_path = self._local_meta_path(package_name, version_code)
                local_meta_path.parent.mkdir(parents=True, exist_ok=True)
                self._write_json_atomic(local_meta_path, meta)
                # cleanup of temp file
                try:
                    if tmp_local.exists():
                        tmp_local.unlink(missing_ok=True)
                except Exception:
                    pass
                self.logger.debug("Fetched and cached remote meta for %s/%s", package_name, version_code)
                return meta
            except Exception as e:
                self.logger.debug("Failed to download remote meta %s: %s", remote, e)
                return None
        finally:
            self._release(key)

    def get_cached_meta(self, package_name: str, version_code: Union[int, str]) -> Optional[Dict[str, Any]]:
        p = self._local_meta_path(package_name, version_code)
        return self._read_json(p)

    # ---------------- artifact helpers (with artifact-level lock) ----------------
    def _artifact_remote_path(self, package_name: str, version_code: Union[int, str], filename: str) -> str:
        return f"packages/{package_name}/{version_code}/{filename}"

    def _artifact_local_path(self, package_name: str, version_code: Union[int, str], filename: str) -> Path:
        return self._packages_cache_dir / package_name / str(version_code) / filename

    def update_cache_for_package(self,
                                 package_name: str,
                                 version_code: Optional[Union[int, str]] = None,
                                 force_download: bool = False,
                                 extract_xapk: bool = False) -> DownloadResult:
        """
        Ensure meta + artifact cached for package/version.
        Uses locks to prevent concurrent downloads and cache corruption.
        """
        if version_code is None:
            latest = self.get_latest_version_from_index(package_name)
            if not latest:
                raise FileNotFoundError(f"No remote entry for package {package_name}")
            version_code = latest.get("latest_version_code") or latest.get("latest_version")
            assert version_code is not None

        # prefer remote meta to know artifact and sha
        meta = self.get_remote_meta(package_name, version_code)
        if meta is None:
            # fallback to cached meta
            meta = self.get_cached_meta(package_name, version_code)
            if meta is None:
                # submit missing request under lock
                self.logger.info("Remote meta missing for %s/%s; submitting missing request", package_name,
                                 version_code)
                self.submit_missing_request(package_name, version_code, notes="auto-request from client")
                raise FileNotFoundError(f"Remote meta missing for {package_name}/{version_code}")

        file_info = meta.get("file", {})
        ftype = file_info.get("type")
        if ftype == "apk":
            filename = file_info.get("filename")
            content_sha = file_info.get("content_sha256")
            remote_path = self._artifact_remote_path(package_name, version_code, filename)
            local_path = self._artifact_local_path(package_name, version_code, filename)
            local_path.parent.mkdir(parents=True, exist_ok=True)

            artifact_key = f"artifact:{package_name}:{version_code}:{filename}"
            got = self._acquire(artifact_key, timeout=self.default_lock_timeout)
            if not got:
                self.logger.warning("Could not acquire artifact lock for %s; checking cache", artifact_key)
                if local_path.exists() and content_sha:
                    if self._sha256(local_path) == content_sha:
                        self.logger.debug("Cache valid for %s after failing acquire; returning cache", local_path)
                        return DownloadResult(local_path, from_cache=True, content_sha256=content_sha)
                raise RuntimeError("Failed to acquire artifact lock and cache not valid")

            try:
                # re-check under lock
                if not force_download and local_path.exists() and content_sha:
                    try:
                        if self._sha256(local_path) == content_sha:
                            self.logger.debug("Cache hit (after lock) for %s", local_path)
                            return DownloadResult(local_path, from_cache=True, content_sha256=content_sha)
                        else:
                            self.logger.info("Cache sha mismatch for %s; re-downloading", local_path)
                    except Exception:
                        self.logger.info("Failed to compute local sha; re-downloading")

                # perform download via provider into the target location (provider will use its temp->atomic)
                self.logger.info("Downloading artifact %s (remote=%s) into %s", filename, remote_path, local_path)
                t0 = time.time()
                saved = self.provider.download(remote_path, str(local_path), overwrite=True)
                t1 = time.time()
                saved_path = Path(saved)
                self.logger.info("Downloaded %s => %s (%.2fs)", remote_path, saved_path, (t1 - t0))
                if content_sha:
                    if self._sha256(saved_path) != content_sha:
                        saved_path.unlink(missing_ok=True)
                        self.logger.error("Downloaded file SHA mismatch for %s/%s/%s", package_name, version_code,
                                          filename)
                        raise RuntimeError(f"Downloaded file SHA mismatch for {package_name}/{version_code}/{filename}")
                return DownloadResult(saved_path, from_cache=False, content_sha256=content_sha)
            finally:
                self._release(artifact_key)

        elif ftype == "xapk":
            xapk_name = file_info.get("filename")
            content_sha = file_info.get("content_sha256")
            remote_path = self._artifact_remote_path(package_name, version_code, xapk_name)
            local_path = self._artifact_local_path(package_name, version_code, xapk_name)
            local_path.parent.mkdir(parents=True, exist_ok=True)

            artifact_key = f"artifact:{package_name}:{version_code}:{xapk_name}"
            got = self._acquire(artifact_key, timeout=self.default_lock_timeout)
            if not got:
                self.logger.warning("Could not acquire artifact lock for %s; checking cache", artifact_key)
                if local_path.exists() and content_sha:
                    if self._sha256(local_path) == content_sha:
                        self.logger.debug("Cache valid for xapk %s after failing acquire; returning cache", local_path)
                        return DownloadResult(local_path, from_cache=True, content_sha256=content_sha)
                raise RuntimeError("Failed to acquire artifact lock and cache not valid for xapk")

            try:
                if not force_download and local_path.exists() and content_sha:
                    try:
                        if self._sha256(local_path) == content_sha:
                            self.logger.debug("Cache hit (after lock) for xapk %s", local_path)
                            if extract_xapk:
                                # Ensure extracted contained/ dir exists
                                self._ensure_xapk_extracted_with_lock(local_path, package_name, version_code)
                            return DownloadResult(local_path, from_cache=True, content_sha256=content_sha)
                        else:
                            self.logger.info("Cache sha mismatch for xapk %s; re-downloading", local_path)
                    except Exception:
                        self.logger.info("Failed to compute local xapk sha; re-downloading")

                self.logger.info("Downloading xapk %s (remote=%s) into %s", xapk_name, remote_path, local_path)
                t0 = time.time()
                saved = self.provider.download(remote_path, str(local_path), overwrite=True)
                t1 = time.time()
                saved_path = Path(saved)
                self.logger.info("Downloaded xapk %s => %s (%.2fs)", remote_path, saved_path, (t1 - t0))
                if content_sha:
                    if self._sha256(saved_path) != content_sha:
                        saved_path.unlink(missing_ok=True)
                        self.logger.error("Downloaded xapk SHA mismatch for %s/%s/%s", package_name, version_code,
                                          xapk_name)
                        raise RuntimeError(
                            f"Downloaded xapk SHA mismatch for {package_name}/{version_code}/{xapk_name}")
                if extract_xapk:
                    self._ensure_xapk_extracted_with_lock(saved_path, package_name, version_code)
                return DownloadResult(saved_path, from_cache=False, content_sha256=content_sha)
            finally:
                self._release(artifact_key)
        else:
            raise RuntimeError(f"Unknown file type in meta: {ftype}")

    # ---------------- xapk extraction helpers ----------------
    def _extract_xapk_to_cache(self, xapk_local_path: Path, package_name: str, version_code: Union[int, str]) -> Path:
        """
        幂等地将 xapk 中的所有文件提取到:
          <cache>/packages/<package>/<version>/contained/

        要点：
          - 保留 xapk 中的所有文件（不仅限于 .apk），以便后续的 provider 或安装逻辑可以读取目录内所有关键文件完成安装。
          - 不会删除或清理目录中已存在但不在 xapk 内的额外文件（遵守“不要删除非apk文件”的要求）。
          - 对每个被解压的文件：先写入同目录下的临时文件（.tmp），写入成功后原子替换到目标路径。
          - 对于 meta 中声明了 content_sha256 的条目（通常针对 contained apks），若本地已存在且 sha 匹配，则跳过该文件的写入以节省 I/O。
          - 本函数**不做进程间锁**；上层应使用 `_ensure_xapk_extracted_with_lock` 实现跨进程同步。
          - 返回提取目录 Path（`contained_dir`），调用者可根据需要使用该目录。
        """
        contained_dir = self._packages_cache_dir / package_name / str(version_code) / "contained"
        contained_dir.mkdir(parents=True, exist_ok=True)

        # meta 中可能包含 contained_apks 列表及其 content_sha256，我们使用它来减少不必要的覆盖
        meta = self.get_cached_meta(package_name, version_code) or {}
        contained_meta = (meta.get("file", {}) or {}).get("contained_apks", []) or []

        # build a lookup: filename -> expected sha (if provided)
        expected_sha_map = {}
        for c in contained_meta:
            fname = Path(c.get("filename", "")).name
            sha = c.get("content_sha256")
            if fname:
                expected_sha_map[fname] = sha

        # open zip and extract ALL entries (preserve directory structure), but be path-traversal safe
        with zipfile.ZipFile(str(xapk_local_path), "r") as zf:
            for member in zf.namelist():
                # normalize member path and avoid absolute / traversal entries
                member_path = Path(member)
                # Do NOT skip on '.' in parts - we check safety by resolving against contained_dir
                if member_path.is_absolute():
                    # skip absolute entries
                    continue

                # target path under contained_dir using the basename or the member path relative structure.
                # We keep internal paths to preserve any internal directory layout.
                target_path = (contained_dir / member_path).resolve()

                # Ensure the target is still within contained_dir (safety check)
                try:
                    target_path.relative_to(contained_dir.resolve())
                except Exception:
                    # if it's outside the intended dir for any reason, skip it
                    continue

                # If the member is a directory entry (endswith '/'), ensure dir exists and continue
                if member.endswith("/") or member_path.name == "":
                    target_path.mkdir(parents=True, exist_ok=True)
                    continue

                # For file entries: prepare tmp path then write and atomically replace
                tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")

                # If expected SHA present and file exists and matches -> skip extracting this file
                expected_sha = expected_sha_map.get(target_path.name)
                if expected_sha and target_path.exists():
                    try:
                        if self._sha256(target_path) == expected_sha:
                            # already present and matches expected content; skip extraction
                            continue
                    except Exception:
                        # on any sha-check failure, fall through to re-extract
                        pass

                # Ensure parent dir exists
                target_path.parent.mkdir(parents=True, exist_ok=True)

                # Extract member to tmp file then atomically replace
                try:
                    with zf.open(member) as src, tmp_path.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                    # Move/replace atomically (Path.replace on same filesystem)
                    tmp_path.replace(target_path)
                finally:
                    # safety: ensure temp file removed if something went wrong
                    if tmp_path.exists():
                        try:
                            tmp_path.unlink()
                        except Exception:
                            pass

        # keep all existing files that are not part of the xapk (do not delete anything)
        self.logger.debug("Extraction complete for %s/%s into %s", package_name, version_code, contained_dir)
        return contained_dir

    def _ensure_xapk_extracted_with_lock(self,
                                         xapk_local_path: Path,
                                         package_name: str,
                                         version_code: Union[int, str],
                                         timeout_seconds: float = 120.0,
                                         poll_interval: float = 0.5) -> Path:
        """
        确保 xapk 被解压到 contained/ 目录，并处理多进程竞争：
          - lock key 使用 xapk 的 content_sha（若 meta 中有）或 xapk 文件 sha 的组合，
            形如: f"xapk_extract:{package}:{version}:{content_sha}"，保证当 xapk 文件改变时会用新的锁和新目录。
          - 尝试 acquire 锁（blocking, timeout = timeout_seconds）。获得锁的进程负责调用 _extract_xapk_to_cache。
          - 未获得锁的进程会轮询检测 contained 目录是否已完成（通过校验全部 expected contained 文件存在并校验 sha）。
          - 若超时仍未准备好，抛出 TimeoutError。
        返回：contained_dir Path（已存在且包含 extracted apks）。
        """
        import time
        from pathlib import Path

        start = time.time()
        meta = self.get_cached_meta(package_name, version_code) or {}
        file_info = meta.get("file", {}) or {}
        # prefer meta declared xapk sha, fallback to actual file sha
        xapk_content_sha = file_info.get("content_sha256")
        if not xapk_content_sha:
            try:
                xapk_content_sha = self._sha256(xapk_local_path)
            except Exception:
                xapk_content_sha = "nosha"

        lock_key = f"xapk_extract:{package_name}:{version_code}:{xapk_content_sha}"
        contained_dir = self._packages_cache_dir / package_name / str(version_code) / "contained"

        # helper: validate that contained_dir satisfies meta expectations
        def _is_extraction_complete() -> bool:
            # If meta lists contained_apks, require each filename present and (if content_sha provided) matching.
            contained_meta = (meta.get("file", {}) or {}).get("contained_apks", []) or []
            if contained_meta:
                for c in contained_meta:
                    fname = Path(c.get("filename", "")).name
                    expected_sha = c.get("content_sha256")
                    target = contained_dir / fname
                    if not target.exists():
                        return False
                    if expected_sha:
                        try:
                            if self._sha256(target) != expected_sha:
                                return False
                        except Exception:
                            return False
                return True
            else:
                # if meta lacks list, treat extraction complete if at least one .apk exists
                if contained_dir.exists() and any(p.suffix.lower() == ".apk" for p in contained_dir.iterdir()):
                    return True
                return False

        # Quick check: maybe already extracted and valid
        if _is_extraction_complete():
            self.logger.debug("xapk already extracted for %s/%s", package_name, version_code)
            return contained_dir

        # Try to acquire lock for extraction
        remaining = timeout_seconds - (time.time() - start)
        if remaining <= 0:
            raise TimeoutError("Timeout before attempting to acquire extract lock")

        got = self._acquire(lock_key, timeout=remaining)
        if not got:
            # couldn't acquire lock within remaining -> wait until other process finishes, polling contained_dir
            end_time = start + timeout_seconds
            while time.time() < end_time:
                if _is_extraction_complete():
                    self.logger.debug("xapk extraction observed complete (other process) for %s/%s", package_name,
                                      version_code)
                    return contained_dir
                time.sleep(poll_interval)
            raise TimeoutError("Timed out waiting for xapk extraction (failed to acquire lock)")
        # We hold the lock now; do double-check and extract if necessary
        try:
            if _is_extraction_complete():
                return contained_dir
            # perform extraction (this method is idempotent and atomic per-file)
            self.logger.info("Performing xapk extraction for %s/%s (holding lock %s)", package_name, version_code,
                             lock_key)
            self._extract_xapk_to_cache(xapk_local_path, package_name, version_code)
            # verify
            if not _is_extraction_complete():
                self.logger.error("Extraction finished but validation failed for %s/%s", package_name, version_code)
                raise RuntimeError("Extraction finished but validation failed")
            self.logger.info("xapk extraction done for %s/%s", package_name, version_code)
            return contained_dir
        finally:
            try:
                self._release(lock_key)
            except Exception:
                self.logger.debug("Failed to release xapk extract lock %s", lock_key)

    @staticmethod
    def _sha256(p: Path) -> str:
        import hashlib
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    # ---------------- selection helper (unchanged) ----------------
    @staticmethod
    def select_best_apk_for_device(meta: Dict[str, Any], device_abis: List[str]) -> Optional[Dict[str, Any]]:
        file_info = meta.get("file", {})
        ctype = file_info.get("type")
        if ctype == "apk":
            abis = file_info.get("abis") or meta.get("abis") or []
            if not abis:
                return {"container_type": "apk", "container_filename": file_info.get("filename"), "selected": file_info}
            for d in device_abis:
                if d in abis:
                    return {"container_type": "apk", "container_filename": file_info.get("filename"),
                            "selected": file_info}
            return None
        elif ctype == "xapk":
            contained = file_info.get("contained_apks", []) or []
            for d in device_abis:
                for c in contained:
                    if d in (c.get("abis") or []):
                        return {"container_type": "xapk", "container_filename": file_info.get("filename"),
                                "selected": c}
            for c in contained:
                if set(c.get("abis") or []) & set(device_abis):
                    return {"container_type": "xapk", "container_filename": file_info.get("filename"), "selected": c}
            for c in contained:
                if c.get("filename", "").lower().endswith("base.apk"):
                    return {"container_type": "xapk", "container_filename": file_info.get("filename"), "selected": c}
            if contained:
                return {"container_type": "xapk", "container_filename": file_info.get("filename"),
                        "selected": contained[0]}
            return None
        else:
            return None

    @staticmethod
    def _probe_device_info(device_id: str, package_name: str, include_cache=False) -> Tuple[Optional[int], Optional[str]]:
        try:
            a = adb.get_installed_package_version_code(device_id, package_name, include_cache)
            b = adb.get_installed_package_version(device_id, package_name, include_cache)
            if a < 0 or not b:
                return None, None
            return a, b
        except Exception:
            return None, None

    # ---------------- missing request helper ----------------
    def submit_missing_request(self, package_name: str, version_code: Union[int, str], notes: str = ""):
        """
        Submit a missing artifact request to repo requests dir; idempotent.
        If a request file for same package/version exists, skip.
        """
        req_dir = self._requests_local_dir
        req_dir.mkdir(parents=True, exist_ok=True)
        req_file = req_dir / f"{package_name}_{version_code}.req"
        if req_file.exists():
            self.logger.debug("Missing request already exists for %s/%s", package_name, version_code)
            return False
        try:
            req = {
                "package": package_name,
                "version": version_code,
                "notes": notes,
                "ts": datetime.utcnow().isoformat() + "Z"
            }
            req_file.write_text(json.dumps(req, ensure_ascii=False, indent=2), encoding="utf-8")
            self.logger.info("Submitted missing request for %s/%s", package_name, version_code)
            return True
        except Exception as e:
            self.logger.exception("Failed to write missing request file for %s/%s: %s", package_name, version_code, e)
            return False

    # ---------------- new: parallel prefetch helper ----------------
    def prefetch_caches_parallel(self,
                                 pkg_ver_list: List[Tuple[str, Union[int, str]]],
                                 max_workers: Optional[int] = None,
                                 force_download: bool = False,
                                 extract_xapk: bool = False) -> Dict[Tuple[str, Union[int, str]], Dict[str, Any]]:
        """
        Prefetch a list of (package, version) pairs into cache in parallel.
        Returns mapping (package, version) -> result dict:
            { "success": bool, "download_result": DownloadResult or None, "error": str or None }

        - Uses self._download_semaphore to limit concurrent provider download operations.
        - Each task will call update_cache_for_package internally (so artifact-level locks are respected).
        - This method is reusable (you can call it outside install_batch_parallel).
        """
        if not pkg_ver_list:
            return {}

        max_workers = int(max_workers or min(8, len(pkg_ver_list)))
        results: Dict[Tuple[str, Union[int, str]], Dict[str, Any]] = {}

        def _task(pkg, ver):
            key = (pkg, ver)
            try:
                self.logger.debug("Prefetch task queued for %s/%s", pkg, ver)
                # Acquire semaphore to limit provider concurrency
                acquired = self._download_semaphore.acquire(timeout=600)
                if not acquired:
                    self.logger.warning("Timeout waiting for download semaphore for %s/%s", pkg, ver)
                    return key, {"success": False, "download_result": None, "error": "semaphore_timeout"}
                try:
                    self.logger.info("Starting cached download for %s/%s (controlled slot)", pkg, ver)
                    dr = self.update_cache_for_package(pkg, ver, force_download=force_download,
                                                       extract_xapk=extract_xapk)
                    self.logger.info("Prefetch finished for %s/%s -> %s (from_cache=%s)", pkg, ver, dr.local_path,
                                     dr.from_cache)
                    return key, {"success": True, "download_result": dr, "error": None}
                finally:
                    self._download_semaphore.release()
            except Exception as e:
                self.logger.exception("Prefetch failed for %s/%s: %s", pkg, ver, e)
                return key, {"success": False, "download_result": None, "error": repr(e)}

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_task, pkg, ver): (pkg, ver) for (pkg, ver) in pkg_ver_list}
            for fut in as_completed(futures):
                pkg, ver = futures[fut]
                try:
                    k, r = fut.result()
                except Exception as e:
                    self.logger.exception("Unexpected exception in prefetch future for %s/%s: %s", pkg, ver, e)
                    r = {"success": False, "download_result": None, "error": repr(e)}
                    k = (pkg, ver)
                results[k] = r
        return results

    # ---------------- install_batch_parallel (enhanced) ----------------
    def install_batch_parallel(self,
                               device_id: str,
                               install_specs: List[Union[str, Dict[str, Any]]],
                               compare_mode_default: str = "existence",
                               max_workers: int = 8,
                               per_install_timeout: int = 3600,
                               install_options: Tuple[str, ...] = ('-r', '-g', '-t'),
                               precheck: bool = True,
                               allow_remote_fetch: bool = True,
                               force: bool = False,
                               downgrade: bool = False,
                               retries: int = 2) -> Dict[str, Dict[str, Any]]:
        """
        并行批量安装多个 app 到同一台设备的方案（ThreadPoolExecutor）。
        - install_specs: list of package_name (str) or dicts with keys matching install_cached_to_device params
          e.g. "com.example.app"  or {"package_name": "com.example.app", "version_code": 123, "device_abis": [.]}
        - 返回: dict mapping task_key -> result_dict (result format same as install_cached_to_device)
        - precheck=True: 在提交实际安装前并发地做 compare-only 检查以过滤掉可跳过项，避免下载。
        - 每个任务会使用 per_install_timeout 作为其超时时间（install_cached_to_device 的 timeout_seconds）
        Note: 本方法不会自动对设备加锁（除非 caller 的 spec 指定 device_lock=True）。
        """
        # normalize specs to dicts
        norm_specs: List[dict] = []
        for s in install_specs:
            if isinstance(s, str):
                norm_specs.append({"package_name": s, "compare_mode": compare_mode_default})
            elif isinstance(s, dict):
                d = dict(s)
                if "package_name" not in d:
                    raise ValueError("install spec dict must contain 'package_name'")
                d.setdefault("compare_mode", compare_mode_default)
                norm_specs.append(d)
            else:
                raise ValueError("install_specs entries must be str or dict")

        # Build per-spec defaults
        for d in norm_specs:
            d.setdefault("device_abis", ["arm64-v8a", "armeabi-v7a"])
            d.setdefault("compare_mode", "existence")
            d.setdefault("install_options", install_options)
            d.setdefault("allow_remote_fetch", allow_remote_fetch)
            d.setdefault("force", force)
            d.setdefault("downgrade", downgrade)
            d.setdefault("retries", retries)
            d.setdefault("timeout_seconds", per_install_timeout)
            d.setdefault("device_lock", False)

        # helper: perform compare-only check (without downloading) -> return True if needs install
        def _needs_install(spec) -> Tuple[bool, Optional[Dict[str, Any]]]:
            pkg = spec["package_name"]
            comp_mode = (spec.get("compare_mode") or "existence").lower()
            version_code = spec.get("version_code")
            # device_abis = spec.get("device_abis")

            # probe device
            try:
                dvc_code, dvc_name = self._probe_device_info(device_id, pkg)
            except Exception as e:
                self.logger.debug("Device probe failed for %s: %s", pkg, e)
                dvc_code, dvc_name = None, None

            # decide early if we can skip without downloading meta/artifact.
            if comp_mode == "none" or spec.get("force"):
                return True, {"device_before": {"version_code": dvc_code, "version_name": dvc_name}}

            # if compare_mode == existence: skip if installed
            if comp_mode == "existence":
                if dvc_code is not None or dvc_name is not None:
                    self.logger.info("Skipping %s due to existence on device (compare_mode=existence)", pkg)
                    return False, {"device_before": {"version_code": dvc_code, "version_name": dvc_name},
                                   "reason": "existence_skip"}
                return True, {"device_before": {"version_code": dvc_code, "version_name": dvc_name}}

            # For version_code/name comparisons we may need meta to resolve requested version if not specified
            res = {"device_before": {"version_code": dvc_code, "version_name": dvc_name}}
            if comp_mode in ("version_code", "prefer_newer"):
                # try to resolve requested version_code if not provided
                if version_code is None:
                    latest = self.get_latest_version_from_index(pkg)
                    if latest:
                        version_code = latest.get("latest_version_code") or latest.get("latest_version")
                        if version_code is not None:
                            spec["version_code"] = version_code
                            res["resolved_version"] = version_code
                            self.logger.debug("Resolved latest version for %s -> %s", pkg, version_code)
                # compare numeric version
                try:
                    if dvc_code is not None and version_code is not None:
                        req_v = int(version_code)
                        if dvc_code == req_v:
                            self.logger.info("Device already has same version_code for %s -> skipping", pkg)
                            return False, {**res, "reason": "version_code_equal_skip"}
                        if dvc_code > req_v and not spec.get("downgrade", False):
                            self.logger.info("Device version (%s) is newer than target (%s) for %s -> skipping",
                                             dvc_code, req_v, pkg)
                            return False, {**res, "reason": "device_has_newer_version_skip"}
                except Exception:
                    # fall through to require install (conservative)
                    self.logger.debug("Numeric version compare failed for %s; will proceed to install", pkg)
                    return True, res

            if comp_mode == "version_name":
                # best effort using device version name
                tgt_name = spec.get("version_name")
                if not tgt_name:
                    latest = self.get_latest_version_from_index(pkg)
                    if latest:
                        tgt_name = latest.get("version_name")
                        spec["version_name"] = tgt_name
                if dvc_name and tgt_name and dvc_name == tgt_name:
                    self.logger.info("Device already has same version_name for %s -> skipping", pkg)
                    return False, {**res, "reason": "version_name_equal_skip"}
                return True, res

            # default conservative: install
            return True, res

        # 1) precheck stage (parallel)
        precheck_map: Dict[int, Dict[str, Any]] = {}
        if precheck:
            self.logger.info("Running precheck for %d specs (parallel=%d)", len(norm_specs),
                             min(max_workers, len(norm_specs)))
            with ThreadPoolExecutor(max_workers=min(max_workers, max(1, len(norm_specs)))) as ex:
                futures = {ex.submit(_needs_install, spec): i for i, spec in enumerate(norm_specs)}
                for fut in as_completed(futures):
                    idx = futures[fut]
                    try:
                        needs, info = fut.result()
                    except Exception as e:
                        self.logger.exception("Precheck failed for spec idx %s: %s", idx, e)
                        needs, info = True, {"error": repr(e)}
                    precheck_map[idx] = {"needs_install": bool(needs), "info": info}

        else:
            # no precheck: assume all need install
            for i in range(len(norm_specs)):
                precheck_map[i] = {"needs_install": True, "info": {}}

        # prepare lists for those which really need downloading/install
        to_install_indices = [i for i, v in precheck_map.items() if v.get("needs_install")]
        skipped_indices = [i for i, v in precheck_map.items() if not v.get("needs_install")]

        results: Dict[str, Dict[str, Any]] = {}
        # mark skipped
        for i in skipped_indices:
            spec = norm_specs[i]
            key = f"{spec['package_name']}:{spec.get('version_code', 'latest')}"
            results[key] = {
                "package_name": spec["package_name"],
                "requested_version": spec.get("version_code"),
                "action": "skipped",
                "notes": ["precheck_skip", precheck_map[i].get("info", {}).get("reason")],
                "device_before": precheck_map[i].get("info", {}).get("device_before"),
                "elapsed_seconds": 0.0
            }

        if not to_install_indices:
            self.logger.info("No installs required after precheck.")
            return results

        # 2) prefetch caches in parallel (only the ones we need)
        pkg_ver_list = []
        for i in to_install_indices:
            spec = norm_specs[i]
            pkg = spec["package_name"]
            ver = spec.get("version_code")
            # try to resolve version if not provided
            if ver is None:
                latest = self.get_latest_version_from_index(pkg)
                if latest:
                    ver = latest.get("latest_version_code") or latest.get("latest_version")
                    spec["version_code"] = ver
            pkg_ver_list.append((pkg, ver))
        self.logger.info("Prefetching caches for %d packages (concurrency limited to %d)", len(pkg_ver_list),
                         self.max_concurrent_downloads)
        prefetch_results = self.prefetch_caches_parallel(pkg_ver_list,
                                                         max_workers=min(len(pkg_ver_list), max_workers),
                                                         force_download=False,
                                                         extract_xapk=False)

        # Record prefetch failures as failed results immediately (if not allowed remote fetch)
        install_candidates = []
        for i in to_install_indices:
            spec = norm_specs[i]
            pkg = spec["package_name"]
            ver = spec.get("version_code")
            if ver is not None:
                key = (pkg, ver)
                pre = prefetch_results.get(key)
            else:
                pre = None
            task_key = f"{pkg}:{ver}"
            if pre is None:
                # no prefetch info -> attempt direct install (will try to fetch if allow_remote_fetch)
                install_candidates.append((i, spec))
            elif not pre["success"]:
                # prefetch failed
                if not spec.get("allow_remote_fetch", True):
                    results[task_key] = {
                        "package_name": pkg,
                        "requested_version": ver,
                        "action": "failed",
                        "notes": [f"prefetch_failed:{pre.get('error')}"],
                        "elapsed_seconds": 0.0
                    }
                else:
                    # allow remote fetch -> still try
                    self.logger.warning(
                        "Prefetch failed for %s/%s but allow_remote_fetch=True -> will attempt install which may re-download",
                        pkg, ver)
                    install_candidates.append((i, spec))
            else:
                # prefetch success -> proceed to install using cached artifact
                install_candidates.append((i, spec))

        if not install_candidates:
            self.logger.info("No installation candidates after prefetch and policy checks.")
            return results

        # 3) perform parallel installs (each will call install_cached_to_device)
        def _install_task(idx_spec_tuple):
            idx, spec = idx_spec_tuple
            pkg = spec["package_name"]
            ver = spec.get("version_code")
            task_key = f"{pkg}:{ver}"
            self.logger.info("Starting install task for %s (idx=%s)", task_key, idx)
            try:
                res = self.install_cached_to_device(
                    device_id=device_id,
                    package_name=pkg,
                    version_code=ver,
                    device_abis=spec.get("device_abis"),
                    compare_mode=spec.get("compare_mode", "existence"),
                    install_options=spec.get("install_options", install_options),
                    allow_remote_fetch=spec.get("allow_remote_fetch", True),
                    force=spec.get("force", False),
                    downgrade=spec.get("downgrade", False),
                    retries=spec.get("retries", retries),
                    device_lock=spec.get("device_lock", False),
                    timeout_seconds=spec.get("timeout_seconds", per_install_timeout)
                )
                if isinstance(res, dict):
                    self.logger.info("Install finished for %s: action=%s", task_key, res.get("action"))
                    return task_key, res
                else:
                    self.logger.warning("Install returned non-dict for %s -> wrapping", task_key)
                    return task_key, {"action": "failed", "notes": ["invalid_install_result"], "raw": res}
            except Exception as e:
                self.logger.exception("Install task for %s failed: %s", task_key, e)
                return task_key, {"action": "failed", "notes": [f"exception:{repr(e)}"]}

        with ThreadPoolExecutor(max_workers=min(max_workers, max(1, len(install_candidates)))) as ex:
            futures = {ex.submit(_install_task, t): t for t in install_candidates}
            for fut in as_completed(futures):
                try:
                    k, r = fut.result()
                except Exception as e:
                    self.logger.exception("Unexpected exception in install future: %s", e)
                    # derive key from tuple if possible
                    tup = futures[fut]
                    pkg = tup[1]["package_name"]
                    ver = tup[1].get("version_code")
                    k = f"{pkg}:{ver}"
                    r = {"action": "failed", "notes": [repr(e)]}
                results[k] = r

        return results

    # ---------------- remaining existing methods unchanged ----------------
    # (keep your previously implemented install_cached_to_device and other helpers)
    # For clarity, we include install_cached_to_device signature and implementation here,
    # but do not change its contract except added logs at key points.
    def install_cached_to_device(self,
                                 device_id: str,
                                 package_name: str,
                                 version_code: Optional[Union[int, str]] = None,
                                 device_abis: Optional[List[str]] = None,
                                 compare_mode: str = "existence",
                                 install_options: Tuple[str, ...] = ('-r', '-g', '-t'),
                                 allow_remote_fetch: bool = True,
                                 force: bool = False,
                                 downgrade: bool = False,
                                 retries: int = 2,
                                 device_lock: bool = False,
                                 timeout_seconds: int = 3600) -> Dict[str, Any]:
        """
        安装仓库中的 app 到指定 Android 设备

        简要
        ----
        将仓库（通过 provider）中的某个 package/version 的 artifact（apk 或 xapk）安装到指定设备。
        该函数会负责：
          * 从 remote 拉取或使用本地缓存的 global_index/meta/artifact（可控是否允许远端拉取）；
          * 根据 device_abis 与 meta 选择最合适的二进制（apk 或 xapk）；
          * 在需要时把 artifact 下载并缓存（`update_cache_for_package`，受 artifact 锁保护）；
          * 根据 `compare_mode` 决定是否跳过安装（默认宽松：只要设备存在该包就跳过）；
          * 使用 provider.local_adb_install(...) 执行真正的安装操作（provider 必须实现该方法）；
          * （可选）对设备加锁，避免并发安装冲突（受注入的 resource_lock_manager 控制）；
          * 全程遵循 `timeout_seconds` 的总时限，返回详细的操作结果便于排查。

        参数
        ----
        package_name (str)
            要安装的应用包名（如 "com.example.app"）。必填。

        version_code (Optional[int|str], default=None)
            指定要安装的 versionCode。若为 None（默认），会从 global_index 中选取当前最新版本。

        device_id (str)
            目标设备标识（例如 adb serial）。**必填**，无默认值。

        device_abis (Optional[List[str]], default=None)
            设备支持的 ABI 列表（按优先级，从高到低），例如 ["arm64-v8a","armeabi-v7a"]。
            若为 None，默认使用 ["arm64-v8a","armeabi-v7a"]（首选 64 位）。

        compare_mode (str, default="existence")
            安装前的版本/存在性比较策略（决定是否跳过安装）：
              - "none"：不比较，总是尝试安装（受 force 控制）。
              - "existence"：只要设备上存在该包（任意版本）就跳过（**默认、宽松**）。
              - "version_code"：按 numeric versionCode 比较（支持跳过相同或更高版本；受 downgrade 控制）。
              - "version_name"：按 versionName 字符串比较（先精确比，再尝试数值段比较）。
              - "prefer_newer"：优先尝试 version_code，比不可用时退回 version_name。

        install_options (Tuple[str,...], default=('-r','-g','-t'))
            传递给 provider.local_adb_install 的安装选项（如 adb install 的参数）。

        allow_remote_fetch (bool, default=True)
            是否允许在本地缓存缺失时从远端 repo 下载 artifact（True：允许；False：不允许，缺失则报错）。

        force (bool, default=False)
            强制安装，忽略比较策略（即使版本相同也会安装）。

        downgrade (bool, default=False)
            是否允许降级安装（当设备上版本高于目标版本时）。默认 False。

        retries (int, default=2)
            当调用 provider.local_adb_install 失败时的最大重试次数（总尝试次数）。

        device_lock (bool, default=False)
            是否对目标设备加锁（使用 resource_lock_manager.acquire_resource / release_resource）。
            默认为 False（不自动加设备级锁）。若为 True，需确保在初始化时注入可用的 lock manager；
            未注入时退化为进程内锁（**无法跨进程/跨主机互斥**）。

        timeout_seconds (int, default=300)
            本次操作的**总超时时间（秒）**。函数在各个阶段都会检查是否超时；若超时会尽快终止并以 timed_out 返回。

        返回值（dict）
        ----
        函数始终返回一个 dict，包含操作的详细记录，主要字段包括但不限于：
          - package_name: str
          - requested_version: 原始输入的 version_code（或 None）
          - resolved_version: 实际用于安装的 version_code（若输入为 None 则为 index 上解析到的最新）
          - container_type: "apk" | "xapk"
          - selected: 被选中的 meta 条目（apk 条目或 xapk.contained_apk 条目）
          - artifact_local_path: 本地缓存的 artifact 路径（apk 或 xapk）
          - device_before: {"version_code": int|None, "version_name": str|None}（安装前探测结果）
          - device_after:  同上（安装后探测结果，若可探测）
          - action: "installed" | "skipped" | "failed" | "timed_out"
          - install_attempts: list of {attempt, start, duration_seconds, success, error?}
          - timed_out: bool
          - notes: list of short diagnostic strings (例如 "existence_skip", "artifact_not_cached_and_no_fetch", ...)
          - timestamp, elapsed_seconds: 操作时间信息

        行为约定与细节
        ----
        * Artifact 选择
          - 使用 `select_best_apk_for_device(meta, device_abis)` 决定安装目标（apk 或 xapk 中的 contained apk）。

        * 缓存与校验
          - 下载时会尽量使用本地缓存；若 meta 提供 `content_sha256`，会校验下载文件与声明 hash 是否一致以保证完整性。
          - `update_cache_for_package` 内部对 artifact 使用 artifact 级别锁，避免并发写入造成损坏。

        * 并发控制
          - 建议注入实现良好的 `resource_lock_manager`（数据库/redis 等实现），以获得跨进程/跨主机的互斥能力。
          - 若未注入，客户端会使用进程内锁作为回退方案（只能保障同一进程内的线程安全）。
          - `device_lock` 为 True 时，方法会尝试获取 key=`device:{device_id}` 的锁，防止同一设备被并发写入。

        * 版本比较语义
          - 在 `compare_mode != "none"` 且 `force == False` 时，方法会尝试探测设备安装的版本（优先使用 provider 提供的查询接口，如 `get_installed_version`；若不可用则回退到 adb dumpsys）。
          - 各 `compare_mode` 的具体判定逻辑见上文“参数详解”部分。`downgrade=True` 用于允许把设备上的较高版本降级到 target。

        * 超时
          - `timeout_seconds` 为此次调用的总时限。函数会在下载/探测/安装循环中检查剩余时间并尽早返回 `timed_out` 状态。

        异常与错误处理
        ----
        函数会在无法进行关键操作时抛出异常（便于上层捕获），典型包括但不限于：
          - `FileNotFoundError`：meta/artifact 在缓存和远端均不存在且 `allow_remote_fetch=False`，或下载失败。
          - `RuntimeError`：provider 不支持 `local_adb_install`、锁管理器异常等。
        此外，函数也会以返回的 `install_attempts` 与 `notes` 提供详细失败信息，调用者应结合异常与返回值做完整的错误处理与日志记录。

        示例（简短）
        ----
        # 安装最新（宽松：若设备已安装任意版本则跳过）
        res = client.install_cached_to_device("com.example.app", device_id="device123")

        # 强制重装最新
        res = client.install_cached_to_device("com.example.app", device_id="device123", force=True)

        # 安装特定 versionCode，按 version_code 比较并禁止降级
        res = client.install_cached_to_device("com.example.app", version_code=200, device_id="device123",
                                              compare_mode="version_code", downgrade=False)
        """

        def _info(fmt, *a, **k):
            self.logger.info(fmt, *a, ext_event=True, **k)

        def _debug(fmt, *a, **k):
            self.logger.debug(fmt, *a, **k)

        # start timer
        start = time.time()

        def elapsed() -> float:
            return time.time() - start

        if device_abis is None:
            device_abis = ["arm64-v8a", "armeabi-v7a"]

        compare_mode = (compare_mode or "existence").lower()

        result: Dict[str, Any] = {
            "package_name": package_name,
            "requested_version": version_code,
            "resolved_version": None,
            "container_type": None,
            "selected": None,
            "artifact_local_path": None,
            "device_before": None,
            "device_after": None,
            "action": None,
            "install_attempts": [],
            "timed_out": False,
            "notes": [],
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "elapsed_seconds": 0.0
        }

        if not device_id:
            raise ValueError("device_id is required")

        # -------------------------
        # 0) Resolve requested version early if needed for precheck
        # -------------------------
        resolved_version = version_code
        if resolved_version is None:
            # Only attempt to resolve latest from index (cheap) for compare modes that need a concrete target
            if compare_mode in ("version_code", "prefer_newer", "version_name"):
                latest = self.get_latest_version_from_index(package_name)
                if not latest:
                    # cannot resolve latest; we will conservatively proceed to installation path (can't skip)
                    _debug("Could not resolve latest for %s during precheck; proceeding conservatively", package_name)
                else:
                    resolved_version = latest.get("latest_version_code") or latest.get("latest_version")
                    if resolved_version is not None:
                        result["requested_version"] = resolved_version
                        _debug("Precheck resolved latest version for %s -> %s", package_name, resolved_version)

        # early timeout check
        if elapsed() > timeout_seconds:
            result.update({"timed_out": True, "action": "timed_out", "notes": ["timeout_before_start"],
                           "elapsed_seconds": elapsed()})
            return result

        # -------------------------
        # 1) PRECHECK: probe device + decide whether we can skip without downloading meta/artifact
        # -------------------------
        device_ver_code = None
        device_ver_name = None
        precheck_info: Dict[str, Any] = {}
        if compare_mode != "none" and not force:
            try:
                device_ver_code, device_ver_name = self._probe_device_info(device_id, package_name)
                precheck_info["device_before"] = {"version_code": device_ver_code, "version_name": device_ver_name}
                _debug("Precheck: probed device %s for %s -> code=%s name=%s", device_id, package_name, device_ver_code,
                       device_ver_name)
            except Exception as e:
                _debug("Precheck: probe_device_info failed for %s: %s", package_name, e)
                # if probe fails, be conservative and proceed (do not skip)
                device_ver_code, device_ver_name = None, None

            # existence: if device has package installed, skip immediately (no meta/artifact download)
            if compare_mode == "existence":
                if device_ver_code is not None or device_ver_name is not None:
                    result["device_before"] = precheck_info.get("device_before")
                    result["action"] = "skipped"
                    result["notes"].append("existence_skip")
                    result["elapsed_seconds"] = elapsed()
                    _info("Precheck skip (existence) for %s on device %s", package_name, device_id)
                    return result

            # version_code / prefer_newer: can often decide with device probe + resolved_version
            if compare_mode in ("version_code", "prefer_newer"):
                if resolved_version is not None and device_ver_code is not None:
                    try:
                        req_v = int(resolved_version)
                        dvc_v = int(device_ver_code)
                        if dvc_v == req_v:
                            result["device_before"] = precheck_info.get("device_before")
                            result["action"] = "skipped"
                            result["notes"].append("version_code_equal_skip")
                            result["elapsed_seconds"] = elapsed()
                            _info("Precheck skip (version_code equal) for %s on device %s", package_name, device_id)
                            return result
                        if dvc_v > req_v and not downgrade:
                            result["device_before"] = precheck_info.get("device_before")
                            result["action"] = "skipped"
                            result["notes"].append("device_has_newer_version_skip")
                            result["elapsed_seconds"] = elapsed()
                            _info("Precheck skip (device newer) for %s on device %s", package_name, device_id)
                            return result
                    except Exception:
                        _debug("Precheck numeric compare failed for %s; will continue to full flow", package_name)

            # version_name: if target name known and equals device -> skip
            if compare_mode == "version_name":
                target_name = None
                # prefer resolved_version -> meta would give version_name, but we try to avoid meta fetch if possible:
                # if user provided a version_name param (unlikely here), use it; otherwise, try index
                # resolve from index if possible
                if "version_name" in precheck_info:
                    target_name = precheck_info["version_name"]
                if target_name is None and resolved_version is not None:
                    # try to get latest meta info from index (but not full artifact)
                    latest = self.get_latest_version_from_index(package_name)
                    if latest:
                        target_name = latest.get("version_name")
                        if target_name:
                            _debug("Precheck resolved version_name from index for %s -> %s", package_name, target_name)
                if device_ver_name and target_name and device_ver_name == target_name:
                    result["device_before"] = precheck_info.get("device_before")
                    result["action"] = "skipped"
                    result["notes"].append("version_name_equal_skip")
                    result["elapsed_seconds"] = elapsed()
                    _info("Precheck skip (version_name equal) for %s on device %s", package_name, device_id)
                    return result

        # If we reach here: precheck did not allow skipping -> proceed to normal flow
        result["device_before"] = {"version_code": device_ver_code, "version_name": device_ver_name}

        # -------------------------
        # 2) Resolve version (if still None) and load meta (cached preferred, optional remote fetch)
        # -------------------------
        # If we didn't already resolve version, try now (this mirrors previous behavior)
        if resolved_version is None:
            latest = self.get_latest_version_from_index(package_name)
            if not latest:
                result["action"] = "failed"
                result["notes"].append("no-index-entry")
                raise FileNotFoundError(f"No index entry for package {package_name}")
            resolved_version = latest.get("latest_version_code") or latest.get("latest_version")
            result["requested_version"] = resolved_version

        # final timeout check
        if elapsed() > timeout_seconds:
            result.update({"timed_out": True, "action": "timed_out", "notes": ["timeout_before_meta"],
                           "elapsed_seconds": elapsed()})
            return result

        # load meta (cached preferred, optional remote fetch)
        meta = self.get_cached_meta(package_name, resolved_version)
        if meta is None and allow_remote_fetch:
            meta = self.get_remote_meta(package_name, resolved_version)
        if meta is None:
            try:
                self.submit_missing_request(package_name, resolved_version,
                                            notes="install_cached_to_device auto-request")
            except Exception:
                pass
            result["action"] = "failed"
            result["notes"].append("meta_missing; request_submitted")
            raise FileNotFoundError(f"Meta missing for {package_name}/{resolved_version}")

        result["resolved_version"] = resolved_version

        # -------------------------
        # 3) choose candidate by meta + device_abis
        # -------------------------
        selection = self.select_best_apk_for_device(meta, device_abis)
        if selection is None:
            result["action"] = "failed"
            result["notes"].append("no-compatible-artifact")
            raise RuntimeError(f"No compatible artifact in meta for device ABIs: {device_abis}")
        result["container_type"] = selection["container_type"]
        result["selected"] = selection["selected"]

        # -------------------------
        # 4) ensure artifact cached (no extraction here) — only executed because precheck required install
        # -------------------------
        try:
            if result["container_type"] == "apk":
                filename = selection["selected"].get("filename")
                if elapsed() > timeout_seconds:
                    result.update({"timed_out": True, "action": "timed_out", "notes": ["timeout_before_download"],
                                   "elapsed_seconds": elapsed()})
                    return result
                # update_cache_for_package will handle artifact-level locking and download
                self.update_cache_for_package(package_name, resolved_version, force_download=False)
                local_art = self._artifact_local_path(package_name, resolved_version, filename)
                result["artifact_local_path"] = str(local_art) if local_art else None
            else:
                # xapk: ensure cached but DO NOT extract here
                xapk_name = meta.get("file", {}).get("filename")
                if elapsed() > timeout_seconds:
                    result.update({"timed_out": True, "action": "timed_out", "notes": ["timeout_before_download_xapk"],
                                   "elapsed_seconds": elapsed()})
                    return result
                self.update_cache_for_package(package_name, resolved_version, force_download=False, extract_xapk=False)
                local_art = self._artifact_local_path(package_name, resolved_version, xapk_name)
                result["artifact_local_path"] = str(local_art) if local_art else None
        except Exception as e:
            result["action"] = "failed"
            result["notes"].append(f"download_error:{e}")
            raise

        # -------------------------
        # 5) verify artifact exists (try one forced fetch if allowed)
        # -------------------------
        artifact_path = Path(result["artifact_local_path"]) if result["artifact_local_path"] else None
        if not artifact_path or not artifact_path.exists():
            if allow_remote_fetch:
                try:
                    self.update_cache_for_package(package_name, resolved_version, force_download=True,
                                                  extract_xapk=False)
                except Exception as e:
                    result["action"] = "failed"
                    result["notes"].append(f"download_retry_failed:{e}")
                    raise
                artifact_path = Path(result["artifact_local_path"]) if result["artifact_local_path"] else None
                if not artifact_path or not artifact_path.exists():
                    result["action"] = "failed"
                    result["notes"].append("artifact_not_found_after_retry")
                    raise FileNotFoundError("Artifact not cached after retry")
            else:
                result["action"] = "failed"
                result["notes"].append("artifact_not_cached_and_no_fetch")
                raise FileNotFoundError("Artifact not cached and allow_remote_fetch=False")

        # -------------------------
        # 6) probe device (if not already obtained) — we already probed in precheck, but refresh if needed
        # -------------------------
        if compare_mode != "none" and result.get("device_before") is None:
            try:
                dc, dn = self._probe_device_info(device_id, package_name)
                result["device_before"] = {"version_code": dc, "version_name": dn}
            except Exception:
                result["notes"].append("device_probe_failed")

        # -------------------------
        # 7) final compare policy (honor force/downgrade) — we already attempted some prechecks, but re-evaluate conservatively
        # -------------------------
        def _parse_vername(vn: Optional[str]):
            if not vn:
                return ()
            nums = re.findall(r'\d+', vn)
            return tuple(int(x) for x in nums) if nums else (vn,)

        skip_install = False
        if not force:
            try:
                dvc_code = result.get("device_before", {}).get("version_code")
                dvc_name = result.get("device_before", {}).get("version_name")
                if compare_mode == "existence":
                    if dvc_code is not None or dvc_name is not None:
                        skip_install = True
                        result["notes"].append("existence_skip")
                elif compare_mode == "version_code":
                    if dvc_code is not None:
                        req_v = int(resolved_version)
                        if dvc_code == req_v:
                            skip_install = True
                            result["notes"].append("version_code_equal_skip")
                        elif dvc_code > req_v and not downgrade:
                            skip_install = True
                            result["notes"].append("device_has_newer_version_skip")
                elif compare_mode == "version_name":
                    if dvc_name is not None:
                        meta_vn = meta.get("version_name") or meta.get("version")
                        if meta_vn and dvc_name == meta_vn:
                            skip_install = True
                            result["notes"].append("version_name_equal_skip")
                        else:
                            if meta_vn and _parse_vername(dvc_name) == _parse_vername(meta_vn):
                                skip_install = True
                                result["notes"].append("version_name_tuple_equal_skip")
                elif compare_mode == "prefer_newer":
                    if dvc_code is not None:
                        req_v = int(resolved_version)
                        if dvc_code == req_v:
                            skip_install = True
                            result["notes"].append("prefer_newer_code_equal_skip")
                        elif dvc_code > req_v and not downgrade:
                            skip_install = True
                            result["notes"].append("prefer_newer_device_newer_skip")
                    elif dvc_name is not None:
                        meta_vn = meta.get("version_name") or meta.get("version")
                        if meta_vn and dvc_name == meta_vn:
                            skip_install = True
                            result["notes"].append("prefer_newer_name_equal_skip")
            except Exception:
                _debug("Final compare policy raised; proceeding to install for safety")

        if skip_install:
            result["action"] = "skipped"
            result["elapsed_seconds"] = elapsed()
            _info("Final policy skip for %s on device %s (%s)", package_name, device_id,
                  result["notes"][-1] if result["notes"] else "")
            return result

        # -------------------------
        # 8) optional device lock
        # -------------------------
        got_device_lock = False
        device_key = f"device:{device_id}"
        if device_lock:
            got_device_lock = self._acquire(device_key, timeout=min(30, timeout_seconds))
            if not got_device_lock:
                result["notes"].append("device_lock_failed")
                _debug("Device lock acquisition failed for %s", device_key)

        # -------------------------
        # 9) prepare final_install_path (extract xapk under global extraction lock if needed)
        # -------------------------
        final_install_path: Union[str, Path, None] = None
        if result["container_type"] == "apk":
            final_install_path = Path(result["artifact_local_path"])
        else:
            # xapk extraction: use lock-aware helper (single responsibility)
            remaining = max(0.0, timeout_seconds - elapsed())
            if remaining <= 0:
                if device_lock and got_device_lock:
                    self._release(device_key)
                result.update({"timed_out": True, "action": "timed_out", "notes": ["timeout_before_extraction"],
                               "elapsed_seconds": elapsed()})
                return result

            try:
                # this helper must implement cross-process lock & return the extracted "contained" dir path
                contained_dir = self._ensure_xapk_extracted_with_lock(
                    Path(result["artifact_local_path"]),
                    package_name,
                    resolved_version,
                    timeout_seconds=remaining
                )
                final_install_path = Path(contained_dir)
            except TimeoutError:
                if device_lock and got_device_lock:
                    self._release(device_key)
                result.update({"timed_out": True, "action": "timed_out", "notes": ["xapk_extraction_timeout"],
                               "elapsed_seconds": elapsed()})
                return result
            except Exception as e:
                if device_lock and got_device_lock:
                    self._release(device_key)
                result["action"] = "failed"
                result["notes"].append(f"xapk_extraction_failed:{e}")
                raise

        # -------------------------
        # 10) perform installation attempts via provider.local_adb_install
        # -------------------------
        install_func = None
        if hasattr(self.provider, "local_adb_install"):
            install_func = getattr(self.provider, "local_adb_install")
        else:
            try:
                install_func = getattr(self.provider.__class__, "local_adb_install")
            except Exception:
                install_func = None

        uninstall_func = getattr(self.provider, "local_adb_uninstall", None)
        need_uninstall = bool(uninstall_func and self._probe_device_info(device_id, package_name, include_cache=True)[0] is not None and self._probe_device_info(device_id, package_name, include_cache=False)[0] is None)

        if install_func is None:
            if device_lock and got_device_lock:
                self._release(device_key)
            result["action"] = "failed"
            result["notes"].append("provider_missing_local_adb_install")
            raise RuntimeError("Provider does not expose local_adb_install")

        if final_install_path is None or not Path(final_install_path).exists():
            if device_lock and got_device_lock:
                self._release(device_key)
            result["action"] = "failed"
            result["notes"].append("final_artifact_missing")
            raise FileNotFoundError("Final artifact path missing for installation")

        attempts = []
        success = False
        last_exc = None
        try:
            for attempt in range(1, max(1, retries) + 1):
                if elapsed() > timeout_seconds:
                    result.update({"timed_out": True})
                    result["notes"].append("timeout_before_attempt")
                    break
                t0 = time.time()
                attempt_info: Dict[str, Any] = {"attempt": attempt, "start": datetime.utcnow().isoformat() + "Z"}
                try:
                    if need_uninstall:
                        try:
                            self.logger.info(f'App residues found! Uninstall residues for {package_name}')
                            uninstall_func(device_id, package_name)
                        except Exception:
                            pass

                    # flexible call signature
                    try:
                        self.logger.info(f'Installing {package_name} from {final_install_path}')
                        ok = install_func(device_id, str(final_install_path), install_options)
                    except TypeError:
                        ok = install_func(device_id, str(final_install_path), install_options=install_options)
                    attempt_info["success"] = bool(ok)
                    attempt_info["duration_seconds"] = time.time() - t0
                    attempts.append(attempt_info)
                    if ok:
                        success = True
                        break
                    else:
                        last_exc = RuntimeError("provider.local_adb_install returned False")
                        attempt_info["error"] = "install_returned_false"
                except Exception as e:
                    last_exc = e
                    attempt_info["success"] = False
                    attempt_info["duration_seconds"] = time.time() - t0
                    attempt_info["error"] = repr(e)
                    attempts.append(attempt_info)
                    backoff = min(5, 2 ** attempt)
                    if elapsed() + backoff > timeout_seconds:
                        break
                    time.sleep(backoff)
        finally:
            # ensure device lock released if held
            if device_lock and got_device_lock:
                try:
                    self._release(device_key)
                except Exception:
                    _debug("Failed to release device lock %s", device_key)

        result["install_attempts"] = attempts

        # -------------------------
        # 11) final device probe (optional)
        # -------------------------
        if not result["timed_out"]:
            try:
                dc, dn = self._probe_device_info(device_id, package_name)
                result["device_after"] = {"version_code": dc, "version_name": dn}
            except Exception:
                result["device_after"] = None

        result["elapsed_seconds"] = elapsed()
        if result["timed_out"]:
            result["action"] = "timed_out"
            result["notes"].append("operation_timed_out")
            return result

        if success:
            result["action"] = "installed"
            result["notes"].append("install_success")
        else:
            result["action"] = "failed"
            if last_exc:
                result["notes"].append(f"last_exception:{repr(last_exc)}")

        return result

    # ---------------- cache utilities ----------------
    def list_cached_packages(self) -> List[Tuple[str, str]]:
        out = []
        if not self._packages_cache_dir.exists():
            return out
        for pkg_dir in self._packages_cache_dir.iterdir():
            if not pkg_dir.is_dir():
                continue
            for ver_dir in pkg_dir.iterdir():
                out.append((pkg_dir.name, ver_dir.name))
        return out

    def clear_cache(self, package_name: Optional[str] = None, version_code: Optional[Union[int, str]] = None):
        if package_name is None:
            shutil.rmtree(self._packages_cache_dir, ignore_errors=True)
            self._packages_cache_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info("Cleared entire package cache")
            return
        pkg_dir = self._packages_cache_dir / package_name
        if version_code is None:
            shutil.rmtree(pkg_dir, ignore_errors=True)
            self.logger.info("Cleared cache for package %s", package_name)
            return
        ver_dir = pkg_dir / str(version_code)
        shutil.rmtree(ver_dir, ignore_errors=True)
        self.logger.info("Cleared cache for %s/%s", package_name, version_code)

    def clean_stale_cache(self,
                          dry_run: bool = True,
                          keep_only_latest: bool = False,
                          packages: Optional[List[str]] = None,
                          lock_timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        清理本地 cache 中与远端 repo 不一致或不再需要的 version 目录（多进程安全）。

        行为概述
        - 若 keep_only_latest == False（默认）：对于本地每个 package/version，若远端没有对应的 meta.json（通过 provider.is_exists 检测），则删除该本地版本缓存（meta+artifact）。
        - 若 keep_only_latest == True：将只保留远端 index 中声明的最新版本（global_index 中 latest_version_code），删除该 package 的其它本地版本。
        - packages: 可选地限制为只针对指定包列表（list of package_name）执行清理；默认对本地 cache 下所有包执行。
        - dry_run: True 时仅列出将要删除的路径而不实际删除（默认 True）。
        - lock_timeout: 获取每个资源锁的超时（秒）。若 None 则使用 self.default_lock_timeout。

        并发/锁设计（必须理解）
        - 在读取 global_index 时，会尝试获取 key="index" 的锁以避免与并发更新冲突（若无法获取会回退并尽量使用缓存）。
        - 在删除某个 package/version 前，会尝试获取该资源的元数据级锁（key=f"meta:{package}:{version}"）。若无法获取锁（被其他进程持有），当前进程会跳过该版本并将其列入 skipped。
        - 该函数依赖于在初始化时注入的 resource_lock_manager（如果有）以实现跨进程/跨主机互斥；若没有注入，则回退为进程内 threading.Lock，只能保证线程内安全。

        返回（报告字典）
        {
          "checked": int,               # 遍历的本地 package/version 数量
          "candidates": int,            # 满足删除条件（dry_run 显示将删除）的数量
          "deleted": int,               # 实际删除数量（dry_run=False 时）
          "skipped_locked": [paths],    # 由于锁竞争而跳过的本地路径
          "skipped_keep": [paths],      # 因为策略保留的本地路径
          "errors": [ { "path": str, "error": str }, ... ],
          "deleted_paths": [paths],     # 实际删除的路径（dry_run=False）
          "timestamp": ISO8601
        }

        注意
        - provider.is_exists(remote_meta_path) 用于判断远端是否存在对应 meta.json；如果 provider.is_exists 抛异常，视为远端不存在（并记录错误）。
        - 在 keep_only_latest 模式下，我们以 global_index.json 中每个 package 的 latest_version_code 作为“应保留版本”。因此建议在执行该模式前确保 global_index 是最新（可先手动调用 fetch_global_index(force=True)）。
        - 如果你需要不同的保留策略（例如保留最近 N 个版本），可以在此基础上扩展：获取 local 版本列表 -> 排序 -> 仅删除超出保留阈值的版本（在删除前仍应按上面的锁与远端存在性检查）。
        """
        import shutil
        from datetime import datetime

        report = {
            "checked": 0,
            "candidates": 0,
            "deleted": 0,
            "skipped_locked": [],
            "skipped_keep": [],
            "errors": [],
            "deleted_paths": [],
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

        if lock_timeout is None:
            lock_timeout = getattr(self, "default_lock_timeout", 10.0)

        # ensure packages cache dir exists
        pkg_cache_root = self._packages_cache_dir
        if not pkg_cache_root.exists():
            return report  # nothing to do

        # optionally restrict to given packages
        pkg_dirs = []
        if packages:
            for p in packages:
                d = pkg_cache_root / p
                if d.exists() and d.is_dir():
                    pkg_dirs.append(d)
        else:
            pkg_dirs = [d for d in pkg_cache_root.iterdir() if d.is_dir()]

        # if keep_only_latest, try to read global_index (acquire index lock)
        index_data = None
        if keep_only_latest:
            idx_key = "index"
            got_idx_lock = self._acquire(idx_key, timeout=lock_timeout)
            try:
                try:
                    index_data = self.fetch_global_index(force=False)
                except Exception:
                    # fetch failed -> attempt to use cached index if present
                    try:
                        index_data = self._read_json(self._index_cache_path)
                    except Exception:
                        index_data = None
            finally:
                if got_idx_lock:
                    self._release(idx_key)
        # Build retention map if keep_only_latest
        keep_map = {}  # package_name -> set([version_to_keep])
        if keep_only_latest and index_data:
            for a in index_data.get("apps", []):
                pkg = a.get("package_name")
                v = a.get("latest_version_code") or a.get("latest_version")
                if pkg and v is not None:
                    keep_map.setdefault(pkg, set()).add(str(v))

        # iterate packages and versions
        for pkg_dir in pkg_dirs:
            pkg_name = pkg_dir.name
            if not pkg_dir.is_dir():
                continue
            for ver_dir in pkg_dir.iterdir():
                if not ver_dir.is_dir():
                    continue
                report["checked"] += 1
                ver = ver_dir.name
                local_meta = ver_dir / "meta.json"
                # decide whether to consider deletion
                should_delete = False
                reason = None

                if keep_only_latest:
                    # if this version is not listed in keep_map for this package -> candidate for deletion
                    keep_versions = keep_map.get(pkg_name, set())
                    if str(ver) in keep_versions:
                        report["skipped_keep"].append(str(ver_dir))
                        continue
                    else:
                        # candidate, but double-check remote meta existence: if remote still lists this exact version (rare), keep
                        remote_meta_path = f"packages/{pkg_name}/{ver}/meta.json"
                        try:
                            exists = False
                            try:
                                exists = self.provider.is_exists(remote_meta_path)
                            except Exception:
                                # provider.is_exists may raise; handle as False but record
                                exists = False
                            if exists:
                                # remote still has this version (unexpected if keep_only_latest), keep it
                                report["skipped_keep"].append(str(ver_dir))
                                continue
                            else:
                                should_delete = True
                                reason = "not_latest_remote"
                        except Exception as e:
                            report["errors"].append(
                                {"path": str(ver_dir), "error": f"keep_only_latest_check_error:{e}"})
                            continue
                else:
                    # keep_only_latest == False: delete if remote meta not exists
                    remote_meta_path = f"packages/{pkg_name}/{ver}/meta.json"
                    try:
                        exists = False
                        try:
                            exists = self.provider.is_exists(remote_meta_path)
                        except Exception:
                            # treat exceptions as not exists but record the error
                            exists = False
                            report["errors"].append({"path": str(ver_dir), "error": "provider.is_exists_failed"})
                        if not exists:
                            should_delete = True
                            reason = "remote_meta_missing"
                        else:
                            report["skipped_keep"].append(str(ver_dir))
                            continue
                    except Exception as e:
                        report["errors"].append({"path": str(ver_dir), "error": str(e)})
                        continue

                if should_delete:
                    report["candidates"] += 1
                    # attempt to acquire meta lock for this version before deleting
                    lock_key = f"meta:{pkg_name}:{ver}"
                    got = self._acquire(lock_key, timeout=lock_timeout)
                    if not got:
                        report["skipped_locked"].append(str(ver_dir))
                        continue
                    try:
                        # double-check remote meta existence just before deletion to avoid TOCTOU
                        try:
                            still_exists = False
                            try:
                                still_exists = self.provider.is_exists(remote_meta_path)
                            except Exception:
                                still_exists = False
                            if still_exists and not keep_only_latest:
                                # remote came alive again -> skip deletion
                                report["skipped_keep"].append(str(ver_dir))
                                continue
                            # perform deletion (or dry-run)
                            if dry_run:
                                report["deleted_paths"].append(str(ver_dir))
                            else:
                                try:
                                    shutil.rmtree(ver_dir)
                                    report["deleted"] += 1
                                    report["deleted_paths"].append(str(ver_dir))
                                except Exception as e:
                                    report["errors"].append({"path": str(ver_dir), "error": str(e)})
                        except Exception as e:
                            report["errors"].append({"path": str(ver_dir), "error": f"predelete_check_error:{e}"})
                    finally:
                        # release lock
                        try:
                            self._release(lock_key)
                        except Exception:
                            # don't fail on release
                            pass

        return report


def _mock_main():
    from tpytest.resource_provider import LocalProvider, FeishuProvider
    from powertrde.utils.feishu.feishu_api_helper import FeishuApiHelper

    provider = LocalProvider(r'D:\apks\repo')
    # feishu = FeishuApiHelper('xxx', 'xxx')
    # feishu.register_root_folder_token('', 'KDWffifO5lBwc8dgPvfcWQG5ntX')
    # provider = FeishuProvider(feishu, '')
    from powertrde.utils.lazy_shared_pool import LazySharedPool

    lock_manager = LazySharedPool(r'D:\apks\.app_repo_cache\res_lock.db')
    client = AppRepoClient(provider, cache_dir=r'D:\apks\.app_repo_cache', index_ttl_seconds=300,
                           resource_lock_manager=lock_manager)

    # fetch index
    # idx = client.fetch_global_index()
    # apps = [a['package_name'] for a in idx.get('apps', [])]
    # print("apps:", [a['package_name'] for a in idx.get('apps', [])])

    # r = client.install_cached_to_device(adb.first_device(), 'com.transsion.emmctest')
    # print(r)

    rr = client.install_batch_parallel('ASALE3741B000022', ['com.twitter.android'])
    print(rr)


def _mock_main2():
    from tpytest.resource_provider import LocalProvider

    provider = LocalProvider(r'D:\apks\repo')
    from powertrde.utils.lazy_shared_pool import LazySharedPool

    lock_manager = LazySharedPool(r'D:\apks\.app_repo_cache\res_lock.db')
    client = AppRepoClient(provider, cache_dir=r'D:\apks\.app_repo_cache', index_ttl_seconds=300,
                           resource_lock_manager=lock_manager)
    rr = client.install_batch_parallel('BCL8000000000311', ['com.twitter.android'])
    print(rr)


if __name__ == '__main__':
    _mock_main()
