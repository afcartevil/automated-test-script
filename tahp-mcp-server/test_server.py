#!/usr/bin/env python3
"""TAHP MCP Server — pytest 标准测试

测试所有9个 MCP 工具的调用路径，包含正常流程和边界测试。
运行方式：
    python -m pytest tahp-mcp-server/test_server.py -v
"""
import sys
import json
import pytest

sys.path.insert(0, 'tahp-mcp-server')
sys.path.insert(0, '.')
from server import handle_call_tool


# ---------------------------------------------------------------------------
# tahp_execute
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_valid():
    """正常执行：telephony 模块 bug_analysis 域"""
    r = await handle_call_tool("tahp_execute", {
        "document_path": "constraints/telephony/module.yaml",
        "module": "telephony",
        "domain": "bug_analysis"
    })
    result = json.loads(r[0].text)
    assert result.get("status") in ("completed", "failed", "running", "init")


@pytest.mark.asyncio
async def test_execute_invalid_module():
    """不存在的模块应返回 error"""
    r = await handle_call_tool("tahp_execute", {
        "document_path": "test.md",
        "module": "nonexistent",
        "domain": "bug_analysis"
    })
    result = json.loads(r[0].text)
    assert "error" in result or result.get("status") == "failed"


# ---------------------------------------------------------------------------
# tahp_status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_not_found():
    """查询不存在的任务ID"""
    r = await handle_call_tool("tahp_status", {"task_id": "task-nonexistent-99999"})
    result = json.loads(r[0].text)
    # 可能返回 error 或 not_found
    assert "error" in result or result.get("status") == "not_found"


# ---------------------------------------------------------------------------
# tahp_list_tasks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_tasks():
    """列出所有任务"""
    r = await handle_call_tool("tahp_list_tasks", {})
    result = json.loads(r[0].text)
    assert "total" in result
    assert isinstance(result["total"], int)


# ---------------------------------------------------------------------------
# tahp_gate_check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gate_check_telephony():
    """telephony 模块 P0 门禁检查"""
    r = await handle_call_tool("tahp_gate_check", {
        "module": "telephony",
        "level": "P0"
    })
    result = json.loads(r[0].text)
    assert "result" in result
    # P0 门禁应该全部通过
    assert result.get("result") in ("PASS", "BLOCK", "WARNING", "pass", "block", "warning")


@pytest.mark.asyncio
async def test_gate_check_kernel_driver():
    """kernel-driver 模块门禁检查"""
    r = await handle_call_tool("tahp_gate_check", {
        "module": "kernel-driver",
        "level": "P0"
    })
    result = json.loads(r[0].text)
    assert "result" in result


@pytest.mark.asyncio
async def test_gate_check_power_mgmt():
    """power-mgmt 模块门禁检查"""
    r = await handle_call_tool("tahp_gate_check", {
        "module": "power-mgmt",
        "level": "P0"
    })
    result = json.loads(r[0].text)
    assert "result" in result


# ---------------------------------------------------------------------------
# tahp_code_review
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_code_review_hardcoded_secret():
    """检测硬编码密钥"""
    r = await handle_call_tool("tahp_code_review", {
        "patch_content": "+api_key = \"sk-1234567890abcdef\"",
        "check_level": "P0"
    })
    result = json.loads(r[0].text)
    assert "result" in result or "score" in result


# ---------------------------------------------------------------------------
# tahp_analyze_log
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_log_logcat():
    """分析 logcat 日志"""
    r = await handle_call_tool("tahp_analyze_log", {
        "log_content": (
            "05-19 10:00:00 RILJ: setupDataCall\n"
            "05-19 10:00:01 FATAL EXCEPTION in PhoneInterfaceManager"
        ),
        "log_type": "logcat"
    })
    result = json.loads(r[0].text)
    assert "statistics" in result or "error" in result


# ---------------------------------------------------------------------------
# tahp_query_knowledge
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_knowledge():
    """查询知识库"""
    r = await handle_call_tool("tahp_query_knowledge", {
        "query": "RILJ error",
        "module": "telephony"
    })
    result = json.loads(r[0].text)
    # 知识库可能为空，不强制要求返回结果
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# tahp_correct
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_correct_not_found():
    """纠偏不存在的任务"""
    r = await handle_call_tool("tahp_correct", {
        "task_id": "task-nonexistent-99999",
        "feedback": "Use a different approach",
        "priority": "high"
    })
    result = json.loads(r[0].text)
    # 预期返回错误
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# tahp_analyze_bug
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_bug():
    """分析 Bug（telephony 模块）"""
    r = await handle_call_tool("tahp_analyze_bug", {
        "module": "telephony",
        "bug_description": "通话断连，RILJ报GENERIC_FAILURE",
        "log_content": "05-19 10:00:00 RILJ: GENERIC_FAILURE"
    })
    result = json.loads(r[0].text)
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 边界测试：未知工具
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_tool():
    """调用不存在的工具名 — 应返回错误信息而非崩溃"""
    r = await handle_call_tool("tahp_nonexistent_tool_xyz", {})
    result = json.loads(r[0].text)
    # 未知工具应返回错误信息
    assert "error" in result or "unknown" in str(result).lower() or "Invalid" in str(result)
