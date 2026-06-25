---
name: device-self-check
description: >-
  TAHP Console「AI 自检」设备自动化测试：概览/详情/自定义测试/用例详情界面布局、
  多设备并行调度、str4/week/custom 测试流程、SSE 推送与 Python 用例执行。
  在 Cursor 中调整 AI 自检 UI、测试流程、用例目录、前置条件、结果复用或报告生成时使用。
---

# AI 自检（device-self-check）

> **Cursor 项目 Skill**（`.cursor/skills/device-self-check/`），供 Cursor Agent 开发调优使用；**不是** `skills/.claude/skills/` 下的 Hermes/Console 业务 Skill。

Console 入口：`/#/tahp/self-check`（`DeviceSelfCheckView.vue`）。  
生产路径：**Vue 前端 → Koa BFF → Node 调度 → Python 用例**（不经 Hermes Agent）。

## 何时加载本 Skill

- 修改 AI 自检界面布局、交互、状态展示
- 调整测试启动/继续/结束/复测/自定义用例流程
- 新增或修改用例、模块前置条件、结果复用规则
- 排查设备状态不同步、SSE、人工确认、报告生成问题

**先读代码再改**：以 `tahp-console/packages/server/src/services/tahp/device-self-check.ts` 与 `DeviceSelfCheckView.vue` 为准；设计背景见仓库根目录 `ai自检设计文档.md`、`ai自检流程梳理.md`（可能未入库）。

---

## 架构

```
DeviceSelfCheckView.vue
  │ HTTP + EventSource(SSE)
  ▼
routes/tahp/device-self-check.ts
  ▼
services/tahp/device-self-check.ts   ← 设备/会话/调度/报告
  │ spawn python
  ▼
services/tahp/self-check/python/
  run_case.py → cases/{str4|week}/{module}/caseN.py
  case_config/*.json（由 BFF case_config/ 加载）
```

报告输出：`reports/self-check/{deviceId}/{timestamp}/`（CSV + summary.json + xlsx）。

---

## 关键文件

| 层级 | 路径 | 职责 |
|------|------|------|
| 前端主视图 | `tahp-console/packages/client/src/views/tahp/DeviceSelfCheckView.vue` | 四视图模式、设备卡片、详情、SSE |
| 前端 API | `tahp-console/packages/client/src/api/tahp/device-self-check.ts` | 类型与 REST 封装 |
| 路由 | `tahp-console/packages/server/src/routes/tahp/device-self-check.ts` | REST + SSE |
| 核心服务 | `tahp-console/packages/server/src/services/tahp/device-self-check.ts` | 全部业务逻辑 |
| 模块配置 | `tahp-console/packages/server/src/services/tahp/self-check/case_config/*.json` | SIM/辅测机/用例元数据 |
| Python | `tahp-console/packages/server/src/services/tahp/self-check/python/` | 用例实现与 `run_case.py` |
| E2E | `tahp-console/tests/e2e/self-check.spec.ts` | 页面冒烟 |

---

## 界面布局

### 视图模式 `viewMode`

| 值 | 显示条件 | 内容 |
|----|----------|------|
| `overview` | 默认；`!selectedDeviceId` | 用例大类名称列表 + 设备网格 + GerritReviewWorkspace |
| `caseCatalog` | 概览点击用例大类 | 左用例列表 + 右用例设置/手动测试步骤详情 |
| `detail` | `selectedDeviceId` 有值 | 左用例树 + 右设备信息/用例详情 |
| `customTest` | 用户点「自定义测试」 | 三级用例勾选 + DUT/辅测机选择 |

导航状态：

- `selectedDeviceId`：非空即详情页（与 `viewMode` 部分重叠，详情以 `selectedDeviceId` 为准）
- `pageTitle`：详情显示设备名；`customTest` 显示「自定义测试」；`caseCatalog` 显示用例大类名；否则「AI 自检」

### 概览页（自上而下）

1. **EaPageHead**：标题（概览页无额外操作按钮）
2. **用例大类**（`EaCard`，数据来自 `getCaseCatalogs()`，`onMounted` 静默加载）
   - 大类名称以 `ea-domain-chip` 小标签横向排布，点击进入 `caseCatalog` 详情
3. **设备列表**（`EaCard`）：标题行含「自定义测试 / 刷新设备」+ `device-grid` 卡片
   - 点击规则：辅测机且非「待命/空闲」时不可进详情
   - 卡片字段：状态图标、名称、角色、所属用例、插卡、时间/用时
4. **GerritReviewWorkspace**：概览底部 Code Review 工作区（与自检流程独立）

### 用例大类详情页（`caseCatalog`）

- **布局**：与设备详情页相同（`detail-container` + 左 `sidebar-card` + 右 `detail-main`）
- **页头标题**：用例大类名（如「转测摸底测试」）
- **左侧**：`case-list` / `module-group` / `case-item`（与设备详情用例树同结构，可展开/收起）
- **右侧上**：`detail-card-content` + 用例设置（自动复测勾选 + 次数）
- **右侧下**：`case-detail-header` + `case-detail-content` / `case-info` / `case-steps`（与设备详情用例详情同结构）

### 设备详情页

