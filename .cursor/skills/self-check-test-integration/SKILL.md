---
name: self-check-test-integration
description: >-
  将新测试项（测试大类/模块/用例）集成到 TAHP AI 自检的通用流程。
  集成前必须先明确用例对外能力（启动、停止、状态、时长、刷机等），
  能力清单确认后方可改代码；集成时前后端同步修改；
  新增 StandardTestType 须同步加入 AI 测试自规划「测试规划」测试大类选择项（PlanTestType）；
  完成后执行自检验证。参考实现：monkey、smoke。与 device-self-check skill 配合使用。
---

# AI 自检 — 测试项集成 Skill

> **Cursor 项目 Skill**（`.cursor/skills/self-check-test-integration/`）。  
> 在新增/接入测试大类（如 `str4` / `week` / `monkey`）、模块或用例时使用。  
> 界面与运行时细节见 [device-self-check](../device-self-check/SKILL.md)；本 Skill 聚焦**集成门禁、能力定义、改动清单与验收**。

## 何时加载

- 用户要求「把 XX 测试接入 AI 自检」「新增测试大类/用例」
- 从外部工具（如 `D:\RD_tool\...`）移植脚本到自检 Python 目录
- 需要评估某测试是否适合自检框架（同步用例 vs 后台长跑）

**硬性规则**：未完成「能力清单」填写与确认，**禁止**开始改 `case_config`、Python 用例或前后端类型。

---

## 集成总览

```
阶段 0  能力定义（门禁）── 填写能力矩阵，确认生命周期与停止策略
   ↓
阶段 1  资产落仓 ── case_config + cases + tools（如有）
   ↓
阶段 2  后端 ── testType / 模块 / settings / 生命周期钩子 / 路由
   ↓
阶段 3  前端 ── API 类型 / 文案 / 选择器 / 类型专属设置面板
   ↓
阶段 4  AI 测试自规划 ── 测试规划「测试大类」选择项 + PlanTestType（与自检 testType 对齐）
   ↓
阶段 5  规划自动执行刷机（若需要）── test-plan-executor / device-flash PlannedTestType
   ↓
阶段 6  自检验证 ── vitest + 手动冒烟
```

前后端**同一阶段内成对提交**：后端 catalog 先可用，前端才能展示；新增 `AutoTestSettings` 字段须 GET/POST settings 与 UI 同时落地。

---

## 阶段 0：能力清单（集成前必做）

为待接入测试填写下表。**每一项必须勾选「有/无」并写清实现方式**；「有」但未说明调用链的，视为未完成。

### 0.1 执行形态

| 能力 | 说明 | 自检框架期望 |
|------|------|----------------|
| **同步执行** | 用例在 `run_case.py` 超时内结束并返回 pass/fail | 默认模式；超时见 `CASE_EXEC_TIMEOUT_MS`（默认 120s） |
| **后台启动** | 启动成功后进程在设备/主机后台继续运行 | 用例 `run()` **尽快返回** `pass`；会话可结束而任务仍运行 |
| **会话与任务解耦** | 测试 Session 结束 ≠ 设备侧任务结束 | 须在能力矩阵中显式声明，并定义停止入口 |

### 0.2 生命周期能力

| 能力 | 是否必需 | 实现位置（示例） |
|------|----------|------------------|
| **启动 (start)** | 通常必需 | `case{N}.py` → 工具脚本；或标准 `runTestFlow` |
| **停止 (stop)** | 后台类**必需** | `endTest()` 钩子（monkey：`stopMonkeyForDevice`）；或独立 REST |
| **状态 (status)** | 可选 | 工具脚本子命令；若 UI 要展示须暴露 BFF API |
| **暂停/继续** | 可选 | `continueTest()` 仅用于前置条件暂停；非标流程需单独设计 |
| **时长/配额** | 可选 | `AutoTestSettings` + `buildDeviceInfo()` → `device_info` |

### 0.3 设备与环境

| 能力 | 说明 |
|------|------|
| **DUT 数量** | `case_config.conditions.dutSimCount` |
| **辅测机** | `auxRequired` / `auxSimCount`；镜像模式见 `defaultCaseMode`（当前仅文档用途） |
| **刷机前置** | `startTest` 的 `flash` payload；规划自动执行见 `buildPlannedTestFlashPayload` |
| **模块 init** | `cases/.../init.py` + `module_init_done` 防重复初始化 |

