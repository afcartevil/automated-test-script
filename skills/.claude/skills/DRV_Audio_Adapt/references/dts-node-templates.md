# DTS 节点模板与 enum 数值表

本表给出阶段 2（kernel DTS）所需的全部节点模板与 enum 取值。**禁止凭印象**写 enum，必须按本表落值。

## 0. 升级后 DTS：格式与取值分离（强制）

| 维度 | 唯一依据 | 禁止 |
| --- | --- | --- |
| **节点格式**（节点名、挂在哪个 `&i2cX`/`&odm`、有哪些属性、属性写在哪个节点上） | **本文件各 § 模板 + [workflows/02-kernel-dts.md](../workflows/02-kernel-dts.md)** | 照搬升级前 DTS 整段；臆造模板外节点（如 `tran_audio` 解耦节点） |
| **属性取值**（`reg`、`dev_index`、`tran_pa_type`、`tran_typec_type`、GPIO 引脚号） | **升级前项目 DTS** Grep 同名属性；缺则问开发者 | 凭 sunmao 占位模板里的错误 GPIO/类型 |
| **DWS GPIO 字段**（mode/direction/pull 等） | **升级前 DWS** 中同 GPIO 编号节点 | 手写默认值 |

执行顺序：先按 §2.0 清空升级后项目 DTS 中 SOP 列出的音频节点 → 再**仅按本表模板**追加节点 → 属性值从升级前填入。

> **父总线一致性**：PA / HL1280 所用 `&i2cX` 编号、`reg` 等**取值**须与升级前一致；**写法**须符合本表模板，不得把升级前解耦格式原样复制到升级后。

> 调用顺序前提：阶段 2 必须先执行 [workflows/02-kernel-dts.md §2.0](../workflows/02-kernel-dts.md) 清空 SOP 列出的全部音频节点（含 `tran_audio` 等模板外遗留），再**仅按本表模板**追加。

## 1. PA 节点（按 PA 类型选其一）

| PA 类型 | DTS 节点名 |
| --- | --- |
| AW PA | `aw87xxx_pa` |
| OCA PA | `oca72xxx_pa` |
| FS1599N / FS1589N | `fs15xx_pa` |

移植步骤：

1. 在升级前 **项目 DTS**（`pre_project_dts_path`）中 Grep 当前 PA 节点，**仅提取取值**：I2C 总线号（`&i2cX`）、`reg`、`dev_index`、`status` 等。
2. 在升级后 DTS 的**同一 `&i2cX`** 下，按本表节点名与属性名**手写模板结构**追加 PA 子节点（禁止复制升级前整段含注释/多余属性的格式）。
3. **必须核对** I2C 总线编号与升级前一致；不一致 → 询问开发者。
4. checkpoint 记录：升级前/后 I2C 总线号、`reg`、`dev_index` 是否一致。

```dts
节点名@地址 {
    compatible = "xxx";
    reg = <X>;
    dev_index = < Y >;
    status = "okay";
};
```
## 2. `tran_audio_controller` 节点

固定模板（放置在 `&odm` 下）：

```dts
tran_audio_controller:tran_audio_controller {
    compatible = "tran-audio-controller";
    tran_pa_type = <X>;
    tran_typec_type = <Y>;
    typec_usb_change_gpio    = <&pio A 0>;
    audio_usb_switch_dio32020 = <&pio B 0>;
    mic_gnd_switch_dio1520    = <&pio C 0>;
};
```

属性配置规则：

### 2.1 `tran_pa_type`

来自内核 enum：

```
enum tran_pa_type {
    TRAN_PA_TYPE_MIN          = -1,
    TRAN_PA_TYPE_DEFAULT      = 0,
    TRAN_PA_TYPE_FS1599N      = 1,
    TRAN_PA_TYPE_AW87390      = 2,
    TRAN_PA_TYPE_SMARTPA_AW883XX = 3,
    TRAN_PA_TYPE_OCA72XXX     = 4,
    TRAN_PA_TYPE_FS1589N      = 5,
    TRAN_PA_TYPE_MAX,
};
```

| PA 类型 | 取值 |
| --- | --- |
| AW PA | `2`（`TRAN_PA_TYPE_AW87390`）|
| FS1599N | `1`（`TRAN_PA_TYPE_FS1599N`） |
| FS1589N | `5`（`TRAN_PA_TYPE_FS1589N`） |
| OCA PA | `4`（`TRAN_PA_TYPE_OCA72XXX`） |

### 2.2 `tran_typec_type`

来自内核 enum：

