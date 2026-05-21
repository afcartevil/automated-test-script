/**
 * TAHP 路径解析 — 集中处理 tahp-mcp-server / scripts / constraints / playbooks / reports 等位置。
 *
 * 优先级:
 *   1. 环境变量 (TAHP_PROJECT_ROOT / TAHP_PYTHON / TAHP_MCP_SERVER)
 *   2. 自动推断 (tahp-console 上级目录)
 */
import { existsSync } from 'fs'
import { resolve, dirname, join } from 'path'

function deriveProjectRoot(): string {
  if (process.env.TAHP_PROJECT_ROOT) return resolve(process.env.TAHP_PROJECT_ROOT)
  // dist/server/index.js 或 packages/server/src/services/tahp/paths.ts → 工程根
  const candidates = [
    resolve(__dirname, '..', '..', '..', '..', '..'),  // dist 模式
    resolve(__dirname, '..', '..', '..', '..', '..', '..'),  // src 模式
  ]
  for (const c of candidates) {
    if (existsSync(join(c, 'tahp-mcp-server', 'server.py'))) return c
  }
  return candidates[0]
}

const projectRoot = deriveProjectRoot()

export const tahpPaths = {
  projectRoot,
  python: process.env.TAHP_PYTHON || (process.platform === 'win32' ? 'python' : 'python3'),
  mcpServer: process.env.TAHP_MCP_SERVER
    ? resolve(process.env.TAHP_MCP_SERVER)
    : join(projectRoot, 'tahp-mcp-server', 'server.py'),
  constraintsDir: join(projectRoot, 'constraints'),
  playbooksDir: join(projectRoot, 'playbooks'),
  knowledgeDir: join(projectRoot, 'knowledge-base'),
  reportsDir: join(projectRoot, 'reports'),
  scriptsDir: join(projectRoot, 'scripts'),
  toolsDir: join(projectRoot, 'tools'),
}

export function hasTahpProject(): boolean {
  return existsSync(tahpPaths.mcpServer)
}
