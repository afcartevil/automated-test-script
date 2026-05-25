# ProjectConfig.mk 音频宏控表

升级后目标文件（落位点）：`{base_code_sunmao}/vendor/transsion/projects/{project_name_sunmao}/ProjectConfig.mk`。

## 0. 三级 fallback 决策树（每个宏控必须走完）

1. **优先级 1：升级前文件**。在 [variables.md §6.1](variables.md) 列出的 4 个升级前 `ProjectConfig*.mk` 文件中按宏控名 Grep。命中即采用升级前值。
2. **优先级 2：软件配置表**。若升级前 4 个文件全部未命中该宏控，依下方"每个宏控的软件配置表映射"取值。
3. **优先级 3：SOP 默认原则**。若软件配置表上也没有，按下方"默认原则"取值。
4. 三层都不能确定 → **停下问开发者**，禁止臆造。

> 同一宏控在升级前文件中多处出现且取值不同：以"项目层 > overlay > BSP > device/transsion 公共层"的就近原则取值，并在阶段 1 摘要里显式提示开发者人工 review 这条冲突。

## 1. 宏控全表

下表中"可选值"按当前 vnd 在用项目实践归纳。出现表外值时不要自己映射，问开发者。

### 1.1 扬声器 / 听筒

| 宏控 | 含义 | 可选值 | 软件配置表映射 | 默认原则 |
| --- | --- | --- | --- | --- |
| `MTK_AUDIO_SPEAKER_PATH` | 扬声器接线方式 | `int_hp_buf`（PA 接在耳机通路）/ `int_lo_buf`（PA 接 LO 通路）/ `smartpa_xxx` | 看 SPK PATH：`LO` → `int_lo_buf`；`HP` → `int_hp_buf`；智能 PA 走 `smartpa_xxx` | 未知必问 |
| `MTK_AUDIO_NUMBER_OF_SPEAKER` | 扬声器个数（MTK 侧） | `1` / `2` | SPK 个数 | 单 SPK → `1`；双 SPK → `2` |
| `TRAN_AUDIO_RCV_PA_CONNENT` | 听筒外部是否连接 PA（即是否双扬） | `yes` / `no` | 看 SPK 个数 | 双 SPK → `yes`；单 SPK → `no` |
| `TRAN_AUDIO_RCV_PATH` | 听筒走的通路 | `hpl`（借耳机左声道驱动听筒）/ `rcv_mux`（原生听筒专用通路） | 看通路 | 默认 `rcv_mux` |

### 1.2 麦克风

| 宏控 | 含义 | 可选值 | 软件配置表映射 | 默认原则 |
| --- | --- | --- | --- | --- |
| `MTK_AUDIO_NUMBER_OF_MIC` | mic 个数（MTK 侧） | `1` / `2` / `3` / ... | MIC 个数 | — |
| `TRAN_AUDIO_NUMBER_OF_MIC` | mic 个数（客制化侧） | 与上同步 | MIC 个数 | 与 `MTK_AUDIO_NUMBER_OF_MIC` 保持一致 |
| `MTK_DUAL_MIC_SUPPORT` | 是否双 mic | `yes` / `no` | MIC 个数 ≥ 2 → `yes` | — |
| `TRAN_AUDIO_MODE_OF_PHONEMIC` | 手机 mic 模式 | `1`（AMIC 模拟）/ `2`（DMIC 数字） | `PHONE_MIC_MODE` 或 MIC 类型 | 未知必问 |
| `TRAN_AUDIO_MODE_OF_HEADSETMIC` | 耳机 mic 模式 | `1`（AMIC）/ `2`（DMIC） | `HEADSET_MIC_MODE` | 未知必问 |

### 1.3 通话降噪

| 宏控 | 含义 | 可选值 | 软件配置表映射 | 默认原则 |
| --- | --- | --- | --- | --- |
| `MTK_INCALL_HANDSFREE_DMNR` | 语音通话免提双麦降噪 | `yes` / `no` | 配置表字段同名 | 双 MIC 且无明确关 → 沿用升级前 |
| `MTK_VOIP_HANDSFREE_DMNR` | VoIP 通话免提双麦降噪（平台降噪） | `yes` / `no` | 同上 | 同上 |

### 1.4 智能功放（PA）

| 宏控 | 含义 | 可选值 | 软件配置表映射 | 默认原则 |
| --- | --- | --- | --- | --- |
| `MTK_SPK_AP_SWMIX_PROCESS` | PA aurisys 算法处理前是否在 AP 侧 SW 混音（需 PA 自身支持） | `true` / `false` | — | AW PA → `true`；FSM PA（`FS1599N` / `FS1589N`）→ `false`；OCS / OCA PA → `true` |
| `TRAN_AUDIO_FS1599N_SUPPORT` | 是否使用 FS1599N | `yes` / `no` | PA 型号 = FS1599N（**FS1588N 视作 FS1599N**） | 当前 PA=FS1599N 时写 `yes`；其余不用写 |
| `TRAN_AUDIO_FS1589N_SUPPORT` | 是否使用 FS1589N | `yes` / `no` | PA 型号 = FS1589N | 当前 PA=FS1589N 时写 `yes`；其余不用写 |
| `TRAN_AUDIO_AW87XXX_SUPPORT` | 是否使用 AW PA | `yes` / `no` | PA 型号 = AW | 当前 PA=AW 时写 `yes`；其余不用写 |
| `TRAN_AUDIO_OCA72XXX_SUPPORT` | 是否使用 OCA PA | `yes` / `no` | PA 型号 = OCA | 当前 PA=OCA 时写 `yes`；其余不用写 |

