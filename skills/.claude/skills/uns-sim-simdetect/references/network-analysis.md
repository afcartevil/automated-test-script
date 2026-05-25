# Network Analysis Reference

## 1. 适用范围

本专题用于指导以下网络类问题的首轮分析与归因：

- SPN / PLMN / 运营商名称显示异常
- APN 配置异常、配置与竞品/对比机不一致
- RAT 图标异常（2G / 3G / 4G / 5G）
- IMS / VoWiFi 图标显示异常
- 手动搜网、手动选网、搜网列表异常
- 驻网状态异常、当前网络与预期网络不一致

> 先确认“网络返回了什么”，再判断“系统显示错了什么”。不少网络问题本质不是注册失败，而是显示策略、配置同步或运营商下发信息不一致。

---

## 2. 分析前的最小证据集

开始分析前，优先补齐这些信息：

- 问题类型：SPN / APN / RAT 图标 / IMS 图标 / 搜网 / 驻网 / 手动选网
- 问题时间点
- 平台：MTK / SPRD / Qcom
- 软件版本、baseband 版本
- SIM 卡、运营商、卡槽信息
- 问题地点与是否漫游
- DUT / REF 对比结果
- 是否可稳定复现
- 视频或截图（状态栏、设置页、搜网列表）
- 可用日志：main_log / radio_log / modem log / net log

### 2.1 外部因素先排除

优先确认：

1. DUT 与 REF 是否处于**同地点、同运营商、同卡、同网络策略**。
2. 是否存在漫游、弱网、网络限制、卡套餐能力差异。
3. APN 修改诉求是否有**运营商官方依据**，不要仅因“和对比机不一致”就直接改配置。
4. 手动搜网列表出现同品牌运营商多条记录时，先核查 **PLMN 是否不同**，不要误判为重复异常。

### 2.2 推荐优先查看的日志

- **radio_log**：`OPERATOR`、`DATA_REGISTRATION_STATE`、手动搜网返回结果
- **main_log**：`NetworkScanHelper`、状态栏/设置界面相关行为
- **ServiceStateTracker / SST**：运营商名称更新、SPN/PLMN 显示策略
- **modem log / net log**：驻网、注册制式、网络侧限制与数据能力

---

## 3. 先分问题子域，再看断点

Network 类问题不要混成一锅。先判断属于哪一类：

### 3.1 运营商名称显示类

核心目标：确认**网络下发值**、**客制配置值**、**最终显示结果**三者是否一致。

- 网络侧返回：`OPERATOR`
- 配置侧字段：`rawSpn` / `rawPlmn` / `newSpn`
- 最终显示结果：`updateSpnDisplay...` 或 `notifyCarrierDisplayNameDataChanged`

### 3.2 APN 配置类

核心目标：确认问题是：

- 需求本身没依据
- APN 配置与运营商官方要求不一致
- 同平台基线版本没有同步最新 APN 参数

### 3.3 RAT / IMS / VoWiFi 图标类

核心目标：确认终端是否真的已拿到对应注册能力与数据能力，而不是单纯 UI 不刷。

- 重点看 `DATA_REGISTRATION_STATE`
- 再看 IMS / VoWiFi 状态相关日志
- 部分版本需要同时具备数据能力才显示制式图标

### 3.4 搜网 / 驻网 / 手动选网类

核心目标：确认问题发生在：

- 调制解调器返回列表阶段
- Android 侧展示阶段
- 网络接入权限判断阶段

手动搜网至少要同时看：

- radio log 中返回的运营商列表
- main log 中 `NetworkScanHelper` 的解析结果

---

## 4. 平台关键日志速查

## 4.1 SPN / PLMN / 运营商显示

### 4.1.1 MTK

核心关键字：

- `MTKSST`
- `updateCarrierDisplayName`
- `updateSpnDisplay`
- `notifyCarrierDisplayNameDataChanged`

重点字段：

- `OPERATOR`：网络返回的运营商长名/短名
- `rawSpn`：客制配置名称
- `plmn`：网络下发名称
- `CarrierDisplayNameData`：最终显示结果汇总
- `[GsmSST0] / [GsmSST1]`：区分卡槽

判断方法：

