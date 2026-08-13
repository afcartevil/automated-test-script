# SIM 卡 PIN 锁分析指南

## 概述

PIN (Personal Identification Number) 是 SIM 卡的安全保护功能。当 SIM 卡设置了 PIN 码保护后，每次开机或重新插卡都需要输入正确的 PIN 码才能使用。

## 关键特征

### 1. 硬件识别正常，但无法注册网络

**典型表现**：
- ✅ SIM 卡硬件识别成功（有 ATR、ICCID）
- ✅ `+ESIMS:1,29` 识卡成功
- ❌ 无法注册网络，显示 `OUT_OF_SERVICE` 或 `Emergency calls only`
- ❌ 用户可能误以为是"无 SIM 卡"

### 2. 状态码特征

**simState 状态码**：
```
simState = 1  →  SIM_STATE_ABSENT (SIM 卡不存在)
simState = 2  →  SIM_STATE_PIN_REQUIRED (需要 PIN 码) ← PIN 锁定
simState = 5  →  SIM_STATE_READY (SIM 卡就绪)
simState = 6  →  SIM_STATE_NOT_READY (SIM 卡未就绪)
```

**onSimStateChanged 状态转换**：
```
onSimStateChanged 1 -> 2    ← 从 ABSENT 变为 PIN_REQUIRED
onSimStateChanged 2 -> 5    ← 从 PIN_REQUIRED 变为 READY（PIN 码已输入）
```

### 3. handleGetSimStatusResponse 中的 pin 字段

```
handleGetSimStatusResponse, result:0, state:1, pin:1, atr:80,3B9F94, icid:21,898800
                                                  ↑
pin:0 = 无需 PIN 码
pin:1 = PIN_REQUIRED (需要 PIN 码) ← PIN 锁定
pin:2 = 已解锁
```

## 关键日志

### 1. AT+CPIN 查询

**查询命令**：
```
AT> AT+CPIN?
```

**可能的响应**：
```
AT< +CPIN: READY        ← PIN 码已解锁，SIM 卡可用
AT< +CPIN: SIM PIN      ← 需要输入 PIN 码
AT< +CPIN: SIM PUK      ← PIN 码输入错误次数过多，需要 PUK 码
AT< +CPIN: SIM PIN2     ← 需要输入 PIN2 码（用于特定功能）
AT< +CPIN: SIM PUK2     ← PIN2 码输入错误过多，需要 PUK2 码
```

**参考标准**：3GPP TS 27.007 Section 10.4.2

### 2. 网络注册状态

**PIN 锁定时的网络状态**：
```
[GsmSST0] updateCarrierDisplayName: radio is on but out of service, 
                                    set plmn='Emergency calls only'

[GsmSST0] combinePsRegistrationStates: 
          mVoiceRegState=1(OUT_OF_SERVICE), 
          mDataRegState=1(OUT_OF_SERVICE)
```

### 3. 完整日志示例

```
# 插卡
13:40:15.632 [0] handleSimStateChanged, +ESIMS:1,12  ← 插卡

# 识卡成功
13:40:17.874 [0] handleSimStateChanged, +ESIMS:1,29  ← 识卡成功

# 状态变为 PIN_REQUIRED
13:40:17.889 [0] onSimStateChanged 1 -> 2  ← simState 变为 2 (PIN_REQUIRED)

# handleGetSimStatusResponse 显示 pin:1
13:40:17.884 [0] handleGetSimStatusResponse, result:0, state:1, pin:1, 
                  atr:80,3B9F94, icid:21,898800  ← pin:1 表示需要 PIN 码

# 网络状态变为 OUT_OF_SERVICE
13:40:17.938 [GsmSST0] updateCarrierDisplayName: radio is on but out of service, 
                        set plmn='Emergency calls only'

13:40:18.204 [GsmSST0] combinePsRegistrationStates: 
                        mVoiceRegState=1(OUT_OF_SERVICE), 
                        mDataRegState=1(OUT_OF_SERVICE)

# 系统查询 PIN 状态
13:42:34.307 [0] AT> AT+CPIN?
13:42:34.315 [0] AT< +CPIN: SIM PIN  ← 确认需要 PIN 码
```

## 判断流程

