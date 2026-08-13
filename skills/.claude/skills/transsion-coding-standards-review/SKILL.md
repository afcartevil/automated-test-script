---
name: transsion-coding-standards-review
description: >-
  按传音研发中心编码规范（M.RD-223 C/C++ V1.4 + Java/Android 规范）审核代码变更：
  注释格式与包裹块位置、命名、AOSP 修改方式与流程风险、修改建议。
  用于 code review、CR 审核、检查 patch 是否符合传音编码规范、审查 frameworks/vendor/BSP 改动时使用。
---

# 传音编码规范审核

基于 **M.RD-223 研发中心 C/C++ 编码操作规范 V1.4** 与 **Java 编码规范（通信产品三部）**，审核 diff/patch/代码片段是否符合规范；不合规项给出可落地的修改建议。

## 审核工作流

```
1. 识别语言/层级 → Java/Kotlin | C/C++(kernel/hal/native) | 配置(xml/rc/mk/dts/sh)
2. 识别修改类型 → 新增 | 修改 | 删除 | 注释掉
3. 识别代码归属 → OS库 | 项目库 | AOSP原生路径 | vendor/tran_os | overlay
4. 按本 skill 检查：注释 → 命名 → AOSP修改方式 → 流程风险
5. 输出结构化审核报告（见文末模板）
```

**原则**：不确定时，仿照同文件/同模块原生 code；原生 code 不得删除，只能注释或 overlay 替换。

---

## 1. 注释规范（必查）

### 1.1 通用格式

```
[部门简称]: <add|modify|delete> <修改原因(英文)> <bug_id> [(feature)] [by] <修改人> <YYYYMMDD> [start|end]
```

| 字段 | 要求 |
|------|------|
| 部门简称 | C/C++：OS/SPD/BSP/SDD/TSD/TCD/ITD；Java 项目库同理；**OS 库固定用 `OS`** |
| 修改原因 | **英文**，简述 why，禁止中文/拼音 |
| bug_id | 必须有；无则先在 JIRA 建单 |
| feature | 新增功能建议标注 |
| start/end | 代码块必须用 start/end **成对包裹** |

### 1.2 按文件类型的注释语法

| 文件类型 | 语法 | 包裹规则 |
|----------|------|----------|
| `.c/.cpp/.h/.java` | `//` | add/modify/delete 均需 start…end 包裹整块变更 |
| `.mk/.rc/.sh/.config` | `#` | 同上 |
| `.xml` | `<!-- -->` | 同上 |
| `.te`(SELinux) | `#` | **仅加在新增权限行前**；文件末尾禁止注释和空行 |
| `.dts` | `/* */` | 模块首次提交上下两端加总注释；后续只改两端注释 |

**示例（Java 项目库）**：
```java
// TDD:add fix null pointer SLLEL-1705 by jinxian.lei 20220815 start
mDateText.setColor(Color.BLACK);
// TDD:add fix null pointer SLLEL-1705 by jinxian.lei 20220815 end
```

**示例（C/C++ BSP）**：
```c
//BSP: add support fingerprint FSHSJB-812 by chao.liu2 20180606 start
tran_fingerprint_init();
//BSP: add support fingerprint FSHSJB-812 by chao.liu2 20180606 end
```

### 1.3 包裹块位置（常见违规）

| 违规 | 正确做法 |
|------|----------|
| 只写 start 无 end | 变更代码首尾必须成对 |
| 一个 start 包住多处不相关修改 | 每处逻辑独立一对 start/end |
| 注释写在代码行中间 | start 在变更前一行，end 在变更后一行 |
| 修改 AOSP 原生行但未包注释 | 凡改动原生行必须 modify + start/end |
| 中文/拼音原因 | 改为英文原因描述 |
| OS 库用部门简称而非 OS | OS 库统一 `// OS:...` |

---

## 2. 命名规范（必查）

### 2.1 C/C++

| 对象 | 规则 | 示例 |
|------|------|------|
| 宏 | `TRAN_` + 全大写下划线 | `TRAN_I2C_DRIVERID_BMA250` |
| 局部变量 | `tran_` + 小写下划线 | `tran_suspend_time` |
| 全局变量 | `g_tran_` + 小写下划线 | `g_tran_auxadc_solution` |
| 静态变量 | `tran_` + 小写下划线 | `tran_gsensor_init_flag` |
| 自定义符号 | 加 `tran_`/`TRAN_` 表明身份 | 禁止中文拼音、随意命名 |

