# 超声距感口袋防误触

## 路径

AP 侧宏控文件：

```text
{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}/ProjectConfig.mk
```

SCP 侧宏控文件：

```text
{base_code_sunmao}/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/{platform_name}/{project_name1}_{project_name2}/project.mk
```

升级前防误触参数文件：

```text
{base_code}/device/transsion/{project_name1}_{project_name2}/audio/usndantitouch/touchrej_config.json
```

升级后防误触参数文件：

```text
{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}/audio/usndantitouch/touchrej_config.json
```

## 步骤

1. 配置 AP 侧宏控：

```make
TRAN_AUDIO_ANTI_TOUCH_SUPPORT = yes
```

2. 配置 SCP 侧宏控：

```make
CFG_ANTI_TOUCH_ULTRASOUND_SUPPORT = yes
```

3. 将 `touchrej_config.json` 从升级前路径复制到升级后路径。

## 继续前必须询问

- `platform_name` 未知。
- SCP 侧宏控文件不存在。
- 升级前 `touchrej_config.json` 不存在。
- 升级后 `touchrej_config.json` 已存在且内容不同。
