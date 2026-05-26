---
name: mtk-suspend-resume-abnormal-log-analysis
description: "MTK显示-亮灭屏: 分析亮灭屏异常、休眠唤醒失败、按键无响应问题，覆盖PowerManager→DRM→Panel链路 | PowerManagerService/Waking_up/Going_to_sleep/lcm_resume/lcm_suspend/mtk_drm_crtc/screen/wakeup/AOD/亮屏无响应/灭屏未真灭/唤醒黑屏 | 当用户报告MTK设备按电源键不亮/不灭、唤醒失败、灭屏后背光仍亮时使用。注意: 亮灭屏可能伴随背光问题→mtk-backlight-abnormal-log-analysis，唤醒花屏可能关联撕裂→mtk-screen-tearing-abnormal-log-analysis"
funcType: "AI故障分析"
category: "驱动"
---

# MTK 平台 亮灭屏/休眠唤醒 异常 分析

## 适用范围

- **问题类型**：MTK平台显示领域亮灭屏、休眠唤醒异常
- **适用场景**：
  - 按电源键亮屏无响应、亮屏延迟
  - 按电源键灭屏无响应、灭屏后屏幕未真正熄灭
  - 休眠后无法唤醒、唤醒后花屏/黑屏
  - 亮屏后无背光、灭屏后背光仍亮
  - Panel enable/disable 流程异常导致的显示问题
- **适用芯片平台**：MTK

## 不适用场景

- 非MTK芯片平台的显示问题
- 与亮灭屏链路无关的纯应用层逻辑异常
- 无法提供 main/android log 与 kernel log 的场景
- 仅术语解释类问答、无需完整SOP排查流程的场景
- 非显示领域的 PowerManager/电源管理问题（如CPU休眠唤醒）

## 前置条件

分析前需确认以下输入信息可用：

| 输入项 | 必需性 | 用途 |
|--------|--------|------|
| 问题设备的MTK芯片平台型号 | 必需 | 确认芯片平台匹配 |
| 问题复现步骤、发生概率 | 必需 | 确认问题复现条件 |
| 触发方式 | 必需 | 电源键/抬腕/AOD/超时灭屏等 |
| 预期行为与实际异常描述 | 必需 | 明确异常现象 |
| `main_log` / Android log | 必需 | 分析上层PowerManager状态变化 |
| `kernel_log` | 必需 | 分析底层Panel enable/disable执行情况 |
| 近期修改的代码文件、可疑提交记录 | 可选 | 辅助定位 |

## 问题有效性确认

开始分析前，先确认：
1. Linux内核日志可正常打印
2. Android main log可正常获取
3. 芯片平台为MTK
4. 问题属于显示领域亮灭屏、休眠唤醒异常

## 分析工作流

按以下步骤依次执行，不得跳步、不得颠倒顺序。详细操作参阅 [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)。

### 步骤1：获取日志
- **目标**：获取与亮灭屏异常直接相关的日志文件
- **操作**：
  - 如果给定的是JIRA号、文件夹等非直接Log文件，先获取日志文件
  - 排除与显示领域无关的日志文件，仅保留Kernel日志、Android日志等有效文件
  - 若存在mobilelog文件夹，需提取其中的kernel_log和main_log
- **判断**：
  - 未获取到kernel_log或main_log -> 停止分析，向用户索要缺失日志
  - 已获取到必需日志 -> 进入步骤2

### 步骤2：日志关键字过滤
- **目标**：按SOP关键字缩小分析范围
- **操作**：
  - 优先关键字（不区分大小写）：`power`、`PowerManagerService`、`screen`、`wakeup`
  - 显示链路补充关键字（不区分大小写）：`lcm`、`panel`、`drm`、`disp`、`dsi`、`hwc`
  - 按main_log与kernel_log分别整理过滤结果 -> 进入步骤3

### 步骤3：问题阶段判定
- **目标**：先判定问题方向，再判定发生阶段
- **第一层判定**：问题属于"亮屏异常"还是"灭屏异常"
- **第二层判定**：问题发生在"上层下发指令阶段"还是"底层执行阶段"

### 步骤4：分层日志分析

#### 子步骤4.1 上层（Framework/PowerManager）分析

1. **检查是否触发按键事件**
   - 搜索 `PowerManagerService.*onUserActivity|Input.*KEY_POWER`
   - 未打印 → 按键事件未送达PowerManagerService（非显示问题，需转输入链路排查）

2. **检查PowerManager状态变化**
   - 亮屏：搜索 `PowerManagerService.*Waking up|Display Power.*state=ON`
   - 灭屏：搜索 `PowerManagerService.*Going to sleep|Display Power.*state=OFF`
   - 未打印对应状态 → 上层未下发亮/灭屏请求

3. **检查SurfaceFlinger/DisplayManager通知**
   - 搜索 `SurfaceFlinger.*Screen acquired|Screen released`
   - 搜索 `DisplayPowerController.*Unblocked screen on|Blocked screen on`

#### 子步骤4.2 底层（Kernel/DRM/Panel）分析

1. **检查DRM CRTC enable/disable**
   - 亮屏：搜索 `mtk_drm_crtc_atomic_enable`
   - 灭屏：搜索 `mtk_drm_crtc_atomic_disable`
   - 未打印 → DRM层未接收到上层的亮/灭屏请求

