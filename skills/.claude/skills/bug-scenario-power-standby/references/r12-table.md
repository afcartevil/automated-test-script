# SPM 唤醒原因 R12 — 名称与位索引参考

**目录**：§1 SOP 列出源 · §2 Legacy 32 槽 · §3 新旧命名 · §4 操作建议 · §5 多比特 r12 / `r12_ext`

**必读声明**

- **R12 位定义随芯片与内核版本变化**；飞书 sheet / 内部 Excel 与 **`${platform}_pcm_def.h`**（或 `spm_def.h` / `mt_*_spm_pcm.h` 等）为 **最终依据**。  
- 本文件 = **SOP 所列名称** + **可公开追溯的 legacy 字符串表** + **新旧命名对照**。若三者冲突，以 **当前项目头文件 + 实机 log** 为准，结论打 **`待验证`** 直到核对完成。

***

## 1. 《功耗待机问题分析 SOP》直接列出的唤醒源（优先用于本 Skill 叙事）

与内部文档 **§步骤 2.2** 一致：

| 名称（log 中常见） | 含义 / 排查方向（SOP） |
|--------------------|-------------------------|
| **R12_EINT_EVENT_B** | 外部中断；可 `cat /proc/interrupts`；常与 PMIC / RTC / alarm 等配合 |
| **R12_CONN2AP_SPM_WAKEUP_B** | connsys 唤醒；应用经 WiFi 等联网时，可结合 **netlog** 定位应用 |
| **R12_SCP2SPM_WAKEUP_B** | SCP / sensor 相关（如 VOW 等） |
| **R12_CCIF0_EVENT_B** | modem **CCCI**；继续在 log 里跟 **ccci channel** |
| **R12_AP2AP_PEER_EVENT_B** | modem **数据业务**；旧平台或见 **R12_CLDMA_EVENT_B**；结合 **netlog** |
| *别名* **R12_CLDMA_EVENT_B** | 与上行类似（旧命名） |

**debug_flag / r13**：若 SOP 规则要求看 **r13** 各位，**必须** 对照 **当前平台 pcm 定义**；勿凭本表臆解 bit。

***

## 2. Legacy `wakesrc_str[]`（32 槽位）— 来源与用法

以下为 **Android 公开树** 中 `mt_spm_internal.c`（**`kernel/mediatek` android-mtk-3.18**）里 **`wakesrc_str[32]`** 的字符串表，用于理解 **「`r12 = 0x??` 对应哪些位置位」** 的**常见命名**：

源文件路径（可追溯）：  
`kernel/mediatek` → `drivers/misc/mediatek/base/power/spm_v2/mt_spm_internal.c`（blob 历史版本可查）。

| Bit | 字符串名（legacy 表） |
|-----|------------------------|
| 0 | R12_PCM_TIMER |
| 1 | R12_MD32_WDT_EVENT_B |
| 2 | R12_KP_IRQ_B |
| 3 | R12_APWDT_EVENT_B |
| 4 | R12_APXGPT1_EVENT_B |
| 5 | **R12_CONN2AP_SPM_WAKEUP_B** |
| 6 | **R12_EINT_EVENT_B** |
| 7 | R12_CONN_WDT_IRQ_B |
| 8 | **R12_CCIF0_EVENT_B** |
| 9 | R12_LOWBATTERY_IRQ_B |
| 10 | R12_MD32_SPM_IRQ_B |
| 11 | R12_26M_WAKE |
| 12 | R12_26M_SLEEP |
| 13 | R12_PCM_WDT_WAKEUP_B |
| 14 | R12_USB_CDSC_B |
| 15 | R12_USB_POWERDWN_B |
| 16 | R12_C2K_WDT_IRQ_B |
| 17 | R12_EINT_EVENT_SECURE_B |
| 18 | R12_CCIF1_EVENT_B |
| 19 | R12_UART0_IRQ_B |
| 20 | R12_AFE_IRQ_MCU_B |
| 21 | R12_THERM_CTRL_EVENT_B |
| 22 | R12_SYS_CIRQ_IRQ_B |
| 23 | R12_MD2_WDT_B |
| 24 | R12_CSYSPWREQ_B |
| 25 | R12_MD1_WDT_B |
| 26 | **R12_CLDMA_EVENT_B** |
| 27 | R12_SEJ_WDT_GPT_B |
| 28 | R12_ALL_MD32_WAKEUP_B |
| 29 | R12_CPU_IRQ_B |
| 30 | R12_APSRC_WAKE |
| 31 | R12_APSRC_SLEEP |

