---
tahp_adapt_skill: true
name: kb-skill-telephony-carrier-porting-mpqmp9rg
domain_label: "telephony — carrier_porting"
domain_id: "kb-skill-telephony-carrier-porting-mpqmp9rg"
module: "通信"
module_raw: "telephony"
func_type: "运营商移植"
func_type_raw: "carrier_porting"
category: "AI自动化适配"
funcType: "运营商移植"
group: "通信"
status: "deprecated"
generated_from_knowledge: true
generated_from_entries: '["kb-53ac5810","kb-58d1895c","kb-5ee13372","kb-8967ab63","kb-8979e91b","kb-a0dc0d77"]'
created_at: "2026-05-29T07:58:11.096Z"
source: knowledge_base
---

# Android网络问题（SPN/APN/RAT/搜网）日志分析与故障排查

## 适用场景
- 适用模块：通信模块
- 适用业务类型：运营商移植
- 典型触发条件：
  - SPN/PLMN 显示与预期不符（如运营商名称显示错误、显示为空或不随网络变化）
  - APN 配置异常，与对比机或运营商规范不一致，导致数据业务失败
  - RAT（网络制式）/IMS（VoLTE/VoWiFi）图标不显示或状态异常
  - 手动搜网列表重复、缺失，或搜网失败

## ⚠️ 不适用情况（请人工补充）
- 仅在运营商名称显示或 APN 配置已确认与运营商需求文档不符时，才执行修改操作；若无官方依据，属于需求未明确场景，待人工确认。
- 日志显示搜网失败原因并非协议栈或配置问题，而是硬件射频校准或天线问题，属于硬件领域，待人工确认。

## 核心处理方法

### 一、SPN/PLMN 显示问题定位

#### MTK 平台
1. 抓取 Android Log，过滤 `ServiceStateTracker` 相关日志。
2. 搜索关键字：`MTKSST`、`updateCarrierDisplayName`、`updateSpnDisplay`。
3. 关键日志解析：
   ```
   //网络返回的运营商长名和短名
   D RILJ    : [0668]< OPERATOR {MD8475B_SmartStudio, MD8475B, 65010} [PHONE0]
   //更新运营商名称
   D MTKSST  : [GsmSST1] updateCarrierDisplayName: rawSpn = Airtel ZM
   D MTKSST  : [GsmSST1] updateSpnDisplay: rule = 3
   D MTKSST  : [GsmSST1] notifyCarrierDisplayNameDataChanged: changed sending intent, rule=3, CarrierDisplayNameData={ spn = null, dataSpn = Airtel ZM, showSpn = false, plmn = No service, showPlmn = true, subId=1
   ```
    - `OPERATOR` 中的 `PHONE0` 代表 SIM 卡 1，`PHONE1` 代表 SIM 卡 2。
    - `rawSpn` 为厂商配置名称，`plmn` 为网络下发名称。
    - `notifyCarrierDisplayNameDataChanged` 是最终显示结果汇总，包含 `showSpn`、`showPlmn` 等标志。
    - `[GsmSST0]` 对应 SIM 卡 1，`[GsmSST1]` 对应 SIM 卡 2。

4. 异常判断：对比配置项（如 `rawSpn`、`dataSpn`）与最终显示的 `showSpn`/`showPlmn`，若不一致则定位为显示逻辑异常。

#### 展锐平台
1. 抓取 Android Log，过滤 `SST` 相关日志。
2. 搜索关键字：`SST`、`updateSpnDisplayLegacy`、`updateSpnDisplay`。
3. 关键日志解析：
   ```
   D SST     : [0] updateSpnDisplayLegacy+
   D SST     : [0] updateSpnDisplay: rawPlmn = Etisalat e&
   D SST     : [0] updateSpnDisplay: newSpn = null , rawSpn = 
   D SST     : [0] updateSpnDisplay: updateSpnDisplay: changed sending intent, rule=2, showPlmn='true', plmn='e&', showSpn='false', spn='e&', dataSpn='', subId='26'
   ```
    - `newSpn` 为客制化显示名称，`rawSpn` 为第三方获取名称。
    - `updateSpnDisplay: changed sending intent` 包含最终显示策略。
    - `[0]` 对应 SIM 卡 1，`[1]` 对应 SIM 卡 2。

