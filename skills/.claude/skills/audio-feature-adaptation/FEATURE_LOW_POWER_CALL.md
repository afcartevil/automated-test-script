# 低功耗系统语音通话

## 额外必要输入

以下任一信息未知时，执行前必须先询问：

- 是否支持 ADSP
- ADSP 类型：`HIFI` 系列或 `RV` 系列

## 路径

AP 侧宏控文件：

```text
{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}/ProjectConfig.mk
```

HIFI ADSP 侧宏控文件：

```text
{base_code_sunmao}/vendor/mediatek/proprietary/tinysys/adsp/HIFI3/project/{platform_name}/HIFI3_A/{project_name1}_{project_name2}/project.mk
{base_code_sunmao}/vendor/mediatek/proprietary/tinysys/adsp/HIFI3/project/{platform_name}/HIFI3_B/{project_name1}_{project_name2}/project.mk
```

HIFI Aurisys 配置文件：

```text
{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}/audio/aurisys_config_hifi3.xml
```

RV Aurisys 配置文件：

```text
{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}/audio/aurisys_config_rv.xml
```

## 步骤

1. 如果 ADSP 类型为 `HIFI`，配置以下 AP 侧宏控：

```make
MTK_AUDIODSP_SUPPORT = yes
```

如果 ADSP 类型为 `RV`，该步骤不配置 AP 侧宏控。

2. 如果 ADSP 类型为 `HIFI`，在两个 HIFI ADSP 侧宏控文件中配置以下宏控：

```make
CFG_MTK_AUDIODSP_SUPPORT = yes
```

如果 ADSP 类型为 `RV`，跳过 ADSP 侧宏控配置。

3. 修改对应的 Aurisys 配置文件：
   - `HIFI`：修改 `aurisys_config_hifi3.xml`。
   - `RV`：修改 `aurisys_config_rv.xml`。

对于 `AURISYS_SCENARIO_DSP_PHONE_CALL`，将上行和下行库都设置为 `mtk_sp`：

```xml
<aurisys_scenario aurisys_scenario="AURISYS_SCENARIO_DSP_PHONE_CALL">
    <uplink_library_name_list digital_gain_lib_name="mtk_sp">
        <library name="mtk_sp"/>
    </uplink_library_name_list>
    <downlink_library_name_list digital_gain_lib_name="mtk_sp">
        <library name="mtk_sp"/>
    </downlink_library_name_list>
</aurisys_scenario>
```

## 继续前必须询问

- ADSP 支持情况或 ADSP 类型未知。
- ADSP 类型既不是 `HIFI` 也不是 `RV`。
- ADSP 类型为 `HIFI` 时，任一必要 HIFI ADSP 宏控文件缺失。
- 选定的 Aurisys 配置文件缺失。
- 找不到 `AURISYS_SCENARIO_DSP_PHONE_CALL`。
- 该场景中存在额外的项目自定义库，直接替换可能移除预期行为。
