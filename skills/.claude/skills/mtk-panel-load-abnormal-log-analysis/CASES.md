# 典型案例

## 案例1：开机黑屏

- **现象**：开机黑屏，串口日志正常打印
- **关键日志**：
  ```text
  [LK/LCM_DRV] nt36672c_fhdp_dsi_vdo_120hz_lj6, islcmfound = 0
  ```
- **分析**：`islcmfound = 0` 说明LK阶段未识别到有效屏幕，屏幕加载失败
- **根因**：LK阶段屏幕加载失败

---

## 案例2：开机卡Logo

- **现象**：LK Logo正常显示，进入内核后黑屏
- **关键日志**：
  ```text
  [    5.234567] mtk-dsi 1400b000.dsi: Waiting for bridge or panel driver
  [    6.234567] mtk-dsi 1400b000.dsi: Waiting for bridge or panel driver
  [    7.234567] mtk-dsi 1400b000.dsi: Waiting for bridge or panel driver
  ```
- **分析**：DRM加载完成后持续打印DSI等待日志，说明Panel驱动一直未就绪
- **根因**：Kernel阶段Panel加载失败

---

## 案例3：进Kernel花屏

- **现象**：LK Logo正常显示，进入内核后花屏
- **关键日志**：
  ```text
  [DISP][E]Cannot find disp pinctrl!
  ```
- **分析**：显示引脚控制器找不到，GPIO配置有问题导致Panel驱动无法正确控制屏幕
- **根因**：显示GPIO配置异常，需排查`.dts`和`.dws`文件中显示相关的GPIO引脚配置