```
enum tran_typec_type {
    TRAN_TYPEC_TYPE_MIN     = -1,
    TRAN_TYPEC_TYPE_DEFAULT = 0,
    TRAN_TYPEC_TYPE_WAS4783C = 1,
    TRAN_TYPEC_TYPE_HL1280  = 2,
    TRAN_TYPEC_TYPE_DIO1520 = 3,
    TRAN_TYPEC_TYPE_MAX,
};
```

| typec switch 类型 | 取值 |
| --- | --- |
| HL1280 | `2` |
| DIO1520 | `3` |
| 3.5mm 耳机（非 typec） | **不配置该属性**（连同 `tran_audio_controller` 中关于 typec 的 GPIO 属性也省略） |

判定方法（**芯片类型**仅用升级前项目 DTS + 开发者硬件说明；**禁止**用升级后 sunmao 占位推断）：

- 在升级前 **项目 DTS**（`pre_project_dts_path`，非 `{platform_name}.dts`）中 Grep `hl1280`、`dio1520`、`tran_audio_sliptswitch`：
  - 仅命中 `hl1280` → HL1280（模板 §3.1）。
  - 命中 `dio1520` 或 `tran_audio_sliptswitch` → DIO1520（模板 §2 + §3.2）；**不得**因升级前存在 `tran_audio` 解耦节点而在升级后保留该节点。
  - 都未命中 → 3.5mm。
  - 都命中 → 跳出，问开发者。
- 开发者明确硬件型号与升级前判定冲突 → 停下确认。

### 2.3 GPIO 三件套

三个 GPIO **只写在 `tran_audio_controller` 节点上**（DIO1520 / HL1280 的 TypeC 均如此）。从升级前 **项目 DTS**（`pre_project_dts_path`）Grep 同名属性，**仅抄引脚编号** `<&pio <num> 0>`，写入升级后模板 §2 的 `tran_audio_controller`：

| 属性 | 适用场景 | 不适用时 |
| --- | --- | --- |
| `typec_usb_change_gpio` | TypeC 耳机（HL1280 / DIO1520 任一） | 3.5mm 耳机时省略 |
| `audio_usb_switch_dio32020` | 仅 DIO1520 | HL1280 / 3.5mm 时省略 |
| `mic_gnd_switch_dio1520` | 仅 DIO1520 | HL1280 / 3.5mm 时省略 |

> 升级前 DTS 中能搜到属性但 typec 类型判定为 3.5mm（或反之）→ 必须停下问开发者，不要自动取舍。
>
> GPIO 号沿用升级前值（板级一致性），不要凭印象改。

## 3. typec switch 节点

按 typec 类型选其一：

### 3.1 HL1280

在升级前 **项目 DTS**（`pre_project_dts_path`）读取 `reg`、I2C 总线号；在升级后 DTS 对应 `&i2cX` 下按下列**固定结构**追加（禁止复制升级前整段）：

```dts
hl1280-audioswitch@<reg> {
    compatible = "mediatek,hl1280-audioswitch";
    reg = <0x??>;
    status = "okay";
};
```

### 3.2 DIO1520

**必须同时满足** §2 `tran_audio_controller`（含 `tran_typec_type = <3>` 与 §2.3 三件套 GPIO）**与**下列两节点（放在 `&odm` 下）。**禁止**使用升级前解耦节点 `tran_audio`；**禁止**在 `tran_audio_sliptswitch_gpio` 上写 GPIO 属性。

```dts
tran_audio_sliptswitch {
    compatible = "transsion,sliptswitch-audioswitch";
};

tran_audio_sliptswitch_gpio {
    compatible = "transsion,sliptswitch-gpio-audioswitch";
};
```

> 两节点**仅**包含 `compatible`，不得追加 `typec_usb_change_gpio` 等属性。  

### 3.3 3.5mm

不需要 typec switch 节点。

## 4. 阶段 2 自检

阶段 2 执行完后，自检并在 checkpoint 里列出：

- PA 节点：是否已移植，是否挂在正确的 I2C 总线（升级前/升级后总线一致性）。
- `tran_audio_controller` 节点：是否在 `&odm` 下；`tran_pa_type` / `tran_typec_type` / 三个 GPIO 属性是否齐全且与 PA / typec 类型自洽。
- typec switch 节点（仅 TypeC 耳机时）：HL1280 节点是否挂正确的 I2C；DIO1520 两节点是否在 `&odm` 下且**仅含 compatible**。
- 升级后 DTS 中 **不得** 出现模板外节点名：`tran_audio`、升级前解耦遗留节点等（§2.0 清理后 Grep 应为 0）。
- 升级前后 GPIO 号是否完全一致。
- 父节点一致性：PA/HL1280/typec 控制节点的"升级前父节点 vs 升级后父节点"是否逐项一致，并在 checkpoint 中显式列出。
