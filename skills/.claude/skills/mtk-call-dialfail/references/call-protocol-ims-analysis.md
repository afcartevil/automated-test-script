# Call Protocol / IMS Analysis Reference

## 1. 适用范围

本专题用于处理更偏 **CS / IMS / VoWiFi / Ut / XCAP / Network reject** 的 Call 问题，典型包括：

- 上层建链已经完成，但通话仍失败或异常挂断
- `SET_DISCONNECTED=error`
- IMS 注册失败、VoWiFi 注册失败
- SIP 流程在 `INVITE / 183 / PRACK / CANCEL / 200 OK` 之间异常中断
- 补充业务（Call Forwarding / Call Waiting / Call Barring / CLIR）失败

如果问题停在拨号入口、InCall 绑定、界面或音频路由，请转 `call-framework-analysis.md`。

---

## 2. 先判域：CS 还是 IMS

### 2.1 Call 主业务
- **CS domain**：传统 2G / 3G，或 4G 回落 CSFB 后走 CS 呼叫
- **IMS domain**：VoLTE / VoNR / VoWiFi 场景，基于 SIP 建链

### 2.2 补充业务（Supplementary Service）
- **CS 域**：多看 `REGISTER / FACILITY / RELEASE COMPLETE`
- **IMS 域**：通常走 `Ut / XCAP / HTTP`，部分场景依赖 `GBA / BSF / TAS`

### 2.3 判域方法
优先结合：
- 状态栏图标（4G / 5G / HD / VoWiFi）
- 视频录屏
- radio log 中 `VOICE_REG` / `DATA_REG`
- modem log 中频点与制式信息
- IMS 相关日志：`REGISTER` / `INVITE` / `PRACK` / `NOTIFY`

---

## 3. 协议侧标准流程速查

## 3.1 CS MO 流程（典型）
1. RRC Connection Setup
2. CM Service Request
3. Authentication & Security
4. Setup
5. Call Proceeding
6. RAB Assignment
7. Alerting
8. Connect
9. Connect ACK

## 3.2 IMS MO 流程（典型）
1. SIP `INVITE`
2. `100 Trying`
3. `183 Session Progress`
4. `PRACK` + `200 OK`
5. Dedicated bearer setup（QCI=1）
6. `UPDATE` + `200 OK`
7. `180 Ringing`
8. `200 OK (INVITE)`
9. `ACK`
10. RTP media established

## 3.3 IMS 注册流程（与语音、VoWiFi 强相关）
1. 建立 IMS PDN（通常 QCI=5）
2. 发送 `REGISTER`
3. 网络返回 `401 Unauthorized`
4. 终端携鉴权信息再次 `REGISTER`
5. 网络返回 `200 OK`
6. 终端发 `SUBSCRIBE`
7. 网络发 `NOTIFY`
8. `state=active` 才算注册可用

## 3.4 补充业务流程
### CS 域
- UE 发送 `REGISTER`
- 网络通过 `FACILITY / RELEASE COMPLETE` 返回 `Return Result` 或 `Return Error`

### IMS 域（Ut / XCAP）
- `BSF / GBA` 认证
- 终端对 TAS 发起 `HTTP GET / PUT` 访问 `simservs.xml` 等节点
- 成功通常看 `HTTP 200 OK`
- 失败重点看 `401 / 403 / 404 / 5xx` 与 response body

---

## 4. 关键日志与断点定位方法

### 4.1 Call 主业务重点看
- `Telecom.*SET_DISCONNECTED`
- `DisconnectCause / TelephonyCause / ImsReasonInfo`
- `INVITE / PRACK / CANCEL / RELEASE / DISCONNECT / Cause / Reason`
- `DATA_CALL_REQ / DATA_CALL_CNF`

### 4.2 IMS 注册 / VoWiFi 重点看
- `EIMSCFG`
- `REGISTER / 401 / 200 OK / NOTIFY`
- `IMS status = active / terminated`
- `DATA_CALL_REQ / DATA_CALL_CNF`
- APN / WLAN APN / IP 获取日志

### 4.3 补充业务重点看
- `HTTP GET / PUT`
- `401 Unauthorized`
- `403 Forbidden`
- `404 Not Found`
- XCAP URL / DNS 解析 / AKA 鉴权 / TAS 返回体
- `CC__REGISTER / CC__RELEASE_COMPLETE / Return Error`

---

## 5. 场景化分析打法

## 5.1 拨号失败 / 掉话（上层流程已走通）

分析顺序：
1. 先确认 `notifyCreateConnectionComplete`、`setCallState` 等上层建链已完成
2. 看 `SET_DISCONNECTED` 与原因码
3. 按标准信令找断点：
   - CS：是否走到 `Alerting / Connect`
   - IMS：是否到 `183 / PRACK / dedicated bearer / 180 / 200 OK`
4. 结合 DUT / REF 判断是终端、网络还是配置问题

