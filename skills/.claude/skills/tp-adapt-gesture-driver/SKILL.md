---
funcType: "AI自动化适配"
category: "驱动"
---
﻿---
name: tp-adapt-gesture-driver
description: Guides Transsion TP gesture stack adaptation and kernel-side debugging using transsion core (tran_ts_controller, vendor_gesture_map, state machine), transsion_gesture proc/sysfs nodes, and vendor suspend/resume hooks. Use when bring-up or migrating Goodix/Focaltech/Chipone/etc. under drivers/input/touchscreen/transsion, or when debugging gesture ID mapping, gesture_flag, doze/gesture suspend, KEY_F26/KEY_FINGER reporting, or proc node writes (gesture_function, gesture_flag).
---

# Transsion TP 手势驱动适配与内核调试

面向 **传音 Transsion touchscreen 中间层**（`drivers/input/touchscreen/transsion`）下的灭屏手势：**新机适配、IC 迁移、手势不上报、手势模式进不去、映射错误**。日志侧结论可联动 `mtk-tp-gesture-log-analysis`；通用 TP 分层与证据要求可联动 `tp-driver-debug-expert`。

## 代码分层（必读心智模型）

1. **Core**：`transsion/core/transsion_core.c` — `state_change_machine()` 根据 `gesture_state_get` 结果在 `TRAN_ACTIVE_MODE` / `TRAN_SUSPEND_MODE` / `TRAN_GESTURE_SUSPEND_MODE` 间切换；suspend/resume 时调用各 vendor 的 `tran_ts_suspend` / `tran_ts_resume`。
2. **Gesture 中间层**：`transsion/core/transsion_gesture.c`、`core/include/transsion_gesture.h` — 维护手势开关表、`GestureIdTranslate` → `GestureHandle`、proc/sysfs 节点、向 `input_dev` 上报键值。
3. **Vendor 适配**：`transsion/vendor/<vendor>/...` — 实现 `struct tran_controller_ops`，填充 `struct tran_ts_controller`（含 `gesture_map`、`gesture_flag`），在 suspend 分支里按 core 模式打开/关闭 IC 手势（参考 Goodix：`TRAN_GESTURE_SUSPEND_MODE` 时 `tran_vendor_gesture_enable(1)`，纯休眠则 disable）。

### 关键数据结构（适配时对齐）

- `struct vendor_gesture_map`：`vendor_code` → `tran_code`，表以 `{0,0}` 结尾；`GestureIdTranslate` 遍历映射，找不到则不上报。
- `struct tran_core_ops`：`gesture_state_get`（是否允许进入手势休眠链路）、`gesture_id_report`（一般由 `gesture_init` 挂成 `GestureIdTranslate`）、可选 `gesture_switch_status`。
- `g_tran_ts.function_support` 含 `TRAN_GESTURE_FUNCTION` 时，`GESTURE_IS_SUPPORT` 为真（与节点/功能裁剪相关，适配时确认 DTS/Kconfig/平台初始化）。

传音侧手势字符与类型定义见 `core/include/transsion_gesture.h`（如 `GESTURE_DC`、`GESTURE_w` 等与上层约定）。

## 新版 IC / 新项目适配清单

按顺序自检，避免遗漏：

1. **注册 controller**：`register_ts_controller()`，`controller_init_state`、`input_dev`、`*ops`、`*ext_ops` 赋值完整。
2. **`gesture_map`**：将 **固件实际上报的 gesture id** 逐项映射到传音 `tran_code`；新增手势必须同时满足：IC 上报值正确、映射表有项、`gesture_maps[]`（`transsion_gesture.c`）中对应类别已 enable。
3. **`gesture_flag`**：默认通常为 true；若灭屏被强制切深度休眠，核对 `gesture_flag` / `gesture_write_flag` 与 `/proc` 写入口行为。
4. **`tran_vendor_gesture_enable`**：必须能在 suspend 路径把 IC 手势开关打到与 core 模式一致；对照参考机型 vendor 实现（Goodix：`goodix_controller.controller_state == TRAN_GESTURE_SUSPEND_MODE` 时 enable）。
5. **中断里手势上报**：解析 gesture 包后调用 `tpd_ops->gesture_id_report(vendor_gesture_id, ctr)`（名称以实际代码为准，等价于走到 `GestureIdTranslate`）。
6. **`gesture_state_get`（Doze 聚合）**：`SetDozeStatus` 依赖各子类 enable（双击/音乐/字母总开关/特殊手势）；上层写的 proc 格式错误会导致开关无效（见下节）。
7. **双 TP**：区分 `TRAN_MAIN_CONTROLLER` / `TRAN_SUB_CONTROLLER`，主副屏各自 `gesture_flag` 与 `sub_gesture_mode_write` / `gesture_mode_write` 逻辑不一致时易出现「一面屏手势失效」。

