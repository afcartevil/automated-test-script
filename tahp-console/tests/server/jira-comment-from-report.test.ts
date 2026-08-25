import { describe, it, expect } from 'vitest'
import {
  extractJiraCommentBlocks,
  hasJiraRemarkSection,
} from '../../packages/server/src/services/tahp/jira-comment-from-report'
import { composeJiraCommentFromReport } from '../../packages/server/src/services/tahp/compose-jira-comment'

const SECTION9_REPORT = `### 1. 摘要 / TL;DR

**问题**: 飞行模式下紧急号码拨号失败。

### 9. Jira 备注（结论 / 依据 / 建议）

【分析结论】
飞行模式下马里新紧急号码拨号失败，根因是 ECC 配置未覆盖当地号码段。

【结论依据】
1. ecc_db.xml 未包含马里 2024 版紧急号码段
2. RadioLog disconnect cause INVALID_NUMBER
   at com.android.phone.EccCallHelper.route(EccCallHelper.java:142)
   Caused by: android.telephony.DisconnectCause: INVALID_NUMBER

【建议】
1. 更新 ecc_db.xml 添加马里紧急号码
2. 回归验证飞行模式拨号
`

const SECTION9_H2_FENCED = `## 8. 风险与遗留问题

无

---

## 9. Jira 备注（结论 / 依据 / 建议）

\`\`\`
【分析结论】
LJ9 插入 Salam Mobile SIM 后 IMS 未启动，设置中号码为空。

【结论依据】
1. ImsProvisioningController: getTechsFromCarrierConfig failed
2. 全 radio_log 无任何 ImsRegistration 日志

【建议】
1. 补全 carrier_config.xml IMS 配置
\`\`\`
`

const SECTION9_H2_FENCED_TRAILING = `## 9. Jira 备注（结论 / 依据 / 建议）

\`\`\`
【分析结论】
test conclusion

【结论依据】
1. evidence one

【建议】
1. suggestion one
\`\`\`

---

\`\`\`

\`\`\`
`

describe('jira-comment-from-report', () => {
  it('extracts §9 with ## heading and code fence (agent real output)', () => {
    const blocks = extractJiraCommentBlocks(SECTION9_H2_FENCED)
    expect(blocks).not.toBeNull()
    expect(blocks!.conclusion).toContain('Salam Mobile')
    expect(blocks!.evidence).toHaveLength(2)
    expect(blocks!.suggestions[0]).toContain('carrier_config')
    expect(hasJiraRemarkSection(SECTION9_H2_FENCED)).toBe(true)
  })

  it('strips trailing fences and separators after §9 code block', () => {
    const blocks = extractJiraCommentBlocks(SECTION9_H2_FENCED_TRAILING)
    expect(blocks!.suggestions).toHaveLength(1)
    expect(blocks!.suggestions[0]).toBe('suggestion one')
    const out = composeJiraCommentFromReport(SECTION9_H2_FENCED_TRAILING)
    expect(out).not.toMatch(/`{3}/)
    expect(out).not.toMatch(/^[-─_]{3,}$/m)
    expect(out).not.toContain('|')
  })

  it('extracts three blocks from §9', () => {
    const blocks = extractJiraCommentBlocks(SECTION9_REPORT)
    expect(blocks).not.toBeNull()
    expect(blocks!.conclusion).toContain('ECC 配置未覆盖')
    expect(blocks!.evidence).toHaveLength(2)
    expect(blocks!.evidence[1]).toContain('Caused by')
    expect(blocks!.suggestions).toHaveLength(2)
  })

  it('detects §9 section', () => {
    expect(hasJiraRemarkSection(SECTION9_REPORT)).toBe(true)
    expect(hasJiraRemarkSection('### 1. 摘要\n\n无 Jira 节')).toBe(false)
  })

  it('returns null when §9 missing', () => {
    expect(extractJiraCommentBlocks('### 1. 摘要\n\n仅八节旧报告')).toBeNull()
  })
})

describe('composeJiraCommentFromReport', () => {
  it('assembles Jira wiki headers from §9 without trailing markdown junk', () => {
    const out = composeJiraCommentFromReport(SECTION9_REPORT)
    expect(out).toContain('*分析结论：*')
    expect(out).toMatch(/\*分析结论：\*\n飞行模式下马里新紧急号码拨号失败/)
    expect(out).toContain('*结论依据：*')
    expect(out).toContain('ecc_db.xml 未包含马里')
    expect(out).toContain('*建议：*')
    expect(out).toContain('更新 ecc_db.xml 添加马里紧急号码')
    expect(out).not.toContain('**')
  })

  it('parses §9 with ## heading and fenced body (regression fixture)', () => {
    const out = composeJiraCommentFromReport(SECTION9_H2_FENCED_TRAILING)
    expect(out).toContain('*分析结论：*')
    expect(out).toContain('test conclusion')
    expect(out).toContain('suggestion one')
    expect(out).not.toMatch(/`{3}/)
    expect(out).not.toMatch(/^[-─_]{3,}$/m)
  })

  it('does not drop 【建议】 when 结论依据 contains an inner code fence', () => {
    const report = `### 9. Jira 备注（结论 / 依据 / 建议）

【分析结论】
kernel panic 发生在 dump_backtrace。

【结论依据】
1. Call trace:
\`\`\`
[ 1.549149][ T1] Call trace:
[ 1.549152][ T1] dump_backtrace+0xf4/0x118
\`\`\`

【建议】
1. 核对 watchdog 喂狗路径
2. 补齐 last_kmsg 现场
`
    const blocks = extractJiraCommentBlocks(report)
    expect(blocks!.suggestions).toEqual(['核对 watchdog 喂狗路径', '补齐 last_kmsg 现场'])
    const out = composeJiraCommentFromReport(report)
    expect(out).not.toContain('报告 §9 未填写建议')
    expect(out).toContain('核对 watchdog 喂狗路径')
  })

  it('parses 建议： headers and 1、 numbering', () => {
    const report = `### 9. Jira 备注（结论 / 依据 / 建议）

分析结论：ECC 未覆盖当地号码。

结论依据：
1、ecc_db.xml 缺号段

建议：
1、补齐 ecc_db.xml
`
    const blocks = extractJiraCommentBlocks(report)
    expect(blocks!.conclusion).toContain('ECC 未覆盖')
    expect(blocks!.evidence[0]).toContain('ecc_db.xml')
    expect(blocks!.suggestions[0]).toContain('补齐 ecc_db.xml')
  })

  it('parses **建议** heading after bold stripping', () => {
    const report = `### 9. Jira 备注（结论 / 依据 / 建议）

**分析结论**
kernel panic。

**结论依据**
Call trace 指向 dump_backtrace。

**建议**
核对 watchdog 喂狗路径
`
    const blocks = extractJiraCommentBlocks(report)
    expect(blocks!.suggestions[0]).toContain('核对 watchdog 喂狗路径')
    const out = composeJiraCommentFromReport(report)
    expect(out).not.toContain('报告 §9 未填写建议')
  })

  it('falls back to §6 修复建议 when §9 建议 is empty', () => {
    const report = `### 6. 修复建议

1. 更新 ecc_db.xml 添加马里紧急号码

### 9. Jira 备注（结论 / 依据 / 建议）

【分析结论】
飞行模式拨号失败。

【结论依据】
1. RadioLog INVALID_NUMBER
`
    const blocks = extractJiraCommentBlocks(report)
    expect(blocks!.suggestions[0]).toContain('更新 ecc_db.xml')
    const out = composeJiraCommentFromReport(report)
    expect(out).not.toContain('报告 §9 未填写建议')
  })
})
