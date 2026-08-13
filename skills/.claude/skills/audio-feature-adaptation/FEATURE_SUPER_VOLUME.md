# 大音量

## 路径

升级后项目音频参数目录：

```text
{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}/audio/audio_param/
```

升级后平台音频参数目录：

```text
{base_code_sunmao}/device/mediatek/vendor/common/audio_param/
```

## 步骤

1. 将以下文件从平台音频参数目录复制到项目音频参数目录：

```text
PlaybackVolDigi_AudioParam.xml
Speech_ParamUnitDesc.xml
SpeechUI_ParamUnitDesc.xml
SpeechVol_AudioParam.xml
VoIPVol_AudioParam.xml
Volume_AudioParam.xml
```

2. 修改 `PlaybackVolDigi_AudioParam.xml`：
   - 查找 `<Param path="Music,SPK" param_id="..."/>`。
   - 将其改为一个未使用的新 `param_id`，例如 `max_existing_param_id + 1`。
   - 在 `<ParamUnitPool>` 下使用同一个新 ID 添加以下 `ParamUnit`：

```xml
<ParamUnit param_id="NEW_ID">
        <Param name="digital_gain" value="-64,-48,-45,-42,-39,-36,-33,-30,-27,-24,-21,-18,-15,-12,-9,-6,-3,0"/>
</ParamUnit>
```

3. 修改 `Speech_ParamUnitDesc.xml`：
   - 在 `<CategoryType name="VolIndex" wording="Volume">` 中，确保 `0` 到 `16` 等级都存在。
   - 如果缺少 `15` 和 `16`，按以下方式添加：

```xml
<Category name="15" wording="Level15"/>
<Category name="16" wording="Level16"/>
```

4. 按照 `Speech_ParamUnitDesc.xml` 的同样方式修改 `SpeechUI_ParamUnitDesc.xml`。

5. 修改 `SpeechVol_AudioParam.xml`：
   - 查找 `<Param path="SPK" param_id="..."/>` 使用的 `param_id`。
   - 在对应 `ParamUnit` 中设置：

```xml
<Param name="dl_gain" value="40,39,38,37,34,31,28,25,22,19,16,14,12,10,7,4,1"/>
```

6. 修改 `VoIPVol_AudioParam.xml`：
   - 查找 `path="RCV"` 和 `path="SPK"` 使用的 `param_id`。
   - 在两个对应 `ParamUnit` 块中设置：

```xml
<Param name="dl_gain" value="40,39,38,37,34,31,28,25,22,19,16,14,12,10,7,4,1"/>
```

7. 修改 `Volume_AudioParam.xml`：
   - 查找 `<Param path="Common_SPK_LO" param_id="..."/>` 使用的 `param_id`。
   - 在对应 `ParamUnit` 中设置：

```xml
<Param name="spk_gain_level" value="18"/>
<Param name="spk_gain_db" value="-64,0,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17"/>
<Param name="spk_gain_idx" value="0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17"/>
<Param name="spk_gain_string" value="MUTE,0Db,2Db,3Db,4Db,5Db,6Db,7Db,8Db,9Db,10Db,11Db,12Db,13Db,14Db,15Db,16Db,17Db"/>
```

## 继续前必须询问

- 任一必要的平台参数文件缺失。
- 任一目标文件已存在，且与平台源文件不同。
- 无法找到 SOP 引用的 `path`。
- SOP 引用的 `param_id` 没有匹配的 `ParamUnit`。
- 无法确信地选择新的 `param_id`。
- 当前 XML 中已有项目自定义的大音量值，且与 SOP 目标值冲突。

## 开发者提醒

- 在 SCM 中配置 `ro.tr_audio.supervol.feature.support`。
