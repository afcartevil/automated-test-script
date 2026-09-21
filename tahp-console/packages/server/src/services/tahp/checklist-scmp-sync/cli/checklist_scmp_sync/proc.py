from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any


ROW_PREFIX = re.compile(r"^\[row=(\d+)\]\s?")


def resolve_executable(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt":
        for suffix in (".cmd", ".exe", ".bat"):
            found = shutil.which(name + suffix)
            if found:
                return found
    raise FileNotFoundError(f"找不到可执行文件: {name}")


def python_executable() -> str:
    return sys.executable or resolve_executable("python")


class CommandError(RuntimeError):
    def __init__(self, message: str, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


def run_json_command(
    args: list[str],
    *,
    input_text: str | None = None,
    timeout: int = 180,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    completed = subprocess.run(
        args,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
        check=False,
    )
    payload = _extract_json(completed.stdout)
    if completed.returncode != 0:
        message = None
        if isinstance(payload, dict):
            err = payload.get("error") or {}
            message = err.get("message") or payload.get("msg")
        raise CommandError(
            message or (completed.stderr.strip() or f"command failed: {args}"),
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    if not isinstance(payload, dict):
        raise CommandError(
            f"command did not return JSON object: {args}",
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    return payload


def _extract_json(stdout: str) -> Any:
    text = (stdout or "").strip()
    if not text:
        return {}
    start = text.find("{")
    if start < 0:
        start = text.find("[")
    if start < 0:
        raise CommandError("no JSON in command output", stdout=stdout)
    blob = text[start:]
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(blob)
        return obj


def parse_annotated_csv(annotated_csv: str) -> list[tuple[int, list[str]]]:
    if not annotated_csv:
        return []
    reader = csv.reader(io.StringIO(annotated_csv))
    rows: list[tuple[int, list[str]]] = []
    for record in reader:
        if not record:
            continue
        match = ROW_PREFIX.match(record[0] or "")
        if match is None:
            continue
        record[0] = ROW_PREFIX.sub("", record[0], count=1)
        rows.append((int(match.group(1)), record))
    return rows