2. **检查Panel enable/disable流程**
   - 亮屏：搜索 `[LCM] lcm_resume|panel_enable` — begin和end必须成对出现
   - 灭屏：搜索 `[LCM] lcm_suspend|panel_disable` — begin和end必须成对出现
   - 仅有begin无end或流程中断 → Panel上/下电流程执行失败

3. **检查背光配合情况**（结合 `mtk-backlight-abnormal-log-analysis`）
   - 亮屏后无背光：检查 `lcm_setbacklight_cmdq` 是否被调用、level是否为0
   - 灭屏后背光仍亮：检查是否缺失 `lcm_setbacklight_cmdq level = 0`

#### 子步骤4.3 特殊问题分析

1. **唤醒后花屏**：检查是否存在 `mtk-dsi` 相关错误、TE信号异常
2. **AOD场景异常**：检查AOD相关日志 `aod`、`doze`
3. **灭屏未真灭**：对比灭屏指令下发与Panel disable执行是否完整

## 关键字速查

完整的关键字列表和日志示例，参阅 [KEYWORDS.md](KEYWORDS.md)。

SOP官方关键字（不区分大小写）：`power`、`PowerManagerService`、`screen`、`wakeup`、`lcm`、`panel`、`drm`

### 关键日志示例与解读

#### 上层触发亮屏
```text
PowerManagerService: Waking up from sleep (uid=1000, reason=WAKE_REASON_POWER_BUTTON, details=android.policy:POWER)
```
**解读**：PowerManagerService收到唤醒请求，`reason`标识触发源（电源键/抬腕等）。

#### 上层触发灭屏
```text
PowerManagerService: Going to sleep due to power button (uid 1000)...
```
**解读**：PowerManagerService收到休眠请求。

#### 底层Panel亮屏流程
```text
[    xxx] [LCM] lcm_resume begin
[    xxx] [LCM] lcm_resume end
```
**解读**：Panel上电流程，begin和end必须成对出现。

#### 底层Panel灭屏流程
```text
[    xxx] [LCM] lcm_suspend begin
[    xxx] [LCM] lcm_suspend end
```
**解读**：Panel下电流程，begin和end必须成对出现。

#### DRM CRTC状态切换
```text
[    xxx] [DRM] mtk_drm_crtc_atomic_enable
[    xxx] [DRM] mtk_drm_crtc_atomic_disable
```
**解读**：DRM层的CRTC使能/禁用，驱动Panel上/下电的实际执行点。

## 输出格式

按以下模板输出分析结论：

```markdown
# MTK 亮灭屏/休眠唤醒异常日志分析报告

## 基本信息
- **分析时间**：{当前时间}
- **日志来源**：{用户提供的日志文件列表}
- **问题描述**：{用户提供的问题描述}
- **芯片平台**：{MTK平台型号}
- **触发方式**：{电源键/抬腕/AOD/超时灭屏}

## 问题有效性确认
- 是否符合SOP适用范围：{是/否}
- 判定依据：{简述}

## 现象与类型总结
- **异常现象**：{描述}
- **问题类型**：{亮屏异常/灭屏异常/唤醒异常}
- **问题阶段**：{上层指令阶段/底层执行阶段/上下层链路断连}

## 分析过程
### 步骤1：获取日志
- 日志来源：{JIRA / 目录 / 日志文件来源}
- 提取结果：{获得的日志文件列表}
- 判断结论：{是否满足继续分析条件}

### 步骤2：日志关键字过滤
- 优先关键字：power, PowerManagerService, screen, wakeup
- 补充关键字：lcm, panel, drm, disp, dsi, hwc
- main_log过滤结果：{摘要}
- kernel_log过滤结果：{摘要}

### 步骤3：问题阶段判定
- 异常方向：{亮屏异常/灭屏异常}
- 问题阶段：{上层指令/底层执行/链路断连}

### 步骤4：分层日志分析
#### 上层分析
{按键事件/PowerManager状态/SurfaceFlinger通知检查结果}

#### 底层分析
{DRM CRTC/Panel enable-disable/背光配合检查结果}

#### 特殊问题排查
{AOD/唤醒花屏/灭屏未真灭相关检查结果}

## 关键日志证据
{引用与异常强相关的原始日志片段，严格对应SOP日志解读规则}

## 根因候选排序
按可能性从高到低排列：
1. {根因1} — 证据：{对应日志行}
2. {根因2} — 证据：{对应日志行}

## 下一步调试动作
{最小可验证、符合SOP规范的排查步骤}

## 配置/补丁修改方向
{仅在有明确日志证据时输出，无证据不输出}
```

## 约束

1. 所有分析内容100%基于提供的SOP，不得新增SOP未定义的关键字、根因、分析流程
2. 所有结论必须有对应的原始日志证据支撑，不得编造无依据的猜测、推断
3. 仅处理MTK平台的亮灭屏、休眠唤醒异常问题，不得超出适用范围
4. 日志解读必须严格遵循SOP规则，不得自行修改、扩展日志含义
5. 缺少必须日志文件时，必须先向用户索要，不得无日志强行输出结论
6. 不假装看过未提供的日志；没有kernel_log和main_log时，不直接对亮灭屏链路下结论
7. 按键事件未送达PowerManagerService时，应明确指出非显示问题，建议转输入链路排查

## 参考信息

- 关键字与日志示例：参阅 [KEYWORDS.md](KEYWORDS.md)
- 常见问题与根因对照：参阅 [COMMON_ISSUES.md](COMMON_ISSUES.md)
- 典型案例参考：参阅 [CASES.md](CASES.md)
- 详细分析步骤：参阅 [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)
