# Stability Analysis Reference

## 1. 适用范围

本专题用于指导以下 Modem 稳定性问题的首轮分析与归因：

- Baseband 版本显示 `Unknown`
- IMEI 丢失或显示异常
- SIM 不识别且伴随 Modem 异常迹象
- 信号短时间消失（约 10s 左右）后自动恢复
- 弹出 modem crash 提示
- 蜂窝数据掉网、偶发通信能力整体失效
- OTA 后通信能力异常
- FANSAEE / MonkeyAEE / 大数据监控捕获到的 Modem EE

> 这类问题不要只盯现象。`Baseband Unknown`、`IMEI 消失`、`短时掉信号后恢复`，很多时候只是 Modem EE 的外在表现，真正要找的是 EE 点和触发模块。

---

## 2. 分析前的最小证据集

开始分析前，优先补齐这些信息：

- 现象类型：Baseband Unknown / IMEI 异常 / crash 提示 / 掉信号恢复 / 不识卡 / 掉网
- 问题时间点
- 平台：MTK / SPRD / Qcom
- 软件版本、baseband 版本
- OTA 场景、Monkey/Fans 场景或大数据场景说明
- DUT / REF 对比结果
- 更换 SIM、切换网络环境后的对比结果
- 是否可稳定复现
- 全量日志包

### 2.1 外部因素先排除

优先确认：

1. 更换 SIM 卡后问题是否仍复现。
2. 更换网络环境后问题是否仍复现。
3. 若是市场客诉类 EE，不要默认就是软件问题，资料明确提示这类问题**很多可能是硬件导致 Modem 加载失败**。
4. 记录清楚触发路径，避免后续无法复现或无法对比 patch 效果。

### 2.2 必须具备的核心日志

至少要确认日志包中包含：

- `main_log`
- `modem log / modem dump log`
- `_EE_INVALID` dump 目录
- `__exp_main.txt`
- `SYS_KERNEL_LOG`
- `taglog`（粉丝日志 / FANSAEE 场景）
- `minidump`（大数据场景）

---

## 3. 先判断是不是 Modem EE

以下现象出现时，优先按 Modem EE 路径分析：

- Baseband 显示 `Unknown`
- IMEI 丢失
- SIM 不识别且伴随 baseband 异常
- 信号突然消失后自动恢复
- 系统弹出 modem crash 提示
- 日志中出现 `Modem exception` / `[ASSERT]` / `[Fatal error]`

### 3.1 资料中的 5 类 EE 场景

1. **Baseband Unknown / 不识卡类 EE**
2. **信号消失后恢复 / modem crash 界面类 EE**
3. **FANSAEE / MonkeyAEE 触发类 EE**
4. **大数据 USIC 监控捕获类 EE**
5. **非常规 EE**（如 IO 负载过高、OTA 升级被打断）

---

## 4. 关键日志与关键词速查

### 4.1 关键日志文件

- `main_log`
- `modem dump log`
- `__exp_main.txt`
- `SYS_KERNEL_LOG`
- `taglog`
- `minidump`

### 4.2 关键搜索词

- `ccci_mdinit`
- `Modem exception`
- `[ASSERT]`
- `[Fatal error]`
- `exception`
- `assert`
- `crash`

### 4.3 先看什么

1. **先找 EE 是否真的发生**：`main_log` 搜 `Modem exception / assert`。
2. **再拿 ASSERT 详情**：文件路径、行号、`P1/P2/P3` 参数。
3. **再判断所属模块**：
   - `rf check` 目录：多数偏 RF 配置错误
   - `mml1/` 目录：多数偏射频相关问题
4. **若日志打印前就挂死**：改抓 dump，必要时手动触发 dump / crash 采集。

---

## 5. 标准分析流程

## 5.1 先确认 EE 证据是否完整

### 常规场景

- `modem log` 中找 `_EE_INVALID` 目录
- `main_log` 中搜索 `exception` 或 `assert`
- 从 `aee_exp` / `__exp_main.txt` 中确认 EE 点

### 打印不全场景

若 AP log 没来得及完整打印，资料建议：

- 手动触发 dump 模式
- 补抓 dump log
- 再确认 EE 点

## 5.2 再做初步归因

从 ASSERT 中提取：

- 报错文件路径
- 行号
- `P1 / P2 / P3`

然后按下面顺序判断：

1. 本地能否根据路径判断大类模块
2. 是否命中已有已知问题
3. 若未知，准备符号表和全量 DbgInfo 升级给平台侧

## 5.3 已知问题 / 未知问题分流

### 已知问题

- 查到相同根因 CR
- 确认 patch ID
- 确认 patch 申请情况
- 合入 patch 并做基本功能自检

### 未知问题

需准备至少这些材料给平台：

1. 问题时间点的 `MD log` 和 `MD dump bin`
2. 问题时间点的 `AP log`
3. 对应版本的 `Modem ELF`
4. `DbgInfo_XXX all files`

之后再跟平台侧跟进 debug patch 与正式 patch。

---

## 6. 场景化分析打法

## 6.1 Baseband Unknown / 不识卡 / IMEI 丢失

