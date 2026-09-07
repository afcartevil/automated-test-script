---
name: device-self-check
description: >-
  TAHP Console「AI 自检」V0.9：页头 Tab 导航、总览功能看板、
  设备并行调度、刷机、str4/week/custom 测试流程、SSE 与 Python 用例执行。
  在 Cursor 中调整 AI 自检 UI、测试流程、用例目录、刷机或报告时使用。
---

# AI 自检（device-self-check）

> **Cursor 项目 Skill**（`.cursor/skills/device-self-check/`），供 Cursor Agent 开发调优使用；**不是** `skills/.claude/skills/` 下的 Hermes/Console 业务 Skill。

Console 入口：`/#/tahp/self-check`（`DeviceSelfCheckView.vue`）。  
生产路径：**Vue 前端 → Koa BFF → Node 调度 → Python 用例**（不经 Hermes Agent）。

## 何时加载本 Skill

- 修改 AI 自检界面布局、Tab、流水线、设备执行区交互
- 调整测试启动/继续/结束/复测/刷机/自定义用例流程
- 新增或修改用例、模块前置条件、结果复用规则
- 排查设备状态不同步、SSE、人工确认、报告生成问题
- **将新测试大类/外部工具接入自检**：先读 [self-check-test-integration](../self-check-test-integration/SKILL.md) 完成能力清单，再改代码

**先读代码再改**：状态与业务逻辑在 `useDeviceSelfCheck.ts`，设备执行 UI 在 `SelfCheckDeviceRun.vue`，后端以 `device-self-check.ts`（service）为准。

---

## 架构

```
DeviceSelfCheckView.vue          ← Tab 壳层 + provide 上下文
  ├─ useDeviceSelfCheck.ts       ← 状态、SSE、测试/刷机/用例详情
  ├─ SelfCheckPageHeader         ← 标题 + 右侧 Tab 导航
  ├─ SelfCheckOverview           ← 「总览」Tab：5 功能看板卡
  ├─ TestPlanningWorkspace       ← 「项目规划」Tab
  ├─ SelfCheckChecklist + SelfCheckDeviceRun  ← 「设备执行」Tab
  ├─ GerritReviewWorkspace       ← 「AI Review」Tab
  └─ SelfCheckReportReview       ← 「测试报告」Tab
        │ HTTP + EventSource(SSE)
        ▼
routes/tahp/device-self-check.ts
        ▼
services/tahp/device-self-check.ts   ← 设备/会话/调度/报告
services/tahp/device-flash.ts        ← 刷机 device_update
        │ spawn python
        ▼
services/tahp/self-check/python/
  run_case.py → cases/{str4|week|smoke|power}/{module}/caseN.py
  case_config/*.json
  tools/sdd_test/si_run.py          ← 冒烟 USD（cases/smoke/usd/case1.py 调用）
  tools/tpower_auto/run_power_env.py  ← 功耗电流分析（cases/power/current_analysis/case1.py 调用 run 前台阻塞）
```

报告输出：`reports/self-check/{deviceId}/{timestamp}/`（CSV + summary.json + xlsx）。

---

## 关键文件

| 层级 | 路径 | 职责 |
|------|------|------|
| 页面壳层 | `views/tahp/DeviceSelfCheckView.vue` | Tab 切换、provide `DEVICE_SELF_CHECK_KEY` |
| 核心 Composable | `composables/useDeviceSelfCheck.ts` | 全部前端状态与 API 调用 |
| 设备执行 UI | `components/tahp/self-check/SelfCheckDeviceRun.vue` | 设备列表/详情/自定义测试/用例大类详情 |
| 用例大类卡片 | `components/tahp/self-check/SelfCheckChecklist.vue` | 顶部 str4/week/smoke/monkey 卡片 |
| 总览 UI | `components/tahp/self-check/SelfCheckOverview.vue` | 5 功能看板卡 |
| 页头 | `components/tahp/self-check/SelfCheckPageHeader.vue` | 标题 + 右侧 Tab |
| 功能卡 | `components/tahp/self-check/SelfCheckOverviewCard.vue` | 总览模块卡片壳 |
| 流程状态 | `components/tahp/self-check/SelfCheckFlowStatus.vue` | 紧凑 pipeline 列表 |
| 工具函数 | `components/tahp/self-check/self-check-utils.ts` | 状态色、文案等 |
| 刷机进度 | `utils/flash-progress.ts` | 解析 device_update 日志 |
| 前端 API | `api/tahp/device-self-check.ts` | 类型与 REST 封装 |
| 刷机服务 | `services/tahp/device-flash.ts` | device_update 调度 |
| 核心服务 | `services/tahp/device-self-check.ts` | 调度、会话、报告 |
| 报告列表 | `services/tahp/self-check-reports.ts` | 测试报告审阅与用例结果修正 |
| 验测任务代理 | `routes/tahp/central-sso.ts` + `services/tahp/sync/central-client.ts` | `GET /api/tahp/verify-tasks/mine`（中心 verify/mine?view=open 转发） |
| Python | `services/tahp/self-check/python/` | 用例与 `run_case.py` |
| E2E | `tests/e2e/self-check.spec.ts` | 页面冒烟 |

