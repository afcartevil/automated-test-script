# DWS GPIO 移植规则（preloader / tools/dct / proprietary/custom 共用）

阶段 3 / 4 / 5 共用同一套"从 DTS 推导出需移植的 GPIO、再写入对应 DWS"的逻辑，差别只在目标文件路径。

## 1. 需移植的 GPIO 列表（从 DTS 推导）

读取**阶段 2 完成后**升级后侧 DTS 中 **`tran_audio_controller` 节点**上的 GPIO 属性（升级后模板规定三件套 GPIO 均写在该节点；禁止从已删除的 `tran_audio` 等遗留节点取号）：

| DTS 属性 | DWS 中需要配置的 GPIO 含义 |
| --- | --- |
| `typec_usb_change_gpio` | TypeC 接小板时的 USB change 切换 GPIO |
| `audio_usb_switch_dio32020` | DIO1520 使用的 USB switch GPIO |
| `mic_gnd_switch_dio1520` | DIO1520 使用的 MIC GND switch GPIO |

GPIO 编号示例（出自 SOP 给的样例）：

```dts
tran_audio_controller:tran_audio_controller {
    compatible = "tran-audio-controller";
    tran_pa_type = <2>;
    tran_typec_type = <3>;
    typec_usb_change_gpio     = <&pio 189 0>;
    audio_usb_switch_dio32020 = <&pio 43 0>;
    mic_gnd_switch_dio1520    = <&pio 18 0>;
};
```

→ 需在 DWS 中配置 GPIO189 / GPIO43 / GPIO18。

## 2. 取值原则

- **存在性以 DTS 为准**：阶段 2 完成后的升级后 DTS 中存在哪些属性，DWS 就配哪些 GPIO。DTS 中没有的属性，DWS 不补。
- **数值以升级前 DWS 为准**：从 [variables.md §6.1](variables.md) 给出的升级前 DWS 文件中 Grep 这些 GPIO 编号，把升级前 DWS 中的配置（mode / level / driving 等所有字段）原样抄到升级后 DWS 中。
- 升级前 DWS 中找不到对应 GPIO 配置 → 必须问开发者（说明升级前可能没有跑通 typec / PA 切换，不能硬补默认值）。

## 3. 目标文件

阶段共用本表 §1/§2 的判定，仅写入位置不同：

| 阶段 | 升级后目标 DWS |
| --- | --- |
| 阶段 3：preloader | `{base_code_sunmao}/vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/{project_name_sunmao}/dct/dct/codegen.dws` |
| 阶段 4：tools/dct | `{base_code_sunmao}/vendor/mediatek/proprietary/tools/dct/dws/{platform_name}/{project_name_sunmao}.dws` |
| 阶段 5：proprietary/custom | `{base_code_sunmao}/vendor/mediatek/proprietary/custom/{project_name_sunmao}/kernel/dct/dct/codegen.dws` |

## 4. 操作要点

- DWS 是 XML 风格的二进制工具配置文件，不要"按 macro 风格"瞎编结构。每个 GPIO 在 DWS 中通常是一个 `<GPIO>` 节点，节点完整字段（mode / direction / pull / level / driving）要照搬升级前；用 Read 看升级前 DWS 的具体节点结构再用 StrReplace 修改对应字段，不要 Write 整段重写。
- 找到升级前 DWS 中目标 GPIO 节点的方法：按 GPIO 编号 Grep（如 `<PinNum>189`），定位节点起止后整段比对。
- 三个阶段共用一份"升级前 DWS"作为唯一数据源，但写到三个不同的"升级后 DWS"中。三个目标 DWS 中关于这几条 GPIO 的配置应当 **完全一致**。

## 5. 自检（阶段 5 完成后强制比对）

- 三个目标 DWS 中（仅当对应 GPIO 存在于 DTS 时）：GPIO 编号一致、模式一致、电平一致。
- 若三处之间出现配置不一致，必须在阶段 5 checkpoint 里显式给出 diff，让开发者定夺，**不要**自动以哪一个为准。

## 6. 跳出条款

- 升级前 DWS 文件不存在（变量推导失败）→ 跳出 SOP，问开发者是否有备份或参考项目。
- 升级前 DWS 存在但 GPIO 节点缺失（DTS 有该属性但 DWS 没配过）→ 视为升级前未完整跑通，必须问开发者是否硬要在升级后侧新增（新增时基于 GPIO 通用默认配置只是"勉强方案"，需开发者明确签字）。
