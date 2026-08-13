# KE 详细分析步骤

## 总流程

1. 归类异常（先分支）
2. 对齐时间与版本（建基线）
3. 锁定主证据（栈与关键日志）
4. 符号映射（地址到函数）
5. 分支深挖（按类型）
6. 输出结论（Jira 化）

## 步骤1: 归类异常

### 操作
1. 读取 `__exp_main.txt` 的 `Exception Class/Type`。
2. 读取 `out.json` 的 `exception_type` 交叉验证。
3. 记录 `CRDISPATCH_KEY` 用于快速路由。

### 输出
- 归类结果: `KE-Oops/Panic | ATF_CRASH | HWT/HWR | Hang detect | OCP reboot | 其他`
- 置信度: `高/中/低`

## 步骤2: 建立分析基线

### 操作
1. 从 `__exp_main.txt` 提取 build 指纹、机型、SoC、时间。
2. 从 `_分析报告.txt` 提取平台与版本。
3. 对照 `SYS_VERSION_INFO` 校验符号版本。

### 规则
- 基线冲突（平台/版本不一致）必须写入报告。
- 未完成版本校验，不进入最终代码级结论。

## 步骤3: 主证据定位

### 操作
1. 按优先级检索:
   - `SYS_KERNEL_LOG`
   - `SYS_LAST_KMSG`
   - `sys_pstore_raw`（若有）
2. 搜索关键词: `backtrace|pc|lr|kernel offset|BUG|Oops|Kernel panic - not syncing`。
3. 从 backtrace 中剔除公共异常框架，定位首个业务相关栈帧。

### 输出
- 关键线程/CPU
- 关键函数地址与调用链
- 异常触发时间线

## 步骤4: 符号映射

### 操作
1. 确认版本后获取匹配 `vmlinux` 与相关 `ko`。
2. 使用 `addr2line` 或 `gdb/trace32` 做地址映射。
3. 形成“日志地址 -> 函数 -> 文件行号”闭环。

### 规则
- 符号不匹配时，标记“结论仅到模块级，非代码行级”。

## 步骤5: 分支实操

### A. KE-Oops/Panic
- 判断标志: `Kernel panic - not syncing` / `BUG` / `Oops`
- 核查点: fault address、寄存器、首个业务栈帧

### B. ATF_CRASH
- 区分:
  - `Unhandled Exception in EL3` -> exception 路径
  - `PANIC in` / `assert` -> assert/panic 路径
- 若有 `SYS_TFA_BL31_RAMDUMP`，优先升级 MTK 深入解析


## 步骤6: Jira 化输出

最少包含:
1. 异常分类与触发场景
2. 崩溃 CPU/线程与关键函数
3. 证据三件套:
   - 关键日志原文（文件名 + 关键行）
   - 调用栈链路
   - 符号映射信息（vmlinux/ko 版本）
4. 初步结论（高/中/低置信度）
5. 下一步动作（补日志/复现/协同/提 CR）