> 2026-09：「AI 测试自规划」已下线删除（`test-planning.ts` / `test-plan-executor.ts` / `test-plan-executions.ts` / `project-info-xlsx.ts`），定时指派由中心 BFF「任务中心 → 质量验测 → 定时任务」接管。

---

## 界面布局（V0.9）

### 页头

`SelfCheckPageHeader`：左侧「AI 自检」标题 + 副标题；右侧 `EaInnerTabs`（`align="end"`）。  
**不再**在页头展示统计四卡或横向流水线（`SelfCheckHero` / 页面级 `SelfCheckPipeline` 已移除）。

### 顶层 Tab `activeTab`

| key | 组件 | 内容 |
|-----|------|------|
| `overview` | `SelfCheckOverview` | 看板：流程状态、验测任务（中心指派）、测试执行、评审补全、测试报告 |
| `devices` | `SelfCheckChecklist` + `SelfCheckDeviceRun` | 用例大类卡片（点击进入详情）+ 设备列表/详情/自定义测试 |
| `gerrit` | `GerritReviewWorkspace` | AI Code Review + 用例推荐 |
| `review` | `SelfCheckReportReview` | 测试报告列表 + 可展开详情（复测/改结果/人工审阅） |

设计说明见 `docs/tahp-self-check-ui-redesign.md`。

### 「设备执行」Tab 布局

**顶部用例卡片**（`SelfCheckChecklist`）：展示 `str4` / `week` / `smoke` / `monkey` / `gms` / `power` 等用例大类。

- 标题：与用例大类名一致（转测摸底测试、周版本测试）
- 覆盖：该大类包含的模块名（`moduleLabel` 拼接）
- 自动化 / 前置：由 `self-check-utils` 根据模块配置聚合（含 SIM、辅测机要求）
- 无「最近」与操作按钮；点击卡片 → `openCaseCatalog(testType)` 在设备列表上方展开用例面板

**内层 `viewMode`**（`SelfCheckDeviceRun`）：

| 值 | 条件 | 内容 |
|----|------|------|
| `list` | 默认 | 用例面板（可选）+ 设备列表 + 设备详情（可选），`self-check-stack` 纵向叠放 |
| `customTest` | 点击「自定义测试」 | 三级勾选 + DUT/辅测机选择 |

点击用例 / 设备 → 自动滚动到对应区块（不互斥）。用例详情区纵向高度约一屏（`100vh - 顶栏偏移`），稍下滑即见设备列表。

### 用例大类展开面板（`catalogPanelExpanded`）

- 位于设备列表**上方**；大类名、覆盖/自动化/前置、自动复测；左用例列表 + 右用例详情
- 纵向高度约一屏（`calc(100vh - 48px)`）；概览区 + 列表/详情区在面板内 flex 分配，框内滚动
- 与设备详情可同时展开

### 设备详情面板（`deviceDetailExpanded`）

- 位于设备列表**下方**；与用例面板相同三框布局：顶部设备概览 + 左用例列表 + 右操作/用例详情
- 纵向高度约一屏（`calc(100vh - 48px)`）；概览 + 列表/详情在面板内 flex 分配，框内滚动
- 与用例面板可同时展开

### 设备详情（空闲时操作）

- **刷机**（已实现）：`device_update`，可选 Root 包、市场版本；`startTest` 可带 `flash` payload
- 开始测试 / 继续测试 / **结束测试**（终止当前执行中的用例与流程）
- **错误**状态设备：设备列表可用「错误」筛选；详情区展示异常位置与原因，支持 **恢复测试**（从报错模块继续）或 **结束测试**

测试正常结束或手动结束后，设备**自动恢复空闲**；完整报告写入「测试报告」Tab。

设备列表筛选：全部 / 测试中 / 等待测试 / 空闲 / **错误** / 辅测机（已移除无意义的「通过」「失败」筛选项）。

### 测试报告 Tab（`SelfCheckReportReview`）

- 列表展示近 72 小时报告；点击报告**向下展开**详情面板（布局与设备详情三框类似）
- 左侧用例列表 + 右侧用例详情，支持**复测此用例**、**修改用例结果**、人工审阅结论
- 报告内复测要求对应设备处于**空闲**状态

### 实时更新

- `useDeviceSelfCheck` 内 `connectEventStream()` 全局 SSE
- 事件：`device_updated`、`test_completed`、`case_completed` 等
- SSE 失败降级：轮询 `getDeviceDetail` + `getPendingManualDecision`

### AI 测试自规划（已下线）

> 2026-09 起「自动规划」Tab 与服务端 executor 整体删除，定时指派改由中心 BFF 定时任务完成；历史报告标题中的「AI规划」标记保留展示（`summary.json` 的 `aiPlanned/scheduleKey` 仍用于历史报告的项目归属解析）。

