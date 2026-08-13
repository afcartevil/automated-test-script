# 详细分析步骤

## 步骤1：获取日志

### 操作细则

1. 如果给定的是JIRA号：
   - 从JIRA的`Log and Screenshot address`获取mobilelog或用户提供的log地址
   - 下载并解压日志包

2. 如果给定的是文件夹：
   - 遍历文件夹，识别日志文件类型
   - 排除与显示领域无关的日志文件（如modem_log、radio_log等）
   - 仅保留：串口日志、Kernel日志、Android日志等有效文件

3. 若存在mobilelog文件夹：
   - 提取`APLog_*/main_log_*`作为main_log
   - 提取`APLog_*/kernel_log_*`作为kernel_log
   - 开机阶段相关日志优先提取`boot_normal`子文件夹内的kernel_log

### 判断标准

- **无kernel_log且无main_log**：停止分析，提示用户需提供至少一份日志
- **仅有main_log无kernel_log**：可分析上层背光设置，但底层分析受限，需在报告中说明
- **仅有kernel_log无main_log**：可分析底层背光执行，但上层分析受限，需在报告中说明
- **两者齐全**：进入步骤2

## 步骤2：日志关键字过滤

### 操作细则

1. 在main_log中搜索以下关键字（不区分大小写）：
   ```
   power|backlight|brightness|aal|lcm|panel|LocalDisplayAdapter|led
   ```

2. 在kernel_log中搜索以下关键字（不区分大小写）：
   ```
   power|backlight|brightness|aal|lcm|panel|led
   ```

3. 分别整理过滤结果，按时间排序

### 判断标准

- **过滤结果完全为空**：扩大关键字范围，或确认日志文件是否正确、是否发生日志轮转
- **过滤结果非空**：提取关键行，进入步骤3

## 步骤3：问题分类与链路分析

### 3.1 背光设置失效

**判定条件**：用户设置亮度但屏幕亮度无变化

1. 先读main_log，搜索`LocalDisplayAdapter.*set backlight`或`write.*brightness`
2. 确认上层是否发出了背光设置指令
3. 再读kernel_log，搜索`lcm_setbacklight_cmdq`
4. 确认底层是否执行了背光设置
5. 对比上下层背光值是否一致

**结论导向**：
| 上层设置 | 底层设置 | 结论 |
|----------|----------|------|
| 有 | 无 | 背光设置未到达底层，排查HAL/驱动通路 |
| 无 | 无 | 上层未发起背光设置，转单给上层 |
| 有 | 有（值不一致） | 背光值映射问题，排查gamma/bl映射曲线 |

### 3.2 闪屏

**判定条件**：屏幕亮度出现短时跳变

1. 在main_log中搜索`LocalDisplayAdapter.*set backlight`，检查相邻两笔背光值是否存在大幅跳变（差值>0.05浮点值或>30 nits视为大幅跳变）
2. 在kernel_log中搜索`lcm_setbacklight_cmdq`，检查底层背光值是否存在跳变
3. 若上层和底层均无背光设置跳变，检查AAL相关日志：
   - main_log中搜索`AalUtils|AAL.*setSmartBacklightStrength`
   - kernel_log中搜索`AALMain`
4. 若仍无发现，可检查是否修改颜色模式，以及PQ、CCORR等模块状态变化

### 3.3 黑屏

**判定条件**：屏幕全黑，无法看到任何内容

1. 先判断Power状态是否变化：
   - 在kernel_log中搜索`power`相关打印
   - 检查是否存在屏幕关闭/开启序列
2. 判断是否背光写0导致黑屏：
   - 在kernel_log中搜索`lcm_setbacklight_cmdq level = 0`
   - 确认level=0的时间与用户报告的黑屏时间是否吻合
3. 若为Power状态变化导致背光写0，需继续分析屏幕重启原因：
   - 重点搜索`esd check fail, will do esd recovery`
   - 检查ESD Recovery触发的完整时序

### 3.4 亮度过低

**判定条件**：屏幕亮度异常偏低

1. 在main_log中搜索`LocalDisplayAdapter.*set backlight`，检查背光值是否在短时间内由较高值快速降为较低值
2. 在kernel_log中搜索`lcm_setbacklight_cmdq`，确认底层背光值变化
3. 检查AAL/ESS模块是否在降低背光：
   - 搜索`AalUtils|AAL.*BL=`检查背光变化趋势

## 补充检查项

### ESD Recovery 检查

在kernel_log中搜索关键字：`esd check fail|esd recovery`

### AAL/ESS 模块检查

在main_log中搜索：`AalUtils|AAL.*BL=|setSmartBacklightStrength`
在kernel_log中搜索：`AALMain`

### Power 状态检查

在kernel_log中搜索：`power|suspend|resume|panel_power`

### 颜色模式/PQ/CCORR 检查

若上层和底层均无背光设置异常，可能是颜色模式或PQ模块导致显示效果变化（非背光变化），在main_log中搜索：`ColorMode|PQ|CCORR`
