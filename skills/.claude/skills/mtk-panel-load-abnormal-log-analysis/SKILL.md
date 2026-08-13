---
name: mtk-panel-load-abnormal-log-analysis
description: "MTK显示-Panel加载: 分析开机黑屏、卡Logo、Panel上电/加载失败问题，覆盖LK+Kernel双阶段 | lcm/panel/drm/dsi/islcmfound/lcm_probe/Waiting for bridge/Cannot find disp pinctrl/开机黑屏/卡logo | 当用户报告MTK设备开机黑屏、Boot Logo不显示、进Kernel黑屏/花屏时使用。注意: 进系统后的花屏撕裂走mtk-screen-tearing-abnormal-log-analysis，背光问题走mtk-backlight-abnormal-log-analysis"
funcType: "AI故障分析"
category: "驱动"
---

# MTK 平台 Panel 加载失败/黑屏/卡Logo 分析

## 适用范围

- **问题类型**：MTK平台开机阶段Panel加载失败
- **适用场景**：
  - 开机黑屏，无任何画面输出
  - Boot Logo不显示、Boot Logo显示后卡死
  - Panel上电失败、初始化失败、唤醒异常
  - LK阶段屏幕识别失败、Kernel阶段Panel probe失败
  - 开机阶段显示GPIO初始化失败、DRM模块加载异常
- **适用芯片平台**：MTK

## 不适用场景

- 非MTK芯片平台的显示问题
- Boot阶段/内核无任何日志打印的死机、掉电问题
- 纯应用层UI逻辑异常、与系统显示驱动无关的问题
- 进系统后亮屏异常、休眠唤醒异常（非开机阶段）的问题
- 仅一次性术语问答，无需完整SOP流程排查的场景

## 前置条件

分析前需确认以下输入信息可用：

| 输入项 | 必需性 | 用途 |
|--------|--------|------|
| 问题设备的MTK芯片平台型号 | 必需 | 确认芯片平台匹配 |
| 问题复现步骤、发生概率 | 必需 | 确认问题可复现性 |
| 预期行为与实际异常描述 | 必需 | 明确异常现象 |
| 串口Log | 必需 | 分析LK阶段运行情况 |
| Mobile Log（kernel_log、main_log） | 必需 | 分析内核阶段运行情况 |
| 近期修改的代码文件、可疑提交记录 | 可选 | 辅助定位 |

> 若存在mobilelog文件夹，需提取其中的kernel_log、main_log；开机阶段日志优先提取boot_normal子文件夹内的文件。

## 问题有效性确认

开始分析前，先确认：
1. 开机Boot阶段日志可正常打印
2. Linux内核日志可正常打印
3. 芯片平台为MTK

## 分析工作流

按以下步骤依次执行，不得跳步、不得颠倒顺序。详细操作参阅 [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)。

### 步骤1：日志完整性校验
- **目标**：确认日志文件是否满足分析条件
- **操作**：
  - 确认是否已获取串口Log（LK阶段）、Kernel Log
  - 过滤并排除与显示领域无关的日志文件，仅保留SOP定义的有效日志
- **判断**：
  - 缺少必须日志 -> 停止分析，向用户索要缺失日志
  - 日志齐全 -> 进入步骤2

### 步骤2：日志关键字过滤
- **目标**：按SOP关键字缩小分析范围
- **操作**：严格按照SOP给定的关键字过滤日志（不区分大小写）：`lcm`、`panel`、`drm`、`hwc`、`surfaceflinger`、`disp`、`dsi`
- **按LK阶段、Kernel阶段分别整理过滤结果** -> 进入步骤3

### 步骤3：问题阶段判定
- **目标**：确定问题发生在LK阶段还是Kernel阶段
- **判定规则**：
  - 若存在LK阶段串口日志，**优先分析LK阶段是否存在异常**，再分析Kernel阶段
  - 若不存在LK阶段串口日志，直接进入Kernel阶段分析

### 步骤4：分阶段日志分析

#### 子步骤4.1 LK阶段分析（按优先级排序）

1. 检查是否打印 `we will check lcm: [屏幕名], i=0`
   - 未打印 → 判定为LK阶段未执行屏幕识别流程
   - 已打印 → 继续检查

2. 检查 `islcmfound` 字段值
   - `islcmfound = 0` → 判定为LK阶段屏幕加载失败，未识别到有效屏幕
   - `islcmfound = 1` → 判定为LK阶段屏幕识别成功，继续检查

3. 检查屏幕名称打印 `lcm_name = [屏幕名]`，确认屏幕型号匹配

4. 检查 `[LK/LCM_DRV] lcm_epc_read epc_strings = [值]`
   - 数值全为0 → 判定为屏幕寄存器读取失败，屏幕硬件未连接或上电异常

