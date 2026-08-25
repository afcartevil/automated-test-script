import { describe, expect, it } from 'vitest'
import {
  buildJiraCommentSections,
  joinSelectedSnippets,
  toggleJiraCommentSection,
} from '../../packages/client/src/utils/jira-comment-sections'

const REPORT = `### 1. 摘要 / TL;DR

飞行模式下紧急号码拨号失败。

### 4. 根因定位（最关键）

ECC 配置未覆盖当地号码段。

### 9. Jira 备注（结论 / 依据 / 建议）

【分析结论】
飞行模式下马里新紧急号码拨号失败。

【结论依据】
1. ecc_db.xml 未包含马里紧急号码段

【建议】
1. 更新 ecc_db.xml
`

describe('jira comment section picker', () => {
  it('defaults 根因定位 and Jira 备注 as selected and uses §9 assembled text', () => {
    const sections = buildJiraCommentSections(REPORT)
    expect(sections.map(s => s.title)).toEqual([
      '摘要 / TL;DR',
      '根因定位（最关键）',
      'Jira 备注（结论 / 依据 / 建议）',
    ])
    const selected = sections.filter(s => s.defaultSelected)
    expect(selected.map(s => s.title)).toEqual([
      '根因定位（最关键）',
      'Jira 备注（结论 / 依据 / 建议）',
    ])
    const remark = selected.find(s => s.title.includes('Jira 备注'))!
    expect(remark.snippet).toContain('*分析结论：*')
    expect(remark.snippet).toContain('飞行模式下马里新紧急号码拨号失败')
    const joined = joinSelectedSnippets(sections, selected.map(s => s.id))
    expect(joined).toContain('ECC 配置未覆盖当地号码段')
    expect(joined).toContain('*分析结论：*')
  })

  it('appends a section after the default preview and removes it on uncheck', () => {
    const sections = buildJiraCommentSections(REPORT)
    const selected = sections.filter(s => s.defaultSelected)
    const defaultPreview = joinSelectedSnippets(sections, selected.map(s => s.id))
    const summary = sections.find(s => s.title.includes('摘要'))!
    const checked = toggleJiraCommentSection({
      preview: defaultPreview,
      snippet: summary.snippet,
      selected: true,
    })
    expect(checked.preview.startsWith(defaultPreview)).toBe(true)
    expect(checked.preview).toContain('飞行模式下紧急号码拨号失败')

    const unchecked = toggleJiraCommentSection({
      preview: checked.preview,
      snippet: summary.snippet,
      selected: false,
      inserted: checked.inserted,
    })
    expect(unchecked.preview).toBe(defaultPreview)
  })

  it('keeps user-edited preview when the inserted snippet no longer matches', () => {
    const edited = '*分析结论：*\n用户改过的结论'
    const result = toggleJiraCommentSection({
      preview: edited,
      snippet: '*分析结论：*\n原始结论',
      selected: false,
      inserted: '*分析结论：*\n原始结论',
    })
    expect(result.preview).toBe(edited)
  })

  it('uses assembled §9 text including suggestions from inner-fenced evidence', () => {
    const report = `### 9. Jira 备注（结论 / 依据 / 建议）

【分析结论】
kernel panic。

【结论依据】
1. Call trace:
\`\`\`
dump_backtrace+0xf4/0x118
\`\`\`

【建议】
1. 核对 watchdog 喂狗路径
`
    const sections = buildJiraCommentSections(report)
    const remark = sections.find(s => s.defaultSelected)!
    expect(remark.snippet).toContain('核对 watchdog 喂狗路径')
    expect(remark.snippet).not.toContain('报告 §9 未填写建议')
  })
})
