#!/usr/bin/env node
/**
 * 从 run_adapter.bat 以无窗口方式拉起托盘（单实例）。
 */
import { spawn } from 'child_process'
import { existsSync, openSync } from 'fs'
import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'
import {
  getTrayIconPath,
  getTrayLogFile,
  isTrayEnabled,
  readTrayPid,
  isProcessRunning,
  shouldRestartTray,
  stopTray,
} from './tray-actions.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const consoleRoot = resolve(__dirname, '..', '..')
const trayEntry = resolve(consoleRoot, 'bin', 'easyadapter-tray.mjs')
const logPrefix = '[EasyAdapter]'

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function main() {
  if (process.platform !== 'win32') {
    process.exit(0)
  }
  if (!isTrayEnabled()) {
    console.log(`${logPrefix} 托盘已禁用 (TAHP_TRAY=0)`)
    process.exit(0)
  }
  if (!existsSync(trayEntry)) {
    console.error(`${logPrefix} 未找到托盘入口: ${trayEntry}`)
    process.exit(1)
  }

  const iconPath = getTrayIconPath()
  if (!existsSync(iconPath)) {
    console.error(`${logPrefix} 托盘图标不存在: ${iconPath}`)
    console.error('  请执行: cd tahp-console && npm run tray:icon')
    process.exit(1)
  }

  if (shouldRestartTray()) {
    const stopped = stopTray()
    if (stopped.stopped) {
      console.log(`${logPrefix} 已停止旧托盘进程`)
      await sleep(300)
    }
  } else {
    const existing = readTrayPid()
    if (existing && isProcessRunning(existing)) {
      console.log(`${logPrefix} 托盘已在运行 (PID: ${existing})`)
      process.exit(0)
    }
  }

  let logFd
  try {
    logFd = openSync(getTrayLogFile(), 'a')
  } catch {
    logFd = 'ignore'
  }

  const child = spawn(process.execPath, [trayEntry], {
    cwd: consoleRoot,
    detached: true,
    stdio: ['ignore', logFd, logFd],
    windowsHide: true,
    env: process.env,
  })
  child.unref()

  await sleep(1000)
  if (!isProcessRunning(child.pid)) {
    console.error(`${logPrefix} 托盘启动后立即退出，请查看: ${getTrayLogFile()}`)
    process.exit(1)
  }

  console.log(`${logPrefix} 托盘已启动 (PID: ${child.pid})`)
}

main().catch((err) => {
  console.error(`${logPrefix} 托盘启动失败:`, err)
  process.exit(1)
})
