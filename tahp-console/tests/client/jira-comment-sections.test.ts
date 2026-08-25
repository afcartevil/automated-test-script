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
  it('defaults only Jira 备注 as selected and uses §9 assembled text', () => {
    const sections = buildJiraCommentSections(REPORT)
    expect(sections.map(s => s.title)).toEqual([
      '摘要 / TL;DR',
      '根因定位（最关键）',
      'Jira 备注（结论 / 依据 / 建议）',
    ])
    const selected = sections.filter(s => s.defaultSelected)
    expect(selected).toHaveLength(1)
    expect(selected[0].title).toMatch(/Jira 备注/)
    expect(selected[0].snippet).toContain('*分析结论：*')
    expect(selected[0].snippet).toContain('飞行模式下马里新紧急号码拨号失败')
    expect(joinSelectedSnippets(sections, selected.map(s => s.id))).toBe(selected[0].snippet)
  })

  it('appends a section after the default preview and removes it on uncheck', () => {
    const sections = buildJiraCommentSections(REPORT)
    const remark = sections.find(s => s.defaultSelected)!
    const summary = sections.find(s => s.title.includes('摘要'))!
    let preview = remark.snippet
    const checked = toggleJiraCommentSection({
      preview,
      snippet: summary.snippet,
      selected: true,
    })
    preview = checked.preview
    expect(preview.startsWith(remark.snippet)).toBe(true)
    expect(preview).toContain('飞行模式下紧急号码拨号失败')

    const unchecked = toggleJiraCommentSection({
      preview,
      snippet: summary.snippet,
      selected: false,
      inserted: checked.inserted,
    })
    expect(unchecked.preview).toBe(remark.snippet)
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
})
