# KE 常见问题对照

| 序号 | 场景 | 日志特征 | 常见根因 | 建议动作 |
|---|---|---|---|---|
| 1 | KE Panic/Oops | `Kernel panic - not syncing` / `BUG` / `Oops` | 空指针、越界访问、非法状态机 | 优先符号映射到代码行，核对 fault address 与首个业务栈帧 |
| 2 | ATF exception | `Unhandled Exception in EL3` | EL3 侧访问错误、状态异常 | 检查 `SYS_TFA_CRASH_REPORT`，有 `SYS_TFA_BL31_RAMDUMP` 时转 MTK |
| 3 | ATF assert/panic | `PANIC in` / `assert` | ATF 主动保护触发 | 确认触发条件与前序日志，补充业务触发路径 |
| 4 | 平台版本冲突 | build 指纹与报告平台不一致 | 工具识别口径差异、提单错误 | 以同包 build 指纹为准，报告中注明冲突 |
| 5 | 符号不匹配 | 地址映射结果异常或不可复现 | vmlinux/ko 版本错误 | 重新确认版本号与符号来源后再下代码级结论 |

## 快速决策

- 出现 `SYS_TFA_BL31_RAMDUMP`：优先 MTK 路径，不硬做本地代码结论。
- 没有可用 backtrace：至少给到模块级结论，并明确缺失证据。
