/**
 * 从 adapt-agent 自检审核 Markdown 中解析各环节 PASS/FAIL 摘要。
 * 优先解析 Agent 输出的「审核结果概览」固定表，其次启发式解析。
 */

export type AuditCheckStatus = 'pass' | 'fail' | 'warn' | 'na' | 'unknown'

export interface AuditCheckItem {
  key: string
  label: string
  status: AuditCheckStatus
  reason: string
}

export const AUDIT_STATUS_LABEL: Record<AuditCheckStatus, string> = {
  pass: 'PASS',
  fail: 'FAIL',
  warn: 'WARN',
  na: 'N/A',
  unknown: 'UNKNOWN',
}

const OVERVIEW_LABEL_KEYS: Record<string, { key: string; label: string }> = {
  'skill 遵从性自检': { key: 'skill_compliance', label: 'Skill 遵从性自检' },
  '编码规范审核报告': { key: 'coding_standards', label: '编码规范审核报告' },
  'aosp 流程风险评估': { key: 'aosp_risk', label: 'AOSP 流程风险评估' },
}

function clip(text: string, max = 140): string {
  const s = text.replace(/\s+/g, ' ').trim()
  return s.length <= max ? s : `${s.slice(0, max)}…`
}

function parseStatusToken(token: string): AuditCheckStatus {
  const t = token.toUpperCase().replace(/\s+/g, '')
  if (t.includes('FAIL') || t.includes('不通过')) return 'fail'
  if (t.includes('WARN') || t.includes('有条件')) return 'warn'
  if (t === 'N/A' || t === 'NA' || t.includes('不适用')) return 'na'
  if (t.includes('PASS') || t.includes('通过')) return 'pass'
  return 'unknown'
}

