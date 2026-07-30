/**
 * Harness 官方 Skill 与工程副本边界。
 *
 * - 官方 harness-* / transsion-harness：由 `harness install` 装到本机客户端目录，不随工程分发。
 * - 工程可保留自研封装（如 harness-flash-single-img）。
 */
import { existsSync } from 'fs'
import { homedir } from 'os'
import { join } from 'path'

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

export function isOfficialHarnessSkillId(skillId: string): boolean {
  const id = (skillId || '').trim()
  if (!id) return false
  if (PROJECT_HARNESS_WRAPPER_SKILL_IDS.has(id)) return false
  if (id === 'transsion-harness') return true
  if (id === 'transsion-harness-install') return false
  return id.startsWith('harness-')
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
  return [
    '# Harness 官方 Skill（本机安装，非工程 skills/）',
    '',
    '- **禁止**在工程 `skills/.claude/skills/` 下查找或 Read 官方 `transsion-harness` / `harness-*`（自研封装 `harness-flash-single-img` 除外）。',
    `- 官方 Skill 由 \`harness install\` 安装到本机客户端目录：${formatHarnessHostSkillRootsForPrompt()}。`,
    '- 需要某官方子 skill 时，在上述本机目录中 Read 对应 `SKILL.md`；找不到则先升级/安装 harness（见配置检查），不要回退到工程旧副本。',
    '- 执行仍以本机 `harness` CLI 为准；Skill 文件只提供路由与契约，须与 CLI 版本匹配。',
  ].join('\n')
}
