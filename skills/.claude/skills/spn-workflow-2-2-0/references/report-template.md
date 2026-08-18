# SPN 分析与修改报告模板

```markdown
## SPN 故障分析 — <JIRA_KEY>（<PLATFORM>）

### 结论
<一句话说明根因、责任层和是否需要改码>

### Jira 与环境
- Summary：
- 问题版本：
- 项目/平台：
- 国家/运营商：
- SIM MCCMNC：
- 注册 MCCMNC：
- 卡类型/卡槽：
- 复现场景：

### 平台判定
- 证据 1：<path:time/tag>
- 证据 2：<property/class>

### 时间线
1. <time> SIM state/subId
2. <time> EF_SPN/SIM numeric
3. <time> 注册 PLMN/NITZ/EONS
4. <time> Telephony lookup/broadcast
5. <time> SystemUI/displayName

### 日志证据
- <path + line/time + original value>
- <path + line/time + original value>
- <path + line/time + original value>

### 链路断点
<class.method: input → actual output → expected output>

### 根因
- 结论：
- 置信度：已证实 / 高概率 / 待确认
- 排除项：

### 修复设计
- Repo：
- File/function：
- 修改：
- 为什么能解决：
- 回归风险：

### Diff
- Repo 1：<stat + files>
- Repo 2：<stat + files>

### 验证
- [ ] 原场景
- [ ] 同运营商其他 SIM
- [ ] 实际驻网运营商 SIM
- [ ] 单卡/双卡与热插拔
- [ ] 自动驻网/手动搜网
- [ ] 状态栏/锁屏/通知栏/displayName
- [ ] 模块编译

### 分支解析
- Jira version：
- Project/partition：
- Workspace revision：
- Target Gerrit branch：
- Resolution：matched / ambiguous / mismatch

### 提交结果
- Commit：
- Gerrit CR：
- 未执行项：

### 看板上报
- ANALYZED record：`event_id=` / upload status=
- SUBMITTED record（如有）：`event_id=` / upload status=
```

## 表述要求

- 先写结论，再写证据。
- 不把推断写成事实。
- 不用“应该、可能”替代缺失证据；明确列为待确认。
- ANALYZED 报告交付前必须完成看板 `record`（见 [dashboard.md](dashboard.md)）。
- 时间线至少覆盖错误值首次出现和正确值最终出现。
- 修复设计必须精确到 repo、文件和函数。
- 没有真实 diff、编译或 CR 时不得使用“已完成”。
