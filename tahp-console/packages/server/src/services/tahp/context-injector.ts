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
import { invalidateKbSearchIndex } from './kb-search'
import { logger } from '../logger'

// ---------------------------------------------------------------------------
// 类型定义
// ---------------------------------------------------------------------------

interface ContextItem {
  type: 'skill' | 'knowledge'
  title: string
  summary: string
  keywords: string[]
  /** 相对工程根的文件路径（知识条目 JSON 或 SKILL.md 父目录） */
  path?: string
  entryId?: string
  status?: string
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
    .map(s => s.replace(/[()（）\[\]【】#*`]/g, '').trim())
    .filter(s => s.length >= 2)
}

/** 查询词与条目的相关度（0～1），用于对话上下文筛选 */
function scoreContextItem(item: ContextItem, queryTokens: string[]): number {
  if (queryTokens.length === 0) return 0
  const hay = [
    item.title,
    item.summary,
    ...item.keywords,
    item.entryId || '',
  ].join(' ').toLowerCase()
  let hits = 0
  for (const qt of queryTokens) {
    if (hay.includes(qt)) hits++
  }
  return hits / queryTokens.length
}

const KB_DATA_ENTRIES_REL = 'knowledge-base/.kb-data/entries'

function loadKbDataEntryItems(): ContextItem[] {
  const entriesDir = join(tahpPaths.knowledgeDir, '.kb-data', 'entries')
  if (!existsSync(entriesDir)) return []

  const items: ContextItem[] = []
  for (const file of safeReadDir(entriesDir)) {
    if (!file.endsWith('.json')) continue
    const fullPath = join(entriesDir, file)
    try {
      const raw = readFileSync(fullPath, 'utf-8')
      const entry = JSON.parse(raw) as {
        id?: string
        content?: string
        module?: string
        func_type?: string
        category?: string
        keywords?: string[]
        source_file?: string
        status?: string
      }
      const status = String(entry.status || 'pending_review')
      // 对话检索：排除已拒绝/已删除；**已归档仍参与检索**（归档仅表示管理态，非不可搜）
      if (status === 'rejected' || status === 'deleted') continue

      const content = String(entry.content || '')
      const preview = content
        .replace(/^#{1,6}\s+/gm, '')
        .replace(/\|/g, ' ')
        .replace(/\s+/g, ' ')
        .trim()
        .slice(0, 200)
      const entryId = String(entry.id || file.replace(/\.json$/, ''))
      const title = entry.source_file
        ? `知识条目: ${entry.source_file}`
        : `知识条目: ${entryId}`

      items.push({
        type: 'knowledge',
        title,
        summary: `[${entry.module || 'shared'} / ${entry.func_type || '-'} / ${status}] ${preview}`,
        keywords: [
          ...tokenize(entryId),
          ...tokenize(content.slice(0, 4000)),
          ...tokenize((entry.keywords || []).join(' ')),
          ...tokenize(entry.source_file || ''),
          ...tokenize(entry.module || ''),
          ...tokenize(entry.func_type || ''),
          ...tokenize(entry.category || ''),
        ],
        path: `${KB_DATA_ENTRIES_REL}/${entryId}.json`,
        entryId,
        status,
      })
    } catch (err) {
      logger.warn('[context-injector] kb entry parse error %s: %s', file, err)
    }
  }
  return items
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

  // ── 2. 知识库（legacy index.yaml）──────────────────────────────────────────
  const includeLegacyYaml = process.env.TAHP_CHAT_LEGACY_YAML === '1'
  const knowledgeDir = tahpPaths.knowledgeDir
  if (includeLegacyYaml && existsSync(knowledgeDir)) {
    for (const moduleName of safeReadDir(knowledgeDir)) {
      if (moduleName.startsWith('.')) continue
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
            path: `knowledge-base/${moduleName}/index.yaml`,
          })
        }
      } catch (err) {
        logger.warn('[context-injector] knowledge parse error %s: %s', moduleName, err)
      }
    }
  }

