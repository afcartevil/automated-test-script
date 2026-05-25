# PA 文件移植矩阵

本表是 4 种 PA × 4 类文件 × 2 种升级场景的 **源-目矩阵**。

- "升级前 PA 根" `{pre_pa_root}` = `{base_code}/device/transsion/{project_name_sunmao}/`
- "升级后 PA 根" `{post_pa_root}` = `{base_code_sunmao}/vendor/transsion/projects/{project_name_sunmao}/`

所有源路径采用 **OR 集合**——任一存在即可取该路径作为源。**全部不存在 → 必须问开发者**。

## 0. 旧文件清理（动手前先做）

在 `{post_pa_root}/audio/` 下，**统一全量删除** 下列四个 PA 专用目录（任一存在则删，不做"是否与当前 PA 类型匹配"的判定）：

- `aw87xxx/`：AW PA 专用目录
- `oca72xxx/`：OCA PA 专用目录
- `fs1599n/`：FS1599N 专用目录
- `fs1589n/`：FS1589N 专用目录

删完以后 `{post_pa_root}/audio/` 下不应残留任何 PA 子目录。

后续 §1~§4 在为"当前 PA 类型"移植文件时，会按需 **新建** 对应的子目录（例如当前 PA = AW，则在 §1 中新建 `{post_pa_root}/audio/aw87xxx/`）。

> 这样做的优势：① 不依赖"当前 PA 类型"判定的准确性，避免误删/误留；② 升级后侧的 PA 目录全部来自本轮新建，状态干净，便于复盘。
>
> **不要** 顺手把 `{post_pa_root}/audio/` 整个目录删掉——该目录下还有其他非 PA 内容（如本轮即将移植的 `audio_device.xml`、`audiotest/` 等）。

`audio_param/` 残留目录的处理见本文件 §5。

## 1. AW PA

### 1.1 固件

| 文件 | vnd12 非榫卯 源（取其一） | vnd14 非榫卯 源（取其一） | 升级后目标 |
| --- | --- | --- | --- |
| `aw87xxx_acf.bin` | `{pre_pa_root}/awinic/aw87xxx_acf.bin` | `{pre_pa_root}/audio/aw87xxx/aw87xxx_acf.bin` | `{post_pa_root}/audio/aw87xxx/aw87xxx_acf.bin` |
| `awinic_params.bin` | `{pre_pa_root}/awinic/awinic_params.bin` | `{pre_pa_root}/audio/aw87xxx/awinic_params.bin` | `{post_pa_root}/audio/aw87xxx/awinic_params.bin` |

### 1.2 SO（仅 vnd12 → vnd16 涉及，且必须重取）

- vnd14 → vnd14：**不需要 SO 移植**（vnd14 使用公共 so），SKILL 必须在阶段 1 摘要里明确告知开发者"已跳过 SO 移植"。
- vnd12 → vnd16：**禁止复制旧 so**。原因：ARSI API 从 1.6.0 升到 1.9.0 不兼容。强制未决项：
  - 通知 AFE 升级前后 ARSI API 版本 / PA 算法库版本 / 集成方式（AP 侧 / ADSP HIFI / ADSP RV55）/ PA 参数是否可复用。
  - 找 FAE 索取升级后的 PA 算法 so。

### 1.3 PA 参数

| 文件 | vnd12 非榫卯 源（取其一） | vnd14 非榫卯 源（取其一） | 升级后目标 |
| --- | --- | --- | --- |
| `AW_DSP.bin` | `{pre_pa_root}/awinic/AW_DSP.bin`<br/>`{pre_pa_root}/awinic/aurisys/AW_DSP.bin` | `{pre_pa_root}/audio/aw87xxx/smartpa_param/AW_DSP.bin` | `{post_pa_root}/audio/aw87xxx/smartpa_param/AW_DSP.bin` |
| `AW_SINWAVE_DSP.bin` | （vnd12 通常无此文件，缺则提示） | `{pre_pa_root}/audio/aw87xxx/smartpa_param/AW_SINWAVE_DSP.bin` | `{post_pa_root}/audio/aw87xxx/smartpa_param/AW_SINWAVE_DSP.bin` |

### 1.4 aurisys_config.xml

| 文件 | vnd12 非榫卯 源（取其一） | vnd14 非榫卯 源（取其一） | 升级后目标 |
| --- | --- | --- | --- |
| `aurisys_config.xml` | `{pre_pa_root}/awinic/aurisys_config.xml`<br/>`{pre_pa_root}/awinic/aurisys/aurisys_config.xml` | `{pre_pa_root}/audio/aw87xxx/aurisys_config.xml` | `{post_pa_root}/audio/aw87xxx/aurisys_config.xml` |

移植后 **强制** 路径改写（见 §6）。

## 2. FS1599N PA

> 软件配置表上写 `FS1588N` 一律视作 `FS1599N`。

### 2.1 固件

