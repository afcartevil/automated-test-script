/**
 * TAHP 工程上下文注入器
 *
 * 扫描工程的 skills / knowledge-base / constraints / playbooks，
 * 根据用户输入做关键词匹配，返回注入到 LLM system prompt 的上下文字符串。
 * 让对话模式也能"看到"工程内容，无需 MCP 工具。
 */

import { existsSync, readFileSync, readdirSync } from 'fs'
import { join, basename } from 'path'
import yaml from 'js-yaml'
import { tahpPaths, hasTahpProject } from './paths'
import { logger } from '../logger'

// ---------------------------------------------------------------------------
// 类型定义
// ---------------------------------------------------------------------------

interface ContextItem {
  type: 'skill' | 'knowledge' | 'constraint' | 'playbook'
  title: string
  summary: string
  keywords: string[]
  fullContent?: string  // 限制大小，用于详细展示
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
          fullContent: raw.length > 2500 ? raw.slice(0, 2500) + '\n...(截断)' : raw,
        })
      } catch (err) {
        logger.warn('[context-injector] skill parse error %s: %s', skillName, err)
      }
    }
  }

  // ── 2. 模块约束 ────────────────────────────────────────────────────────────
  const constraintsDir = tahpPaths.constraintsDir
  if (existsSync(constraintsDir)) {
    for (const moduleName of safeReadDir(constraintsDir)) {
      const moduleYamlPath = join(constraintsDir, moduleName, 'module.yaml')
      if (!existsSync(moduleYamlPath)) continue
      try {
        const raw = readFileSync(moduleYamlPath, 'utf-8')
        const cfg = yaml.load(raw) as Record<string, any>
        const displayName = String(cfg?.module?.display_name || moduleName)
        const components: string[] = (cfg?.scope?.includes || []).map((s: any) => String(s.component || s.path || ''))
        const scope = `包含组件: ${components.filter(Boolean).join(', ')}`
        items.push({
          type: 'constraint',
          title: `模块约束: ${displayName} (${moduleName})`,
          summary: scope,
          keywords: [
            ...tokenize(moduleName),
            ...tokenize(displayName),
            ...components.flatMap(c => tokenize(c)),
          ],
          fullContent: raw.length > 1500 ? raw.slice(0, 1500) + '\n...(截断)' : raw,
        })

        // 扫描同目录下其他 domain yaml
        const domainFiles = safeReadDir(join(constraintsDir, moduleName))
          .filter(f => f.endsWith('.yaml') && f !== 'module.yaml')
        for (const domainFile of domainFiles) {
          try {
            const dRaw = readFileSync(join(constraintsDir, moduleName, domainFile), 'utf-8')
            const dCfg = yaml.load(dRaw) as Record<string, any>
            const dName = basename(domainFile, '.yaml')
            items.push({
              type: 'constraint',
              title: `约束域: ${moduleName}/${dName}`,
              summary: String(dCfg?.description || dCfg?.name || dName),
              keywords: [
                ...tokenize(moduleName),
                ...tokenize(dName),
                ...tokenize(String(dCfg?.description || '')),
              ],
              fullContent: dRaw.length > 1200 ? dRaw.slice(0, 1200) + '\n...(截断)' : dRaw,
            })
          } catch { /* skip malformed */ }
        }
      } catch (err) {
        logger.warn('[context-injector] constraint parse error %s: %s', moduleName, err)
      }
    }
  }

  // ── 3. 知识库 ──────────────────────────────────────────────────────────────
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

  // ── 4. Playbooks ──────────────────────────────────────────────────────────
  const playbooksDir = tahpPaths.playbooksDir
  if (existsSync(playbooksDir)) {
    for (const file of safeReadDir(playbooksDir).filter(f => f.endsWith('.yaml'))) {
      try {
        const raw = readFileSync(join(playbooksDir, file), 'utf-8')
        const cfg = yaml.load(raw) as Record<string, any>
        const name = String(cfg?.name || file)
        const desc = String(cfg?.description || cfg?.trigger || '')
        items.push({
          type: 'playbook',
          title: `Playbook: ${name}`,
          summary: desc,
          keywords: [
            ...tokenize(name),
            ...tokenize(desc),
            ...tokenize(basename(file, '.yaml')),
          ],
          fullContent: raw.length > 1000 ? raw.slice(0, 1000) + '\n...(截断)' : raw,
        })
      } catch (err) {
        logger.warn('[context-injector] playbook parse error %s: %s', file, err)
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
    lines.push('**当前场景**: AI Bug 分析 — 拉取 JIRA 后必须选择并加载匹配的日志/领域分析 Skill。')
  } else if (scenario === 'adapt_debug') {
    lines.push('**当前场景**: AI 适配调试 — 优先加载用户指定的关联 Adapt Skill 并按 SOP 排查。')
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

/**
 * 完整 TAHP 系统上下文 = Skill 执行规范 + 工程扫描（skills / 约束 / playbook / 关键词匹配节选）。
 */
export function buildFullTahpSystemContext(
  userInput: string,
  options?: {
    preferredSkillIds?: string[]
    scenario?: TahpSkillScenario
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

  const parts = [
    buildSkillExecutionDirective({ preferredSkillIds, scenario }),
    buildTahpContext(userInput),
  ].filter(p => p.trim().length > 0)

  return parts.join('\n\n')
}

// ---------------------------------------------------------------------------
// 对外接口
// ---------------------------------------------------------------------------

/**
 * 根据用户输入，构造注入到 LLM system prompt 的工程上下文字符串。
 *
 * - 始终包含：项目概览、skill 列表、模块约束摘要、playbook 列表
 * - 按关键词匹配：高相关内容注入详细文本（最多 3 条）
 * - 无匹配时只返回轻量概览（不膨胀 token）
 */
export function buildTahpContext(userInput: string): string {
  if (!hasTahpProject()) return ''

  const inputLower = (userInput || '').toLowerCase()
  const index = getIndex()
  if (index.length === 0) return ''

  // ── 关键词评分 ─────────────────────────────────────────────────────────────
  const scored = index
    .map(item => {
      let score = 0
      for (const kw of item.keywords) {
        if (kw.length >= 2 && inputLower.includes(kw)) {
          score += kw.length  // 越长的关键词权重越高
        }
      }
      return { item, score }
    })
    .filter(s => s.score > 0)
    .sort((a, b) => b.score - a.score)

  // ── 构建输出 ───────────────────────────────────────────────────────────────
  const root = tahpPaths.projectRoot
  const skillsDir = join(root, 'skills', '.claude', 'skills')
  const lines: string[] = []

  // 明确标注：这是实时扫描的真实文件内容
  lines.push('# TAHP 工程上下文（服务器实时扫描，非模板预设）')
  lines.push('')
  lines.push('> **重要说明**：以下内容由服务器在处理本次请求时实时扫描工程文件生成。')
  lines.push('> 如果用户询问某个 skill/文件是否存在，请以下方列表为准，不要推测或假设。')
  lines.push('')
  lines.push('## 工程根目录')
  lines.push(`  路径: \`${root}\``)
  lines.push('  目录结构: skills/(AI技能) | knowledge-base/(知识库) | constraints/(模块约束) | playbooks/(执行Pipeline) | tahp-mcp-server/(MCP服务器) | tahp-console/(Web控制台)')
  lines.push('')

  // Skill 列表（含目录路径，便于 LLM 精确引用）
  const skillItems = index.filter(i => i.type === 'skill')
  if (skillItems.length > 0) {
    lines.push(`## 已扫描到的 Skills（共 ${skillItems.length} 个）`)
    lines.push(`  扫描目录: \`${skillsDir}\``)
    lines.push('  以下是该目录下实际存在的所有 SKILL.md 文件对应的 skill：')
    lines.push('')
    for (const item of skillItems) {
      const skillName = item.title.replace('Skill: ', '')
      lines.push(`  - **${skillName}**: ${item.summary}`)
      lines.push(`    文件路径: \`${join(skillsDir, skillName, 'SKILL.md')}\``)
    }
    lines.push('')
    lines.push(`  ⚠️ 注意：上述 ${skillItems.length} 个是全部已有的 skill，此目录下不存在其他 skill。`)
    lines.push('  如果用户询问某个 skill 是否存在但不在上述列表中，请明确告知该 skill 当前工程中不存在。')
    lines.push('')
  } else {
    lines.push(`## Skills`)
    lines.push(`  扫描目录: \`${skillsDir}\`（未找到任何 SKILL.md）`)
    lines.push('')
  }

  // 模块约束摘要（只列 module.yaml，不展开 domain）
  const moduleConstraints = index.filter(i => i.type === 'constraint' && i.title.startsWith('模块约束:'))
  if (moduleConstraints.length > 0) {
    lines.push(`## 模块约束（共 ${moduleConstraints.length} 个模块）`)
    lines.push(`  扫描目录: \`${join(root, 'constraints')}\``)
    for (const item of moduleConstraints) {
      lines.push(`  - **${item.title}**: ${item.summary}`)
    }
    lines.push('')
  }

  // Playbook 列表
  const playbookItems = index.filter(i => i.type === 'playbook')
  if (playbookItems.length > 0) {
    lines.push(`## Playbooks（共 ${playbookItems.length} 个）`)
    lines.push(`  扫描目录: \`${join(root, 'playbooks')}\``)
    for (const item of playbookItems) {
      lines.push(`  - **${item.title}**: ${item.summary}`)
    }
    lines.push('')
  }

  // 知识库索引（仅条目标题，不加载全文）
  const knowledgeItems = index.filter(i => i.type === 'knowledge')
  if (knowledgeItems.length > 0) {
    lines.push(`## 知识库索引（共 ${knowledgeItems.length} 条）`)
    lines.push(`  扫描目录: \`${join(root, 'knowledge-base')}\``)
    for (const item of knowledgeItems) {
      lines.push(`  - ${item.summary}`)
    }
    lines.push('')
  }

  // 高相关详细内容（取 top 3，只取有 fullContent 的条目）
  const detailed = scored.slice(0, 3).filter(s => s.item.fullContent)
  if (detailed.length > 0) {
    lines.push('## 当前问题相关详细内容（关键词匹配结果）')
    for (const { item, score } of detailed) {
      lines.push(`### ${item.title}`)
      lines.push(`> 相关度评分: ${score}`)
      lines.push('')
      lines.push('```')
      lines.push(item.fullContent!.trim())
      lines.push('```')
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