4. 异常判断逻辑与 MTK 平台类似，对比原始值与最终 `showSpn`/`showPlmn` 标志。

#### 高通平台
1. 抓取 Radio Log，过滤 `SST` 或 `QtiServiceStateTracker` 相关日志。
2. 搜索关键字：`SST`、`updateSpnDisplay`、`getCarrierDisplayNameLegacy`。
3. 关键日志解析：
   ```
   // 网络返回运营商名称
   D RILJ    : [9500]< OPERATOR {CMCC, CMCC, 46000} [PHONE0]
   // 更新运营商名称显示
   D SST     : [0] updateCarrierDisplayName: rawPlmn = CMCC
   D SST     : [0] updateCarrierDisplayName: rawSpn = CMCC
   D SST     : [0] updateSpnDisplay: origin = Spn=CMCC, DataSpn=CMCC, ShowSpn=true, Plmn=CMCC, ShowPlmn=false
   D SST     : [0] updateSpnDisplay: rule = 1
   ```
    - `[0]` 对应 SIM 卡 1，`[1]` 对应 SIM 卡 2。
    - `rule` 数值对应不同的显示规则（如 1 表示显示 SPN 不显示 PLMN）。

4. 异常判断：同样比较配置值与实际显示结果。

### 二、APN 错误问题处理

1. **问题确认**：测试反馈 APN 配置与对比机不符，首先验证需求来源，优先确认是否有运营商官方文档支撑。
2. **抓取日志**：过滤 `DPM-0` 或 `ApnSetting` 相关日志，查看当前已配置的 APN 列表。
   示例日志：
   ```
   D DPM-0   : Added [DataProfile=[ApnSetting] CSL Data, 2649, 45400, hkcsl, 192.168.59.51, http://192.168.58.171:8002, 192.168.59.51, 8080, 8080, 0, mms | supl | hipri | default, IP, IP, true, 0, false, 0, 0, 0, 0, 0, null, , false, UNKNOWN, UNKNOWN, 0, -1, -1, false, 3, 961, false, UNEDITED, TrafficDescriptor={mDnn=hkcsl, null}, preferred=false]
   ```
   字段包含 APN 名、MCC/MNC、APN 类型、协议类型等。
3. **修改原则**：
   - 对比同平台基线版本 APN 配置差异。
   - 仅在需求明确且有官方依据时，执行 APN 修改操作。
   - 同步运营商最新 APN 参数，防止网络连接失败。

### 三、RAT/IMS 图标显示问题定位

1. **RAT 图标**：搜索 `DATA_REGISTRATION_STATE` 日志，检查当前注册制式与数据能力。
   ```
   D RILJ    : [8825]< DATA_REGISTRATION_STATE RegStateResult{regState: REG_HOME, rat: LTE_CA, ...}
   ```
   - `rat` 字段表示当前无线接入技术，如 `LTE_CA`、`NR` 等。
   - 某些版本（如 TOS16.2）要求数据能力完备（如 DNS 地址可用）才显示制式图标，若 `rat` 正确但图标不显示，需检查数据能力的相关日志。

2. **IMS 图标（VoWiFi）**：搜索 `ImsPhoneCallTracker` 日志，查看 WFC（Wi-Fi Calling）状态。
   ```
   D ImsPhoneCallTracker: [0] Do not switch WFC mode, isWfcEnabled:false, isEmergencyNumber:true, mCarrierSwitchWfcModeRequired:false
   ```
   通过 `isWfcEnabled` 等标志判断是否使能 WFC，若为 `false` 排查相关配置或注册状态。

