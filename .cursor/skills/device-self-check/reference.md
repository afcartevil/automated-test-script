# AI 自检 — 参考手册

## REST API

Base：`/api/tahp/device-self-check`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/devices` | 设备列表 |
| POST | `/devices/refresh` | ADB 刷新 |
| GET | `/devices/:deviceId` | 设备 + session |
| POST | `/devices/:deviceId/role` | 设置角色 |
| POST | `/devices/:deviceId/test/start` | `{ testType, flash? }`；`flash` 含刷机包路径等 |
| POST | `/devices/:deviceId/test/custom-start` | `{ selectedCases[], customAuxDeviceIds[] }` |
| POST | `/devices/:deviceId/test/continue` | 前置条件满足后继续 |
| POST | `/devices/:deviceId/test/resume` | 错误状态恢复测试（从当前/报错模块继续） |
| POST | `/devices/:deviceId/test/end` | 终止当前测试（杀用例进程、停 monkey），生成部分报告后设备恢复空闲 |
| POST | `/devices/:deviceId/case-result` | 人工改结果 |
| POST | `/devices/:deviceId/case/retest` | 单用例复测 |
| GET | `/module-conditions` | 模块配置全集 |
| GET | `/case-catalogs` | 用例大类（分组） |
| GET | `/case-catalogs/:testType/detail` | 用例详情（含 `case_info.json` 手动步骤） |
| POST | `/manual-decision` | `{ decisionId, decision }` |
| GET | `/devices/:deviceId/pending-manual-decision` | 待处理人工确认 |
| GET/POST | `/settings` | `autoRetestEnabled` / `autoRetestCount` 等 |
| POST | `/flash/pick-path` | 本地选择刷机包路径 |
| GET | `/pipeline` | 流水线阶段状态 |
| GET | `/reports` | 测试报告列表（`sinceHours` / `pendingOnly`） |
| GET | `/reports/:reportId` | 报告详情（含 `allCaseItems`） |
| POST | `/reports/:reportId/review` | 报告审阅（`reviewed` / `retest` / `pending`） |
| POST | `/reports/:reportId/case-result` | 修改报告中单用例结果（仅 JSON，不跑用例） |
| POST | `/reports/:reportId/retest` | 从报告复测单用例（需设备空闲，完成后回写报告并恢复空闲） |
| GET | `/tpower/status` | T-Power 连接探测 |
| GET/POST | `/tpower/config` | T-Power 配置 |
| GET | `/events` | SSE 流 |

`selectedCases` 元素格式：`{testType}/{module}/{caseIndex}`，例：`str4/tdd/5`。

---

## SSE 事件

| 事件 | 数据要点 |
|------|----------|
| `device_list_updated` | `{ devices }` |
| `device_updated` | `{ device }` |
| `test_started` | `{ deviceId, testType, session }` |
| `test_completed` | `{ deviceId, session }` |
| `report_ready` | `{ deviceId, resultDir }` — 报告落盘后触发，前端据此刷新「测试报告」 |
| `test_ended` | `{ deviceId }` |
| `case_completed` | `{ deviceId, caseKey, result }` |
| `step_update` | `{ caseKey, step }` |
| `precheck_failed` | `{ deviceId, module, reason, type }` |
| `manual_confirm` | `{ decisionId, caseKey, message }` |

`caseKey` 格式：`{testType}/{module}/{caseIndex}`。

---

## 核心类型（前端 `device-self-check.ts`）

### DeviceRole / DeviceStatus

- 角色：`未分配` | `测试机` | `辅测机`（概览空闲卡片显示「未分配」即使 role 为测试机）
- 状态：`空闲` | `初始化中` | `等待测试开始` | `测试中` | `不满足前置条件` | `完成(通过)` | `完成(失败)` | `错误` | `占用中` | `待命`

### CaseResult.status

`未开始` | `进行中` | `通过` | `失败` | `部分通过` | `待确认` | `NA` | `跳过`

### TestSession 关键字段

```typescript
{
  deviceId, testType, modules, currentModuleIndex,
  moduleProgress, caseResults, isRunning,
  auxiliaryDevices,        // 运行时分配的辅测机
  selectedCases?,          // custom 专用
  customAuxDevices?,       // custom 启动时指定
}
```

---

## Python 用例协议

`run_case.py` 子进程 stdout 每行一个 JSON：

```json
{"type":"step","step":"步骤描述-成功|失败|进行中"}
{"type":"manual_confirm","message":"请确认..."}
{"status":"pass","message":"结论","full_automation":true}
```

人工确认时 BFF 向子进程 stdin 写入 `pass` 或 `fail`。

用例 `run()` 返回同上最终 JSON。模块级 `init.py` 通过 `importlib` 执行 `run()`（非 spawn）。

---

## 用例目录结构

```
self-check/
├── case_config/
│   ├── str4_tdd.json
│   ├── str4_driver_component.json
│   ├── str4_driver_hardware.json
│   ├── week_tdd.json
│   └── week_driver.json
└── python/
    ├── case.json
    ├── case_catalog.py
    ├── run_case.py
    ├── cases/str4|week/{module}/case{N}.py
    ├── cases/.../case_info.json
    ├── cases/.../init.py
    └── utils/device_init.py, tdd/, driver/
