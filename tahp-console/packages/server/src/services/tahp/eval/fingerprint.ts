/**
 * 变体指纹 — 让两次评测结果可比。
 *
 * skills_hash 用于区分「skill 改过了」：指纹不同的两次评测，分数差异不能单一归因于模型或 prompt。
 */
import { createHash } from 'crypto'
import { existsSync, readdirSync, statSync } from 'fs'
import { join, relative } from 'path'
import { tahpPaths } from '../paths'

const MAX_WALK_DEPTH = 6

function collectSkillFiles(dir: string, root: string, depth: number, out: string[]): void {
  if (depth > MAX_WALK_DEPTH) return
  let entries: string[]
  try {
    entries = readdirSync(dir)
  } catch {
    return
  }
  for (const entry of entries) {
    const full = join(dir, entry)
    let stat: ReturnType<typeof statSync>
    try {
      stat = statSync(full)
    } catch {
      continue
    }
    if (stat.isDirectory()) {
      collectSkillFiles(full, root, depth + 1, out)
    } else if (entry === 'SKILL.md') {
      const rel = relative(root, full).replace(/\\/g, '/')
      out.push(`${rel}:${stat.size}:${Math.round(stat.mtimeMs)}`)
    }
  }
}

/**
 * skills 目录内容摘要。只统计 SKILL.md（路径 + 体积 + 修改时间），
 * 不读文件内容，289 个 skill 的规模下开销可忽略。
 */
export function computeSkillsHash(skillsDir = tahpPaths.skillsDir): string {
  if (!existsSync(skillsDir)) return 'no-skills'
  const parts: string[] = []
  collectSkillFiles(skillsDir, skillsDir, 0, parts)
  if (!parts.length) return 'no-skills'
  parts.sort()
  return createHash('sha1').update(parts.join('\n')).digest('hex').slice(0, 12)
}
