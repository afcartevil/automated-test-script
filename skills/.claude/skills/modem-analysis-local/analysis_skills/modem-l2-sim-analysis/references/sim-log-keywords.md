# SIM 卡日志搜索关键字清单

## 搜索优先级

### P0 — 硬件问题（必搜）
| 关键字 | 日志来源 | 含义 |
|--------|---------|------|
| `AnswerToReset` | radio_log / main_log | ATR 响应检测 |
| `No ATR` | ps.txt (Modem) | 无 ATR 响应 |
| `ESIM_PINS` | ps.txt (Modem) | SIM 引脚信号状态 |
| `SIM_DRV` | ps.txt (Modem) | SIM 驱动层事件 |
| `physical_card_reset` | ps.txt (Modem) | SIM 硬件复位 |
| `DCL_USIM_NO_ATR` | ps.txt (Modem) | USIM 无 ATR 错误码 |
| `SIM_DETECT` | ps.txt (Modem) | SIM 检测结果 |
| `SIM_RESET_ERROR` | ps.txt (Modem) | SIM 复位错误 |

### P1 — ESIMS 状态序列（必搜）
| 关键字 | 日志来源 | 含义 |
|--------|---------|------|
| `handleSimStateChanged, +ESIMS` | radio_log | 所有 ESIMS 状态变化 |
| `+ESIMS:0,1` | radio_log | SIM_ACCESS_ERROR |
| `+ESIMS:0,13` | radio_log | SIM_RECOVERY_START |
| `+ESIMS:1,14` | radio_log | SIM_RECOVERY_END |
| `+ESIMS:0,23` | radio_log | SIM_FAST_RECOVERY_START |
| `+ESIMS:1,24` | radio_log | SIM_FAST_RECOVERY_SUCCESS |
| `+ESIMS:0,17` | radio_log | SIM_CARD_TECHNICAL_PROBLEM |
| `+ESIMS:0,11` | radio_log | SIM_PLUG_OUT |
| `+ESIMS:1,12` | radio_log | SIM_PLUG_IN |
| `+ESIMS:1,29` | radio_log | SIM_STATE_ENABLE（识卡成功） |
| `AT+ESIMS?` | radio_log | 主动查询 SIM 状态 |

### P1 — SIM 状态与加载（必搜）
| 关键字 | 日志来源 | 含义 |
|--------|---------|------|
| `onSimStateChanged` | radio_log | SIM 状态变化（含状态码） |
| `CARDSTATE_ABSENT` | radio_log | 卡不存在 |
| `CARDSTATE_PRESENT` | radio_log | 卡存在 |
| `handleSimStateChange.*LOADED` | radio_log | SIM 加载完成 |
| `handleSimStateChange.*READY` | radio_log | SIM 就绪 |
| `sim busy` | radio_log | SIM 卡忙，需重试 |
| `handleGetSimStatusResponse` | radio_log | SIM 状态查询响应 |

### P2 — NAS 层状态（按需搜）
| 关键字 | 日志来源 | 含义 |
|--------|---------|------|
| `EMMUSIMSRV_USIM_REMOVED` | ps.txt (Modem) | NAS 层确认 USIM 移除 |
| `EMM_DEREGISTERED` | ps.txt (Modem) | EMM 去注册 |
| `NO_IMSI` | ps.txt (Modem) | 无 IMSI |

### P2 — 特殊场景（按需搜）
| 关键字 | 日志来源 | 含义 |
|--------|---------|------|
| `AT+CPIN?` | radio_log | 查询 PIN 码状态 |
| `+CPIN: SIM PIN` | radio_log | 需要 PIN 码 |
| `+CPIN: SIM PUK` | radio_log | 需要 PUK 码（PIN 输入错误过多） |
| `+CPIN: READY` | radio_log | PIN 码已解锁 |
| `PIN_REQUIRED` | radio_log / main_log | PIN 锁状态 |
| `simState.*2` | radio_log | simState=2 表示 PIN_REQUIRED |
| `onSimStateChanged.*1.*2` | radio_log | 状态从 ABSENT 变为 PIN_REQUIRED |
| `Emergency calls only` | main_log | 仅限紧急呼叫（可能是 PIN 锁定） |
| `OUT_OF_SERVICE` | main_log | 无服务（需结合 ICCID/ATR 判断是否 PIN 锁） |
| `eSIM ignore hot plug` | ps.txt (Modem) | eSIM 占用（仅 slot 1） |
| `MSG_ID_SIM_ERROR_IND` | ps.txt (Modem) | SIM 错误指示 |
| `Assert` / `ModemEE` | radio_log | Modem 异常 |
| `ESLOTSINFO` | radio_log | Slot 状态信息 |
| `MIPC_SIM_ESIM_SWITCH_SET_REQ` | radio_log | eSIM 开关切换请求（MODE=01 开，MODE=00 关） |
| `MIPC_SIM_ESIM_SWITCH_SET_CNF` | radio_log | eSIM 开关切换确认（ESIM_PSIM_STATE=01 eSIM，=00 pSIM） |
| `eid:32,` | radio_log | Slot 为 eSIM 卡槽（eid 非 0） |

### P3 — UI 层（按需搜）
| 关键字 | 日志来源 | 含义 |
|--------|---------|------|
| `MobileIconViewModel` | main_log | SIM 图标显示状态 |
| `ModernStatusBarMobileView` | main_log | 状态栏 SIM 视图 |
| `SIM_STATE_CHANGED` | main_log | SIM 状态广播 |
| `StatusBarNetworkRateView` | main_log | 网络速率视图 |

## 卡槽区分
- `[0]` / `[SIM_DRV:0]` / `slot 0` / `slotId=0` → SIM1
- `[1]` / `[SIM_DRV:1]` / `slot 1` / `slotId=1` → SIM2
