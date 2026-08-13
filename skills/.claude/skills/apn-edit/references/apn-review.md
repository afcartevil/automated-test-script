# APN Review 流程

修改 APN 后、提交 Gerrit 前，**必须**按仓库根目录 `.agent/test-suggestion.md` 逐条 review。

## 执行步骤

1. **读取规则**：完整阅读 `.agent/test-suggestion.md`（规则会随项目更新，禁止凭记忆检查）
2. **对照 diff**：针对本次 `git diff` 涉及的全部文件与 APN 条目，逐条应用规则
3. **输出 review 报告**（格式见 test-suggestion.md 文末表格）
4. **处置**：
   - 全部 **通过** → 可进入 `gerrit-submit`
   - 任一 **不通过** → 修正 XML 后重新从 Step 3 验证并再次 review

## 与 schema 的关系

- 字段含义、文件范围：以 `apn-schema.md` 为准
- 归档/业务合规：以 `.agent/test-suggestion.md` 为准（review 规则 SSOT）

## 各规则检查要点

### 规则 1：补充业务参数默认隐藏

- 在 diff 中查找 `type` 含 `ims`、`xcap`，或 `type="emergency"` / carrier 为 `SOS` / `SOS(wifi)` 的条目
- 确认存在 `user_visible="false"`
- 需求明确要求可见时，在「说明」列引用需求原文

### 规则 2：同 PLMN + 同 APN 不重复

- 对 diff 涉及的每个文件，按 `mcc`+`mnc`+`apn` 全文件检索
- 同一组合出现多组且无 `mvno_type`/`mvno_match_data` 区分 → 不通过
- 新增条目前须确认不与已有条目冲突

### 规则 3：协议禁止 IPV4

- 在 diff 中检索 `protocol="IPV4"` 或 `roaming_protocol="IPV4"`
- 应改为 `IP`，或按归档要求使用 `IPV4V6` / `IPV6` 等合法值
- 不得新增或保留 `IPV4` 字面量

### 规则 4：全文件搜索后修改

- 确认修改前已对目标 `mcc`+`mnc` 做过全文件 grep，而非仅读插入点上下文
- review 报告「说明」列简述搜索命令与命中条目数
- 若同一 PLMN 有多处条目，确认本次变更已覆盖所有应改位置