### 总览「验测任务」卡片

- 数据源：`useVerifyTasks`（15s 轮询 + `onActivated` 立即刷新）→ EA 服务端 `GET /api/tahp/verify-tasks/mine` → 中心 `verify/mine?view=open`（会话模式转发）。
- 展示：项目（`project`）、测试项（`item_label`）、指派时间 + 指派账号（`created_at` · `created_by`，如 admin / auto-plan）；中心侧完成/取消后下一轮轮询即移除。
- 「进入 →」跳「测试执行」Tab。

---

## 测试流程

### 测试类型

| testType | 标签 | 模块顺序 |
|----------|------|----------|
| `str4` | 转测摸底测试 | driver_component → driver_hardware → tdd |
| `week` | 周版本测试 | driver → tdd |
| `monkey` | monkey测试 | monkey |
| `smoke` | 冒烟测试 | usd（`si_run --test-type usd`） |
| `gms` | GMS测试 | cts / gts / vts |
| `power` | 功耗自动化测试 | current_analysis（`run_power_env.py run` 前台阻塞，子线程执行飞书任务） |
| `custom` | 自定义测试 | 用户勾选顺序 |

新增标准 testType 流程见 [self-check-test-integration](../self-check-test-integration/SKILL.md)。

### 标准流程（str4 / week）

```
刷新设备 → 设备详情选角色/用例大类 → startTest({ flash? })
  → 可选刷机（device_update）→ runTestFlow()
  → 逐模块 runModule() → 前置条件 / Python 用例 / 结果复用
  → 模块末按 settings 自动复测失败的全自动用例
  → finishTest + generateTestReport
```

### 自定义流程（custom）

概览设备执行 Tab → 自定义测试 → 勾选用例 + 选 DUT/辅测机 → `startCustomTest()`。

### 单用例执行要点

- 有 `case{N}.py` → `execPythonCase`，stdout JSON 协议
- 无脚本 → `待确认` + SSE `manual_confirm`
- 超时默认 120s；**功耗自动化**默认 24h（`TAHP_POWER_TIMEOUT_MS`）

### 功耗自动化（power）流程

与冒烟/GMS 一致：`startTest` → 初始化 → **测试中**（用例阻塞）→ 完成 → 报告。

- `case1.py` 前台运行 `run_power_env.py run`（内部 `task_proc_thread` 子线程调度飞书任务）
- **首次启动功耗测试**时自动 pip 安装完整运行时依赖（`openai` / `opencv` 等）
- 执行期间设备保持 **测试中**；实时步骤来自 `log/power_env_daemon.log` 尾行
- **结束测试** / 用例 cleanup → `stop` 终止环境 → 汇总 `output/*.xlsx` 写入结论
- 报告复制最新 xlsx 为 `test_report.xlsx`，结论含通过/失败项统计

---

### 模块前置条件

见 `case_config/*.json` → `moduleConditions`（str4/tdd 需 2 SIM + 1 辅测机等）。

---

## 常见改动指引

| 目标 | 优先修改 |
|------|----------|
| **新测试项接入** | [self-check-test-integration](../self-check-test-integration/SKILL.md) → case_config / python / 前后端清单 |
| Tab / 总览 / 流水线 UI | `DeviceSelfCheckView.vue`、对应 `SelfCheck*.vue` |
| 设备列表/详情/用例详情 UI | `SelfCheckDeviceRun.vue` |
| 状态、API、SSE、刷机逻辑 | `useDeviceSelfCheck.ts` |
| 新 REST 能力 | service → routes → `client/api` |
| 用例逻辑 | `self-check/python/cases/...` |
| 刷机工具链 | `device-flash.ts`、`self-check/flash_tool/` |
| 报告审阅 / 报告内复测改结果 | `self-check-reports.ts`、`SelfCheckReportReview.vue` |

**最小变更**：UI 改组件；流程变更需核对 SSE 与 `TestSession` 字段。

---

## 验证

```bash
cd tahp-console
npm run setup          # 含功耗自动化 Python 依赖
npm run dev            # 启动前仅 ensure Hermes Agent
npm run setup:power    # 可选：手动预装功耗依赖
npm test
npx playwright test tests/e2e/self-check.spec.ts
```

**启动时依赖初始化**（`predev` / `prestart` / `dev-server` / `bootstrap`）：

- 仅确保 **Hermes Agent**；**不**安装功耗 Python 依赖
- 功耗依赖在**启动功耗自动化测试**时自动检查/安装（`ensurePowerTestPythonDeps`）
- `TAHP_SKIP_POWER_DEPS=1` — 跳过功耗依赖安装
- `npm run setup:power` — 手动预装（可选）

---

## 延伸阅读

- API / SSE / 类型： [reference.md](reference.md)
- **测试项集成（能力门禁 + 验收）**：[self-check-test-integration](../self-check-test-integration/SKILL.md)
- 流程细节：`ai自检流程梳理.md`（可能未入库）
