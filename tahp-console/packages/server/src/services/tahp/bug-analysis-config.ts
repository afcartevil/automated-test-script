/**
 * 智能诊断 — 远程分析渠道开关
 *
 * 落盘：{TAHP工程根}/.tahp/bug-analysis-config.json
 * 默认两渠道关闭；仅影响 Jira 单条/批量，本地日志模式忽略。
 *
 * 环境变量覆盖（可选，0/false/off 关闭，1/true/on 开启）：
 *   TAHP_BUGFIX_CHANNEL / TAHP_LOGINSIGHT_CHANNEL
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import { tahpPaths } from './paths'
import { getTahpSkillsRoot, tahpSkillMdPath } from './context-injector'

export type RemoteChannelId = 'bugfix_analysis' | 'loginsight_remote'

export interface RemoteChannelConfig {
  enabled: boolean
  /** Skill 目录名（工程 skills 树或外部目录名） */
  skill_id: string
  /**
   * 可选：Skill 根目录绝对路径（SKILL.md 所在目录的父级即 skill 根）。
   * 未配置时优先工程内 `skills/.claude/skills/<skill_id>`。
   */
  skill_path?: string
}

export interface BugAnalysisChannelConfig {
  remote_channels: Record<RemoteChannelId, RemoteChannelConfig>
  updated_at?: string
}

const DEFAULT_CHANNELS: Record<RemoteChannelId, RemoteChannelConfig> = {
  bugfix_analysis: {
    enabled: false,
    skill_id: 'bugfix-analysis',
  },
  loginsight_remote: {
    enabled: false,
    skill_id: 'loginsight-remote-cli',
  },
}

function tahpConfigDir(): string {
  const d = join(tahpPaths.projectRoot, '.tahp')
  if (!existsSync(d)) mkdirSync(d, { recursive: true })
  return d
}

export function bugAnalysisConfigPath(): string {
  return join(tahpConfigDir(), 'bug-analysis-config.json')
}

function parseEnvBool(raw: string | undefined): boolean | undefined {
  if (raw == null || raw === '') return undefined
  const v = raw.trim().toLowerCase()
  if (['0', 'false', 'off', 'no'].includes(v)) return false
  if (['1', 'true', 'on', 'yes'].includes(v)) return true
  return undefined
}

function normalizeChannel(
  id: RemoteChannelId,
  raw: Partial<RemoteChannelConfig> | undefined,
): RemoteChannelConfig {
  const def = DEFAULT_CHANNELS[id]
  const skillId = String(raw?.skill_id || def.skill_id).trim() || def.skill_id
  const skillPath = typeof raw?.skill_path === 'string' ? raw.skill_path.trim() : ''
  return {
    enabled: typeof raw?.enabled === 'boolean' ? raw.enabled : def.enabled,
    skill_id: skillId,
    skill_path: skillPath || undefined,
  }
}

function applyEnvOverrides(cfg: BugAnalysisChannelConfig): BugAnalysisChannelConfig {
  const bugfixEnv = parseEnvBool(process.env.TAHP_BUGFIX_CHANNEL)
  const loginsightEnv = parseEnvBool(process.env.TAHP_LOGINSIGHT_CHANNEL)
  const next = {
    remote_channels: {
      bugfix_analysis: { ...cfg.remote_channels.bugfix_analysis },
      loginsight_remote: { ...cfg.remote_channels.loginsight_remote },
    },
    updated_at: cfg.updated_at,
  }
  if (bugfixEnv !== undefined) next.remote_channels.bugfix_analysis.enabled = bugfixEnv
  if (loginsightEnv !== undefined) next.remote_channels.loginsight_remote.enabled = loginsightEnv
  return next
}

/** 默认配置（两渠道全开） */
export function defaultBugAnalysisChannelConfig(): BugAnalysisChannelConfig {
  return {
    remote_channels: {
      bugfix_analysis: { ...DEFAULT_CHANNELS.bugfix_analysis },
      loginsight_remote: { ...DEFAULT_CHANNELS.loginsight_remote },
    },
  }
}

export function readBugAnalysisChannelConfig(): BugAnalysisChannelConfig {
  const p = bugAnalysisConfigPath()
  let base = defaultBugAnalysisChannelConfig()
  if (existsSync(p)) {
    try {
      const raw = JSON.parse(readFileSync(p, 'utf-8')) as Record<string, unknown>
      const channels = (raw.remote_channels || {}) as Record<string, Partial<RemoteChannelConfig>>
      base = {
        remote_channels: {
          bugfix_analysis: normalizeChannel('bugfix_analysis', channels.bugfix_analysis),
          loginsight_remote: normalizeChannel('loginsight_remote', channels.loginsight_remote),
        },
        updated_at: typeof raw.updated_at === 'string' ? raw.updated_at : undefined,
      }
    } catch {
      /* 损坏文件时回退默认 */
    }
  }
  return applyEnvOverrides(base)
}

