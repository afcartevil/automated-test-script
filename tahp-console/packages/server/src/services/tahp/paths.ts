/**
 * TAHP 路径解析 — 集中处理 skills / knowledge-base / reports 等位置。
 *
 * 优先级:
 *   1. 环境变量 TAHP_PROJECT_ROOT
 *   2. 自动推断 (tahp-console 上级目录，含 skills 或 knowledge-base)
 */
import { existsSync } from 'fs'
import { resolve, dirname, join } from 'path'

function isTahpProjectRoot(dir: string): boolean {
  return (
    existsSync(join(dir, 'skills', '.claude', 'skills')) ||
    existsSync(join(dir, 'knowledge-base'))
  )
}

function deriveProjectRoot(): string {
  if (process.env.TAHP_PROJECT_ROOT) return resolve(process.env.TAHP_PROJECT_ROOT)
  const candidates = [
    resolve(__dirname, '..', '..', '..', '..', '..'), // dist 模式
    resolve(__dirname, '..', '..', '..', '..', '..', '..'), // src 模式
  ]
  for (const c of candidates) {
    if (isTahpProjectRoot(c)) return c
  }
  return candidates[0]
}

const projectRoot = deriveProjectRoot()

export const tahpPaths = {
  projectRoot,
  python: process.env.TAHP_PYTHON || (process.platform === 'win32' ? 'python' : 'python3'),
  knowledgeDir: join(projectRoot, 'knowledge-base'),
  reportsDir: join(projectRoot, 'reports'),
  skillsDir: join(projectRoot, 'skills', '.claude', 'skills'),
  selfCheckDir: join(__dirname, 'self-check'),
}

export function hasTahpProject(): boolean {
  return isTahpProjectRoot(tahpPaths.projectRoot)
}
