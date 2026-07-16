"""SQLite 数据库层 - 任务与分析结果持久化。

表结构：
- tasks: 任务元信息（每条分析任务一条记录）
- patches: 补丁分析结果（SHA 主键，与任务解耦）
- task_patches: 任务-补丁关联表（多对多）
- config: 配置项（LLM 等）
"""
import json
import os
import shutil
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

def _resolve_data_dir() -> Path:
    override = os.environ.get("GKI_DATA_DIR", "").strip()
    if override:
        return Path(override) / "web_app" / "data"
    return Path(__file__).parent / "data"


DATA_DIR = _resolve_data_dir()
DB_PATH = DATA_DIR / "gki_patch.db"
# Committed seed snapshot; runtime DB lives under DATA_DIR and is gitignored.
SEED_DB_PATH = Path(__file__).resolve().parent / "seed" / "gki_patch.db.seed"

_db_write_lock = threading.RLock()
_DB_CONNECT_TIMEOUT = 30.0
_DB_BUSY_TIMEOUT_MS = 30000
_DB_RETRY_ATTEMPTS = 6
_DB_RETRY_BASE_DELAY = 0.15

T = TypeVar("T")


def _ensure_db_from_seed() -> None:
    """Create runtime DB from the committed seed when missing."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists() or not SEED_DB_PATH.is_file():
        return
    shutil.copy2(SEED_DB_PATH, DB_PATH)


def _get_conn() -> sqlite3.Connection:
    _ensure_db_from_seed()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=_DB_CONNECT_TIMEOUT)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={_DB_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _is_sqlite_lock_error(exc: BaseException) -> bool:
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    msg = str(exc).lower()
    return "locked" in msg or "busy" in msg


def _run_db_write(operation: Callable[[], T]) -> T:
    """Serialize SQLite writes and retry transient lock errors."""
    last_exc: Optional[BaseException] = None
    for attempt in range(_DB_RETRY_ATTEMPTS):
        try:
            with _db_write_lock:
                return operation()
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if not _is_sqlite_lock_error(exc) or attempt >= _DB_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(_DB_RETRY_BASE_DELAY * (2 ** attempt))
    if last_exc:
        raise last_exc
    raise RuntimeError("unreachable")


def init_db() -> None:
    """Initialize database schema with migration from legacy layout."""
    conn = _get_conn()

    # ── Core tables ────────────────────────────────────
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id          TEXT PRIMARY KEY,
            type        TEXT NOT NULL DEFAULT 'range',
            repo        TEXT NOT NULL DEFAULT '',
            from_tag    TEXT DEFAULT '',
            to_tag      TEXT DEFAULT '',
            sample_size INTEGER DEFAULT 0,
            status      TEXT NOT NULL DEFAULT 'pending',
            total       INTEGER DEFAULT 0,
            analyzed    INTEGER DEFAULT 0,
            failed      INTEGER DEFAULT 0,
            error_msg   TEXT DEFAULT '',
            created_at  TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );
    """)
    conn.commit()

    # ── Migration: summary column ──────────────────────
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN summary TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    # ── Migration: test_summary_llm column ──────────────
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN test_summary_llm TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    # ── Migration: llm_token columns ────────────────────
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN llm_prompt_tokens INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN llm_completion_tokens INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # ── Migration: elapsed_seconds column ────────────
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN elapsed_seconds REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # ── Migration: new_analyzed / reused_count columns ─
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN new_analyzed INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN reused_count INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # ── Migration: diff_file path column ───────────
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN diff_file TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    # ── Migration: squash_summary column ───────────
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN squash_summary TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    # ── 区间 patch 缓存表（repo + tag 区间 → 磁盘文件路径） ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS interval_diffs (
            repo          TEXT NOT NULL DEFAULT '',
            from_tag      TEXT NOT NULL,
            to_tag        TEXT NOT NULL,
            diff_file     TEXT NOT NULL,
            squash_file   TEXT NOT NULL,
            commit_count  INTEGER DEFAULT 0,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            PRIMARY KEY (repo, from_tag, to_tag)
        )
    """)
    conn.commit()

    # ── Migration: module_summaries column ───────────
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN module_summaries TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    conn.commit()

    # ── Migration: module_chunk_summaries column (chunk cache / resume) ──
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN module_chunk_summaries TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    conn.commit()

    # ── Migration: monthly_subtag_results (embedded sub-tag analysis) ──
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN monthly_subtag_results TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    conn.commit()

    # ── Migration: subsequent Fixes snapshot (defect scan) ──
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN future_fix_pool_count INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN future_fix_task_count INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN future_fix_patches TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    conn.commit()

    # ── Migration: check for legacy patches table ─────
    legacy_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='patches_legacy'"
    ).fetchone() is not None

    if not legacy_exists:
        # Check if current patches table has old format (with task_id)
        table_info = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='patches'"
        ).fetchone()
        if table_info:
            cols = [
                r["name"] for r in
                conn.execute("PRAGMA table_info(patches)").fetchall()
            ]
            if "task_id" in cols:
                print("[DB] 检测到旧版 patches 表，开始迁移...", flush=True)
                conn.execute("ALTER TABLE patches RENAME TO patches_legacy")
                conn.commit()
                legacy_exists = True

    # ── Create new standalone patches + task_patches ───
    conn.execute("""
        CREATE TABLE IF NOT EXISTS patches (
            sha          TEXT PRIMARY KEY,
            title        TEXT NOT NULL DEFAULT '',
            score        REAL DEFAULT 0,
            recommendation TEXT DEFAULT '',
            key_risk     TEXT DEFAULT '',
            data         TEXT NOT NULL DEFAULT '{}',
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL,
            dev_module   TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_patches (
            task_id      TEXT NOT NULL,
            sha          TEXT NOT NULL,
            created_at   TEXT NOT NULL,
            PRIMARY KEY (task_id, sha),
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (sha) REFERENCES patches(sha) ON DELETE CASCADE
        )
    """)
    conn.commit()

    # ── Migrate data from legacy ──────────────────────
    if legacy_exists:
        new_empty = conn.execute("SELECT count(*) FROM patches").fetchone()[0] == 0
        if new_empty:
            print("[DB] 迁移旧版 patches 数据到新结构...", flush=True)
            old_rows = conn.execute("SELECT * FROM patches_legacy").fetchall()
            now = datetime.now().isoformat()
            for d in [dict(r) for r in old_rows]:
                sha = d["sha"]
                conn.execute(
                    """INSERT OR IGNORE INTO patches
                       (sha, title, score, recommendation, key_risk, data, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (sha, d.get("title", ""),
                     float(d.get("score", 0) or 0),
                     d.get("recommendation", ""),
                     d.get("key_risk", ""),
                     d.get("data", "{}"),
                     d.get("created_at", now), now)
                )
                task_id = d.get("task_id", "")
                if task_id:
                    conn.execute(
                        "INSERT OR IGNORE INTO task_patches (task_id, sha, created_at) VALUES (?, ?, ?)",
                        (task_id, sha, now)
                    )
            conn.execute("DROP TABLE patches_legacy")
            conn.commit()
            print(f"[DB] 迁移完成: {len(old_rows)} 条", flush=True)

    # ── Migration: patches.dev_module column (must run after patches exists) ──
    try:
        conn.execute("ALTER TABLE patches ADD COLUMN dev_module TEXT DEFAULT ''")
        rows = conn.execute(
            "SELECT sha, data FROM patches WHERE dev_module = '' OR dev_module IS NULL"
        ).fetchall()
        for row in rows:
            try:
                data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
                dm = data.get("dev_module", "")
                if dm:
                    conn.execute("UPDATE patches SET dev_module=? WHERE sha=?", (dm, row["sha"]))
            except (json.JSONDecodeError, TypeError):
                pass
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # ── Crash analysis table ──────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crash_analysis (
            id                TEXT PRIMARY KEY,
            from_tag          TEXT NOT NULL DEFAULT '',
            to_tag            TEXT NOT NULL DEFAULT '',
            crash_log         TEXT NOT NULL DEFAULT '',
            status            TEXT NOT NULL DEFAULT 'pending',
            crash_summary     TEXT DEFAULT '',
            suspected_patches TEXT DEFAULT '[]',
            is_caused_by_merge INTEGER DEFAULT 0,
            fix_commits       TEXT DEFAULT '[]',
            recommendations   TEXT DEFAULT '{}',
            full_report       TEXT DEFAULT '',
            error_msg         TEXT DEFAULT '',
            elapsed_seconds   REAL DEFAULT 0,
            created_at        TEXT NOT NULL,
            completed_at      TEXT DEFAULT ''
        )
    """)
    conn.commit()

    # ── Migration: recommendations column ───────────────
    try:
        conn.execute("ALTER TABLE crash_analysis ADD COLUMN recommendations TEXT DEFAULT '{}'")
    except sqlite3.OperationalError:
        pass
    conn.commit()

    # ── GKI upgrade jobs ────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS upgrade_jobs (
            id                TEXT PRIMARY KEY,
            analysis_task_id  TEXT DEFAULT '',
            repo              TEXT NOT NULL DEFAULT '',
            target_repo_dir   TEXT NOT NULL DEFAULT '',
            from_tag          TEXT NOT NULL DEFAULT '',
            to_tag            TEXT NOT NULL DEFAULT '',
            apply_mode        TEXT NOT NULL DEFAULT 'squash',
            patch_file        TEXT NOT NULL DEFAULT '',
            status            TEXT NOT NULL DEFAULT 'pending',
            phase             TEXT NOT NULL DEFAULT 'prepare',
            conflict_files    TEXT DEFAULT '[]',
            applied_commits   INTEGER DEFAULT 0,
            total_commits     INTEGER DEFAULT 0,
            commit_sha        TEXT DEFAULT '',
            build_command     TEXT DEFAULT '',
            build_workdir     TEXT DEFAULT '',
            build_exit_code   INTEGER DEFAULT -1,
            build_log_file    TEXT DEFAULT '',
            backup_branch     TEXT DEFAULT '',
            error_msg         TEXT DEFAULT '',
            options           TEXT DEFAULT '{}',
            created_at        TEXT NOT NULL,
            completed_at      TEXT DEFAULT ''
        )
    """)
    conn.commit()

    try:
        conn.execute("ALTER TABLE upgrade_jobs ADD COLUMN build_workdir TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE upgrade_jobs ADD COLUMN remote_temp_dir TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE upgrade_jobs ADD COLUMN local_repo_mount TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE upgrade_jobs ADD COLUMN local_build_mount TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    conn.commit()

    conn.close()
    _verify_schema()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(r["name"]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


_SCHEMA_REQUIREMENTS: Dict[str, set[str]] = {
    "tasks": {
        "id", "type", "repo", "from_tag", "to_tag", "sample_size", "status",
        "total", "analyzed", "failed", "error_msg", "created_at", "completed_at",
        "summary", "test_summary_llm", "llm_prompt_tokens", "llm_completion_tokens",
        "elapsed_seconds", "new_analyzed", "reused_count", "diff_file",
        "squash_summary", "module_summaries", "module_chunk_summaries",
        "monthly_subtag_results",
    },
    "patches": {
        "sha", "title", "score", "recommendation", "key_risk", "data",
        "created_at", "updated_at", "dev_module",
    },
    "task_patches": {"task_id", "sha", "created_at"},
    "interval_diffs": {
        "repo", "from_tag", "to_tag", "diff_file", "squash_file",
        "commit_count", "created_at", "updated_at",
    },
    "crash_analysis": {
        "id", "from_tag", "to_tag", "crash_log", "status", "recommendations",
    },
    "upgrade_jobs": {
        "id", "repo", "from_tag", "to_tag", "status", "build_workdir",
        "remote_temp_dir", "local_repo_mount", "local_build_mount",
    },
}


def _verify_schema() -> None:
    """Fail fast when init_db leaves required columns missing (fresh DB / migration bugs)."""
    conn = _get_conn()
    try:
        missing: Dict[str, List[str]] = {}
        for table, required in _SCHEMA_REQUIREMENTS.items():
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not exists:
                missing[table] = sorted(required)
                continue
            cols = _table_columns(conn, table)
            absent = sorted(required - cols)
            if absent:
                missing[table] = absent
        if missing:
            detail = "; ".join(f"{table}: {', '.join(cols)}" for table, cols in missing.items())
            raise RuntimeError(f"Database schema verification failed: {detail}")
    finally:
        conn.close()


# ── Task CRUD ──────────────────────────────────────────

def create_task(task_id: str, task_type: str, repo: str,
                from_tag: str = "", to_tag: str = "",
                sample_size: int = 0) -> None:
    def _op() -> None:
        conn = _get_conn()
        now = datetime.now().isoformat()
        try:
            conn.execute(
                """INSERT INTO tasks (id, type, repo, from_tag, to_tag, sample_size, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (task_id, task_type, repo, from_tag, to_tag, sample_size, now),
            )
            conn.commit()
        finally:
            conn.close()

    _run_db_write(_op)


def update_task(task_id: str, **kwargs: Any) -> None:
    if not kwargs:
        return

    def _op() -> None:
        conn = _get_conn()
        try:
            sets = ", ".join(f"{k}=?" for k in kwargs)
            vals = list(kwargs.values()) + [task_id]
            conn.execute(f"UPDATE tasks SET {sets} WHERE id=?", vals)
            conn.commit()
        finally:
            conn.close()

    _run_db_write(_op)


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_tasks(limit: int = 50) -> List[Dict[str, Any]]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_task(task_id: str) -> None:
    conn = _get_conn()
    # task_patches has ON DELETE CASCADE, so deleting task removes links
    conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.commit()
    conn.close()


# ── Patch CRUD ─────────────────────────────────────────

def get_patches_by_shas(shas: List[str]) -> List[Dict[str, Any]]:
    """Batch fetch patch rows by SHA list (preserves no particular order)."""
    unique = [s.strip() for s in shas if s and str(s).strip()]
    if not unique:
        return []
    conn = _get_conn()
    rows: List[Dict[str, Any]] = []
    chunk_size = 400
    try:
        for i in range(0, len(unique), chunk_size):
            chunk = unique[i:i + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            found = conn.execute(
                f"SELECT * FROM patches WHERE sha IN ({placeholders})",
                chunk,
            ).fetchall()
            rows.extend(dict(r) for r in found)
    finally:
        conn.close()
    return rows


def get_patch(sha: str) -> Optional[Dict[str, Any]]:
    """Get a patch by SHA (from standalone patches table)."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM patches WHERE sha=?", (sha,)).fetchone()
    conn.close()
    return dict(row) if row else None


def patch_exists(sha: str) -> bool:
    """Check if a patch already exists in the database."""
    conn = _get_conn()
    row = conn.execute("SELECT 1 FROM patches WHERE sha=?", (sha,)).fetchone()
    conn.close()
    return row is not None


# ── Interval diff cache CRUD ───────────────────────────

def get_interval_diff(
    repo: str, from_tag: str, to_tag: str,
) -> Optional[Dict[str, Any]]:
    """Get cached interval patch metadata by repo + tag range."""
    conn = _get_conn()
    row = conn.execute(
        """SELECT * FROM interval_diffs
           WHERE repo=? AND from_tag=? AND to_tag=?""",
        (repo, from_tag, to_tag),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_interval_diff(
    repo: str,
    from_tag: str,
    to_tag: str,
    diff_file: str,
    squash_file: str,
    commit_count: int = 0,
) -> None:
    """Insert or update interval patch cache record."""
    conn = _get_conn()
    now = datetime.now().isoformat()
    existing = conn.execute(
        """SELECT 1 FROM interval_diffs
           WHERE repo=? AND from_tag=? AND to_tag=?""",
        (repo, from_tag, to_tag),
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE interval_diffs
               SET diff_file=?, squash_file=?, commit_count=?, updated_at=?
               WHERE repo=? AND from_tag=? AND to_tag=?""",
            (diff_file, squash_file, commit_count, now, repo, from_tag, to_tag),
        )
    else:
        conn.execute(
            """INSERT INTO interval_diffs
               (repo, from_tag, to_tag, diff_file, squash_file, commit_count,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (repo, from_tag, to_tag, diff_file, squash_file,
             commit_count, now, now),
        )
    conn.commit()
    conn.close()


def delete_interval_diff(repo: str, from_tag: str, to_tag: str) -> None:
    """Remove stale interval patch cache record."""
    conn = _get_conn()
    conn.execute(
        """DELETE FROM interval_diffs
           WHERE repo=? AND from_tag=? AND to_tag=?""",
        (repo, from_tag, to_tag),
    )
    conn.commit()
    conn.close()


def upsert_patch(patch_data: Dict[str, Any]) -> bool:
    """Insert or update a patch record (SHA-keyed, standalone).
    Returns True if it was an update (already existed), False if new insert.
    """
    sha = patch_data.get("commit", "") or patch_data.get("sha", "")
    if not sha:
        return False

    result: Dict[str, bool] = {"is_update": False}

    def _op() -> None:
        conn = _get_conn()
        now = datetime.now().isoformat()
        try:
            result["is_update"] = _upsert_patch_on_conn(conn, patch_data, now)
            conn.commit()
        finally:
            conn.close()

    _run_db_write(_op)
    return result["is_update"]


def get_patch_by_sha(sha: str) -> Optional[Dict[str, Any]]:
    """Get a single patch by its SHA. Returns None if not found.
    Supports both full SHA (exact match) and short SHA (prefix match).
    """
    if not sha:
        return None
    conn = _get_conn()
    # Try exact match first
    row = conn.execute(
        "SELECT * FROM patches WHERE sha = ?",
        (sha,),
    ).fetchone()
    # If not found and SHA is short, try prefix match
    if not row and len(sha) < 40:
        row = conn.execute(
            "SELECT * FROM patches WHERE sha LIKE ?",
            (f"{sha}%",),
        ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    # Parse data JSON
    try:
        d["data"] = json.loads(d.get("data", "{}") or "{}")
    except (json.JSONDecodeError, TypeError):
        d["data"] = {}
    return d


def link_task_patch(task_id: str, sha: str) -> None:
    """Create a link between a task and a patch."""
    if not sha:
        return

    def _op() -> None:
        conn = _get_conn()
        now = datetime.now().isoformat()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO task_patches (task_id, sha, created_at) VALUES (?, ?, ?)",
                (task_id, sha, now),
            )
            conn.commit()
        finally:
            conn.close()

    _run_db_write(_op)


def _upsert_patch_on_conn(conn: sqlite3.Connection, patch_data: Dict[str, Any], now: str) -> bool:
    """Upsert one patch using an existing connection. Returns True if update."""
    sha = patch_data.get("commit", "") or patch_data.get("sha", "")
    if not sha:
        return False
    existing = conn.execute("SELECT data FROM patches WHERE sha=?", (sha,)).fetchone()
    is_update = existing is not None
    if is_update and existing:
        try:
            prev = json.loads(existing["data"] or "{}")
        except (json.JSONDecodeError, TypeError):
            prev = {}
        if isinstance(prev, dict):
            for key in ("fix_in_future", "crash_patterns", "upstream_sha"):
                if not patch_data.get(key) and prev.get(key):
                    patch_data[key] = prev[key]
    row = (
        patch_data.get("title", ""),
        float(patch_data.get("score", 0) or 0),
        patch_data.get("recommendation", ""),
        patch_data.get("key_risk", ""),
        json.dumps(patch_data, ensure_ascii=False),
        now,
        patch_data.get("dev_module", ""),
        sha,
    )
    if is_update:
        conn.execute(
            """UPDATE patches
               SET title=?, score=?, recommendation=?, key_risk=?,
                   data=?, updated_at=?, dev_module=?
               WHERE sha=?""",
            row,
        )
    else:
        conn.execute(
            """INSERT INTO patches
               (sha, title, score, recommendation, key_risk, data, created_at, updated_at, dev_module)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sha, row[0], row[1], row[2], row[3], row[4], now, row[5], row[6]),
        )
    return is_update


class PatchBatchWriter:
    """Batch patch upserts and task links in fewer SQLite transactions."""

    def __init__(self, batch_size: int = 20):
        self.batch_size = max(1, batch_size)
        self._patches: List[Dict[str, Any]] = []
        self._links: List[Tuple[str, str]] = []

    def upsert(self, patch_data: Dict[str, Any]) -> None:
        self._patches.append(patch_data)
        if len(self._patches) >= self.batch_size:
            self.flush()

    def link(self, task_id: str, sha: str) -> None:
        if not task_id or not sha:
            return
        self._links.append((task_id, sha))
        if len(self._patches) + len(self._links) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if not self._patches and not self._links:
            return

        patches = self._patches
        links = self._links

        def _op() -> None:
            conn = _get_conn()
            now = datetime.now().isoformat()
            try:
                for patch_data in patches:
                    _upsert_patch_on_conn(conn, patch_data, now)
                for task_id, sha in links:
                    conn.execute(
                        "INSERT OR IGNORE INTO task_patches (task_id, sha, created_at) VALUES (?, ?, ?)",
                        (task_id, sha, now),
                    )
                conn.commit()
            finally:
                conn.close()

        _run_db_write(_op)
        self._patches.clear()
        self._links.clear()


def get_task_patches(task_id: str, dev_module: str = "") -> List[Dict[str, Any]]:
    """Get all patches linked to a task, optionally filtered by dev_module."""
    conn = _get_conn()
    if dev_module:
        rows = conn.execute(
            """SELECT p.* FROM patches p
               JOIN task_patches tp ON tp.sha = p.sha
               WHERE tp.task_id = ? AND p.dev_module = ?
               ORDER BY p.score DESC""",
            (task_id, dev_module),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT p.* FROM patches p
               JOIN task_patches tp ON tp.sha = p.sha
               WHERE tp.task_id = ?
               ORDER BY p.score DESC""",
            (task_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_task_module_stats(task_id: str) -> List[Dict[str, Any]]:
    """Get per-module statistics for a task's patches."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT p.dev_module,
                  COUNT(*) as count,
                  AVG(p.score) as avg_score,
                  MAX(p.score) as max_score,
                  MIN(p.score) as min_score
           FROM patches p
           JOIN task_patches tp ON tp.sha = p.sha
           WHERE tp.task_id = ?
           GROUP BY p.dev_module
           ORDER BY count DESC""",
        (task_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Backward-compat aliases ────────────────────────────

# save_patch(task_id, data) → upsert_patch(data) + link_task_patch(task_id, sha)
def save_patch(task_id: str, patch_data: Dict[str, Any]) -> None:
    """Legacy wrapper: upsert patch data + link to task."""
    sha = patch_data.get("commit", "") or patch_data.get("sha", "")
    upsert_patch(patch_data)
    link_task_patch(task_id, sha)


# get_patches_by_task(task_id) → get_task_patches(task_id)
def get_patches_by_task(task_id: str, dev_module: str = "") -> List[Dict[str, Any]]:
    """Legacy wrapper."""
    return get_task_patches(task_id, dev_module=dev_module)


def list_all_patches(
    page: int = 1,
    page_size: int = 50,
    search: str = "",
    dev_module: str = "",
) -> Dict[str, Any]:
    """Paginated query of all patches with optional search and module filter."""
    EMPTY_DEV_MODULE_FILTER = "__empty__"
    conn = _get_conn()
    where_clauses = []
    params: list = []

    if search:
        where_clauses.append("(sha LIKE ? OR title LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like])
    if dev_module == EMPTY_DEV_MODULE_FILTER:
        where_clauses.append("(dev_module = '' OR dev_module IS NULL)")
    elif dev_module:
        where_clauses.append("dev_module = ?")
        params.append(dev_module)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    total = conn.execute(
        f"SELECT COUNT(*) FROM patches WHERE {where_sql}", params
    ).fetchone()[0]

    offset = (max(1, page) - 1) * page_size
    rows = conn.execute(
        f"""SELECT sha, title, score, recommendation, key_risk,
                   dev_module, created_at, updated_at
            FROM patches WHERE {where_sql}
            ORDER BY updated_at DESC LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    ).fetchall()
    conn.close()

    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_all_module_stats() -> List[Dict[str, Any]]:
    """Get per-module statistics across all patches."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT dev_module, COUNT(*) as count,
                  ROUND(AVG(score), 2) as avg_score,
                  MAX(score) as max_score,
                  MIN(score) as min_score
           FROM patches GROUP BY dev_module ORDER BY count DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_range_comparison_stats(task_ids: List[str]) -> List[Dict[str, Any]]:
    """Compute comparison statistics for multiple tasks (ranges).
    
    Returns a list of stats dicts, one per task_id, containing:
      - task_id, from_tag, to_tag
      - total_patches, avg_score, min_score, max_score
      - risk_distribution: {high, medium, low, none}
      - module_distribution: {module_name: count}
      - llm_analyzed_count
      - has_future_fix_count
      - top_risk_patches: [{sha, title, score}]
    """
    import json as _json
    if not task_ids:
        return []
    
    conn = _get_conn()
    results = []
    
    for tid in task_ids:
        # Basic task info
        task_row = conn.execute(
            "SELECT id, from_tag, to_tag, total FROM tasks WHERE id = ?", (tid,)
        ).fetchone()
        if not task_row:
            continue
        
        task = dict(task_row)
        
        # Score statistics
        score_stats = conn.execute("""
            SELECT COUNT(*) as total_patches,
                   ROUND(AVG(p.score), 2) as avg_score,
                   ROUND(MIN(p.score), 2) as min_score,
                   ROUND(MAX(p.score), 2) as max_score
            FROM patches p
            JOIN task_patches tp ON tp.sha = p.sha
            WHERE tp.task_id = ?
        """, (tid,)).fetchone()
        
        stats = {
            "task_id": tid,
            "from_tag": task["from_tag"],
            "to_tag": task["to_tag"],
            "total_patches": score_stats["total_patches"] or 0,
            "avg_score": score_stats["avg_score"] or 0,
            "min_score": score_stats["min_score"] or 0,
            "max_score": score_stats["max_score"] or 0,
        }
        
        # Module distribution
        mod_rows = conn.execute("""
            SELECT p.dev_module, COUNT(*) as count
            FROM patches p
            JOIN task_patches tp ON tp.sha = p.sha
            WHERE tp.task_id = ? AND p.dev_module != ''
            GROUP BY p.dev_module ORDER BY count DESC
        """, (tid,)).fetchall()
        stats["module_distribution"] = {r["dev_module"]: r["count"] for r in mod_rows}
        
        # Risk distribution (based on recommendation field)
        risk_counts = {"high": 0, "medium": 0, "low": 0, "none": 0}
        rec_rows = conn.execute("""
            SELECT p.recommendation
            FROM patches p
            JOIN task_patches tp ON tp.sha = p.sha
            WHERE tp.task_id = ?
        """, (tid,)).fetchall()
        for r in rec_rows:
            rec = (r["recommendation"] or "").lower()
            if "high" in rec or "\u9ad8" in rec:
                risk_counts["high"] += 1
            elif "medium" in rec or "\u4e2d" in rec:
                risk_counts["medium"] += 1
            elif "low" in rec or "\u4f4e" in rec:
                risk_counts["low"] += 1
            else:
                risk_counts["none"] += 1
        stats["risk_distribution"] = risk_counts
        
        # LLM analyzed count & future fix count (from data JSON)
        data_rows = conn.execute("""
            SELECT p.data
            FROM patches p
            JOIN task_patches tp ON tp.sha = p.sha
            WHERE tp.task_id = ?
        """, (tid,)).fetchall()
        llm_count = 0
        fix_count = 0
        for r in data_rows:
            try:
                d = _json.loads(r["data"]) if isinstance(r["data"], str) else r["data"]
            except Exception:
                d = {}
            if d.get("llm_analyzed"):
                llm_count += 1
            if d.get("fix_in_future"):
                fix_count += 1
        stats["llm_analyzed_count"] = llm_count
        stats["has_future_fix_count"] = fix_count
        
        # Top risk patches (lowest scores)
        top_rows = conn.execute("""
            SELECT p.sha, p.title, p.score
            FROM patches p
            JOIN task_patches tp ON tp.sha = p.sha
            WHERE tp.task_id = ?
            ORDER BY p.score ASC LIMIT 10
        """, (tid,)).fetchall()
        stats["top_risk_patches"] = [
            {"sha": r["sha"][:12], "title": r["title"][:60], "score": r["score"]}
            for r in top_rows
        ]
        
        results.append(stats)
    
    conn.close()
    return results


def get_cross_range_overlap(task_ids: List[str]) -> Dict[str, Any]:
    """Find patches that appear in multiple ranges (by title/subject match).
    
    Returns:
      - overlap_patches: list of {title, ranges: [task_ids], scores: {task_id: score}}
      - unique_patches: count of patches unique to each range
    """
    if len(task_ids) < 2:
        return {"overlap_patches": [], "unique_patches": {}}
    
    conn = _get_conn()
    # title -> {task_id: {sha, score}}
    title_map: Dict[str, Dict[str, Dict]] = {}
    
    for tid in task_ids:
        rows = conn.execute("""
            SELECT p.sha, p.title, p.score
            FROM patches p
            JOIN task_patches tp ON tp.sha = p.sha
            WHERE tp.task_id = ?
        """, (tid,)).fetchall()
        for r in rows:
            title = r["title"]
            if title not in title_map:
                title_map[title] = {}
            title_map[title][tid] = {"sha": r["sha"][:12], "score": r["score"]}
    
    # Find overlaps (appear in 2+ ranges)
    overlap_patches = []
    unique_per_range = {tid: 0 for tid in task_ids}
    
    for title, ranges in title_map.items():
        if len(ranges) >= 2:
            overlap_patches.append({
                "title": title[:80],
                "range_count": len(ranges),
                "ranges": list(ranges.keys()),
                "scores": {tid: info["score"] for tid, info in ranges.items()},
            })
        else:
            for tid in ranges:
                unique_per_range[tid] = unique_per_range.get(tid, 0) + 1
    
    # Sort by range_count desc, then by avg score asc
    overlap_patches.sort(key=lambda x: (-x["range_count"], 
                                         sum(x["scores"].values()) / max(len(x["scores"]), 1)))
    
    conn.close()
    return {
        "overlap_patches": overlap_patches[:50],  # Top 50
        "unique_patches": unique_per_range,
        "total_overlap": len(overlap_patches),
    }

# ── LLM Config CRUD ─────────────────────────────────────

_LLM_KEYS = ("llm_api_key", "llm_api_base", "llm_model")


def get_db_llm_config() -> Dict[str, str]:
    """Get LLM config from DB. Returns only keys that exist in DB."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT key, value FROM config WHERE key IN (?, ?, ?)", _LLM_KEYS
    ).fetchall()
    conn.close()
    result: Dict[str, str] = {}
    key_map = {"llm_api_key": "api_key", "llm_api_base": "api_base", "llm_model": "model"}
    for r in rows:
        result[key_map[r["key"]]] = r["value"]
    return result


def save_db_llm_config(api_key: str, api_base: str, model: str) -> None:
    """Save LLM config to DB. Empty values are stored as-is."""
    conn = _get_conn()
    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('llm_api_key', ?)", (api_key,))
    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('llm_api_base', ?)", (api_base,))
    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('llm_model', ?)", (model,))
    conn.commit()
    conn.close()


def delete_db_llm_config() -> None:
    """Remove all LLM config entries from DB (fall back to env vars)."""
    conn = _get_conn()
    conn.execute("DELETE FROM config WHERE key IN (?, ?, ?)", _LLM_KEYS)
    conn.commit()
    conn.close()


_REPO_DIR_KEY = "repo_dir"


def get_db_repo_dir() -> str:
    """Get local kernel repo path from DB."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT value FROM config WHERE key = ?", (_REPO_DIR_KEY,)
    ).fetchone()
    conn.close()
    return row["value"] if row else ""


def save_db_repo_dir(repo_dir: str) -> None:
    """Save local kernel repo path to DB."""
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
        (_REPO_DIR_KEY, repo_dir),
    )
    conn.commit()
    conn.close()


# ── SSH credentials (settings UI → DB) ─────────────────

_SSH_CREDENTIALS_KEY = "ssh_credentials"
_SSH_CREDENTIAL_FIELDS = (
    "bastion_user",
    "bastion_password",
    "target_ip",
    "target_user",
    "target_password",
)


def get_db_ssh_credentials() -> Dict[str, str]:
    """Read SSH credentials JSON from config table."""
    import json

    conn = _get_conn()
    row = conn.execute(
        "SELECT value FROM config WHERE key = ?", (_SSH_CREDENTIALS_KEY,)
    ).fetchone()
    conn.close()
    if not row or not row["value"]:
        return {}
    try:
        data = json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: str(data.get(k) or "").strip() for k in _SSH_CREDENTIAL_FIELDS}


def save_db_ssh_credentials(creds: Dict[str, str]) -> None:
    """Persist SSH credentials to config table."""
    import json

    payload = {k: str(creds.get(k) or "").strip() for k in _SSH_CREDENTIAL_FIELDS}
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
        (_SSH_CREDENTIALS_KEY, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def delete_db_ssh_credentials() -> None:
    """Remove SSH credentials from config table."""
    conn = _get_conn()
    conn.execute("DELETE FROM config WHERE key = ?", (_SSH_CREDENTIALS_KEY,))
    conn.commit()
    conn.close()


def get_config_value(key: str) -> str:
    conn = _get_conn()
    row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else ""


def set_config_value(key: str, value: str) -> None:
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
    conn.close()


# ── Upgrade job CRUD ───────────────────────────────────

def create_upgrade_job(job: Dict[str, Any]) -> None:
    conn = _get_conn()
    conn.execute(
        """INSERT INTO upgrade_jobs (
               id, analysis_task_id, repo, target_repo_dir, from_tag, to_tag,
               apply_mode, patch_file, status, phase, options, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            job["id"],
            job.get("analysis_task_id", ""),
            job.get("repo", ""),
            job.get("target_repo_dir", ""),
            job.get("from_tag", ""),
            job.get("to_tag", ""),
            job.get("apply_mode", "squash"),
            job.get("patch_file", ""),
            job.get("status", "pending"),
            job.get("phase", "prepare"),
            json.dumps(job.get("options") or {}, ensure_ascii=False),
            job.get("created_at") or datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def update_upgrade_job(job_id: str, **kwargs: Any) -> None:
    if not kwargs:
        return
    if "conflict_files" in kwargs and not isinstance(kwargs["conflict_files"], str):
        kwargs["conflict_files"] = json.dumps(kwargs["conflict_files"], ensure_ascii=False)
    if "options" in kwargs and not isinstance(kwargs["options"], str):
        kwargs["options"] = json.dumps(kwargs["options"], ensure_ascii=False)
    conn = _get_conn()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [job_id]
    conn.execute(f"UPDATE upgrade_jobs SET {sets} WHERE id=?", vals)
    conn.commit()
    conn.close()


def get_upgrade_job(job_id: str) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM upgrade_jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    for field in ("conflict_files", "options"):
        try:
            raw = d.get(field) or ("[]" if field == "conflict_files" else "{}")
            d[field] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            d[field] = [] if field == "conflict_files" else {}
    return d


def list_upgrade_jobs(limit: int = 50) -> List[Dict[str, Any]]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM upgrade_jobs ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    result: List[Dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        for field in ("conflict_files", "options"):
            try:
                raw = d.get(field) or ("[]" if field == "conflict_files" else "{}")
                d[field] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                d[field] = [] if field == "conflict_files" else {}
        result.append(d)
    return result


def delete_upgrade_job(job_id: str) -> None:
    conn = _get_conn()
    conn.execute("DELETE FROM upgrade_jobs WHERE id=?", (job_id,))
    conn.commit()
    conn.close()


# ── Crash Analysis CRUD ─────────────────────────────────

def create_crash_analysis(
    crash_id: str, from_tag: str, to_tag: str, crash_log: str
) -> None:
    conn = _get_conn()
    now = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO crash_analysis
           (id, from_tag, to_tag, crash_log, status, created_at)
           VALUES (?, ?, ?, ?, 'pending', ?)""",
        (crash_id, from_tag, to_tag, crash_log, now),
    )
    conn.commit()
    conn.close()


def update_crash_analysis(crash_id: str, **kwargs: Any) -> None:
    if not kwargs:
        return
    conn = _get_conn()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [crash_id]
    conn.execute(f"UPDATE crash_analysis SET {sets} WHERE id=?", vals)
    conn.commit()
    conn.close()


def get_crash_analysis(crash_id: str) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM crash_analysis WHERE id=?", (crash_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    # Parse JSON fields
    for field in ("suspected_patches", "fix_commits", "crash_summary", "recommendations"):
        try:
            raw = d.get(field, "" if field in ("crash_summary", "recommendations") else "[]")
            d[field] = json.loads(raw or ("[]" if field in ("suspected_patches", "fix_commits") else "{}"))
        except (json.JSONDecodeError, TypeError):
            d[field] = [] if field in ("suspected_patches", "fix_commits") else {}
    return d


def list_crash_analyses(limit: int = 50) -> List[Dict[str, Any]]:
    conn = _get_conn()
    rows = conn.execute(
        """SELECT id, from_tag, to_tag, status, is_caused_by_merge,
                  created_at, completed_at, elapsed_seconds
           FROM crash_analysis ORDER BY created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_crash_analysis(crash_id: str) -> None:
    conn = _get_conn()
    conn.execute("DELETE FROM crash_analysis WHERE id=?", (crash_id,))
    conn.commit()
    conn.close()
