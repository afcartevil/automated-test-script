"""flow/game：YAML 配规则，Python 做引擎。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from yaml_config import load_yaml_config


def load_reference_yaml(ref_dir: Path, filename: str) -> dict[str, Any]:
    return load_yaml_config(ref_dir / filename)


def load_keyword_patterns(ref_dir: Path) -> dict[str, Any]:
    data = load_reference_yaml(ref_dir, "keyword-patterns.yaml")
    return data if data else {"categories": {}}


def load_analysis_standards(ref_dir: Path, filename: str = "analysis-standards.yaml") -> dict[str, Any]:
    return load_reference_yaml(ref_dir, filename)


def threshold(standards: dict[str, Any], key: str, default: Any) -> Any:
    block = standards.get("thresholds") or {}
    if key in block:
        return block[key]
    return standards.get(key, default)


def evidence_cap(standards: dict[str, Any], default: int = 40) -> int:
    return int(threshold(standards, "evidence_cap", standards.get("evidence_cap", default)))