  // ── 3. 知识库（Console .kb-data/entries — 智能诊断沉淀、文档导入等）────────
  items.push(...loadKbDataEntryItems())

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

/** 测试或知识库变更后强制刷新索引 */
export function invalidateContextIndex(): void {
  _index = null
  _indexBuiltAt = 0
  invalidateKbSearchIndex()
}

// ---------------------------------------------------------------------------
// Skill 路径与执行规范（Agent / LLM 系统提示词共用）
// ---------------------------------------------------------------------------

export type TahpSkillScenario = 'bug_analysis' | 'adapt_debug' | 'skill_config' | 'chat'

/** TAHP 仓内 Skill 根目录（相对工程根，用于提示词） */
export const TAHP_SKILLS_REL_ROOT = 'skills/.claude/skills'

/** TAHP 工程根目录在提示词中的相对表示 */
export const TAHP_PROJECT_REL_ROOT = '.'

/** TAHP 仓内 Claude Skill 根目录（绝对路径，运行时 Read 用） */
export function getTahpSkillsRoot(): string {
  return join(tahpPaths.projectRoot, 'skills', '.claude', 'skills')
}

/** 提示词中使用的 Skill 根目录（相对路径，便于工程拷贝到其他主机） */
export function getTahpSkillsRootForPrompt(): string {
  return TAHP_SKILLS_REL_ROOT
}

export function tahpSkillMdPath(skillId: string): string {
  return join(getTahpSkillsRoot(), skillId, 'SKILL.md')
}

/** 提示词中使用的 Skill.md 相对路径 */
export function tahpSkillMdRelativePath(skillId: string): string {
  return `${TAHP_SKILLS_REL_ROOT}/${skillId}/SKILL.md`
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

export function inferSkillScenario(text: string): TahpSkillScenario {
  if (/jira\s*key|bug\s*分析|根因定位|8\s*节报告|tools_invoked|待分析\s*bug/i.test(text)) {
    return 'bug_analysis'
  }
  if (/适配调试|adapt[- ]?debug|前置条件|升级路径|bsp\s*适配|关联\s*skills/i.test(text)) {
    return 'adapt_debug'
  }
  return 'chat'
}

/**
 * 历史案例模式专用指令：禁止 Agent 转向 Skill 检索。
 */
export function buildHistoricalCaseDirective(): string {
  return [
    '# TAHP 对话 — 历史案例模式（必读）',
    '',
    '**当前为「历史案例」检索模式。**',
    '- **仅**回答知识库 `bug_distill` 沉淀案例；**禁止**列举、加载或搜索 Skill。',
    '- **禁止** search_files / grep `skills/`、`harness`、全盘搜工程。',
    '- 用户问「有哪些 / 列出案例」：只输出精简表格（JIRA | 现象 | 一句话结论），数据必须来自预检索命中。',
    '- 预检索无命中：说明知识库暂无匹配，建议换关键词；**不要**改用 Skill 列表作答。',
  ].join('\n')
}

/**
 * Skill 按需加载的执行规范（注入 system prompt，指导 Agent Read SKILL.md）。
 */
export function buildSkillExecutionDirective(options?: {
  preferredSkillIds?: string[]
  scenario?: TahpSkillScenario
}): string {
  const skillsDir = getTahpSkillsRootForPrompt()
  const scenario = options?.scenario ?? 'chat'
  const lines: string[] = [
    '# TAHP Skill 执行规范（必读）',
    '',
    `工程内 Skill 根目录（唯一权威来源，相对工程根）: \`${skillsDir}\``,
    '每个 Skill 为 `<skillId>/SKILL.md`。**按需**选择 1～3 个相关 Skill，禁止编造不存在的 skillId。',
    '',
    '## 如何使用工程内 Skill',
    '1. 若下方预检索已给出知识库命中，先引用知识库结论；Skill 仅作补充。',
    '2. 仅当需要执行 SOP 步骤时 Read 对应 `SKILL.md`（1～3 个），禁止编造 skillId。',
    '3. 通信问题域未明：先 Read `com-comm-analysis-foundation` 做路由，再选叶子 Skill。',
    '4. MTK 充电/器件适配：先 Read `mtk-adapt-template-router`，再下钻具体 adapt Skill。',
    '5. 须真实调用工具；完成后在回复中列出实际使用的 skill 与 MCP 工具名。',
    '',
  ]

  if (scenario === 'bug_analysis') {
    lines.push('**当前场景**: 智能诊断 — 拉取 JIRA 后必须选择并加载匹配的日志/领域分析 Skill。')
  } else if (scenario === 'adapt_debug') {
    lines.push('**当前场景**: AI 适配调试 — 优先加载用户指定的关联 Adapt Skill 并按 SOP 排查；全部完成后必须 Read `transsion-coding-standards-review` 并在报告末尾输出自检审核。')
  } else if (scenario === 'skill_config') {
    lines.push('**当前场景**: 常用 Skill 配置 — 仅引导用户完成指定 Skill 的环境与凭据配置，按 SKILL.md 的 setup / setup-check 章节执行。')
  } else {
    lines.push('**当前场景**: TAHP 对话 — 优先使用下方「预检索结果」作答。')
    lines.push('**禁止**在未读预检索结果前对 `skills/`、`knowledge-base/`、`harness` 做 search_files/grep 全盘搜索。')
    lines.push('若预检索「知识库命中」非空：**必须直接引用摘要中的结论与 JIRA**，不要声称知识库无内容，不要从零开始写通用排查框架。')
    lines.push('仅当预检索无命中或用户追问细节时，才 Read 对应 JSON / SKILL.md。')
  }
  lines.push('')

  const preferred = [...new Set((options?.preferredSkillIds ?? []).filter(Boolean))]
  if (preferred.length > 0) {
    lines.push('## 优先 Skill（须最先 Read 并遵循）')
    for (const id of preferred) {
      lines.push(`- **${id}**: \`${tahpSkillMdRelativePath(id)}\``)
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
        includeSkillCatalog: true,
        includeKnowledge: true,
      }
    case 'skill_config':
      return {
        includeSkillCatalog: false,
        includeKnowledge: false,
      }
    case 'chat':
    default:
      return {
        includeSkillCatalog: false,
        includeKnowledge: false,
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
  userInput: string,
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

  const queryTokens = tokenize(userInput)
  const root = TAHP_PROJECT_REL_ROOT
  const skillsDir = TAHP_SKILLS_REL_ROOT
  const lines: string[] = []

  lines.push('# TAHP 工程上下文（索引摘要，非 Skill 正文）')
  lines.push('')
  lines.push('> Skill 正文不在此注入，请按上方「Skill 执行规范」Read 对应 `SKILL.md`。')
  lines.push('> 知识库全文在 `knowledge-base/.kb-data/entries/<id>.json` 的 `content` 字段，命中后须 Read 该文件。')
  lines.push('')
  lines.push('## 工程根目录')
  lines.push(`  路径: \`${root}\`（当前 TAHP 工程根，所有下列路径均相对此目录）`)
  lines.push('')

  if (includeSkillCatalog) {
    const skillItems = index.filter(i => i.type === 'skill')
    if (skillItems.length > 0) {
      lines.push(`## 已扫描到的 Skills（共 ${skillItems.length} 个，仅索引）`)
      lines.push(`  扫描目录: \`${skillsDir}\``)
      for (const item of skillItems) {
        const skillName = item.title.replace('Skill: ', '')
        lines.push(`  - **${skillName}**: ${item.summary}`)
        lines.push(`    文件路径: \`${skillsDir}/${skillName}/SKILL.md\``)
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
    const kbDataItems = knowledgeItems.filter(i => i.path?.includes('.kb-data/entries'))
    const legacyItems = knowledgeItems.filter(i => !i.path?.includes('.kb-data/entries'))

    // 按用户问题筛选相关知识条目（含已归档）
    const rankedKb = kbDataItems
      .map(item => ({ item, score: scoreContextItem(item, queryTokens) }))
      .filter(({ score }) => score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 8)

    if (rankedKb.length > 0) {
      lines.push(`## 相关知识库条目（与用户问题匹配，共 ${rankedKb.length} 条，请 Read JSON 获取全文）`)
      lines.push(`  存储目录: \`${KB_DATA_ENTRIES_REL}/\``)
      for (const { item, score } of rankedKb) {
        lines.push(`  - **${item.title}**（相关度 ${Math.round(score * 100)}%）`)
        lines.push(`    ${item.summary}`)
        if (item.path) lines.push(`    文件路径: \`${item.path}\`（读取 content 字段）`)
      }
      lines.push('')
    } else if (kbDataItems.length > 0 && queryTokens.length > 0) {
      lines.push(`## 知识库（.kb-data）`)
      lines.push(`  已索引 ${kbDataItems.length} 条条目，当前问题未命中关键词；可 Read \`${KB_DATA_ENTRIES_REL}/\` 下 JSON 或让用户提供更具体关键词。`)
      lines.push('')
    }

    if (legacyItems.length > 0) {
      lines.push(`## 知识库索引（legacy index.yaml，共 ${legacyItems.length} 条）`)
      lines.push(`  扫描目录: \`knowledge-base/<module>/index.yaml\``)
      for (const item of legacyItems) {
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
