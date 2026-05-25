---
name: mtk-screen-tearing-abnormal-log-analysis
description: "MTK显示-花屏撕裂: 分析花屏、撕裂、残影拖影、局部异常问题，覆盖SurfaceFlinger→DRM/DSI链路 | tearing/vsync/te/frame_done/cmdq/dsi_underrun/CMDQ_timeout/wait_TE_timeout/花屏/雪花/撕裂/残影 | 当用户报告MTK设备运行时花屏、画面撕裂、残影、局部花屏时使用。注意: 开机阶段花屏走mtk-panel-load-abnormal-log-analysis，亮灭屏异常走mtk-suspend-resume-abnormal-log-analysis"
---

# MTK 平台 花屏/撕裂/画面异常 分析

## 适用范围

- **问题类型**：MTK平台显示领域花屏、画面撕裂、画面残影、局部显示异常
- **适用场景**：
  - 全屏花屏、雪花屏、彩条
  - 画面撕裂（上下半屏不同步）
  - 残影、拖影、上一帧画面残留
  - 局部区域花屏、块状错位
  - 特定场景（滑动/视频/游戏）出现的画面异常
- **适用芯片平台**：MTK

## 不适用场景

- 非MTK芯片平台的显示问题
- 纯应用绘制错误（应用自身渲染Bug）导致的画面异常
- 开机阶段花屏（应使用 `mtk-panel-load-abnormal-log-analysis`）
- 无法提供 main/android log 与 kernel log 的场景
- 仅术语解释类问答、无需完整SOP排查流程的场景

## 前置条件

分析前需确认以下输入信息可用：

| 输入项 | 必需性 | 用途 |
|--------|--------|------|
| 问题设备的MTK芯片平台型号 | 必需 | 确认芯片平台匹配 |
| 问题复现步骤、发生概率、复现场景 | 必需 | 确认问题复现条件 |
| 异常区域与持续时间 | 必需 | 判定问题类型 |
| 异常画面截图或录屏 | 建议 | 辅助确认异常形态 |
| `main_log` / Android log | 必需 | 分析合成链路状态 |
| `kernel_log` | 必需 | 分析DRM/DSI/TE信号状态 |
| 近期修改的代码文件、可疑提交记录 | 可选 | 辅助定位 |

## 问题有效性确认

开始分析前，先确认：
1. Linux内核日志可正常打印
2. Android main log可正常获取
3. 芯片平台为MTK
4. 问题属于显示领域花屏、画面撕裂、画面残影、局部显示异常

## 分析工作流

按以下步骤依次执行，不得跳步、不得颠倒顺序。详细操作参阅 [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)。

### 步骤1：获取日志
- **目标**：获取与画面异常直接相关的日志文件
- **操作**：
  - 如果给定的是JIRA号、文件夹等非直接Log文件，先获取日志文件
  - 排除与显示领域无关的日志文件
  - 若存在mobilelog文件夹，需提取其中的kernel_log和main_log
- **判断**：
  - 未获取到kernel_log或main_log -> 停止分析，向用户索要缺失日志
  - 已获取到必需日志 -> 进入步骤2

### 步骤2：日志关键字过滤
- **目标**：按SOP关键字缩小分析范围
- **操作**：
  - 优先关键字（不区分大小写）：`tearing`、`vsync`、`te`、`frame_done`、`cmdq`
  - 显示链路补充关键字（不区分大小写）：`drm`、`dsi`、`disp`、`lcm`、`hwc`、`surfaceflinger`
  - 按main_log与kernel_log分别整理过滤结果
- **判断**：
  - 过滤结果为空 -> 扩大关键字范围或确认日志是否正确
  - 过滤结果非空 -> 进入步骤3

### 步骤3：问题类型判定
- **目标**：根据现象判定问题类型，不同类行走不同分析路径
- **类型分类**：
  - **全屏花屏**：全屏雪花、彩条、马赛克 → 走子步骤4.1
  - **撕裂**：上下半屏不同步 → 走子步骤4.2
  - **残影/拖影**：上一帧残留、画面拖尾 → 走子步骤4.3
  - **局部异常**：局部区域花屏、块状错位 → 走子步骤4.4

### 步骤4：分类型日志分析

#### 子步骤4.1 全屏花屏分析
1. 检查DSI链路错误：搜索 `mtk-dsi.*underrun|DSI error|LCD-CV error`
   - 打印错误 → 判定为DSI信号异常导致花屏
2. 检查CMDQ执行异常：搜索 `cmdq.*timeout|cmdq.*error`
   - 打印超时 → 判定为CMDQ任务执行异常，画面未正确刷新
