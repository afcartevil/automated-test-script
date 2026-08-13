# Call Analysis Routing Reference

## 1. 目的

本文件不再承担所有 Call 细节知识，而是作为 **Call 域总览路由页** 使用。

适用问题：
- 无法拨出 / 无法来电 / 通话中异常挂断
- 无通话界面 / 无铃声 / 音频路由异常 / 视频通话异常
- IMS 语音、VoWiFi、补充业务异常

首轮目标只有两件事：

1. 先找到 **最早断点**
2. 再决定进入 **上层框架专题** 还是 **协议 / IMS 专题**

> 原则：先分流，再深挖。别一上来把上层、协议、网络、运营商全拌一锅。

---

## 2. 分析前的最小证据集

开始前优先补齐这些信息：

- 现象类型：无法拨出 / 无法来电 / 挂断 / 无界面 / 无铃声 / 补充业务失败 / 视频通话异常
- 问题时间点
- DUT / REF 对比结果
- 平台信息：MTK / SPRD / Qcom
- 版本信息：软件版本、baseband 版本
- 当前网络域：2G / 3G / 4G / 5G、CS / IMS、VoLTE / VoNR / VoWiFi
- SIM 卡与运营商信息
- 视频或截图
- 可用日志：main_log / radio_log / sys_log / crash_log / modem log / net log

### 2.1 外部因素先排除
优先做 DUT / REF 交叉验证：

1. DUT 与 REF 在**同地点、同运营商、同卡、同功能开关**下对比。
2. 必要时互换 SIM 卡再对比。
3. 注意排除：
   - 勿扰模式（Do Not Disturb）
   - 骚扰拦截 / 黑名单
   - 通话功能开关不一致
   - 运营商套餐或补充业务权限未开通

---

## 3. 先判网络域：CS 还是 IMS

Call / 补充业务分析的第一步，不是搜挂断码，而是先确认当前问题属于哪个域。

- **CS domain**：传统 2G / 3G，或 4G 回落 CSFB 后走 CS 呼叫
- **IMS domain**：VoLTE / VoNR / VoWiFi 场景，基于 SIP 建链
- **Supplementary Service**：CS 域多看 `REGISTER / FACILITY / RELEASE COMPLETE`；IMS 域多看 `Ut / XCAP / HTTP`

优先结合：
- 状态栏图标（4G / 5G / HD / VoWiFi）
- 视频录屏
- radio log 中 `VOICE_REG` / `DATA_REG`
- modem log 中频点与制式信息
- IMS 相关日志：`REGISTER` / `INVITE` / `PRACK` / `NOTIFY`

> 判错域，后面的分析基本都会歪。

---

## 4. Call 二次分流决策表

| 首轮现象 / 日志线索 | 主文件 | 说明 |
| --- | --- | --- |
| 连 `Telecom.*Event.*CREATED` 都没有 | `call-framework-analysis.md` | 拨号动作可能还没进入 Telecom / Telephony |
| `notifyNewRingingConnection` 有，但来电界面没拉起 | `call-framework-analysis.md` | 多半停在 Telecom / InCall / UI 绑定 |
| 无铃声、音频路由异常、视频通话按钮/选卡异常 | `call-framework-analysis.md` | 更偏 CallAudio / InCall / 上层交互 |
| 上层建链已完成，但 `SET_DISCONNECTED` 为 `error` | `call-protocol-ims-analysis.md` | 需要继续看协议、承载、底层原因 |
| SIP `INVITE / PRACK / CANCEL / Reason` 或 HTTP/XCAP 明显异常 | `call-protocol-ims-analysis.md` | 已进入 IMS / 补充业务流程 |
| IMS 注册失败、VoWiFi 注册失败、补充业务被拒 | `call-protocol-ims-analysis.md` | 首轮优先看注册、PDN、XCAP、网络返回 |
| 还不确定走哪边 | 继续留在本文件 | 先按第 5 节做断点判断 |

---

## 5. 首轮断点判断顺序

### 5.1 先看是不是上层入口问题
优先搜索：
- `CallIntentProcessor`
- `Telecom.*Event.*CREATED`
- `notifyNewRingingConnection`
- `Attempting to bind to InCall`
- `Telecom.*InCallController.*onConnected`

如果这些入口动作都不完整，优先进入 `call-framework-analysis.md`。

### 5.2 再看是不是协议 / 承载问题
优先搜索：
- `Telecom.*SET_DISCONNECTED`
- `DisconnectCause / TelephonyCause / ImsReasonInfo`
- `INVITE / 183 / PRACK / CANCEL / RELEASE / DISCONNECT`
- `REGISTER / 401 / 200 OK / NOTIFY`
- `HTTP GET / PUT / 401 / 403 / 404`
- `DATA_CALL_REQ / DATA_CALL_CNF`

如果这些日志已经很明确，优先进入 `call-protocol-ims-analysis.md`。

### 5.3 最后一层兜底规则
- 上层流程都没走到位：先看 Framework
- 上层流程走通后失败：先看 Protocol / IMS
- REF 同现象、网络拒绝明确：优先考虑网络 / 运营商侧

---

## 6. 输出与协同规则

- 最终输出统一复用 `SKILL.md` 的标准模板。
- Call 类问题建议额外补充：
  - `Domain: CS / IMS / Supplementary / Unknown`
  - `Call Id`（若已拿到）
  - `Last successful step / First failed step`
- 若需要其他业务接力分析，再补充承接方、交接理由和需要附带的日志材料。

---

## 7. 当前资料边界

本页只负责**Call 领域分流**，不再堆叠全部细节知识。

深挖时请转到：
- `call-framework-analysis.md`：上层来去电、InCall、音频、视频通话
- `call-protocol-ims-analysis.md`：CS / IMS 信令、IMS 注册、VoWiFi、补充业务

这样拆开不是为了好看，是为了别再让模型在 1 个大文件里迷路。
