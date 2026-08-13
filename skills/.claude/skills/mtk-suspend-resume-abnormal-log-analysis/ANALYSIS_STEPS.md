# 详细分析步骤

## 步骤1：获取日志

### 操作细则

1. 如果给定的是JIRA号：
   - 从JIRA的`Log and Screenshot address`获取mobilelog或用户提供的log地址
   - 下载并解压日志包

2. 如果给定的是文件夹：
   - 遍历文件夹，识别日志文件类型
   - 排除与显示领域无关的日志文件（如modem_log、radio_log等）

3. 若存在mobilelog文件夹：
   - 提取`APLog_*/main_log_*`作为main_log
   - 提取`APLog_*/kernel_log_*`作为kernel_log

### 判断标准

- **无kernel_log且无main_log**：停止分析，提示用户需提供至少一份日志
- **仅有main_log无kernel_log**：可分析上层PowerManager状态，但底层执行分析受限
- **仅有kernel_log无main_log**：可分析底层Panel执行，但上层指令分析受限
- **两者齐全**：进入步骤2

## 步骤2：日志关键字过滤

### 操作细则

1. 优先关键字过滤（不区分大小写）：
   ```
   power|PowerManagerService|screen|wakeup
   ```

2. 显示链路补充关键字过滤（不区分大小写）：
   ```
   lcm|panel|drm|disp|dsi|hwc
   ```

3. 分别整理main_log和kernel_log的过滤结果，按时间排序

### 判断标准

- **过滤结果完全为空**：扩大关键字范围或确认日志文件是否正确
- **过滤结果非空**：提取关键行，进入步骤3

## 步骤3：问题阶段判定

### 第一层判定：亮屏异常 vs 灭屏异常

根据用户描述的现象判定：
- 按键后屏幕不亮、亮屏延迟 → 亮屏异常
- 按键后屏幕不灭、灭屏后仍有显示 → 灭屏异常
- 休眠后无法唤醒 → 亮屏异常（唤醒）

### 第二层判定：上层指令 vs 底层执行

检查以下关键日志的有无：

| 分层 | 亮屏关键日志 | 灭屏关键日志 |
|------|-------------|-------------|
| 上层指令 | `PowerManagerService: Waking up` | `PowerManagerService: Going to sleep` |
| 底层执行(DRM) | `mtk_drm_crtc_atomic_enable` | `mtk_drm_crtc_atomic_disable` |
| 底层执行(Panel) | `[LCM] lcm_resume` | `[LCM] lcm_suspend` |

判定规则：
- 有上层指令、无底层执行 → 链路断在上层到DRM之间
- 有DRM执行、无Panel执行 → 链路断在DRM到Panel之间
- 有上层指令、有底层执行、但表现异常 → Panel执行流程不完整或背光配合异常
- 无上层指令 → 非显示问题，按键事件未送达

## 步骤4：分层日志分析

### 4.1 上层（Framework/PowerManager）分析

#### 检查1：按键事件
- **搜索关键字**：`PowerManagerService.*onUserActivity|Input.*KEY_POWER`
- **搜索目标**：确认电源键事件是否被系统接收
- **判断**：
  - 未打印 → 按键事件未送达PowerManagerService，非显示问题，建议转输入链路排查
  - 已打印 → 按键事件已送达

#### 检查2：PowerManager状态变化
- **搜索关键字**：
  - 亮屏：`PowerManagerService.*Waking up`
  - 灭屏：`PowerManagerService.*Going to sleep`
- **搜索目标**：确认上层是否下发了亮/灭屏请求
- **判断**：
  - 未打印 → 上层未下发亮/灭屏请求（主结论）
  - 已打印 → 记录触发原因和时间，继续检查3

#### 检查3：DisplayManager/SurfaceFlinger通知
- **搜索关键字**：
  - `SurfaceFlinger.*Screen acquired|Screen released`
  - `Display Power.*state=ON|state=OFF`
  - `DisplayPowerController.*Unblocked screen on|Blocked screen on`
- **搜索目标**：确认DisplayManager状态切换是否正常
- **判断**：
  - 状态正常切换 → 上层链路完整，问题在下层
  - 状态未切换 → DisplayManager状态机异常

### 4.2 底层（Kernel/DRM/Panel）分析

#### 检查1：DRM CRTC enable/disable
- **搜索关键字**：`mtk_drm_crtc_atomic_enable|mtk_drm_crtc_atomic_disable`
- **搜索目标**：确认DRM层是否收到亮/灭屏请求
- **判断**：
  - 上层有指令、DRM无打印 → 链路断在HAL/DRM之间
  - 有打印 → 继续检查2

#### 检查2：Panel enable/disable流程
- **搜索关键字**：
  - 亮屏：`lcm_resume|panel_enable`
  - 灭屏：`lcm_suspend|panel_disable`
- **搜索目标**：确认begin和end是否成对出现
- **判断**：
  - begin和end成对出现 → Panel上下电流程正常
  - 仅有begin无end → Panel上下电流程执行失败（主结论）
  - 两者都无 → Panel驱动未响应，需检查Panel驱动加载

#### 检查3：背光配合情况
- **搜索关键字**：`lcm_setbacklight_cmdq`
- **搜索目标**：确认背光是否随亮灭屏正确切换
- **判断**：
  - 亮屏后无`lcm_setbacklight_cmdq`或level=0 → 背光未随亮屏下发（结合backlight SOP）
  - 灭屏后有`lcm_suspend`但无`level = 0` → 灭屏未关背光

### 4.3 特殊问题分析

#### 唤醒后花屏
- **搜索关键字**：`mtk-dsi.*error|mtk-dsi.*underrun|wait TE timeout`
- **判断**：
  - 有DSI/TE错误 → 结合`mtk-screen-tearing-abnormal-log-analysis`分析

#### AOD场景异常
- **搜索关键字**：`aod|doze|AOD`
- **判断**：AOD模式下的状态切换是否正常

#### 灭屏未真灭
- **对比检查**：灭屏指令（Going to sleep）→ DRM disable → lcm_suspend → 背光关
- **判断**：链路上哪一环缺失
