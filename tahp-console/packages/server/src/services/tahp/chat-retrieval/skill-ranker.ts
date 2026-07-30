import { existsSync, readFileSync, readdirSync } from 'fs'
import { join } from 'path'
import yaml from 'js-yaml'
import { tahpPaths } from '../paths'
import { TAHP_SKILLS_REL_ROOT, tahpSkillMdRelativePath } from '../context-injector'
import { tokenize } from '../kb-search/bm25'
import type { SkillHit } from './types'
import { isOfficialHarnessSkillId } from '../harness-host-skills'

const DOMAIN_ROUTERS: Array<{ patterns: RegExp[]; skillId: string }> = [
  { patterns: [/通信|modem|vowifi|vozwifi|sim|rat|telephony/i], skillId: 'com-comm-analysis-foundation' },
  { patterns: [/mtk|充电|器件|adapt/i], skillId: 'mtk-adapt-template-router' },
  { patterns: [/编码规范|code review|standards/i], skillId: 'transsion-coding-standards-review' },
]

function parseFrontmatter(raw: string): { data: Record<string, unknown>; content: string } {
  const match = raw.match(/^---\s*\n([\s\S]*?)\n---\s*\n([\s\S]*)$/)
  if (!match) return { data: {}, content: raw }
  try {
    return { data: (yaml.load(match[1]) as Record<string, unknown>) || {}, content: match[2] }
  } catch {
    return { data: {}, content: raw }
  }
}

function extractSection(content: string, headings: string[], maxLen = 1200): string {
  for (const h of headings) {
    const re = new RegExp(`##\\s*${h}[\\s\\S]*?(?=\\n##|$)`, 'i')
    const m = content.match(re)
    if (m) return m[0].slice(0, maxLen)
  }
  return content.slice(0, maxLen)
}

interface SkillIndexItem {
  skill_id: string
  description: string
  keywords: string[]
  body: string
}

let _skills: SkillIndexItem[] | null = null

function loadSkills(): SkillIndexItem[] {
  if (_skills) return _skills
  const skillsDir = join(tahpPaths.projectRoot, 'skills', '.claude', 'skills')
  const items: SkillIndexItem[] = []
  if (!existsSync(skillsDir)) {
    _skills = items
    return items
  }
  for (const name of readdirSync(skillsDir)) {
    if (isOfficialHarnessSkillId(name)) continue
    const md = join(skillsDir, name, 'SKILL.md')
    if (!existsSync(md)) continue
    try {
      const raw = readFileSync(md, 'utf-8')
      const { data, content } = parseFrontmatter(raw)
      const description = String(data?.description || name)
      const triggerMatch = content.match(/##\s*触发条件\s*\n([\s\S]*?)(?=\n##|$)/)
      const trigger = triggerMatch?.[1]?.trim() || ''
      items.push({
        skill_id: name,
        description,
        keywords: [...tokenize(name), ...tokenize(description), ...tokenize(trigger)],
        body: content,
      })
    } catch { /* skip */ }
  }
  _skills = items
  return items
}

export function rankSkills(query: string, options?: {
  limit?: number
  preferred_skill_ids?: string[]
  include_excerpt?: boolean
}): SkillHit[] {
  const limit = options?.limit ?? 3
  const qTokens = new Set(tokenize(query))
  const preferred = new Set(options?.preferred_skill_ids || [])
  const hits: SkillHit[] = []

  for (const router of DOMAIN_ROUTERS) {
    if (router.patterns.some(p => p.test(query)) && !hits.some(h => h.skill_id === router.skillId)) {
      const sk = loadSkills().find(s => s.skill_id === router.skillId)
      if (sk) {
        hits.push({
          skill_id: sk.skill_id,
          description: sk.description,
          path: tahpSkillMdRelativePath(sk.skill_id),
          relevance: 90,
          excerpt: options?.include_excerpt
            ? extractSection(sk.body, ['触发条件', '分析步骤', 'SOP', 'Procedure'])
            : undefined,
        })
      }
    }
  }

  for (const sk of loadSkills()) {
    if (preferred.has(sk.skill_id)) {
      hits.push({
        skill_id: sk.skill_id,
        description: sk.description,
        path: tahpSkillMdRelativePath(sk.skill_id),
        relevance: 100,
        excerpt: options?.include_excerpt
          ? extractSection(sk.body, ['触发条件', '分析步骤', 'SOP'])
          : undefined,
      })
      continue
    }
    let overlap = 0
    for (const t of qTokens) {
      if (sk.keywords.some(k => k.includes(t) || t.includes(k))) overlap++
    }
    const score = qTokens.size ? (overlap / qTokens.size) * 80 : 0
    if (score > 5) {
      hits.push({
        skill_id: sk.skill_id,
        description: sk.description,
        path: tahpSkillMdRelativePath(sk.skill_id),
        relevance: Math.round(score),
        excerpt: options?.include_excerpt && score > 20
          ? extractSection(sk.body, ['触发条件', '分析步骤', 'SOP'])
          : undefined,
      })
    }
  }

  hits.sort((a, b) => b.relevance - a.relevance)
  const seen = new Set<string>()
  const out: SkillHit[] = []
  for (const h of hits) {
    if (seen.has(h.skill_id)) continue
    seen.add(h.skill_id)
    out.push(h)
    if (out.length >= limit) break
  }
  return out
}

export function invalidateSkillRankerCache(): void {
  _skills = null
}

export { TAHP_SKILLS_REL_ROOT }
