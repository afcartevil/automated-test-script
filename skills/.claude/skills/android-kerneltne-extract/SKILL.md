---
name: android-kerneltne-extract
description: "Android-KernelTNE提取: 从Jira日志目录提取.tne文件，按异常编码分类解压+KSST64分析 | .tne/decompress/KSST64/0xffffff0c/HANG/HWT/KE/OCP_REBOOT | 当用户要求tne解压、异常编码分类、KSST64提取时使用"
---

# Android Kernel TNE 提取（decompress + KSST64）

## 依赖工具与位置

- `decompress`：`tools/decompress/`（源路径：`Z:/ai_tools/decompress/`）
- `SpOfflineDebugSuite`：`tools/SpOfflineDebugSuite/`（源路径：`Z:/ai_tools/SpOfflineDebugSuite/`）

如副本缺失或版本过旧，复制 `Z:/ai_tools` 下对应目录覆盖到本 skill 的 `tools/` 下。

## 处理目标

在 Jira 单关联日志目录下递归查找后缀为 `.tne` 的文件，重点处理这四类文件名前缀：

- `0xffffff0c_***.tne` -> HANG 异常
- `0xffffff0d_***.tne` -> HWT 异常
- `0xffffff04_***.tne` -> KE 异常
- `0xffffff15_***.tne` -> OCP_REBOOT 异常

## 标准流程

1. 获取日志根目录 `LOG_ROOT`
   - 用户给 Jira 单号时，先按既有流程下载日志到本地（可复用 `jira_login_download`）。
   - 用户已给路径时，直接使用该目录。

2. 查找 `.tne`
   - 在 `LOG_ROOT` 下递归查找 `*.tne`。
   - 对每个文件记录：文件路径、所属异常类型（按上述四类映射）。

3. 解压 `.tne`
   - 先判断 `.tne` 在含该文件的目录是否有写权限，若无写权限，先将 `.tne` 下载到本地，再执行以下步骤，若有写权限可以直接执行以下步骤
   - 在 `.tne` 文件所在目录执行：

```bash
decompress <xxx.tne>
```

   - 等价表述即：`decompress **.tne`（对匹配到的每个 `.tne` 逐个执行）。

4. 对解压生成目录执行 KSST64
   - 根据步骤 3 生成的最后一级目录：`path` + `dir_name`，执行：

```bash
printf '\nq\n' | ./SpOfflineDebugSuite/linux/KSST64 path/dir_name/
```

   - 在本 skill 中推荐使用绝对路径版本，避免依赖当前工作目录：

```bash
printf '\nq\n' | "$SKILL_ROOT/tools/SpOfflineDebugSuite/linux/KSST64" "$path/$dir_name/"
```

## 自动化脚本

可直接运行：

```bash
bash /path/to/repo/.cursor/skills/android-kerneltne-extract/scripts/kerneltne_extract_all.sh /path/to/LOG_ROOT
```

脚本会：
- 递归查找所有 `.tne`
- 自动分类（HANG/HWT/KE/OCP_REBOOT/OTHER）
- 执行 `decompress <file.tne>`
- 收集解压后最后一级目录，并逐个执行 `printf '\nq\n' | KSST64 <path/dir_name>/`

## 输出要求

向用户汇总以下信息：
- 共发现多少个 `.tne`，四类异常分别多少个
- 每个 `.tne` 的解压是否成功
- 每个 `path/dir_name` 的 KSST64 是否成功
- 失败项的错误信息与建议下一步
