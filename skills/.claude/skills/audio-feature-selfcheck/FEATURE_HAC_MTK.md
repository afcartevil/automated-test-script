# 听力助手-MTK

## 检查路径

宏控适配文件：

```text
{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}/ProjectConfig.mk
```

## 自检步骤

1. 确认宏控适配文件存在。
2. 检查宏控适配文件中是否包含有效宏控：

```makefile
MTK_HAC_SUPPORT = yes
```

## 结论规则

- 存在有效 `MTK_HAC_SUPPORT = yes`：`已适配`
- 不存在有效 `MTK_HAC_SUPPORT`：`未适配`
- 存在有效 `MTK_HAC_SUPPORT` 但值不是 `yes`：`未适配`
- 文件不存在、路径变量无法确定、或 `MTK_HAC_SUPPORT` 存在多个互相冲突的有效值：`无法判断`

## 证据要求

报告中必须列出：

- `ProjectConfig.mk` 的绝对路径
- `MTK_HAC_SUPPORT` 的命中情况
- 有效行内容和行号；未命中时说明未找到有效宏控
