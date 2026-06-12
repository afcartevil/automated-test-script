/**
 * TAHP 工程上下文注入器
 *
 * 扫描工程的 skills / knowledge-base，
 * 根据用户输入做关键词匹配，返回注入到 LLM system prompt 的上下文字符串。
 * 让对话模式也能"看到"工程内容，无需 MCP 工具。
 */

import { existsSync, readFileSync, readdirSync } from 'fs'
import { join } from 'path'
import yaml from 'js-yaml'
import { tahpPaths, hasTahpProject } from './paths'
import { logger } from '../logger'

// ---------------------------------------------------------------------------
// 类型定义
// ---------------------------------------------------------------------------

interface ContextItem {
  type: 'skill' | 'knowledge'
  title: string
  summary: string
  keywords: string[]
}

/** buildTahpContext 可注入的章节（不含 Skill 正文，正文须运行时 Read） */
export interface BuildTahpContextOptions {
  includeSkillCatalog?: boolean
  includeKnowledge?: boolean
}

// ---------------------------------------------------------------------------
// 索引缓存（60s TTL，文件变更后自动刷新）
// ---------------------------------------------------------------------------

let _index: ContextItem[] | null = null
let _indexBuiltAt = 0
const INDEX_TTL_MS = 60_000

// ---------------------------------------------------------------------------
// 辅助函数
// ---------------------------------------------------------------------------

function safeReadDir(dir: string): string[] {
  try { return readdirSync(dir) } catch { return [] }
}

function parseFrontmatter(raw: string): { data: Record<string, unknown>; content: string } {
  const match = raw.match(/^---\s*\n([\s\S]*?)\n---\s*\n([\s\S]*)$/)
  if (!match) return { data: {}, content: raw }
  try {
    return { data: (yaml.load(match[1]) as Record<string, unknown>) || {}, content: match[2] }
  } catch {
    return { data: {}, content: raw }
  }
}

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .split(/[\s，,。？！；:\-\/\n\r\t]+/)
    .map(s => s.replace(/[()（）\[\]【】]/g, '').trim())
    .filter(s => s.length >= 2)
}

// ---------------------------------------------------------------------------
// 索引构建
// ---------------------------------------------------------------------------

