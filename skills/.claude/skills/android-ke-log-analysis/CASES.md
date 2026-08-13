# KE 典型案例

## 案例1: ATF exception（EL3）

### 现象
重启后 DB 显示 ATF crash。

### 分析过程
1. `SYS_TFA_CRASH_REPORT` 搜到 `Unhandled Exception in EL3`。
2. 在 `__exp_main.txt/out.json` 确认异常归类为 ATF 分支。
3. 检查是否存在 `SYS_TFA_BL31_RAMDUMP` 并准备转 MTK。

### 结论
ATF exception 路径，优先 MTK 深入定位；本地仅输出触发场景与前后行为证据。

## 案例2: KE panic（代码级定位）

### 现象
系统出现 panic 重启。

### 分析过程
1. `SYS_KERNEL_LOG` 搜到 `Kernel panic - not syncing`。
2. 提取 backtrace，定位首个业务相关栈帧。
3. 用匹配版本 `vmlinux/ko` 进行 addr2line 映射。

### 结论
从“日志地址 -> 函数 -> 文件行号”闭环后，给出代码级根因方向。

## 案例3: 平台版本冲突

### 现象
报告平台与 build 指纹不一致，导致符号映射失败。

### 分析过程
1. 对比 `_分析报告.txt` 平台字段与 `__exp_main.txt` build 指纹。
2. 用 `SYS_VERSION_INFO` 二次校验。
3. 重新拉取对应版本符号。

### 结论
统一基线后再做代码级分析；冲突信息需写入 Jira。
