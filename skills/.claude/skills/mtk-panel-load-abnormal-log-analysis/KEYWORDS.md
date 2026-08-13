# 关键字速查

## SOP官方关键字（不区分大小写）

| 关键字 | 适用日志 | 说明 |
|--------|----------|------|
| `lcm` | LK串口, kernel_log | LCM（液晶模组）驱动相关，含屏幕识别、初始化、probe全链路 |
| `panel` | LK串口, kernel_log | Panel（面板）驱动，加载和上电流程 |
| `drm` | kernel_log | Direct Rendering Manager，MTK显示驱动框架核心模块 |
| `hwc` | main_log | Hardware Composer，负责图层合成 |
| `surfaceflinger` | main_log | SurfaceFlinger，Android显示合成服务 |
| `disp` | kernel_log | Display子系统，含GPIO、ESD、Pinctrl相关打印 |
| `dsi` | kernel_log | MIPI DSI接口，Panel与主控之间的显示串行接口 |

## 关键日志示例与解读

### 1. LK阶段关键日志

#### 1.1 屏幕识别流程
```text
we will check lcm: [nt36672c_fhdp_dsi_vdo_120hz_lj6], i=0
```
**解读**：LK开始检查屏幕，`[屏幕名]`标识目标屏幕型号，`i=0`表示第一轮检查。

#### 1.2 屏幕识别结果
```text
[LK/LCM_DRV] nt36672c_fhdp_dsi_vdo_120hz_lj6, islcmfound = 1
```
**解读**：
- `islcmfound = 1` → 屏幕识别成功
- `islcmfound = 0` → 屏幕识别失败，未找到有效屏幕

#### 1.3 EPC寄存器读取
```text
[LK/LCM_DRV] lcm_epc_read epc_strings = 000000000000000000000000000000000000
```
**解读**：EPC寄存器值全为0 → 屏幕硬件未连接或上电异常，芯片无法读取屏幕寄存器。

#### 1.4 Panel上电初始化
```text
[LK/LCM_DRV]lcm_get_params lcm power init
```
**解读**：Panel上电初始化流程入口。同项目正常日志有该打印、异常日志无打印 → Panel上电流程未正常执行。

#### 1.5 LK初始化完成
```text
[LK/LCM_DRV] lcm_init is cmd = 0 --
mt_disp_init xxx, found:x, lcm:"nt36672c_fhdp_dsi_vdo_120hz_lj6"
```
**解读**：LK阶段屏幕初始化完成，`lcm_init`返回0表示成功，`found:x`表示找到的屏幕数量。

### 2. Kernel阶段关键日志

#### 2.1 DRM模块加载
```text
init: init 6: Loading module /lib/modules/mediatek_drm_v1.ko with args ''
```
**解读**：MTK DRM内核模块开始加载。无该日志 → DRM驱动未加载，后续显示链无法正常工作。

#### 2.2 Panel Probe流程
```text
<6>[    1.130871][   T10] [LCM] lcm_probe begin
<6>[    1.131110][   T10] [LCM] lcm_probe end
```
**解读**：Panel probe开始和结束。**必须成对出现**，仅有begin无end → Panel probe执行失败。

#### 2.3 DSI等待日志
```text
mtk-dsi 1400b000.dsi: Waiting for bridge or panel driver
```
**解读**：
- DRM加载前期少量打印 → 正常，DSI等待Panel驱动就绪
- DRM加载完成后持续打印或全部日志持续打印 → Panel加载失败，DSI一直等待

#### 2.4 GPIO配置错误
```text
[DISP][E]Cannot find disp pinctrl!
```
**解读**：显示引脚控制器未找到 → 屏幕GPIO配置错误，需排查`.dts`和`.dws`文件。
