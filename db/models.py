# -*- coding: utf-8 -*-
"""知识条目数据模型

纯 Python dataclass，支持 Markdown + YAML frontmatter 双向转换，
以及 ChromaDB metadata 格式转换。
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


# 合法的 type 值
VALID_TYPES = {
    "tech_doc", "experience_case", "analysis_log",
    "correction", "error_pattern",
}

# 合法的 category 值
VALID_CATEGORIES = {
    "bug_analysis", "code_adaptation", "version_adaptation",
    "carrier_porting", "architecture", "api_reference",
    "protocol", "vendor_guide",
}

# 合法的 source 值
VALID_SOURCES = {
    "manual_feed", "auto_captured", "evoskill_extracted", "source_analyzed",
}


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _generate_id(module: str, seq: int | None = None) -> str:
    """生成知识条目 ID: kb-{module}-{date}-{seq}"""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    if seq is None:
        seq = uuid.uuid4().int % 10000
    return f"kb-{module}-{date_str}-{seq:04d}"


@dataclass
class KnowledgeEntry:
    """知识条目数据模型"""

    id: str                              # kb-{module}-{date}-{seq}
    module: str                          # 模块名
    title: str                           # 标题
    type: str                            # tech_doc / experience_case / analysis_log / correction / error_pattern
    category: str                        # bug_analysis / code_adaptation / ...
    source: str                          # manual_feed / auto_captured / evoskill_extracted / source_analyzed
    created_at: str                      # ISO 8601
    updated_at: str
    author: str                          # owner-name / system
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.80            # 0.0-1.0
    content: str = ""                    # Markdown 正文
    metadata: dict[str, Any] = field(default_factory=dict)
    referenced_by: list[str] = field(default_factory=list)

    def __post_init__(self):
        """校验字段合法性"""
        if self.type not in VALID_TYPES:
            raise ValueError(f"无效的 type: {self.type}，合法值: {VALID_TYPES}")
        if self.category not in VALID_CATEGORIES:
            raise ValueError(f"无效的 category: {self.category}，合法值: {VALID_CATEGORIES}")
        if self.source not in VALID_SOURCES:
            raise ValueError(f"无效的 source: {self.source}，合法值: {VALID_SOURCES}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence 必须在 0.0-1.0 之间，当前: {self.confidence}")

    def to_frontmatter(self) -> str:
        """生成 YAML frontmatter 格式字符串"""
        fm = {
            "id": self.id,
            "module": self.module,
            "title": self.title,
            "type": self.type,
            "category": self.category,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "author": self.author,
            "tags": self.tags,
            "confidence": self.confidence,
            "referenced_by": self.referenced_by,
        }
        # 合并非标准 metadata
        if self.metadata:
            fm["metadata"] = self.metadata

        lines = ["---"]
        lines.append(yaml.dump(fm, allow_unicode=True, default_flow_style=False).rstrip())
        lines.append("---")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """导出为 Markdown + YAML frontmatter"""
        parts = [self.to_frontmatter()]
        if self.content:
            parts.append("")
            parts.append(self.content)
        return "\n".join(parts)

    def to_chroma_metadata(self) -> dict[str, Any]:
        """转为 ChromaDB metadata

        ChromaDB metadata 值只支持 str/int/float/bool，
        list/dict 需要序列化为 JSON 字符串。
        """
        import json

        meta: dict[str, Any] = {
            "id": self.id,
            "module": self.module,
            "title": self.title,
            "type": self.type,
            "category": self.category,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "author": self.author,
            "confidence": self.confidence,
            "tags": json.dumps(self.tags, ensure_ascii=False),
            "referenced_by": json.dumps(self.referenced_by, ensure_ascii=False),
        }
        if self.metadata:
            meta["extra_metadata"] = json.dumps(self.metadata, ensure_ascii=False)
        return meta

    @classmethod
    def from_markdown(cls, filepath: str | Path) -> "KnowledgeEntry":
        """从 Markdown + YAML frontmatter 解析知识条目

        Args:
            filepath: Markdown 文件路径

        Returns:
            KnowledgeEntry 实例

        Raises:
            ValueError: frontmatter 格式错误
            FileNotFoundError: 文件不存在
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"文件不存在: {filepath}")

        text = filepath.read_text(encoding="utf-8")

        # 解析 YAML frontmatter
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
        if not match:
            raise ValueError(f"未找到有效的 YAML frontmatter: {filepath}")

        fm_str = match.group(1)
        content = match.group(2)

        try:
            fm = yaml.safe_load(fm_str)
        except yaml.YAMLError as e:
            raise ValueError(f"YAML 解析错误: {filepath}: {e}") from e

        if not isinstance(fm, dict):
            raise ValueError(f"frontmatter 必须是 YAML 映射: {filepath}")

        # 提取 metadata 子字段
        extra_metadata = fm.pop("metadata", {}) or {}

        # 解析 JSON 字符串字段
        import json

        tags = fm.get("tags", [])
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except json.JSONDecodeError:
                tags = [t.strip() for t in tags.split(",") if t.strip()]

        referenced_by = fm.get("referenced_by", [])
        if isinstance(referenced_by, str):
            try:
                referenced_by = json.loads(referenced_by)
            except json.JSONDecodeError:
                referenced_by = []

        return cls(
            id=fm.get("id", _generate_id(fm.get("module", "unknown"))),
            module=fm.get("module", "unknown"),
            title=fm.get("title", filepath.stem),
            type=fm.get("type", "tech_doc"),
            category=fm.get("category", "api_reference"),
            source=fm.get("source", "manual_feed"),
            created_at=fm.get("created_at", _now_iso()),
            updated_at=fm.get("updated_at", _now_iso()),
            author=fm.get("author", "system"),
            tags=tags,
            confidence=float(fm.get("confidence", 0.80)),
            content=content.strip(),
            metadata=extra_metadata if isinstance(extra_metadata, dict) else {},
            referenced_by=referenced_by,
        )

    @classmethod
    def create(
        cls,
        module: str,
        title: str,
        entry_type: str,
        category: str,
        content: str = "",
        source: str = "manual_feed",
        author: str = "system",
        tags: list[str] | None = None,
        confidence: float = 0.80,
        metadata: dict[str, Any] | None = None,
    ) -> "KnowledgeEntry":
        """创建新知识条目的便捷方法"""
        now = _now_iso()
        entry_id = _generate_id(module)
        return cls(
            id=entry_id,
            module=module,
            title=title,
            type=entry_type,
            category=category,
            source=source,
            created_at=now,
            updated_at=now,
            author=author,
            tags=tags or [],
            confidence=confidence,
            content=content,
            metadata=metadata or {},
            referenced_by=[],
        )
