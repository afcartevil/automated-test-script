#!/usr/bin/env node
/**
 * BFF 监督进程：以非 detached 子进程拉起 dist/server，捕获 exit code / signal。
 * JS uncaughtException 抓不到的 native / taskkill 类退出，至少能留下退出码与系统侧诊断。
 *
 * 环境变量（由 tahp-console start 注入）：
 *   TAHP_BFF_SERVER_ENTRY  服务入口 js
 *   TAHP_BFF_LOG_FILE      server.log
 *   TAHP_BFF_PID_FILE      server.pid（写入**子进程** PID，供 stop/tray 使用）
 *   TAHP_CONSOLE_HOME
 */
import { spawn } from 'child_process'
import { openSync, writeFileSync, mkdirSync, existsSync, readFileSync, unlinkSync } from 'fs'
import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'
import { isProcessRunning } from './tray-actions.mjs'
import { recordUnexpectedExit, isExpectedExit } from './crash-log.mjs'

const serverEntry = process.env.TAHP_BFF_SERVER_ENTRY?.trim()
const logFile = process.env.TAHP_BFF_LOG_FILE?.trim()
const pidFile = process.env.TAHP_BFF_PID_FILE?.trim()
const consoleHome = process.env.TAHP_CONSOLE_HOME?.trim()

if (!serverEntry || !logFile || !pidFile) {
  console.error('[bff-supervisor] missing TAHP_BFF_SERVER_ENTRY / LOG_FILE / PID_FILE')
  process.exit(1)
}

mkdirSync(dirname(pidFile), { recursive: true })
mkdirSync(dirname(logFile), { recursive: true })

const logFd = openSync(logFile, 'a')
const childEnv = { ...process.env }
delete childEnv.TAHP_BFF_SERVER_ENTRY

const child = spawn(process.execPath, [serverEntry], {
  stdio: ['ignore', logFd, logFd],
  env: childEnv,
  windowsHide: true,
})

writeFileSync(pidFile, `${child.pid}\n`, 'utf8')

function spawnWatchdog(pid) {
  const watchdog = resolve(fileURLToPath(new URL('.', import.meta.url)), 'bff-watchdog.mjs')
  if (!existsSync(watchdog) || !pid) return
  const w = spawn(process.execPath, [watchdog, String(pid)], {
    detached: true,
    stdio: 'ignore',
    env: {
      ...process.env,
      TAHP_CONSOLE_HOME: consoleHome || process.env.TAHP_CONSOLE_HOME,
      HERMES_WEB_UI_HOME: consoleHome || process.env.HERMES_WEB_UI_HOME || process.env.TAHP_CONSOLE_HOME,
    },
    windowsHide: true,
  })
  w.unref()
}

spawnWatchdog(child.pid)

child.on('error', (err) => {
  try {
    recordUnexpectedExit(child.pid || 0, {
      type: 'supervisor-spawn-error',
      detectedBy: 'bff-supervisor',
      error: { message: err.message, stack: err.stack },
    })
  } catch { /* ignore */ }
  process.exit(1)
})

child.on('exit', (code, signal) => {
  const pid = child.pid
  const expected = pid ? isExpectedExit(pid) : false
  if (!expected) {
    try {
      recordUnexpectedExit(pid || 0, {
        type: 'supervisor-exit',
        detectedBy: 'bff-supervisor',
        exitCode: code,
        signal: signal || null,
        note: [
          'BFF 子进程退出且无 graceful/stop-requested 标记。',
          `exitCode=${code ?? 'null'} signal=${signal ?? 'null'}。`,
          '若二者均为 null，多为 Windows 强杀且未产生可观察信号；请结合 host/winEvents 与 server.log。',
        ].join(' '),
      })
    } catch (err) {
      console.error('[bff-supervisor] failed to write crash log:', err)
    }
  }
  try {
    if (pid && !isProcessRunning(pid)) {
      const cur = parseInt(readFileSync(pidFile, 'utf8').trim(), 10)
      if (cur === pid) unlinkSync(pidFile)
    }
  } catch { /* stop 可能已删 pid 文件 */ }
  process.exit(0)
})
