---
name: device-self-check
description: >-
  TAHP Console「AI 自检」V0.8：Tab 化总览/项目规划/设备执行/AI Review/报告 Review、
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

**先读代码再改**：状态与业务逻辑在 `useDeviceSelfCheck.ts`，设备执行 UI 在 `SelfCheckDeviceRun.vue`，后端以 `device-self-check.ts`（service）为准。

---

## 架构

```
DeviceSelfCheckView.vue          ← Tab 壳层 + provide 上下文
  ├─ useDeviceSelfCheck.ts       ← 状态、SSE、测试/刷机/用例详情
  ├─ SelfCheckHero / Pipeline
  ├─ SelfCheckOverview           ← 「总览」Tab
  ├─ TestPlanningWorkspace       ← 「项目规划」Tab
  ├─ SelfCheckChecklist + SelfCheckDeviceRun  ← 「设备执行」Tab
  ├─ GerritReviewWorkspace       ← 「AI Review」Tab
  └─ SelfCheckReportReview       ← 「报告 Review」Tab
        │ HTTP + EventSource(SSE)
        ▼
routes/tahp/device-self-check.ts
        ▼
services/tahp/device-self-check.ts   ← 设备/会话/调度/报告
services/tahp/device-flash.ts        ← 刷机 device_update
        │ spawn python
        ▼
services/tahp/self-check/python/
  run_case.py → cases/{str4|week}/{module}/caseN.py
  case_config/*.json
```

报告输出：`reports/self-check/{deviceId}/{timestamp}/`（CSV + summary.json + xlsx）。

---

## 关键文件

| 层级 | 路径 | 职责 |
|------|------|------|
| 页面壳层 | `views/tahp/DeviceSelfCheckView.vue` | Tab 切换、provide `DEVICE_SELF_CHECK_KEY` |
| 核心 Composable | `composables/useDeviceSelfCheck.ts` | 全部前端状态与 API 调用 |
| 设备执行 UI | `components/tahp/self-check/SelfCheckDeviceRun.vue` | 设备列表/详情/自定义测试/用例大类详情 |
| 用例大类卡片 | `components/tahp/self-check/SelfCheckChecklist.vue` | 顶部 str4/week 卡片，点击进入用例详情 |
| 总览 UI | `components/tahp/self-check/SelfCheckOverview.vue` | 运行中设备、节点、计划任务摘要 |
| 工具函数 | `components/tahp/self-check/self-check-utils.ts` | 状态色、文案等 |
| 刷机进度 | `utils/flash-progress.ts` | 解析 device_update 日志 |
| 前端 API | `api/tahp/device-self-check.ts` | 类型与 REST 封装 |
| 刷机服务 | `services/tahp/device-flash.ts` | device_update 调度 |
| 核心服务 | `services/tahp/device-self-check.ts` | 调度、会话、报告 |
| 报告列表 | `services/tahp/self-check-reports.ts` | 报告 Review |
| Python | `services/tahp/self-check/python/` | 用例与 `run_case.py` |
| E2E | `tests/e2e/self-check.spec.ts` | 页面冒烟 |

---

## 界面布局（V0.8）

### 顶层 Tab `activeTab`

| key | 组件 | 内容 |
|-----|------|------|
| `overview` | `SelfCheckOverview` | 运行中设备、即将到节点、计划任务、待审报告摘要 |
| `planning` | `TestPlanningWorkspace` | 项目节点与测试排期规则 |
| `devices` | `SelfCheckChecklist` + `SelfCheckDeviceRun` | 用例大类卡片（点击进入详情）+ 设备列表/详情/自定义测试 |
| `gerrit` | `GerritReviewWorkspace` | AI Code Review + 用例推荐 |
| `review` | `SelfCheckReportReview` | 自检报告审阅 |

页头区：`SelfCheckHero`（统计、同步项目节点、新建任务、刷新设备）+ `SelfCheckPipeline`（流水线阶段）。

### 「设备执行」Tab 布局

**顶部用例卡片**（`SelfCheckChecklist`）：展示 `str4` / `week` / `monkey` 三个用例大类。

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
- 开始测试 / 继续测试 / 结束测试
- 用例详情（进行中）：步骤、人工确认、复测/改结果

### 实时更新

- `useDeviceSelfCheck` 内 `connectEventStream()` 全局 SSE
- 事件：`device_updated`、`test_completed`、`case_completed` 等
- SSE 失败降级：轮询 `getDeviceDetail` + `getPendingManualDecision`

---

## 测试流程

### 测试类型

| testType | 标签 | 模块顺序 |
|----------|------|----------|
| `str4` | 转测摸底测试 | driver_component → driver_hardware → tdd |
| `week` | 周版本测试 | driver → tdd |
| `custom` | 自定义测试 | 用户勾选顺序 |

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
- 超时默认 120s

### 模块前置条件

见 `case_config/*.json` → `moduleConditions`（str4/tdd 需 2 SIM + 1 辅测机等）。

---

## 常见改动指引

| 目标 | 优先修改 |
|------|----------|
| Tab / 总览 / 流水线 UI | `DeviceSelfCheckView.vue`、对应 `SelfCheck*.vue` |
| 设备列表/详情/用例详情 UI | `SelfCheckDeviceRun.vue` |
| 状态、API、SSE、刷机逻辑 | `useDeviceSelfCheck.ts` |
| 新 REST 能力 | service → routes → `client/api` |
| 用例逻辑 | `self-check/python/cases/...` |
| 刷机工具链 | `device-flash.ts`、`self-check/flash_tool/` |
| 报告 Review | `self-check-reports.ts`、`SelfCheckReportReview.vue` |

**最小变更**：UI 改组件；流程变更需核对 SSE 与 `TestSession` 字段。

---

## 验证

```bash
cd tahp-console
npm run setup
npm test
npx playwright test tests/e2e/self-check.spec.ts
```

---

## 延伸阅读

- API / SSE / 类型： [reference.md](reference.md)
- 流程细节：`ai自检流程梳理.md`（可能未入库）
