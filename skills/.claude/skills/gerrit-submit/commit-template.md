# 研发代码提交规范（字段参考）

完整规范来源：[研发代码提交规范](https://transsioner.feishu.cn/wiki/VMclwfBRxi65BNks0dSc2aGynid)

## 模板正文

```text
ID:<AR_ID 或 BUG_ID>
DESCRIPTION:<清晰描述要解决的问题/需求>
TYPE:<见下方枚举>
AFFECT_PROJECTS:<影响范围>
TEST_SUGGESTIONS:<给测试的建议>
[是否自检]：是
[是否影响其它项目]:否
[是否影响其它平台]:否
[是否chery-pick其它分支]:否
```

前 5 行为公司拦截校验的核心字段；后 4 行为本 skill 要求的扩展信息。核心字段名与冒号后内容同一行、无 markdown；扩展行保持方括号标题，默认值如上（可按实际情况改为「是」并在 DESCRIPTION / TEST_SUGGESTIONS 中补充说明）。

## 字段规则

### ID（必填，用户提供）

- **只能**填 AR ID 或 BUG ID，**禁止** task ID。
- BUG ID：Jira 上有效 ID（状态非 Closed / Resolved），如 `TOS1501-63219`。
- AR ID：以需求管理系统为准，格式如 `AR-202506-002681`（见 https://alm.transsion.com/#/）。
- 不合规则会被 Gerrit/CI 拦截。
- 用户已要求提交时：**即使** Jira/AR 摘要与 diff 看起来无关，仍使用用户给出的 ID，不要停下来确认。

### DESCRIPTION

描述 **本次 diff 实际改动**，清晰明了。常用写法：新增 xx / 删除 xx / 修复 xx / 移植 xx。  
若单号业务描述与 diff 不一致，仍按 diff 写 DESCRIPTION（不要编造未改动的业务行为）。

### TYPE（必须是下列之一，否则拦截）

| 值 | 含义 |
|---|---|
| `func` | 新功能或新需求 |
| `fix` | Bug 修复 |
| `opti` | 性能/功能优化 |
| `port` | 代码移植 |
| `refactor` | 代码重构 |
| `revert` | 代码回退 |
| `patch` | 补丁；DESCRIPTION 必须说清解决了什么问题或实现了什么功能 |
| `apm` | 仅监控打点、异常日志处理 |
| `conf` | 仅配置变化（开关宏、properties 等） |
| `test` | 单测和自动化 case |
| `NativeInssue` | 解决 Android/芯片厂原生问题（注意拼写，规范原文如此） |

不要用 `perf` 等未列出的别名（规范样例里偶有笔误，以本表为准）。

### AFFECT_PROJECTS

影响范围，三种写法之一：

1. `ALL` — 影响所有项目（可注明 tOS 版本）
2. 平台：`D7300,G99`（逗号分隔）
3. 项目：`X658B,KF6,KF6m`（逗号分隔）

与 TYPE 联合使用，供测试与项目管理评估影响面。  
用户已要求提交且无法精确推断时：优先用路径/仓名/Jira 项目 key，再不行填 `ALL`，不要停问。

### TEST_SUGGESTIONS

给测试的建议；DevOps 流水线会拉取该字段辅助制定测试策略。写可执行的检查点，不要空泛写「自测通过」。

### 扩展信息（后 4 行）

| 行 | 默认 | 填写说明 |
|---|---|---|
| `[是否自检]：` | `是` | 已自测填「是」；未自测填「否」，并在 TEST_SUGGESTIONS 说明风险 |
| `[是否影响其它项目]:` | `否` | 跨项目影响填「是」，并与 AFFECT_PROJECTS 一致 |
| `[是否影响其它平台]:` | `否` | 跨平台（如 MTK/QCOM/SPRD）影响填「是」 |
| `[是否chery-pick其它分支]:` | `否` | 需要/已经 cherry-pick 到其它分支填「是」（标题拼写按模板原文 `chery-pick`） |

用户未特别说明时用默认值；目标分支有多个且本次会向多分支 upload 时，将 `[是否chery-pick其它分支]` 设为 `是`。

## 规范样例

### 示例 1：BUG 修复

```text
ID:TOS1501-63219
DESCRIPTION:修复无网络下影音娱乐二级列表页变声缩略图一直加载中
TYPE:fix
AFFECT_PROJECTS:X6853
TEST_SUGGESTIONS:1、涉及无网络加载下二级列表页有没有一直加载中情况 2、无网络切有网络和有网络切无网络情况下是否会存在一直加载中情况
[是否自检]：是
[是否影响其它项目]:否
[是否影响其它平台]:否
[是否chery-pick其它分支]:否
```

### 示例 2：优化（TYPE 用 opti，不用 perf）

```text
ID:AR-SA-0014-001-002
DESCRIPTION:优化获取验证码时间间隔从100s变为60s
TYPE:opti
AFFECT_PROJECTS:tOS15.1.0所有项目
TEST_SUGGESTIONS:1、测试获取时间间隔60秒后再输入验证码能否验证 2、测试倒计时接近60s秒验证情况
[是否自检]：是
[是否影响其它项目]:是
[是否影响其它平台]:否
[是否chery-pick其它分支]:否
```

## 渲染方式

按本文件模板**直接拼接** commit message，不要调用 `harness gerrit commit-message`（其扩展字段与本 skill 不一致）。