```
SIM 卡有 ICCID 和 ATR，但无法注册网络？
│
├─ 步骤 1：检查 AT+CPIN? 返回值
│   ├─ +CPIN: SIM PIN → PIN 锁定，需要输入 PIN 码
│   ├─ +CPIN: SIM PUK → PIN 码输入错误过多，需要 PUK 码
│   └─ +CPIN: READY → PIN 码已解锁，检查其他原因
│
├─ 步骤 2：检查 simState 是否为 2 (PIN_REQUIRED)
│   └─ onSimStateChanged 日志中查找 "1 -> 2" 或 "simState.*2"
│
├─ 步骤 3：检查 handleGetSimStatusResponse 中 pin 字段
│   └─ pin:1 表示 PIN_REQUIRED
│
└─ 步骤 4：检查网络状态
    └─ OUT_OF_SERVICE + Emergency calls only → 典型 PIN 锁定特征
```

## 常见误判

### ❌ 错误判断 1：看到 OUT_OF_SERVICE 就认为是网络问题
**正确做法**：
- 先检查 SIM 卡是否有 ICCID 和 ATR
- 如果有，再检查是否 PIN 锁定

### ❌ 错误判断 2：看到状态栏叉号就认为是"无 SIM 卡"
**正确做法**：
- 状态栏叉号可能表示：
  1. 无 SIM 卡（ABSENT）
  2. PIN 锁定（PIN_REQUIRED）
  3. 无网络服务（OUT_OF_SERVICE）
- 需要结合日志判断具体原因

### ❌ 错误判断 3：看到 `+ESIMS:1,29→0,1` 就认为是硬件问题
**正确做法**：
- 检查是否有 ATR 错误
- 检查是否有救卡流程 (`0,13→1,14`)
- 检查是否 PIN 锁定
- 未插卡时 `1,29→0,1` 是正常打印

### ✅ 正确判断：PIN 锁定的完整证据链
1. ✅ SIM 卡硬件识别成功（有 ATR、ICCID）
2. ✅ `+ESIMS:1,29` 识卡成功
3. ✅ `simState = 2` 或 `onSimStateChanged 1 -> 2`
4. ✅ `handleGetSimStatusResponse` 中 `pin:1`
5. ✅ `AT+CPIN?` 返回 `SIM PIN`
6. ✅ 网络状态 `OUT_OF_SERVICE` + `Emergency calls only`

## 解决方案

### 1. 输入 PIN 码解锁
- 用户需要在设置中输入正确的 PIN 码
- PIN 码通常是 4-8 位数字
- 默认 PIN 码通常是 `0000`、`1234` 或运营商提供的码

### 2. PIN 码输入错误处理
- PIN 码通常允许输入错误 3 次
- 超过 3 次后，SIM 卡会被锁定，需要 PUK 码解锁
- PUK 码由运营商提供，通常在 SIM 卡包装上

### 3. 关闭 PIN 码保护
- 如果用户不需要 PIN 码保护，可以在设置中关闭
- 关闭后，开机或重新插卡时不再需要输入 PIN 码

### 4. 告知用户
- 这不是硬件故障，而是 SIM 卡安全功能正常工作
- 需要用户输入 PIN 码才能使用 SIM 卡
- 如果忘记 PIN 码，联系运营商获取 PUK 码

## 实际案例

### 案例：OS162-36393

**用户反馈**：
- "No cellular network. Showing no sim card"
- 视频显示两张卡都有叉号

**初步判断**：
- 误以为是"无 SIM 卡"或硬件故障

**实际分析**：
```
13:40:17 Slot 0 识卡成功，有 ICCID、ATR
13:40:17 simState 变为 2 (PIN_REQUIRED)
13:40:17 handleGetSimStatusResponse pin:1
13:40:18 网络状态 OUT_OF_SERVICE
13:42:34 AT+CPIN? 返回 SIM PIN
```

**最终结论**：
- Slot 0: PIN 锁定，需要输入 PIN 码
- Slot 1: 未插卡
- 不是硬件故障，是 SIM 卡安全功能正常工作

## 参考资料

- 3GPP TS 27.007 Section 10.4.2 - Enter PIN (+CPIN)
- 3GPP TS 31.101 - UICC-terminal interface
- Android TelephonyManager.SIM_STATE_* 常量定义
