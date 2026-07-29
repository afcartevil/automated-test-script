# lazy_shared_pool.py
"""
LazySharedPool
- 去中心化、懒触发 cleanup（on-demand heartbeat）
- group + members + reference counting
- resources: 独立实体，拥有 owner_group_id (nullable)、claimed_at、data(JSON)
- init-lock (atomic mkdir) properly serializes schema migration/creation: ONLY the lock-holder runs migration/create.
- Robust, retry-safe acquire_resource: handles IntegrityError / conditional UPDATE races.
- psutil optional for PID/create_time checks.
"""
import shutil
import socket
import sqlite3
import tempfile
import time
import json
import os
import uuid
import threading
from typing import Optional, Dict, Any

try:
    import psutil

    _HAS_PSUTIL = True
except Exception:
    psutil = None
    _HAS_PSUTIL = False

# Tunables
DEFAULT_STALE_TTL = 10.0
DEFAULT_DB_BUSY_TIMEOUT_MS = 30000
DEFAULT_LOCK_TIMEOUT = 5.0
DEFAULT_LOCK_BACKOFF = 0.05

# Init-lock settings
INIT_LOCK_SUFFIX = ".initlock"
INIT_LOCK_WAIT_TIMEOUT = 30.0
INIT_LOCK_STALE_SECONDS = 60.0
INIT_LOCK_POLL_INTERVAL = 0.05

# Lock directory suffix (used for any file-level operation that mutates DB file/WAL)
_FILE_OP_LOCK_SUFFIX = ".fileop.lock"
_FILE_OP_LOCK_POLL = 0.05
_FILE_OP_LOCK_STALE = 60.0  # seconds, consider stale if older than this and empty


def _now() -> float:
    """返回当前时间戳（float 秒）。"""
    return time.time()


def _require_psutil():
    if not _HAS_PSUTIL:
        raise RuntimeError("psutil required: pip install psutil")


def _psutil_pid_exists(pid: int) -> bool:
    if not _HAS_PSUTIL:
        return False
    try:
        return bool(psutil.pid_exists(pid))
    except Exception:
        return False


def _psutil_process_create_time(pid: int) -> Optional[float]:
    if not _HAS_PSUTIL:
        return None
    try:
        return psutil.Process(pid).create_time()
    except Exception:
        return None


