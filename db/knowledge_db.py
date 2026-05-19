# -*- coding: utf-8 -*-
"""核心知识库操作类

基于 SQLite + numpy 的向量知识库，支持语义搜索、过滤检索、跨模块查询。
使用 onnxruntime 的 DefaultEmbeddingFunction 计算向量，SQLite 持久化存储。
零 C++ 依赖（除 onnxruntime），兼容 Windows/Linux/macOS。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import struct
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from db.config import KnowledgeBaseConfig
from db.models import KnowledgeEntry, _now_iso

logger = logging.getLogger(__name__)

# Collection 类型与表名的映射
_COLLECTION_TABLES = {
    "knowledge": "kb_knowledge",
    "cases": "kb_cases",
    "patterns": "kb_patterns",
}

# SQLite 建表 DDL
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table_name} (
    id TEXT PRIMARY KEY,
    module TEXT NOT NULL,
    title TEXT NOT NULL,
    type TEXT NOT NULL,
    category TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT,
    updated_at TEXT,
    author TEXT,
    confidence REAL,
    tags TEXT,           -- JSON 数组
    content TEXT,
    extra_metadata TEXT, -- JSON 对象
    referenced_by TEXT,  -- JSON 数组
    embedding BLOB       -- numpy float32 向量，二进制存储
);

CREATE INDEX IF NOT EXISTS idx_{table_name}_module ON {table_name}(module);
CREATE INDEX IF NOT EXISTS idx_{table_name}_type ON {table_name}(type);
CREATE INDEX IF NOT EXISTS idx_{table_name}_category ON {table_name}(category);
"""


def _embedding_to_bytes(vec: np.ndarray) -> bytes:
    """numpy float32 向量 → 二进制"""
    return vec.astype(np.float32).tobytes()


def _bytes_to_embedding(data: bytes) -> np.ndarray:
    """二进制 → numpy float32 向量"""
    return np.frombuffer(data, dtype=np.float32).copy()


def _row_to_entry(row: sqlite3.Row) -> KnowledgeEntry:
    """SQLite 行 → KnowledgeEntry"""
    tags = json.loads(row["tags"]) if row["tags"] else []
    referenced_by = json.loads(row["referenced_by"]) if row["referenced_by"] else []
    extra_meta = json.loads(row["extra_metadata"]) if row["extra_metadata"] else {}

    return KnowledgeEntry(
        id=row["id"],
        module=row["module"],
        title=row["title"],
        type=row["type"],
        category=row["category"],
        source=row["source"],
        created_at=row["created_at"] or "",
        updated_at=row["updated_at"] or "",
        author=row["author"] or "system",
        tags=tags,
        confidence=row["confidence"] or 0.80,
        content=row["content"] or "",
        metadata=extra_meta,
        referenced_by=referenced_by,
    )


