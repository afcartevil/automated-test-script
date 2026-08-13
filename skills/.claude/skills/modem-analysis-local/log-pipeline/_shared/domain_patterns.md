# L2 业务域分析模式配置

本文件定义各业务域的日志匹配模式和候选原因生成规则。

---

## call 语音域

### 匹配模式

| 模式 | 说明 |
|------|------|
| `\becpi\b` | ECPI 呼叫控制 |
| `\batd\b` | ATD 拨号命令 |
| `\binvite\b` | SIP INVITE |
| `\bbye\b` | SIP BYE |
| `\b183\b` | SIP 183 Session Progress |
| `\b180\b` | SIP 180 Ringing |
| `\b200 ok\b` | SIP 200 OK |
| `\b403\b` | SIP 403 Forbidden |
| `\b404\b` | SIP 404 Not Found |
| `\b408\b` | SIP 408 Request Timeout |
| `\b480\b` | SIP 480 Temporarily Unavailable |
| `\b486\b` | SIP 486 Busy Here |
| `\b487\b` | SIP 487 Request Terminated |
| `\b488\b` | SIP 488 Not Acceptable Here |
| `\bims\b` | IMS 相关 |
| `\bvolte\b` | VoLTE 相关 |
| `\bvowifi\b` | VoWiFi 相关 |
| `\bpaging\b` | 寻呼 |

### 候选原因规则

| 条件 | 候选原因 |
|------|----------|
| 匹配到 `403\|404\|408\|480\|486\|487\|488` | SIP/呼叫流程中出现拒绝码或失败响应。 |
| 匹配到 `ims` 且包含 `fail\|oos\|not registered` | IMS 注册或驻网条件异常，影响语音相关业务。 |
| 无匹配 | 日志中未定位到稳定的 call 关键流程，需先确认问题时间窗或业务域。 |

---

## sms 短信域

### 匹配模式

| 模式 | 说明 |
|------|------|
| `\bsms\b` | SMS 关键字 |
| `\bsmsc\b` | SMSC 短信中心 |
| `\bcp[\s_-]?(?:data\|ack\|error\|delivery)\b` | CP 层消息 |
| `\brp[\s_-]?(?:data\|ack\|error)\b` | RP 层消息 |
| `\bsip[\s_-]?message\b` | SIP MESSAGE 方法 |
| `\bmessage[\s_-]?(?:request\|response)\b` | MESSAGE 请求/响应 |
| `\bsip-frag\b` | SIP Fragment |
| `\bsms-over-ip\b` | SMS over IP |
| `\bsmsc[\s_-]?(?:address\|number)\b` | SMSC 地址 |
| `\bclass[\s_-]?2\b` | Class 2 SMS (SIM 存储) |
| `\bdelivery[\s_-]?(?:report\|status)\b` | 投递报告 |
| `\bsubmit[\s_-]?(?:report\|status)\b` | 提交报告 |

### 候选原因规则

| 条件 | 候选原因 |
|------|----------|
| 匹配到 `sms` 且包含 `fail\|error\|reject` | SMS 发送失败，需检查短信流程。 |
| 匹配到 `cp-error\|rp-error` | SMS CP/RP 层传输失败，需检查网络侧配置。 |
| 匹配到 `sip-message` 且包含 `403\|404\|500\|503` | SMS over VoWiFi 被 SIP 层拒绝。 |
| 匹配到 `sms-over-ip` 且无 `200 ok` | SMS over IP 流程未完成，需检查 IMS 注册状态。 |
| 匹配到 `vowifi` 且包含 `sms` 且包含 `fail` | VoWiFi 环境下 SMS 发送失败，需检查 WiFi 通话配置。 |
| 无匹配 | 日志中未定位到 SMS 关键流程，需确认是否为短信业务问题。 |

---

## data 数据域

### 匹配模式

| 模式 | 说明 |
|------|------|
| `\battach\b` | 附着流程 |
| `\bapn\b` | APN 配置 |
| `\bbearer\b` | 承载 |
| `\bdns\b` | DNS 解析 |
| `\bip\b` | IP 地址 |
| `\bpdn\b` | PDN 连接 |
| `\besm\b` | ESM 管理 |
| `\bemm\b` | EMM 管理 |
| `\bthroughput\b` | 吞吐量 |
| `\bdeactivate\b` | 去激活 |
| `\breject\b` | 拒绝 |
| `断流` | 断流关键字 |
| `无数据` | 无数据关键字 |

### 候选原因规则

| 条件 | 候选原因 |
|------|----------|
| 匹配到 `reject\|deactivate\|dns\|apn\|pdn\|esm` | 数据侧 attach / bearer / DNS / APN 流程中存在失败或拒绝。 |
| 无匹配 | 日志中未定位到稳定的数据业务流程，需先确认问题时间窗或业务域。 |

---

## sim 卡域

### 匹配模式

| 模式 | 说明 |
|------|------|
| `\banswertoreset\b` | ATR 响应 |
| `\batr\b` | ATR |
| `\+esims` | eSIM |
| `handlesimstatechanged` | SIM 状态变化 |
| `tranradioext` | Radio 扩展 |
| `updatesimstate.*(?:absent\|unknown\|card_io_error\|not_ready\|locked\|rejected\|error)` | SIM 状态异常 |
| `\bsim[_ -]?io[_ -]?error\b` | SIM IO 错误 |
| `\bicc.*(?:absent\|error\|reject)\b` | ICC 异常 |
| `\bno sim\b` | 无 SIM |
| `\bsim.*(?:absent\|unknown\|hotplug\|removed)\b` | SIM 移除/未知 |
| `\bicc\b` | ICC |
| `\bsim\b` | SIM |
| `\bcard io error\b` | 卡 IO 错误 |
| `\babsent\b` | 缺失 |
| `\bunknown\b` | 未知 |

### 候选原因规则

| 条件 | 候选原因 |
|------|----------|
| 匹配到 `answertoreset\|atr` | SIM 接触或 ATR 解析异常。 |
| 匹配到 `+esims\|handlesimstatechanged` | eSIM / Telephony 状态切换链路异常。 |
| 匹配到 `updatesimstate` | SIM 状态机上报异常。 |
| L0 子系统异常 | ModemEE / PhoneCrash 干扰了 SIM 结论，需要先恢复基础环境。 |
| 无匹配 | 未找到足够的 SIM 关键证据，建议先核对时间窗和 DUT 分组。 |

---

## 配置格式说明

### 匹配模式格式

```markdown
| 模式 | 说明 |
|------|------|
| `正则表达式` | 描述 |
```

### 候选原因规则格式

```markdown
| 条件 | 候选原因 |
|------|----------|
| 匹配到 `pattern1\|pattern2` | 候选原因描述 |
| 无匹配 | 默认候选原因 |
```

### 条件语法

- `匹配到 "pattern"` - 日志中存在匹配该模式的行
- `匹配到 "pattern1" 且包含 "pattern2"` - 同时满足两个条件
- `匹配到 "pattern" 且无 "pattern2"` - 匹配第一个但不匹配第二个
- `无匹配` - 该域没有任何匹配
- `L0 子系统异常` - L0 检测到子系统异常
