# TAHP 工程完整解析

> **TECNO AI Harness Platform** — 双引擎AI平台用于Android底软集成  
> 版本：Phase 0 | 最后更新：2026-05-18

---

## 目录

1. [项目概述](#1-项目概述)
2. [整体工程架构](#2-整体工程架构)
3. [目录结构与文件作用](#3-目录结构与文件作用)
4. [核心机制详解](#4-核心机制详解)
5. [新手使用指南](#5-新手使用指南)
6. [落地场景与实际用例](#6-落地场景与实际用例)
7. [与传统方式对比](#7-与传统方式对比)
8. [常见问题 FAQ](#8-常见问题-faq)

---

## 1. 项目概述

### 1.1 什么是 TAHP？

**TAHP（TECNO AI Harness Platform）** 是一个基于 **Agent = Model + Harness** 范式的双引擎 AI 辅助平台，专为 Android 底层软件集成场景设计。

**核心理念**：让 AI 在**约束框架（Harness）**内工作，而不是自由发挥。通过预定义的约束规范、Skill 引擎和执行编排，实现可预测、可验证、可迭代的 AI 辅助开发。

### 1.2 解决什么问题？

| 痛点 | TAHP 解决方案 |
|------|--------------|
| AI 生成代码质量不稳定 | 约束框架 + 质量门禁 |
| 缺乏领域知识注入 | 约束文件 + Skill 引擎 |
| 无法验证 AI 输出 | 评估体系 + 自动迭代 |
| 多模块协同困难 | 统一配置 + 执行编排 |

### 1.3 核心特性

- **双引擎**：诊断引擎（Bug 分析）+ 适配引擎（版本升级/特性移植/运营商适配）
- **三级策略**：全自动（>95%）/ 半自动（70-95%）/ 人工（<70%）
- **质量门禁**：P0（BLOCK）/ P1（WARNING）/ P2（RECORD）
- **EvoSkill 进化**：自动迭代优化 Skill，提升准确率
- **零服务器成本**：纯本地执行，基于 Git 版本控制

---

## 2. 整体工程架构

### 2.1 四层架构

```
+-------------------------------------------------------+
|              Evaluation & Iteration                     |
|       评估与迭代层：质量门禁 / EvoSkill进化              |
+-------------------------------------------------------+
|              Execution Orchestration                    |
|        执行编排层：Playbook流水线 / 分级策略              |
+-------------------------------------------------------+
|                  Skill Engine                           |
|          Skill引擎层：诊断引擎 / 适配引擎                 |
+-------------------------------------------------------+
|              Constraint Management                      |
|          约束管理层：模块约束 / 共享约束                  |
+-------------------------------------------------------+
                           |
                           v
                  MCP Tools（外部工具集成）
```

### 2.2 架构分层说明

#### 第一层：Constraint Management（约束管理层）
- **作用**：定义 AI 工作的边界和规则
- **核心文件**：`constraints/<module>/module.yaml`、`constraints/<module>/<scenario>.yaml`
- **共享约束**：`constraints/shared/` 下的跨模块通用规则

#### 第二层：Skill Engine（Skill 引擎层）
- **作用**：将约束转化为 AI 可执行的 Skill
- **双引擎**：
  - 诊断引擎：`skills/*/telephony-bug-analyzer/`
  - 适配引擎：`skills/*/telephony-version-adapter/`、`carrier-porting-assistant/`
- **Skill 结构**：`SKILL.md`（协议文档）+ `examples/`（参考案例）

#### 第三层：Execution Orchestration（执行编排层）
- **作用**：定义 AI 执行流程，实现分级策略
- **核心文件**：`playbooks/*.yaml`（流水线定义）
- **分级策略**：全自动 / 半自动 / 人工

#### 第四层：Evaluation & Iteration（评估与迭代层）
- **作用**：验证 AI 输出质量，驱动 Skill 自动进化
- **核心机制**：质量门禁（P0/P1/P2）、EvoSkill 进化引擎
- **配置文件**：`.evoskill/config.toml`

### 2.3 数据流向

```
用户输入（Bug日志 / 版本差异 / 运营商需求）
                    |
                    v
          +-----------------------+
          |  约束管理层（读取）    |
          +----------+------------+
                     | 约束注入
                     v
          +-----------------------+
          |  Skill引擎层（执行）  |
          +----------+------------+
                     | AI生成结果
                     v
          +-----------------------+
          |  质量门禁（验证）      |
          +----------+------------+
                     |
        +------------+------------+
        |                         |
    通过（P1/P2）            未通过（P0）
        |                         |
        v                         v
  提交/交付               EvoSkill进化 -> 重新执行
```

---

## 3. 目录结构与文件作用

### 3.1 根目录文件

| 文件 | 作用 |
|------|------|
| `README.md` | 项目说明、快速上手指南 |
| `CLAUDE.md` | Claude Code 项目指令文件（AI 行为约束） |
| `AGENTS.md` | Agent 角色定义与协作规范 |
| `config/project.yaml` | 项目全局配置（模块、场景、MCP工具） |
| `.gitlab-ci.yml` | GitLab CI/CD 流水线配置 |
| `.evoskill/config.toml` | EvoSkill 进化引擎配置 |

### 3.2 constraints/ 约束文件目录

```
constraints/
+-- shared/                          # 跨模块共享约束
|   +-- coding-standards.yaml        # Android底层编码规范
|   +-- api-migration-rules/        # API迁移规则数据库
|   |   +-- telephony-migration.yaml  # 通信模块API迁移规则
|   +-- quality-gates.yaml          # 质量门禁定义
+-- telephony/                       # 通信模块约束
|   +-- module.yaml                 # 模块基础信息
|   +-- bug-analysis.yaml           # Bug分析场景约束
|   +-- version-adaptation.yaml     # 版本适配场景约束
|   +-- carrier-porting.yaml        # 运营商适配场景约束
+-- kernel-driver/                   # 内核驱动模块约束
|   +-- ...
+-- power-mgmt/                      # 功耗管理模块约束
    +-- ...
```

**文件作用说明**：

- `module.yaml`：定义模块名称、负责人、范围（includes/excludes）
- `<scenario>.yaml`：定义特定场景的 AI 约束（输入格式、输出规范、参考文档）
- `coding-standards.yaml`：跨模块通用编码规范
- `api-migration-rules/*.yaml`：API 变更数据库，供版本适配场景查询

### 3.3 skills/ Skill 引擎目录

```
skills/
+-- .claude/skills/
    +-- telephony-bug-analyzer/          # 通信Bug分析 Skill
    |   +-- SKILL.md                     # Skill 协议文档
    |   +-- examples/
    |       +-- bug-input-1.txt          # 输入示例
    |       +-- expected-output-1.txt    # 期望输出示例
    +-- kernel-panic-tracer/             # 内核崩溃追踪 Skill
    |   +-- ...
    +-- power-leak-detector/             # 功耗泄漏检测 Skill
    |   +-- ...
    +-- telephony-version-adapter/       # 通信版本适配 Skill
    |   +-- ...
    +-- carrier-porting-assistant/       # 运营商适配助手 Skill
        +-- ...
```

### 3.4 playbooks/ 执行编排目录

```
playbooks/
+-- bug-analysis-pipeline.yaml         # Bug分析流水线
+-- version-upgrade-pipeline.yaml      # 版本升级流水线
+-- feature-porting-pipeline.yaml      # 特性移植流水线
+-- carrier-porting-pipeline.yaml      # 运营商适配流水线
```

### 3.5 tools/ MCP 工具目录

```
tools/
+-- android-log-analyzer/
|   +-- tool.py              # 工具实现（MCP协议）
|   +-- requirements.txt    # Python依赖
+-- aosp-diff-analyzer/
|   +-- ...
+-- patch-generator/
|   +-- ...
+-- api-migration-db/
|   +-- ...
+-- build-verifier/
|   +-- ...
+-- regression-test-runner/
|   +-- ...
+-- code-review-checker/
    +-- ...
```

**MCP 工具列表**（Phase 0 为桩函数，Phase 1 实现）：

| 工具 | 作用 |
|------|------|
| `android-log-analyzer` | 解析 Android logcat/tombstone 日志 |
| `aosp-diff-analyzer` | 分析 AOSP 版本间代码差异 |
| `patch-generator` | 生成代码补丁（git format-patch 格式） |
| `api-migration-db` | 查询 API 迁移规则数据库 |
| `build-verifier` | 编译验证（调用 build.sh） |
| `regression-test-runner` | 回归测试（调用 CommSmokeTest） |
| `code-review-checker` | 代码审查（检查编码规范） |

### 3.6 scripts/ 脚本目录

```
scripts/
+-- gate_check.py              # 质量门禁检查脚本
+-- init_module.py             # 新模块初始化脚本
+-- init_scenario.py           # 新场景初始化脚本
+-- evoskill_runner.py         # EvoSkill 进化运行器
+-- validate_constraints.py    # 约束文件格式验证脚本
```

### 3.7 docs/ 文档目录

```
docs/
+-- architecture/              # 架构设计文档
|   +-- 01-overview.md
|   +-- 02-constraint-system.md
|   +-- 03-skill-engine.md
|   +-- 04-execution-orchestration.md
|   +-- 05-evaluation-iteration.md
+-- quality/                   # 质量门禁文档
|   +-- quality-gates.md
+-- TAHP-工程完整解析.md       # 本文档
```

---

## 4. 核心机制详解

### 4.1 约束系统（Constraint System）

#### 4.1.1 约束文件结构

**模块级约束**（`constraints/telephony/module.yaml`）：

```yaml
module: telephony
owner: neng.zhou
description: 通信模块（RIL/Telephony/Modem）
scope:
  includes:
    - packages/services/Telephony/
    - frameworks/opt/telephony/
  excludes:
    - test/
    - vendor/
```

**场景级约束**（`constraints/telephony/bug-analysis.yaml`）：

```yaml
scenario: bug-analysis
module: telephony
input:
  format: android-logcat
  required_fields: [timestamp, level, tag, message]
output:
  format: root-cause-analysis
  required_sections: [summary, root_cause, fix_suggestion, confidence]
references:
  - docs/architecture/02-constraint-system.md
examples:
  - examples/bug-case-1.md
```

#### 4.1.2 约束如何工作？

1. AI 读取约束文件（通过 Skill 协议注入）
2. 按照约束定义的输入格式解析用户输入
3. 按照约束定义的输出规范生成结果
4. 参考约束中引用的文档和示例

### 4.2 Skill 引擎（Skill Engine）

#### 4.2.1 Skill 协议结构

```markdown
# Skill: <skill-name>

## Role
你是一个<角色描述>。

## Input Format
接受的输入格式：
- 字段1：说明
- 字段2：说明

## Output Specification
输出必须包含以下部分：
1. **摘要**：...
2. **根因分析**：...
3. **修复建议**：...
4. **置信度**：...

## Constraints
- 约束1
- 约束2

## Examples
### 示例1
输入：...
输出：...
```

#### 4.2.2 双引擎说明

**诊断引擎**（Diagnostic Engine）：
- 场景：Bug 分析
- 输入：Android 日志（logcat/tombstone）
- 输出：根因分析 + 修复建议
- Skill：`telephony-bug-analyzer`、`kernel-panic-tracer`、`power-leak-detector`

**适配引擎**（Adaptation Engine）：
- 场景：版本升级、特性移植、运营商适配
- 输入：版本差异、目标需求
- 输出：适配方案、代码补丁
- Skill：`telephony-version-adapter`、`carrier-porting-assistant`

### 4.3 执行编排（Execution Orchestration）

#### 4.3.1 分级策略

| 级别 | 置信度阈值 | 执行方式 | 人工介入 |
|------|-----------|---------|---------|
| 全自动 | > 95% | AI 全自动执行并提交 | 不需要 |
| 半自动 | 70-95% | AI 生成方案，人工确认后执行 | 需要确认 |
| 人工 | < 70% | AI 提供建议，人工主导执行 | 主导执行 |

#### 4.3.2 Playbook 流水线

```yaml
name: bug-analysis-pipeline
description: Bug分析流水线
inputs:
  - name: log_file
    type: file
    required: true
  - name: module
    type: string
    default: telephony
steps:
  - name: parse-log
    tool: android-log-analyzer
    inputs:
      log_file: ${{ inputs.log_file }}
    outputs:
      - parsed_log
  - name: analyze
    skill: telephony-bug-analyzer
    inputs:
      parsed_log: ${{ steps.parse-log.outputs.parsed_log }}
    constraint: constraints/telephony/bug-analysis.yaml
    outputs:
      - analysis_result
  - name: quality-check
    script: scripts/gate_check.py
    inputs:
      result: ${{ steps.analyze.outputs.analysis_result }}
    gate: constraints/shared/quality-gates.yaml
    outputs:
      - gate_result
```

### 4.4 评估与迭代（Evaluation & Iteration）

#### 4.4.1 质量门禁

**P0（BLOCK）**：
- 编译错误
- 明显的功能错误
- 违反编码规范
- **处理**：阻止提交，必须修复

**P1（WARNING）**：
- 潜在的逻辑问题
- 性能隐患
- 代码风格问题
- **处理**：记录警告，可人工确认后通过

**P2（RECORD）**：
- 建议性优化
- 文档完善建议
- **处理**：记录备查，不影响提交

#### 4.4.2 EvoSkill 进化引擎

**工作原理**：
1. 准备评估数据集（eval-data/）
2. 运行 Skill 并收集结果
3. 对比期望输出，计算准确率
4. 如果准确率 < 阈值，自动调整 Skill 协议
5. 重复步骤 2-4，最多迭代 N 次（配置中定义为 frontier）

**配置说明**（`.evoskill/config.toml`）：

```toml
[evoskill]
frontier = 3          # 保留最近3个版本的Skill
concurrency = 4        # 并发运行4个评估任务
iteration_limit = 20    # 最多迭代20次

[evaluation]
accuracy_threshold = 0.90    # 准确率阈值90%
eval_data_path = "eval-data/"
```

---

## 5. 新手使用指南

### 5.1 环境准备

**依赖项**：
- Python 3.8+
- Git
- Claude Code CLI（可选，用于 AI 辅助）

**克隆仓库**：

```bash
git clone git@gitlab.transsion.com:neng.zhou/tahp.git
cd tahp
```

### 5.2 快速上手：第一个 Bug 分析

#### 步骤 1：准备输入数据

将 Android 设备日志保存到文件：

```bash
adb logcat -d > /tmp/telephony-bug.log
```

#### 步骤 2：运行 Bug 分析流水线

```bash
# 方式1：使用 Playbook 流水线（推荐）
python scripts/run_playbook.py playbooks/bug-analysis-pipeline.yaml \
  --input log_file=/tmp/telephony-bug.log \
  --input module=telephony

# 方式2：分步执行（调试用）
# 步骤2.1：解析日志
python tools/android-log-analyzer/tool.py --input /tmp/telephony-bug.log

# 步骤2.2：AI 分析（需要 Claude Code）
claude -p "按照 constraints/telephony/bug-analysis.yaml 约束，分析以下日志的根因：..."

# 步骤2.3：质量检查
python scripts/gate_check.py --input analysis-result.md
```

#### 步骤 3：查看结果

分析结果保存在 `outputs/<timestamp>/analysis-result.md`。

### 5.3 添加新模块

#### 步骤 1：运行初始化脚本

```bash
python scripts/init_module.py --module wifi
```

脚本会自动创建：

```
constraints/wifi/
+-- module.yaml
+-- bug-analysis.yaml
+-- version-adaptation.yaml
+-- ...
```

#### 步骤 2：编辑模块约束

编辑 `constraints/wifi/module.yaml`：

```yaml
module: wifi
owner: <你的名字>
description: WiFi模块（WPA Supplicant/WiFi HAL）
scope:
  includes:
    - frameworks/opt/net/wifi/
    - packages/modules/Wifi/
  excludes:
    - test/
```

#### 步骤 3：添加场景约束

根据业务需要，编辑对应的场景约束文件（参考 `constraints/telephony/` 下的示例）。

#### 步骤 4：创建 Skill

```bash
mkdir -p skills/.claude/skills/wifi-bug-analyzer
# 参考 skills/.claude/skills/telephony-bug-analyzer/SKILL.md 创建
```

#### 步骤 5：提交到 GitLab

```bash
git add constraints/wifi/ skills/.claude/skills/wifi-bug-analyzer/
git commit -m "feat: add wifi module constraints and skill"
git push origin master
```

### 5.4 运行 EvoSkill 进化

```bash
# 准备评估数据
mkdir -p eval-data/telephony-bug-analyzer/
# 添加 <input, expected-output> 对到该目录

# 运行进化
python scripts/evoskill_runner.py \
  --skill skills/.claude/skills/telephony-bug-analyzer/SKILL.md \
  --eval-data eval-data/telephony-bug-analyzer/

# 查看进化结果
cat .evoskill/frontier/telephony-bug-analyzer/latest/SKILL.md
```

---

## 6. 落地场景与实际用例

### 6.1 场景一：通信模块 Bug 分析

**业务背景**：
某款机型的 WiFi Calling 功能在特定运营商网络下崩溃，需要分析 logcat 和 tombstone 找到根因。

**传统方式**：
1. 工程师手动分析 5000+ 行 logcat
2. 搜索关键错误信息
3. 查看源码相关位置
4. 提出假设并验证
5. **耗时**：2-4 小时

**使用 TAHP**：

```bash
# 1. 收集日志
adb logcat -d > /tmp/wificalling-crash.log
adb shell cat /data/tombstones/tombstone_05 > /tmp/tombstone_05.txt

# 2. 运行 TAHP Bug分析流水线
python scripts/run_playbook.py playbooks/bug-analysis-pipeline.yaml \
  --input log_file=/tmp/wificalling-crash.log \
  --input module=telephony

# 3. 查看 AI 分析结果
cat outputs/20260518/analysis-result.md
```

**输出示例**（简化）：

```markdown
## 摘要
WiFi Calling 在 Vodafone IN 网络下崩溃，根因是 IMS 服务在处理 SIP 重注册时
空指针解引用。

## 根因分析
文件：packages/services/Telephony/src/com/android/ims/ImsService.java:1247
问题：mImsConfig 在未初始化时被访问
触发条件：飞行模式切换 + WiFi Calling 重启

## 修复建议
在访问 mImsConfig 前添加 null 检查：
```java
if (mImsConfig != null) {
    mImsConfig.getConfig(...)
}
```

## 置信度
92% （基于类似案例 telephony-bug-case-23）
```

**效率提升**：
- 传统方式：2-4 小时
- TAHP：5-15 分钟
- **提升**：8-16 倍

### 6.2 场景二：Android 版本升级适配

**业务背景**：
从 Android 15 升级到 Android 16，通信模块有 127 个文件需要调整（API 变更）。

**传统方式**：
1. 使用 `diff` 工具对比 AOSP 15/16 差异
2. 逐个文件检查 API 变更
3. 手动修改代码
4. 编译验证
5. **耗时**：3-5 天

**使用 TAHP**：

```bash
# 1. 分析版本差异
python tools/aosp-diff-analyzer/tool.py \
  --old aosp-15/telephony \
  --new aosp-16/telephony \
  --output /tmp/telephony-diff.json

# 2. 查询 API 迁移规则
python tools/api-migration-db/tool.py \
  --diff /tmp/telephony-diff.json \
  --output /tmp/migration-rules.json

# 3. 运行版本适配流水线
python scripts/run_playbook.py playbooks/version-upgrade-pipeline.yaml \
  --input diff_file=/tmp/telephony-diff.json \
  --input module=telephony

# 4. 审查 AI 生成的补丁
git diff --cached  # 查看暂存区的修改

# 5. 编译验证
bash build.sh telephony

# 6. 提交
git commit -m "feat: telephony module A15->A16 adaptation"
```

**效率提升**：
- 传统方式：3-5 天
- TAHP：4-8 小时
- **提升**：6-10 倍

### 6.3 场景三：运营商需求适配

**业务背景**：
Vodafone 印度要求新增 WiFi Calling 增强功能，涉及 12 个文件修改。

**使用 TAHP**：

```bash
# 1. 准备运营商需求文档
# 将 Vodafone RFP 文档整理为结构化需求

# 2. 运行运营商适配流水线
python scripts/run_playbook.py playbooks/carrier-porting-pipeline.yaml \
  --input requirement=/tmp/vodafone-wificalling-req.md \
  --input module=telephony \
  --input carrier=vodafone-in

# 3. 查看 AI 生成的适配方案和代码补丁
ls outputs/20260518/carrier-porting/
```

### 6.4 场景四：EvoSkill 自动优化

**业务背景**：
发现 `telephony-bug-analyzer` 在分析 RIL 相关 Bug 时准确率低（仅 65%）。

**使用 EvoSkill**：

```bash
# 1. 准备评估数据（输入 + 期望输出）
ls eval-data/telephony-bug-analyzer/
# input-01.txt  input-02.txt  ...  input-20.txt
# expected-01.md  expected-02.md  ...  expected-20.md

# 2. 运行 EvoSkill 进化
python scripts/evoskill_runner.py \
  --skill skills/.claude/skills/telephony-bug-analyzer/SKILL.md \
  --eval-data eval-data/telephony-bug-analyzer/ \
  --iterations 20

# 3. 查看进化结果
# 迭代 8 次后，准确率达到 91%，自动停止
cat .evoskill/frontier/telephony-bug-analyzer/iteration-8/SKILL.md
```

**效果**：
- 进化前准确率：65%
- 进化后准确率：91%
- **提升**：40%

---

## 7. 与传统方式对比

| 维度 | 传统方式 | TAHP 方式 | 提升 |
|------|---------|----------|------|
| **Bug 分析耗时** | 2-4 小时 | 5-15 分钟 | 8-16x |
| **版本升级适配耗时** | 3-5 天 | 4-8 小时 | 6-10x |
| **代码质量** | 依赖个人经验 | 约束保证 + 质量门禁 | 更稳定 |
| **知识传承** | 口头传授 / 文档 | 约束文件 + Skill | 可复用 |
| **多模块协同** | 各自为战 | 统一框架 | 高效率 |
| **AI 输出可控性** | 低（自由格式） | 高（约束框架） | 可预测 |

---

## 8. 常见问题 FAQ

### Q1：TAHP 需要服务器吗？
**A**：不需要。TAHP 是纯本地执行的，基于 Git 进行版本控制。只需一台开发机即可。

### Q2：没有 Claude Code 能用吗？
**A**：可以。TAHP 的约束文件和 Playbook 流水线是与 AI 模型无关的。你可以对接任何支持标准输入的 AI 工具。

### Q3：如何贡献新的约束或 Skill？
**A**：参考本文档 5.3 节，或通过 Merge Request 贡献。

### Q4：EvoSkill 会自动修改我的代码吗？
**A**：不会。EvoSkill 只优化 Skill 协议文件（SKILL.md），不会修改约束文件或业务代码。

### Q5：质量门禁可以自定义吗？
**A**：可以。`constraints/shared/quality-gates.yaml` 定义了可扩展的质量规则，支持自定义 P0/P1/P2 规则。

### Q6：支持哪些 Android 版本？
**A**：TAHP 是与 Android 版本无关的框架。你需要为每个版本适配场景准备对应的 API 迁移规则（放在 `constraints/shared/api-migration-rules/`）。

---

## 附录

### A. 参考文档

- [TAHP 方案设计](./TECNO-AI-Harness-Platform-方案设计.md)
- [架构设计文档](./architecture/)
- [质量门禁规范](./quality/quality-gates.md)

### B. 相关仓库

- GitLab：`git@gitlab.transsion.com:neng.zhou/tahp.git`
- 本地路径：`E:\TAHP\tahp`

### C. 联系方式

- 负责人：neng.zhou
- 模块负责人详见各 `constraints/<module>/module.yaml`

---

*本文档由 TAHP 项目组维护。最后更新：2026-05-18*
