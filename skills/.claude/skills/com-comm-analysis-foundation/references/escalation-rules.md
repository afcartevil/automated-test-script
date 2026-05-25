# Escalation Rules Reference

## 1. 目的

本文件用于统一通信售后问题的升级路径，避免两种常见低效动作：

- 证据不足就直接甩给平台方
- 明明断点已经很清楚，却还在错误层面反复兜圈

核心原则：**先找断点，再决定升级对象。**

---

## 2. 通用升级判断规则

在决定升级前，至少先回答这 4 个问题：

1. 正常流程走到了哪一步？
2. 从哪一步开始缺失 / 被拒绝 / 中断？
3. 断点位于哪一层：App / Framework / Telephony / RIL / Modem / Network / Carrier Config / Hardware？
4. 当前证据是否足以支持这个判断？

如果这 4 个问题都回答不出来，先别急着升级，先补证据。

---

## 3. 按问题类型的升级建议

## 3.1 Call / IMS 类

### 升级到上层（App / Framework / Dialer / Telecom）

当出现以下证据时：

- `Telecom.*Event.*CREATED` 都没有
- 来电已上报，但 InCall bind 失败
- `onConnected` 没出现或界面未拉起
- 音频路由、铃声、视频选卡问题明显停在上层流程

### 升级到 Telephony / RIL / Modem / Protocol

当出现以下证据时：

- 上层流程已走通，但 `SET_DISCONNECTED` 为 `error`
- IMS / CS 协议流程中途被拒绝或中断
- `INVITE / PRACK / RELEASE / Cause / Reason` 已明确指向底层或网络侧

### 升级到运营商 / 网络侧

当出现以下证据时：

- DUT / REF 同地点同卡同网现象一致
- 协议日志显示网络拒绝、补充业务权限缺失或媒体承载异常
- 业务开通、套餐、TAS / XCAP / 网络策略明显不满足

---

## 3.2 Network / APN / 搜网类

### 升级到 Android 显示 / 配置侧

当出现以下证据时：

- `OPERATOR` 返回值正常，但 `updateSpnDisplay` 最终显示错误
- 搜网列表在底层返回完整，但界面展示不全或误判重复
- 图标显示逻辑与实际能力不一致

### 升级到配置 / 产品 / 客制化维护方

当出现以下证据时：

- `rawSpn / rawPlmn / newSpn` 显示配置异常
- APN 参数与运营商官方要求不一致
- 多语言 SPN / PLMN 客制配置未覆盖

### 升级到运营商 / 网络侧

当出现以下证据时：

- `OPERATOR` / `DATA_REGISTRATION_STATE` 本身就异常
- 搜网列表显示 `FORBIDDEN`，明确是接入限制
- 运营商下发值缺失、PLMN 为空或网络能力未满足

---

## 3.3 SIM 类

### 升级到硬件侧

当出现以下证据时：

- Modem 没有任何插卡上报
- 所有卡都不识别
- 没收到 ATR
- 反复掉卡且明显与卡槽接触 / 干扰相关
- 热插拔关闭后问题消失，或怀疑 polarity 配置错误

### 升级到 RIL / Uicc / Framework

当出现以下证据时：

- Modem 已上报插卡，但 `EVENT_ICC_STATUS_CHANGED / UNSOL_RESPONSE_SIM_STATUS_CHANGED` 未正确消费
- READY / LOADED 广播异常
- `onAllRecordsLoaded` 已完成，但上层状态/显示异常

### 升级到卡 / 运营商侧

当出现以下证据时：

- 只有个别卡异常，多机复现
- `CARD_RESTRICTED`
- PIN / PUK 锁卡由卡侧状态决定

---

## 3.4 Stability / Modem EE 类

### 升级到平台方（芯片 / Modem 团队）

当出现以下证据时：

- 已抓到 `Modem exception` / `[ASSERT]` / `[Fatal error]`
- 已拿到 ASSERT 文件路径、行号、P1/P2/P3
- 本地无法进一步闭环，需要符号表 / 平台闭源模块支持

### 升级到硬件侧

当出现以下证据时：

- 市场客诉类 EE，且更像 Modem 加载失败
- 单机问题明显，换机/换环境后不复现
- 疑似供电、RF、板级异常引发 EE

### 升级到系统 / 产品侧

当出现以下证据时：

- IO loading 过高导致资源抢占
- OTA 流程被打断导致 NV / 分区数据损坏
- 版本集成、patch 依赖漏合、系统策略引发间接触发

---

## 4. 升级前必须带上的材料

## 4.1 通用材料

- 问题现象描述
- 问题时间点
- 机型 / 平台 / 软件版本 / baseband 版本
- SIM / 运营商 / 卡槽信息
- DUT / REF 对比结果
- 视频 / 截图
- 复现步骤
- 完整日志包

## 4.2 Modem EE 特殊材料

若升级到平台方，资料要求至少补齐：

1. 问题时间点的 `MD log`
2. `MD dump bin`
3. `AP log`
4. 对应版本的 `Modem ELF`
5. `DbgInfo_XXX all files`
6. ASSERT 文件路径、行号、P1/P2/P3

## 4.3 SPRD dump 相关材料

如为展锐 dump 问题，建议补齐：

- 含 `.dmp` 与 `minidump` 的 dump log
- 问题版本信息
- 版本对应符号表（如 `.axf`）

---

## 5. 不建议升级的典型情况

下面这些情况，先别急着往外抛：

- 只有一句“有问题”，没有时间点
- 只给截图，没有日志
- 没做 DUT / REF 对比
- 还没搞清楚断点在哪一层
- APN 改动没有运营商官方依据
- SIM 问题没做多卡/多机交叉验证
- EE 问题没有 ASSERT 关键信息

这类单子如果直接升级，十有八九会被打回来。工程界的回旋镖，飞得都挺准。

---

## 6. 输出建议

接力分析时，统一复用 `SKILL.md` 的标准输出模板，不再单独维护第二套完整模板。

本文件只补充 3 个额外要求：

1. **明确为什么需要接力**：是证据已经足够，还是当前层已定位清楚但需要下一责任层继续闭环。
2. **明确承接对象**：不要只写“升级平台”这种大而化之的说法，要写清是 App / Framework / Telephony / RIL / Modem / Network / Carrier Config / Hardware 中的哪一类。
3. **明确交接材料**：日志包、视频、版本、DUT/REF 结果、当前结论缺一不可。

---

## 7. 最后一句原则

**升级不是甩锅，是把问题交给“最有证据支持的下一责任层”。**

这两者看起来很像，实际上差别挺大。 