| 文件 | vnd12 非榫卯 源（取其一） | vnd14 非榫卯 源（取其一） | 升级后目标 |
| --- | --- | --- | --- |
| `fs1599.fsm` | `{pre_pa_root}/fs1599.fsm`<br/>`{pre_pa_root}/fs1599n/fs1599.fsm`<br/>`{pre_pa_root}/fsm_mtk_lib/fs1599.fsm` | `{pre_pa_root}/fsm_mtk_lib/fs1599.fsm`<br/>`{pre_pa_root}/audio/fs1599n/fs1599.fsm` | `{post_pa_root}/audio/fs1599n/fs1599.fsm` |

### 2.2 SO

- vnd14 → vnd14：不需要移植（公共 so）。
- vnd12 → vnd16：与 AW PA 同——禁止复制旧 so，必须找 FAE 重取 + 通知 AFE。

### 2.3 PA 参数

> 涉及 5 个文件：`preset_alarm.bin` / `preset_default.bin` / `preset_music.bin` / `preset_ringtone.bin` / `preset_voip.bin`。每个文件按下表独立 OR 选源。

| 文件 | vnd12 非榫卯 源目录（取其一） | vnd14 非榫卯 源目录（取其一） | 升级后目标目录 |
| --- | --- | --- | --- |
| `preset_*.bin`（5 个） | `{pre_pa_root}/`<br/>`{pre_pa_root}/fs1599n/`<br/>`{pre_pa_root}/fsm_mtk_lib/` | `{pre_pa_root}/fsm_mtk_lib/`<br/>`{pre_pa_root}/audio/fs1599n/` | `{post_pa_root}/audio/fs1599n/` |

### 2.4 aurisys_config.xml（注意文件名是 `aurisys_config_fs.xml`）

| 文件 | vnd12 非榫卯 源（取其一） | vnd14 非榫卯 源（取其一） | 升级后目标 |
| --- | --- | --- | --- |
| `aurisys_config_fs.xml` | `{pre_pa_root}/fsm_mtk_lib/aurisys_config.xml`<br/>`{pre_pa_root}/fsm_mtk_lib/aurisys_config_fs.xml`<br/>`{pre_pa_root}/fs1599n/aurisys_config_fs.xml`<br/>`{pre_pa_root}/aurisys_config_fs.xml` | `{pre_pa_root}/fsm_mtk_lib/aurisys_config_fs.xml`<br/>`{pre_pa_root}/audio/fs1599n/aurisys_config_fs.xml` | `{post_pa_root}/audio/fs1599n/aurisys_config_fs.xml` |

> 注意 vnd12 非榫卯下文件名可能为 `aurisys_config.xml`（无 `_fs` 后缀），但升级后侧统一改名为 `aurisys_config_fs.xml`。移植时按目标文件名落位，并完成 §6 的路径改写。

## 3. FS1589N PA

### 3.1 固件

| 文件 | vnd12 非榫卯 源（取其一） | vnd14 非榫卯 源（取其一） | 升级后目标 |
| --- | --- | --- | --- |
| `fs1589.fsm` | `{pre_pa_root}/fs1589n/fs1589.fsm` | `{pre_pa_root}/audio/fs1589n/fs1589.fsm` | `{post_pa_root}/audio/fs1589n/fs1589.fsm` |

### 3.2 SO

同 §1.2。

### 3.3 PA 参数

涉及 6 个文件：`preset_lp.bin` / `preset_default.bin` / `preset_music.bin` / `preset_ringtone.bin` / `preset_voip.bin` / `preset_voice.bin`。

| 文件 | vnd12 非榫卯 源目录（取其一） | vnd14 非榫卯 源目录（取其一） | 升级后目标目录 |
| --- | --- | --- | --- |
| `preset_*.bin`（6 个） | `{pre_pa_root}/`<br/>`{pre_pa_root}/fs1589n/`<br/>`{pre_pa_root}/fsm_mtk_lib/` | `{pre_pa_root}/fsm_mtk_lib/`<br/>`{pre_pa_root}/audio/fs1589n/` | `{post_pa_root}/audio/fs1589n/` |

### 3.4 aurisys_config_fs.xml

| 文件 | vnd12 非榫卯 源（取其一） | vnd14 非榫卯 源（取其一） | 升级后目标 |
| --- | --- | --- | --- |
| `aurisys_config_fs.xml` | `{pre_pa_root}/fsm_mtk_lib/aurisys_config.xml`<br/>`{pre_pa_root}/fsm_mtk_lib/aurisys_config_fs.xml`<br/>`{pre_pa_root}/fs1589n/aurisys_config_fs.xml`<br/>`{pre_pa_root}/aurisys_config_fs.xml` | `{pre_pa_root}/fsm_mtk_lib/aurisys_config_fs.xml`<br/>`{pre_pa_root}/audio/fs1589n/aurisys_config_fs.xml` | `{post_pa_root}/audio/fs1589n/aurisys_config_fs.xml` |

## 4. OCA PA

### 4.1 固件

| 文件 | vnd12 非榫卯 源 | vnd14 非榫卯 源 | 升级后目标 |
| --- | --- | --- | --- |
| `ocs72xxx_cf.bin` | `{pre_pa_root}/ocs/ocs72xxx_cf.bin` | `{pre_pa_root}/audio/oca72xxx/ocs72xxx_cf.bin` | `{post_pa_root}/audio/oca72xxx/ocs72xxx_cf.bin` |