## Proc / sysfs 调试（内核侧）

创建逻辑在 `transsion_gesture.c` 的 `tran_gesture_proc_node[]` / `gesture_init()`。

| 节点（常见） | 用途 |
|-------------|------|
| `/proc/main_gesture_function`、`/proc/gesture_function` | 写 **3 字节**命令：`cmd[0]cmd[1]` 选手势，`cmd[2]`：`1`=开，`2`=关（见 `cmd_get_enable`） |
| `/proc/main_gesture_state`、`/proc/gesture_state` | 读各 `xx : 0/1` 开关状态 |
| `/proc/main_gesture_flag`、`/proc/gesture_flag` | 主/副 **手势模式恢复与深度休眠切换**（写入字符 `'0'`/`'1'`/`'3'` 等，代码路径含 resume+suspend 重建手势） |
| `/proc/touch_gesture` | **手势注入测试**：写入如 `cc0`、`aa0`、`w00` 等，内部设 `g_gtp_gesture` 后调 `GestureHandle` |

Sysfs：`gesture_test` 属性（device 上）用于简单开关双击类测试（见 `store_gesture_test`）。

调试时内核日志关键字：`[tran_touch`、`[tran_touch-INFO`、`[tran_touch-ERROR`、`<<-CTP-INFO->>`、`[GESTURE]`。

## 上报路径（判断是否「驱动已上报」）

`GestureHandle()` 典型行为：

- 普通允许的手势：写入 `gesture_data`，并对 `input_dev` **脉冲上报 `KEY_F26`**（按下再抬起）。
- 单击类（`GESTURE_OC`）：`KEY_F20` 脉冲。
- FOD down/up：`KEY_FINGER` 按下/抬起，且受 `g_tran_ts.fp_status.g_fod_flag` 互斥保护。

若内核已打印 `[GESTURE]gesture report KEY_F26 done` 但上层无响应，优先转 **Framework / Keyguard** 链路（`mtk-tp-gesture-log-analysis`）。

## 常见故障与定位方向

| 现象 | 优先怀疑 |
|------|-----------|
| 灭屏完全无手势 | `gesture_state_get` 返回 0；上层未写开 `gesture_function`；`gesture_flag` 被置 false；IC 侧 enter gesture fail |
| 部分手势无效 | `vendor_gesture_map` 缺项或 vendor_code 与 FW 不一致；`code_is_enable` 对应类型未开 |
| 仅双击无效 | `gesturedouble_enabled` / `cc` 项 enable；口袋模式/上层拦截（需 main_log） |
| 字母手势无效 | `al` / `gesturechar_enabled` 与单字母 `x0` 项；映射表是否含该字母 |
| 音乐手势无效 | `aa/bb/ab/ba` 四类 enable |
| resume 后手势丢失 | `state_change_machine` 与 vendor resume 顺序；`gesture_write_flag` 状态 |
| 副屏异常 | 使用 `gesture_flag` / `sub_gesture_*` 分支而非 main |

## 与其它 Skill 的分工

- **本 Skill**：内核 `transsion` 树内适配、映射表、suspend/gesture 模式、proc 自测、KEY 上报确认。
- **`tp-log-gesture`**：JIRA/日志侧灭屏手势失效分析。

## 输出模板（适配评审 / 问题结论）

```markdown
## Transsion TP 手势驱动结论

### 范围
- IC / 分支：
- 单双 TP：

### 内核事实
- controller 注册与 `gesture_map`：[
- suspend 时 core 模式：`TRAN_GESTURE_SUSPEND_MODE` 是否成立
- IC 手势开关：`tran_vendor_gesture_enable` 行为
- 实测 proc：`gesture_function` / `gesture_flag` 写入与读出

### 根因判断
- 驱动层 / 映射层 / IC FW / 上层（择一或组合）

### 建议修改
- 文件与改动要点（映射表 / suspend 分支 / 上报调用点）

### 待补日志（若仍不明确）
- `kernel_log` 中含 `[GESTURE]`、`tran_touch` 片段；必要时 `main_log` Keyguard
```

## 参考代码锚点（便于打开对照）

- Core 状态机：`transsion/core/transsion_core.c` 中 `state_change_machine`、`ts_state_machine[]`
- Gesture 映射与上报：`transsion/core/transsion_gesture.c` 中 `GestureIdTranslate`、`GestureHandle`、`gesture_init`
- Vendor 表示例：`transsion/vendor/goodix/gt9916_common/goodix_ts_core.c` 中 `goodix_gestures_maps`、`suspend()` 内 `goodix_gesture_enable`

---

保持改动范围：**仅在手势链路相关的 vendor 文件与映射**；勿顺带大范围格式化无关驱动代码。