class LazySharedPool:
    def __init__(
            self,
            db_path: str,
            group_id: Optional[str] = None,
            member_id: Optional[str] = None,
            stale_ttl: float = DEFAULT_STALE_TTL,
            use_psutil: bool = True,
            auto_touch_on_ops: bool = True,
            init_lock_wait: float = INIT_LOCK_WAIT_TIMEOUT,
    ):
        """
        初始化一个共享池实例（进程内对象）。

        - 每个实例代表一个 member（成员），隶属于一个 group（组）。
        - group + members 共同表达“谁在用 / 是否仍存活”。
        - resources 表用于管理资源条目（可做互斥占有，也可做共享资源的元数据承载）。
        """
        # ensure pid set before member_id uses it
        self.db_base_path = db_path
        self.db_path = db_path
        self.pid = os.getpid()

        self.group_id = group_id or self._gen_group_id()
        self.member_id = member_id or self._gen_member_id(self.group_id)

        self.use_psutil = bool(use_psutil)
        if self.use_psutil:
            _require_psutil()
        self.start_time = _psutil_process_create_time(self.pid) or _now()

        self.stale_ttl = float(stale_ttl)
        self.auto_touch_on_ops = auto_touch_on_ops
        self.init_lock_wait = float(init_lock_wait)

        self._local_lock = threading.RLock()

        self._conn = self._open_db(self.db_base_path)

        # init-lock protects schema migration and creation
        got_lock = self._acquire_init_lock(wait_seconds=init_lock_wait)
        try:
            if got_lock:
                self._ensure_schema_migration()
                self._init_schema()
            else:
                # wait for lock release then ensure schema exists (best-effort)
                self._wait_for_init_lock_release(wait_seconds=init_lock_wait)
                if not self._schema_ok():
                    got2 = self._acquire_init_lock(wait_seconds=3.0)
                    try:
                        if got2:
                            self._ensure_schema_migration()
                            self._init_schema()
                        else:
                            # fallback create (best-effort)
                            self._init_schema()
                    finally:
                        if got2:
                            self._release_init_lock()
        finally:
            if got_lock:
                self._release_init_lock()

        self._register_member_initial(wait_seconds=self.init_lock_wait)

    # ------------- file-op cross-process lock helpers (放入类中) -------------
    def _file_op_lock_path(self) -> str:
        """返回当前 DB 文件对应的“文件级操作锁”目录路径。"""
        base = getattr(self, "db_base_path", self.db_path)
        return f"{base}{_FILE_OP_LOCK_SUFFIX}"

    def _acquire_file_op_lock(self, wait_seconds: float = 30.0, stale_seconds: float = _FILE_OP_LOCK_STALE) -> bool:
        """
        获取跨进程的“文件级操作锁”（基于 mkdir 原子性）。

        - 成功返回 True，超时返回 False。
        - 若锁目录存在且超过 stale_seconds 且为空，尝试清理后重试。
        """
        lockdir = self._file_op_lock_path()
        deadline = time.time() + max(0.0, float(wait_seconds))
        hostname = socket.gethostname()
        owner_info = f"{os.getpid()}@{hostname}\n{time.time()}\n"

        while time.time() < deadline:
            try:
                os.mkdir(lockdir)
                # write owner info to a small file, useful for debugging
                try:
                    with open(os.path.join(lockdir, "owner"), "w", encoding="utf-8") as f:
                        f.write(owner_info)
                except Exception:
                    pass
                return True
            except FileExistsError:
                # check staleness: if too old and empty, attempt removal (best-effort)
                try:
                    st = os.stat(lockdir)
                    age = time.time() - st.st_mtime
                    if age > stale_seconds:
                        # attempt to remove only if empty (safe)
                        try:
                            if not os.listdir(lockdir):
                                os.rmdir(lockdir)
                                # loop and try to acquire
                                continue
                        except Exception:
                            # ignore and keep waiting
                            pass
                except FileNotFoundError:
                    # disappeared between checks; retry
                    continue
                except Exception:
                    pass
                time.sleep(_FILE_OP_LOCK_POLL)
            except PermissionError:
                time.sleep(_FILE_OP_LOCK_POLL)
            except Exception:
                time.sleep(_FILE_OP_LOCK_POLL)

        # timed out
        return False

    def _release_file_op_lock(self):
        """释放“文件级操作锁”（尽力而为）。"""
        lockdir = self._file_op_lock_path()
        try:
            ownerf = os.path.join(lockdir, "owner")
            if os.path.exists(ownerf):
                try:
                    os.remove(ownerf)
                except Exception:
                    pass
            os.rmdir(lockdir)
        except Exception:
            # ignore failure to remove (maybe removed or non-empty)
            pass

    # ---------------- init-lock ----------------
    def _lockdir_path(self) -> str:
        """返回初始化锁目录路径（用于串行化建表/迁移）。"""
        base = getattr(self, "db_base_path", self.db_path)
        return f"{base}{INIT_LOCK_SUFFIX}"

    def _wait_for_file_op_lock_release(self, wait_seconds: float) -> bool:
        lockdir = self._file_op_lock_path()
        deadline = time.time() + max(0.0, wait_seconds)
        while time.time() < deadline:
            if not os.path.exists(lockdir):
                return True
            time.sleep(0.02)
        return False

    def _db_pointer_path(self, base_path: str) -> str:
        return f"{base_path}.ptr"

    def _resolve_active_db_path(self, base_path: str) -> str:
        ptr = self._db_pointer_path(base_path)
        try:
            with open(ptr, "r", encoding="utf-8") as f:
                raw = (f.readline() or "").strip()
        except Exception:
            raw = ""
        if not raw:
            return os.path.abspath(base_path)
        if not os.path.isabs(raw):
            raw = os.path.join(os.path.dirname(base_path), raw)
        return os.path.abspath(raw)

    def _set_active_db_path(self, base_path: str, active_path: str) -> bool:
        ptr = self._db_pointer_path(base_path)
        d = os.path.dirname(ptr)
        if d and not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
        tmp = f"{ptr}.tmp.{uuid.uuid4().hex}"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(os.path.abspath(active_path))
                f.write("\n")
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
            os.replace(tmp, ptr)
            return True
        except Exception:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            return False

    def _make_rotated_db_path(self, base_path: str) -> str:
        d = os.path.dirname(base_path) or "."
        base_name = os.path.basename(base_path)
        ts = int(time.time() * 1000)
        suffix = uuid.uuid4().hex[:8]
        return os.path.abspath(os.path.join(d, f"{base_name}.rot.{ts}.{suffix}.db"))

    def _acquire_init_lock(self, wait_seconds: float = INIT_LOCK_WAIT_TIMEOUT) -> bool:
        """获取初始化锁（基于 mkdir 原子性），用于保护 schema 创建/迁移。"""
        lockdir = self._lockdir_path()
        deadline = time.time() + max(0.0, wait_seconds)
        while time.time() < deadline:
            try:
                os.mkdir(lockdir)
                try:
                    with open(os.path.join(lockdir, "owner"), "w") as f:
                        f.write(f"{os.getpid()}\n{time.time()}\n")
                except Exception:
                    pass
                return True
            except FileExistsError:
                # check staleness
                try:
                    st = os.stat(lockdir)
                    if time.time() - st.st_mtime > INIT_LOCK_STALE_SECONDS:
                        # try removing empty stale lockdir
                        try:
                            if not os.listdir(lockdir):
                                os.rmdir(lockdir)
                                continue
                        except Exception:
                            pass
                except FileNotFoundError:
                    continue
                except Exception:
                    pass
                time.sleep(INIT_LOCK_POLL_INTERVAL)
            except Exception:
                time.sleep(INIT_LOCK_POLL_INTERVAL)
        return False

    def _release_init_lock(self):
        """释放初始化锁（尽力而为）。"""
        lockdir = self._lockdir_path()
        try:
            ownerf = os.path.join(lockdir, "owner")
            if os.path.exists(ownerf):
                try:
                    os.remove(ownerf)
                except Exception:
                    pass
            os.rmdir(lockdir)
        except Exception:
            pass

    def _wait_for_init_lock_release(self, wait_seconds: float) -> bool:
        """等待初始化锁释放，超时返回 False。"""
        lockdir = self._lockdir_path()
        deadline = time.time() + max(0.0, wait_seconds)
        while time.time() < deadline:
            if not os.path.exists(lockdir):
                return True
            time.sleep(0.02)
        return False

    # ---------------- DB open / schema ----------------
    def _open_db(self, path: str) -> sqlite3.Connection:
        """
        打开 SQLite DB；若完整性检查失败则尝试修复。

        - 使用 file-op lock 保证同一时刻只有一个进程执行修复/替换。
        - 其他进程等待锁释放后重新打开 DB。
        """
        base_path = os.path.abspath(path)

        # ensure directory exists
        d = os.path.dirname(base_path)
        if d and not os.path.exists(d):
            os.makedirs(d, exist_ok=True)

        active_path = self._resolve_active_db_path(base_path)

        # first try to open normally (may create new empty DB if not exists)
        try:
            conn = sqlite3.connect(active_path, timeout=DEFAULT_DB_BUSY_TIMEOUT_MS / 1000.0, check_same_thread=False,
                                   isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.execute(f"PRAGMA busy_timeout={int(DEFAULT_DB_BUSY_TIMEOUT_MS)};")
        except Exception:
            # if open fails (permission/truncated), try repair flow below by acquiring file lock
            conn = None

        def integrity_ok(c):
            try:
                cur = c.cursor()
                cur.execute("PRAGMA integrity_check;")
                res = cur.fetchall()
                cur.close()
                return bool(res and all((row[0] == 'ok' for row in res)))
            except Exception:
                return False

        if conn is not None and integrity_ok(conn):
            self.db_path = active_path
            return conn

        # If here: either conn failed to open or integrity_check failed.
        # Acquire file-op lock and let one process try repair; others will wait for release then re-open.
        got = self._acquire_file_op_lock(wait_seconds=30.0, stale_seconds=_FILE_OP_LOCK_STALE)
        if got:
            try:
                active_path = self._resolve_active_db_path(base_path)
                # Double-check: maybe another process repaired already before we acquired lock
                # Close previously opened conn if any
                try:
                    if conn:
                        conn.close()
                except Exception:
                    pass

                # Re-attempt open (another process might have repaired while we waited)
                try:
                    conn2 = sqlite3.connect(active_path, timeout=DEFAULT_DB_BUSY_TIMEOUT_MS / 1000.0, check_same_thread=False,
                                            isolation_level=None)
                    conn2.execute("PRAGMA journal_mode=WAL;")
                    conn2.execute("PRAGMA synchronous=NORMAL;")
                    conn2.execute("PRAGMA foreign_keys=ON;")
                    conn2.execute(f"PRAGMA busy_timeout={int(DEFAULT_DB_BUSY_TIMEOUT_MS)};")
                    if integrity_ok(conn2):
                        self.db_path = active_path
                        return conn2
                    # else proceed to try repair (we hold lock)
                except Exception:
                    # continue to repair flow
                    pass

                # Attempt repair via dump (this function will perform replace under the same lock)
                repaired = self._attempt_repair_via_dump(base_path, active_path)
                if repaired:
                    return repaired

                # Repair via dump failed: backup corrupt file and create new DB atomically
                try:
                    self._backup_corrupt_db(active_path, reason="integrity_failed_no_dump")
                except Exception:
                    pass

                rotated_path = self._make_rotated_db_path(base_path)
                try:
                    self._set_active_db_path(base_path, rotated_path)
                except Exception:
                    pass
                self.db_path = rotated_path
                # create fresh DB at rotated path
                new_conn = sqlite3.connect(rotated_path, timeout=DEFAULT_DB_BUSY_TIMEOUT_MS / 1000.0, check_same_thread=False,
                                           isolation_level=None)
                new_conn.execute("PRAGMA journal_mode=WAL;")
                new_conn.execute("PRAGMA synchronous=NORMAL;")
                new_conn.execute("PRAGMA foreign_keys=ON;")
                new_conn.execute(f"PRAGMA busy_timeout={int(DEFAULT_DB_BUSY_TIMEOUT_MS)};")
                return new_conn
            finally:
                self._release_file_op_lock()
        else:
            # failed to acquire lock within wait: wait for lock to be released by holder then reopen
            # This avoids multiple processes trying to repair concurrently.
            self._wait_for_file_op_lock_release(wait_seconds=30.0)
            # attempt to open again
            try:
                active_path = self._resolve_active_db_path(base_path)
                conn3 = sqlite3.connect(active_path, timeout=DEFAULT_DB_BUSY_TIMEOUT_MS / 1000.0, check_same_thread=False,
                                        isolation_level=None)
                conn3.execute("PRAGMA journal_mode=WAL;")
                conn3.execute("PRAGMA synchronous=NORMAL;")
                conn3.execute("PRAGMA foreign_keys=ON;")
                conn3.execute(f"PRAGMA busy_timeout={int(DEFAULT_DB_BUSY_TIMEOUT_MS)};")
                # final integrity check
                try:
                    cur = conn3.cursor()
                    cur.execute("PRAGMA integrity_check;")
                    res = cur.fetchall()
                    cur.close()
                    if res and all((row[0] == 'ok' for row in res)):
                        self.db_path = active_path
                        return conn3
                except Exception:
                    pass
                # if still bad, as last resort try to open read-only (or create new)
            except Exception:
                pass

            # fallback: backup & create new
            rotated_path = self._make_rotated_db_path(base_path)
            try:
                got2 = self._acquire_file_op_lock(wait_seconds=3.0, stale_seconds=_FILE_OP_LOCK_STALE)
                if got2:
                    try:
                        try:
                            self._backup_corrupt_db(active_path, reason="fallback_after_lock_wait")
                        except Exception:
                            pass
                        self._set_active_db_path(base_path, rotated_path)
                    finally:
                        self._release_file_op_lock()
            except Exception:
                pass
            self.db_path = rotated_path
            conn_f = sqlite3.connect(rotated_path, timeout=DEFAULT_DB_BUSY_TIMEOUT_MS / 1000.0, check_same_thread=False,
                                     isolation_level=None)
            conn_f.execute("PRAGMA journal_mode=WAL;")
            conn_f.execute("PRAGMA synchronous=NORMAL;")
            conn_f.execute("PRAGMA foreign_keys=ON;")
            conn_f.execute(f"PRAGMA busy_timeout={int(DEFAULT_DB_BUSY_TIMEOUT_MS)};")
            return conn_f

    def _attempt_repair_via_dump(self, base_path: str, broken_path: str) -> Optional[sqlite3.Connection]:
        """
        尝试通过 iterdump 导出并重建数据库，然后原子替换原文件。

        该方法应在持有 file-op lock 的情况下调用，避免并发修复/替换导致竞态。
        """
        # ensure temp file in same dir to allow atomic replace
        tmp_dir = os.path.dirname(broken_path) or "."
        tmp_fd = None
        tmp_path = None
        src = None
        try:
            # open a read connection to extract dump
            src = sqlite3.connect(broken_path, timeout=5.0, check_same_thread=False)
            dump_lines = []
            # iterdump may raise if DB is very corrupted; wrap in try
            for line in src.iterdump():
                dump_lines.append(line)
            src.close()
            dump_sql = "\n".join(dump_lines)
            if not dump_sql.strip():
                return None

            # create temporary file in same dir
            tmp_fd, tmp_path = tempfile.mkstemp(prefix="sqlite_repair_", suffix=".db", dir=tmp_dir)
            os.close(tmp_fd)
            # ensure it's removed if exists
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

            # create new DB and populate
            new_conn = sqlite3.connect(tmp_path, timeout=DEFAULT_DB_BUSY_TIMEOUT_MS / 1000.0, check_same_thread=False,
                                       isolation_level=None)
            new_conn.executescript(dump_sql)
            # set pragmas on new db
            new_conn.execute("PRAGMA journal_mode=WAL;")
            new_conn.execute("PRAGMA synchronous=NORMAL;")
            new_conn.execute("PRAGMA foreign_keys=ON;")
            new_conn.execute(f"PRAGMA busy_timeout={int(DEFAULT_DB_BUSY_TIMEOUT_MS)};")
            new_conn.commit()
            new_conn.close()

            # backup original (still under lock)
            try:
                self._backup_corrupt_db(broken_path, reason="repair_via_dump_backup")
            except Exception:
                # ignore backup error, but proceed
                pass

            # atomic replace (os.replace is atomic on same filesystem on both Windows and POSIX)
            try:
                os.replace(tmp_path, broken_path)
                active_path = broken_path
            except Exception:
                active_path = tmp_path
                try:
                    self._set_active_db_path(base_path, active_path)
                except Exception:
                    pass

            # remove WAL/SHM remnants safely (still under lock)
            for ext in ("-wal", "-shm"):
                pext = broken_path + ext
                try:
                    if os.path.exists(pext):
                        os.remove(pext)
                except Exception:
                    pass

            # open and return repaired connection
            self.db_path = os.path.abspath(active_path)
            repaired = sqlite3.connect(active_path, timeout=DEFAULT_DB_BUSY_TIMEOUT_MS / 1000.0, check_same_thread=False,
                                       isolation_level=None)
            repaired.execute("PRAGMA journal_mode=WAL;")
            repaired.execute("PRAGMA synchronous=NORMAL;")
            repaired.execute("PRAGMA foreign_keys=ON;")
            repaired.execute(f"PRAGMA busy_timeout={int(DEFAULT_DB_BUSY_TIMEOUT_MS)};")
            return repaired
        except Exception:
            # cleanup temp file
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            try:
                src.close()
            except Exception:
                pass
            return None

    def _backup_corrupt_db(self, path: str, reason: str = ""):
        """
        备份疑似损坏的 DB 文件（建议在持有 file-op lock 时调用以避免竞态）。
        """
        try:
            if not os.path.exists(path):
                return
            ts = int(time.time())
            bak = f"{path}.corrupt.{ts}.bak"
            try:
                os.replace(path, bak)
            except Exception:
                try:
                    shutil.copy2(path, bak)
                    os.remove(path)
                except Exception:
                    pass
            # also backup wal & shm if exist
            for ext in ("-wal", "-shm"):
                pext = path + ext
                if os.path.exists(pext):
                    try:
                        shutil.copy2(pext, bak + ext)
                        os.remove(pext)
                    except Exception:
                        pass
            # write reason file
            try:
                with open(bak + ".reason", "w", encoding="utf-8") as rf:
                    rf.write(f"backup_reason={reason}\nbackup_time={time.ctime()}\n")
            except Exception:
                pass
        except Exception:
            pass


    def _schema_ok(self) -> bool:
        """检查关键表是否存在（用于判断 schema 是否已初始化）。"""
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='resources'")
            ok = cur.fetchone() is not None
            cur.close()
            return ok
        except Exception:
            return False

    def _ensure_schema_migration(self):
        """执行轻量 schema 迁移（必须由 init-lock 持有者调用）。"""
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='resources'")
            if cur.fetchone():
                cur.execute("PRAGMA table_info(resources)")
                cols = [r[1] for r in cur.fetchall()]
                if 'data' not in cols:
                    try:
                        cur.execute("ALTER TABLE resources ADD COLUMN data TEXT")
                    except sqlite3.OperationalError:
                        pass
            cur.close()
        except Exception:
            pass

    def _init_schema(self):
        """初始化数据库 schema（建表，幂等）。"""
        with self._local_lock:
            cur = self._conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                group_id TEXT PRIMARY KEY,
                metadata TEXT
            );""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS members (
                member_id TEXT PRIMARY KEY,
                group_id TEXT NOT NULL,
                pid INTEGER NOT NULL,
                start_time REAL NOT NULL,
                last_heartbeat REAL NOT NULL,
                metadata TEXT,
                FOREIGN KEY(group_id) REFERENCES groups(group_id) ON DELETE CASCADE
            );""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS group_kv (
                group_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                PRIMARY KEY (group_id, key),
                FOREIGN KEY(group_id) REFERENCES groups(group_id) ON DELETE CASCADE
            );""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS member_kv (
                member_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                PRIMARY KEY (member_id, key),
                FOREIGN KEY(member_id) REFERENCES members(member_id) ON DELETE CASCADE
            );""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS resources (
                key TEXT PRIMARY KEY,
                owner_group_id TEXT,
                claimed_at REAL,
                data TEXT,
                FOREIGN KEY(owner_group_id) REFERENCES groups(group_id) ON DELETE SET NULL
            );""")
            cur.close()

    # ---------------- ids & registration ----------------
    def _gen_group_id(self) -> str:
        """生成 group_id（默认包含时间戳与随机串）。"""
        return f"group-{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"

    def _gen_member_id(self, group_id: str) -> str:
        """生成 member_id（默认包含 group_id、pid 与随机串）。"""
        return f"{group_id}-{self.pid}-{uuid.uuid4().hex[:6]}"

    def _is_db_locked_error(self, e: Exception) -> bool:
        msg = str(e).lower()
        return ("database is locked" in msg) or ("database is busy" in msg) or ("database locked" in msg)

    def _reopen_on_rotated_db(self) -> bool:
        base_path = os.path.abspath(self.db_base_path)
        rotated_path = self._make_rotated_db_path(base_path)
        got = self._acquire_file_op_lock(wait_seconds=3.0, stale_seconds=_FILE_OP_LOCK_STALE)
        if not got:
            return False
        try:
            try:
                self._set_active_db_path(base_path, rotated_path)
            except Exception:
                pass

            try:
                if getattr(self, "_conn", None) is not None:
                    try:
                        self._conn.close()
                    except Exception:
                        pass
            except Exception:
                pass

            new_conn = sqlite3.connect(
                rotated_path,
                timeout=DEFAULT_DB_BUSY_TIMEOUT_MS / 1000.0,
                check_same_thread=False,
                isolation_level=None,
            )
            new_conn.execute("PRAGMA journal_mode=WAL;")
            new_conn.execute("PRAGMA synchronous=NORMAL;")
            new_conn.execute("PRAGMA foreign_keys=ON;")
            new_conn.execute(f"PRAGMA busy_timeout={int(DEFAULT_DB_BUSY_TIMEOUT_MS)};")
            self._conn = new_conn
            self.db_path = rotated_path

            got_init = self._acquire_init_lock(wait_seconds=3.0)
            try:
                if got_init:
                    self._ensure_schema_migration()
                    self._init_schema()
                else:
                    self._wait_for_init_lock_release(wait_seconds=3.0)
                    try:
                        self._init_schema()
                    except Exception:
                        pass
            finally:
                if got_init:
                    self._release_init_lock()
            return True
        finally:
            self._release_file_op_lock()

    def _register_member_initial(self, wait_seconds: float) -> bool:
        first_wait = min(5.0, max(0.0, float(wait_seconds)))
        deadline = time.time() + first_wait
        backoff = DEFAULT_LOCK_BACKOFF
        tried_rotate = False

        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                if not tried_rotate:
                    tried_rotate = True
                    if self._reopen_on_rotated_db():
                        deadline = time.time() + max(3.0, first_wait)
                        backoff = DEFAULT_LOCK_BACKOFF
                        continue
                return False

            with self._local_lock:
                begun = self._try_begin_immediate(timeout=min(1.0, max(0.05, remaining)))
                if not begun:
                    pass
                else:
                    now = _now()
                    cur = self._conn.cursor()
                    try:
                        cur.execute(
                            "INSERT OR IGNORE INTO groups (group_id, metadata) VALUES (?, ?)",
                            (self.group_id, json.dumps({}, ensure_ascii=False)),
                        )
                        cur.execute(
                            "INSERT OR REPLACE INTO members (member_id, group_id, pid, start_time, last_heartbeat, metadata) VALUES (?, ?, ?, ?, ?, ?)",
                            (self.member_id, self.group_id, self.pid, self.start_time, now, json.dumps({}, ensure_ascii=False)),
                        )
                        cur.close()
                        self._conn.commit()
                        return True
                    except sqlite3.OperationalError as e:
                        try:
                            cur.close()
                        except Exception:
                            pass
                        try:
                            self._conn.rollback()
                        except Exception:
                            pass
                        if self._is_db_locked_error(e):
                            if os.path.exists(self._lockdir_path()):
                                self._wait_for_init_lock_release(wait_seconds=min(2.0, remaining))
                        else:
                            raise
                    except Exception:
                        try:
                            cur.close()
                        except Exception:
                            pass
                        try:
                            self._conn.rollback()
                        except Exception:
                            pass
                        raise

            time.sleep(backoff)
            backoff = min(backoff * 2, 0.5)

    # ---------------- utility ----------------
    def _try_begin_immediate(self, timeout: float = DEFAULT_LOCK_TIMEOUT) -> bool:
        """尝试以 BEGIN IMMEDIATE 方式开启写事务；超时返回 False。"""
        deadline = time.time() + timeout
        backoff = DEFAULT_LOCK_BACKOFF
        while time.time() < deadline:
            try:
                self._conn.execute("BEGIN IMMEDIATE;")
                return True
            except sqlite3.OperationalError:
                time.sleep(backoff)
                backoff = min(backoff * 2, 0.5)
        return False

    def _run_immediate_write(self, op, wait_seconds: float, rotate_on_timeout: bool = True) -> bool:
        deadline = time.time() + max(0.0, float(wait_seconds))
        backoff = DEFAULT_LOCK_BACKOFF
        tried_rotate = False

        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                if rotate_on_timeout and (not tried_rotate):
                    tried_rotate = True
                    if self._reopen_on_rotated_db():
                        deadline = time.time() + max(3.0, float(wait_seconds))
                        backoff = DEFAULT_LOCK_BACKOFF
                        continue
                return False

            with self._local_lock:
                begun = self._try_begin_immediate(timeout=min(1.0, max(0.05, remaining)))
                if not begun:
                    pass
                else:
                    cur = self._conn.cursor()
                    try:
                        op(cur)
                        cur.close()
                        self._conn.commit()
                        return True
                    except sqlite3.OperationalError as e:
                        try:
                            cur.close()
                        except Exception:
                            pass
                        try:
                            self._conn.rollback()
                        except Exception:
                            pass
                        if self._is_db_locked_error(e):
                            if os.path.exists(self._lockdir_path()):
                                self._wait_for_init_lock_release(wait_seconds=min(2.0, remaining))
                        else:
                            raise
                    except Exception:
                        try:
                            cur.close()
                        except Exception:
                            pass
                        try:
                            self._conn.rollback()
                        except Exception:
                            pass
                        raise

            time.sleep(backoff)
            backoff = min(backoff * 2, 0.5)

    def _get_create_time(self, pid: int) -> Optional[float]:
        """获取进程创建时间（依赖 psutil；不可用则返回 None）。"""
        return _psutil_process_create_time(pid)

    def _is_member_alive(self, pid: int, start_time: float, last_heartbeat: float, now: float) -> bool:
        """
        成员存活判定（全局统一规则）：

        - 若启用 psutil：优先用 (pid 是否存在 + create_time≈start_time) 做强判定（实时性更好）。
        - 若无法用 psutil 得出结论，则退化为基于 last_heartbeat + stale_ttl 的弱判定。
        """
        if self.use_psutil:
            try:
                if not _psutil_pid_exists(pid):
                    return False
                p_ct = self._get_create_time(pid)
                if p_ct is None:
                    return True
                if abs(p_ct - start_time) > 2.0:
                    return False
                return True
            except Exception:
                pass
        return (now - last_heartbeat) <= self.stale_ttl

    def _count_live_members(self, group_id: str) -> int:
        """
        统计指定 group 当前被判定为存活的成员数（使用 _is_member_alive 规则）。
        """
        cur = self._conn.cursor()
        cur.execute("SELECT pid, start_time, last_heartbeat FROM members WHERE group_id = ?", (group_id,))
        rows = cur.fetchall()
        cur.close()
        now = _now()
        cnt = 0
        for pid, st, lh in rows:
            if self._is_member_alive(pid, st, lh, now):
                cnt += 1
        return cnt

    # ---------------- lazy touch & cleanup (fixed) ----------------
    def _lazy_touch_and_cleanup(self, lock_timeout: float = DEFAULT_LOCK_TIMEOUT):
        """懒触发心跳与清理：更新自身心跳，并尽力清理死亡成员/空组。"""
        with self._local_lock:
            begun = self._try_begin_immediate(timeout=lock_timeout)
            if not begun:
                # best-effort: update our heartbeat only
                try:
                    now = _now()
                    cur = self._conn.cursor()
                    cur.execute("UPDATE members SET last_heartbeat = ? WHERE member_id = ?", (now, self.member_id))
                    cur.close()
                    self._conn.commit()
                except Exception:
                    pass
                return

            try:
                now = _now()
                cur = self._conn.cursor()
                # ensure group exists & update our heartbeat
                cur.execute("INSERT OR IGNORE INTO groups (group_id, metadata) VALUES (?, ?)",
                            (self.group_id, json.dumps({}, ensure_ascii=False)))
                cur.execute(
                    "INSERT OR REPLACE INTO members (member_id, group_id, pid, start_time, last_heartbeat, metadata) VALUES (?, ?, ?, ?, ?, COALESCE((SELECT metadata FROM members WHERE member_id = ?), ?))",
                    (self.member_id, self.group_id, self.pid, self.start_time, now, self.member_id, json.dumps({}))
                )

                # scan members, remove those not alive per _is_member_alive
                cur.execute("SELECT member_id, pid, start_time, last_heartbeat FROM members")
                rows = cur.fetchall()
                to_remove = []
                for member_id, pid, start_time, last_heartbeat in rows:
                    if not self._is_member_alive(pid, start_time, last_heartbeat, now):
                        to_remove.append(member_id)

                if to_remove:
                    for mid in to_remove:
                        cur.execute("DELETE FROM members WHERE member_id = ?", (mid,))

                # remove empty groups (but first clear resources.owner_group_id for them)
                cur.execute("""
                    SELECT g.group_id FROM groups g
                    LEFT JOIN members m ON g.group_id = m.group_id
                    WHERE m.member_id IS NULL
                """)
                empty_groups = [r[0] for r in cur.fetchall()]
                if empty_groups:
                    for gid in empty_groups:
                        cur.execute(
                            "UPDATE resources SET owner_group_id = NULL, claimed_at = NULL WHERE owner_group_id = ?",
                            (gid,))
                        cur.execute("DELETE FROM groups WHERE group_id = ?", (gid,))

                cur.close()
                self._conn.commit()
            except Exception:
                try:
                    self._conn.rollback()
                except Exception:
                    pass

    # ---------------- group/member KV (unchanged) ----------------
    def set_group_kv(self, key: str, value: Any):
        """设置当前 group 的 KV（value 自动 JSON 序列化）。"""
        if self.auto_touch_on_ops:
            self._lazy_touch_and_cleanup()
        val = json.dumps(value, ensure_ascii=False)
        ok = self._run_immediate_write(
            lambda cur: (
                cur.execute(
                    "INSERT OR IGNORE INTO groups (group_id, metadata) VALUES (?, ?)",
                    (self.group_id, json.dumps({}, ensure_ascii=False)),
                ),
                cur.execute(
                    "INSERT OR REPLACE INTO group_kv (group_id, key, value) VALUES (?, ?, ?)",
                    (self.group_id, key, val),
                ),
            ),
            wait_seconds=min(5.0, float(getattr(self, "init_lock_wait", 5.0))),
            rotate_on_timeout=True,
        )
        if not ok:
            raise sqlite3.OperationalError("database is locked")

    def get_group_kv(self, key: str) -> Optional[Any]:
        """读取当前 group 的 KV（优先按 JSON 反序列化）。"""
        if self.auto_touch_on_ops:
            self._lazy_touch_and_cleanup()
        cur = self._conn.cursor()
        cur.execute("SELECT value FROM group_kv WHERE group_id = ? AND key = ?", (self.group_id, key))
        r = cur.fetchone()
        cur.close()
        if not r:
            return None
        try:
            return json.loads(r[0])
        except Exception:
            return r[0]

    def set_member_kv(self, key: str, value: Any):
        """设置当前 member 的 KV（value 自动 JSON 序列化）。"""
        if self.auto_touch_on_ops:
            self._lazy_touch_and_cleanup()
        val = json.dumps(value, ensure_ascii=False)
        ok = self._run_immediate_write(
            lambda cur: (
                cur.execute(
                    "INSERT OR IGNORE INTO groups (group_id, metadata) VALUES (?, ?)",
                    (self.group_id, json.dumps({}, ensure_ascii=False)),
                ),
                cur.execute(
                    "INSERT OR REPLACE INTO members (member_id, group_id, pid, start_time, last_heartbeat, metadata) VALUES (?, ?, ?, ?, ?, COALESCE((SELECT metadata FROM members WHERE member_id = ?), ?))",
                    (self.member_id, self.group_id, self.pid, self.start_time, _now(), self.member_id, json.dumps({})),
                ),
                cur.execute(
                    "INSERT OR REPLACE INTO member_kv (member_id, key, value) VALUES (?, ?, ?)",
                    (self.member_id, key, val),
                ),
            ),
            wait_seconds=min(5.0, float(getattr(self, "init_lock_wait", 5.0))),
            rotate_on_timeout=True,
        )
        if not ok:
            raise sqlite3.OperationalError("database is locked")

    def get_member_kv(self, key: str) -> Optional[Any]:
        """读取当前 member 的 KV（优先按 JSON 反序列化）。"""
        if self.auto_touch_on_ops:
            self._lazy_touch_and_cleanup()
        cur = self._conn.cursor()
        cur.execute("SELECT value FROM member_kv WHERE member_id = ? AND key = ?", (self.member_id, key))
        r = cur.fetchone()
        cur.close()
        if not r:
            return None
        try:
            return json.loads(r[0])
        except Exception:
            return r[0]

    # ---------------- snapshot ----------------
    def list_groups_snapshot(self):
        """返回当前 DB 的快照（groups/members/group_kv/resources），并尽力触发一次清理。"""
        with self._local_lock:
            begun = self._try_begin_immediate()
            if not begun:
                self._lazy_touch_and_cleanup()
                return self._read_snapshot()
            try:
                self._lazy_touch_and_cleanup()
                cur = self._conn.cursor()
                cur.execute("SELECT group_id, metadata FROM groups")
                groups = cur.fetchall()
                result = {}
                for gid, meta in groups:
                    try:
                        meta_obj = json.loads(meta) if meta else {}
                    except Exception:
                        meta_obj = meta
                    result[gid] = {"metadata": meta_obj, "members": {}, "group_kv": {}, "resources": {}}
                cur.execute("SELECT member_id, group_id, pid, start_time, last_heartbeat, metadata FROM members")
                for mid, gid, pid, st, lb, meta in cur.fetchall():
                    try:
                        meta_obj = json.loads(meta) if meta else {}
                    except Exception:
                        meta_obj = meta
                    result.setdefault(gid, {"metadata": {}, "members": {}, "group_kv": {}, "resources": {}})["members"][
                        mid] = {"pid": pid, "start_time": st, "last_heartbeat": lb, "metadata": meta_obj}
                cur.execute("SELECT group_id, key, value FROM group_kv")
                for gid, k, v in cur.fetchall():
                    try:
                        vv = json.loads(v)
                    except Exception:
                        vv = v
                    result.setdefault(gid, {"metadata": {}, "members": {}, "group_kv": {}, "resources": {}})[
                        "group_kv"][k] = vv
                cur.execute("SELECT key, owner_group_id, claimed_at, data FROM resources")
                for key, owner, claimed_at, data in cur.fetchall():
                    try:
                        d = json.loads(data) if data else None
                    except Exception:
                        d = data
                    if owner and owner in result:
                        result[owner]["resources"][key] = {"owner_group_id": owner, "claimed_at": claimed_at, "data": d}
                    else:
                        result.setdefault("__unowned_resources__", {})[key] = {"owner_group_id": owner,
                                                                               "claimed_at": claimed_at, "data": d}
                cur.close()
                self._conn.commit()
                return result
            except Exception:
                try:
                    self._conn.rollback()
                except Exception:
                    pass
                return self._read_snapshot()

    def _read_snapshot(self):
        """在不加写锁的情况下读取快照（用于 list_groups_snapshot 的降级路径）。"""
        cur = self._conn.cursor()
        result = {}
        cur.execute("SELECT group_id, metadata FROM groups")
        for gid, meta in cur.fetchall():
            try:
                meta_obj = json.loads(meta) if meta else {}
            except Exception:
                meta_obj = meta
            result[gid] = {"metadata": meta_obj, "members": {}, "group_kv": {}, "resources": {}}
        cur.execute("SELECT member_id, group_id, pid, start_time, last_heartbeat, metadata FROM members")
        for mid, gid, pid, st, lb, meta in cur.fetchall():
            try:
                meta_obj = json.loads(meta) if meta else {}
            except Exception:
                meta_obj = meta
            result.setdefault(gid, {"metadata": {}, "members": {}, "group_kv": {}, "resources": {}})["members"][mid] = {
                "pid": pid, "start_time": st, "last_heartbeat": lb, "metadata": meta_obj}
        cur.execute("SELECT group_id, key, value FROM group_kv")
        for gid, k, v in cur.fetchall():
            try:
                vv = json.loads(v)
            except Exception:
                vv = v
            result.setdefault(gid, {"metadata": {}, "members": {}, "group_kv": {}, "resources": {}})["group_kv"][k] = vv
        cur.execute("SELECT key, owner_group_id, claimed_at, data FROM resources")
        for key, owner, claimed_at, data in cur.fetchall():
            try:
                d = json.loads(data) if data else None
            except Exception:
                d = data
            if owner and owner in result:
                result[owner]["resources"][key] = {"owner_group_id": owner, "claimed_at": claimed_at, "data": d}
            else:
                result.setdefault("__unowned_resources__", {})[key] = {"owner_group_id": owner,
                                                                       "claimed_at": claimed_at, "data": d}
        cur.close()
        return result

    # ---------------- resource APIs ----------------
    def create_resource(self, key: str, data: Optional[dict] = None, overwrite: bool = False) -> bool:
        """创建或覆盖资源条目；不改变 owner（默认 NULL）。"""
        if self.auto_touch_on_ops:
            self._lazy_touch_and_cleanup()
        djson = json.dumps(data, ensure_ascii=False) if data is not None else None
        with self._local_lock:
            cur = self._conn.cursor()
            if not overwrite:
                cur.execute("SELECT 1 FROM resources WHERE key = ?", (key,))
                if cur.fetchone():
                    cur.close()
                    return False
            cur.execute(
                "INSERT OR REPLACE INTO resources (key, owner_group_id, claimed_at, data) VALUES (?, NULL, NULL, ?)",
                (key, djson))
            cur.close()
            self._conn.commit()
            return True

    def get_resource(self, key: str) -> Optional[Dict[str, Any]]:
        """读取资源条目（包含 owner_group_id、claimed_at、data）。"""
        if self.auto_touch_on_ops:
            self._lazy_touch_and_cleanup()
        cur = self._conn.cursor()
        cur.execute("SELECT key, owner_group_id, claimed_at, data FROM resources WHERE key = ?", (key,))
        r = cur.fetchone()
        cur.close()
        if not r:
            return None
        k, owner, claimed_at, data = r
        try:
            d = json.loads(data) if data else None
        except Exception:
            d = data
        return {"key": k, "owner_group_id": owner, "claimed_at": claimed_at, "data": d}

    def update_resource_data(self, key: str, data: dict) -> bool:
        """仅在当前 group 持有该资源时，更新 resources.data。"""
        if self.auto_touch_on_ops:
            self._lazy_touch_and_cleanup()
        djson = json.dumps(data, ensure_ascii=False)
        with self._local_lock:
            begun = self._try_begin_immediate()
            if not begun:
                cur = self._conn.cursor()
                cur.execute("SELECT owner_group_id FROM resources WHERE key = ?", (key,))
                r = cur.fetchone()
                cur.close()
                if not r or r[0] != self.group_id:
                    return False
                cur = self._conn.cursor()
                cur.execute("UPDATE resources SET data = ? WHERE key = ?", (djson, key))
                cur.close()
                self._conn.commit()
                return True
            try:
                cur = self._conn.cursor()
                cur.execute("SELECT owner_group_id FROM resources WHERE key = ?", (key,))
                r = cur.fetchone()
                if not r or r[0] != self.group_id:
                    cur.close()
                    self._conn.commit()
                    return False
                cur.execute("UPDATE resources SET data = ? WHERE key = ?", (djson, key))
                cur.close()
                self._conn.commit()
                return True
            except Exception:
                try:
                    self._conn.rollback()
                except Exception:
                    pass
                return False

    def release_resource(self, key: str) -> bool:
        """
        安全且幂等的释放资源（组级释放）。
        - 返回 True 表示本次调用确实把资源从当前组释放（即之前 owner==self.group_id）。
        - 返回 False 表示资源不存在或当前组并非 owner（没有任何修改）。
        语义说明：
          * 不会释放其他组占有的资源（条件 WHERE owner_group_id = ?）。
          * 多次调用对同一资源幂等（第二次以后返回 False）。
        """
        # Optional lazy cleanup to keep DB reasonably fresh (best-effort).
        if self.auto_touch_on_ops:
            try:
                self._lazy_touch_and_cleanup()
            except Exception:
                pass

        with self._local_lock:
            # Prefer to get a write transaction to ensure conditional update is atomic.
            began = self._try_begin_immediate(timeout=DEFAULT_LOCK_TIMEOUT)
            try:
                cur = self._conn.cursor()
                # Conditional update: only clear owner if owner is this group.
                cur.execute(
                    "UPDATE resources SET owner_group_id = NULL, claimed_at = NULL WHERE key = ? AND owner_group_id = ?",
                    (key, self.group_id)
                )
                # rowcount indicates whether we actually changed a row.
                changed = getattr(cur, "rowcount", None)
                cur.close()
                # commit if we had a transaction
                try:
                    self._conn.commit()
                except Exception:
                    # If commit fails, try rollback to keep DB consistent
                    try:
                        self._conn.rollback()
                    except Exception:
                        pass

                if changed is not None:
                    return changed > 0

                # If driver doesn't provide rowcount, do a quick confirm query
                cur2 = self._conn.cursor()
                cur2.execute("SELECT owner_group_id FROM resources WHERE key = ?", (key,))
                r = cur2.fetchone()
                cur2.close()
                # If row absent => treated as not owned by us now (or deleted)
                if not r:
                    return False
                return r[0] is None  # True if now unowned (we succeeded), False if still owned by someone else
            finally:
                # If we couldn't begin immediate (began False), we've still attempted a conditional update.
                # Nothing else to do; DB commit/rollback already attempted above.
                pass

    def acquire_resource(self, key: str, timeout: float = 5.0, retry_delay: float = 0.1) -> bool:
        """
        可靠的阻塞式互斥占有（资源级）：

        - 使用 BEGIN IMMEDIATE 获取写事务。
        - 资源不存在则 INSERT（处理 IntegrityError 竞态）。
        - owner 为空则条件 UPDATE（WHERE owner_group_id IS NULL）抢占。
        - owner 为自己则直接成功。
        - owner 为其他组则用 _count_live_members 判定旧 owner 是否已无存活成员，必要时清理后重试。
        """
        deadline = time.time() + max(0.0, float(timeout))
        immediate_only = (timeout == 0)
        while True:
            try:
                self._lazy_touch_and_cleanup()
            except Exception:
                pass

            with self._local_lock:
                begun = self._try_begin_immediate(timeout=min(1.0, max(0.1, retry_delay * 2)))
                if not begun:
                    if immediate_only:
                        return False
                    if time.time() >= deadline:
                        return False
                    time.sleep(retry_delay)
                    continue

                try:
                    cur = self._conn.cursor()
                    cur.execute("SELECT owner_group_id FROM resources WHERE key = ?", (key,))
                    rr = cur.fetchone()
                    if not rr:
                        # try insert
                        try:
                            cur.execute(
                                "INSERT INTO resources (key, owner_group_id, claimed_at, data) VALUES (?, ?, ?, NULL)",
                                (key, self.group_id, _now()))
                            self._conn.commit()
                            cur.close()
                            return True
                        except sqlite3.IntegrityError:
                            try:
                                self._conn.rollback()
                            except Exception:
                                pass
                            cur.close()
                            if immediate_only:
                                return False
                            if time.time() >= deadline:
                                return False
                            time.sleep(retry_delay)
                            continue
                    owner = rr[0]
                    if owner is None:
                        cur.execute(
                            "UPDATE resources SET owner_group_id = ?, claimed_at = ? WHERE key = ? AND owner_group_id IS NULL",
                            (self.group_id, _now(), key))
                        changed = getattr(cur, "rowcount", None)
                        if changed is None or changed <= 0:
                            cur.execute("SELECT owner_group_id FROM resources WHERE key = ?", (key,))
                            rr2 = cur.fetchone()
                            cur.close()
                            if rr2 and rr2[0] == self.group_id:
                                try:
                                    self._conn.commit()
                                except Exception:
                                    pass
                                return True
                            try:
                                self._conn.commit()
                            except Exception:
                                pass
                            if immediate_only:
                                return False
                            if time.time() >= deadline:
                                return False
                            time.sleep(retry_delay)
                            continue
                        else:
                            try:
                                self._conn.commit()
                            except Exception:
                                pass
                            cur.close()
                            return True
                    if owner == self.group_id:
                        cur.close()
                        self._conn.commit()
                        return True

                    # owner != us -> count live members of owner group
                    owner_member_count = self._count_live_members(owner)
                    if owner_member_count == 0:
                        # clear stale owner using conditional update
                        cur.execute(
                            "UPDATE resources SET owner_group_id = NULL, claimed_at = NULL WHERE key = ? AND owner_group_id = ?",
                            (key, owner))
                        changed = getattr(cur, "rowcount", None)
                        if changed is None or changed > 0:
                            try:
                                self._conn.commit()
                            except Exception:
                                pass
                            cur.close()
                            # loop and try claim again
                            if immediate_only:
                                return False
                            if time.time() >= deadline:
                                return False
                            time.sleep(min(retry_delay, 0.05))
                            continue
                        else:
                            # someone racing, retry
                            try:
                                self._conn.commit()
                            except Exception:
                                pass
                            cur.close()
                            if immediate_only:
                                return False
                            if time.time() >= deadline:
                                return False
                            time.sleep(retry_delay)
                            continue
                    else:
                        cur.close()
                        self._conn.commit()
                        if immediate_only:
                            return False
                        if time.time() >= deadline:
                            return False
                        time.sleep(retry_delay)
                        continue
                except Exception:
                    try:
                        self._conn.rollback()
                    except Exception:
                        pass
                    if immediate_only:
                        return False
                    if time.time() >= deadline:
                        return False
                    time.sleep(retry_delay)
                    continue

    def force_acquire_resource(self, key: str, timeout: float = 5.0) -> Dict[str, Any]:
        """
        强制夺取资源: 无论资源当前由谁占有，直接设置为本组拥有。
        如果当前本组已持有，则直接返回，无需重复写入。

        返回:
          {
            "acquired": True/False,     # True表示调用后该资源归本组所有
            "prev_owner": <str or None>,# 之前的owner group_id
            "prev_owner_live_members": int, # takeover时旧owner活跃成员数
            "timestamp": float or None, # takeover发生的时间戳
            "error": <str或None>        # 错误信息
          }
        """
        now_ts = _now()
        got = self._try_begin_immediate(timeout=timeout)
        if not got:
            return {"acquired": False, "prev_owner": None, "prev_owner_live_members": 0, "timestamp": None,
                    "error": "lock_timeout"}

        with self._local_lock:
            try:
                cur = self._conn.cursor()
                cur.execute("SELECT owner_group_id FROM resources WHERE key = ?", (key,))
                row = cur.fetchone()
                prev_owner = row[0] if row else None

                # 防呆：如果本组已拥有，无需覆盖
                if prev_owner == self.group_id:
                    cur.close()
                    return {
                        "acquired": True,
                        "prev_owner": self.group_id,
                        "prev_owner_live_members": int(self._count_live_members(self.group_id)),
                        "timestamp": now_ts,
                        "error": None
                    }

                if not row:
                    # 不存在 -> 创建并持有
                    cur.execute(
                        "INSERT INTO resources (key, owner_group_id, claimed_at, data) VALUES (?, ?, ?, NULL)",
                        (key, self.group_id, now_ts)
                    )
                else:
                    # 存在 -> 强制覆盖owner
                    cur.execute(
                        "UPDATE resources SET owner_group_id = ?, claimed_at = ? WHERE key = ?",
                        (self.group_id, now_ts, key)
                    )

                self._conn.commit()
                cur.close()

                prev_owner_live = 0
                if prev_owner and prev_owner != self.group_id:
                    try:
                        prev_owner_live = int(self._count_live_members(prev_owner))
                    except Exception:
                        prev_owner_live = 0

                return {
                    "acquired": True,
                    "prev_owner": prev_owner,
                    "prev_owner_live_members": prev_owner_live,
                    "timestamp": now_ts,
                    "error": None
                }
            except Exception as e:
                try:
                    self._conn.rollback()
                except Exception:
                    pass
                return {"acquired": False, "prev_owner": None, "prev_owner_live_members": 0, "timestamp": None,
                        "error": str(e)}

    def list_group_resources(self, group_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        返回指定组（默认当前组）所拥有的所有资源字典，格式:
          { resource_key: {"key": key, "owner_group_id": gid, "claimed_at": ts, "data": <parsed json or raw>} }
        """
        gid = group_id or self.group_id
        if self.auto_touch_on_ops:
            try:
                self._lazy_touch_and_cleanup()
            except Exception:
                pass

        with self._local_lock:
            cur = self._conn.cursor()
            cur.execute("SELECT key, claimed_at, data FROM resources WHERE owner_group_id = ?", (gid,))
            rows = cur.fetchall()
            cur.close()

        result: Dict[str, Dict[str, Any]] = {}
        for key, claimed_at, data in rows:
            try:
                parsed = json.loads(data) if data else None
            except Exception:
                parsed = data
            result[key] = {"key": key, "owner_group_id": gid, "claimed_at": claimed_at, "data": parsed}
        return result

    def get_owned_resource(self, key: str) -> Optional[Dict[str, Any]]:
        """
        返回当前组持有的指定资源的信息（含 data），若该资源不存在或不被当前组持有则返回 None。
        """
        if self.auto_touch_on_ops:
            try:
                self._lazy_touch_and_cleanup()
            except Exception:
                pass

        with self._local_lock:
            cur = self._conn.cursor()
            cur.execute("SELECT owner_group_id, claimed_at, data FROM resources WHERE key = ?", (key,))
            row = cur.fetchone()
            cur.close()

        if not row:
            return None
        owner, claimed_at, data = row
        if owner != self.group_id:
            return None
        try:
            parsed = json.loads(data) if data else None
        except Exception:
            parsed = data
        return {"key": key, "owner_group_id": owner, "claimed_at": claimed_at, "data": parsed}

    def is_resource_owned_by_group(self, key: str, group_id: Optional[str] = None) -> bool:
        """
        判断指定资源是否当前被某组持有（默认检查当前组）。
        返回 True/False。
        """
        gid = group_id or self.group_id
        if self.auto_touch_on_ops:
            try:
                self._lazy_touch_and_cleanup()
            except Exception:
                pass

        with self._local_lock:
            cur = self._conn.cursor()
            cur.execute("SELECT 1 FROM resources WHERE key = ? AND owner_group_id = ?", (key, gid))
            r = cur.fetchone()
            cur.close()
        return bool(r)

    # ---------------- delete_resource (safe: block->claim->delete) ----------------
    def delete_resource(self, key: str, timeout: float = 5.0) -> bool:
        """
        安全删除资源（保证互斥语义）：

        1) 资源不存在返回 False。
        2) 先通过 acquire_resource 阻塞获取占有权。
        3) 获取后执行条件 DELETE（WHERE key=? AND owner_group_id=?），避免误删他人资源。
        """
        # quick existence check (don't create resource if missing)
        cur = self._conn.cursor()
        cur.execute("SELECT 1 FROM resources WHERE key = ?", (key,))
        exists = cur.fetchone() is not None
        cur.close()
        if not exists:
            return False

        # block until we get ownership
        acquired = self.acquire_resource(key, timeout=timeout)
        if not acquired:
            return False

        # Now we should be owner — delete atomically
        with self._local_lock:
            if not self._try_begin_immediate(timeout=DEFAULT_LOCK_TIMEOUT):
                # fallback conditional delete
                try:
                    cur = self._conn.cursor()
                    cur.execute("DELETE FROM resources WHERE key = ? AND owner_group_id = ?", (key, self.group_id))
                    deleted = getattr(cur, "rowcount", None)
                    cur.close()
                    self._conn.commit()
                    if deleted is not None:
                        return deleted > 0
                    # fallback verify
                    cur2 = self._conn.cursor()
                    cur2.execute("SELECT 1 FROM resources WHERE key = ?", (key,))
                    still = cur2.fetchone() is not None
                    cur2.close()
                    return not still
                except Exception:
                    try:
                        self._conn.rollback()
                    except Exception:
                        pass
                    return False

            try:
                cur = self._conn.cursor()
                cur.execute("DELETE FROM resources WHERE key = ? AND owner_group_id = ?", (key, self.group_id))
                deleted = getattr(cur, "rowcount", None)
                cur.close()
                self._conn.commit()
                if deleted is not None:
                    return deleted > 0
                cur2 = self._conn.cursor()
                cur2.execute("SELECT 1 FROM resources WHERE key = ?", (key,))
                still = cur2.fetchone() is not None
                cur2.close()
                return not still
            except Exception:
                try:
                    self._conn.rollback()
                except Exception:
                    pass
                return False

    # ---------------- refcount & misc ----------------
    def group_refcount(self, group_id: Optional[str] = None) -> int:
        """返回指定 group 的“存活成员数”（可视作引用计数）。"""
        gid = group_id or self.group_id
        if self.auto_touch_on_ops:
            self._lazy_touch_and_cleanup()
        return self._count_live_members(gid)

    def unregister_member(self):
        """注销当前 member，并尽力清理空组及其占有资源。"""
        with self._local_lock:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM members WHERE member_id = ?", (self.member_id,))
            # clear resources and remove empty groups
            cur.execute("""
                SELECT g.group_id FROM groups g LEFT JOIN members m ON g.group_id = m.group_id WHERE m.member_id IS NULL
            """)
            empty = [r[0] for r in cur.fetchall()]
            for gid in empty:
                cur.execute("UPDATE resources SET owner_group_id = NULL, claimed_at = NULL WHERE owner_group_id = ?",
                            (gid,))
                cur.execute("DELETE FROM groups WHERE group_id = ?", (gid,))
            cur.close()
            self._conn.commit()

    def close(self):
        """
        关闭连接：

        - 在 file-op lock 下做一次 WAL checkpoint（尽力而为），避免与修复/替换流程竞态。
        - 注销当前 member，并关闭 DB 连接（尽力而为）。
        """
        # Acquire short file-op lock to serialize checkpoint/close with repair operations
        got = False
        try:
            got = self._acquire_file_op_lock(wait_seconds=5.0)
            try:
                # best-effort checkpoint FULL to flush WAL to main DB file
                try:
                    with self._local_lock:
                        self._conn.execute("PRAGMA wal_checkpoint(FULL);")
                except Exception:
                    pass
            finally:
                if got:
                    self._release_file_op_lock()
        except Exception:
            pass

        # proceed to unregister and close DB
        try:
            self.unregister_member()
        except Exception:
            pass
        try:
            with self._local_lock:
                try:
                    self._conn.close()
                except Exception:
                    pass
        except Exception:
            pass

    @staticmethod
    def cleanup_db(db_path: str, stale_ttl: float = DEFAULT_STALE_TTL, use_psutil: bool = True):
        """对指定 DB 做一次离线清理：删除死亡 members，清理空组并释放其资源占有。"""
        if use_psutil:
            _require_psutil()
        conn = sqlite3.connect(db_path, timeout=DEFAULT_DB_BUSY_TIMEOUT_MS / 1000.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        cur = conn.cursor()
        cur.execute("SELECT member_id, group_id, pid, start_time, last_heartbeat FROM members")
        rows = cur.fetchall()
        now = time.time()
        remove = []
        for mid, gid, pid, st, lh in rows:
            alive = False
            if (now - lh) <= stale_ttl:
                alive = True
            else:
                if use_psutil:
                    try:
                        if _psutil_pid_exists(pid):
                            p_ct = _psutil_process_create_time(pid)
                            if p_ct is not None and abs(p_ct - st) <= 2.0:
                                alive = True
                    except Exception:
                        pass
            if not alive:
                remove.append(mid)
        if remove:
            for mid in remove:
                cur.execute("DELETE FROM members WHERE member_id = ?", (mid,))
            cur.execute("""
                SELECT g.group_id FROM groups g LEFT JOIN members m ON g.group_id = m.group_id WHERE m.member_id IS NULL
            """)
            empty_groups = [r[0] for r in cur.fetchall()]
            for gid in empty_groups:
                cur.execute("UPDATE resources SET owner_group_id = NULL, claimed_at = NULL WHERE owner_group_id = ?",
                            (gid,))
                cur.execute("DELETE FROM groups WHERE group_id = ?", (gid,))
            conn.commit()
        cur.close()
        conn.close()

    def delete_group_kv(self, key: str) -> bool:
        """删除当前 group 的指定 KV 键；若不存在则返回 False。"""
        if self.auto_touch_on_ops:
            try:
                self._lazy_touch_and_cleanup()
            except Exception:
                pass
        changed_box = {"changed": None}

        def op(cur):
            cur.execute("DELETE FROM group_kv WHERE group_id = ? AND key = ?", (self.group_id, key))
            changed_box["changed"] = getattr(cur, "rowcount", None)

        ok = self._run_immediate_write(
            op,
            wait_seconds=min(5.0, float(getattr(self, "init_lock_wait", 5.0))),
            rotate_on_timeout=True,
        )
        if not ok:
            raise sqlite3.OperationalError("database is locked")
        changed = changed_box.get("changed", None)
        if changed is None:
            cur2 = self._conn.cursor()
            cur2.execute("SELECT 1 FROM group_kv WHERE group_id = ? AND key = ?", (self.group_id, key))
            still = cur2.fetchone() is not None
            cur2.close()
            return not still
        return changed > 0

    def upsert_resource_data_unchecked(self, key: str, data: Any, create_if_missing: bool = True) -> bool:
        """
        不校验 owner 直接写入 resources.data（用于“共享资源”场景的资源元数据写入）。

        - 默认资源不存在则创建（owner_group_id/claimed_at 保持 NULL）。
        - 该方法不会改变互斥占有语义，因为它不修改 owner 字段。
        """
        if self.auto_touch_on_ops:
            try:
                self._lazy_touch_and_cleanup()
            except Exception:
                pass
        djson = json.dumps(data, ensure_ascii=False)

        def op(cur):
            cur.execute("UPDATE resources SET data = ? WHERE key = ?", (djson, key))
            changed = getattr(cur, "rowcount", None)
            if changed is None:
                cur.execute("SELECT 1 FROM resources WHERE key = ?", (key,))
                exists = cur.fetchone() is not None
            else:
                exists = changed > 0
            if (not exists) and create_if_missing:
                cur.execute(
                    "INSERT OR IGNORE INTO resources (key, owner_group_id, claimed_at, data) VALUES (?, NULL, NULL, ?)",
                    (key, djson),
                )

        try:
            ok = self._run_immediate_write(
                op,
                wait_seconds=min(5.0, float(getattr(self, "init_lock_wait", 5.0))),
                rotate_on_timeout=True,
            )
            if not ok:
                raise sqlite3.OperationalError("database is locked")
            return True
        except sqlite3.OperationalError:
            raise
        except Exception:
            return False

    def join_shared_resource(self, resource_key: str, user_params: Any = None, joined_at: Optional[float] = None) -> None:
        """
        以“共享资源使用者”的身份加入 resource_key（例如 THUB）。

        - 该方法不会占有资源（不写 owner_group_id），因此不会与互斥能力冲突。
        - 使用参数写入 group_kv，键空间为 shared:<resource_key>:*。
        - 当 group 无任何存活成员后，中心侧触发清理会自动级联删除这些 KV，从而“自动消失”。
        """
        ts = _now() if joined_at is None else float(joined_at)
        self.set_group_kv(f"shared:{resource_key}:joined_at", ts)
        self.set_group_kv(f"shared:{resource_key}:params", user_params)

    def update_shared_resource_params(self, resource_key: str, user_params: Any) -> None:
        """更新当前 group 在指定共享资源下的使用参数。"""
        self.set_group_kv(f"shared:{resource_key}:params", user_params)

    def leave_shared_resource(self, resource_key: str) -> None:
        """主动退出指定共享资源：删除当前 group 下记录的 joined_at/params。"""
        self.delete_group_kv(f"shared:{resource_key}:params")
        self.delete_group_kv(f"shared:{resource_key}:joined_at")

    def get_shared_resource_user_params(self, resource_key: str, group_id: Optional[str] = None) -> Optional[Any]:
        """读取指定 group（默认当前 group）在共享资源下的使用参数。"""
        gid = group_id or self.group_id
        if self.auto_touch_on_ops:
            try:
                self._lazy_touch_and_cleanup()
            except Exception:
                pass
        cur = self._conn.cursor()
        cur.execute("SELECT value FROM group_kv WHERE group_id = ? AND key = ?", (gid, f"shared:{resource_key}:params"))
        r = cur.fetchone()
        cur.close()
        if not r:
            return None
        try:
            return json.loads(r[0])
        except Exception:
            return r[0]

    def list_shared_resource_users(self, resource_key: str) -> Dict[str, Dict[str, Any]]:
        """
        列出当前 DB 中仍存活、且声明正在使用该共享资源的所有 group。

        返回：
          { group_id: {"joined_at": float|None, "params": Any, "member_count": int, "last_heartbeat": float|None} }
        """
        if self.auto_touch_on_ops:
            try:
                self._lazy_touch_and_cleanup()
            except Exception:
                pass
        params_key = f"shared:{resource_key}:params"
        joined_key = f"shared:{resource_key}:joined_at"
        now = _now()
        with self._local_lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT
                    p.group_id,
                    p.value AS params_value,
                    j.value AS joined_value
                FROM group_kv p
                LEFT JOIN group_kv j ON j.group_id = p.group_id AND j.key = ?
                WHERE p.key = ?
                """,
                (joined_key, params_key),
            )
            rows = cur.fetchall()
            group_ids = [r[0] for r in rows]
            members_by_gid: Dict[str, list] = {}
            if group_ids:
                placeholders = ",".join(["?"] * len(group_ids))
                cur.execute(
                    f"SELECT group_id, pid, start_time, last_heartbeat FROM members WHERE group_id IN ({placeholders})",
                    tuple(group_ids),
                )
                for gid, pid, st, lh in cur.fetchall():
                    members_by_gid.setdefault(gid, []).append((pid, st, lh))
            cur.close()
        result: Dict[str, Dict[str, Any]] = {}
        for gid, params_v, joined_v in rows:
            try:
                params_obj = json.loads(params_v) if params_v is not None else None
            except Exception:
                params_obj = params_v
            try:
                joined_obj = json.loads(joined_v) if joined_v is not None else None
            except Exception:
                joined_obj = joined_v
            try:
                joined_ts = float(joined_obj) if joined_obj is not None else None
            except Exception:
                joined_ts = None
            live_cnt = 0
            live_last_hb: Optional[float] = None
            for pid, st, lh in members_by_gid.get(gid, []):
                if self._is_member_alive(int(pid), float(st), float(lh), now):
                    live_cnt += 1
                    if live_last_hb is None or float(lh) > live_last_hb:
                        live_last_hb = float(lh)
            if live_cnt <= 0:
                continue
            result[gid] = {"joined_at": joined_ts, "params": params_obj, "member_count": live_cnt, "last_heartbeat": live_last_hb}
        return result

    def set_shared_resource_merged_params(self, resource_key: str, merged_params: Any) -> bool:
        """
        写入中心侧合并后的共享资源参数到 resources.data（不校验 owner）。

        存储结构：
          {"merged_params": <Any>, "updated_at": <float>}
        """
        payload = {"merged_params": merged_params, "updated_at": _now()}
        return self.upsert_resource_data_unchecked(resource_key, payload, create_if_missing=True)


# ------------------------------- Demo ------------------------------------

def _main1():
    DB = r"D:\hehe\lazy_pool_ref.db"
    GROUP = "my-test-group-01"
    p = LazySharedPool(DB, group_id=GROUP)
    print("member:", p.member_id, "group:", p.group_id)

    # 创建资源描述（可选）
    # p.create_resource("device:usb123", data={"serial": "usb123", "type": "adb"})

    # 占有资源（非阻塞尝试）
    ok = p.acquire_resource("device:usb123", timeout=30)
    print("main1 claim device:", ok)  # True expected

    # 拥有后可以更新 resource.data
    p.update_resource_data("摄像头", {"serial": "usb123", "type": "adb", "owner_note": "reserved by group-01"})

    # 长时间运行以模拟占有
    time.sleep(300)
    p.close()


def _main2():
    DB = r"D:\hehe\lazy_pool_ref.db"
    GROUP = "my-test-group-02"
    p = LazySharedPool(DB, group_id=GROUP)
    print("trying to claim device")
    ok = p.acquire_resource("123456678768", timeout=30.0)
    print("main2 claim result:", ok)
    if ok:
        # can update only if acquired
        p.update_resource_data("device:usb123", {"note": "I own it now"})
    else:
        res = p.get_resource("device:usb123")
        print("current owner:", res["owner_group_id"], "data:", res["data"])
    time.sleep(30)
    p.close()


def _main3():
    DB = r"D:\hehe\lazy_pool_ref.db"
    GROUP = "my-test-group-02"
    p = LazySharedPool(DB, group_id=GROUP)
    ok = p.delete_resource("device:usb123", timeout=30.0)
    print("main3 delete result:", ok)
    p.close()


def _main4():
    DB = r"D:\hehe\lazy_pool_ref.db"
    GROUP = "my-test-group-01"
    p = LazySharedPool(DB, group_id=GROUP)
    from datetime import datetime
    from datetime import timedelta
    end_time = datetime.now() + timedelta(hours=1)
    p.join_shared_resource('摄像头', {'结束时间': end_time.isoformat()})



def _main5():
    DB = r"D:\hehe\lazy_pool_ref.db"
    GROUP = "my-test-group-02"
    p = LazySharedPool(DB, group_id=GROUP)
    p.join_shared_resource('摄像头', None)
    p.leave_shared_resource('摄像头')


def _main6_server():
    DB = r"D:\hehe\lazy_pool_ref.db"
    GROUP = "my-test-group-video-server"
    p = LazySharedPool(DB, group_id=GROUP)
    # p.acquire_resource('摄像头', timeout=0)
    _users = p.list_shared_resource_users('摄像头')
    # p.upsert_resource_data_unchecked('摄像头', {'状态': '坏了'})
    print(_users)


if __name__ == '__main__':
    _main1()
    # _main2()
