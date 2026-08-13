# 听力助手

## 路径

升级后宏控文件：

```text
{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}/ProjectConfig.mk
```

## 步骤

在升级后宏控文件中配置以下宏控：

```make
MTK_HAC_SUPPORT = yes
```

## 继续前必须询问

- 升级后宏控文件不存在。
- 宏控已存在但值冲突，并且上下文显示 HAC 可能是被项目有意关闭的。
