# 输入与派生上下文

## 开发者必填输入

任何自检开始前，先收集以下信息：

- `base_code_sunmao`：升级后的 vnd/vendor 侧绝对路径。
- `project_name`：从 SPUG 获取的项目编译选项全名。
- `features`：需要自检的 Audio 特性。

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

按以下方式确认：

1. 如果默认候选目录存在，直接使用该目录。
2. 如果默认候选目录不存在，询问开发者确认 `{project_name1}_{project_name2}` 是否正确，或提供正确的项目目录名。

## 宏控适配文件

当前 SOP 中的宏控检查文件为：

```text
{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}/ProjectConfig.mk
```

如果文件不存在，结论为 `无法判断`，并将该文件路径列为阻塞项。

## 支持的特性名称

将用户输入归一化为以下内部名称：

- `hac_mtk`：听力助手-MTK、HAC-MTK、HAC、听力助手、`MTK_HAC_SUPPORT`

如果请求的特性无法映射到以上名称，询问开发者该特性是否超出当前 SOP。
