#!/usr/bin/env node
/**
 * 开发模式有序启动：
 *   1. 后端 (nodemon → 8650)
 *   2. 轮询 /health 就绪
 *   3. 前端 (Vite → 5173)
 *
 * 避免 Vite 代理在后端未监听时大量 ECONNREFUSED / 502。
 * 环境变量：
 *   TAHP_OPEN_BROWSER=0  — 不自动打开浏览器
 *   TAHP_DEV_URL         — 浏览器地址，默认 http://localhost:5173
 *   PORT                 — 后端端口，默认 8650
 */
import { spawn, execSync } from 'child_process'
import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'
import { freePort } from './lib/free-port.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = resolve(__dirname, '..')
const PORT = String(process.env.PORT || '8650')
const healthUrl = `http://127.0.0.1:${PORT}/health`
const clientUrl = process.env.TAHP_DEV_URL || 'http://localhost:5173'
const openBrowser = process.env.TAHP_OPEN_BROWSER !== '0'
const isWin = process.platform === 'win32'

/** @type {import('child_process').ChildProcess[]} */
const children = []

function spawnNpm(script) {
  const child = spawn(isWin ? 'npm.cmd' : 'npm', ['run', script], {
    cwd: root,
    stdio: 'inherit',
    shell: isWin,
    env: process.env,
  })
  children.push(child)
  return child
}

async function waitForHealth(maxMs = 120000, intervalMs = 500) {
  const deadline = Date.now() + maxMs
  process.stdout.write(`[dev] 等待后端就绪 ${healthUrl}`)
  while (Date.now() < deadline) {
    try {
      const res = await fetch(healthUrl, { signal: AbortSignal.timeout(2500) })
      if (res.ok) {
        process.stdout.write('\n')
        return true
      }
    } catch {
      // 后端尚未监听
    }
    process.stdout.write('.')
    await new Promise(r => setTimeout(r, intervalMs))
  }
  process.stdout.write('\n')
  return false
}

function openBrowserUrl(url) {
  try {
    if (isWin) execSync(`start "" "${url}"`, { stdio: 'ignore' })
    else if (process.platform === 'darwin') execSync(`open "${url}"`, { stdio: 'ignore' })
    else execSync(`xdg-open "${url}"`, { stdio: 'ignore' })
  } catch {
    // 忽略无法打开浏览器
  }
}

function shutdown() {
  for (const child of children) {
    try {
      if (isWin) spawn('taskkill', ['/pid', String(child.pid), '/t', '/f'], { stdio: 'ignore', windowsHide: true })
      else child.kill('SIGTERM')
    } catch {
      try { child.kill('SIGKILL') } catch { /* ignore */ }
    }
  }
}

let exiting = false
function exitOnce(code) {
  if (exiting) return
  exiting = true
  shutdown()
  setTimeout(() => process.exit(code), 400)
}

console.log('[dev] 启动顺序: 释放端口 → 后端 → 健康检查 → 前端')
console.log('[dev] 首次启动含 Agent 环境检查，约需 5–15 秒，请稍候…')

const portNum = parseInt(PORT, 10)
freePort(portNum)
freePort(5173)

const server = spawnNpm('dev:server')
const ready = await waitForHealth()

if (!ready) {
  console.warn('[dev] 警告: 后端在超时内未通过健康检查，仍将启动前端（可能出现短暂代理错误）')
} else {
  console.log('[dev] 后端已就绪，启动前端 Vite…')
}

const client = spawnNpm('dev:client')

if (openBrowser) {
  setTimeout(() => {
    console.log(`[dev] 打开浏览器 ${clientUrl}`)
    openBrowserUrl(clientUrl)
  }, 2000)
}

server.on('exit', (code) => {
  if (code) console.error(`[dev] 后端进程退出 code=${code}`)
  exitOnce(code ?? 1)
})

client.on('exit', (code) => {
  if (code) console.error(`[dev] 前端进程退出 code=${code}`)
  exitOnce(code ?? 0)
})

process.on('SIGINT', () => exitOnce(0))
process.on('SIGTERM', () => exitOnce(0))
