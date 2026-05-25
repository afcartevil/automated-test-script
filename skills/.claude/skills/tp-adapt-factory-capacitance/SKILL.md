---
name: tp-adapt-factory-capacitance
description: >-
  Imports Transsion MTK factory TP capacitance (容值) test end-to-end when missing:
  `/proc/tp_panel_test` proc, controller `ops` callback for tp_panel_test, vendor
  implementation, and factory config/APK alignment. Use when 导入容值测试、工模无容值项、
  proc 可读但无结果、ops 未挂接、新机型 port 工厂 TP 自测，或 Touch Panel 工厂流缺 capacitance.
---

# Transsion 工厂 TP 容值测试 — 未导入时的完整导入流程

工模通过 **`/proc/tp_panel_test`**（**open → read**，部分方案同一 fd 上 **write 再 read**）访问内核；内核再把命令落到 **当前 vendor 触摸驱动**的容值/面板自检实现。本技能的目标是：当容值测试**尚未导入**时，**直接改代码与配置完成导入**，而不是只做现象分析。

## 1. 先判定「未导入」指哪一种（必须逐项勾选）

在动手合代码前，用机台或代码结论对齐缺口（可多选）：

| 缺口 | 典型证据 | 导入时侧重 |
|------|----------|------------|
| **A. proc 未注册** | `/proc/tp_panel_test` 不存在；内核无 `tp_panel_test` 相关 `proc_create` | 从参考工程移植 proc 注册与 `file_operations` |
| **B. proc 有、vendor 未实现 / `ops` 未挂** | 节点存在，read 恒空/固定失败；或 core 里调用 `controller->ops->…` 但该成员为 **NULL** / 未在 vendor 里填入 | **在对应 `controller` 的 `ops` 中注册 `tp_panel_test`（或公共层实际调用的同名）回调**，并实现函数体 |
| **C. 协议与工模不一致** | APK write 子项，内核只实现 read（或反之） | 对照工厂 APK **strace / 源码** 统一 read/write 协议 |
| **D. 工厂菜单或流控未开** | 内核正常，`factory.ini` / `factory.chn.ini` 或工厂 APK 子项未启用 | 改 `custom/<project>/factory/*.ini` 或 APK 资源（以参考机为准） |
| **E. 副屏/双 TP** | 主屏 OK、副屏无proc或读错屏 | 按参考工程为 sub 注册独立 proc 或参数区分 |

未烧机时：**在当前 kernel / vendor 树内检索** `tp_panel_test`、`panel_test`、`proc_create`；与**已支持容值的参考机型**对比，缺失即视为未导入。

## 2. 选定参考工程（强制）

- 优先：**同 TP IC / 同一 vendor 驱动族**且工厂已验证容值 OK 的分支或 `custom/<ref>/`。
- 若无同 IC：退而求其次选 **同一 Transsion touch 架构**（`transsion` core + 相同 proc 协议），再换 vendor 命令字。

在参考树中锁定这些位置（路径随分支变化，以搜索结果为准）：

- `proc` 注册与 **`struct proc_ops` / `file_operations`**（`read`/`write`/`open`/`release`）。
- 从 proc 处理函数跳到 **IC 容值或 self-test** 的函数（常见为发固件命令、读 raw、再格式化输出给工厂）。
- **公共层若通过 `g_tran_ts.controller[MAIN/SUB].ops` 分发**：在参考工程中对照 **结构体类型定义**（如 `struct tran_ts_operations` 等，以当前分支符号为准）里 **与 panel test / selftest 对应的成员名**，以及 vendor 里 **`.xxx = yyy_handler` 初始化行**。

**禁止**：凭空发明 `/proc/tp_panel_test` 的字符串协议；**必须与参考工程或现网工厂 APK 行为一致**。

## 2.1 必查：vendor 是否在 controller 的 `ops` 里挂上 `tp_panel_test` 分发（导入前/后都做）

Transsion 架构下，`/proc/tp_panel_test` 的读写处理函数常会 **`TRAN_MAIN_CONTROLLER` / `TRAN_SUB_CONTROLLER`** 取当前 `controller`，再调用 **`ops` 上某一成员函数**（成员名因分支而异，常见含 `panel_test`、`tp_panel_test`、`self_test`、`factory_test` 等）。**仅注册 proc 而在 vendor 的 `ops` 静态初始化里未赋值或仍为 `NULL`，容值逻辑仍算未导入。**

**Agent 在代码上必须逐项确认：**

1. **从 proc 入口追到调用点**  
   打开实现 `/proc/tp_panel_test` 的 `.c`，跟踪 **read / write** 最终调用的函数指针是哪一个（例如 `pController->ops->tp_panel_test` 之类 —— **以实际代码为准，不要臆测成员名**）。

2. **在头文件中找到 `ops` 结构体定义**  
   确认该成员是否已存在、参数与返回值类型（`char *buf`、`size_t count`、错误码等）。

