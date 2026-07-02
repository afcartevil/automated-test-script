# 无网通讯

## 路径

宏控文件：

```text
{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}/ProjectConfig.mk
```

项目音频参数目录：

```text
{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}/audio/audio_param/
```

平台音频参数目录：

```text
{base_code_sunmao}/device/mediatek/vendor/common/audio_param/
```

## 步骤

1. 配置以下宏控：

```make
TRAN_AUDIO_BTTRANCALL_SUPPORT = yes
```

2. 将以下文件从平台音频参数目录复制到项目音频参数目录：

```text
VoIPv2_ParamUnitDesc.xml
VoIPVol_ParamUnitDesc.xml
```

3. 修改 `VoIPv2_ParamUnitDesc.xml`：
   - 查找 `<CategoryType name="Scene" feature_option="VIR_SCENE_CUSTOMIZATION_SUPPORT">`。
   - 确保其中包含：

```xml
<Category name="Bttranchatscene" wording="Bttranchatscene" visible="true"/>
```

最终代码块应包含 `Default`、`App1`、`App2` 和 `Bttranchatscene`。

4. 修改 `VoIPVol_ParamUnitDesc.xml`：
   - 查找 `<CategoryType name="Scene" feature_option="VIR_SCENE_CUSTOMIZATION_SUPPORT">`。
   - 确保其中包含：

```xml
<Category name="Bttranchatscene"/>
```

最终代码块应包含 `Default`、`App1`、`App2` 和 `Bttranchatscene`。

## 继续前必须询问

- 任一必要的平台参数文件缺失。
- 目标参数文件已存在，且与平台源文件不同。
- 找不到目标 `CategoryType`。
- `Bttranchatscene` 已存在但属性不同。
