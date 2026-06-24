# L2 SIM 卡分析 Playbook

## 5 步分析流程

### 第一步：确认基本信息与定位时间窗

**1a. 定位问题时间点（按优先级）：**
1. 日志包中的截图/录屏文件名时间戳（如 `Screenshot_20260330-121443.jpg` → 12:14:43，`Screen_Recording_20260330_143548.mp4` → 14:35:48）。这是设备本地时间，与日志时间戳一致，最准确
2. 截图/录屏内容中状态栏显示的时钟时间（辅助验证）
3. 如果没有图片或视频，以 Jira 描述中的"最后一次问题发生时间"为准
4. 兜底：在 radio_log 中搜索 SIM 异常事件（+ESIMS:0,1 / 0,13 / AnswerToReset），取最近的事件簇时间

**1b. 确认基本信息：**
- 从 Jira 确认：几张卡、哪个 slot、问题现象
- 从截图确认：状态栏有几个 SIM 图标（判断单卡/双卡）、是否有叉号/无信号
- 从 `analysis.l0_baseline` 获取主日志组
- 从 `analysis.l1_business` 确认 primary_domain = `sim`

**1c. 确认插卡状态：**
- 通过截图中 SIM 图标数量判断单卡/双卡
- 通过 Jira 描述或评论确认哪些 slot 插了卡
- 仅凭日志无法 100% 确认某个 slot 是否插卡（`+ESIMS:1,29→0,1` 和 ICCID 字段长度均不能作为判断依据）
- 未插卡的 slot 开机时 `+ESIMS:1,29→0,1` 是正常打印，不要误判为硬件问题

### 第二步：硬件问题排查（优先级最高）
按 `sim-hardware.md` 执行 ATR 检测和热插拔分析。
- 有 ATR 错误 → 硬件接触问题，优先级最高
- 无 ATR 错误 → 继续后续分析

### 第三步：AT+ESIMS 序列分析
按 `sim-at-esims.md` 提取并分析所有 `handleSimStateChanged, +ESIMS` 日志。
- 识别不识卡模式（`1,29→0,1`）
- 识别救卡流程（`0,13→1,14`）和快速救卡（`0,23→1,24`）
- 识别 sim busy 重试（`handleGetSimStatusResponse, sim busy`）
- 热插拔序列是否完整

### 第四步：状态流转分析
按 `sim-state-flow.md` 提取 `updateSimState` / `onSimStateChanged` 日志。
- 判断是否达到 LOADED
- 识别异常转换（ABSENT→CARD_IO_ERROR 等）
- 分析时间间隔是否正常

### 第五步：特殊场景检测

#### PIN 锁检测（重要！）
**关键日志**：
1. **AT+CPIN 查询**：
   ```
   AT> AT+CPIN?
   AT< +CPIN: SIM PIN    ← SIM 卡需要 PIN 码
   AT< +CPIN: READY      ← SIM 卡已解锁
   AT< +CPIN: SIM PUK    ← PIN 码输入错误次数过多，需要 PUK 码
   ```

2. **simState 状态码**：
   - `simState = 1` = `SIM_STATE_ABSENT` (SIM 卡不存在)
   - `simState = 2` = `SIM_STATE_PIN_REQUIRED` (需要 PIN 码)
   - `simState = 5` = `SIM_STATE_READY` (SIM 卡就绪)
   - `simState = 6` = `SIM_STATE_NOT_READY` (SIM 卡未就绪)

3. **onSimStateChanged 日志**：
   ```
   onSimStateChanged 1 -> 2    ← 从 ABSENT 变为 PIN_REQUIRED
   onSimStateChanged 2 -> 5    ← 从 PIN_REQUIRED 变为 READY（PIN 码已输入）
   ```

4. **handleGetSimStatusResponse 中的 pin 字段**：
   ```
   handleGetSimStatusResponse, result:0, state:1, pin:1, atr:..., icid:...
                                                      ↑
   pin:0 = 无需 PIN 码
   pin:1 = PIN_REQUIRED (需要 PIN 码)
   pin:2 = 已解锁
   ```

5. **网络状态特征**：
   - PIN 锁定时，SIM 卡硬件识别成功（有 ATR、ICCID）
   - 但无法注册网络，显示 `OUT_OF_SERVICE` 或 `Emergency calls only`
   - 用户可能误以为是"无 SIM 卡"，实际是 PIN 锁定

**判断流程**：
```
SIM 卡有 ICCID 和 ATR，但无法注册网络？
├─ 检查 AT+CPIN? 返回值
│   ├─ SIM PIN → PIN 锁定，需要输入 PIN 码
│   ├─ SIM PUK → PIN 码输入错误过多，需要 PUK 码
│   └─ READY → PIN 码已解锁，检查其他原因
├─ 检查 simState 是否为 2 (PIN_REQUIRED)
└─ 检查 handleGetSimStatusResponse 中 pin 字段是否为 1
```

**常见误判**：
- ❌ 看到 `OUT_OF_SERVICE` 就认为是网络问题
- ❌ 看到状态栏叉号就认为是"无 SIM 卡"
- ✅ 正确判断：有 ICCID/ATR 但无法注册网络 → 检查 PIN 锁

#### eSIM 占用检测（仅 slot 1）
- eSIM 占用：`eSIM ignore hot plug`
- Modem 异常：`Assert` / `ModemEE` / `PhoneCrash`
- **eSIM 开关检测**：
  - 搜索 `MIPC_SIM_ESIM_SWITCH_SET_REQ`，MODE=01 表示 eSIM 开关已打开
  - eSIM 开关打开时，Slot 1 热插拔不会产生 `+ESIMS:0,11/1,12`，属正常行为
  - 通过 `eid:32,` 非 0 确认该 slot 为 eSIM 卡槽
  - 详见 `sim-hardware.md` eSIM 开关状态检测章节

## 问题分类

| 分类 | 关键证据 |
|------|---------|
| `HARDWARE_NO_ATR` | `AnswerToReset` 错误 + `No ATR` + `+ESIMS:0,1` |
| `SIM_ACCESS_ERROR` | `+ESIMS:1,29→0,1` + 后续有救卡/拔出（确认已插卡） |
| `HOT_PLUG_ISSUE` | 快速插拔（间隔 < 2s）或多次连续插拔 |
| `PIN_LOCK` | `updateSimState: PIN_REQUIRED` + 无后续 READY |
| `RECOVERY_SUCCESS` | `+ESIMS:0,13` + `+ESIMS:1,14` + 状态恢复 |
| `RECOVERY_FAILED` | `+ESIMS:0,13` 无 `+ESIMS:1,14` |
| `ESIM_CONFLICT` | `eSIM ignore hot plug` + `MSG_ID_SIM_ERROR_IND` |
| `MODEM_CRASH` | `Assert` / `ModemEE` |
| `SIM_BUSY` | `sim busy, may retry` 多次重试 |
| `SIM_CARD_TECHNICAL_PROBLEM` | `+ESIMS:0,17` |
| `NORMAL` | 正常识卡 |

## 注意事项
1. 优先级：硬件问题 > 状态异常 > 特殊场景
2. 每个结论必须有完整的证据链
3. 所有分析围绕第一步定位的时间窗展开
4. 明确区分 slot 0 和 slot 1，先确认哪些 slot 插了卡
5. grep 结果被截断时必须分时间段追查，不能基于不完整数据下结论
6. 搜索关键字清单见 `sim-log-keywords.md`，按 P0→P3 逐一搜索
