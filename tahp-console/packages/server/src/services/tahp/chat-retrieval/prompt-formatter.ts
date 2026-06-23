import type { RetrievalBundle } from './types'
import { TAHP_SKILLS_REL_ROOT } from './skill-ranker'

export function formatRetrievalPrompt(bundle: RetrievalBundle): string {
  const lines: string[] = [
    '# TAHP 对话 — 预检索结果',
    '',
    `**检索策略**: ${bundle.strategy_label}（intent: \`${bundle.intent}\`，耗时 ${bundle.latency_ms}ms）`,
    '',
    '## 行为约束',
    ...bundle.directives.map(d => `- ${d}`),
    '',
  ]

  if (bundle.kb_hits.length > 0) {
    lines.push(`## 知识库命中（${bundle.kb_hits.length} 条，请优先引用）`)
    for (const hit of bundle.kb_hits) {
      lines.push(`### ${hit.title}（${hit.id}，相关度 ${hit.relevance}%，${hit.source_type}）`)
      if (hit.jira_key) lines.push(`- JIRA: ${hit.jira_key}`)
      lines.push(`- 模块: ${hit.module} / ${hit.func_type} / 状态: ${hit.status}`)
      lines.push(`- 摘要: ${hit.snippet}`)
      lines.push(`- 路径: \`${hit.path}\``)
      lines.push('')
    }
  }

  if (bundle.skill_hits.length > 0) {
    lines.push(`## 相关 Skill（${bundle.skill_hits.length} 个）`)
    lines.push(`> Skill 根目录: \`${TAHP_SKILLS_REL_ROOT}\``)
    for (const sk of bundle.skill_hits) {
      lines.push(`### ${sk.skill_id}（相关度 ${sk.relevance}%）`)
      lines.push(`- ${sk.description}`)
      lines.push(`- 路径: \`${sk.path}\``)
      if (sk.excerpt) {
        lines.push('')
        lines.push(sk.excerpt)
      }
      lines.push('')
    }
  }

  if (bundle.lark_hits.length > 0) {
    lines.push(`## 飞书文档（${bundle.lark_hits.length} 篇）`)
    for (const doc of bundle.lark_hits) {
      lines.push(`### ${doc.title}`)
      if (doc.url) lines.push(`- 链接: ${doc.url}`)
      lines.push(`- 节选: ${doc.excerpt}`)
      lines.push('')
    }
  }

  if (bundle.kb_hits.length === 0 && bundle.skill_hits.length === 0 && bundle.lark_hits.length === 0) {
    lines.push('## 检索结果')
    lines.push('当前策略下未命中预索引内容；请基于用户问题谨慎作答，并建议用户提供更具体关键词或切换检索模式。')
    lines.push('')
  }

  if (bundle.catalog_mode) {
    lines.push('## 答复格式（必须遵守）')
    lines.push('- **仅**输出 Markdown 表格：`JIRA | 标题/现象 | 一句话结论`')
    lines.push('- 一行一条预检索案例；结论来自上方「知识库命中」摘要，勿编造')
    lines.push('- **禁止**输出 Skill 清单、分析 SOP、或「需要我加载 Skill 吗」类结尾')
    lines.push('')
  }

  return lines.join('\n')
}