> 4 个 PA 类型宏控必须 **互斥**——只能有一个为 `yes`。其余宏控为 `no` （缺省不写即可）。多于一个 `yes` 或 0 个 `yes` → 必须问开发者。

### 1.5 算法框架 / 后处理

| 宏控 | 含义 | 可选值 | 软件配置表映射 | 默认原则 |
| --- | --- | --- | --- | --- |
| `MTK_AURISYS_FRAMEWORK_SUPPORT` | 是否启用 Aurisys 框架 | `yes` / `no` | 同名字段 | 沿用升级前；未知必问 |
| `MTK_BESLOUDNESS_SUPPORT` | 是否支持 DRC（Bessound） | `yes` / `no` | 同名字段 | 同上 |
| `MTK_BESLOUDNESS_RUN_WITH_HAL` | DRC 是否在 HAL 侧运行 | `yes` / `no` | 同名字段 | 同上 |
| `MTK_AUDIO_HD_REC_SUPPORT` | 是否支持高清录音 | `yes` / `no` | 同名字段 | 同上 |

### 1.6 耳机接口

| 宏控 | 含义 | 可选值 | 软件配置表映射 | 默认原则 |
| --- | --- | --- | --- | --- |
| `TRAN_AUDIO_TYPEC_SUPPORT` | 是否 TypeC 耳机接口 | `true` / `false` | TypeC 耳机字段 | **芯片类型**以升级前项目 DTS 判定（见 [dts-node-templates.md §2.2](dts-node-templates.md)）：`hl1280` / `dio1520` / `tran_audio_sliptswitch` 任一命中 → `true`；都未命中 → `false`。升级后 DTS **写法**须符合升级后模板，与宏控判定相互独立。 |

## 2. 配置原则汇总（机械流程，不要绕过）

对 §1 列出的每个宏控，依次走：

1. 在升级前 4 个 ProjectConfig 文件里 Grep 宏控名 → 命中即抄。
2. 否则按"软件配置表映射"列查表。
3. 否则按"默认原则"列查表。
4. 仍无定论 → 问开发者。

冲突点处理：

- 升级前文件值与软件配置表值冲突 → 默认采用 **升级前文件**，但在阶段 1 摘要里把冲突显式列给开发者审阅（typical 案例：换 PA 型号时软件配置表先改、升级前文件还没改）。
- 4 个 PA SUPPORT 宏控的互斥性必须在最终落盘前再校验一次（判定标准：恰好 1 个 `yes`；其余缺省不写）。

## 3. 写入策略

升级后 ProjectConfig.mk 落位文件：`{base_code_sunmao}/vendor/transsion/projects/{project_name_sunmao}/ProjectConfig.mk`。

- 若目标文件中已存在该宏控行 → 用 StrReplace 替换右值，保留原赋值符号（`:=` / `?=` / `=`）。
- 若目标文件中不存在 → 在文件尾追加（或追加到最相近的同前缀宏控所在区段），用 `:=` 赋值，保持每行一个宏控。
- 对 4 个 PA `*_SUPPORT` 宏控：默认仅确保当前 PA 对应宏控为 `yes`；其余宏控若不存在可保持缺省，不强制补 `no`。
- 不要新增本表外的宏控。表外宏控的需求 → 跳出 SOP，问开发者并显式标注"非 SOP 范围"。

## 4. 阶段 1 完成时的强制自检

阶段 1（projects repo）执行完后，本 SKILL 必须自检以下点并在 checkpoint 摘要里给出 yes/no：

1. 4 个 PA `*_SUPPORT` 宏控是否互斥（恰好 1 个 `yes`；其余为 `no` （缺省不屑写））
2. `MTK_AUDIO_NUMBER_OF_MIC` 与 `TRAN_AUDIO_NUMBER_OF_MIC` 是否一致。
3. `MTK_DUAL_MIC_SUPPORT` 与 mic 个数是否一致（≥2 ⇔ `yes`）。
4. `TRAN_AUDIO_RCV_PA_CONNENT` 与 `MTK_AUDIO_NUMBER_OF_SPEAKER` 是否一致（双扬 ⇔ `yes`）。
5. `MTK_AUDIO_SPEAKER_PATH` 与 PA 类型 / `MTK_SPK_AP_SWMIX_PROCESS` 是否搭配合理。
6. `TRAN_AUDIO_TYPEC_SUPPORT` 是否与 DTS 中 `hl1280` / `dio1520` 关键字的命中情况一致。

任一不一致 → 不视为 SKILL 失败，但必须在 checkpoint 摘要里明确列出"待人工确认项"。