1. 先看 `OPERATOR` 返回值。
2. 再看 `rawSpn / plmn`。
3. 最后看 `notifyCarrierDisplayNameDataChanged` 中 `showSpn / showPlmn / subId`。

若配置要求显示 PLMN，实际却显示 SPN，或反过来，可直接定位为**显示逻辑异常或配置映射异常**。

### 4.1.2 SPRD / Qcom

核心关键字：

- `SST`
- `updateSpnDisplayLegacy`
- `updateSpnDisplay`
- `getCarrierDisplayNameLegacy`

重点字段：

- `rawPlmn`
- `rawSpn`
- `newSpn`
- `showPlmn / showSpn`
- `[0] / [1]`：区分卡槽

判断方法与 MTK 一致：

1. 看网络返回的运营商信息。
2. 看配置层取到的 `rawPlmn / rawSpn / newSpn`。
3. 看最终 `changed sending intent` 汇总出的显示策略。

---

## 5. 关键断点与日志定位方法

## 5.1 SPN / PLMN 显示异常

### 先看三层值是否一致

1. **网络返回值**：`OPERATOR`
2. **配置/客制值**：`rawSpn / rawPlmn / newSpn`
3. **最终显示策略**：`showSpn / showPlmn / spn / plmn`

### 快速判断

- 网络下发值为空：先怀疑网络侧或注册信息缺失
- 网络下发正常，但最终显示错误：优先看 `updateSpnDisplay` 逻辑
- 多语言或本地化场景异常：优先怀疑客制 SPN 覆盖不全

## 5.2 APN 配置异常

### 重点日志

- `DPM-0`
- `Added [DataProfile=[ApnSetting] ...]`
- `TrafficDescriptor={mDnn=...}`

### 重点关注

- 当前运营商下已加载的 APN 列表
- `default / ims / xcap` 等业务类型是否齐全
- APN 名称、协议栈、承载 RAT 范围是否符合预期

### 判断规则

- 仅因“与对比机不一致”不能直接判 bug
- 必须先核查需求来源与运营商文档
- 再对比同平台基线版本是否已具备对应配置
- 只有需求明确且有官方依据时，才建议修改 APN

## 5.3 RAT / IMS / VoWiFi 图标异常

### 重点日志

- `DATA_REGISTRATION_STATE`
- `RegStateResult{regState: ... , rat: ...}`
- `ImsPhoneCallTracker`
- `isWfcEnabled`

### 判断规则

1. `DATA_REGISTRATION_STATE` 先确认当前注册制式与拒绝原因。
2. 结合 `lteVopsInfo`、`nrIndicators` 等字段判断 4G/5G 能力。
3. VoWiFi 图标类问题补看 WFC/IMS 状态日志。
4. 某些版本下，制式图标显示依赖数据能力同时满足，不能只看语音注册。

## 5.4 手动搜网 / 驻网异常

### 重点日志

- radio log：`QUERY_AVAILABLE_NETWORKS_WITH_ACT`
- main log：`NetworkScanHelper`

### 字段含义

- `CURRENT`：当前驻留网络
- `AVAILABLE`：可接入网络
- `FORBIDDEN`：受限网络

### 判断规则

1. 若 radio log 已返回完整列表，但界面显示不全，偏 Android 展示或过滤逻辑。
2. 若列表内运营商品牌名重复，先比对 `operatorNumeric / PLMN` 是否不同。
3. `CURRENT / AVAILABLE / FORBIDDEN` 是网络接入状态，不应仅按品牌名判断异常。

## 5.5 V2 补强：PLMN 选择流程与搜网时延观察点

基于 `21届雏鹰培训/第二阶段/PLMN选择流程-叶笑尘-20200903.pptx` 的增量信息，可把“手动搜网 / 驻网 / 重复运营商列表”这类问题的判断再补细一层。

### 5.5.1 先补齐几个 PLMN 概念，避免把正常现象看成异常