### 分析步骤

1. 先看 baseband 状态，初步判断是否为 Modem EE。
2. 在 `main_log` 中搜 `Modem exception`。
3. 查是否有 ASSERT 报错、文件路径、行号、参数。
4. 判断是否涉及 Modem 启动、img 加载、NV 校验、状态检查。

### 常见归因

- **配置错误**
- **patch 依赖漏合**
- **平台修改引入问题**
- **单机硬件问题**
- **NV 校验失败**（尤其 OTA 打断后）

## 6.2 信号消失后自动恢复 / 弹出 modem crash 提示

### 分析步骤

1. 先在 `main_log` 搜 `Modem exception`。
2. 再定位 ASSERT 的具体文件 / 行号 / 参数。
3. 如果路径在 `rf check` 或 `mml1/`，优先按 RF / 射频方向看。
4. 若日志不足，补抓 dump 再确认。

### 常见归因

- **RF 配置错误**
- **射频相关异常**
- **偶发系统负载触发的 Modem 超时 / EE**

## 6.3 FANSAEE / MonkeyAEE 场景

### 分析步骤

1. 在 `__exp_main.txt` 确认 EE 点。
2. 从粉丝日志系统捞对应 `taglog`。
3. 若无对应 `taglog`，需发起采集申请。

### 常见归因

- **随机压力场景触发底层异常**
- **已知 EE 在压力或边界场景复现**

## 6.4 大数据 USIC 监控场景

### 分析步骤

1. 使用 TNE 解析工具分析日志。
2. 必要时根据大数据记录补捞 `modem dump`。
3. 核心仍看 `main_log + minidump + ASSERT`。

### 常见归因

- **线上偶发 EE**
- **需要结合 minidump 做进一步平台分析**

## 6.5 非常规 EE（IO 负载 / OTA 中断）

### 分析步骤

1. 在 `main_log` 搜 `Modem exception`。
2. 提取 ASSERT 的文件、行号、参数。
3. 结合场景确认是否存在 OTA 被打断、后台 IO 抢占等非标准触发因素。

### 常见归因

- **IO loading 过高导致 Modem EE**
- **OTA 过程中被强行打断，导致 NV/版本数据损坏**

---

## 7. 典型案例沉淀

## 7.1 OTA 后不识卡、IMEI 消失、Baseband Unknown

### 已知现象

- OTA 升级后出现不识卡
- IMEI 丢失
- Baseband 显示 `Unknown`

### 文档给出的归因路径

1. 先看 baseband，初判为 Modem EE。
2. `main_log` 中搜 `Modem exception`。
3. ASSERT 指向 NV 校验相关模块。
4. 根因是 **OTA 升级被打断，NV 分区数据损坏，Modem 启动校验失败触发 EE**。

### 处理建议

- 合入 NV 校验兼容补丁
- OTA 包增加完整性校验
- 避免升级过程异常中断

## 7.2 IO 负载过高导致偶现 EE

### 已知现象

- 机器无操作情况下偶现 10 秒左右掉信号
- 随后自动恢复

### 文档给出的归因路径

1. 查看 modem dump 日志。
2. ASSERT 落在 IO 读写相关模块。
3. 问题发生时后台多个进程同时进行 IO 读写，抢占 Modem 子系统调度资源，超时触发 EE。

### 处理建议

- 优化系统 IO 调度策略
- 限制后台进程 IO 优先级
- 减少对 Modem 子系统资源抢占

---

## 8. 展锐平台补充要点

资料对 SPRD 的扩展重点是三步：

1. **dump 抓取**
2. **dump 解析**
3. **初步分析**

### 关键做法

- 在抓到的 Modem log 中关注 `minidump` 和 `.dmp`
- `.dmp` 可放入 `logel` 工具解析，生成 `.ass` / `.mem`
- `android.log` 中搜索 `MODEM_CTRL / assert / crash`
- 若需进一步升级给平台，准备：
  - Dump log（含 dmp 与 minidump）
  - 问题版本信息（含 Modem 版本号）
  - 版本对应符号表（如 `.axf`）

---

## 9. 输出建议

对外输出时，建议按下面的口径组织：

1. **先判断是否已经具备 EE 证据**，不要只根据外在现象下结论。
2. **明确给出 ASSERT 文件路径、行号、P1/P2/P3**，这是升级分析的核心材料。
3. **明确已知/未知问题分流**：已知就走 patch，未知就备齐符号表与全量日志升级平台。
4. **不要默认 EE 一定是软件问题**，市场客诉类要同步提醒硬件排查可能性。

---

## 10. 当前资料边界

当前专题已经覆盖：

- Modem EE 的标准判断入口
- Baseband Unknown / IMEI / 信号恢复类问题的共性打法
- ASSERT 路径、行号、参数的核心价值
- 已知/未知问题的升级材料要求
- OTA 中断、IO 负载、FANSAEE、大数据等典型场景

当前资料对平台侧闭源源码细节无法直接展开，本地分析若无法从路径与参数完成归因，应尽快转平台侧并附齐符号表与 DbgInfo。 
