# -*- coding: utf-8 -*-
"""知识库配置管理

支持从 knowledge-base/config.yaml 加载配置，
向量嵌入使用 onnxruntime + all-MiniLM-L6-v2 (384d)，
持久化存储使用 SQLite（WAL 模式）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _project_root() -> Path:
    """获取项目根目录（db/ 的上一级）"""
    return Path(__file__).resolve().parent.parent


@dataclass
class EmbeddingConfig:
    """向量嵌入配置"""
    model: str = "default"  # default = chromadb 内置 all-MiniLM-L6-v2
    model_name: str = ""    # 外部模型名称（当 model != default 时使用）
    device: str = "cpu"


@dataclass
class RetrievalConfig:
    """检索配置"""
    default_top_k: int = 5
    min_confidence: float = 0.05  # 低阈值以支持跨语言检索
    cross_module_top_k: int = 3
    rerank: bool = False


@dataclass
class AutoCaptureConfig:
    """自动捕获配置"""
    # Bug 分析
    bug_min_confidence: float = 0.80
    bug_gate_results: list[str] = field(default_factory=lambda: ["PASS", "WARNING"])
    # 纠正记录
    corrections_always: bool = True
    # 适配记录
    adaptation_compile_pass: bool = True
    adaptation_regression_pass: bool = True
    # EvoSkill 提取
    evoskill_min_score_improvement: float = 0.05


@dataclass
class ConstraintExtractionConfig:
    """约束提取配置"""
    auto_trigger: bool = True
    owner_review_required: bool = True
    confidence_threshold: float = 0.75


@dataclass
class KnowledgeBaseConfig:
    """知识库全局配置"""

    # 目录配置
    data_dir: Path = field(default_factory=lambda: _project_root() / "knowledge-base")
    chroma_persist_dir: Path = field(default_factory=lambda: _project_root() / ".chroma_db")

    # 数据库类型
    db_type: str = "chromadb"

    # 嵌入配置
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)

    # 检索配置
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)

    # 自动捕获配置
    auto_capture: AutoCaptureConfig = field(default_factory=AutoCaptureConfig)

    # 约束提取配置
    constraint_extraction: ConstraintExtractionConfig = field(default_factory=ConstraintExtractionConfig)

    # 来源开关
    sources: dict[str, bool] = field(default_factory=lambda: {
        "manual_feed": True,
        "auto_capture": True,
        "cross_module_sync": True,
    })

    @classmethod
    def from_yaml(cls, filepath: str | Path | None = None) -> "KnowledgeBaseConfig":
        """从 YAML 文件加载配置

        Args:
            filepath: 配置文件路径，默认为 knowledge-base/config.yaml
        """
        if filepath is None:
            filepath = cls().data_dir / "config.yaml"
        filepath = Path(filepath)

        config = cls()

        if not filepath.exists():
            return config

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            return config

        # 解析 database 部分
        db_data = data.get("database", {})
        if "persist_dir" in db_data:
            config.db_type = db_data.get("type", config.db_type)
            config.chroma_persist_dir = _project_root() / db_data["persist_dir"]

        # 解析 embedding
        emb_data = data.get("embedding", db_data)
        if "embedding_model" in db_data:
            config.embedding.model = db_data["embedding_model"]

        # 解析 retrieval
        ret_data = data.get("retrieval", {})
        if ret_data:
            config.retrieval.default_top_k = ret_data.get("default_top_k", config.retrieval.default_top_k)
            config.retrieval.min_confidence = ret_data.get("min_confidence", config.retrieval.min_confidence)
            config.retrieval.cross_module_top_k = ret_data.get("cross_module_top_k", config.retrieval.cross_module_top_k)
            config.retrieval.rerank = ret_data.get("rerank", config.retrieval.rerank)

        # 解析 sources
        src_data = data.get("sources", {})
        if src_data:
            config.sources = {k: bool(v) for k, v in src_data.items()}

        # 解析 auto_capture
        ac_data = data.get("auto_capture", {})
        if ac_data:
            ba = ac_data.get("bug_analysis", {})
            config.auto_capture.bug_min_confidence = ba.get("min_confidence", config.auto_capture.bug_min_confidence)
            config.auto_capture.bug_gate_results = ba.get("gate_result", config.auto_capture.bug_gate_results)
            corr = ac_data.get("corrections", {})
            config.auto_capture.corrections_always = corr.get("always", config.auto_capture.corrections_always)
            adapt = ac_data.get("adaptation", {})
            config.auto_capture.adaptation_compile_pass = adapt.get("compile_pass", config.auto_capture.adaptation_compile_pass)
            config.auto_capture.adaptation_regression_pass = adapt.get("regression_pass", config.auto_capture.adaptation_regression_pass)
            evo = ac_data.get("evoskill", {})
            config.auto_capture.evoskill_min_score_improvement = evo.get("min_score_improvement", config.auto_capture.evoskill_min_score_improvement)

        # 解析 constraint_extraction
        ce_data = data.get("constraint_extraction", {})
        if ce_data:
            config.constraint_extraction.auto_trigger = ce_data.get("auto_trigger", config.constraint_extraction.auto_trigger)
            config.constraint_extraction.owner_review_required = ce_data.get("owner_review_required", config.constraint_extraction.owner_review_required)
            config.constraint_extraction.confidence_threshold = ce_data.get("confidence_threshold", config.constraint_extraction.confidence_threshold)

        return config

    def to_dict(self) -> dict[str, Any]:
        """导出为字典"""
        return {
            "data_dir": str(self.data_dir),
            "chroma_persist_dir": str(self.chroma_persist_dir),
            "db_type": self.db_type,
            "embedding": {
                "model": self.embedding.model,
                "model_name": self.embedding.model_name,
                "device": self.embedding.device,
            },
            "retrieval": {
                "default_top_k": self.retrieval.default_top_k,
                "min_confidence": self.retrieval.min_confidence,
                "cross_module_top_k": self.retrieval.cross_module_top_k,
                "rerank": self.retrieval.rerank,
            },
            "sources": self.sources,
        }