- `PLMN = MCC + MNC`，同品牌运营商在不同 `MCC/MNC` 下可能显示成相近名字，但它们并不是同一个网络。
- `RPLMN`：终端上次成功登记的 PLMN，自动搜网时通常优先尝试。
- `HPLMN / EHPLMN / EPLMN`：归属网及等效归属网/等效网，决定了为什么 UE 会优先回到某些“更高优先级”的网络。
- `VPLMN`：访问网；漫游场景下经常需要和 HPLMN / EPLMN 一起看。
- `FPLMN`：被网络拒绝后加入的禁用 PLMN 列表；看到“明明搜到了却不再尝试接入”的现象时要优先怀疑这里。
- `UPLMN / OPLMN`：分别代表用户手动选择偏好和运营商预置偏好，都会影响选网顺序。

这组概念的直接价值是：

1. 解释“同品牌多条记录”为什么可能是正常现象；
2. 解释“为什么 DUT 会优先回到某个网络，而不是停在当前可用网”；
3. 解释“为什么某个网搜得到但后续不再尝试注册”。

### 5.5.2 自动 / 手动搜网时，优先关注的选择策略

课件给出的核心顺序可概括为：

1. 自动模式下，UE 会优先结合历史登记网（如 `RPLMN`）与归属优先级去找候选网；
2. 搜网会区分 `stored only` 与 `full band` 两种路径，不是所有情况下都会直接全频扫描；
3. 手动模式下，一旦用户注册到某个 PLMN，UE **不会自动改去其他 PLMN**，除非：
   - 新 PLMN 属于当前注册网的等效 PLMN；或
   - 用户重新切回自动模式。

因此遇到“手动选网后没有自动回切”“自动搜网比预期慢”“对比机停留网络不同”时，不要先拍成 bug，先确认：

- 当前是否处于自动还是手动模式；
- 目标网与当前网是否属于 `EHPLMN / EPLMN`；
- DUT 是否仍优先尝试 `RPLMN`；
- 当前搜网流程是 `stored only` 还是已经落到 `full band`。

### 5.5.3 为什么搜得到网、但不一定能注册或持续驻留

从补强资料看，下面几类机制很关键：

- UE 扫频后，会把可用网络按条件上报给 NAS；弱网场景下还会结合信号质量信息上报。
- 如果收到 `PLMN not allowed`，目标网可能被写入 `FPLMN list`；后续“再次不尝试注册”就未必是框架过滤问题，而可能是协议侧记忆机制。
- 如果收到 `No Suitable Cells In Location Area` 一类拒绝，相关 forbidden LA 记录也会影响后续尝试。
- 小区选择并不是“搜到就能驻留”，还要满足诸如 `Srxlev > 0`、`Squal > 0` 之类的基础条件。

所以当现象是：

- 能搜到网但点选后失败；
- 一度驻上又掉回别的网络；
- DUT 与 REF 选中的 PLMN 不同；

要把 **搜网结果**、**注册拒绝原因**、**FPLMN / forbidden LA 状态**、**驻留门限条件** 连起来一起看。

### 5.5.4 搜网时延的几个高价值排查点

补强资料里有几条很实战的时延线索：

1. **双卡共享射频资源**：在 MTK 双卡平台上，副卡若正处于 paging、service request 或其他连接态业务，可能直接拖慢主卡搜网。
2. **PS service 挂起搜网流程**：UE 正在做 PS 业务时，`PLMN list procedure` 可能被挂起，手动搜网时延会明显变长。
3. **SIM 中 PLMN 类型差异**：测试机与对比机若卡内的 PLMN 类型或优先级配置不同，搜网顺序和耗时也会不同。
4. **测试动作本身影响结论**：例如搜网过程中副卡并行业务，会把“平台性能差”伪装成“搜网异常”。

这意味着：只统计“多久出列表”还不够，最好同步记录：

- 双卡当时是否同时在线；
- 副卡是否有 paging / data / service request；
- 当前是自动搜网还是手动搜网；
- 用户是否刚从手动模式切回自动模式；
- DUT / REF 使用的 SIM 卡是否同运营商、同类型、同卡槽。

> 这组 V2 补强最有用的地方，不是多记几个缩写，而是把“搜网慢 / 列表怪 / 选网行为不一致”从结果描述，补成了可核查的协议与策略视角。

---

## 6. 场景化分析打法


## 6.1 运营商名称显示错误

### 分析步骤

