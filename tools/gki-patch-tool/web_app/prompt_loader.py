"""Load and render LLM prompt templates from config/prompts/."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

from web_app.app_paths import bundle_root, install_root

_VAR_RE = re.compile(r"\{\{(\w+)\}\}")
_cache: Dict[str, str] = {}


def prompts_dir() -> Path:
    installed = install_root() / "config" / "prompts"
    if installed.is_dir():
        return installed
    return bundle_root() / "config" / "prompts"


def load_prompt(name: str, *, suffix: str = ".md") -> str:
    """Load a prompt template by name (supports subpaths like snippets/foo)."""
    rel = f"{name}{suffix}"
    for base in (install_root() / "config" / "prompts", bundle_root() / "config" / "prompts"):
        path = base / rel
        if path.is_file():
            mtime = path.stat().st_mtime
            cache_key = f"{path}:{mtime}"
            if cache_key in _cache:
                return _cache[cache_key]
            text = path.read_text(encoding="utf-8")
            _cache.clear()
            _cache[cache_key] = text
            return text
    raise FileNotFoundError(f"Prompt template not found: {rel}")


def render_prompt(
    name: str,
    variables: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> str:
    """Render a prompt template, replacing {{placeholders}} with provided values."""
    text = load_prompt(name)
    vars_map: Dict[str, Any] = {}
    if variables:
        vars_map.update(variables)
    vars_map.update(kwargs)

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = vars_map.get(key, "")
        return "" if value is None else str(value)

    return _VAR_RE.sub(_replace, text)
