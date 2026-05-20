# TAHP — Claude Code 配置

## 项目
TECNO AI Harness Platform (TAHP) — 传音Android底软集成部双引擎AI平台。

## 首先阅读
执行任何任务前，必须先阅读 AGENTS.md 了解项目导航和约束体系。

---

## 架构分层

```
AI Agent (Claude Code)
    │
    ▼
MCP Protocol ── server.py (9个Tool注册 + 分发)
    │
    ├── core/     ── execute/status/correct/gate_check/query_knowledge
    ├── adapters/ ── ToolRegistry → 7个现有tools/封装
    └── progress/ ── TaskTracker + ProgressEmitter
    │
    ▼
constraints/  ── 业务约束 (module.yaml + domain yaml)
playbooks/    ── 执行编排
knowledge-base/ ── 语义知识库
```

### 模块与约束域

| 模块 | Domain | 约束文件 |
|------|--------|----------|
| telephony (通信) | bug_analysis / code_adaptation / version_adaptation / carrier_porting | constraints/telephony/ |
| kernel-driver (内核驱动) | bug_analysis / code_adaptation | constraints/kernel-driver/ |
| power-mgmt (功耗管理) | bug_analysis | constraints/power-mgmt/ |
| shared (共享) | code_adaptation | constraints/shared/ |

---

## 核心规则

1. **Scope锁定**: 每次操作前先读取对应模块约束文件，只操作 scope.includes 中的路径
2. **防幻觉**: 所有代码产出必须有据可查，禁止编造
3. **一次性正确**: 分析→计划→确认→修改→验证，不允许试错式迭代
4. **最小变更**: 只修改与任务直接相关的代码

### 安全红线（P0阻塞）

1. 不修改 scope.excludes 中列出的任何文件
2. 不在未验证API存在性的情况下生成代码
3. 不硬编码密钥/Token/设备标识
4. 涉及安全相关的Bug必须标记为Critical
5. 所有代码修改必须在编译门禁中通过

---

## 验证命令

```bash
# 约束校验
python scripts/validate_constraints.py constraints/ --recursive --strict

# P0门禁（单模块）
python scripts/gate_check.py constraints/telephony/ --level P0

# 全部测试
python -m pytest tahp-mcp-server/ scripts/tests/ -v

# MCP Server 测试
python -m pytest tahp-mcp-server/test_server.py -v

# 评测（需先填充eval用例）
python scripts/evaluate.py skills/<skill>/ constraints/<module>/eval-data/

# Pre-commit检查
powershell -File scripts/pre-commit-check.ps1
```

---

## 扩展指南

### 如何新增 MCP 工具
1. 在 `tahp-mcp-server/handlers/` 下创建新 Handler 文件，实现 `IToolHandler` 协议
2. 在 `tahp-mcp-server/server.py` 的 `_list_tools()` 中添加工具定义
3. 在 `tahp-mcp-server/server.py` 的 `_dispatch_tool()` 中注册 handler
4. 在 `tahp-mcp-server/test_server.py` 中添加对应测试

### 如何新增模块
```bash
python scripts/init_module.py --module your-module --owner your-name
```
然后编辑生成的 `constraints/<module>/module.yaml` 填写 scope 信息。

### 如何新增约束域
1. 在 `constraints/<module>/` 下添加 domain yaml（如 `bug-analysis.yaml`）
2. 在 `playbooks/` 下添加对应的 pipeline yaml
3. 在 `templates/module-template/` 更新模板

---

## 质量门禁体系

| 级别 | 门禁 | 失败处理 |
|------|------|------------|
| P0 | 编译通过 + Scope合规 + 安全红线 + API真实性 | BLOCK (exit 1) |
| P1 | 编码风格 + Lint + 废弃API + TODO关联 | WARNING (exit 2) |
| P2 | 代码复杂度 + 重复率 + 注释覆盖 | 记录 |

---

## MCP工具列表

| 工具名 | 用途 |
|--------|------|
| tahp_execute | 执行开发任务 |
| tahp_status | 查询任务状态 |
| tahp_correct | 纠偏正在执行的任务 |
| tahp_gate_check | 质量门禁检查 |
| tahp_list_tasks | 列出所有任务 |
| tahp_query_knowledge | 查询知识库 |
| tahp_code_review | 代码审查 |
| tahp_analyze_log | 日志分析 |
| tahp_analyze_bug | Bug分析 |

tools/ 目录下封装了7个底层工具:
android-log-analyzer, aosp-diff-analyzer, patch-generator, api-migration-db, build-verifier, regression-test-runner, code-review-checker

---

## 文件操作范围
- 可操作: constraints/, skills/, playbooks/, scripts/, docs/, reports/, knowledge-base/
- 禁止: .git/, .env, 其他模块约束文件（除非显式授权）

---

## 输出格式
- Bug分析报告: TAHP-AI代码生成约束规范 §5.1
- 代码修改: TAHP-AI代码生成约束规范 §5.2
- 适配报告: TAHP-版本适配约束规范 §7.3

---

## 已知技术债务
- eval用例仅telephony模块有3个基准用例，kernel-driver和power-mgmt待补充
- server.py 工具分发为 if-elif 链，待重构为 handler 注册模式
- 知识库基准数据（telephony RILJ错误模式等）待填充
- EvoSkill进化脚本未激活，评测闭环待建立
