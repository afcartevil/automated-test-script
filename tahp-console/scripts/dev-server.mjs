#!/usr/bin/env node
/** nodemon 入口：先确保 bundled hermes-agent，再启动 TS 服务 */
import { spawn } from 'child_process'
import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'
import { ensureHermesAgent } from './ensure-hermes-agent.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const consoleRoot = resolve(__dirname, '..')

const agent = ensureHermesAgent({ quiet: false })
if (!agent.ok) {
  console.error('\n[dev-server] Hermes Agent 初始化失败，服务仍将启动但 Bridge/Bug 分析可能不可用。\n')
}

const child = spawn(
  process.execPath,
  [
    '-r', 'ts-node/register',
    'packages/server/src/index.ts',
  ],
  {
    cwd: consoleRoot,
    stdio: 'inherit',
    env: { ...process.env, NODE_OPTIONS: '--no-warnings' },
    windowsHide: false,
  },
)

child.on('exit', (code) => process.exit(code ?? 1))
process.on('SIGTERM', () => child.kill('SIGTERM'))
process.on('SIGINT', () => child.kill('SIGINT'))
