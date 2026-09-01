"""jira-ops log download must wait until the CLI process exits."""

import json
from unittest.mock import MagicMock, patch

from tools.log_download_wait import (
    is_log_download_command,
    is_log_download_progress_line,
    is_log_download_tool_call,
)
from tests.tools.test_terminal_foreground_timeout_cap import _make_env_config


def test_detects_prepare_logs_and_siblings():
    assert is_log_download_command(
        'cd jira-ops && python scripts/api_jira.py prepare-logs --issue X-1'
    )
    assert is_log_download_command("python scripts/api_jira.py download-logs --issue X-1")
    assert is_log_download_command("python scripts/api_jira.py download-box --url https://sgbox")
    assert not is_log_download_command("python scripts/api_jira.py get --issue X-1")
    assert not is_log_download_command("echo hello")
    assert not is_log_download_command(None)


def test_only_terminal_tool_calls_qualify():
    args = {"command": "python scripts/api_jira.py prepare-logs --issue X-1", "timeout": 300}
    assert is_log_download_tool_call("terminal", args)
    assert not is_log_download_tool_call("web_extract", args)
    assert not is_log_download_tool_call("terminal", {"command": "ls"})


def test_foreground_log_download_ignores_timeout_cap_and_waits_until_exit():
    from tools.terminal_tool import terminal_tool, FOREGROUND_MAX_TIMEOUT

    mock_env = MagicMock()
    mock_env.execute.return_value = {"output": '{"ok":true}', "returncode": 0}

    with patch("tools.terminal_tool._get_env_config", return_value=_make_env_config()), \
         patch("tools.terminal_tool._start_cleanup_thread"), \
         patch("tools.terminal_tool._active_environments", {"default": mock_env}), \
         patch("tools.terminal_tool._last_activity", {"default": 0}), \
         patch("tools.terminal_tool._check_all_guards", return_value={"approved": True}):
        result = json.loads(terminal_tool(
            command="python scripts/api_jira.py prepare-logs --issue X-1",
            timeout=FOREGROUND_MAX_TIMEOUT + 999,
        ))

    assert result.get("error") in (None, "")
    kwargs = mock_env.execute.call_args.kwargs
    assert kwargs.get("wait_until_complete") is True


def test_detects_download_progress_lines():
    assert is_log_download_progress_line(
        "下载进度: 24.1% (1.65 GB/6.84 GB) 速度: 870.3 KB/s 剩余: 1h 42m"
    )
    assert is_log_download_progress_line("开始流式下载...")
    assert is_log_download_progress_line("[文件] X1102D-16.3.0.147.zip (6.84 GB)")
    assert not is_log_download_progress_line("ls -la /tmp")
    assert not is_log_download_progress_line("")
    assert not is_log_download_progress_line(None)


def test_maybe_emit_output_progress_dedupes_same_line():
    from tools.environments.base import (
        _BoundedOutputCollector,
        maybe_emit_output_progress,
        set_output_progress_callback,
    )

    collector = _BoundedOutputCollector(1_000)
    collector.append(
        "\r下载进度: 24.1% (1.65 GB/6.84 GB) 速度: 870 KB/s 剩余: 1h    "
    )
    seen: list[str] = []
    set_output_progress_callback(seen.append)
    try:
        state = {"last_progress_emit": 0.0, "progress_interval": 0.0}
        maybe_emit_output_progress(collector, state)
        maybe_emit_output_progress(collector, state)
        assert len(seen) == 1
        assert "24.1%" in seen[0]
        collector.append("\nunrelated stdout without progress keywords\n")
        maybe_emit_output_progress(collector, state)
        assert len(seen) == 1
    finally:
        set_output_progress_callback(None)
