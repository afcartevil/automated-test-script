# 测试项集成 — 参考手册

## case_config JSON 字段

路径：`tahp-console/packages/server/src/services/tahp/self-check/case_config/{testType}_{module}.json`

```json
{
  "testType": "monkey",
  "module": "monkey",
  "moduleLabel": "monkey测试",
  "conditions": {
    "dutSimCount": 0,
    "auxRequired": 0,
    "auxSimCount": 0
  },
  "defaultCaseMode": "solo",
  "cases": [
    { "caseIndex": 1, "caseName": "monkey测试", "canReuse": false }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `conditions.dutSimCount` | DUT 所需 SIM 卡数 |
| `conditions.auxRequired` | 辅测机数量（0/1） |
| `conditions.auxSimCount` | 辅测机 SIM 数 |
| `cases[].canReuse` | 是否允许结果复用（同模块历史 pass 跳过） |
| `defaultCaseMode` | `solo` / `aux_for_dut_mirror`（当前运行时未读取，仅文档） |

---

## 执行形态对照

| 形态 | 用例 `run()` 行为 | Session 结束时机 | 停止要求 |
|------|-------------------|------------------|----------|
| **同步**（str4/week 多数用例） | 阻塞至完成，返回 pass/fail | 全部模块跑完 | `endTest` 释放设备即可 |
| **后台启动**（monkey） | 启动命令成功即 pass | 单模块用例结束即 `finishTest` | **必须**在 `endTest` 调工具 stop |
| **人工**（无 py） | 返回 pending | 等待 `manual-decision` | 无后台进程 |
| **custom 勾选** | 按勾选顺序执行各 case | 同同步/后台混合 | 按各用例形态分别处理 |

---

## 生命周期能力实现模式

### 模式 A：同步用例（默认）

```
startTest → runTestFlow → execPythonCase (timeout 120s) → pass/fail → finishTest
```

无需额外 stop；`endTest` 中断当前 spawn（若仍在跑）。

### 模式 B：后台启动 + endTest 停止（monkey）

```
startTest → case1.py → subprocess: tool start → return pass
         → runTestFlow 结束 → 设备状态 完成(通过)
         → 设备侧 tool 继续运行

