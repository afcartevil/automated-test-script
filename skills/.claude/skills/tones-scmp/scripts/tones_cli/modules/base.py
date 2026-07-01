"""Base class for HAR-derived API modules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from tones_cli.http_client import TonesHttpClient


class ApiModule(ABC):
    """Each module wraps a set of related endpoints from one HAR capture."""

    name: str
    description: str

    def __init__(self, client: TonesHttpClient | None = None):
        self.client = client or TonesHttpClient()

    @abstractmethod
    def register_commands(self, subparsers) -> None:
        """Attach argparse subcommands to the CLI."""

    @staticmethod
    def unwrap(response: dict[str, Any]) -> Any:
        return response.get("data", response)