### 0.4 交互与结果

| 能力 | 说明 |
|------|------|
| **全自动** | `full_automation: true`；失败是否触发模块末自动复测（`getAutoRetestConfig`） |
| **人工确认** | stdout `manual_confirm` JSON；前端 `POST /manual-decision` |
| **结果复用** | `case_config.cases[].canReuse` |
| **步骤流式输出** | `step_update` → SSE `step_update` |

### 0.5 能力矩阵模板（复制填写）

```markdown
## {测试名} 能力矩阵

- testType 提议值：`________`
- 执行形态：□ 同步  □ 后台启动（会话结束后的行为：________）
- 启动：命令/API ________  超时 ________
- 停止：□ endTest 钩子  □ 独立 API  □ 仅工具自停  路径 ________
- 状态查询：□ 无  □ 有（是否暴露 BFF：________）
- 时长/配置项：________  默认 ________  校验规则 ________
- 刷机：□ 不需要  □ 手动  □ 规划自动（是否 Root：________）
- SIM/辅测：dutSim=__ auxRequired=__ auxSim=__
- 自动复测：□ 沿用 str4/week  □ 禁用（monkey 模式）
- 规划排期：□ 不入规划  □ 入 PlanTestType
```

**门禁**：上表经需求方确认后，方可进入阶段 1。

---

## 阶段 1：资产落仓

目录根：`tahp-console/packages/server/src/services/tahp/self-check/`

| 资产 | 路径模式 | 说明 |
|------|----------|------|
| 模块配置 | `case_config/{testType}_{module}.json` | 见 [reference.md](reference.md) JSON 字段 |
| 用例脚本 | `python/cases/{testType}/{module}/case{N}.py` | 必须 `def run(**context)` |
| 用例元数据 | `python/cases/.../case_info.json` | 前置/步骤/期望；仅名称亦可 |
| 模块初始化 | `python/cases/.../init.py` | 可选 |
| 外部工具 | `python/tools/{tool_name}/` | 长脚本与资源（黑名单等）放此，勿散落 |

**注册**：新 `case_config` 文件名必须加入 `device-self-check.ts` → `loadCaseConfigs()` 的 `configFiles` 数组（当前非自动扫描）。

**Python 契约**（`run_case.py`）：

- 返回：`{ status, message, full_automation? }`，status ∈ `pass|fail|部分pass|pending|skip`
- 上下文：`device_info`、`step_update`、`manual_confirm`、`test_type`、`module`
- 最终一行 JSON 含 `status` 字段供 Node 解析

---

## 阶段 2：后端改动清单

文件：[`device-self-check.ts`](../../../tahp-console/packages/server/src/services/tahp/device-self-check.ts)

| 步骤 | 改动 |
|------|------|
| 1 | `StandardTestType` 增加新类型（`custom` 不需改此项） |
| 2 | `loadCaseConfigs()` 注册 json |
| 3 | `getModulesForTestType()` 返回模块顺序 |
| 4 | `getAllCaseCatalogs()`：`TEST_TYPE_LABELS`、`typeOrder`、`MODULE_ORDER` |
| 5 | `buildDeviceInfo()`：传入类型专属 settings |
| 6 | `AutoTestSettings` + `getSettings`/`saveSettings` + 校验函数 |
| 7 | `getAutoRetestConfig()`：若长跑/一次性任务则禁用复测 |
| 8 | **停止钩子**：后台类在 `endTest()` 调用 `stopXxxForDevice()` |
| 9 | 路由 [`routes/tahp/device-self-check.ts`](../../../tahp-console/packages/server/src/routes/tahp/device-self-check.ts)：`test/start` body 的 `testType` union |

