/**
 * 智能诊断 — 用户指定代码源（可选，三种模式通用）
 *
 * 用户在界面只填一个输入框，这里自动判型：
 *   - local_path      本地磁盘 / 映射盘 / UNC 代码路径
 *   - opengrok_branch OpenGrok 代码分支名
 *   - opengrok_url    OpenGrok xref 链接（可带文件与行号）
 *   - unknown         判不出来，作为线索透传，不阻断任务
 *
 * 判型结果决定注入 Agent 的取证硬规则：本地路径走 Read / Grep，
 * OpenGrok 走本机官方 `asf-opengrok` Skill + `asf --json opengrok` CLI。
 *
 * 落盘：报告 JSON 的 `code_source` 字段（旧报告无此字段，按 undefined 处理）。
 */
import { existsSync } from 'fs'
import { resolveHarnessHostSkillMd } from './harness-host-skills'
import { hostCliPrefix } from './host-tool-runtime'

export type CodeSourceKind = 'local_path' | 'opengrok_branch' | 'opengrok_url' | 'unknown'

export interface CodeSourceRef {
  /** 用户原始输入（去首尾空白） */
  raw: string
  kind: CodeSourceKind
  /** local_path：规范化后的路径 */
  path?: string
  /** local_path：BFF 启动任务时的存在性探测结果 */
  exists?: boolean
  /** opengrok_*：分支名（url 从 /xref/<branch>/ 解析） */
  branch?: string
  /** opengrok_url：xref 中的文件路径（以 / 开头） */
  filePath?: string
  /** opengrok_url：锚点行号 */
  startLine?: number
  /** true 表示 branch 命中已知分支清单 */
  branchKnown?: boolean
}

/** OpenGrok 已知代码分支（平台侧维护，供 UI 下拉与判型使用） */
export const OPENGROK_BRANCHES = [
  'tOS_mtk_A13_trunk',
  'tOS_mtk_A15_trunk',
  'tOS_mtk_A16_trunk',
  'tOS_mtk_A17_trunk',
  'tOS_mtk_A16_vnd_trunk',
  'tran_mtk_main.mp1.rc_trunk',
  'tran_mtk_u0.mp1.rc_trunk',
  'tran_mtk_t0.mp1.rc_trunk',
  'tran_mtk_u0.vnd.mp1.rc_trunk',
  'transsion_mtk.s0.mp1_trunk',
  'tran_sprd_v0_sys_trunk',
  'tran_sprd_t0_v_vnd_trunk',
  'tran_sprd_v1_vnd_trunk',
  'tran_sprd_v1_krn_trunk',
  'tOS_unisoc_A16_sys_trunk',
  'tOS_qcom_A14_trunk',
  'tOS_qcom_A14_nonhlos_trunk',
  'tOS_qcom_A16_trunk',
  'tOS_qcom_A17_trunk',
] as const

export const DEFAULT_OPENGROK_BRANCH = 'tOS_mtk_A16_trunk'

/** 官方 OpenGrok Skill 候选目录名（本机安装，asf / harness 两套命名） */
const OPENGROK_SKILL_IDS = ['asf-opengrok', 'harness-opengrok'] as const

const KNOWN_BRANCH_SET = new Set<string>(OPENGROK_BRANCHES)

/** 分支名形态：tOS_* / tran_* / transsion_*，允许 . 与 _ */
const BRANCH_LIKE_RE = /^(tOS|tos|tran|transsion)[A-Za-z0-9._-]*$/
/** 分支模糊关键字：A16 / A17 等，OpenGrok CLI 支持 --branch A17 模糊匹配 */
const BRANCH_QUERY_RE = /^A\d{2}$/i
const WIN_DRIVE_RE = /^[A-Za-z]:[\\/]/
const UNC_RE = /^\\\\[^\\]/

