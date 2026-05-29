---
tahp_adapt_skill: true
name: kb-skill-telephony-bug-analysis-mppj539v
domain_label: "telephony — bug_analysis"
domain_id: "kb-skill-telephony-bug-analysis-mppj539v"
module: "通信"
func_type: "AI故障分析"
funcType: "AI故障分析"
group: "通信"
status: "deprecated"
generated_from_knowledge: true
generated_from_entries: '["kb-61c0c843","kb-632fd9ca","kb-86f855e4","kb-a86866c6","kb-c36eb613","kb-dceb8985"]'
created_at: "2026-05-28T13:30:56.131Z"
source: knowledge_base
---

# Modem EE 异常崩溃问题定位与处理

## 适用场景
- 适用模块：通信模块
- 适用业务类型：Bug 分析
- 典型触发条件：
  1. 手机出现掉网、不识卡、IMEI 显示异常、基带版本显示为 Unknown 等问题
  2. 信号短时间消失后自动恢复或弹出 Modem Crash 提示
  3. FANSAEE/MonkeyAEE 测试触发或大数据 USIC 监控捕获到 `External (EE)` 异常
  4. 日志中出现 `[ASSERT]` 或 `[Fatal error]` 关键打印，且报错文件路径位于 Modem 侧（如 `mcu/`, `mml1/` 等目录）

## ⚠️ 不适用情况（请人工补充）
- 单纯的 SIM 卡物理损坏或运营商网络故障导致的掉网，非 Modem 固件崩溃引发（待人工确认）
- 应用层网络请求失败，且内核/底层日志未发现 Modem 异常重启或 Assert（待人工确认）

## 核心处理方法
1.  **问题确认与外部排查**：
    - 更换 SIM 卡、更换网络环境（如从 5G 切 4G，或更换运营商），确认问题是否依然复现。排除 SIM 卡损坏和运营商网络波动。

2.  **日志抓取准备与复现**：
    - **开启关键开关**：进入工程模式，确保 Modem Dump 保存功能开启且 Modem 自动 Reset 功能关闭（防止重启冲掉现场）。
      - `*#9646633#` -> Debug&LOG -> YLog -> Settings -> Log Setting -> Modem log Setting -> ModemReset 关闭。
      - `*#9646633#` -> Debug&LOG -> YLog -> Settings -> Log Setting -> Modem log Setting -> ModemSaveDump 打开。
    - **抓取日志**：按照复现路径操作，触发 Modem EE 崩溃。
    - **确认核心产物**：导出日志后，确认包含 `_EE_INVALID` dump 目录、`main_log`、`modem log`、`__exp_main.txt` 等文件。

3.  **日志分析关键步骤**：
    - **寻找异常发生点**：在 `main_log` 或 `__exp_main.txt` 中搜索关键词：`modem exception`、`[ASSERT]`、`[Fatal error]`。
    - **提取关键特征**：获取 ASSERT 打印的具体信息：
      - **文件名与行号**：如 `file: mcu/l1/mml1/.../mml1_rf_error_check.c`，`line:156`。
      - **参数**：提取 P1/P2/P3 的值（如 `p1:0x00000003, p2:0x0000000b, p3:0x00000007`）。
    - **初步定界分析**：
      - 若报错路径包含 `rf check` 目录，通常为 RF 配置错误。
      - 若报错路径包含 `mml1/` 目录，通常为射频相关问题。
      - 若为 `IO_LOADING` 负载过高等情况，需排查是否存在 OTA 升级强行打断、大核频响过高导致 Modem 无响应等场景。

4.  **问题定位与处理流程**：
    - **已知问题排查**：根据提取的文件名、行号、P1/P2/P3 参数，在内部 Jira、MTK Online 等平台上搜索是否为已知问题或历史 Case。
    - **未知问题提报**：若为未知问题，提取对应版本的 Modem ELF 文件、DbgInfo 全量文件及完整 Dump，提交给芯片平台（MTK/展锐/高通）进行根因分析。

## 示例

### 正例
- **问题场景**：信号消失后自动恢复。
- **日志特征**：
  ```
  [ASSERT] file: mcu/l1/mml1/mml1_rf/src/mmrf/gen99/mml1_rf_error_check.c
  line: 156
  p1: 0x00000003
  p2: 0x0000000b
  p3: 0x00000007
  ```
- **分析结论**：报错文件位于 `mml1` 射频目录下的 RF 错误检查函数，属于射频相关的 Modem EE。

### ⚠️ 反例（请人工补充）
- 待人工补充：请补充一个“日志中出现 Modem 重置打印，但实际为正常的 OTA 升级冷重启，而非异常崩溃”的反例。

## ⚠️ 版本与平台约束（请确认）
- Android 版本范围：【待确认，知识条目提及大数据、FANSAEE 等场景，推测多用于 Android 10 及以上项目，请确认是否覆盖低版本】
- 芯片平台：MTK、展锐（SPRD）、高通全系列手机平台
- AOSP 分支：【待确认，请注明是否有特定分支限制】

## 注意事项
1.  **符号表匹配**：提交给平台分析时，**必须**提供与软件版本完全匹配的符号表（ELF/DbgInfo 文件），否则无法解析调用栈。
2.  **Dump 抓取时机**：部分 Modem EE 可能在日志打印前就挂死，常规抓取不到。若未找到 ASSERT 打印，需手动触发 dump 模式抓取 minidump 或全量 dump。
3.  **文件路径分析逻辑**：不要直接复看代码，先在项目代码里核对报错文件路径是否真实存在。若存在则查看上下文逻辑；若不存在，大多为平台私有库 release 版本异常，直接走平台提 Case 流程。

## 维护信息
- 维护人：【待指定】
- 生成来源：知识库 6 条条目
- 模板版本：v1.0

---
