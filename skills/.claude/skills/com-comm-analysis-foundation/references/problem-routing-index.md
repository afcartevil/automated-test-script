# Problem Routing Index Reference

## 1. 目的

本文件是整个 Skill 的**首选路由入口**。

**与叶子目录协作**：域与专题文件选定后，必须用 `references/leaf-skill-routing.md` 将问题**映射到具体叶子文件夹**（打开 `<目录>/SKILL.md` 做 patterns 级分析）；不要停留在专题 `.md`  alone。

先在这里确定：

1. 问题属于哪个主域
2. 首轮最小证据集是什么
3. 主专题应该看哪个文件
4. 最多补哪一个辅助专题

> 规则很简单：**先路由，再分析；先 1 个主专题，最多再补 1 个辅助专题。**

---

## 2. 路由总规则

### 2.1 先看“最早断点”
- 如果问题还没进入业务主流程，优先看上层入口与状态流转。
- 如果上层流程已经走通，失败发生在协议、承载、网络返回、HTTP/SIP 等阶段，优先看协议或网络侧专题。

### 2.2 先补最小证据集
所有问题首轮至少确认：
- 现象描述
- 问题时间点
- 平台 / 版本 / baseband
- SIM / 运营商 / 卡槽
- DUT / REF 对比
- 关键日志类型

### 2.3 避免大范围混读
- 首轮只选 **1 个主专题**。
- 只有当主专题已经定位出跨域断点时，才补 **1 个辅助专题**。
- 不要把 Call / Network / SIM / Stability 四个专题一次性全带上。

---

## 3. 问题路由速查表

| 用户现象 / 首轮线索 | 先补哪些证据 | 主专题 | 可选辅助专题 | 路由说明 |
| --- | --- | --- | --- | --- |
| 无法拨号、无法来电、掉话，但还不清楚断点在哪 | 时间点、DUT/REF、sys/radio/main log、录屏 | `call-analysis.md` | `log-collection.md` | 先进入 Call 总览路由，再决定走上层还是协议侧 |
| 无通话界面、无铃声、音频路由异常、视频通话按钮/选卡异常 | sys_log、main_log、录屏 | `call-framework-analysis.md` | `call-analysis.md` | 这类通常先看 Dialer / Telecom / InCall / Audio 路径 |
| 上层流程正常，但 `SET_DISCONNECTED=error`、SIP/HTTP 拒绝、IMS 注册失败、VoWiFi/补充业务异常 | modem / radio / net log、错误码、运营商信息 | `call-protocol-ims-analysis.md` | `escalation-rules.md` | 这类优先看 CS / IMS / Ut / XCAP / bearer / network reject |
| SPN / PLMN 显示异常、APN 异常、4G/5G/VoWiFi 图标异常、手动搜网异常 | radio log、配置版本、录屏 | `network-analysis.md` | `log-collection.md` | 先分清是网络返回异常、配置异常还是 Android 显示异常 |
| 不识卡、掉卡、PIN/PUK、IMSI/ICCID 读取失败、READY/LOADED 异常 | radio/modem log、多卡多机对比、卡槽信息 | `sim-analysis.md` | `log-collection.md` | 先按识卡状态机排查，再判断硬件 / RIL / 卡侧 |
| Baseband Unknown、IMEI 异常、信号消失后恢复、Modem crash / ASSERT | modem log、dump、ASSERT、版本号 | `stability-analysis.md` | `escalation-rules.md` | 先判断是否已具备 EE 证据，再决定是否接力平台 |
| 用户只给了截图或一句话，没有日志 | 时间点、录屏、版本、log 包 | `log-collection.md` | `problem-routing-index.md` | 先补材料，别急着做根因判断 |
| 已经知道断点，但不确定该交给谁继续分析 | 当前结论、断点层级、日志包 | `escalation-rules.md` | 对应主专题 | 接力分析要带上结论、证据和交接材料 |

---

## 4. Call 领域二次分流

当路由到 Call 域后，再用下面这张表做一次分流：

| 现象 / 断点 | 主文件 | 说明 |
| --- | --- | --- |
| `CREATED` 前就断、来电 UI 拉不起来、无铃声、音频路由、视频通话交互异常 | `call-framework-analysis.md` | 更偏 Android 上层、Telecom、InCall、Audio |
| 上层建链完成后失败、`SET_DISCONNECTED=error`、IMS 注册 / VoWiFi / 补充业务、SIP/HTTP 被拒 | `call-protocol-ims-analysis.md` | 更偏 CS / IMS / Ut / XCAP / bearer / network 返回 |
| 还不知道该走哪边 | `call-analysis.md` | 先用总览路由判断最早断点 |

---

## 5. 跨域问题处理规则

### 5.1 Call ↔ Network
- 若问题核心是**图标 / SPN / APN / 搜网 / 驻网**，先走 `network-analysis.md`。
- 若问题核心是**语音业务建链、注册、补充业务**，先走 Call。

### 5.2 Call ↔ Stability
- 若出现 `Baseband Unknown`、ASSERT、信号整体丢失后恢复，先走 `stability-analysis.md`。
- 若只是某次通话失败但基带总体正常，先走 Call。

### 5.3 SIM ↔ 其他域
- 若基础识卡都没成功，先走 `sim-analysis.md`。
- 只有在 SIM 已 READY / LOADED 后，才继续看 Call / Network 上层问题。

---

## 6. 输出约束

- 最终输出统一复用 `SKILL.md` 的标准模板。
- 回答中最好显式写出：
  - 这次选了哪个主专题
  - 如有辅助专题，为什么补它
  - 当前结论基于哪些证据

这一步看起来像“多写一句”，其实能少掉很多模型自由发挥。别让模型自嗨，路由先拴住它。

---

## 7. 叶子 Skill 目录（与 Jira 现象对齐）

完整「现象 → 同级目录名 → 协作加载顺序」见 **`references/leaf-skill-routing.md`**。本节不重复该表，仅强调：

- 同一主域内可能有多枚叶子（MTK / UNISOC / COMMON），**按芯片与现象**择一为主。
- 与 `com-comm-analysis-foundation`、`com-comm-sop-source-archive` 的加载关系见 `leaf-skill-routing.md` 第 1 节。