### 从 `r12 = 0x40` 的数学说明（与 SOP 案例 2 原文一致）

- **数论**：`0x40 = 1 << 6`，在 §2 表中将 **bit 6** 标为 **`R12_EINT_EVENT_B`**。**仅用于核对**：当且仅当你确认 §2 表适用于当前内核，且 **log 中该行 `r12 = 0x40`**，才可如此称呼；否则只复述 **十六进制**。

***

## 3. 新旧平台命名对照（口述规则，非位对齐保证）

| 新/常用描述（SOP / 新平台 log） | 可能对应的 legacy / 旧名 |
|--------------------------------|---------------------------|
| **R12_AP2AP_PEER_EVENT_B**（modem 数据） | 常与 **R12_CLDMA_EVENT_B**（bit 26）同一责任域；以头文件为准 |
| **R12_SCP2SPM_WAKEUP_B** | 可能占用原 MD32/SCP 相关若干 bit 之一；**必须以当前 SoC 表为准** |

***

## 4. 分析时建议操作

1. 在 kernel 中搜索 **`suspend wake up by`** / **`SPM] wake up by`**，读出 **`r12=`** 十六进制。  
2. 对 `r12` 做 **按位或**，对照 **当前项目** `wakesrc_str` 或 `spm_sleep_res` 调试符号（新内核可能有 **扩展 `r12_ext`**，勿忽略）。  
3. 对 SOP 强调的 **conn / modem / sensor** 几类，优先与 **netlog、CCCI、connsys sleep 统计** 交叉验证。  
4. 无法在仓库内找到对应表时：报告中写 **「位含义待芯片文档确认」**，并保留 **原始 `r12`/`r12_ext` 行** 作为证据。

***

## 5. 多比特 `r12`、`r12_ext` 与掩码算术（非测量数据）

### 5.1 一次唤醒多原因并存

- `r12` **可同时置多位**：当 **现场日志** 中 `r12` 的 **置位个数 > 1** 时，应在 **核对你所分析的内核** 中 `wakesrc_str`（或等价表）后，**逐位**列出名称；**主次排序** 只能依据 **本时间窗内 log 的出现频次、与耗电路径的时序关联**（均需 **Evidence**），**禁止**凭主观「哪个更耗电」瞎排序。  
- 若 log 打印 **`r12_ext`**：表示 **扩展唤醒域**（平台相关），**不可**仅用 §2 的 32 槽表解码；需 **同仓库 SPM 驱动** 中的扩展字符串表或 TRM。**无表则不要解读具体 bit 含义。**

### 5.2 掩码与 §2 legacy 名称的**纯数学对照**（教学用）

下表 **不是** 任何项目的实测采样表，也 **不是** 鼓励你在报告中填写这些十六进制——**仅说明**：若且唯若 **现场 `r12=` 恰好为该值**，且你 **已确认** §2 表适用于当前内核版本，才可对应到下列名称。

| 十六进制 | 置位 bit（十进制） | 对应 §2 名称（**仅当内核表一致时**） |
|----------|-------------------|--------------------------------------|
| `0x20` | 5 | R12_CONN2AP_SPM_WAKEUP_B |
| `0x40` | 6 | R12_EINT_EVENT_B（SOP 案例 2 原文为 `r12 = 0x40`） |
| `0x60` | 5 与 6 | 为上两行之按位或；表示 **两位同时置位** 时需分别举证 |
| `0x100` | 8 | R12_CCIF0_EVENT_B |
| `0x04000000` | 26 | R12_CLDMA_EVENT_B |

将 **现场 `r12=`** 转为二进制后对为 1 的 bit 查 **你内核** 的表；**对不上** 则保留原始十六进制并标 **`待验证`**，**禁止** 强套上表。