/** 解析 Agent 按提示词输出的固定概览表（优先） */
function parseAuditOverviewTable(text: string): AuditCheckItem[] | null {
  const section = text.match(/## 审核结果概览\s*\n+([\s\S]*?)(?=\n## [^审]|\n#\s|$)/)?.[1]
  if (!section) return null

  const rows = section
    .split('\n')
    .map(l => l.trim())
    .filter(l => l.startsWith('|') && !l.includes('---') && !/检查环节/.test(l))

  const items: AuditCheckItem[] = []
  for (const row of rows) {
    const cells = row.split('|').map(c => c.trim()).filter(Boolean)
    if (cells.length < 2) continue
    const meta = OVERVIEW_LABEL_KEYS[cells[0].toLowerCase()]
    if (!meta) continue
    const status = parseStatusToken(cells[1])
    const reason = clip(cells[2] || cells[1].replace(/PASS|FAIL|WARN|N\/A/gi, '').trim() || '-')
    items.push({ key: meta.key, label: meta.label, status, reason })
  }
  return items.length >= 2 ? items : null
}

function parseSkillCompliance(text: string): AuditCheckItem {
  const section = text.match(/## Skill 遵从性自检([\s\S]*?)(?=\n#\s*编码规范审核报告|\n---\n\n#|\n## 审核结果概览|\n---\s*\n\n\*\*全文|$)/)?.[1] || ''
  const conclusion = section.match(/\*\*结论\*\*[：:]\s*(.+)/)?.[1]?.trim() || ''

  if (conclusion) {
    if (/❌|不遵从|不通过|FAIL/i.test(conclusion)) {
      return { key: 'skill_compliance', label: 'Skill 遵从性自检', status: 'fail', reason: clip(conclusion) }
    }
    if (/⚠️|部分|WARN/i.test(conclusion)) {
      return { key: 'skill_compliance', label: 'Skill 遵从性自检', status: 'warn', reason: clip(conclusion) }
    }
    if (/✅|完全遵从|PASS|通过/i.test(conclusion)) {
      return { key: 'skill_compliance', label: 'Skill 遵从性自检', status: 'pass', reason: clip(conclusion.replace(/^✅\s*/, '')) }
    }
  }

  // 自检表格式（无 **结论** 行）
  if (section.includes('|') && /自检项|是否/.test(section)) {
    const rows = section.split('\n').filter(l => l.startsWith('|') && !l.includes('---') && !/自检项|^\|\s*[-—]/.test(l))
    let passCount = 0
    let failCount = 0
    for (const row of rows) {
      if (/❌|FAIL|不通过|未/.test(row) && !/✅/.test(row.split('|')[2] || '')) failCount++
      else if (/✅|PASS|通过/.test(row)) passCount++
    }
    if (failCount > 0) {
      return { key: 'skill_compliance', label: 'Skill 遵从性自检', status: 'fail', reason: `${failCount} 项自检未通过` }
    }
    if (passCount > 0) {
      return { key: 'skill_compliance', label: 'Skill 遵从性自检', status: 'pass', reason: `自检表 ${passCount} 项全部通过` }
    }
  }

  if (section.trim()) {
    return { key: 'skill_compliance', label: 'Skill 遵从性自检', status: 'unknown', reason: '未解析到结论或自检表' }
  }
  return { key: 'skill_compliance', label: 'Skill 遵从性自检', status: 'unknown', reason: '报告中无此章节' }
}

function parseCodingStandards(text: string): AuditCheckItem {
  const codingBlock = text.match(/#\s*编码规范审核报告([\s\S]*?)(?=\n---\s*\n\n\*\*全文|$)/)?.[1] || text
  const overview = codingBlock.match(/## 概览([\s\S]*?)(?=\n## |$)/)?.[1] || codingBlock
  const line = overview.match(/(?:[-*]\s*)?(?:\*\*)?总体结论(?:\*\*)?[：:]\s*(.+)/)?.[1]?.trim() || ''

  let status: AuditCheckStatus = 'unknown'
  if (/❌|不通过/i.test(line)) status = 'fail'
  else if (/⚠️|有条件通过/i.test(line)) status = 'warn'
  else if (/✅|通过/i.test(line)) status = 'pass'

  let reason = line
    .replace(/^✅\s*|^❌\s*|^⚠️\s*/, '')
    .replace(/^(通过|不通过|有条件通过)\s*[—–-]\s*/, '')
    .trim()

  const stats = overview.match(/问题统计[：:]\s*(.+)/)?.[1]?.trim()
  if (stats && status === 'pass') {
    reason = reason ? `${clip(reason, 100)}（${stats}）` : stats
  } else if (stats && status !== 'pass') {
    reason = reason ? `${clip(reason, 80)}（${stats}）` : stats
  }

  return {
    key: 'coding_standards',
    label: '编码规范审核报告',
    status,
    reason: clip(reason || line || '未找到总体结论'),
  }
}

function parseAospRisk(text: string): AuditCheckItem {
  const section = text.match(/## AOSP 流程风险评估([\s\S]*?)(?=## 合规项|## 问题清单|\n---\s*\n\n\*\*全文|$)/)?.[1] || ''
  const rows = section
    .split('\n')
    .map(l => l.trim())
    .filter(l => l.startsWith('|') && !l.includes('---') && !/^\|\s*子系统/.test(l))

  if (!rows.length) {
    return { key: 'aosp_risk', label: 'AOSP 流程风险评估', status: 'na', reason: '未生成风险评估表' }
  }

  const dataRows = rows.filter(r => {
    const first = r.split('|').map(c => c.trim()).filter(Boolean)[0] || ''
    return first && first !== 'N/A' && first !== '无'
  })

  if (!dataRows.length) {
    return { key: 'aosp_risk', label: 'AOSP 流程风险评估', status: 'pass', reason: '无 AOSP 源码变更，不适用' }
  }

  const reasons: string[] = []
  let worst: AuditCheckStatus = 'pass'

  for (const row of dataRows) {
    const cells = row.split('|').map(c => c.trim()).filter(Boolean)
    if (cells.length < 4) continue
    const [subsystem, changePoint, , compliance, riskLevel, suggestion] = cells
    const risk = riskLevel || ''
    const nonCompliant = /❌/.test(compliance || '')

    if (nonCompliant || /^高/.test(risk)) {
      worst = 'fail'
      reasons.push(`${subsystem}：${clip(changePoint || suggestion || '修改方式不合规', 60)}`)
    } else if (/中/.test(risk) && worst !== 'fail') {
      worst = 'warn'
      reasons.push(`${subsystem}：中等风险`)
    }
  }

  if (worst === 'pass') {
    const firstRow = dataRows[0].split('|').map(c => c.trim()).filter(Boolean)
    const risk = firstRow[4] || ''
    if (/低/.test(risk)) {
      return { key: 'aosp_risk', label: 'AOSP 流程风险评估', status: 'pass', reason: clip(firstRow[5] || '低风险，无 AOSP 合规问题') }
    }
    return { key: 'aosp_risk', label: 'AOSP 流程风险评估', status: 'pass', reason: '各子系统风险可控' }
  }

  return {
    key: 'aosp_risk',
    label: 'AOSP 流程风险评估',
    status: worst,
    reason: clip(reasons.slice(0, 2).join('；') || '存在需关注的风险项'),
  }
}

function parseHeuristicSummary(text: string): AuditCheckItem[] {
  return [
    parseSkillCompliance(text),
    parseCodingStandards(text),
    parseAospRisk(text),
  ]
}

/**
 * 解析自检审核 Markdown。
 * @param auditReport 审核章节正文
 * @param fullResponse 可选：完整 Agent 输出（用于查找顶部的「审核结果概览」）
 */
export function parseAdaptAuditSummary(auditReport: string, fullResponse?: string): AuditCheckItem[] {
  if (!auditReport?.trim() && !fullResponse?.trim()) return []

  const sources = [auditReport, fullResponse].filter(Boolean) as string[]
  for (const src of sources) {
    const overview = parseAuditOverviewTable(src)
    if (overview) return overview
  }

  const text = (auditReport || fullResponse || '').trim()
  return parseHeuristicSummary(text)
}