```

`case_config` JSON 字段：`test_type`, `module`, `module_label`, `conditions`, `default_case_mode`, `cases[]`（含 `case_index`, `case_name`, `mode`, `can_reuse`）。

---

## 结果复用 mirrorResult

条件：用例 `status === '通过'` 且 `canReuse === true` 且存在 `auxiliaryDevices`。

行为：深拷贝结果到辅测机 session，`message` 追加「（镜像自 {sourceDeviceId}）」。失败/待确认不镜像。

---

## 设备刷新策略 refreshDevices

保留状态：`初始化中` | `等待测试开始` | `测试中` | `不满足前置条件` | `待命` | `占用中` | `完成(*)` | `错误`

断开 ADB 的设备从内存移除；空闲设备更新 SIM 信息。

---

## 前端状态变量速查（`useDeviceSelfCheck.ts`）

| 变量 | 用途 |
|------|------|
| `activeTab` | 顶层 Tab：`overview` / `planning` / `devices` / `gerrit` / `review` |
| `viewMode` | 设备执行内层：`list` / `customTest` |
| `catalogPanelExpanded` | 用例大类展开面板是否显示 |
| `deviceDetailExpanded` | 设备详情面板是否展开（列表保持可见） |
| `devices` | 设备列表 |
| `selectedDeviceId` / `selectedDevice` | 详情 `{ device, session }` |
| `moduleConditions` | 用例树数据源 |
| `caseCatalogGroups` | 顶部用例卡片 + 自定义测试目录 |
| `catalogDetailItems` / `selectedCatalogItem` | 用例大类详情页数据 |
| `catalogTypeSettings` | 用例详情页自动复测（`autoRetestEnabled` / `autoRetestCount`） |
| `expandedCatalogDetailModules` / `selectedCatalogCaseKey` | 用例详情页展开/选中 |
| `expandedCatalogTypes` / `expandedCatalogModules` | 自定义测试展开 |
| `selectedCases` | 自定义测试勾选 |
| `customTestDutDeviceId` / `customTestAuxDeviceIds` | 自定义 DUT/辅测 |
| `selectedTestType` | 详情页 str4/week 选择 |
| `enableFlash` / `flashPath` / `flashStageVersion` | 刷机开关与参数 |
| `manualDecision` | 人工确认弹窗 |
| `pipelineStatus` / `reportSummaries` | 流水线与报告摘要 |
| `eventSource` | SSE 连接 |

---

## 设置 `AutoTestSettings`

```typescript
{
  autoTestEnabled: Record<string, boolean>   // 遗留字段，无独立设置页
  autoTestPath: Record<string, string>
  autoRetestEnabled?: Record<string, boolean>  // 按 testType
  autoRetestCount?: Record<string, number>
}
```

持久化：`tahp-console/packages/server/src/services/tahp/self-check/settings.json`（运行时生成）。

---

## 未实现 / 遗留

- T 卡升级（若 UI 仍有 checkbox，以代码为准）
- `autoTestEnabled` / `autoTestPath` 无独立设置页，后端未用于调度
- 设计文档 `ai自检*.md` 可能与 V0.8 不完全一致，以代码为准