export function writeBugAnalysisChannelConfig(input: {
  bugfix_analysis?: boolean
  loginsight_remote?: boolean
  bugfix_skill_path?: string
  loginsight_skill_path?: string
}): BugAnalysisChannelConfig {
  // 写入以磁盘内容 + 入参为准；读时再应用 env 覆盖
  const disk = (() => {
    const p = bugAnalysisConfigPath()
    if (!existsSync(p)) return defaultBugAnalysisChannelConfig()
    try {
      const raw = JSON.parse(readFileSync(p, 'utf-8')) as Record<string, unknown>
      const channels = (raw.remote_channels || {}) as Record<string, Partial<RemoteChannelConfig>>
      return {
        remote_channels: {
          bugfix_analysis: normalizeChannel('bugfix_analysis', channels.bugfix_analysis),
          loginsight_remote: normalizeChannel('loginsight_remote', channels.loginsight_remote),
        },
      } satisfies BugAnalysisChannelConfig
    } catch {
      return defaultBugAnalysisChannelConfig()
    }
  })()

  const next: BugAnalysisChannelConfig = {
    remote_channels: {
      bugfix_analysis: {
        ...disk.remote_channels.bugfix_analysis,
        enabled: typeof input.bugfix_analysis === 'boolean'
          ? input.bugfix_analysis
          : disk.remote_channels.bugfix_analysis.enabled,
        skill_path: input.bugfix_skill_path !== undefined
          ? (input.bugfix_skill_path.trim() || undefined)
          : disk.remote_channels.bugfix_analysis.skill_path,
      },
      loginsight_remote: {
        ...disk.remote_channels.loginsight_remote,
        enabled: typeof input.loginsight_remote === 'boolean'
          ? input.loginsight_remote
          : disk.remote_channels.loginsight_remote.enabled,
        skill_path: input.loginsight_skill_path !== undefined
          ? (input.loginsight_skill_path.trim() || undefined)
          : disk.remote_channels.loginsight_remote.skill_path,
      },
    },
    updated_at: new Date().toISOString(),
  }

  writeFileSync(bugAnalysisConfigPath(), JSON.stringify(next, null, 2), 'utf-8')
  // 返回带 env 覆盖的生效配置（与 read 一致）
  return applyEnvOverrides(next)
}

/** 解析 Skill 可读路径（绝对路径，供 Agent Read） */
export function resolveRemoteSkillPath(ch: RemoteChannelConfig): {
  skillId: string
  skillMdPath: string | null
  found: boolean
} {
  const skillId = ch.skill_id
  const candidates: string[] = []
  if (ch.skill_path?.trim()) {
    const root = ch.skill_path.trim()
    candidates.push(join(root, 'SKILL.md'))
    candidates.push(root.endsWith('SKILL.md') ? root : join(root, 'SKILL.md'))
  }
  candidates.push(tahpSkillMdPath(skillId))
  // 兼容偶发放在工程根 skills 旁
  candidates.push(join(getTahpSkillsRoot(), skillId, 'SKILL.md'))

  for (const p of candidates) {
    if (existsSync(p)) {
      return { skillId, skillMdPath: p, found: true }
    }
  }
  return { skillId, skillMdPath: null, found: false }
}

export function listEnabledRemotePreferredSkillIds(
  cfg: BugAnalysisChannelConfig = readBugAnalysisChannelConfig(),
): string[] {
  const ids: string[] = []
  for (const id of ['loginsight_remote', 'bugfix_analysis'] as RemoteChannelId[]) {
    const ch = cfg.remote_channels[id]
    if (ch.enabled) ids.push(ch.skill_id)
  }
  return ids
}

/**
 * 注入到智能诊断（Jira 单条/批量）系统提示词的远程渠道硬规则。
 * 本地模式勿调用。
 */