### 四、搜网问题定位

1. 搜网问题可通过 `QUERY_AVAILABLE_NETWORKS_WITH_ACT` 返回的网络列表判断。
   示例（Radio Log）：
   ```
   D RILJ    : [5145]< MTK: QUERY_AVAILABLE_NETWORKS_WITH_ACT [OperatorInfo Jio True5G/Jio True5G/405858/CURRENT/0, OperatorInfo Vi India 4G/Vi India 4G/40401/FORBIDDEN/0, ...]
   ```
   列表中包含 `OperatorInfo`，格式为 `长名/短名/MCCMNC/状态/ACT`。
2. 若发现手动搜网出现重复运营商名称，需检查底层搜索逻辑是否对同一网络的不同制式重复上报，或前端显示未去重。

## 示例

### 正例
**问题**：状态栏运营商名称显示为空，而预期应显示“Airtel ZM”。  
**平台**：MTK  
**分析过程**：从日志中过滤 `MTKSST`，发现如下记录：
```
D MTKSST  : [GsmSST1] updateCarrierDisplayName: rawSpn = Airtel ZM
D MTKSST  : [GsmSST1] notifyCarrierDisplayNameDataChanged: changed sending intent, rule=3, CarrierDisplayNameData={ spn = null, dataSpn = Airtel ZM, showSpn = false, plmn = No service, showPlmn = true, subId=1
```
`rawSpn` 有值，但最终 `spn` 为 `null` 且 `showSpn` 为 `false`，导致 SPN 不显示。进一步检查发现 PLMN 返回 `No service`，显示逻辑在无服务时优先显示 PLMN。根本原因是网络侧 PLMN 下发异常，需与运营商确认。

**JIRA 案例**：http://jira.transsion.com/browse/S685LNOS15-299 通过日志发现 PLMN 下发值为空导致显示异常。

**问题**：客制化 SPN 配置未覆盖多语言场景，导致在特定语言下显示错误。  
**JIRA 案例**：http://jira.transsion.com/browse/TOS1510-45066 展示客制化 SPN 配置未覆盖多语言场景。

**APN 问题正例**：http://jira.transsion.com/browse/TOS1610-74748 因未同步运营商最新 APN 参数导致网络连接失败，修正后恢复。

### ⚠️ 反例（请人工补充）
待人工补充：反例可补充“仅凭测试对比机差异即修改 APN，未核实运营商官方规范，导致引入其他运营商的错误配置”，或“未检查 PLMN 空值就修改显示逻辑，忽略网络侧问题”等。

## ⚠️ 版本与平台约束（请确认）
- Android 版本范围：源文档未明确提及，需根据实际项目确认（示例中涉及 TOS16.2）。
- 芯片平台：MTK、展锐、高通
- AOSP 分支：源文档未明确，通常基于各芯片厂商的基线版本，需确认。

## 注意事项
- 不同平台 SIM 槽位索引规则：MTK 使用 `GsmSST0`/`GsmSST1`，展锐/高通使用 `[0]`/`[1]`，对应 SIM 卡 1 和 SIM 卡 2，分析时勿混淆。
- SPN 显示规则（`rule` 值）由 `ServiceStateTracker` 内部逻辑决定，不同平台实现可能略有差异，需结合基线代码验证。
- 搜网日志中 `QUERY_AVAILABLE_NETWORKS_WITH_ACT` 的 `OperatorInfo` 包含状态字段（如 CURRENT/FORBIDDEN），重复问题需注意同一网络的不同制式是否被作为不同条目返回。
- 数据能力完整性（如 DNS 可用性）可能影响 RAT 图标显示，尤其在特定版本中，日志需结合连接性状态综合判断。
- 修改运营商参数前必须获得官方文档支持，避免引入合规风险。

## 维护信息
- 维护人：待指定
- 生成来源：1 个源文档（共 10976 字符）
- 模板版本：v1.0
