# 输入与派生上下文

## 开发者必填输入

任何适配开始前，先收集以下信息：

- `base_code`：升级前 vendor 分支绝对路径。
- `base_code_sunmao`：升级后 vendor 分支绝对路径。
- `project_name`：从 SPUG 获取的升级前项目编译选项。
- `features`：需要适配的 Audio 特性。

如果适配低功耗系统语音通话，还必须收集：

- 是否支持 ADSP。
- ADSP 类型：`HIFI` 系列或 `RV` 系列。

## 项目名解析

将 `project_name` 按 `_` 拆分。

- 第一段：`project_name1`
- 第二段：`project_name2`
- 第三段：`project_name3`
- 其他字段按顺序继续编号

多数 SOP 路径使用 `{project_name1}_{project_name2}`。如果拆不出至少两段，询问开发者正确的项目目录名。

## 升级后项目目录

默认候选目录：

```text
{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}
```

平台名查询固定使用 `{project_name1}_{project_name2}` 目录。按以下方式确认：

1. 如果默认候选目录存在，直接使用该目录。
2. 如果默认候选目录不存在，询问开发者确认 `{project_name1}_{project_name2}` 是否正确，或提供正确的项目目录名。

## 平台名获取

读取：

```text
{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}/ProjectConfig.mk
```

查找 `MTK_PLATFORM`，将其值作为 `platform_name`，并统一转为小写。

遇到以下情况必须询问开发者：

- 文件不存在
- `MTK_PLATFORM` 缺失
- 多个生效的 `MTK_PLATFORM` 值互相冲突

## 支持的特性名称

将用户输入归一化为以下内部名称：

- `dts`
- `dolby`
- `super_volume`
- `hac`
- `ultrasound_proximity`
- `low_power_call`
- `le_audio_offload`
- `usnd_anti_touch`
- `bttran_call`

如果请求的特性无法映射到以上名称，询问开发者该特性是否超出当前 SOP。
