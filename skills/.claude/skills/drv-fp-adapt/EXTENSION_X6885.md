# X6885 指纹开发记录 — 飞书摘录

**定位**：指纹 P1 **主要调试**以主文档 [AI辅助指纹P1调试 / 升级项目指纹调试](https://transsioner.feishu.cn/wiki/A74wwMGsLiTCBXkMJjVccUDfnKd) 为准；本文为 X6885 专项**参考**摘录。

来源：[X6885 指纹开发记录](https://transsioner.feishu.cn/wiki/G2p1wEUC5iERW7kqhpMcyPkfnxd)（与仓库/Gerrit 现状不一致时以最新为准）

## 架构判定

- 在升级前内核指纹驱动目录确认（文档示例 xref）：`kernel/kernel-5.10/drivers/input/fingerprint/`。
- **仅一套 `tran_common` → 非归一化**；升级后仍应保持**非归一化**路径（`tran_fp_legacy` + `tran_common` / `CONFIG_TRAN_FINGERPRINT_LEGACY` 等与主 SOP、CM5 子文档一致）。

## 硬件

- 确认指纹器件型号（文档含选型截图占位）。
- **对照原理图**确认 GPIO（中断、复位、SPI 等）。

## 配置与评审链接（文档中的 Gerrit）

| 环节 | 链接 |
|------|------|
| DTS | <https://gerrit.transsion.com/c/MTK_CODE/quark/kernel_device_modules-6.12/+/1496434> |
| DWS preloader | <https://gerrit.transsion.com/c/MTK_CODE/alps/vendor/mediatek/proprietary/bootable/bootloader/preloader/+/1496576> |
| DWS custom | <https://gerrit.transsion.com/c/MTK_CODE/alps/vendor/mediatek/proprietary/custom/+/1496621> |
| DWS tools/dct | <https://gerrit.transsion.com/c/MTK_CODE/alps/vendor/mediatek/proprietary/tools/dct/+/1496757> |
| 工模 TranfacVnd | <https://gerrit.transsion.com/c/TRAN_CODE/vendor/transsion/tranfac/TranfacVnd/+/1496772> |
| 指纹库 projects | <https://gerrit.transsion.com/c/TRAN_OD_CODE/vendor/transsion/projects/+/1497683> |

## 一供极豪（文档要点）

- 指纹走 **SPI3**；指纹库需挂在 **ODM** 分区；接口切换到 **AIDL**。
- 以下两笔变更文档说明 **不要合入**，仅用于本地编译 **SO / TA** 库：

  - <https://gerrit.transsion.com/c/TRAN_CODE/vendor/transsion/bsp/fingerprint/+/1499747>
  - <https://gerrit.transsion.com/c/MTK_CODE/alps/device/mediatek/mt6789/+/1499731>

- **TA**：初始化 **SPI3**（文档含截图说明）。
- **CA**：设置加载 TA 的路径为 **`odm/app/mcRegistry`**。

## 二供思立微

- **X6855** 项目已升级且同为 **SPI3**：可将 X6855 侧库迁移至当前项目。
- 参考提交：<https://gerrit.transsion.com/c/TRAN_OD_CODE/vendor/transsion/projects/+/1508597>

## Agent 使用建议

- 以 Gerrit Change 为**对照清单**，在目标分支 cherry-pick 或手工移植时核对 **SPI 总线号、ODM 路径、AIDL HAL** 与主 SOP 是否一致。
- 文档中的 `image.png` 等占位在纯文本中无图，关键 GPIO / SPI 以**原理图与本地 DTS**为准。