3. **在目标 vendor 驱动里搜 `ops` 初始化**  
   在对应 IC 的 **`static const struct … ops xxx_ops = { ... }`**（或运行时赋值处）检查：  
   - 与步骤 1 **同名**的成员是否指向 **非 NULL** 的实现函数；  
   - 参考工程同一 IC 有赋值而当前项目缺失 → **必须补上同一成员 + 函数实现**。

4. **主副 controller**  
   若项目有副屏：`TRAN_SUB_CONTROLLER` 使用的 vendor `ops` 是否同样挂接（参考机副屏若支持容值，当前机也需一致）。

5. **与「仅 proc 内直连 I2C」路径区分**  
   若当前分支 proc **不经过 `ops`** 而直接在 proc 文件内调 vendor 静态函数：在 skill 结论中**写明实际路径**；若与参考机架构不一致，导入时仍建议**与参考对齐**（便于后续合码与双 IC 维护）。

**结论模板（写进 MR/回复）：**  
proc 分发函数：… → ops 成员名：… → vendor 实现：文件与函数名（已赋值 / 仍为 NULL）。

## 3. 内核侧导入步骤（agent 按序执行）

1. **搜索当前工程**  
   关键字：`tp_panel_test`、`panel_test`、`proc_create`、`PROC_ENTRY`、`tran_selftest`（若 legacy 共存）、`tran_ts_operations`（或当前树内 `struct … ops` 实际名）、`TRAN_MAIN_CONTROLLER`。

2. **与参考树 diff**  
   列出需新增或修改的 `.c/.h`：proc 模块、vendor 内实现、`Makefile` / `Android.bp` / `Kbuild` 是否包含新对象文件。

3. **移植 proc**  
   - 在 **TP driver probe 成功、controller 可用之后** 创建 `/proc/tp_panel_test`（或与参考一致的时机）；避免 early init 注册、read 时尚未 ready。  
   - 保持与参考一致的 **proc 权限与 owner**；若参考无特殊处理，不要随意加新的全局锁导致和工厂并发冲突。

4. **接 vendor 实现（含 `ops` 挂接）**  
   - **优先**按 **§2.1** 在 **`controller` 的 `ops` 中**增加与参考工程**同成员名**的函数指针，并实现对应 **`.c` 内函数**（发容值/自检命令、组包返回给 proc）。  
   - 若参考通过其它名字回调（如 `self_test`、`factory_panel_test`）：以参考与当前 **proc 调用点**为准对齐，**禁止只抄 proc 不抄 `ops` 表**。  
   - 若参考在 proc 内**直连** bus 而不走 `ops`：仅当本分支历史如此时才跟随；否则仍推荐走 **`ops`** 与公共层一致。  
   - 未实现的 IC：用 **datasheet / 参考驱动** 中工厂命令完成最小可读实现（先保证工厂 APK 能读到合法格式，再优化阈值）。

5. **编译与链接**  
   确认修改的 `.o` 打进实际加载的 **ko**（或 built-in），`MODULE` / `obj-y` 与项目 `ko_order` 一致。

## 4. 工厂 / 上层对齐（常与 D 类缺口同时做）

1. 在 **`vendor/mediatek/proprietary/custom/<project>/factory/`**（或 Transsion 等价目录）对比参考机：  
   `factory.ini`、`factory.chn.ini` 中与 **Touch Panel / 容值 / 子测试**相关的 `MenuItem`、开关项、流程项。  
2. 在工厂 **APK / jar / 资源**中搜索 **`tp_panel_test`**、`/proc/tp_panel_test`、`容值`、`capacitance`、`panel test`，确认：  
   - 打开的 path 是否为 `/proc/tp_panel_test`；  
   - 是否 **write** 以及写入的字节内容。  
3. 只改配置能解决的，**不要改内核**；只改内核不能显示菜单的，**必须改 ini/APK 配置**。

## 5. 导入完成标准（机测）

- `adb shell ls -l /proc/tp_panel_test` 成功。  
- 用 **与工模相同顺序**的 `open/read`（及 `write`）能得到**非空、与参考机格式一致**的结果；或与工厂 APK 联调 PASS。  
- **代码侧**：§2.1 中 **proc → `ops` 成员 → vendor 实现** 链条完整，**无 NULL 函数指针**（除非参考机明确依赖 fallback）。  
- **kernel_log** 无持续 I2C/SPI 错误；必要时可对比参考机的成功 log 片段。

## 6. 交付说明（agent 对用户输出）

完成导入后，用简短清单说明：

- 修改了哪些文件（kernel / factory / APK）。  
- 参考机或参考 commit。  
- `/proc/tp_panel_test` 是否需要 write、典型 read 长度或返回示例一行。  
- **`ops` 挂接**：列出的 `ops` 结构体类型、`成员名`、vendor 中赋值位置与实现函数。  
- 主副屏若仅主屏支持，需写明限制。

## 与其它技能的关系

- **时序类问题**（probe 未完成、controller 未 ready）仍可能导致 read 失败；可结合 `transsion-tp-engineering-sysfs` 核对 init 与 `mtk-tpd` 状态。  
- 本技能**优先完成「从未导入 → 已导入」**；若已导入但仍失败，再按第 1 节表格收紧到具体缺口做增量修复。
