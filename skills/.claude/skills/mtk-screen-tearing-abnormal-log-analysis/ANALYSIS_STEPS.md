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
- **仅有main_log无kernel_log**：可分析合成链路，但DRM/DSI/TE分析受限
- **仅有kernel_log无main_log**：可分析底层链路，但合成侧分析受限
- **两者齐全**：进入步骤2

## 步骤2：日志关键字过滤

### 操作细则

1. 优先关键字过滤（不区分大小写）：
   ```
   tearing|vsync|te|frame_done|cmdq
   ```

2. 显示链路补充关键字过滤（不区分大小写）：
   ```
   drm|dsi|disp|lcm|hwc|surfaceflinger
   ```

3. 分别整理main_log和kernel_log的过滤结果，按时间排序

### 判断标准

- **过滤结果完全为空**：扩大关键字范围，或确认日志文件是否正确
- **过滤结果非空**：提取关键行，进入步骤3

## 步骤3：问题类型判定

根据用户描述的现象，判定问题属于以下哪种类型：

| 类型 | 特征 | 对应分析路径 |
|------|------|-------------|
| 全屏花屏 | 全屏雪花、彩条、马赛克 | 子步骤4.1 |
| 撕裂 | 上下半屏不同步，有横线 | 子步骤4.2 |
| 残影/拖影 | 上一帧残留、拖尾 | 子步骤4.3 |
| 局部异常 | 局部区域花屏、块状错位 | 子步骤4.4 |

## 步骤4：分类型日志分析

### 4.1 全屏花屏分析

#### 检查1：DSI链路错误
- **搜索关键字**：`mtk-dsi.*underrun|DSI error|LCD-CV error`
- **搜索目标**：确认DSI链路是否有错误打印
- **判断**：
  - 打印错误 → DSI信号异常导致花屏，记录错误类型和频率
  - 无错误 → 继续检查2

#### 检查2：CMDQ执行异常
- **搜索关键字**：`cmdq.*timeout|cmdq.*error|CMDQ.*ERR`
- **搜索目标**：确认CMDQ是否有超时或错误
- **判断**：
  - 打印超时/错误 → CMDQ任务执行异常，画面未正确刷新
  - 无异常 → 继续检查3

#### 检查3：Panel Init Code
- **搜索关键字**：`lcm_probe|lcm_init|panel.*init`
- **搜索目标**：确认Panel初始化是否正常
- **判断**：
  - 伴随Panel初始化失败打印 → 可能为屏初始化错误，可结合panel_load_abnormal SOP分析
  - Panel初始化正常 → DSI/CMDQ均无异常的全面排查

### 4.2 撕裂分析

#### 检查1：TE信号
- **搜索关键字**：`wait TE timeout|TE`
- **搜索目标**：确认TE信号是否正常
- **判断**：
  - 打印`wait TE timeout` → TE信号缺失或不稳定，判定为TE同步异常导致撕裂
  - 无TE相关打印 → 检查是否有周期性的TE中断日志或vsync打印，无则TE可能未使能

#### 检查2：VSync同步
- **搜索关键字**：`SurfaceFlinger.*VSync`
- **搜索目标**：确认SurfaceFlinger是否按VSync周期提交
- **判断**：
  - VSync周期不稳定或有丢帧 → 合成侧同步异常

### 4.3 残影/拖影分析

#### 检查1：PQ/Dimming模块状态
- **搜索关键字**：`pq|ccorr|gamma|dither|aal`
- **搜索目标**：确认PQ模块是否有异常打印或状态切换
- **判断**：
  - PQ模块有异常状态切换 → PQ处理异常可能导致残影
  - 无异常 → 继续检查2

#### 检查2：frame_done完成情况
- **搜索关键字**：`frame_done|mtk_drm_crtc`
- **搜索目标**：确认frame_done周期是否稳定
- **判断**：
  - `frame_done timeout` → 一帧未按时完成上屏（主结论）
  - frame_done周期间隔不稳定 → 可能存在偶发性上屏延迟

### 4.4 局部异常分析

#### 检查1：Overlay/HWC图层合成
- **搜索关键字**：`SurfaceFlinger|HWC`
- **搜索目标**：确认HWC图层配置、层数是否异常
- **判断**：
  - 图层数量或配置异常 → 合成阶段问题
  - SurfaceFlinger中layer的region/crop异常 → 局部区域合成定义错误

#### 检查2：ROI（Partial Update）配置
- **搜索关键字**：`ROI|partial.*update|roi`
- **搜索目标**：确认ROI区域计算是否异常
- **判断**：
  - ROI计算值与实际更新区域不匹配 → ROI错误导致局部异常
  - MTK平台ROI功能可能影响局部刷新区域