### 快速判断
- `remote`：对端挂断，通常不算异常
- `local`：继续向前搜 `hangup / hang up`，确认是谁触发挂断
- `error`：优先继续查协议、承载、网络拒绝或底层原因

## 5.2 典型案例：IMS 来电失败（183 后中断）

断点：
- UE 收到 `INVITE`
- UE 正常回 `100 Trying` 与多个 `183 Session Progress`
- 长时间收不到网络 `PRACK`
- 网络随后直接 `CANCEL`

关键依据：
- `CANCEL` 中带 `Media Bearer Lost`
- OTA 未建立 `QCI=1` dedicated bearer

结论：
- **网络侧异常**，不是终端框架层问题

## 5.3 IMS 注册 / VoWiFi 排查顺序
1. IMS / VoWiFi 开关是否打开（可搜 `EIMSCFG`）
2. 网络是否支持 IMS / VoPS
3. IMC 条件检查是否 OK
4. IMS PDN 是否建立成功（`DATA_CALL_REQ / DATA_CALL_CNF`）
5. SIP `REGISTER / 401 / 二次 REGISTER / 200 OK` 是否完整
6. `NOTIFY` 的状态是否为 `active`

### 典型终端侧案例：VoWiFi 注册失败
- IMS PDN 建立失败
- 日志出现 `get NULL WLAN apn info`
- 未拿到有效 IP
- SIP `REGISTER` 根本没发出

结论：
- **终端配置问题**，IMS APN / WLAN APN 配置异常

### 典型网络侧案例：VoWiFi 注册失败
- IMS PDN 正常
- `REGISTER` 正常发出
- 走到 `NOTIFY`
- `IMS status = terminated`，event 为 `reject`
- REF 同 WiFi 下也失败

结论：
- **网络侧主动拒绝**

## 5.4 Supplementary Service 排查四问
1. 当前域是 CS 还是 IMS？
2. 该 SIM / 套餐是否开通该业务权限？
3. Ut / XCAP 配置是否正确？
4. 网络返回了什么错误码？

### 典型案例 1：VoLTE 下呼叫转移设置失败
- 终端已走到 `HTTP PUT` 修改 XCAP XML
- 网络返回 `403 Forbidden`
- response body 指向 `User not authorized for this service`

结论：
- **运营商侧权限未开通 / 卡套餐限制**

### 典型案例 2：3G 下呼叫等待查询失败
- 已发送 `CC__REGISTER`
- 网络回复 `CC__RELEASE_COMPLETE`
- `Return Error: FacilityNotSupported`

结论：
- **网络侧兼容性 / 配置问题**

### 典型案例 3：VoLTE 下呼叫限制查询失败
- 理应走 HTTP/XCAP，但根本没发出 HTTP 请求
- 向前追溯发现 XCAP 域名解析失败
- Carrier config 或 SIM 里的 XCAP Root URI 拼错 / 过期

结论：
- **终端本地配置错误**（XCAP server / DNS 配置问题）

---

## 6. 归因建议矩阵

| 现象 / 断点 | 优先怀疑层 | 关键证据 |
| --- | --- | --- |
| 上层流程正常，`SET_DISCONNECTED` 为 error | Modem / Protocol / Network | `DisconnectCause`、`TelephonyCause`、`ImsReasonInfo` |
| IMS 流程卡在 `183` 后无 `PRACK`，网络 `CANCEL` | Network | `Media Bearer Lost` / 无 `QCI=1` |
| IMS PDN 失败，未拿到 IP，未发 `REGISTER` | Terminal config | `DATA_CALL_CNF` 异常 / APN 配置错误 |
| `403 Forbidden` + `not authorized` | Carrier / Network side | HTTP body / REF 对比 |
| XCAP 无 HTTP 请求，DNS 解析失败 | Terminal config | XCAP URI 配置错误 / DNS 失败 |
| REF 同地同网同卡也复现 | Network / Carrier | 对比结果一致 |

---

## 7. 接力分析建议

当出现以下证据时，通常可以交给对应方继续处理：

- 上层流程已走通，但信令 / 承载 / 原因码明确：接力给 **Telephony / RIL / Modem / Protocol**
- REF 同现象，网络拒绝或权限限制明确：接力给 **运营商 / 网络侧**
- XCAP / APN / 本地参数错误明确：接力给 **配置 / 客制化维护方**

接力时至少带上：
- 问题时间点
- 协议断点
- 关键错误码 / HTTP body / SIP reason
- DUT / REF 对比结果
- 相关 modem / radio / net log

---

## 8. 输出建议

最终输出统一复用 `SKILL.md` 的标准模板；本专题建议额外补充：
- `Domain: CS / IMS / Supplementary`
- `Protocol breakpoint`
- `Reason code / SIP cause / HTTP result`
- `DUT vs REF result`

模板只保留一份，证据可以很多，模板别跟着膨胀。否则模型一开心，就开始自由泳了。