class KnowledgeDB:
    """核心知识库操作类（SQLite + numpy 实现）"""

    # Collection 名称
    COLLECTION_KNOWLEDGE = "knowledge"
    COLLECTION_CASES = "cases"
    COLLECTION_PATTERNS = "patterns"

    def __init__(self, persist_dir: str | Path | None = None, config: KnowledgeBaseConfig | None = None):
        """初始化知识库

        Args:
            persist_dir: 持久化目录，默认从配置读取
            config: 知识库配置，默认自动加载
        """
        self._config = config or KnowledgeBaseConfig.from_yaml()
        self._persist_dir = Path(persist_dir) if persist_dir else self._config.chroma_persist_dir

        # 确保持久化目录存在
        self._persist_dir.mkdir(parents=True, exist_ok=True)

        # 初始化 SQLite 数据库
        self._db_path = self._persist_dir / "knowledge.db"
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

        # 初始化嵌入函数
        self._embedding_fn = self._get_embedding_function()
        self._embedding_dim = 384  # all-MiniLM-L6-v2

        # 创建表
        self._init_tables()

    @property
    def config(self) -> KnowledgeBaseConfig:
        return self._config

    def _get_embedding_function(self):
        """获取 ONNX 嵌入函数

        使用 ChromaDB 内置的 DefaultEmbeddingFunction（基于 onnxruntime + all-MiniLM-L6-v2）。
        该函数独立于 ChromaDB 的存储层，纯计算无副作用。

        Returns:
            embedding function 或 None（降级模式）
        """
        try:
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
            ef = DefaultEmbeddingFunction()
            # 验证可用
            test = ef(["test"])
            if test and len(test[0]) == 384:
                logger.info("使用 ONNX 嵌入模型 (all-MiniLM-L6-v2, 384d)")
                return ef
        except Exception as e:
            logger.warning("ONNX 嵌入不可用: %s", e)

        logger.warning(
            "语义嵌入模型不可用，使用降级文本搜索模式。"
            "安装 onnxruntime==1.20.1 可启用语义搜索"
        )
        return None

    def _init_tables(self):
        """创建知识库表"""
        cursor = self._conn.cursor()
        for coll_name, table_name in _COLLECTION_TABLES.items():
            cursor.executescript(_CREATE_TABLE_SQL.format(table_name=table_name))
        self._conn.commit()
        logger.info("知识库 SQLite 表初始化完成: %s", list(_COLLECTION_TABLES.values()))

    def _table_for_type(self, entry_type: str) -> str:
        """根据知识条目类型返回表名"""
        if entry_type == "experience_case":
            return _COLLECTION_TABLES[self.COLLECTION_CASES]
        elif entry_type == "error_pattern":
            return _COLLECTION_TABLES[self.COLLECTION_PATTERNS]
        return _COLLECTION_TABLES[self.COLLECTION_KNOWLEDGE]

    def _compute_embedding(self, text: str) -> np.ndarray | None:
        """计算文本的向量表示"""
        if self._embedding_fn is None:
            return None
        try:
            result = self._embedding_fn([text])
            return np.array(result[0], dtype=np.float32)
        except Exception as e:
            logger.warning("计算嵌入失败: %s", e)
            return None

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """批量余弦相似度计算

        Args:
            a: 查询向量 (dim,)
            b: 候选向量矩阵 (n, dim)

        Returns:
            相似度数组 (n,)
        """
        if b.size == 0:
            return np.array([])
        a_norm = a / (np.linalg.norm(a) + 1e-10)
        b_norms = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-10)
        return b_norms @ a_norm

    def _insert_row(self, table: str, entry: KnowledgeEntry, embedding: np.ndarray | None):
        """插入/更新一行到指定表"""
        emb_blob = _embedding_to_bytes(embedding) if embedding is not None else None

        self._conn.execute(
            f"""
            INSERT OR REPLACE INTO {table}
                (id, module, title, type, category, source, created_at, updated_at,
                 author, confidence, tags, content, extra_metadata, referenced_by, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id, entry.module, entry.title, entry.type, entry.category,
                entry.source, entry.created_at, entry.updated_at, entry.author,
                entry.confidence,
                json.dumps(entry.tags, ensure_ascii=False),
                entry.content,
                json.dumps(entry.metadata, ensure_ascii=False) if entry.metadata else None,
                json.dumps(entry.referenced_by, ensure_ascii=False),
                emb_blob,
            ),
        )

    def _delete_row(self, table: str, entry_id: str):
        """从指定表删除一行"""
        self._conn.execute(f"DELETE FROM {table} WHERE id = ?", (entry_id,))

    def _search_in_table(
        self,
        table: str,
        query_vec: np.ndarray | None,
        query_text: str,
        module: str | None = None,
        entry_type: str | None = None,
        category: str | None = None,
        n_results: int = 5,
    ) -> list[KnowledgeEntry]:
        """在指定表中搜索"""
        # 构建 WHERE 子句
        conditions = []
        params: list[Any] = []

        if module:
            conditions.append("module = ?")
            params.append(module)
        if entry_type:
            conditions.append("type = ?")
            params.append(entry_type)
        if category:
            conditions.append("category = ?")
            params.append(category)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # 获取所有候选条目
        rows = self._conn.execute(
            f"SELECT * FROM {table} {where}",
            params,
        ).fetchall()

        if not rows:
            return []

        # 如果有向量，用余弦相似度排序
        if query_vec is not None:
            # 提取所有非 None 嵌入
            valid_rows = []
            embeddings = []
            for row in rows:
                if row["embedding"]:
                    valid_rows.append(row)
                    embeddings.append(_bytes_to_embedding(row["embedding"]))

            if not embeddings:
                return []

            emb_matrix = np.array(embeddings, dtype=np.float32)
            similarities = self._cosine_similarity(query_vec, emb_matrix)

            # 过滤置信度
            min_conf = self._config.retrieval.min_confidence
            results = []
            indices = np.argsort(similarities)[::-1][:n_results]

            for idx in indices:
                sim = float(similarities[idx])
                if sim < min_conf:
                    continue
                entry = _row_to_entry(valid_rows[idx])
                entry.metadata["_similarity"] = round(sim, 4)
                results.append(entry)
                if len(results) >= n_results:
                    break
            return results
        else:
            # 降级模式：文本包含匹配
            results = []
            query_lower = query_text.lower()
            for row in rows:
                content = (row["content"] or "").lower()
                title = (row["title"] or "").lower()
                if query_lower in content or query_lower in title:
                    entry = _row_to_entry(row)
                    results.append(entry)
                    if len(results) >= n_results:
                        break
            return results

    def add_entry(self, entry: KnowledgeEntry) -> str:
        """添加知识条目

        Args:
            entry: 知识条目

        Returns:
            条目 ID
        """
        embedding = self._compute_embedding(entry.content or entry.title)

        # 写入类型对应的主表
        table = self._table_for_type(entry.type)
        self._insert_row(table, entry, embedding)

        # 同时在 knowledge 主表保留一份（便于跨类型搜索）
        if entry.type != "tech_doc":
            main_table = _COLLECTION_TABLES[self.COLLECTION_KNOWLEDGE]
            self._insert_row(main_table, entry, embedding)

        self._conn.commit()
        logger.info("添加知识条目: %s (%s)", entry.id, entry.title)
        return entry.id

    def add_entries(self, entries: list[KnowledgeEntry]) -> list[str]:
        """批量添加知识条目

        Args:
            entries: 知识条目列表

        Returns:
            条目 ID 列表
        """
        ids = []
        for entry in entries:
            ids.append(self.add_entry(entry))
        return ids

    def update_entry(self, entry_id: str, entry: KnowledgeEntry):
        """更新知识条目

        Args:
            entry_id: 要更新的条目 ID
            entry: 新的知识条目数据
        """
        entry.updated_at = _now_iso()
        entry.id = entry_id
        self.add_entry(entry)

    def delete_entry(self, entry_id: str):
        """删除知识条目（从所有表中删除）"""
        for table_name in _COLLECTION_TABLES.values():
            self._delete_row(table_name, entry_id)
        self._conn.commit()
        logger.info("删除知识条目: %s", entry_id)

    def get_entry(self, entry_id: str) -> KnowledgeEntry | None:
        """按 ID 获取知识条目"""
        for table_name in _COLLECTION_TABLES.values():
            row = self._conn.execute(
                f"SELECT * FROM {table_name} WHERE id = ?", (entry_id,)
            ).fetchone()
            if row:
                return _row_to_entry(row)
        return None

    def search(
        self,
        query: str,
        module: str | None = None,
        entry_type: str | None = None,
        category: str | None = None,
        n_results: int = 5,
    ) -> list[KnowledgeEntry]:
        """语义搜索，支持按 module/type/category 过滤

        Args:
            query: 搜索查询文本
            module: 按模块过滤
            entry_type: 按类型过滤
            category: 按分类过滤
            n_results: 返回结果数量

        Returns:
            匹配的知识条目列表
        """
        query_vec = self._compute_embedding(query)
        table = _COLLECTION_TABLES[self.COLLECTION_KNOWLEDGE]
        return self._search_in_table(
            table, query_vec, query,
            module=module, entry_type=entry_type,
            category=category, n_results=n_results,
        )

    def search_by_tags(
        self,
        tags: list[str],
        module: str | None = None,
        n_results: int = 5,
    ) -> list[KnowledgeEntry]:
        """按标签搜索

        Args:
            tags: 标签列表
            module: 按模块过滤
            n_results: 返回结果数量

        Returns:
            匹配的知识条目列表
        """
        query = " ".join(tags)
        candidates = self.search(query=query, module=module, n_results=n_results * 3)

        # 过滤包含指定标签的条目
        matched = []
        tag_set = set(tags)
        for entry in candidates:
            if tag_set & set(entry.tags):
                matched.append(entry)
            if len(matched) >= n_results:
                break

        return matched

    def get_stats(self) -> dict[str, Any]:
        """统计信息"""
        stats: dict[str, Any] = {
            "total": 0,
            "by_module": {},
            "by_type": {},
            "by_source": {},
            "by_category": {},
            "collections": {},
        }

        for coll_name, table_name in _COLLECTION_TABLES.items():
            count = self._conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            stats["collections"][coll_name] = count
            stats["total"] += count

            if count == 0:
                continue

            rows = self._conn.execute(
                f"SELECT module, type, source, category FROM {table_name}"
            ).fetchall()
            for row in rows:
                stats["by_module"][row["module"]] = stats["by_module"].get(row["module"], 0) + 1
                stats["by_type"][row["type"]] = stats["by_type"].get(row["type"], 0) + 1
                stats["by_source"][row["source"]] = stats["by_source"].get(row["source"], 0) + 1
                stats["by_category"][row["category"]] = stats["by_category"].get(row["category"], 0) + 1

        return stats

    def get_module_entries(
        self,
        module: str,
        entry_type: str | None = None,
        limit: int = 50,
    ) -> list[KnowledgeEntry]:
        """获取模块的所有知识条目"""
        conditions = ["module = ?"]
        params: list[Any] = [module]
        if entry_type:
            conditions.append("type = ?")
            params.append(entry_type)

        where = " WHERE " + " AND ".join(conditions)
        rows = self._conn.execute(
            f"SELECT * FROM {_COLLECTION_TABLES[self.COLLECTION_KNOWLEDGE]}{where} LIMIT ?",
            params + [limit],
        ).fetchall()

        return [_row_to_entry(row) for row in rows]

    def get_recent_entries(
        self,
        days: int = 7,
        module: str | None = None,
        limit: int = 20,
    ) -> list[KnowledgeEntry]:
        """获取最近的知识条目"""
        conditions = ["updated_at >= ?"]
        params: list[Any] = [(datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")]

        if module:
            conditions.append("module = ?")
            params.append(module)

        where = " WHERE " + " AND ".join(conditions)
        rows = self._conn.execute(
            f"SELECT * FROM {_COLLECTION_TABLES[self.COLLECTION_KNOWLEDGE]}{where} ORDER BY updated_at DESC LIMIT ?",
            params + [limit * 5],
        ).fetchall()

        entries = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        for row in rows:
            updated_at = row["updated_at"] or ""
            try:
                dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue
            if dt >= cutoff:
                entries.append(_row_to_entry(row))
            if len(entries) >= limit:
                break

        return entries

    def cross_module_search(
        self,
        query: str,
        exclude_module: str | None = None,
        n_results: int = 3,
    ) -> list[KnowledgeEntry]:
        """跨模块知识检索"""
        query_vec = self._compute_embedding(query)
        table = _COLLECTION_TABLES[self.COLLECTION_KNOWLEDGE]

        conditions = []
        params: list[Any] = []
        if exclude_module:
            conditions.append("module != ?")
            params.append(exclude_module)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        rows = self._conn.execute(f"SELECT * FROM {table} {where}", params).fetchall()
        if not rows:
            return []

        if query_vec is not None:
            valid_rows = []
            embeddings = []
            for row in rows:
                if row["embedding"]:
                    valid_rows.append(row)
                    embeddings.append(_bytes_to_embedding(row["embedding"]))

            if not embeddings:
                return []

            emb_matrix = np.array(embeddings, dtype=np.float32)
            similarities = self._cosine_similarity(query_vec, emb_matrix)

            min_conf = self._config.retrieval.min_confidence
            results = []
            indices = np.argsort(similarities)[::-1]

            for idx in indices:
                sim = float(similarities[idx])
                if sim < min_conf:
                    continue
                entry = _row_to_entry(valid_rows[idx])
                entry.metadata["_similarity"] = round(sim, 4)
                results.append(entry)
                if len(results) >= n_results:
                    break
            return results
        else:
            return []

    def delete_module_entries(self, module: str):
        """删除模块的所有知识条目"""
        for table_name in _COLLECTION_TABLES.values():
            self._conn.execute(f"DELETE FROM {table_name} WHERE module = ?", (module,))
            count = self._conn.execute(f"SELECT changes()").fetchone()[0]
            if count > 0:
                logger.info("从 %s 删除模块 '%s' 的 %d 条记录", table_name, module, count)
        self._conn.commit()

    def close(self):
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __del__(self):
        self.close()
