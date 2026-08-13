# Modem Tool Automation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为通信/Modem 专业平台工具建立一条可批处理、可降级、可统一输出的自动解析基础链路，并在当前工作区起一套可继续扩展的 Python 骨架。

**Architecture:** 采用“输入编排 + 工具适配层 + 统一结果模型 + 报告输出层”的分层方案。首版不直接替代厂商工具，而是优先封装工具调用、标准化结果、对齐 Skill 的降级输出规范，并通过干跑模式（dry-run）保证在缺少专有工具时也能输出可交接结果。

**Tech Stack:** Python 3.x、标准库 `dataclasses/json/pathlib/subprocess/unittest`、Markdown 文档。

---

### Task 1: 设计文档定型

**Files:**
- Create: `android-comm-overseas-support-skill/docs/modem-tool-automation-design.md`
- Reference: `android-comm-overseas-support-skill/docs/skill-technical-design.md`
- Reference: `android-comm-overseas-support-skill/references/stability-analysis.md`
- Reference: `android-comm-overseas-support-skill/references/log-collection.md`

**Step 1: 明确目标边界**
- 说明为什么不直接替代厂商工具，而是优先封装。
- 说明首版支持的对象：MTK/logel 风格工具适配、统一 JSON、Markdown 报告、dry-run 降级输出。

**Step 2: 固化模块划分**
- 输入接入层
- 平台工具适配层
- 批处理调度层
- 标准化结果层
- Skill/报告输出层

**Step 3: 固化关键接口**
- `ParseJob`
- `ToolAdapter`
- `ParseResult`
- `MarkdownReporter`

**Step 4: 补失败/降级路径**
- 工具不存在
- 符号文件缺失
- 平台无法识别
- 结果不足以得出可靠结论

---

### Task 2: 先写失败测试，再补最小骨架

**Files:**
- Create: `tests/test_modem_auto_parser.py`
- Create: `tools/__init__.py`
- Create: `tools/modem_auto_parser/__init__.py`
- Create: `tools/modem_auto_parser/models.py`
- Create: `tools/modem_auto_parser/adapters/__init__.py`
- Create: `tools/modem_auto_parser/adapters/base.py`
- Create: `tools/modem_auto_parser/adapters/mtk_logel.py`
- Create: `tools/modem_auto_parser/registry.py`
- Create: `tools/modem_auto_parser/orchestrator.py`
- Create: `tools/modem_auto_parser/reporter.py`

**Step 1: 写失败测试**
```python
import unittest
from pathlib import Path

from tools.modem_auto_parser.models import ParseJob
from tools.modem_auto_parser.orchestrator import ParserOrchestrator
from tools.modem_auto_parser.registry import AdapterRegistry
from tools.modem_auto_parser.reporter import MarkdownReporter


class ModemAutoParserTests(unittest.TestCase):
    def test_registry_selects_mtk_adapter_for_dmp_job(self):
        job = ParseJob(
            job_id="job-001",
            platform="mtk",
            domain="stability",
            input_root=Path("sample"),
            files=[Path("sample/crash.dmp")],
        )
        registry = AdapterRegistry.default()
        adapter = registry.pick(job)
        self.assertEqual(adapter.tool_name, "logel")

    def test_orchestrator_returns_degraded_result_without_tool_path(self):
        job = ParseJob(
            job_id="job-002",
            platform="mtk",
            domain="stability",
            input_root=Path("sample"),
            files=[Path("sample/crash.dmp"), Path("sample/__exp_main.txt")],
            metadata={"baseband_version": "MOLY.LR12A.R3"},
        )
        result = ParserOrchestrator(AdapterRegistry.default()).run(job)
        self.assertEqual(result.tool_status, "degraded")
        self.assertIn("tool_path", result.missing_evidence)
        self.assertEqual(result.next_owner, "Modem平台工具维护方")

    def test_markdown_report_contains_skill_sections(self):
        job = ParseJob(
            job_id="job-003",
            platform="mtk",
            domain="stability",
            input_root=Path("sample"),
            files=[Path("sample/crash.dmp")],
        )
        result = ParserOrchestrator(AdapterRegistry.default()).run(job)
        report = MarkdownReporter().render(job, result)
        self.assertIn("## Current Conclusion", report)
        self.assertIn("## Missing Evidence", report)
        self.assertIn("## Handover", report)
```

**Step 2: 运行测试确认失败**
Run: `py -m unittest tests.test_modem_auto_parser -v`
Expected: FAIL with `ModuleNotFoundError` or missing symbol errors because package not created yet.

**Step 3: 写最小实现**
- `models.py`：定义 `ParseJob`、`ParseResult`
- `base.py`：定义 `ToolAdapter` 抽象接口
- `mtk_logel.py`：实现 MTK/logel 占位适配器，未配置工具时返回 degraded 结果
- `registry.py`：注册并选择适配器
- `orchestrator.py`：串联 adapter 执行与标准化结果
- `reporter.py`：输出对齐 Skill 规范的 Markdown

**Step 4: 再次运行测试确认通过**
Run: `py -m unittest tests.test_modem_auto_parser -v`
Expected: PASS

---

### Task 3: CLI 与使用说明

**Files:**
- Create: `tools/modem_auto_parser/cli.py`
- Create: `tools/modem_auto_parser/README.md`

**Step 1: CLI 最小入口**
- 支持读取 JSON 任务描述
- 支持 `--format json|markdown`
- 默认使用 dry-run 可输出结果

**Step 2: 使用说明**
- 给出目录约定
- 给出样例任务 JSON
- 给出如何接入 logel/TNE 的说明
- 给出如何扩展新平台 adapter

**Step 3: 冒烟验证**
Run: `py -m tools.modem_auto_parser.cli --help`
Expected: 输出帮助信息，无异常。

---

### Task 4: 交付与后续扩展建议

**Files:**
- Modify: `android-comm-overseas-support-skill/docs/modem-tool-automation-design.md`
- Modify: `tools/modem_auto_parser/README.md`

**Step 1: 记录当前边界**
- 仅提供首版骨架，不包含真实厂商工具路径
- 真正投产前需要补 license、符号文件管理、执行机隔离与审计

**Step 2: 记录后续扩展顺序**
- 先接 MTK/logel
- 再接 TNE / SPRD / Qcom
- 再接规则引擎与 Skill 知识映射

**Step 3: 验证与交付**
Run:
- `py -m unittest tests.test_modem_auto_parser -v`
- `py -m tools.modem_auto_parser.cli --help`
Expected:
- 测试通过
- CLI 可启动
- 文档与代码路径一致