function buildIndex(): ContextItem[] {
  const items: ContextItem[] = []

  // ── 1. Skills ─────────────────────────────────────────────────────────────
  const skillsDir = join(tahpPaths.projectRoot, 'skills', '.claude', 'skills')
  if (existsSync(skillsDir)) {
    for (const skillName of safeReadDir(skillsDir)) {
      const skillMdPath = join(skillsDir, skillName, 'SKILL.md')
      if (!existsSync(skillMdPath)) continue
      try {
        const raw = readFileSync(skillMdPath, 'utf-8')
        const { data: fm } = parseFrontmatter(raw)
        const description = String(fm?.description || skillName)
        // 提取"触发条件"章节关键词
        const triggerMatch = raw.match(/##\s*触发条件\s*\n([\s\S]*?)(?=\n##|$)/)
        const triggerLine = triggerMatch?.[1]?.trim() || ''
        const keywords = [
          ...tokenize(skillName),
          ...tokenize(String(fm?.module || '')),
          ...tokenize(description),
          ...tokenize(triggerLine),
        ]
        items.push({
          type: 'skill',
          title: `Skill: ${skillName}`,
          summary: description,
          keywords,
        })
      } catch (err) {
        logger.warn('[context-injector] skill parse error %s: %s', skillName, err)
      }
    }
  }

  // ── 2. 知识库 ──────────────────────────────────────────────────────────────
  const knowledgeDir = tahpPaths.knowledgeDir
  if (existsSync(knowledgeDir)) {
    for (const moduleName of safeReadDir(knowledgeDir)) {
      const indexPath = join(knowledgeDir, moduleName, 'index.yaml')
      if (!existsSync(indexPath)) continue
      try {
        const raw = readFileSync(indexPath, 'utf-8')
        const cfg = yaml.load(raw) as Record<string, any>
        const entries: any[] = cfg?.entries || []
        for (const entry of entries) {
          const title = String(entry.title || '')
          const tags: string[] = entry.tags || []
          items.push({
            type: 'knowledge',
            title: `知识库: ${title}`,
            summary: `[${moduleName}] ${title} (confidence: ${entry.confidence ?? '-'})`,
            keywords: [
              ...tokenize(moduleName),
              ...tokenize(title),
              ...tags.flatMap(t => tokenize(t)),
            ],
          })
        }
      } catch (err) {
        logger.warn('[context-injector] knowledge parse error %s: %s', moduleName, err)
      }
    }
  }

  return items
}

function getIndex(): ContextItem[] {
  const now = Date.now()
  if (!_index || now - _indexBuiltAt > INDEX_TTL_MS) {
    try {
      _index = buildIndex()
      _indexBuiltAt = now
      logger.info('[context-injector] 索引构建完成，共 %d 条目', _index.length)
    } catch (err) {
      logger.warn('[context-injector] 索引构建失败: %s', err)
      _index = []
    }
  }
  return _index
}

// ---------------------------------------------------------------------------
// Skill 路径与执行规范（Agent / LLM 系统提示词共用）
// ---------------------------------------------------------------------------

export type TahpSkillScenario = 'bug_analysis' | 'adapt_debug' | 'chat'

/** TAHP 仓内 Claude Skill 根目录：skills/.claude/skills */
export function getTahpSkillsRoot(): string {
  return join(tahpPaths.projectRoot, 'skills', '.claude', 'skills')
}

export function tahpSkillMdPath(skillId: string): string {
  return join(getTahpSkillsRoot(), skillId, 'SKILL.md')
}

/** 从用户消息 / 适配调试 handoff 草稿中解析优先 skill id */
export function extractPreferredSkillIds(text: string): string[] {
  const ids = new Set<string>()
  const patterns = [
    /\*\*关联\s*Skills\*\*:\s*([^\n]+)/gi,
    /关联\s*Skills[：:]\s*([^\n]+)/gi,
    /preferred\s*skills?[：:]\s*([^\n]+)/gi,
  ]
  for (const re of patterns) {
    re.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = re.exec(text)) !== null) {
      for (const part of m[1].split(/[,，、\s]+/)) {
        const id = part.trim().replace(/^[`'"]+|[`'"]+$/g, '')
        if (id && /^[\w][\w.-]*$/i.test(id)) ids.add(id)
      }
    }
  }
  return [...ids]
}

function inferSkillScenario(text: string): TahpSkillScenario {
  if (/jira\s*key|bug\s*分析|根因定位|8\s*节报告|tools_invoked|待分析\s*bug/i.test(text)) {
    return 'bug_analysis'
  }
  if (/适配调试|adapt[- ]?debug|前置条件|升级路径|bsp\s*适配|关联\s*skills/i.test(text)) {
    return 'adapt_debug'
  }
  return 'chat'
}

/**
 * Skill 按需加载的执行规范（注入 system prompt，指导 Agent Read SKILL.md）。
 */
export function buildSkillExecutionDirective(options?: {
  preferredSkillIds?: string[]
  scenario?: TahpSkillScenario
}): string {
  const skillsDir = getTahpSkillsRoot()
  const scenario = options?.scenario ?? 'chat'
  const lines: string[] = [
    '# TAHP Skill 执行规范（必读）',
    '',
    `工程内 Skill 根目录（唯一权威来源）: \`${skillsDir}\``,
    '每个 Skill 为 `<skillId>/SKILL.md`。**按需**选择 1～3 个相关 Skill，禁止编造不存在的 skillId。',
    '',
    '## 如何使用工程内 Skill',
    '1. 结合下方「已扫描到的 Skills」列表与用户问题，选定 skillId。',
    '2. **必须先 Read** 对应 `SKILL.md` 全文（或通过 Skill 工具加载），再严格按其中 SOP / 分析步骤执行。',
    '3. 通信问题域未明：先 Read `com-comm-analysis-foundation` 做路由，再选叶子 Skill。',
    '4. MTK 充电/器件适配：先 Read `mtk-adapt-template-router`，再下钻具体 adapt Skill。',
    '5. 须真实调用工具；完成后在回复中列出实际使用的 skill 与 MCP 工具名。',
    '',
  ]

  if (scenario === 'bug_analysis') {
    lines.push('**当前场景**: 智能诊断 — 拉取 JIRA 后必须选择并加载匹配的日志/领域分析 Skill。')
  } else if (scenario === 'adapt_debug') {
    lines.push('**当前场景**: AI 适配调试 — 优先加载用户指定的关联 Adapt Skill 并按 SOP 排查；全部完成后必须 Read `transsion-coding-standards-review` 并在报告末尾输出自检审核。')
  } else {
    lines.push('**当前场景**: TAHP 对话 — 按问题类型按需加载 Skill，不要一次性 Read 全部 Skill。')
  }
  lines.push('')

  const preferred = [...new Set((options?.preferredSkillIds ?? []).filter(Boolean))]
  if (preferred.length > 0) {
    lines.push('## 优先 Skill（须最先 Read 并遵循）')
    for (const id of preferred) {
      lines.push(`- **${id}**: \`${tahpSkillMdPath(id)}\``)
    }
    lines.push('')
  }

  return lines.join('\n')
}

function defaultContextOptions(scenario: TahpSkillScenario): BuildTahpContextOptions {
  switch (scenario) {
    case 'adapt_debug':
      return {
        includeSkillCatalog: false,
        includeKnowledge: false,
      }
    case 'bug_analysis':
      return {
        includeSkillCatalog: false,
        includeKnowledge: true,
      }
    case 'chat':
    default:
      return {
        includeSkillCatalog: true,
        includeKnowledge: true,
      }
  }
}

/**
 * 完整 TAHP 系统上下文 = Skill 执行规范 +（按场景可选）工程扫描摘要。
 * Skill 正文不注入提示词，须由 Agent 运行时 Read SKILL.md。
 */
export function buildFullTahpSystemContext(
  userInput: string,
  options?: {
    preferredSkillIds?: string[]
    scenario?: TahpSkillScenario
    contextOptions?: BuildTahpContextOptions
  },
): string {
  if (!hasTahpProject()) return ''

  const preferredSkillIds = [
    ...new Set([
      ...(options?.preferredSkillIds ?? []),
      ...extractPreferredSkillIds(userInput),
    ]),
  ]
  const scenario = options?.scenario ?? inferSkillScenario(userInput)
  const ctxOpts = { ...defaultContextOptions(scenario), ...options?.contextOptions }

  const parts = [
    buildSkillExecutionDirective({ preferredSkillIds, scenario }),
    buildTahpContext(userInput, ctxOpts),
  ].filter(p => p.trim().length > 0)

  return parts.join('\n\n')
}

// ---------------------------------------------------------------------------
// 对外接口
// ---------------------------------------------------------------------------

/**
 * 根据用户输入与选项，构造注入到 LLM system prompt 的工程扫描摘要。
 *
 * - 仅输出目录/索引级信息（skill 名+description、知识库标题）
 * - **不注入** Skill 正文；正文须 Agent 运行时 Read
 * - adapt_debug 场景默认跳过本函数（见 defaultContextOptions）
 */
export function buildTahpContext(
  _userInput: string,
  options: BuildTahpContextOptions = {},
): string {
  if (!hasTahpProject()) return ''

  const {
    includeSkillCatalog = true,
    includeKnowledge = true,
  } = options

  if (!includeSkillCatalog && !includeKnowledge) {
    return ''
  }

  const index = getIndex()
  if (index.length === 0) return ''

  const root = tahpPaths.projectRoot
  const skillsDir = join(root, 'skills', '.claude', 'skills')
  const lines: string[] = []

  lines.push('# TAHP 工程上下文（索引摘要，非 Skill 正文）')
  lines.push('')
  lines.push('> Skill 正文不在此注入，请按上方「Skill 执行规范」Read 对应 `SKILL.md`。')
  lines.push('')
  lines.push('## 工程根目录')
  lines.push(`  路径: \`${root}\``)
  lines.push('')

  if (includeSkillCatalog) {
    const skillItems = index.filter(i => i.type === 'skill')
    if (skillItems.length > 0) {
      lines.push(`## 已扫描到的 Skills（共 ${skillItems.length} 个，仅索引）`)
      lines.push(`  扫描目录: \`${skillsDir}\``)
      for (const item of skillItems) {
        const skillName = item.title.replace('Skill: ', '')
        lines.push(`  - **${skillName}**: ${item.summary}`)
        lines.push(`    文件路径: \`${join(skillsDir, skillName, 'SKILL.md')}\``)
      }
      lines.push('')
    } else {
      lines.push(`## Skills`)
      lines.push(`  扫描目录: \`${skillsDir}\`（未找到任何 SKILL.md）`)
      lines.push('')
    }
  }

  if (includeKnowledge) {
    const knowledgeItems = index.filter(i => i.type === 'knowledge')
    if (knowledgeItems.length > 0) {
      lines.push(`## 知识库索引（共 ${knowledgeItems.length} 条）`)
      lines.push(`  扫描目录: \`${join(root, 'knowledge-base')}\``)
      for (const item of knowledgeItems) {
        lines.push(`  - ${item.summary}`)
      }
      lines.push('')
    }
  }

  return lines.join('\n')
}

/**
 * 从 string | ContentBlock[] 中提取纯文本，用于关键词匹配。
 */
export function extractInputText(input: unknown): string {
  if (typeof input === 'string') return input
  if (Array.isArray(input)) {
    return input
      .map((b: any) => {
        if (typeof b === 'string') return b
        if (b?.type === 'text') return String(b.text || '')
        if (b?.text) return String(b.text)
        return ''
      })
      .join(' ')
  }
  return String(input || '')
}