export function buildRemoteChannelDirective(
  cfg: BugAnalysisChannelConfig = readBugAnalysisChannelConfig(),
): string {
  const bugfix = cfg.remote_channels.bugfix_analysis
  const loginsight = cfg.remote_channels.loginsight_remote
  const bugfixRes = resolveRemoteSkillPath(bugfix)
  const loginsightRes = resolveRemoteSkillPath(loginsight)

  const lines: string[] = [
    '# 远程分析渠道（本任务生效 · 硬规则）',
    '',
    `| 渠道 | 开关 | skillId | SKILL.md |`,
    `| --- | --- | --- | --- |`,
    `| bugfix_analysis（通用缺陷） | ${bugfix.enabled ? 'enabled' : 'disabled'} | \`${bugfix.skill_id}\` | ${bugfixRes.found ? `\`${bugfixRes.skillMdPath}\`` : '**未找到**'} |`,
    `| loginsight_remote（稳定性） | ${loginsight.enabled ? 'enabled' : 'disabled'} | \`${loginsight.skill_id}\` | ${loginsightRes.found ? `\`${loginsightRes.skillMdPath}\`` : '**未找到**'} |`,
    '',
    '## 执行顺序（仅 Jira 在线分析；本地日志模式不适用）',
    '',
    '在完成 Step 1（`fetch_jira`）之后、进入本地 Step 2（`download_logs`）之前，必须按下列规则决策：',
    '',
  ]

  const anyEnabled = bugfix.enabled || loginsight.enabled
  if (!anyEnabled) {
    lines.push(
      '1. **两渠道均 disabled**：禁止调用任何远程分析平台 Skill。',
      '2. 直接进入现有本地流程：`download_logs` → `match_skills` → `analyze` → `generate_report`。',
      '',
    )
    return lines.join('\n')
  }

  lines.push('1. 根据 JIRA **标题 + 描述 + 评论 + 标签/组件** 判断问题类型：')
  lines.push('   - **稳定性**（KE / HWT / Hang / NE / ANR / reboot / crash / panic / watchdog / 稳定性等）→ 优先 `loginsight_remote`')
  lines.push('   - **其它类型** → 优先 `bugfix_analysis`')
  lines.push('2. 仅可调用 **enabled** 且 SKILL.md 已找到的渠道；`disabled` 或文件缺失的渠道**禁止**尝试。')
  lines.push('3. 选定渠道后：')
  lines.push('   - **必须 Read** 对应 `SKILL.md` 全文，严格按 SOP 用 CLI 触发远程分析并取回报告。')
  lines.push('   - 远程成功：将平台报告整理为完整 **9 节** Markdown（含第 9 节 Jira 备注），输出 `match_skills`（`matched_skills` 填远程 skillId）、`analyze`、`generate_report` 标记；')
  lines.push('     **可跳过**本地 `download_logs` 与本地领域 Skill 深挖（在 `download_logs` 标记中说明 `logs_downloaded: false`，`message` 写「远程渠道成功，跳过本地日志下载」）。')
  lines.push('4. **失败判定**（任一即回退本地）：CLI 非 0、超时、无分析正文/`analysis_markdown`、平台不可达、Skill 文件缺失、凭据未配置。')
  lines.push('5. 回退本地：按原五步继续 `download_logs` → 匹配工程内领域 Skill → `analyze` → `generate_report`；在 `match_skills` 的 `match_note` 写明 `remote_fallback: <原因>`。')
  lines.push('6. 若目标渠道 disabled，而另一渠道 enabled：仅当问题类型匹配该渠道时才调用，否则直接本地流程。')
  lines.push('7. 两渠道都 enabled 但首选失败：可再试另一渠道一次；仍失败则本地回退。勿无限重试。')
  lines.push('')

  if (bugfix.enabled && !bugfixRes.found) {
    lines.push(`> 警告：bugfix_analysis 已启用但未找到 \`${bugfix.skill_id}/SKILL.md\`。请将 Skill 同步到 \`${getTahpSkillsRoot()}\` 或在配置中设置 \`skill_path\`。本任务视该渠道为不可用并回退。`)
    lines.push('')
  }
  if (loginsight.enabled && !loginsightRes.found) {
    lines.push(`> 警告：loginsight_remote 已启用但未找到 \`${loginsight.skill_id}/SKILL.md\`。请将 Skill 同步到 \`${getTahpSkillsRoot()}\` 或在配置中设置 \`skill_path\`。本任务视该渠道为不可用并回退。`)
    lines.push('')
  }

  return lines.join('\n')
}

/** 供报告落盘的渠道快照 */
export function snapshotRemoteChannelsForReport(
  cfg: BugAnalysisChannelConfig = readBugAnalysisChannelConfig(),
): Record<string, unknown> {
  return {
    bugfix_analysis: {
      enabled: cfg.remote_channels.bugfix_analysis.enabled,
      skill_id: cfg.remote_channels.bugfix_analysis.skill_id,
      skill_found: resolveRemoteSkillPath(cfg.remote_channels.bugfix_analysis).found,
    },
    loginsight_remote: {
      enabled: cfg.remote_channels.loginsight_remote.enabled,
      skill_id: cfg.remote_channels.loginsight_remote.skill_id,
      skill_found: resolveRemoteSkillPath(cfg.remote_channels.loginsight_remote).found,
    },
  }
}