- **左侧**：用例列表（大类→模块→用例），颜色随 `CaseResult.status` 变化
- **右侧上**：设备信息（角色、用例类型、插卡、状态、时间）
- **右侧中（空闲）**：角色切换、用例大类选择（str4/week）、刷机/T卡（占位未实现）、开始测试
- **右侧中（不满足前置条件）**：继续测试
- **右侧下**：用例详情（步骤、结论、人工确认、复测/改结果）
- **页头**：返回概览、打开结果、结束测试 / 停止待命

### 自定义测试页

- 左：大类→模块→用例三级勾选（`selectedCases` 为 `testType/module/caseIndex` 字符串 Set）
- 右：DUT 单选 + 辅测机多选 → `startCustomTest()`
- 启动后跳转 DUT 详情，`testType === 'custom'`，详情页**不显示**常规「开始测试」表单

### 实时更新

- `onMounted` → `connectEventStream()` 全局 SSE
- 事件：`device_updated`、`test_completed` 等同步概览与详情；`goBack()` 时 `loadDevices()`
- SSE 失败降级：1s 轮询 `getDeviceDetail` + `getPendingManualDecision`

---

## 测试流程

### 测试类型

| testType | 标签 | 模块顺序（`getModulesForTestType`） |
|----------|------|-------------------------------------|
| `str4` | 转测摸底测试 | driver_component → driver_hardware → tdd |
| `week` | 周版本测试 | driver → tdd |
| `custom` | 自定义测试 | 用户勾选顺序；按模块首次出现时 `execPythonInit` |

### 标准流程（str4 / week）

```
刷新设备 → 详情选角色/用例大类 → startTest()
  ├─ 辅测机：空闲 → 待命（绑定 testType）
  └─ 测试机：空闲 → 初始化中 → runTestFlow()
        ├─ execDeviceInit（DUT + 已分配辅测机亮屏解锁）
        └─ 逐模块 runModule()
              ├─ checkPreconditions（SIM / 辅测机）
              │     ├─ 失败 → 不满足前置条件（可 continueTest）
              │     └─ 等待辅测 → 等待测试开始
              ├─ execPythonInit（模块 init.py）
              ├─ 逐用例 runCase() → spawn run_case.py
              ├─ 通过且 canReuse → mirrorResult 到辅测机
              ├─ 全自动失败 → 模块内自动复测一次
              └─ 释放辅测机 → 待命
        → finishTest → 完成(通过|失败) + generateTestReport
```

### 自定义流程（custom）

```
概览 → 自定义测试 → 勾选用例 + 选 DUT/辅测机 → startCustomTest()
  → runCustomTestFlow(caseList 顺序)
  → 设备初始化 → 每模块首次用例前 init.py
  → 不阻塞前置条件（仅 SIM 警告日志）
  → 全自动失败项结束后批量复测
  → 报告单 Sheet「自定义测试」，含「所属模块」列
```

### 结束测试 `endTest()`

- 测试机：清空会话，状态回空闲
- 辅测机待命/占用：释放；若同 testType 无活跃 DUT → `releaseAuxDevicesIfNoActiveDut` 将辅测机置空闲
- `canEndTest`：前端对测试中/完成/错误等状态放宽（不限于 `role === 测试机`）

### 单用例执行要点

- Python 存在 `case{N}.py` → `execPythonCase`，stdout 行级 JSON 协议（`step` / `manual_confirm` / 最终 `status`）
- 无脚本 → `待确认` + SSE `manual_confirm`，前端提交 `pass`/`fail`
- 超时默认 120s

### 模块前置条件（`case_config/*.json` → `moduleConditions`）

| 模块 key | dutSim | auxRequired |
|----------|--------|-------------|
| str4/tdd | 2 | 1 |
| str4/driver_component | 0 | 0 |
| str4/driver_hardware | 0 | 0 |
| week/tdd | 1 | 1 |
| week/driver | 0 | 0 |

---

## 常见改动指引

| 目标 | 优先修改 |
|------|----------|
| 概览/详情 UI、按钮可见性 | `DeviceSelfCheckView.vue` + SCSS |
| 新 REST 能力 | `device-self-check.ts`（service）→ routes → `client/api` |
| 模块顺序/前置条件/用例元数据 | `self-check/case_config/*.json` + 重启 BFF |
| 用例逻辑 | `self-check/python/cases/.../caseN.py` + `case_info.json` |
| 报告格式 | `generateTestReport()` / `generateXlsx()` in service |
| 设备状态文案/颜色 | 前端 `getDisplayStatus` / `getStatusColor`；后端 `DeviceStatus` 枚举 |

**最小变更**：UI 纯展示尽量只动 Vue；流程变更需同时核对 SSE 事件与 `TestSession` 字段。

---

## 验证

```bash
cd tahp-console
npm run setup
npm test
# 可选 E2E
npx playwright test tests/e2e/self-check.spec.ts
```

本地需：Python 3、`adb` 可用设备（或 mock API 测 UI）。

---

## 延伸阅读

- API 端点、SSE 事件表、数据模型字段： [reference.md](reference.md)
- 流程细节与待办：`ai自检流程梳理.md`
- 原始界面规格：`ai自检设计文档.md`
