import { describe, expect, it } from 'vitest'
import { parseAdaptAuditSummary } from '../../packages/server/src/services/tahp/adapt-audit-summary'

const PASS_AUDIT = `## Skill 遵从性自检

**结论**: ✅ 完全遵从，无跳步，无编造路径。

# 编码规范审核报告

## 概览

- **总体结论**：✅ 通过 — 纯文本文件，不涉及源码规范
- **问题统计**：🔴 0 | 🟡 0 | 🟢 0

## AOSP 流程风险评估

| 子系统 | 变更点 | 调用链影响 | 修改方式合规 | 风险等级 | 建议 |
|--------|--------|------------|--------------|----------|------|
| N/A | 纯文本测试报告 | 无 | ✅ N/A | 无 | N/A |
`

const CHECKLIST_AUDIT = `## Skill 遵从性自检

| 自检项 | 结果 | 说明 |
|--------|------|------|
| 是否 Read 主控 Skill 全文？ | ✅ | 已加载 |
| 是否按 SOP 顺序执行？ | ✅ | 已完成 |

# 编码规范审核报告

## 概览

- **总体结论**：✅ 通过 — 无代码变更
- **问题统计**：🔴 0 | 🟡 0 | 🟢 0

## AOSP 流程风险评估

| 子系统 | 变更点 | 调用链影响 | 修改方式合规 | 风险等级 | 建议 |
|--------|--------|------------|--------------|----------|------|
| 无 | 无 AOSP 代码改动 | 无 | ✅ N/A | 低 | 无需评估 |
`

const OVERVIEW_AUDIT = `## 审核结果概览

| 检查环节 | 结果 | 说明 |
|----------|------|------|
| Skill 遵从性自检 | PASS | 全部 SOP 已执行 |
| 编码规范审核报告 | PASS | 无源码变更 |
| AOSP 流程风险评估 | N/A | 无 AOSP 改动 |

## Skill 遵从性自检
...
`

describe('parseAdaptAuditSummary', () => {
  it('parses pass scenario with conclusion line', () => {
    const items = parseAdaptAuditSummary(PASS_AUDIT)
    expect(items[0]).toMatchObject({ label: 'Skill 遵从性自检', status: 'pass' })
    expect(items[1].status).toBe('pass')
    expect(items[2].status).toBe('pass')
  })

  it('parses checklist table without conclusion line', () => {
    const items = parseAdaptAuditSummary(CHECKLIST_AUDIT)
    expect(items[0].status).toBe('pass')
    expect(items[0].reason).toContain('全部通过')
    expect(items[1].status).toBe('pass')
    expect(items[2].status).toBe('pass')
  })

  it('prefers fixed overview table when present', () => {
    const items = parseAdaptAuditSummary(OVERVIEW_AUDIT)
    expect(items).toHaveLength(3)
    expect(items[0]).toMatchObject({ status: 'pass', reason: '全部 SOP 已执行' })
    expect(items[2].status).toBe('na')
  })
})
