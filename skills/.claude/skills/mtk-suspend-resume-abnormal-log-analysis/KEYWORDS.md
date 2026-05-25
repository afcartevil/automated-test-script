# 关键字速查

## SOP官方关键字（不区分大小写）

### 上层优先关键字

| 关键字 | 适用日志 | 说明 |
|--------|----------|------|
| `power` | main_log, kernel_log | 电源管理相关，覆盖PowerManager到Kernel电源状态 |
| `PowerManagerService` | main_log | PowerManagerService打印，标识上层亮灭屏指令下发 |
| `screen` | main_log | 屏幕状态变化，含Screen acquired/released |
| `wakeup` | main_log | 唤醒相关，含Waking up原因和触发源 |

### 显示链路补充关键字

| 关键字 | 适用日志 | 说明 |
|--------|----------|------|
| `lcm` | kernel_log | LCM驱动，含lcm_resume/lcm_suspend上下电流程 |
| `panel` | kernel_log | Panel驱动，panel_enable/panel_disable执行 |
| `drm` | kernel_log | DRM框架，mtk_drm_crtc_atomic_enable/disable |
| `disp` | kernel_log | Display子系统，含错误日志标签 `[DISP][E]` |
| `dsi` | kernel_log | MIPI DSI接口，唤醒后花屏相关 |
| `hwc` | main_log | Hardware Composer，合成状态 |

## 关键日志示例与解读

### 1. 上层触发亮屏

```text
PowerManagerService: Waking up from sleep (uid=1000, reason=WAKE_REASON_POWER_BUTTON, details=android.policy:POWER)
```

**解读**：
- `Waking up from sleep` — PowerManagerService被唤醒
- `reason=WAKE_REASON_POWER_BUTTON` — 触发原因为电源键
- `uid=1000` — System进程触发
- 无此日志 → 上层未收到唤醒请求

### 2. 上层触发灭屏

```text
PowerManagerService: Going to sleep due to power button (uid 1000)...
```

**解读**：
- `Going to sleep` — PowerManagerService进入休眠流程
- `due to power button` — 触发原因为电源键
- 无此日志 → 上层未下发灭屏请求

### 3. 底层Panel亮屏流程

```text
[    xxx] [LCM] lcm_resume begin
[    xxx] [LCM] lcm_resume end
```

**解读**：
- `lcm_resume begin` — Panel上电流程开始
- `lcm_resume end` — Panel上电流程完成
- begin和end必须成对出现
- 仅有begin无end → Panel上电流程执行失败

### 4. 底层Panel灭屏流程

```text
[    xxx] [LCM] lcm_suspend begin
[    xxx] [LCM] lcm_suspend end
```

**解读**：
- `lcm_suspend begin` — Panel下电流程开始
- `lcm_suspend end` — Panel下电流程完成
- begin和end必须成对出现
- 仅有begin无end → Panel下电流程执行失败

### 5. DRM CRTC状态切换

```text
[    xxx] [DRM] mtk_drm_crtc_atomic_enable
[    xxx] [DRM] mtk_drm_crtc_atomic_disable
```

**解读**：
- `atomic_enable` — DRM CRTC使能（亮屏侧底层起始点）
- `atomic_disable` — DRM CRTC禁用（灭屏侧底层起始点）
- 上层有Waking up但无atomic_enable → DRM层未收到亮屏请求，链路断在HAL/DRM之间
