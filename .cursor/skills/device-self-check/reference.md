# AI 自检 — 参考手册

## REST API

Base：`/api/tahp/device-self-check`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/devices` | 设备列表 |
| POST | `/devices/refresh` | ADB 刷新 |
| GET | `/devices/:deviceId` | 设备 + session |
| POST | `/devices/:deviceId/role` | 设置角色 |
| POST | `/devices/:deviceId/test/start` | `{ testType: 'str4' \| 'week' }` |
| POST | `/devices/:deviceId/test/custom-start` | `{ selectedCases[], customAuxDeviceIds[] }` |
| POST | `/devices/:deviceId/test/continue` | 前置条件满足后继续 |
| POST | `/devices/:deviceId/test/end` | 结束/释放 |
| POST | `/devices/:deviceId/case-result` | 人工改结果 |
| POST | `/devices/:deviceId/case/retest` | 单用例复测 |
| GET | `/module-conditions` | 模块配置全集 |
| GET | `/case-catalogs` | 用例大类（分组） |
| POST | `/manual-decision` | `{ decisionId, decision }` |
| GET | `/devices/:deviceId/pending-manual-decision` | 待处理人工确认 |
| GET/POST | `/settings` | 自动化脚本开关 |
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

## 前端状态变量速查

| 变量 | 用途 |
|------|------|
| `devices` | 概览设备列表 |
| `selectedDevice` | 详情 `{ device, session }` |
| `moduleConditions` | 设置页 + 用例树数据源 |
| `caseCatalogGroups` | 概览大类 + 自定义测试目录 |
| `expandedOverviewTypes` | 概览大类展开 |
| `expandedCatalogTypes` / `expandedCatalogModules` | 自定义测试展开 |
| `selectedCases` | 自定义测试勾选 |
| `customTestDutDeviceId` / `customTestAuxDeviceIds` | 自定义 DUT/辅测 |
| `selectedTestType` | 详情页 str4/week 选择 |
| `manualDecision` | 人工确认弹窗 |
| `eventSource` | SSE 连接 |

---

## 未实现 / 占位功能

- 刷机、T 卡升级（详情页 checkbox + 路径输入，无后端）
- 概览/详情「打开结果」按钮（部分仅 UI，需接 `resultDir` 或报告下载）
- `ai自检设计文档.md` 中部分设置项可能与当前 `AutoTestSettings` 不完全一致，以代码为准