### 4.2 SO

同 §1.2。

### 4.3 PA 参数

| 文件 | vnd12 非榫卯 源 | vnd14 非榫卯 源 | 升级后目标 |
| --- | --- | --- | --- |
| `ocs_params.bin` | `{pre_pa_root}/ocs/ocs_params.bin` | `{pre_pa_root}/audio/oca72xxx/ocs_params.bin` | `{post_pa_root}/audio/oca72xxx/ocs_params.bin` |

### 4.4 aurisys_config.xml

| 文件 | vnd12 非榫卯 源 | vnd14 非榫卯 源 | 升级后目标 |
| --- | --- | --- | --- |
| `aurisys_config.xml` | **vnd12 非榫卯无此文件**（跳出，问开发者是否需要新建） | `{pre_pa_root}/audio/oca72xxx/aurisys_config.xml` | `{post_pa_root}/audio/oca72xxx/aurisys_config.xml` |

## 5. `audio_param/` 残留清理（与 §6 路径改写独立）

检查 `{post_pa_root}/audio/audio_param/`：

- 存在 → 删除该目录（榫卯方案下参数已迁出 `vendor/etc`）。
- 不存在 → 跳过。

> 本步骤与 §6 的 aurisys xml 路径改写是 **两个独立操作**——它们没有顺序约束，也不互相依赖。aurisys xml 中的 `/vendor/etc/...` 字符串指向运行时 odm 落盘路径，与升级后侧仓库里 `{post_pa_root}/audio/audio_param/` 这个 **源码目录** 不是同一对象。两步可按任意顺序执行，或并行执行。

## 6. aurisys_config*.xml 路径改写规则（强制）

> 文件名拼写以仓库为准：`aurisys_config*.xml`。

所有 `aurisys_config*.xml` 移植到升级后目标路径后，**必须** 将文件中 **全部** `/vendor/etc/` 前缀统一替换为 `/odm/etc/vconfig/audio/`。涉及文件（存在则改）：

| 文件 | 典型落位 |
| --- | --- |
| `aurisys_config.xml` | `{post_pa_root}/audio/aw87xxx/` 或 `oca72xxx/` |
| `aurisys_config_fs.xml` | `{post_pa_root}/audio/fs1599n/` 或 `fs1589n/` |
| `aurisys_config_rv.xml` | `{post_pa_root}/audio/` |
| `aurisys_config_hifi3.xml` | `{post_pa_root}/audio/` |

### 6.1 替换规则（唯一规则）

对 **每个** 目标 xml 全文执行（StrReplace `replace_all` 或等价一次性格式化替换）：

```
/vendor/etc/  →  /odm/etc/vconfig/audio/
```

常见结果示例（子路径原样保留在 `audio/` 之后）：

| 升级前 | 升级后 |
| --- | --- |
| `/vendor/etc/audio_param` | `/odm/etc/vconfig/audio/audio_param` |
| `/vendor/etc/pa_param` | `/odm/etc/vconfig/audio/pa_param` |
| `/vendor/etc/aurisys_dsp_lib/...` | `/odm/etc/vconfig/audio/aurisys_dsp_lib/...` |

### 6.2 禁止误替换

| 字符串 | 是否改 |
| --- | --- |
| `/vendor/etc/` | **必须改**（仅出现在 aurisys_config*.xml 内） |
| `/vendor/lib`、`/vendor/lib64` | **禁止改**（SO 路径，仍在 vendor 分区） |
| `/vendor/etc`（无尾部 `/`） | 若 xml 内存在，改为 `/odm/etc/vconfig/audio`（去掉重复斜杠）；优先保证替换后路径合法 |

### 6.3 改完后强制 Grep 自检

在 `{post_pa_root}/audio/` 下对所有 `aurisys_config*.xml`：

```bash
# 不得残留 vendor/etc
grep -R '"/vendor/etc/' audio/aurisys_config*.xml audio/*/aurisys_config*.xml
# 期望：无输出

# 应出现 odm 前缀
grep -R '"/odm/etc/vconfig/audio/' audio/aurisys_config*.xml audio/*/aurisys_config*.xml
```

checkpoint 须报告：改写文件清单、每个文件 `/vendor/etc/` 命中数（改前）与残留数（改后必须为 0）。

## 7. 强制未决项（vnd12 → vnd16 专用）

在阶段 6 验收阶段 SKILL 必须把以下内容作为"开发者必须人工跟进项"列出（即使阶段 1 没人提）：

- [ ] 已通知 AFE：升级前 ARSI API 版本 = ?，升级后 ARSI API 版本 = ?，PA 算法库版本 = ?，集成方式（AP / ADSP HIFI / ADSP RV55）= ?，PA 参数是否可复用 = ?。
- [ ] 已找 FAE 索取升级后的 PA 算法 so 并按 FAE 指示落位。
- [ ] 升级后侧未误将 vnd12 旧 so 复制进 vendor 分区。

未完成上述事项前，本 SKILL 不应给出"PA 移植完成"的乐观结论。
