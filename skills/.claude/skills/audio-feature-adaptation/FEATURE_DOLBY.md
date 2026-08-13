# Dolby 音效

## 路径

升级后宏控文件：

```text
{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}/ProjectConfig.mk
```

升级前 Dolby 参数文件：

```text
{base_code}/device/transsion/{project_name1}_{project_name2}/audio/dolby/dax-default.xml
```

升级后 Dolby 参数文件：

```text
{base_code_sunmao}/vendor/transsion/vendor_modules/common/audiodolby/tuning/{project_name1}_{project_name2}/dax-default.xml
```

## 步骤

1. 在升级后宏控文件中配置以下宏控：

```make
DOLBY_TUNING_PATH := vendor/transsion/vendor_modules/common/audiodolby/tuning/{project_name1}_{project_name2}/
MEDIA_CODECS_C2_FILE := device/mediatek/{platform_name}/media_codecs_c2_svp.xml
TRAN_AUDIO_DOLBY_SUPPORT = yes
```

2. 将升级前 `dax-default.xml` 复制到升级后 Dolby 参数文件路径。

## 继续前必须询问

- 升级前 `dax-default.xml` 不存在。
- 目标 `dax-default.xml` 已存在，且与升级前文件不同。
- `platform_name` 未知。

## 开发者提醒

- 在 SCM 中配置 `persist.tr_audio.dolby.feature.support`。