3. 检查Panel init code下发情况：结合 `mtk-panel-load-abnormal-log-analysis` 排查屏初始化问题

#### 子步骤4.2 撕裂分析
1. 检查TE信号：搜索 `wait TE timeout|TE`
   - 无TE信号或TE不稳定 → 判定为TE同步异常导致撕裂
2. 检查VSync同步：搜索 `SurfaceFlinger.*VSync`
   - 确认SurfaceFlinger是否按VSync周期正常提交

#### 子步骤4.3 残影/拖影分析
1. 检查PQ/Dimming模块状态：搜索 `pq|ccorr|gamma|dither|aal`
   - PQ模块状态切换异常可能导致残影
2. 检查frame_done完成情况：搜索 `frame_done`
   - `frame_done timeout` → 一帧未按时完成上屏

#### 子步骤4.4 局部异常分析
1. 检查Overlay/HWC图层合成：搜索 `SurfaceFlinger|HWC`
   - HWC图层配置、层数是否异常
   - SurfaceFlinger中layer的region/crop是否异常
2. 检查ROI（Partial Update）配置：MTK平台支持ROI更新，ROI计算错误会导致局部异常

## 关键字速查

完整的关键字列表和日志示例，参阅 [KEYWORDS.md](KEYWORDS.md)。

SOP官方关键字（不区分大小写）：
- 优先：`tearing`、`vsync`、`te`、`frame_done`、`cmdq`
- 补充：`drm`、`dsi`、`disp`、`lcm`、`hwc`、`surfaceflinger`

### 关键日志示例与解读

#### DSI 链路错误
```text
[    xxx] mtk-dsi 14014000.dsi: underrun
[    xxx] [DISP][E] DSI error irq status = 0xXXXX
```
**解读**：DSI信号异常、带宽不足或时序错误，会导致花屏/雪花。

#### CMDQ 超时
```text
[    xxx] [CMDQ][ERR] task timeout, thread=X
```
**解读**：CMDQ任务未按时执行，画面未正确刷新。

#### TE 信号异常
```text
[    xxx] [DISP][E] wait TE timeout
```
**解读**：屏幕TE信号缺失或不稳定，容易引起画面撕裂。

#### Frame done 异常
```text
[    xxx] [DISP][E] frame_done timeout
```
**解读**：一帧未在预期时间内完成上屏，会导致卡顿/残影。

## 输出格式

按以下模板输出分析结论：

```markdown
# MTK 花屏/撕裂/画面异常日志分析报告

## 基本信息
- **分析时间**：{当前时间}
- **日志来源**：{用户提供的日志文件列表}
- **问题描述**：{用户提供的问题描述}
- **芯片平台**：{MTK平台型号}

## 问题有效性确认
- 是否符合SOP适用范围：{是/否}
- 判定依据：{简述}

## 现象与类型总结
- **异常现象**：{描述}
- **问题类型**：{全屏花屏/撕裂/残影拖影/局部异常}

## 分析过程
### 步骤1：获取日志
- 日志来源：{JIRA / 目录 / 日志文件来源}
- 提取结果：{获得的日志文件列表}
- 判断结论：{是否满足继续分析条件}

### 步骤2：日志关键字过滤
- 优先关键字：tearing, vsync, te, frame_done, cmdq
- 补充关键字：drm, dsi, disp, lcm, hwc, surfaceflinger
- main_log过滤结果：{摘要}
- kernel_log过滤结果：{摘要}

### 步骤3：问题类型判定
- 判定结果：{全屏花屏/撕裂/残影拖影/局部异常}

### 步骤4：分类型日志分析
{按对应子步骤4.1~4.4逐项检查结果}

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
3. 仅处理MTK平台的花屏、撕裂、残影、局部异常问题，不得超出适用范围
4. 日志解读必须严格遵循SOP规则，不得自行修改、扩展日志含义
5. 缺少必须日志文件时，必须先向用户索要，不得无日志强行输出结论
6. 不假装看过未提供的日志；没有kernel_log和main_log时，不直接对显示链路下结论
7. 开机阶段花屏应使用 `mtk-panel-load-abnormal-log-analysis`，不得与本skill混用

## 参考信息

- 关键字与日志示例：参阅 [KEYWORDS.md](KEYWORDS.md)
- 常见问题与根因对照：参阅 [COMMON_ISSUES.md](COMMON_ISSUES.md)
- 典型案例参考：参阅 [CASES.md](CASES.md)
- 详细分析步骤：参阅 [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)
