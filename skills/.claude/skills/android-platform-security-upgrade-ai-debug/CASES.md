# 典型案例（摘自飞书 SOP 表述）

SOP：[安全 AI调试SOP](https://transsioner.feishu.cn/docx/JIq0dLEfHopv90xzzDScU7RFnTb)

## 案例1：衍生项目与 anti_ver.json

**现象**：x6885b 为 x6885 衍生项目；升级前分支可能没有 x6885b 独立配置。

**处理**：事实上继承 x6885；**升级后分支**需在 `anti_ver.json` 中增加对衍生项目的配置，并与继承关系一致。

## 案例2：AVB 路径随仓库结构变化

**现象**：升级前在 `tran_projects/lj7/lj7_h782_d1/lj7/device/transsion/lj7_h782/ProjectConfig_BSP.mk` 配置 `TRAN_AVB_REMOTE_SIGN_SUPPORT`。

**处理**：升级后在 `vendor/transsion/projects/lk6_h582/ProjectConfig.mk`（产品目录名以实际为准）保持同一宏取值。

## 案例3：RPMB 门控导入

**现象**：升级前 `ProjectConfig_BSP.mk` 中 `TRAN_ENABLE_RPMB=yes`。

**处理**：按 SOP 导入实体 RPMB：dts `tran,rpmb_control`、preloader RPMB/TEE 宏、升级后 `ProjectConfig.mk` 中 `TRAN_RPMB_SUPPROT` 与 `TRAN_ENABLE_RPMB_FACTORY_SUPPORT`。

## 案例4：RPMB 文件分散三处

**现象**：需同时改 kernel dts、preloader custom mk、Tran `ProjectConfig.mk`。

**处理**：SOP 举例路径包括 `kernel/.../mediatek/cla6_h8910.dts`、`preloader/custom/x6895b_h8925/x6895b_h8925.mk`、`vendor/transsion/projects/lk6_h582/ProjectConfig.mk`；实际以当前项目文件名为准。
