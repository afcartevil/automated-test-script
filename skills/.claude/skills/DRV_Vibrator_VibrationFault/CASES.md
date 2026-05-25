# 典型案例

## 案例1：HAL 层服务异常

### 现象
全场景都没有振动。

### 分析过程
1. 获取 `kernel_log`、`main_log`、`sys_log`
2. 在 sys_log 中搜索 `vib|haptic|richtap`，发现应用通过 `TranVibratorManagerInternal: vibrate: *.he` 下发了 HE 文件
3. 但同时观察到 HAL 层错误日志 `RichTapVibratorService: aac richtap doVibratorStop fail.`
4. 全场景表现一致，说明问题不在某个 HE 文件上

### 根因
HAL 层马达服务异常。

### 关键日志
HAL 马达层服务调用异常：

```
RichTapVibratorService: aac richtap doVibratorStop fail.
```

### 处理建议
- 检查 HAL 层瑞声 / 艾为马达算法库
- 必要时升级或回退算法库版本

---

## 案例2：无振动，有波形文件返回

### 现象
某些场景有 HE 文件的下发且能感受到振动，小部分场景下发了 HE 但没有振动。

### 分析过程
1. 获取 `kernel_log`、`main_log`、`sys_log`
2. 在 sys_log 中确认问题场景已调用 `TranVibratorManagerInternal: vibrate: <文件名>.he`
3. 在 sys_log 中确认 HAL 层 `RichTapVibratorService` 没有 `doVibratorStop fail.` 异常
4. 在 main_log 中搜索 `FileNotFoundException`，发现该 HE 文件缺失
5. sys_log 中伴随 `TranVibratorManagerInternal: can not find patternList.`

### 根因
缺少对应的 HE 文件。

### 关键日志
```
TranFileUtil: java.io.FileNotFoundException: /tr_product/etc/asset/vibrates/XXXX.he: open failed: ENOENT (No such file or directory)
```

### 处理建议
- 在 SCM 平台上配置缺失的 HE 文件
- 验证 `/tr_product/etc/asset/vibrates/` 目录下确实有该 HE

---

## 案例3：有振动，但无波形文件返回

### 现象
能感受到该场景的振动，但该场景没有下发 HE 文件。

### 分析过程
1. 获取 `kernel_log`、`main_log`、`sys_log`
2. 在 `sys_log`/`main_log` 中按问题场景的应用与时间窗口检索：无 `TranVibratorManagerInternal: vibrate: *.he`，**即可判定未走 HE 下发，属安卓原生振动链路（无 HE 波形）**
3. 在 `main_log` 中检索 `SystemVibratorManager vibrate`、`Vibrator: Vibrator using LED trigger` 等作为**可选佐证**（有则写入报告；无则注明仅凭「无 Tran HE 下发」得出结论）

### 根因
应用未适配，该场景未通过 Tran 下发对应的 HE 文件。

### 关键日志
**判定依据（无 Tran HE 下发）**：问题窗口内检索不到如下形式的日志：

```
TranVibratorManagerInternal: vibrate: <场景期望>.he, pkg = <问题应用>, usage = *
```

**佐证示例（可选）**：

```
Vibrator: Vibrator using LED trigger
```

### 处理建议
- 将问题交给对应应用的同事分析适配
- 应用需要调用 `TranVibratorManagerInternal.vibrate(<HE 文件名>, pkg, usage)` 下发 HE 文件
