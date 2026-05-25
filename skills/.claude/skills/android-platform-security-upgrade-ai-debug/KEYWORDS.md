# 关键字、宏与路径参考（飞书 SOP 原文对齐）

SOP 来源：[安全 AI调试SOP](https://transsioner.feishu.cn/docx/JIq0dLEfHopv90xzzDScU7RFnTb)

## 路径模板（将 `(project_name)`、`(platform_name)` 替换为实际值）

### DA 动态防回滚

- 平台：`vendor/mediatek/proprietary/bootable/bootloader/preloader/platform/(platform_name)/default.mak`
- 项目：`vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/(project_name)/(project_name).mk`

### BROM 端口禁用

- 平台：`vendor/mediatek/proprietary/bootable/bootloader/lk2/platform/mediatek/(platform_name)/rules.mk`
- 项目：`vendor/mediatek/proprietary/bootable/bootloader/lk2/project/(project_name).mk`

### 软件防回滚

- Preloader 项目：`vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/(project_name)/(project_name).mk`
- LK2 项目：`vendor/mediatek/proprietary/bootable/bootloader/lk2/project/(project_name).mk`
- 版本号文件：`vendor/mediatek/proprietary/scripts/sign-image_v2/anti_ver.json`

### AVB 在线签名（SOP 示例路径）

- 升级前示例：`tran_projects/<proj>/<product>_.../<proj>/device/transsion/<product>/ProjectConfig_BSP.mk`
- 升级后示例：`vendor/transsion/projects/<product>/ProjectConfig.mk`

### 实体 RPMB（SOP 示例）

- DTS 示例：`kernel/kernel_device_modules-6.12/arch/arm64/boot/dts/mediatek/<具体>.dts`（以仓库为准）
- Preloader 项目：`vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/<project>/<project>.mk`
- Project：`vendor/transsion/projects/<product>/ProjectConfig.mk`

## 宏与配置项（用于搜索 / grep）

竖线分隔便于一次检索：

```
TRAN_DA_ANTI_ROLLBACK_VER|TRAN_BLOW_DISBROM_SUPPORT|MTK_SECURITY_ANTI_ROLLBACK|CONFIG_TRAN_DYNAMIC_BLOW_OTP_VER|TRAN_AVB_REMOTE_SIGN_SUPPORT|TRAN_RPMB_SUPPROT|TRAN_ENABLE_RPMB_FACTORY_SUPPORT|TRAN_ENABLE_RPMB|CFG_RPMB_SET_KEY|CFG_RPMB_KEY_PROGRAMED_IN_KERNEL|CFG_TEE_SUPPORT
```

## Preloader 软件防回滚（SOP 给定写法）

```
MTK_SECURITY_ANTI_ROLLBACK=yes
CONFIG_TRAN_DYNAMIC_BLOW_OTP_VER=yes
export CONFIG_TRAN_DYNAMIC_BLOW_OTP_VER
```

## LK2 软件防回滚（SOP 给定写法）

```
CONFIG_TRAN_DYNAMIC_BLOW_OTP_VER := yes
MTK_SECURITY_ANTI_ROLLBACK := yes
```

## RPMB：DTS 片段（SOP 给定）

```
&mobicore {
    tran,rpmb_control = <1>;
};
```

## RPMB：Preloader（SOP 给定）

```
CFG_RPMB_SET_KEY=1
CFG_RPMB_KEY_PROGRAMED_IN_KERNEL=1
CFG_TEE_SUPPORT := 1
export CFG_RPMB_SET_KEY CFG_RPMB_KEY_PROGRAMED_IN_KERNEL CFG_TEE_SUPPORT
```

## RPMB：Project（SOP 给定，注意 SOP 原文拼写）

```
TRAN_RPMB_SUPPROT=yes
TRAN_ENABLE_RPMB_FACTORY_SUPPORT=yes
```

## 门控（SOP 示例）

升级前 `ProjectConfig_BSP.mk` 中若 `TRAN_ENABLE_RPMB=yes` 则导入 RPMB 相关配置。
