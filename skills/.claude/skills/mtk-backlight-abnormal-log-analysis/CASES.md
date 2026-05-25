# 典型案例

## 案例1：闪高亮

- **现象**：短时间内亮度明显跳变，出现闪屏
- **关键日志**：
  ```text
  02-05 19:27:19.928  1784  3617 D LocalDisplayAdapter: set backlight: 0.14782351, nits = 105.48613, sdrBacklight = 0.14782351, sdrNits = 105.48613
  02-05 19:27:19.932  1784  3617 D LocalDisplayAdapter: set backlight: 0.07235585, nits = 52.97612, sdrBacklight = 0.07235585, sdrNits = 52.97612
  ```
- **分析**：两笔日志间隔仅4ms，背光值从0.148跳变到0.072，nits从105降到53，差值超过50 nits
- **根因**：短时间连续下发两笔差值较大的背光值

---

## 案例2：闪黑屏（背光写0）

- **现象**：运行过程中画面瞬时变黑
- **关键日志**：
  ```text
  [ 9723.689160] [LCM] lcm_setbacklight_cmdq level = 0, mapped_level = 0, dim_state = 1
  ```
- **分析**：`level = 0` 表明背光值被设为0，屏幕完全熄灭
- **根因**：存在背光值写0，导致屏幕闪黑

---

## 案例3：闪黑屏（ESD重启）

- **现象**：屏幕异常后触发重启并伴随黑屏闪烁
- **关键日志**：
  ```text
  [218918.168544] [T30821] [DISP][E][ESD0]esd check fail, will do esd recovery. try=1
  ```
- **分析**：ESD（静电放电）检测失败，触发ESD Recovery流程，该流程会导致屏幕重启，重启过程中背光短暂为0
- **根因**：ESD触发导致屏幕重启
