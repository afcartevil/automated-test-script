# 叶子 Skill 目录路由（Jira / 现象 → 文件夹）

## 1. 路径约定

- 本表中的 **目录名** 与「通信」仓库根下**同级文件夹**一致（与 `com-comm-analysis-foundation`、`com-comm-sop-source-archive` 并列）。
- 每个叶子内入口文件固定为：**`<目录名>/SKILL.md`**；按需再打开同目录 `references/` 下专题 `.md`。
- **协作分析推荐顺序**（给 Agent）：
  1. 读 `com-comm-analysis-foundation/SKILL.md` 定输出模板与证据规则；读 `references/problem-routing-index.md` 定主/辅域。
  2. 用 **本表** 选定 **1 个主叶子目录**，打开其 `SKILL.md`（patterns / normal_log）。
  3. 仅当已定位跨域断点时，再增加 **最多 1 个**辅助叶子或 foundation 内 `references/` 辅助专题（与 `problem-routing-index.md` 一致）。
  4. 需对照原始 SOP 或设计稿时，再打开 `com-comm-sop-source-archive/`。

## 2. 平台列选择（MTK / UNISOC / COMMON）

| 线索 | 优先选用的叶子前缀 |
| --- | --- |
| Jira / 缺陷单芯片字段为 MTK，或日志/属性明确 MTK 机型 | `mtk-*` |
| 芯片字段为 UNISOC / 展锐，或明确展锐平台 | `uns-*` |
| 明确为跨芯片公共、或未限定芯片且存在对应 `com-*` 目录 | `com-*` |
| 同现象同时存在 `mtk-*` 与 `uns-*`，平台不明 | 先 `com-*`（若有）；否则并列阅读两个平台叶子中的 **一个为主**，另一个仅作对比差异 |

---

## 3. Call / 补充业务 / Flash Call

| 典型现象 / Jira 场景 | MTK 叶子目录 | UNISOC 叶子目录 | 其它 |
| --- | --- | --- | --- |
| 拨打电话失败、建立慢、自动挂断、误拨、VoWiFi 视频通话失败、呼叫转移/等待等 | `mtk-call-dialfail` | `uns-call-dialfail` | — |
| 来电接听失败 | `mtk-call-incominganswerfail` | `uns-call-incominganswerfail` | — |
| 紧急通话号码识别异常 | `mtk-call-emergencynumber` | — | — |
| FLASH_CALL_15.xx 失败 | — | `uns-call-flashcall15` | — |
| FLASH_CALL_16 / FLASH_CALL 异常 | `mtk-fl16-flashcall16` | — | — |

---

## 4. SMS / MMS

| 典型现象 | MTK | UNISOC | COMMON |
| --- | --- | --- | --- |
| 发送短信失败 | `mtk-sms-smssendfail` | `uns-sms-smssendfail` | — |
| 接收短信失败 | `mtk-sms-smsrecvfail` | `uns-sms-smsrecvfail` | — |
| 发送彩信失败 | `mtk-sms-mmssendfail` | `uns-sms-mmssendfail` | — |
| 接收彩信失败 | `mtk-sms-mmsrecvfail` | `uns-sms-mmsrecvfail` | — |
| 短信应用 UI / 文案 / 操作体验 | — | — | `com-sms-smsappui` |

---

## 5. SIM / UICC / 状态栏网络呈现

| 典型现象 | MTK | UNISOC | COMMON |
| --- | --- | --- | --- |
| 识卡异常 | `mtk-sim-simdetect` | `uns-sim-simdetect` | — |
| 状态栏网络/VoLTE/VoWiFi/HD 等图标异常 | `mtk-sim-statusbaricon` | `uns-sim-statusbaricon` | — |
| 运营商名称显示异常 | `mtk-sim-operatorname` | `uns-sim-operatorname` | — |
| USSD 文案错误 | — | — | `com-sim-ussdwrongtext` |
| USSD 流程异常 | — | — | `com-sim-ussdflow` |
| APN 配置/界面异常 | — | — | `com-sim-apnchange` |

---

## 6. Network / Data

| 典型现象 | 目录名 | 备注 |
| --- | --- | --- |
| 时区识别错误 | `com-network-timezonewrong` | COMMON |
| 漫游状态异常 | `com-network-roamingstate` | COMMON |
| 信号差、无服务、驻网异常、制式显示异常等 | `com-network-signalabnormal` | COMMON |
| 数据速率慢、吞吐低 | `mtk-network-dataslow` | MTK |
| 数据连接建立失败 | `com-data-datasetupfail` | COMMON |
| 数据不稳定、频繁断开 | `com-data-dataunstable` | COMMON |
| 智能双卡切换失败 | `com-data-ddsswitchfail` | COMMON |
| DATA_STALL / 蜂窝与 Wi‑Fi 切换异常 | `com-dstall-datastall` | COMMON |

---

## 7. Stability / Modem

| 典型现象 | 目录名 |
| --- | --- |
| 异常开关机 | `com-stab-abnormalpowercycle` |
| MODEM_EE 弹窗等 | `mtk-modem-ee-modemee` |

---

## 8. 显示电源 / 背光 / 亮灭屏（COMMON）

以下均为 `com-pwr-*`，与芯片无关时在下列目录中按现象择一：

| 典型现象 | 目录名 |
| --- | --- |
| 自动背光异常 | `com-pwr-autobacklight` |
| 手动调亮度异常 | `com-pwr-manualbrightness` |
| 应用切换亮度异常（非视频/相机） | `com-pwr-brightnessappswitch` |
| 视频/相机界面切换亮度异常 | `com-pwr-brightnessvideocamera` |
| 进入 HBM 异常 | `com-pwr-hbmenter` |
| 退出 HBM 异常 | `com-pwr-hbmexit` |
| 超时自动息屏异常 | `com-pwr-timeoutscreenoff` |
| 灭屏过程异常 | `com-pwr-screenoffanim` |
| 电源键亮屏异常 | `com-pwr-pwrkeywake` |
| 双击亮屏异常 | `com-pwr-doubletapwake` |
| 通知亮屏异常 | `com-pwr-notifwake` |
| 通话贴近灭屏异常 | `com-pwr-proximityscreenoff` |
| 通话贴近灭屏后移开亮屏异常 | `com-pwr-proximitywakeaftercall` |

---

## 9. 传感器（MTK）

| 典型现象 | 目录名 |
| --- | --- |
| 光感快速上报 / 环境切换亮度跟随异常 | `mtk-sensor-alsfastreport` |

---

## 10. 元 Skill（非现象叶子，用于协作）

| 目录名 | `name` | 何时与现象叶子叠加载 |
| --- | --- | --- |
| `com-comm-analysis-foundation` | `com-comm-analysis-foundation` | 定域前、定输出口径、升级/术语、与多叶子协作时 |
| `com-comm-sop-source-archive` | `com-comm-sop-source-archive` | 需引用原始 SOP / 设计文档时 |

---

## 11. 与 `problem-routing-index.md` 的衔接

- **域级**断点（Call 上层 vs 协议、Network vs SIM）仍以 `problem-routing-index.md` 为准。
- **落到具体 grep patterns / normal_log** 时，必须用本表进入对应 **叶子目录**；`call-analysis.md` 等专题文只解决「怎么看问题」，不替代叶子里的 **patterns 清单**。
