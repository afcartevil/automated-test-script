# 超声波距感

## 路径

AP 侧宏控文件：

```text
{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}/ProjectConfig.mk
```

SCP 侧项目目录：

```text
{base_code_sunmao}/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/{platform_name}/{project_name1}_{project_name2}/
```

SCP 侧宏控文件：

```text
{base_code_sunmao}/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/{platform_name}/{project_name1}_{project_name2}/project.mk
```

SCP 侧 cache 链接文件：

```text
{base_code_sunmao}/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/{platform_name}/{project_name1}_{project_name2}/inc/cache_ld.h
```

升级前超声库：

```text
{base_code}/vendor/mediatek/proprietary/tinysys/scp/middleware/uSnd/elliptic/{platform_name}/{project_name1}_{project_name2}/libelliptic_engine.a
```

升级后超声库：

```text
{base_code_sunmao}/vendor/mediatek/proprietary/tinysys/scp/middleware/uSnd/elliptic/{platform_name}/{project_name1}_{project_name2}/libelliptic_engine.a
```

## 步骤

1. 配置 AP 侧宏控：

```make
TRAN_AUDIO_ELLIPTIC_USND_SUPPORT = yes
TRAN_AUDIO_ELLIPTIC_NOSPEAKER_SUPPORT = yes
MTK_ULTRASND_PROXIMITY = yes
```

2. 配置 SCP 侧宏控：

```make
CFG_MTK_ULTRASND_PROXIMITY = yes
```

平台适用时，只配置其中一个平台宏控：

```make
CFG_PLATFORM_MT6897 = yes
CFG_PLATFORM_MT6878 = yes
```

仅当 `platform_name` 为 `mt6897` 时配置 `CFG_PLATFORM_MT6897`。仅当 `platform_name` 为 `mt6878` 时配置 `CFG_PLATFORM_MT6878`。其他平台不添加这两个宏控。

3. 在 `inc/cache_ld.h` 中添加超声 cache 链接代码。

如果是 `mt6878`：

```c
#if defined(CFG_MTK_ULTRASND_PROXIMITY)
#define ULTRA_TEXT_SECTIONS             .text*
#define ULTRA_DATA_SECTIONS             .rodata* .data* .bss* *COMMON
#define CACHE_ULTRASOUND_TEXT \
    $?*/middleware/uSnd/elliptic/mt6878/?*.a:*.obj$(ULTRA_TEXT_SECTIONS)\
    $?*/middleware/uSnd/elliptic/elliptic_engine_wrapper.o$(ULTRA_TEXT_SECTIONS)\
    $?*/middleware/sensorhub/drivers/virtual/elliptic_fusion/elliptic_fusion_sensor.o$(ULTRA_TEXT_SECTIONS)\
    $?*/middleware/sensorhub/algos/RV55_A/fusion/elliptic/elliptic_fusion_wrapper.o$(ULTRA_TEXT_SECTIONS)
#define CACHE_ULTRASOUND_DATA \
    $?*/middleware/uSnd/elliptic/mt6878/?*.a:*.obj$(ULTRA_DATA_SECTIONS)\
    $?*/middleware/uSnd/elliptic/elliptic_engine_wrapper.o$(ULTRA_DATA_SECTIONS)\
    $?*/middleware/sensorhub/drivers/virtual/elliptic_fusion/elliptic_fusion_sensor.o$(.data* .bss* *COMMON)\
    $?*/middleware/sensorhub/algos/RV55_A/fusion/elliptic/elliptic_fusion_wrapper.o$(ULTRA_DATA_SECTIONS)
#endif
```

如果是 `mt6897`：

```c
#if defined(CFG_MTK_ULTRASND_PROXIMITY)
#define ULTRA_TEXT_SECTIONS             .text*
#define ULTRA_DATA_SECTIONS             .rodata* .data* .bss* *COMMON
#define CACHE_ULTRASOUND_TEXT \
        $?*/middleware/uSnd/elliptic/mt6897/?*.a:*.obj$(ULTRA_TEXT_SECTIONS)
#define CACHE_ULTRASOUND_DATA \
        $?*/middleware/uSnd/elliptic/mt6897/?*.a:*.obj$(ULTRA_DATA_SECTIONS)
#endif
```

如果是其他平台，使用通用模板，并将 `{platform_name}` 替换为实际平台名：

```c
#if defined(CFG_MTK_ULTRASND_PROXIMITY)
#define ULTRA_TEXT_SECTIONS             .text*
#define ULTRA_DATA_SECTIONS             .rodata* .data* .bss* *COMMON
#define CACHE_ULTRASOUND_TEXT \
        $?*/middleware/uSnd/elliptic/{platform_name}/?*.a:*.obj$(ULTRA_TEXT_SECTIONS)
#define CACHE_ULTRASOUND_DATA \
        $?*/middleware/uSnd/elliptic/{platform_name}/?*.a:*.obj$(ULTRA_DATA_SECTIONS)
#endif
```

4. 将 `libelliptic_engine.a` 从升级前超声库路径复制到升级后超声库路径。

## 继续前必须询问

- `platform_name` 未知。
- SCP 项目目录、`project.mk` 或 `inc/cache_ld.h` 缺失。
- `cache_ld.h` 中已经存在与 SOP 片段不同的超声 cache 定义。
- 升级前 `libelliptic_engine.a` 不存在。
- 升级后 `libelliptic_engine.a` 已存在且内容不同。

## 开发者提醒

在 SCM 中配置以下属性：

- `ro.odm.tr_audio.midtest_ultrasound.support`
- `ro.tr_audio.ultrasound.support`
- `ro.vendor.audio.us.proximity`