endTest → stopXxxForDevice() → subprocess: tool stop → 释放 session
```

集成后台测试时**必须**：

1. 工具提供可靠 `start` / `stop`（同一 deviceId 维度）
2. Node 在 `endTest` 调用 stop（即使用户未等 watchdog 自停）
3. 文档写明：UI「结束测试」= 停止后台任务 + 释放设备

### 模式 C：需 BFF 状态 API（未在 monkey 实现）

若 UI 要展示「运行中 / 剩余时长」：

1. 工具提供 `status` 子命令
2. 新增 `GET /devices/:id/{tool}-status` 路由
3. 前端轮询或 SSE 推送

**未在能力矩阵中声明模式 C 时，不要半成品暴露 API。**

---

## AutoTestSettings 扩展示例

服务端 `device-self-check.ts`：

```ts
interface AutoTestSettings {
  autoTestEnabled: Record<string, boolean>
  autoTestPath: Record<string, string>
  autoRetestEnabled?: Record<string, boolean>
  autoRetestCount?: Record<string, number>
  monkeyDuration?: string   // monkey 专属
  // 新类型：在此增加字段 + normalize 函数 + save 校验
}
```

持久化：`self-check/settings.json`  
API：`GET/POST /api/tahp/device-self-check/settings`

新字段 checklist：

- [ ] 接口类型（server + client api）
- [ ] 默认值（`getSettings`）
- [ ] 校验（`saveSettings`）
- [ ] 传入 `buildDeviceInfo()` / `device_info`
- [ ] 前端设置面板读写

---

## 前后端同步改动对照表

| 关注点 | 后端 | 前端 |
|--------|------|------|
| 测试类型 union | `StandardTestType` | `api/.../device-self-check.ts` |
| 模块顺序 | `getModulesForTestType` | `MODULE_ORDER`（排序一致） |
| 展示名称 | `getAllCaseCatalogs` labels | `getTestTypeLabel` / `getModuleLabel` |
| 启动入口 | `POST .../test/start` body | `handleStartTest` / 设备详情按钮 |
| 类型设置 | `AutoTestSettings` | 用例大类面板 `catalogTypeSettings` 或等价 |
| 停止 | `endTest` + 钩子 | `handleEndTest`（已有） |

---

## AI 测试自规划 — 测试规划选择项（已下线）

> **2026-09 起本节废止**：「AI 测试自规划」已整体从代码库删除（`test-planning.ts` / `test-plan-executor.ts` / `api/tahp/test-planning.ts` / `TestPlanSettingsModal.vue` / `PlannedTestType`），定时指派由中心 BFF「任务中心 → 质量验测 → 定时任务」接管。新增测试类型无须任何规划侧改动；如需进入中心指派目录，见 BFF 验测任务 catalog 推送（`PUT /api/tahp/sync/verify/catalog`）。

---

## 完整文件 Checklist（新标准 testType）

### Python / 配置

- [ ] `case_config/{type}_{module}.json`
- [ ] `python/cases/{type}/{module}/case_info.json`
- [ ] `python/cases/{type}/{module}/case{N}.py`
- [ ] `python/cases/{type}/{module}/init.py`（可选）
- [ ] `python/tools/...`（可选）
- [ ] `loadCaseConfigs` 注册文件名

### 后端 TypeScript

- [ ] `StandardTestType` / `DeviceTestType`
- [ ] `getModulesForTestType`
- [ ] `getAllCaseCatalogs` labels/order
- [ ] `buildDeviceInfo` / settings
- [ ] `endTest` 停止钩子（后台类）
- [ ] `getAutoRetestConfig`（如需要）
- [ ] `routes/.../device-self-check.ts` start body 类型

### 前端

- [ ] `api/tahp/device-self-check.ts`
- [ ] `self-check-utils.ts`
- [ ] `useDeviceSelfCheck.ts`
- [ ] `SelfCheckDeviceRun.vue`（+ Checklist 如需要）

### 测试

- [ ] `tests/server/device-self-check-{type}.test.ts`
- [ ] 更新既有 `self-check` 相关测试

---

## Monkey 参考实现

### 工具命令（`python/tools/monkey_usd/monkey_test.py`）

| 子命令 | 用途 | 自检是否使用 |
|--------|------|----------------|
| `start -d <duration> --save-log` | 启动并后台 watchdog | case1.py |
| `stop` | 停止 monkey + watchdog | `endTest` → `stopMonkeyForDevice` |
| `status` | 查询状态 | 未接入 BFF |

时长：`Nm` 分钟、`Nd` 天，兼容 `Nh`/`Ns`/组合；默认 `7d`，脚本侧最大约 `14d`。

黑名单：`MonkeyBlackList.txt` 与脚本同目录，由工具推送到设备。

### case1.py 要点

- 从 `device_info.DUT[0].device_id` 或 `monkeyDuration` 读参数
- `subprocess.run` 启动，**60s 超时**（仅覆盖 launch，不等待 7d）
- 成功 → `status: pass`, `full_automation: true`

### 规划自动执行刷机

`buildPlannedTestFlashPayload(deviceId, 'monkey')`：

- `enabled: true`，`resolveLatestDailyFlashPackage`，`stageVersion: 'Open'`
- 尝试 `archive/Root/` 下 Root 包 → `rootPkgPath`

`smoke` / `str4` / `week`：仅 daily 主包，无 Root。

### 相关测试

`tests/server/device-self-check-monkey.test.ts`：

- catalog 含 `monkey测试`
- `case_info` 仅名称、无手动步骤
- `getSettings().monkeyDuration` 有默认值

---

## Python stdout 协议（摘要）

| 行类型 | JSON | 行为 |
|--------|------|------|
| 步骤 | `{"type":"step","step":"..."}` | SSE 更新 UI |
| 人工 | `{"type":"manual_confirm",...}` | 阻塞 stdin |
| 结果 | `{"status":"pass","message":"...","full_automation":true}` | 用例终态 |

Node 映射：`pass`→通过，`fail`→失败，`pending`→待确认，`skip`→跳过。
