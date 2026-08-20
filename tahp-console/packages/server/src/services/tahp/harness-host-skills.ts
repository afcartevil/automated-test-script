/**
 * 官方 ASF / Harness Skill 与工程副本边界。
 *
 * - 官方 asf-* / harness-* / transsion-asf / transsion-harness：由 `asf|harness install` 装到本机客户端目录，不随工程分发。
 * - 工程可保留自研封装（如 harness-flash-single-img）。
 */
import { existsSync } from 'fs'
import { homedir } from 'os'
import { join } from 'path'
import { hostCliPrefix } from './host-tool-runtime'

/** 工程内允许保留的 harness 前缀自研 Skill（非官方安装集） */
export const PROJECT_HARNESS_WRAPPER_SKILL_IDS = new Set([
  'harness-flash-single-img',
])

/** 本机客户端 skill 根（相对用户主目录，跨主机可移植） */
export const HARNESS_HOST_SKILL_ROOTS_REL = [
  '.claude/skills',
  '.cursor/skills',
  '.codex/skills',
  '.trae/skills',
] as const

const VIRTUAL_INSTALL_IDS = new Set([
  'transsion-harness-install',
  'transsion-asf-install',
])

export function isOfficialHarnessSkillId(skillId: string): boolean {
  const id = (skillId || '').trim()
  if (!id) return false
  if (PROJECT_HARNESS_WRAPPER_SKILL_IDS.has(id)) return false
  if (VIRTUAL_INSTALL_IDS.has(id)) return false
  if (id === 'transsion-harness' || id === 'transsion-asf') return true
  if (id === 'harness-install' || id === 'asf-install') return true
  return id.startsWith('harness-') || id.startsWith('asf-')
}

/** 提示词中可移植的本机 skill 根写法（勿写死某台机器的绝对路径） */
export function formatHarnessHostSkillRootsForPrompt(): string {
  return HARNESS_HOST_SKILL_ROOTS_REL
    .map(rel => `\`$HOME/${rel.replace(/\\/g, '/')}\`（Windows：\`%USERPROFILE%\\${rel.replace(/\//g, '\\')}\`）`)
    .join('、')
}

export function resolveHarnessHostSkillMd(
  skillId: string,
  homeDir = homedir(),
): string | null {
  for (const rel of HARNESS_HOST_SKILL_ROOTS_REL) {
    const p = join(homeDir, ...rel.split('/'), skillId, 'SKILL.md')
    if (existsSync(p)) return p
  }
  return null
}

export function buildHarnessHostSkillsDirective(): string {
  const prefix = hostCliPrefix()
  return [
    '# 官方 ASF / Harness Skill（本机安装，非工程 skills/）',
    '',
    '- **禁止**在工程 `skills/.claude/skills/` 下查找或 Read 官方 `transsion-asf` / `asf-*` / `transsion-harness` / `harness-*`（自研封装 `harness-flash-single-img` 除外）。',
    `- 官方 Skill 由 \`${prefix} install\` 安装到本机客户端目录：${formatHarnessHostSkillRootsForPrompt()}。`,
    '- 需要某官方子 skill 时，在上述本机目录中 Read 对应 `SKILL.md`（目录名以本机实际为准，可能是 `asf-device` 或 `harness-device`）；找不到则先升级/安装 CLI（见配置检查），不要回退到工程旧副本。',
    `- 执行以本机 \`${prefix}\` CLI 为准（\`asf\` 与 \`harness\` 为同一套命令，优先 \`asf\`）；Skill 文件只提供路由与契约，须与 CLI 版本匹配。`,
    '- 远程 Linux 命令：升级机静默 `asf --json bridge up --session N`（已有 READY session 则跳过）后 `asf --json bridge cmd`；不要打开 Transhell 桌面 / `config ui` / `bridge-serve`。仅当 CLI 仍有 `remote-runner bridge-exec` 时走旧路径。',
    '- ASF Bridge：`zellij ls` 若仍列出 `agent_session1` 但 `list-panes` 超时，那是幽灵 mux。`bridge down --all` **不会**删 idle 槽，不要反复 down。应 `asf --json bridge up --session 2`（或下一个空闲槽）。',
  ].join('\n')
}