### 2.2 Java/Kotlin

| 对象 | 规则 | 示例 |
|------|------|------|
| 成员变量 | `m` 前缀 + 驼峰 | `mDisplayNameView` |
| 静态变量 | `s` 前缀 + 驼峰 | `sTitle` |
| 常量 | 全大写下划线 | `MMS_TITLE_TAG` |
| 类/方法 | 驼峰 | `NoteBook`, `createText()` |
| 包名 | `com.transsion.*` 全小写 | 禁止 infinix/rlk/tecno/cyin/cy |
| 组件 | Activity/Service/Provider/Receiver 后缀 | `InCallUiActivity` |
| 工具类 | `Util`/`Manager` 后缀 | `LogUtil` |
| 基类/抽象类 | `Base`/`Abstract` 前缀 | `BaseActivity` |
| 宏/feature | `TRAN_*_SUPPORT` 或 `OS_*_SUPPORT` | `TRAN_DIRAC_SUPPORT` |
| SystemProperty | system:`ro.xxx_support`；vendor:`ro.vendor.xxx_support` | 全小写 |
| 资源(OS) | `os_<场景>_<类型>` | `os_btn_bg_blue.xml` |
| 资源(项目) | `tran_<场景>_<类型>` | `tran_contact_photo.png` |
| 字符串 name | OS:`os_*`；项目:`tran_*` | 见 overlay 规范 |
| Theme/Style | `OS.*` 或 `Tran.*` | `OS.Theme.Material.Light` |

---

## 3. AOSP 修改规范（必查）

### 3.1 修改方式决策树

```
改动目标在 frameworks/ 或 mediatek/ 等 AOSP 路径？
├─ 仅资源/字符串/颜色/dimens？ → overlay（禁止直接改原生英文字符串文件）
├─ 新增 Framework 能力？ → vendor/tran_os/framework/.../com/transsion/FEATURE
│                          跨 package 编译问题 → 反射
├─ Settings 新增 KEY？ → OSSettingsExt / TranSettingsExt + defaults.xml overlay + OSProviderUtils
├─ 新增 APK 权限？ → system/etc/permissions/*-tran.xml（新建文件）
├─ init 启动项？ → device/transsion/ProjectXXX/init.project.rc（禁止 copy 整份 init.rc 到项目目录）
├─ C/C++ feature？ → TRAN_*_SUPPORT 宏 + ProjectConfig.mk 分区管理
└─ 必须改原生 .java/.cpp？ → 最小 diff + 规范注释包裹；评估升级 merge 风险
```

### 3.2 Overlay 路径

| 场景 | 路径 |
|------|------|
| OS 资源 | `vendor/tran_os/overlay/...` |
| 项目资源 | `device/tran/product/xxx/ProductConfig/vendor/prjconfig/overlay/...` |
| 字符串 | OS 新建 `os_*.xml`；项目新建 `tran_string.xml` |

**硬规则**：frameworks 下原生英文字符串文件 **不得修改**；dts 射频/音频/Camera 参数用原始参数。

### 3.3 Feature 宏组织（C/C++ & 项目）

- 格式：`TRAN_<器件/功能>_SUPPORT`，放 `ProjectConfig.mk`
- 按部门分区：
```
########## BSP start ##########
TRAN_BSP_TP_SUPPORT = yes
########## BSP end ##########
```

---

## 4. AOSP 流程风险检查（必查）

对每处 AOSP 相关改动，识别子系统并按 [AOSP_RISK_MATRIX.md](AOSP_RISK_MATRIX.md) 检查。至少回答：

1. **改了哪条原生调用链？**（如 Activity 启动、Broadcast、Binder、Settings、Power、Audio、Telephony）
2. **修改方式是否合规？**（overlay/vendor/反射 vs 直接改原生）
3. **升级合入风险？**（注释块是否增加 merge 冲突面）
4. **运行时风险？**（生命周期、线程、权限、SELinux、空指针、越界、魔法值）
5. **是否影响其他模块？**（需知会责任人）

### 4.1 高频风险速查

