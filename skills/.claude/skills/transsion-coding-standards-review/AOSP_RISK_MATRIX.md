# AOSP 修改风险矩阵

Agent 审核 AOSP 相关改动时，先定位子系统，再逐项检查。

## 通用检查（所有 AOSP 改动）

| # | 检查项 | 不合规信号 | 修改建议 |
|---|--------|------------|----------|
| G1 | 修改方式 | 直接改 `frameworks/` 资源/字符串 | 改 overlay；字符串进 `os_*.xml` / `tran_string.xml` |
| G2 | 注释包裹 | 原生行改动无 start/end | 补全 `[部门]: modify <reason> <id> by <人> <日期> start/end` |
| G3 | 升级合入 | 大块重写原生函数 | 下沉 `vendor/tran_os` 或最小行级修改 |
| G4 | 原生删除 | `git diff` 出现 delete 原生逻辑 | 禁止删除；注释掉并说明原因，或 hook/overlay |
| G5 | 魔法值 | 未定义常量数字/字符串 | 提取 `static final` / `#define` / `resources` |
| G6 | 线程 | 主线程 IO/网络/大循环 | 移到 Worker/HandlerThread；加 `@WorkerThread` |
| G7 | 空指针/越界 | 未检查 nullable/数组 index | 加 guard；分析根因而非仅 catch |
| G8 | 模块影响 | 改公共 API/Broadcast/Settings | 列出受影响模块，建议知会责任人 |

---

## 子系统检查

### Framework / SystemServer

| 检查项 | 风险 | 建议 |
|--------|------|------|
| 新增服务/Manager | 启动顺序、权限、SELinux | 放 `vendor/tran_os/.../com/transsion/`；SystemServer 注入用最小 hook |
| 改 AMS/WMS/PMS 流程 | 稳定性、CTS | 确认生命周期状态机；避免破坏 task/stack 语义 |
| 隐藏 API / `@hide` | 跨版本失效 | 反射 + SDK 版本分支 + 单测/机型验证 |
| 新增 Settings KEY | 多用户、备份恢复 | `OSSettingsExt`/`TranSettingsExt` + `defaults.xml` + `OSProviderUtils` |

### Activity / Fragment / UI

| 检查项 | 风险 | 建议 |
|--------|------|------|
| 生命周期回调加重逻辑 | 泄漏、ANR | 耗时移出主线程；`onDestroy` 释放资源 |
| 改 Theme/Style | 全局 UI 回归 | 用 `OS.*`/`Tran.*` 继承链，勿改原生 theme |
| Configuration 变化 | 旋转/折叠屏 | 检查 `onConfigurationChanged` / `recreate` 路径 |

### Broadcast / Intent

| 检查项 | 风险 | 建议 |
|--------|------|------|
| 隐式广播 | Android 8+ 限制 | 用显式广播或 `registerReceiver` 动态注册 |
| 有序广播改优先级 | 时序错乱 | 核对发送/接收顺序与权限 |
| 导出组件 | 安全 | `android:exported` 最小化；权限保护 |

### ContentProvider / Database

| 检查项 | 风险 | 建议 |
|--------|------|------|
| 改原生 Provider | 数据一致性 | 扩展而非改 URI 语义；迁移加 version |
| SQL 拼接 | 注入 | 参数化查询 |
| 跨进程 URI 权限 | 泄漏 | 检查 `grantUriPermission` |

### Telephony / Telecom / IMS

| 检查项 | 风险 | 建议 |
|--------|------|------|
| 改通话状态机 | 掉话、无音 | 对照 `Call`/`Connection` 状态流转图 |
| 双卡逻辑 | 副卡异常 | 检查 `phoneId`/`subId` 全路径 |
| 权限 | 隐私合规 | `READ_PHONE_STATE` 等最小权限 |

### Power / Battery

| 检查项 | 风险 | 建议 |
|--------|------|------|
| WakeLock 泄漏 | 功耗 | `try/finally` 释放；避免长时间 PARTIAL_WAKE_LOCK |
| Alarm 精确闹钟 | 后台限制 | 评估 `SCHEDULE_EXACT_ALARM` |
| Doze 白名单 | 政策 | 禁止私自加白名单 |

### Audio / Media

| 检查项 | 风险 | 建议 |
|--------|------|------|
| AudioFocus | 无声/杂音 | 检查 gain/loss 回调配对 |
| 改 AudioPolicy | 路由错误 | 对照原生 `AudioService` 策略 |

### PackageManager / Permission

| 检查项 | 风险 | 建议 |
|--------|------|------|
| 新 APK 权限 | 安装/运行失败 | `system/etc/permissions/*-tran.xml` |
| 签名/特权 app | 安全 | `privapp-permissions-tran.xml` 同步 |

### Init / Native (C/C++)

| 检查项 | 风险 | 建议 |
|--------|------|------|
| init.rc 整文件覆盖 | 启动失败 | 仅 `init.project.rc` 差异化 |
| 驱动 probe 顺序 | 硬件不可用 | 对照 DTS/模块依赖 |
| 内核指针/中断 | 崩溃 | 判空、释放、竞态检查 |
| 动态 debug log | 量产噪声 | `dev_dbg`/`pr_debug`；量产关闭 error 级正常路径 log |

### Overlay / RRO

| 检查项 | 风险 | 建议 |
|--------|------|------|
| overlay 优先级 | 资源未生效 | 确认 `product`/`vendor` overlay 顺序 |
| 改 bool/integer 默认值 | 行为突变 | 在 `defaults.xml` 统一管理 |

### SELinux

| 检查项 | 风险 | 建议 |
|--------|------|------|
| `.te` 注释位置 | 编译失败 | 仅权限行前 `#` 注释；文件末无空行/注释 |
| 宽权限 | 安全审计 | 最小权限原则 |

---

## 修改方式 → 推荐路径速查

| 需求 | ❌ 避免 | ✅ 推荐 |
|------|---------|---------|
| 改字符串 | 编辑 `frameworks/.../strings.xml` | overlay + `os_strings.xml` / `tran_string.xml` |
| 改颜色/dimen | 直接改 base `values/` | `vendor/tran_os/overlay` 或项目 overlay |
| 新 Framework API | 改 `com.android.server.*` 大类 | `vendor/tran_os/.../com/transsion/feature` + 反射 |
| 新系统属性 | 散落硬编码 | `ro.*_support` / `ro.vendor.*_support` + 文档 |
| 开机脚本 | copy `init.rc` | `init.project.rc` |
| 新 feature | 无宏硬编码 | `TRAN_*_SUPPORT` in `ProjectConfig.mk` |
| 改内核驱动 | 改公共头文件语义 | 独立 `tran_` 符号 + 分层 driver 结构体 |

---

## 风险等级定义

| 等级 | 条件 | 审核结论 |
|------|------|----------|
| **高** | 可能崩溃/安全/合入失败/认证影响/隐私泄露 | 🔴 必须修改 |
| **中** | 特定机型或版本失效；性能/功耗退化 | 🟡 建议修改 |
| **低** | 风格、可读性、非关键 log | 🟢 可选 |