function parseOpengrokUrl(raw: string): CodeSourceRef {
  const ref: CodeSourceRef = { raw, kind: 'opengrok_url' }

  const lineMatch = raw.match(/#L?(\d+)\b/)
  if (lineMatch) {
    const n = Number(lineMatch[1])
    if (Number.isFinite(n) && n > 0) ref.startLine = n
  }

  // http://<host>/xref/<branch>/<file path>?<query>#<anchor>
  const xref = raw.match(/\/xref\/([^/?#]+)(\/[^?#]*)?/)
  if (xref) {
    ref.branch = decodeURIComponent(xref[1])
    const file = (xref[2] || '').replace(/\/+$/, '')
    if (file && file !== '/') ref.filePath = decodeURIComponent(file)
  } else {
    // /search?project=<branch>&... 之类
    const project = raw.match(/[?&]project=([^&#]+)/)
    if (project) ref.branch = decodeURIComponent(project[1])
  }

  if (ref.branch) ref.branchKnown = KNOWN_BRANCH_SET.has(ref.branch)
  return ref
}

/**
 * 存在性探测。
 *
 * UNC 路径（\\host\share）不探测：网络不可达时 existsSync 会阻塞数秒，
 * 而 parseCodeSource 跑在启动任务的 HTTP 请求里。undefined 表示「未探测」，
 * 提示词不会因此给出「路径不可用」警告，交由 Agent 自己用工具确认。
 */
function probeExists(p: string): boolean | undefined {
  if (UNC_RE.test(p)) return undefined
  try {
    return existsSync(p)
  } catch {
    return undefined
  }
}

/** 代码源引用恒为单行短串；截断避免整段文本被注入 system instructions */
const MAX_RAW_LEN = 512

/**
 * 把用户单框输入解析成结构化代码源引用。
 * 空输入返回 undefined；判不出来返回 kind='unknown'，仍作为线索透传。
 */
export function parseCodeSource(raw?: string | null): CodeSourceRef | undefined {
  // 只取第一行：路径 / 分支 / URL 都是单行，多行输入按误粘贴处理
  const text = (raw || '').split(/[\r\n]/)[0].trim().slice(0, MAX_RAW_LEN)
  if (!text) return undefined

  if (/^https?:\/\//i.test(text)) {
    if (/\/xref\//i.test(text) || /opengrok/i.test(text) || /[?&]project=/i.test(text)) {
      return parseOpengrokUrl(text)
    }
    return { raw: text, kind: 'unknown' }
  }

  if (WIN_DRIVE_RE.test(text) || UNC_RE.test(text) || text.startsWith('/')) {
    const path = text.replace(/[\\/]+$/, '') || text
    return { raw: text, kind: 'local_path', path, exists: probeExists(path) }
  }

  if (KNOWN_BRANCH_SET.has(text)) {
    return { raw: text, kind: 'opengrok_branch', branch: text, branchKnown: true }
  }
  if (BRANCH_LIKE_RE.test(text) || BRANCH_QUERY_RE.test(text)) {
    return { raw: text, kind: 'opengrok_branch', branch: text, branchKnown: false }
  }

  return { raw: text, kind: 'unknown' }
}

export function codeSourceKindLabel(kind: CodeSourceKind): string {
  switch (kind) {
    case 'local_path': return '本地/映射盘代码路径'
    case 'opengrok_branch': return 'OpenGrok 代码分支'
    case 'opengrok_url': return 'OpenGrok 代码链接'
    default: return '未判型（按线索处理）'
  }
}

function isOpengrokKind(kind: CodeSourceKind): boolean {
  return kind === 'opengrok_branch' || kind === 'opengrok_url'
}

/** OpenGrok 取证需要优先 Read 的官方 Skill（本机目录，由 context-injector 渲染） */
export function codeSourcePreferredSkillIds(ref?: CodeSourceRef): string[] {
  if (!ref || !isOpengrokKind(ref.kind)) return []
  for (const id of OPENGROK_SKILL_IDS) {
    if (resolveHarnessHostSkillMd(id)) return [id]
  }
  return [OPENGROK_SKILL_IDS[0]]
}

function resolveOpengrokSkill(): { skillId: string; skillMdPath: string | null } {
  for (const id of OPENGROK_SKILL_IDS) {
    const p = resolveHarnessHostSkillMd(id)
    if (p) return { skillId: id, skillMdPath: p }
  }
  return { skillId: OPENGROK_SKILL_IDS[0], skillMdPath: null }
}

/** 注入 user message 的简述块（硬规则在 system instructions 里） */
export function buildCodeSourceUserBlock(ref?: CodeSourceRef): string[] {
  if (!ref) return []
  const lines = [
    '',
    '## 指定代码源（用户指定，必须结合其中的真实代码分析）',
    `- 原始输入: \`${ref.raw}\``,
    `- 识别类型: ${codeSourceKindLabel(ref.kind)}`,
  ]
  if (ref.path) lines.push(`- 代码路径: \`${ref.path}\`${ref.exists === false ? '（BFF 探测：当前不可访问）' : ''}`)
  if (ref.branch) lines.push(`- 分支: \`${ref.branch}\``)
  if (ref.filePath) lines.push(`- 起始文件: \`${ref.filePath}\`${ref.startLine ? ` 第 ${ref.startLine} 行` : ''}`)
  lines.push('- 取证硬规则见系统提示词「指定代码源」段落。')
  return lines
}

/**
 * 注入 system instructions 的代码源取证硬规则。
 * 与远程渠道指令不同：Jira 单条 / 批量 / 本地日志三种模式都注入。
 */
export function buildCodeSourceDirective(ref?: CodeSourceRef): string {
  if (!ref) return ''

  const lines: string[] = [
    '# 指定代码源（本任务生效 · 硬规则）',
    '',
    '用户为本次分析指定了代码源。**根因定位必须落到该代码源中的真实代码**（文件路径 + 行号），',
    '禁止凭记忆或推测描述代码；在指定代码源中找不到对应实现时，须明确写「未在指定代码源中找到」。',
    '',
    '| 项 | 值 |',
    '| --- | --- |',
    `| 原始输入 | \`${ref.raw}\` |`,
    `| 识别类型 | ${codeSourceKindLabel(ref.kind)} |`,
  ]
  if (ref.path) lines.push(`| 代码路径 | \`${ref.path}\` |`)
  if (ref.branch) lines.push(`| 分支 | \`${ref.branch}\` |`)
  if (ref.filePath) lines.push(`| 起始文件 | \`${ref.filePath}\`${ref.startLine ? ` 第 ${ref.startLine} 行` : ''} |`)
  lines.push('')

  if (ref.kind === 'local_path') {
    lines.push('## 取证方式：本地文件系统（只读）')
    lines.push('')
    lines.push(`1. 用 Read / Grep / Glob 在 \`${ref.path}\` 下检索相关源码；该路径可能是映射盘（如 \`Z:\\\`），`)
    lines.push('   访问偏慢时缩小检索范围（按模块子目录 + 关键符号），不要因为慢就跳过取证。')
    lines.push('2. 报告第 3、4 节引用代码时必须写明**绝对路径 + 行号**。')
    lines.push('3. **只读**：禁止在该路径下新建 / 修改 / 删除任何文件，禁止在此执行编译或 git 写操作。')
    lines.push('')
    if (ref.exists === false) {
      lines.push(`> 警告：BFF 启动本任务时探测到 \`${ref.path}\` 不存在或不可访问（映射盘未挂载时常见）。`)
      lines.push('> 请自行用工具确认一次；确认不可用时在 `analyze` 阶段标记的 `message` 写明 `code_source_unavailable`，')
      lines.push('> 改用日志与用户描述完成分析，**禁止**编造该路径下的文件或代码。')
      lines.push('')
    }
    return lines.join('\n')
  }

  if (isOpengrokKind(ref.kind)) {
    const { skillId, skillMdPath } = resolveOpengrokSkill()
    const cli = hostCliPrefix()
    const branch = ref.branch || DEFAULT_OPENGROK_BRANCH

    lines.push('## 取证方式：OpenGrok（跨版本只读源码）')
    lines.push('')
    if (skillMdPath) {
      lines.push(`1. **必须先 Read** 官方 Skill 全文：\`${skillMdPath}\``)
      lines.push(`   （\`${skillId}\` 属官方本机安装 Skill，**勿**在工程 \`skills/.claude/skills/\` 下查找）`)
    } else {
      lines.push(`1. 本机未找到 ${OPENGROK_SKILL_IDS.map(id => `\`${id}\``).join(' / ')} 的 SKILL.md。`)
    }
    lines.push(`2. 按其 SOP 使用 \`${cli} --json opengrok\` 取证，典型顺序：`)
    lines.push(`   - \`${cli} --json opengrok search --branch ${branch} --def <符号> --top 10 --max-hits-per-file 5\` 先拿命中文件与行号`)
    lines.push(`   - \`${cli} --json opengrok find-in-file --file-path <文件> --keyword <关键字>\` 在已知文件内定位`)
    lines.push(`   - \`${cli} --json opengrok fetch --file-path <文件> --start-line N --end-line M\` 只取命中行附近的小范围上下文`)
    lines.push(`3. 分支固定为 \`${branch}\`，除用户另有说明外不要换分支。`)
    if (ref.branchKnown === false) {
      lines.push(`   该分支名不在平台已知清单内，先用 \`${cli} --json opengrok branches --query ${branch}\` 核对真实分支名再检索。`)
      lines.push(`   已知分支清单：${OPENGROK_BRANCHES.join(' / ')}`)
    }
    if (ref.filePath) {
      lines.push(`4. 用户已给出起始位置 \`${ref.filePath}\`${ref.startLine ? ` 第 ${ref.startLine} 行` : ''}，`)
      lines.push(ref.startLine
        ? `   可直接 \`fetch --file-path ${ref.filePath} --start-line ${Math.max(1, ref.startLine - 40)} --end-line ${ref.startLine + 40}\` 起步。`
        : `   可直接 \`find-in-file --file-path ${ref.filePath} --keyword <关键字>\` 起步。`)
    }
    lines.push('5. 报告第 3、4 节引用源码时必须写明**分支 + 文件路径 + 行范围**（可追溯）。')
    lines.push('6. OpenGrok 是只读证据：不要据此给出完整 patch，只给修改方向。')
    lines.push('')
    if (!skillMdPath) {
      lines.push('> 警告：官方 OpenGrok Skill 未安装，本任务视 OpenGrok 取证为**不可用**。')
      lines.push('> 在 `analyze` 阶段标记的 `message` 写明 `code_source_unavailable: opengrok skill 未安装`，')
      lines.push('> 改用日志与用户描述完成分析，**禁止**编造源码内容或行号。')
      lines.push('')
    }
    return lines.join('\n')
  }

  lines.push('## 取证方式：未能判型')
  lines.push('')
  lines.push('该输入既不是绝对路径，也不像 OpenGrok 分支名或 xref 链接。把它当作代码位置线索（仓库名 / 模块名 / 分支关键字）：')
  if (/\s/.test(ref.raw)) {
    lines.push('- 先从该描述中提取仓库名或分支关键字，再用官方 opengrok Skill 的 `branches` 命令核对。')
  } else {
    lines.push(`- 若像分支关键字，先 \`${hostCliPrefix()} --json opengrok branches --query ${ref.raw}\` 核对（须先 Read 官方 opengrok Skill）。`)
  }
  lines.push('- 仍无法确认时，在 `match_skills` 的 `match_note` 写明 `code_source_unresolved`，继续正常分析流程，不要中止。')
  lines.push('- 禁止把该线索当成已验证的代码事实。')
  lines.push('')
  return lines.join('\n')
}

/** 报告落盘用快照（结构与 CodeSourceRef 一致，显式列字段避免带上意外属性） */
export function snapshotCodeSourceForReport(ref?: CodeSourceRef): Record<string, unknown> | undefined {
  if (!ref) return undefined
  return {
    raw: ref.raw,
    kind: ref.kind,
    path: ref.path,
    exists: ref.exists,
    branch: ref.branch,
    file_path: ref.filePath,
    start_line: ref.startLine,
    branch_known: ref.branchKnown,
  }
}

/** 从报告 JSON 恢复（兼容旧报告无此字段，以及只存了原始字符串的情况） */
export function restoreCodeSourceFromReport(raw: unknown): CodeSourceRef | undefined {
  if (!raw) return undefined
  if (typeof raw === 'string') return parseCodeSource(raw)
  if (typeof raw !== 'object') return undefined
  const o = raw as Record<string, unknown>
  const text = typeof o.raw === 'string' ? o.raw.trim() : ''
  if (!text) return undefined
  // 以原始输入重新判型：路径存在性等探测结果需按当前环境刷新
  return parseCodeSource(text)
}