**凡新增 `StandardTestType` 且能力矩阵勾选「入 PlanTestType」**，必须继续完成 [阶段 4](#阶段-4ai-测试自规划--测试规划测试选择项)（与阶段 2/3 同批提交）。

同步更新 [`case_catalog.py`](../../../tahp-console/packages/server/src/services/tahp/self-check/python/case_catalog.py)（若用 Excel/脚本生成目录）：`SHEET_TO_MODULE`、`TEST_TYPE_LABELS`、`MODULE_LABELS`。

---

## 阶段 3：前端改动清单

| 步骤 | 文件 | 改动 |
|------|------|------|
| 1 | `packages/client/src/api/tahp/device-self-check.ts` | `DeviceInfo`/`TestSession`/`startTest` union；`AutoTestSettings` |
| 2 | `components/tahp/self-check/self-check-utils.ts` | `getTestTypeLabel`、`getModuleLabel`、`MODULE_ORDER` |
| 3 | `composables/useDeviceSelfCheck.ts` | 类型专属 settings 读写、启动参数 |
| 4 | `SelfCheckDeviceRun.vue` | 设备详情测试类型按钮；用例大类设置区（如 monkey 时长） |
| 5 | `SelfCheckChecklist.vue` | 若需静态卡片文案则更新（多数情况后端 catalog 驱动） |

**自定义测试**：仅新增 case_config + Python 时，可不扩展 `StandardTestType`；catalog 暴露后左侧树自动出现，走 `startCustomTest`。

---

## 阶段 4：AI 测试自规划 — 测试规划测试选择项

> 入口：`/#/tahp/self-check` → **项目规划** Tab → **测试规划** 表格 / **测试规划设置** 弹窗（`TestPlanSettingsModal`）。  
> 规则持久化：`.tahp-config/test-plan-rules.json`；到点执行见 `test-plan-executor.ts`。

### 何时必须做本阶段

- 能力矩阵 **「规划排期：入 PlanTestType」** 已勾选
- 或需求明确要求：新测试大类出现在「测试规划设置」的**测试大类下拉**中，并可写入排期规则

**禁止**只改自检 `StandardTestType` 而不改 `PlanTestType`——否则 UI 规则无法保存，或保存时报「无效测试大类」。

### `PlanTestType` 与 `StandardTestType` 关系

| 概念 | 用途 |
|------|------|
| `StandardTestType` | 设备自检 `startTest(deviceId, testType)`、用例 catalog |
| `PlanTestType` | 测试规划规则 `testType`、排期 `ScheduleItem.testType`、自动执行 `startTest` 的 testType 参数 |

二者对参与规划的类型**取值应一致**（如 `str4` / `week` / `monkey` / `smoke`）。`custom` 不入规划。

### 改动清单（前后端同步）

| 步骤 | 文件 | 改动要点 |
|------|------|----------|
| 1 | [`test-planning.ts`](../../../tahp-console/packages/server/src/services/tahp/test-planning.ts) | `PlanTestType` union；`TEST_TYPE_LABELS`；`normalizePlanTestType()`（别名如「冒烟」→ `smoke`）；`validateTestPlanRules()` 的 `validTypes` 与错误文案 |
| 2 | [`api/tahp/test-planning.ts`](../../../tahp-console/packages/client/src/api/tahp/test-planning.ts) | `PlanTestType` union（与后端一致） |
| 3 | [`TestPlanSettingsModal.vue`](../../../tahp-console/packages/client/src/components/tahp/TestPlanSettingsModal.vue) | `TEST_TYPE_OPTIONS` 增加一项：`{ label: getTestTypeLabel('<type>'), value: '<type>' }` |
| 4 | [`self-check-utils.ts`](../../../tahp-console/packages/client/src/components/tahp/self-check/self-check-utils.ts) | `getTestTypeLabel('<type>')` 已有文案（阶段 3 应已完成） |
| 5 | [`device-flash.ts`](../../../tahp-console/packages/server/src/services/tahp/device-flash.ts) | `PlannedTestType` 增加新类型（参与**到点自动刷机+启动**时必需） |
| 6 | [`test-plan-executor.ts`](../../../tahp-console/packages/server/src/services/tahp/test-plan-executor.ts) | 一般无需改类型 union（已用 `PlanTestType`）；确认 `buildPlannedTestFlashPayload` 刷机策略（monkey 含 Root，其余仅 daily） |

`TestPlanningWorkspace.vue` 排期表使用 `item.testTypeLabel`，由后端 `getTestTypeLabel` 生成，**通常无需改表格组件**。

### 刷机策略（阶段 5，与规划联动）

| testType | `buildPlannedTestFlashPayload` 行为 |
|----------|-------------------------------------|
| `str4` / `week` / `smoke` | daily + `Open`，无 Root |
| `monkey` | daily + `Open`，尝试 archive `Root/` |

### 测试

```bash
cd tahp-console
npx vitest run tests/server/test-planning.test.ts
npx vitest run tests/server/test-plan-executor.test.ts   # 若涉及自动执行
```

至少覆盖：`normalizePlanTestType`、 `validateTestPlanRules` 接受新类型、保存规则后 schedule 含正确 `testTypeLabel`。

### 已接入规划的类型（参考）

| testType | 规划标签 | 备注 |
|----------|----------|------|
| `str4` | 转测摸底测试 | |
| `week` | 周版本测试 | |
| `monkey` | monkey测试 | 自动执行刷 Root（若可解析） |
| `smoke` | 冒烟测试 | USD 冒烟等 |

---

## 阶段 5：参考实现 — Monkey（能力已落地）

来源计划：集成 monkey 测试（`monkey_usd` → 自检 `python/tools/monkey_usd/`）。

### 已确认能力矩阵

| 能力 | 实现 |
|------|------|
| 执行形态 | **后台启动**；`case1.py` 启动成功后立即 `pass`，Monkey 在设备端继续跑 |
| 启动 | `python monkey_test.py -s <serial> start -d <duration> --save-log` |
| 停止 | **`endTest()`** → `stopMonkeyForDevice` → `monkey_test.py stop`（无独立 stop API） |
| 状态 | 脚本支持 `status`，**未**暴露 BFF |
| 时长 | `settings.monkeyDuration`，默认 `7d`，`normalizeMonkeyDuration` 校验 |
| 刷机 | 规划自动执行：daily + Open；monkey 尝试 archive `Root/` |
| 自动复测 | **禁用** |
| 规划 | `PlanTestType` 含 `monkey` |

### 资产一览

- `case_config/monkey_monkey.json`
- `python/cases/monkey/monkey/case1.py`、`case_info.json`
- `python/tools/monkey_usd/monkey_test.py`、`MonkeyBlackList.txt`

更细的字段与命令见 [reference.md](reference.md#monkey-参考实现)。

---

## 阶段 6：自检验证

### 自动化（必跑）

```bash
cd tahp-console
npm run setup
npx vitest run tests/server/device-self-check-monkey.test.ts   # 按类型替换/新增
npx vitest run tests/server/self-check.test.ts                 # 若存在通用自检用例
npm test                                                       # 全量回归（发 PR 前）
```

**新增测试类型时至少覆盖**：

- `getAllCaseCatalogs()` 含新大类与模块
- `getCaseCatalogDetail(testType)` 字段符合预期
- `getSettings()` 默认值/校验（若有新 settings 字段）
- `startTest(..., '<type>')` 能创建 session（mock Python，禁止真实长跑）
- 若有停止钩子：mock `endTest` 路径或 spawn 参数

### 手动冒烟清单

1. 打开 `/#/tahp/self-check` → 「设备执行」
2. 用例大类卡片出现新类型；点击进入用例面板
3. 类型专属设置（如有）可保存并刷新后仍在
4. 用例详情展示符合 `case_info.json`
5. 设备详情可选该类型 → 可选刷机 → **开始测试**
6. 后台类：会话结束后设备侧任务仍运行；点 **结束测试** 后任务被停止
7. 自定义测试树可勾选并 `startCustomTest`
8. **项目规划** Tab → 测试规划设置 → 测试大类下拉含新类型；保存规则后排期表 `testTypeLabel` 正确
9. （若入规划自动执行）到点自动刷机 + `startTest` 行为符合刷机策略表

### E2E（可选）

```bash
npx playwright test tests/e2e/self-check.spec.ts
```

---

## 与 device-self-check 的分工

| 主题 | 使用 Skill |
|------|------------|
| 新测试项接入流程、能力门禁、验收 | **本 Skill** |
| Tab 布局、SSE、刷机 UI、报告 Review | [device-self-check](../device-self-check/SKILL.md) |
| REST/SSE 字段明细 | [device-self-check/reference.md](../device-self-check/reference.md) |

---

## 延伸阅读

- 能力矩阵与文件对照表：[reference.md](reference.md)
- **测试规划选择项明细**：[reference.md#ai-测试自规划--测试规划选择项](reference.md#ai-测试自规划--测试规划选择项)
- Monkey 原始需求摘要：仓库外计划 `集成monkey测试_02b65b7c.plan.md`（已收敛至本 Skill 阶段 5）
