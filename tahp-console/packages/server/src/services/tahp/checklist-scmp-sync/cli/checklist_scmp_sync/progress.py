from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import datetime
from typing import Any, TextIO

EventCallback = Callable[[dict[str, Any]], None]


def event_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def dumps_jsonl(event: dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"


def emit_jsonl(event: dict[str, Any]) -> None:
    sys.stdout.write(dumps_jsonl(event))
    sys.stdout.flush()


def make_event_callback(*, to_stdout: bool, log_fp: TextIO | None) -> EventCallback:
    def on_event(event: dict[str, Any]) -> None:
        line = dumps_jsonl(event)
        if to_stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
        if log_fp is not None:
            log_fp.write(line)
            log_fp.flush()

    return on_event


def emit(on_event: EventCallback | None, event: str, **fields: Any) -> None:
    if on_event is None:
        return
    payload = {"event": event, "ts": event_timestamp(), **fields}
    on_event(payload)