5. 检查 `[LK/LCM_DRV]lcm_get_params lcm power init` 日志
   - 同项目正常日志有该打印、异常日志无打印 → 判定为Panel上电流程未正常执行

6. 检查 `[LK/LCM_DRV] lcm_init is cmd = 0 --`、`mt_disp_init xxx, found:x, lcm:"xxx"` 等LK初始化完成日志

#### 子步骤4.2 Kernel阶段分析（按优先级排序）

1. 检查MTK DRM模块加载日志 `init: init 6: Loading module /lib/modules/mediatek_drm_v1.ko with args ''`
   - 无该日志 → 判定为DRM驱动模块未加载
   - 有该日志 → 检查后续是否有mtk_drm相关流程日志，确认模块加载正常

2. 检查Panel probe流程日志
   - 必须成对出现 `<6>[    1.130871][   T10] [LCM] lcm_probe begin` 与 `<6>[    1.131110][   T10] [LCM] lcm_probe end`
   - 仅有begin无end → 判定为Panel probe流程执行失败

3. 检查DSI驱动等待日志 `mtk-dsi [寄存器地址].dsi: Waiting for bridge or panel driver`
   - 仅DRM加载前期少量打印 → 正常现象
   - DRM加载完成后持续打印、或日志全程持续打印 → 判定为Panel加载失败

4. 检查GPIO初始化日志 `[DISP][E]Cannot find disp pinctrl!`
   - 打印该日志 → 判定为屏幕引脚配置错误，需排查.dts和.dws文件中的GPIO配置

5. 若上述流程均无异常，可扩展检查GPU加载、SurfaceFlinger启动、HWC异常相关日志

### 步骤5：根因定位与输出
- 所有根因必须有对应的日志证据支撑
- 按可能性从高到低排序根因候选
- 给出符合SOP规范的、可落地的下一步调试动作
- 仅在有明确日志证据时，给出补丁/配置修改方向

## 关键字速查

完整的关键字列表和日志示例，参阅 [KEYWORDS.md](KEYWORDS.md)。

SOP官方关键字（不区分大小写）：`drm`、`lcm`、`panel`、`hwc`、`surfaceflinger`、`disp`、`dsi`

## 输出格式

按以下模板输出分析结论：

```markdown
# MTK Panel 加载异常日志分析报告

## 基本信息
- **分析时间**：{当前时间}
- **日志来源**：{用户提供的日志文件列表}
- **问题描述**：{用户提供的问题描述}
- **芯片平台**：{MTK平台型号}

## 问题有效性确认
- 是否符合SOP适用范围：{是/否}
- 判定依据：{简述}

## 现象与阶段总结
- **异常现象**：{描述}
- **问题阶段**：{LK阶段 / Kernel阶段 / LK+Kernel双阶段}

## 分析过程
### 步骤1：日志完整性校验
- 串口Log：{有/无}
- Kernel Log：{有/无}
- 判断结论：{是否满足继续分析条件}

### 步骤2：日志关键字过滤
- 搜索关键字：lcm, panel, drm, hwc, surfaceflinger, disp, dsi
- LK阶段过滤结果：{摘要}
- Kernel阶段过滤结果：{摘要}

### 步骤3：问题阶段判定
- 判定结果：{LK阶段 / Kernel阶段}

### 步骤4：分阶段日志分析
#### LK阶段分析
{各项检查结果及关键日志}

#### Kernel阶段分析
{各项检查结果及关键日志}

## 关键日志证据
{引用与异常强相关的原始日志片段，严格对应SOP的日志解读规则}

## 根因候选排序
按可能性从高到低排列：
1. {根因1} — 证据：{对应日志行}
2. {根因2} — 证据：{对应日志行}

## 下一步调试动作
{最小可验证的、符合SOP规范的排查步骤}

## 配置/补丁修改方向
{仅在有明确日志证据时输出，无证据不输出}
```

## 约束

1. 所有分析内容100%基于提供的SOP，不得新增SOP未定义的关键字、根因、分析流程
2. 所有结论必须有对应的原始日志证据支撑，不得编造无依据的猜测、推断
3. 仅处理MTK平台、开机阶段的显示问题，不得超出适用范围
4. 日志解读严格遵循SOP给定的规则，不得自行修改、扩展日志含义
5. 缺少必须的日志文件时，必须先向用户索要，不得无日志强行输出结论
6. 不假装看过未提供的日志；没有串口Log和Kernel Log时，不直接对Panel侧下结论

## 参考信息

- 关键字与日志示例：参阅 [KEYWORDS.md](KEYWORDS.md)
- 常见问题与根因对照：参阅 [COMMON_ISSUES.md](COMMON_ISSUES.md)
- 典型案例参考：参阅 [CASES.md](CASES.md)
- 详细分析步骤：参阅 [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)
