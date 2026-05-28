/**
 * TAHP Skill 管理路由
 *
 * POST   /api/tahp/skills/create          — 从文本描述创建 adapt skill
 * GET    /api/tahp/skills/list            — 列出所有 adapt skill（带 tahp_adapt_skill: true）
 * DELETE /api/tahp/skills/:skillId        — 删除一个 adapt skill
 * GET    /api/tahp/adapt/domains          — 返回动态域列表，供 AdaptDebugView 使用
 */
import Router from '@koa/router'
import { tahpPaths } from '../../services/tahp/paths'
import {
  existsSync, mkdirSync, writeFileSync, readdirSync,
  readFileSync, rmSync, statSync,
} from 'fs'
import { join } from 'path'
import { dump as yamlDump } from 'js-yaml'
import { logger } from '../../services/logger'

export const tahpSkillsRoutes = new Router()

// ─── helpers ──────────────────────────────────────────────────────────────────

const SKILLS_ROOT = () => join(tahpPaths.projectRoot, 'skills', '.claude', 'skills')

/** 简单解析 YAML frontmatter —— 不依赖 js-yaml (避免多行 block literal 的坑) */
function parseFrontmatter(text: string): Record<string, any> {
  const match = text.match(/^---\r?\n([\s\S]*?)\r?\n---/)
  if (!match) return {}
  const raw = match[1]
  // 只解析顶层 key: value（不递归 nested YAML）
  const result: Record<string, any> = {}
  let currentKey: string | null = null
  let inArray = false
  const lines = raw.split(/\r?\n/)
  for (const line of lines) {
    // 顶层 key: value
    const kv = line.match(/^(\w[\w_-]*):\s*(.*)$/)
    if (kv && !line.startsWith(' ') && !line.startsWith('-')) {
      currentKey = kv[1]
      inArray = false
      const val = kv[2].trim().replace(/^["']|["']$/g, '')
      if (val === 'true') result[currentKey] = true
      else if (val === 'false') result[currentKey] = false
      else if (val === '') result[currentKey] = []  // assume array follows
      else result[currentKey] = val
      continue
    }
    // Array item (indented with 2 spaces + dash)
    const arr = line.match(/^\s{2}-\s+(.+)$/)
    if (arr && currentKey) {
      if (!Array.isArray(result[currentKey])) result[currentKey] = []
      // Try to parse nested object (minimal)
      const objLine = arr[1].trim()
      const nested: Record<string, any> = {}
      let parsed = false
      // Single-line object: {key: val, ...}
      if (objLine.startsWith('{')) {
        try {
          // Replace single quotes
          const jsonStr = objLine.replace(/'/g, '"').replace(/(\w+):/g, '"$1":')
          Object.assign(nested, JSON.parse(jsonStr))
          parsed = true
        } catch { /* ignore */ }
      }
      if (parsed) {
        result[currentKey].push(nested)
      } else {
        result[currentKey].push(objLine.replace(/^["']|["']$/g, ''))
      }
    }
  }
  return result
}

/** 扫描 skills 目录，返回所有标记了 tahp_adapt_skill: true 的技能 */
function scanAdaptSkills(): Array<{
  skillId: string
  skillDir: string
  meta: Record<string, any>
  content: string
}> {
  const root = SKILLS_ROOT()
  if (!existsSync(root)) return []
  const results: any[] = []

  const entries = readdirSync(root, { withFileTypes: true })
  for (const entry of entries) {
    if (!entry.isDirectory()) continue
    const skillMd = join(root, entry.name, 'SKILL.md')
    if (!existsSync(skillMd)) continue
    try {
      const content = readFileSync(skillMd, 'utf-8')
      const meta = parseFrontmatter(content)
      if (meta.tahp_adapt_skill === true) {
        results.push({
          skillId:  entry.name,
          skillDir: join(root, entry.name),
          meta,
          content,
        })
      }
    } catch { /* skip */ }
  }
  return results
}

// ─── routes ──────────────────────────────────────────────────────────────────

// POST /api/tahp/skills/create — 创建适配技能
tahpSkillsRoutes.post('/api/tahp/skills/create', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const {
    skillId,      // 唯一 ID（kebab-case，用作目录名）
    domainLabel,  // 中文显示名（如 "TEST 测试适配"）
    domainId,     // 域 ID（如 "test"，用于路由 key）
    module: mod,  // 关联模块（telephony / kernel-driver / power-mgmt / shared / custom）
    funcType,     // 业务类型（bug_analysis / code_adaptation / version_adaptation / carrier_porting / ai_self_check）
    icon,         // 徽章文字（2-4 字符）
    color,        // 十六进制颜色
    adaptFields,  // 前置条件字段列表
    content,      // 技能详细说明（Markdown）
    description,  // 一行简介
  } = body

  // 参数校验
  if (!skillId || typeof skillId !== 'string' || !/^[a-zA-Z0-9_-]+$/.test(skillId)) {
    ctx.status = 400
    ctx.body = { success: false, error: 'skillId 必须是合法的 kebab-case 字符串' }
    return
  }
  if (!domainLabel || typeof domainLabel !== 'string') {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 domainLabel' }
    return
  }
  if (!mod || typeof mod !== 'string') {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 module' }
    return
  }
  if (!funcType || typeof funcType !== 'string') {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 funcType（业务类型）' }
    return
  }

  const skillDir = join(SKILLS_ROOT(), String(skillId))
  if (existsSync(skillDir)) {
    ctx.status = 409
    ctx.body = { success: false, error: `skill "${skillId}" 已存在，请使用不同的 ID` }
    return
  }

  const now = new Date().toISOString()
  const fields = Array.isArray(adaptFields) ? adaptFields : []

  // 构建 YAML frontmatter（直接手写字符串，避免 js-yaml 转义问题）
  const fieldsYaml = fields.map((f: any) =>
    `  - name: ${f.name || ''}\n    label: "${f.label || ''}"\n    type: ${f.type || 'text'}\n    required: ${f.required ? 'true' : 'false'}\n    placeholder: "${f.placeholder || ''}"`
  ).join('\n')

  const frontmatter = [
    `tahp_adapt_skill: true`,
    `name: ${skillId}`,
    `domain_label: "${String(domainLabel)}"`,
    `domain_id: "${String(domainId || skillId)}"`,
    `module: ${String(mod)}`,
    `func_type: ${String(funcType)}`,
    `icon: "${String(icon || skillId.slice(0, 4).toUpperCase())}"`,
    `color: "${String(color || '#7c3aed')}"`,
    `status: active`,
    `description: "${String(description || domainLabel)}"`,
    `adapt_fields:`,
    ...(fields.length ? [fieldsYaml] : ['  []']),
    `created_at: "${now}"`,
    `source: user_created`,
  ].join('\n')

  const fileContent = `---\n${frontmatter}\n---\n\n# ${domainLabel}\n\n${content || '用户创建的适配技能。'}\n`

  try {
    mkdirSync(skillDir, { recursive: true })
    writeFileSync(join(skillDir, 'SKILL.md'), fileContent, 'utf-8')
    logger.info({ skillId, mod }, '[tahp-skills] created adapt skill')
    ctx.body = {
      success: true,
      data: {
        skillId,
        path: `skills/.claude/skills/${skillId}/SKILL.md`,
        domainId: String(domainId || skillId),
        domainLabel: String(domainLabel),
      },
    }
  } catch (err) {
    logger.error({ err, skillId }, '[tahp-skills] failed to create skill')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// GET /api/tahp/skills/list — 列出所有 adapt 技能
tahpSkillsRoutes.get('/api/tahp/skills/list', async (ctx) => {
  try {
    const skills = scanAdaptSkills().map(({ skillId, meta }) => ({
      skillId,
      domainId:    meta.domain_id    || skillId,
      domainLabel: meta.domain_label || skillId,
      module:      meta.module       || 'shared',
      funcType:    meta.func_type    || 'bug_analysis',
      icon:        meta.icon         || skillId.slice(0, 4).toUpperCase(),
      color:       meta.color        || '#7c3aed',
      status:      meta.status       || 'active',
      description: meta.description  || '',
      adaptFields: Array.isArray(meta.adapt_fields) ? meta.adapt_fields : [],
      createdAt:   meta.created_at   || '',
    }))
    ctx.body = { success: true, data: { skills, total: skills.length } }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// DELETE /api/tahp/skills/:skillId — 删除 adapt 技能
tahpSkillsRoutes.delete('/api/tahp/skills/:skillId', async (ctx) => {
  const { skillId } = ctx.params
  if (!skillId || !/^[a-zA-Z0-9_-]+$/.test(skillId)) {
    ctx.status = 400
    ctx.body = { success: false, error: '无效的 skillId' }
    return
  }
  const skillDir = join(SKILLS_ROOT(), skillId)
  if (!existsSync(skillDir)) {
    ctx.status = 404
    ctx.body = { success: false, error: `技能 "${skillId}" 不存在` }
    return
  }
  // 校验：只允许删除 adapt skill
  const skillMd = join(skillDir, 'SKILL.md')
  if (existsSync(skillMd)) {
    const meta = parseFrontmatter(readFileSync(skillMd, 'utf-8'))
    if (!meta.tahp_adapt_skill) {
      ctx.status = 403
      ctx.body = { success: false, error: '只能删除通过控制台创建的 adapt 技能' }
      return
    }
  }
  try {
    rmSync(skillDir, { recursive: true, force: true })
    ctx.body = { success: true, data: { deleted: skillId } }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// GET /api/tahp/adapt/domains — 返回动态域列表
tahpSkillsRoutes.get('/api/tahp/adapt/domains', async (ctx) => {
  try {
    const skills = scanAdaptSkills()
    const domains = skills
      .filter(({ meta }) => meta.status !== 'disabled')
      .map(({ skillId, meta }) => ({
        id:            String(meta.domain_id    || skillId),
        label:         String(meta.domain_label || skillId),
        icon:          String(meta.icon         || skillId.slice(0, 4).toUpperCase()),
        color:         String(meta.color        || '#7c3aed'),
        module:        String(meta.module       || 'shared'),
        status:        'active' as const,
        skillId,
        relatedSkills: [skillId],
        fields:        Array.isArray(meta.adapt_fields) ? meta.adapt_fields : [],
      }))
    ctx.body = { success: true, data: { domains } }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})