| 场景 | 风险 | 审核要点 |
|------|------|----------|
| 改 frameworks 原生类 | 升级冲突、CTS | 能否下沉 vendor/tran_os；必须改则最小 diff + 注释 |
| 主线程耗时 | ANR | 检查 Handler/IO/网络是否在主线程 |
| 字符串硬编码/自翻译 | 国际化/合规 | 走 string 资源 + overlay |
| 删原生 code | 合入/认证 | **禁止**；只能注释或 overlay |
| init.rc 整文件 copy | 启动顺序混乱 | 改 `init.project.rc` |
| 权限 XML 末尾注释 | 编译失败 | `.te` 仅行首注释，末尾无空行 |
| Log 滥用 error 级别 | 误判故障 | 正常路径不用 `Log.e`/pr_err |
| 高频 Log | 性能 | 宏控制；量产关闭 DEBUG |
| 隐私数据 Log | 合规 | IMEI/IMSI/位置等禁止打印 |
| 反射调隐藏 API | 版本碎片化 | 加版本判断 + 降级 |
| Settings 直写 | 多用户/权限 | 走 Ext + ProviderUtils |
| 新增自启/常驻 | 功耗/政策 | 需 TL 报备 |
| switch 无 default | 漏处理 | 强制 default 分支 |

---

## 5. 其他必查项（精简）

### C/C++
- `if/for/while` 必须带 `{}`；`if (` 后有空格
- Kernel TAB 缩进；HAL/native 4 空格
- 指针判空；`free` 后置 `NULL`；`if (NULL == ptr)`
- 优先动态 log（`dev_dbg`/`pr_debug` + `CONFIG_DYNAMIC_DEBUG`）
- feature 分层分离，参考 LCM driver 结构体模式

### Java
- 空指针/数组越界/除零保护；`switch` 有 `default`
- `Integer.parseInt` 等需 `NumberFormatException` 保护
- 第三方库版本号固定，禁止 `+`
- 方法建议 <40 行；UI 方法加 `@UiThread` 等注解
- 禁止魔法值；兼容机型 checklist

---

## 6. 审核报告模板

```markdown
# 编码规范审核报告

## 概览
- **审核范围**：{文件/commit/PR 描述}
- **语言/层级**：{Java | C/C++ kernel | HAL | ...}
- **总体结论**：✅ 通过 | ⚠️ 有条件通过 | ❌ 不通过
- **问题统计**：🔴 {n} | 🟡 {n} | 🟢 {n}

## 问题清单

### 🔴 必须修改
#### [{文件}:{行号}] {问题标题}
- **类别**：注释 | 命名 | AOSP修改方式 | 流程风险 | 安全
- **规范依据**：{M.RD-223 x.x / Java规范 x}
- **现状**：{代码片段或描述}
- **风险**：{若不修改的后果，关联 AOSP 流程}
- **修改建议**：
  ```{lang}
  {给出修改后的代码或步骤}
  ```

### 🟡 建议修改
（同上格式）

### 🟢 可选优化
（同上格式）

## AOSP 流程风险评估
| 子系统 | 变更点 | 调用链影响 | 修改方式合规 | 风险等级 | 建议 |
|--------|--------|------------|--------------|----------|------|
| {Telephony/Settings/...} | {简述} | {上下游} | ✅/❌ | 高/中/低 | {措施} |

## 合规项（简要）
- {已符合的要点，便于作者确认}
```

### 严重级别

| 级别 | 含义 |
|------|------|
| 🔴 | 违反硬规范或存在高运行时/合入/合规风险 |
| 🟡 | 不符合推荐实践或中等风险 |
| 🟢 | 风格/可读性优化 |

---

## 7. 执行要点

1. **先读上下文**：同文件已有注释风格、命名前缀、括号风格应对齐原生/周边 code
2. **按变更块审核**：每个 start/end 块独立评估
3. **AOSP 改动必须追溯流程**：不确定调用链时，搜索同模块原生实现或查 OpenGrok（`harness-opengrok`）
4. **建议要可执行**：给出完整注释行、正确命名、推荐路径（overlay/vendor），不只说"不规范"
5. **不臆造 bug_id**：缺失则标注"需补 JIRA 单号"

## 参考

- 完整风险矩阵与子系统检查项：[AOSP_RISK_MATRIX.md](AOSP_RISK_MATRIX.md)
- 源文档：M.RD-223 C/C++ V1.4；Java编码规范-雷锦先
