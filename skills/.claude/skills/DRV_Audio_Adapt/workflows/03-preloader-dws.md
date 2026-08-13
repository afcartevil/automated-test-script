# 阶段 3：alps/vendor/mediatek/proprietary/bootable/bootloader/preloader DWS

**目标 repo**：`MTK_CODE/alps/vendor/mediatek/proprietary/bootable/bootloader/preloader`

**目标文件**：`{base_code_sunmao}/vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/{project_name_sunmao}/dct/dct/codegen.dws`

数据源：[references/dws-gpio-rules.md](../references/dws-gpio-rules.md)。

## 一、执行

1. Read 阶段 2 完成后的升级后 DTS 中的 `tran_audio_controller` 节点，列出存在的 GPIO 属性与编号。
2. 从升级前 DWS（`{base_code}/tran_projects/{project_name1}/{project_name}/{project_name1}/vendor/mediatek/proprietary/tools/dct/dws/{platform_name}/{project_name_sunmao}.dws`）中按 GPIO 编号 Grep 定位每个 GPIO 节点。
3. 把升级前 GPIO 节点的完整字段（mode / direction / pull / level / driving 等所有字段）抄到升级后目标 DWS 中对应 GPIO 节点：
   - 目标 DWS 中已存在该 GPIO 节点 → StrReplace 替换字段值。
   - 目标 DWS 中不存在该 GPIO 节点 → 跳出问开发者（DWS 是由工具按 schema 生成，不要凭手写补节点）。

## 二、自检（按 [dws-gpio-rules.md §5](../references/dws-gpio-rules.md)，阶段 5 完成后整体比对）

阶段 3 本身只做"完成 preloader 这一份 DWS"。三个 DWS 的一致性在阶段 5 末统一校验。

## 三、阶段 3 Checkpoint

| 项 | 内容 |
| --- | --- |
| 本阶段改了什么 | 列出升级后 preloader DWS 中改动的 GPIO（编号 + 关键字段值）；列出未改动的 GPIO（避免漏配） |
| 还差什么 | 升级前 DWS 缺该 GPIO / 节点结构不一致 / DTS 与升级前 DWS 互相缺失 |
| 是否继续 | 默认询问"是否进入阶段 4（tools/dct DWS）？" |

## 四、跳出条款

- 升级前 DWS 不存在或不可读 → 跳出，问开发者是否有备份。
- 升级前 DWS 中目标 GPIO 节点缺失（DTS 有但 DWS 无）→ 跳出，问开发者是否本就没启用，**不要**靠默认值硬补。