1. 查 `OPERATOR`，确认网络返回的长名/短名。
2. 查 `rawSpn / rawPlmn / newSpn`，确认配置层拿到的值。
3. 查 `updateSpnDisplay` 或 `notifyCarrierDisplayNameDataChanged`，确认最终显示策略。
4. 对比实际界面显示与日志结论是否一致。

### 常见归因

- **网络侧下发值异常**：如 PLMN 为空
- **客制配置缺失**：如多语言 SPN 未覆盖
- **显示逻辑异常**：配置与最终 `showSpn / showPlmn` 不匹配

## 6.2 APN 与对比机不一致

### 分析步骤

1. 抓取当前机型 APN 加载日志。
2. 识别 `default / ims / xcap` 等关键 profile 是否存在。
3. 对比同平台基线版本差异。
4. 确认运营商是否有官方配置要求。

### 常见归因

- **需求来源不足**：测试诉求缺少官方依据
- **基线未同步**：未合入运营商最新 APN 参数
- **配置策略差异**：对比机与 DUT 使用的配置源不同

## 6.3 RAT / IMS / VoWiFi 图标不显示

### 分析步骤

1. 查 `DATA_REGISTRATION_STATE` 看注册制式与能力。
2. 查 IMS / WFC 状态日志，看是否启用或注册成功。
3. 对照视频/截图确认是“能力未建立”还是“图标未刷新”。
4. 结合版本特性判断是否依赖数据能力共同成立。

### 常见归因

- **网络能力未满足**：如缺少可用 DNS、数据能力异常
- **IMS / WFC 未启用或未注册**：图标不显示但并非 UI bug
- **版本显示策略差异**：制式图标依赖条件与旧版本不同

## 6.4 手动搜网显示重复运营商 / 选网异常

### 分析步骤

1. 查 `QUERY_AVAILABLE_NETWORKS_WITH_ACT` 返回的列表。
2. 查 `NetworkScanHelper` 对列表的解析结果。
3. 对比品牌名相同条目的 `PLMN` 是否一致。
4. 根据 `CURRENT / AVAILABLE / FORBIDDEN` 判断是否真的异常。

### 常见归因

- **不同 PLMN 的同品牌网络**：属于正常运营商配置
- **Android 展示侧理解错误**：把不同接入状态误判为重复异常
- **网络侧限制**：可见但不可接入，状态显示 `FORBIDDEN`

---

## 7. 典型归因矩阵

| 现象 | 先看哪里 | 常见归因 |
| --- | --- | --- |
| 运营商名称显示不对 | `OPERATOR` + `updateSpnDisplay` | 网络下发异常 / 客制配置缺失 / 显示逻辑异常 |
| APN 与对比机不一致 | `DPM-0` + `ApnSetting` | 官方需求缺失 / 基线未同步 / 配置源差异 |
| 4G/5G 图标不显示 | `DATA_REGISTRATION_STATE` | 注册能力不足 / 数据能力未满足 / 显示策略变化 |
| VoWiFi 图标不显示 | `ImsPhoneCallTracker` + WFC 状态 | WFC 未启用 / IMS 未注册 / 图标显示条件未满足 |
| 手动搜网列表重复 | `QUERY_AVAILABLE_NETWORKS_WITH_ACT` + `NetworkScanHelper` | 不同 PLMN 的同品牌网络，属正常现象 |
| 手动搜网看到网络但无法接入 | 列表状态字段 | `FORBIDDEN` 网络限制或接入权限不足 |

---

## 8. 输出建议

对外输出时，建议使用下面的判断口径：

1. **先明确问题子域**：显示类 / APN 类 / 图标类 / 搜网类。
2. **明确看到的断点**：网络返回、配置解析、最终显示、列表展示，卡在哪一层。
3. **避免一句话拍脑袋**：例如“就是运营商问题”或“就是平台问题”。
4. **对 APN 修改保持克制**：没有运营商官方依据时，不建议直接调整。

---

## 9. 当前资料边界

当前专题主要覆盖：

- SPN / PLMN 显示
- APN 配置
- RAT / IMS / VoWiFi 图标
- 手动搜网列表与状态判断

当前文档**没有系统覆盖**的数据吞吐、Attach 深层失败、复杂驻网恢复、跨 RAT 切换算法等议题。遇到这类问题时，应在本专题基础上继续补充协议侧或 V2 培训资料。 
