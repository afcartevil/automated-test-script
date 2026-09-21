from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .proc import python_executable, run_json_command
from .resolve import SpecMatch, pick_unique_spec


def find_tones_cli(explicit: str | None = None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise FileNotFoundError(f"tones-scmp CLI 不存在: {path}")
        return path
    env_path = os.environ.get("TONES_SCMP_CLI")
    if env_path:
        path = Path(env_path)
        if path.is_file():
            return path
    local_app = os.environ.get("LOCALAPPDATA") or ""
    candidates = [
        Path.home() / ".cursor" / "skills" / "tones-scmp" / "scripts" / "run.py",
        Path(local_app) / "hermes" / "skills" / "tones-scmp" / "scripts" / "run.py",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "找不到 tones-scmp scripts/run.py，请设置环境变量 TONES_SCMP_CLI"
    )


class ScmpClient:
    def __init__(self, tones_cli: Path):
        self.tones_cli = tones_cli

    def _run(self, extra: list[str], timeout: int = 180) -> dict[str, Any]:
        return run_json_command(
            [python_executable(), str(self.tones_cli), "--json", *extra],
            timeout=timeout,
        )

    def login(self) -> None:
        payload = self._run(["auth", "login"])
        if str(payload.get("code")) not in {"0000", "0"}:
            raise RuntimeError(payload.get("msg") or "tones-scmp 登录失败")

    def candidates(self, project: str) -> list[dict[str, Any]]:
        payload = self._run(["scmp", "spd", "candidates", "--name", project])
        return list(payload.get("data") or [])

    def spec_list(self, project_bid: str) -> list[dict[str, Any]]:
        payload = self._run(
            ["scmp", "spd", "spec", "list", "--project-bid", project_bid]
        )
        return list(payload.get("data") or [])

    def market_support(self, spec_bid: str) -> dict[str, dict[str, str]]:
        payload = self._run(
            [
                "scmp",
                "spd",
                "market-support",
                "--spec-bid",
                spec_bid,
                "--include-google",
                "false",
                "--size",
                "99999",
            ],
            timeout=300,
        )
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            return {}
        return {
            str(code): {str(market): str(value) for market, value in (markets or {}).items()}
            for code, markets in data.items()
        }

    def resolve_spec(self, project: str, tos_version: str) -> SpecMatch:
        candidates = self.candidates(project)
        if not candidates:
            raise ValueError(f"SCMP 未找到项目候选: {project}")
        enriched = []
        for item in candidates:
            bid = item.get("bid")
            specs = self.spec_list(str(bid)) if bid else []
            enriched.append({**item, "specs": specs})
        return pick_unique_spec(enriched, tos_version)
